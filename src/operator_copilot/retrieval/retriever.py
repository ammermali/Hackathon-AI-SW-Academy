"""Hybrid Dense (ChromaDB) + Sparse (BM25) retriever with metadata filtering and abstention threshold."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.retrieval.embeddings import get_cached_embeddings
from operator_copilot.retrieval.reranker import (
    _CONVERSATIONAL_FILLER,
    _ITALIAN_STOPWORDS,
    DocumentReranker,
    RankedCandidate,
    normalize_retrieval_query,
)

logger = logging.getLogger("operator_copilot.retrieval.retriever")


@dataclass
class RetrievedChunk:
    """Final retrieved document chunk with relevance score."""

    document: Document
    relevance_score: float
    dense_score: float
    bm25_score: float


class HybridRetriever:
    """Combines ChromaDB cosine similarity with BM25 lexical matching and optional reranking."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.reranker = DocumentReranker()

        self._bm25: BM25Okapi | None = None
        self._bm25_docs: list[Document] = []
        self._bm25_corpus_version: str = ""
        self._bm25_lock = threading.Lock()

    def _get_vectorstore(self) -> Chroma:
        embeddings = get_cached_embeddings(
            self.settings.embedding_provider,
            self.settings.embedding_model,
        )
        return Chroma(
            collection_name=self.settings.collection_name,
            embedding_function=embeddings,
            persist_directory=str(self.settings.vectorstore_path),
            collection_metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        tokens = re.findall(r"\b[a-z0-9_\-\.+]{2,}\b", text.lower())
        return [t for t in tokens if t not in _ITALIAN_STOPWORDS and t not in _CONVERSATIONAL_FILLER]

    @staticmethod
    def _build_chroma_where(filters: dict[str, Any] | None) -> dict[str, Any] | None:
        """Convert plain metadata dict to ChromaDB `where` clause."""
        if not filters:
            return None
        clean = {
            k: v
            for k, v in filters.items()
            if isinstance(v, (str, int, float, bool)) and v != ""
        }
        if not clean:
            return None
        if len(clean) == 1:
            return clean
        return {"$and": [{k: v} for k, v in clean.items()]}

    @staticmethod
    def _matches_filters(meta: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        for k, v in filters.items():
            if isinstance(v, (str, int, float, bool)) and v != "" and meta.get(k) != v:
                return False
        return True

    def _ensure_bm25_index(self, vectorstore: Chroma) -> tuple[BM25Okapi | None, list[Document]]:
        """Thread-safely load/refresh BM25 index whenever corpus_version changes."""
        with self._bm25_lock:
            current_version = self.db.get_corpus_version()
            if self._bm25 is not None and self._bm25_corpus_version == current_version:
                return self._bm25, self._bm25_docs

            raw = vectorstore.get(include=["documents", "metadatas"])
            docs_text = raw.get("documents") or []
            metas = raw.get("metadatas") or []

            docs_list = [
                Document(page_content=txt, metadata=meta or {})
                for txt, meta in zip(docs_text, metas)
            ]

            if docs_list:
                tokenized_corpus = [self._tokenize(d.page_content) for d in docs_list]
                bm25_model: BM25Okapi | None = BM25Okapi(tokenized_corpus)
            else:
                bm25_model = None

            self._bm25_docs = docs_list
            self._bm25 = bm25_model
            self._bm25_corpus_version = current_version
            logger.info("BM25 index synced for corpus_version=%s (%d chunks)", current_version, len(docs_list))
            return bm25_model, docs_list

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks above threshold using hybrid dense + sparse fusion."""
        k = top_k or self.settings.retrieval_top_k
        threshold = self.settings.retrieval_score_threshold if score_threshold is None else score_threshold
        effective_query = normalize_retrieval_query(query)

        vectorstore = self._get_vectorstore()
        collection_count = vectorstore._collection.count()
        if collection_count == 0:
            logger.warning("Vector store collection is empty.")
            return []

        candidate_k = min(collection_count, max(k * 8, 40))
        where_clause = self._build_chroma_where(filters)

        embeddings_fn = vectorstore.embeddings
        query_vec: list[float] | None = None
        if embeddings_fn is not None:
            query_vec = embeddings_fn.embed_query(effective_query)

        # 1. Dense search via Chroma cosine distance -> similarity [0, 1]
        try:
            if query_vec is not None:
                dense_hits = vectorstore._collection.query(
                    query_embeddings=[query_vec],
                    n_results=candidate_k,
                    where=where_clause,
                    include=["documents", "metadatas", "distances"],
                )
            else:
                dense_hits = None
        except Exception as exc:
            logger.error("Chroma search failed: %s", exc)
            dense_hits = None

        candidates_map: dict[str, RankedCandidate] = {}
        if isinstance(dense_hits, dict):
            docs_list = (dense_hits.get("documents") or [[]])[0]
            metas_list = (dense_hits.get("metadatas") or [[]])[0]
            dists_list = (dense_hits.get("distances") or [[]])[0]
            for txt, meta, distance in zip(docs_list, metas_list, dists_list):
                doc = Document(page_content=txt, metadata=meta or {})
                chunk_id = str(doc.metadata.get("chunk_id") or hash(txt))
                dense_sim = max(0.0, min(1.0, 1.0 - float(distance)))
                candidates_map[chunk_id] = RankedCandidate(
                    document=doc,
                    dense_score=dense_sim,
                    bm25_score=0.0,
                    final_score=dense_sim,
                )

        # 2. Sparse BM25 lexical fusion (if enabled)
        w_bm25 = self.settings.hybrid_bm25_weight
        bm25_only_ids: list[str] = []
        if w_bm25 > 0:
            bm25_model, bm25_docs = self._ensure_bm25_index(vectorstore)
            if bm25_model is not None and bm25_docs:
                q_tokens = self._tokenize(effective_query)
                if q_tokens:
                    bm25_raw_scores = bm25_model.get_scores(q_tokens)
                    scored_indices = sorted(
                        range(len(bm25_raw_scores)),
                        key=lambda i: bm25_raw_scores[i],
                        reverse=True,
                    )
                    added = 0
                    for idx in scored_indices:
                        raw_s = float(bm25_raw_scores[idx])
                        if raw_s <= 0.0:
                            break
                        doc = bm25_docs[idx]
                        if not self._matches_filters(doc.metadata, filters):
                            continue
                        bm25_norm = raw_s / (raw_s + 6.0)
                        cid = str(doc.metadata.get("chunk_id") or hash(doc.page_content))
                        if cid in candidates_map:
                            candidates_map[cid].bm25_score = bm25_norm
                        else:
                            candidates_map[cid] = RankedCandidate(
                                document=doc,
                                dense_score=0.0,
                                bm25_score=bm25_norm,
                                final_score=0.0,
                            )
                            bm25_only_ids.append(cid)
                        added += 1
                        if added >= candidate_k:
                            break

        # Hydrate true dense similarity for BM25-only hits so they are never penalized with 0.0
        if bm25_only_ids and query_vec is not None:
            hydrated_ids: set[str] = set()
            try:
                fetched = vectorstore._collection.get(ids=bm25_only_ids, include=["embeddings"])
                fetched_ids = fetched.get("ids") or []
                fetched_embs = fetched.get("embeddings")
                if fetched_embs is not None:
                    for fid, emb in zip(fetched_ids, fetched_embs):
                        if fid in candidates_map and emb is not None:
                            dot = sum(float(a) * float(b) for a, b in zip(query_vec, emb))
                            candidates_map[fid].dense_score = max(0.0, min(1.0, dot))
                            hydrated_ids.add(fid)
            except Exception as exc:
                logger.debug("Chroma get(embeddings) fallback triggered for BM25-only hits: %s", exc)

            missing_ids = [cid for cid in bm25_only_ids if cid not in hydrated_ids]
            if missing_ids and embeddings_fn is not None:
                try:
                    texts = [candidates_map[cid].document.page_content for cid in missing_ids]
                    if hasattr(embeddings_fn, "embed_documents"):
                        doc_vecs = embeddings_fn.embed_documents(texts)
                    else:
                        doc_vecs = [embeddings_fn.embed_query(t) for t in texts]
                    for cid, emb in zip(missing_ids, doc_vecs):
                        dot = sum(float(a) * float(b) for a, b in zip(query_vec, emb))
                        candidates_map[cid].dense_score = max(0.0, min(1.0, dot))
                except Exception as exc:
                    logger.warning("Could not compute fallback embeddings for BM25-only hits: %s", exc)

        # Compute combined hybrid score
        for cand in candidates_map.values():
            cand.final_score = round(
                (1.0 - w_bm25) * cand.dense_score + w_bm25 * cand.bm25_score,
                4,
            )

        # Filter by relevance threshold BEFORE returning (abstention safety)
        qualified = [c for c in candidates_map.values() if c.final_score >= threshold]
        if not qualified:
            logger.info("No chunks met retrieval threshold %.3f for query.", threshold)
            return []

        if self.settings.reranker_enabled:
            ranked = self.reranker.rerank(effective_query, qualified, top_k=k)
        else:
            ranked = sorted(qualified, key=lambda c: c.final_score, reverse=True)[:k]

        return [
            RetrievedChunk(
                document=c.document,
                relevance_score=c.final_score,
                dense_score=c.dense_score,
                bm25_score=c.bm25_score,
            )
            for c in ranked
        ]
