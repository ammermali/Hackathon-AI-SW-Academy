"""Lightweight post-retrieval reranker handling keyword precision, recency, and diversity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document

_ITALIAN_STOPWORDS = {
    "che", "chi", "come", "con", "cosa", "cui", "dal", "dalla", "dalle", "dallo",
    "degli", "dei", "del", "della", "delle", "dello", "devo", "dove", "due", "gli",
    "hai", "hanno", "il", "in", "la", "le", "lo", "ma", "mi", "nel", "nella",
    "nelle", "nello", "non", "per", "piu", "puo", "qual", "quale", "quali", "quando",
    "questo", "questa", "questi", "se", "si", "sono", "su", "sul", "sulla", "tra",
    "un", "una", "uno", "posso", "fare", "essere", "procedura", "errore",
}

_CONVERSATIONAL_FILLER = {
    "yo", "bro", "hey", "ehi", "ciao", "salve", "buongiorno", "buonasera",
    "ragazzi", "raga", "scusa", "scusate", "scusi", "favore", "piacere",
    "gentilmente", "cortesia", "vorrei", "sapere", "sapresti", "potresti",
    "puoi", "dirmi", "spiegami", "spiegarmi", "aiutami", "capire", "aiuto",
    "please", "pls",
}

_LEADING_GREETING_RE = re.compile(
    r"^\s*(?:yo|bro|hey|ehi|ciao|salve|buongiorno|buonasera|raga(?:zzi)?|scusa(?:te|mi)?|per\s+favore|per\s+piacere|gentilmente)(?:[\s,!.:;]+|$)+",
    re.IGNORECASE,
)


def normalize_retrieval_query(query: str) -> str:
    """Strip colloquial greetings/filler while preserving domain terms and uppercase acronyms."""
    raw = (query or "").strip()
    if not raw:
        return ""
    cleaned = raw
    for _ in range(3):
        updated = _LEADING_GREETING_RE.sub("", cleaned).strip()
        if updated == cleaned:
            break
        cleaned = updated

    # Drop isolated filler words from the middle too, keeping uppercase tokens/acronyms intact
    tokens = re.findall(r"\S+", cleaned)
    kept: list[str] = []
    for tok in tokens:
        bare = re.sub(r"^[\W_]+|[\W_]+$", "", tok)
        if bare and not bare.isupper() and bare.lower() in _CONVERSATIONAL_FILLER:
            continue
        kept.append(tok)

    result = re.sub(r"[?!]{2,}", "?", " ".join(kept)).strip()
    return result if len(re.sub(r"\W+", "", result)) >= 2 else re.sub(r"[?!]{2,}", "?", raw)


@dataclass
class RankedCandidate:
    """Intermediate retrieval candidate with multi-signal scoring."""

    document: Document
    dense_score: float
    bm25_score: float
    final_score: float


class DocumentReranker:
    """Reranks candidates using term coverage, exact acronym matches, recency, and doc diversity."""

    def __init__(self, max_chunks_per_doc: int = 2) -> None:
        self.max_chunks_per_doc = max_chunks_per_doc

    @staticmethod
    def _extract_query_terms(query: str) -> list[str]:
        normalized = normalize_retrieval_query(query)
        tokens = re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", normalized.lower())
        return [t for t in tokens if t not in _ITALIAN_STOPWORDS and t not in _CONVERSATIONAL_FILLER]

    def rerank(
        self,
        query: str,
        candidates: list[RankedCandidate],
        top_k: int,
    ) -> list[RankedCandidate]:
        """Score and diversify candidates, preserving relevance order."""
        if not candidates:
            return []

        terms = self._extract_query_terms(query)
        upper_acronyms = set(re.findall(r"\b[A-Z0-9]{2,}(?:[+\-][A-Z0-9]+)?\b", query))

        rescored: list[RankedCandidate] = []
        for cand in candidates:
            content_lower = cand.document.page_content.lower()
            meta: dict[str, Any] = cand.document.metadata
            title_lower = str(meta.get("title", "")).lower()

            # Exact term coverage ratio in chunk content and document title (with light prefix stem tolerance)
            term_score = 0.0
            for t in terms:
                if t in content_lower:
                    term_score += 1.0
                elif len(t) >= 6 and t[:5] in content_lower:
                    term_score += 0.65
            coverage = (term_score / len(terms)) if terms else 0.0

            title_score = 0.0
            for t in terms:
                if t in title_lower:
                    title_score += 1.0
                elif len(t) >= 6 and t[:5] in title_lower:
                    title_score += 0.65
            title_coverage = (title_score / len(terms)) if terms else 0.0

            # Acronym / code boost (e.g. ANPR, AP10, SIOPE+, IUV, VRE, CVE)
            acronym_hits = sum(1 for acr in upper_acronyms if acr in cand.document.page_content)
            acronym_bonus = min(0.15, 0.05 * acronym_hits)

            # Mild recency tie-breaker for documents with explicit doc_year (2018..2026)
            doc_year = meta.get("doc_year")
            recency_bonus = 0.0
            if isinstance(doc_year, int) and doc_year >= 2018:
                recency_bonus = min(0.04, (doc_year - 2018) * 0.005)

            adjusted = (
                cand.final_score
                + (0.10 * coverage)
                + (0.18 * title_coverage)
                + acronym_bonus
                + recency_bonus
            )
            rescored.append(
                RankedCandidate(
                    document=cand.document,
                    dense_score=cand.dense_score,
                    bm25_score=cand.bm25_score,
                    final_score=min(1.0, round(adjusted, 4)),
                )
            )

        rescored.sort(key=lambda c: c.final_score, reverse=True)

        # Diversify across documents so a single huge manual doesn't monopolize all slots
        selected: list[RankedCandidate] = []
        doc_counts: dict[str, int] = {}
        overflow: list[RankedCandidate] = []

        for cand in rescored:
            doc_id = str(cand.document.metadata.get("document_id", cand.document.metadata.get("source", "")))
            count = doc_counts.get(doc_id, 0)
            if count < self.max_chunks_per_doc:
                selected.append(cand)
                doc_counts[doc_id] = count + 1
                if len(selected) >= top_k:
                    break
            else:
                overflow.append(cand)

        if len(selected) < top_k:
            for cand in overflow:
                selected.append(cand)
                if len(selected) >= top_k:
                    break

        return selected
