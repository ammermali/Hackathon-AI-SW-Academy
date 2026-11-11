"""Incremental and rebuildable ChromaDB indexing pipeline."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import DocumentMetadata
from operator_copilot.ingestion.chunker import DocumentChunker
from operator_copilot.ingestion.loaders import DocumentLoader, LoadError, LoadedDocument
from operator_copilot.ingestion.normalizer import ContentNormalizer
from operator_copilot.ingestion.scanner import DataScanner
from operator_copilot.retrieval.embeddings import get_cached_embeddings
from operator_copilot.schemas.response import IngestResponse

logger = logging.getLogger("operator_copilot.ingestion.indexer")


class DocumentIndexer:
    """Manages incremental and full-rebuild ingestion into ChromaDB and SQLite metadata."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.normalizer = ContentNormalizer()
        self.scanner = DataScanner(
            self.settings.data_dir,
            skip_index_files=self.settings.skip_index_files,
        )
        self.loader = DocumentLoader(self.normalizer)
        self.chunker = DocumentChunker(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )

    def _get_vectorstore(self) -> Chroma:
        """Return persistent Chroma vector store configured with cosine similarity."""
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

    def _delete_doc_chunks(self, vectorstore: Chroma, document_id: str) -> None:
        """Delete all existing chunks belonging to document_id from Chroma."""
        try:
            existing = vectorstore.get(where={"document_id": document_id}, include=[])
            ids = existing.get("ids") or []
            if ids:
                vectorstore.delete(ids=ids)
        except Exception as exc:
            logger.debug("No chunks deleted for document_id=%s: %s", document_id, exc)

    def run_ingestion(self, rebuild: bool = False, max_files: int | None = None) -> IngestResponse:
        """Execute incremental or full ingestion of data_dir."""
        t0 = time.perf_counter()

        if rebuild and self.settings.vectorstore_path.exists():
            logger.info("Rebuild requested: clearing vectorstore at %s", self.settings.vectorstore_path)
            shutil.rmtree(self.settings.vectorstore_path, ignore_errors=True)
            self.settings.vectorstore_path.mkdir(parents=True, exist_ok=True)
            with self.db.session() as db:
                db.query(DocumentMetadata).delete()
                db.commit()

        scanned_files = self.scanner.scan(max_files=max_files)
        vectorstore = self._get_vectorstore()

        with self.db.session() as db:
            existing_by_source: dict[str, DocumentMetadata] = {
                row.source: row for row in db.query(DocumentMetadata).all()
            }

        scanned_sources = {sf.relative_path for sf in scanned_files}
        corpus_changed = rebuild

        # Handle deleted files
        deleted_sources = [src for src in existing_by_source if src not in scanned_sources]
        if deleted_sources and max_files is None:
            with self.db.session() as db:
                for src in deleted_sources:
                    row = db.query(DocumentMetadata).filter_by(source=src).first()
                    if row:
                        self._delete_doc_chunks(vectorstore, row.document_id)
                        db.delete(row)
                        corpus_changed = True
                db.commit()

        # Track seen normalized hashes and titles for duplicate detection
        seen_norm_hashes: dict[str, str] = {}
        seen_by_title: dict[str, list[str]] = defaultdict(list)

        if not rebuild:
            for src, row in existing_by_source.items():
                if row.status == "indexed" and src in scanned_sources:
                    seen_norm_hashes[row.normalized_hash] = src

        files_indexed = 0
        files_skipped_unchanged = 0
        files_skipped_duplicate = 0
        files_failed = 0
        chunks_created = 0

        pending_chunks: list[Document] = []
        pending_ids: list[str] = []

        for sf in scanned_files:
            existing = existing_by_source.get(sf.relative_path)
            if not rebuild and existing and existing.file_hash == sf.file_hash:
                if existing.status == "indexed":
                    files_skipped_unchanged += 1
                    continue
                if existing.status == "skipped_duplicate":
                    files_skipped_duplicate += 1
                    continue

            loaded_or_err = self.loader.load(sf)
            if isinstance(loaded_or_err, LoadError):
                files_failed += 1
                self._upsert_doc_metadata(
                    document_id=loaded_or_err.document_id,
                    source=loaded_or_err.source,
                    file_hash=loaded_or_err.file_hash,
                    normalized_hash="",
                    document_type="unknown",
                    area_name=None,
                    doc_year=None,
                    chunk_count=0,
                    status="unreadable",
                    error_message=loaded_or_err.error,
                )
                continue

            doc: LoadedDocument = loaded_or_err

            # 1. Exact canonical hash deduplication
            is_dup = False
            dup_reason = ""
            if doc.normalized_hash in seen_norm_hashes and seen_norm_hashes[doc.normalized_hash] != doc.source:
                is_dup = True
                dup_reason = f"Exact canonical duplicate of {seen_norm_hashes[doc.normalized_hash]}"

            # 2. Near-duplicate check across files sharing identical title
            title_key = str(doc.metadata.get("title", "")).strip().lower()
            if not is_dup and self.settings.dedup_near_duplicates and title_key:
                for prev_canon in seen_by_title.get(title_key, []):
                    sim = self.normalizer.jaccard_similarity(doc.canonical_content, prev_canon, k=5)
                    if sim >= self.settings.near_dup_threshold:
                        is_dup = True
                        dup_reason = f"Near-duplicate (Jaccard={sim:.2f}) of document with same title '{title_key}'"
                        break

            if is_dup:
                files_skipped_duplicate += 1
                if existing and existing.status == "indexed":
                    self._delete_doc_chunks(vectorstore, doc.document_id)
                    corpus_changed = True
                self._upsert_doc_metadata(
                    document_id=doc.document_id,
                    source=doc.source,
                    file_hash=doc.file_hash,
                    normalized_hash=doc.normalized_hash,
                    document_type=str(doc.metadata.get("document_type", "manual")),
                    area_name=doc.metadata.get("area_name"),
                    doc_year=doc.metadata.get("doc_year"),
                    chunk_count=0,
                    status="skipped_duplicate",
                    error_message=dup_reason,
                )
                continue

            # Unique or updated document -> index
            seen_norm_hashes[doc.normalized_hash] = doc.source
            if title_key:
                seen_by_title[title_key].append(doc.canonical_content)

            if existing:
                self._delete_doc_chunks(vectorstore, doc.document_id)

            doc_chunks = self.chunker.chunk_document(doc)
            for c in doc_chunks:
                pending_chunks.append(c)
                pending_ids.append(c.metadata["chunk_id"])

            files_indexed += 1
            chunks_created += len(doc_chunks)
            corpus_changed = True

            self._upsert_doc_metadata(
                document_id=doc.document_id,
                source=doc.source,
                file_hash=doc.file_hash,
                normalized_hash=doc.normalized_hash,
                document_type=str(doc.metadata.get("document_type", "manual")),
                area_name=doc.metadata.get("area_name"),
                doc_year=doc.metadata.get("doc_year"),
                chunk_count=len(doc_chunks),
                status="indexed",
                error_message=None,
            )

            # Flush in batches to keep memory bounded
            if len(pending_chunks) >= 256:
                vectorstore.add_documents(documents=pending_chunks, ids=pending_ids)
                pending_chunks.clear()
                pending_ids.clear()

        if pending_chunks:
            vectorstore.add_documents(documents=pending_chunks, ids=pending_ids)

        if corpus_changed:
            new_version = f"v_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            self.db.set_state("corpus_version", new_version)
        else:
            new_version = self.db.get_corpus_version()

        self.db.set_state("last_indexed_at", datetime.now(timezone.utc).isoformat())
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        logger.info(
            "Ingestion done: scanned=%d indexed=%d unchanged=%d duplicates=%d failed=%d chunks=%d time_ms=%d",
            len(scanned_files),
            files_indexed,
            files_skipped_unchanged,
            files_skipped_duplicate,
            files_failed,
            chunks_created,
            elapsed_ms,
        )

        return IngestResponse(
            status="completed",
            corpus_version=new_version,
            files_scanned=len(scanned_files),
            files_indexed=files_indexed,
            files_skipped_unchanged=files_skipped_unchanged,
            files_skipped_duplicate=files_skipped_duplicate,
            files_failed=files_failed,
            chunks_created=chunks_created,
            processing_time_ms=elapsed_ms,
        )

    def _upsert_doc_metadata(
        self,
        *,
        document_id: str,
        source: str,
        file_hash: str,
        normalized_hash: str,
        document_type: str,
        area_name: str | None,
        doc_year: int | None,
        chunk_count: int,
        status: str,
        error_message: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.db.session() as db:
            row = db.query(DocumentMetadata).filter_by(source=source).first()
            if row is None:
                db.add(
                    DocumentMetadata(
                        document_id=document_id,
                        source=source,
                        file_hash=file_hash,
                        normalized_hash=normalized_hash,
                        document_type=document_type,
                        area_name=area_name,
                        doc_year=doc_year,
                        chunk_count=chunk_count,
                        status=status,
                        error_message=error_message,
                        indexed_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.file_hash = file_hash
                row.normalized_hash = normalized_hash
                row.document_type = document_type
                row.area_name = area_name
                row.doc_year = doc_year
                row.chunk_count = chunk_count
                row.status = status
                row.error_message = error_message
                row.updated_at = now
            db.commit()
