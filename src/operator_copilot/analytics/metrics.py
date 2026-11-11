"""Real-time analytics and KPI collector for Operator Copilot."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import (
    CacheEntry,
    DocumentMetadata,
    QueryFeedback,
    QueryHistory,
)
from operator_copilot.schemas.response import DocumentInfoResponse, MetricsResponse


class MetricsCollector:
    """Aggregates real operational, knowledge, cache, and user metrics from SQLite."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)

    def collect_metrics(self) -> MetricsResponse:
        """Compute performance, knowledge, cache, user, and learning-readiness metrics."""
        now = datetime.now(timezone.utc)

        with self.db.session() as db:
            histories = db.query(QueryHistory).all()
            total_queries = len(histories)

            if total_queries > 0:
                cache_hits = sum(1 for h in histories if h.cache_hit)
                cache_misses = total_queries - cache_hits
                cache_hit_rate = round(cache_hits / total_queries, 4)
                errors_count = sum(1 for h in histories if h.error is not None)
                error_rate = round(errors_count / total_queries, 4)
                avg_processing_ms = round(sum(h.processing_time_ms for h in histories) / total_queries, 2)

                non_cached = [h for h in histories if not h.cache_hit]
                avg_retrieval_ms = (
                    round(sum(h.retrieval_time_ms for h in non_cached) / len(non_cached), 2)
                    if non_cached
                    else 0.0
                )
                avg_generation_ms = (
                    round(sum(h.generation_time_ms for h in non_cached) / len(non_cached), 2)
                    if non_cached
                    else 0.0
                )
                insufficient_evidence_count = sum(1 for h in histories if h.needs_escalation)
            else:
                cache_hits = 0
                cache_misses = 0
                cache_hit_rate = 0.0
                errors_count = 0
                error_rate = 0.0
                avg_processing_ms = 0.0
                avg_retrieval_ms = 0.0
                avg_generation_ms = 0.0
                insufficient_evidence_count = 0

            # Document & topic frequency across queries
            doc_counter: Counter[str] = Counter()
            topic_counter: Counter[str] = Counter()
            user_counter: Counter[str] = Counter()
            escalation_topics: Counter[str] = Counter()

            for h in histories:
                user_counter[h.user_id] += 1
                if h.topic:
                    topic_counter[h.topic] += 1
                    if h.needs_escalation:
                        escalation_topics[h.topic] += 1
                for doc_src in h.retrieved_doc_ids or []:
                    doc_counter[doc_src] += 1

            # Knowledge base stats
            docs = db.query(DocumentMetadata).all()
            indexed_docs = [d for d in docs if d.status == "indexed"]
            unreadable_docs = [d for d in docs if d.status == "unreadable"]
            duplicate_docs = [d for d in docs if d.status == "skipped_duplicate"]
            total_chunks = sum(d.chunk_count for d in indexed_docs)

            # Active cache entries
            active_cache_entries = db.query(CacheEntry).filter(CacheEntry.expires_at > now).count()

            # Feedback stats
            feedbacks = db.query(QueryFeedback).all()
            fb_count = len(feedbacks)
            positive_fb = sum(1 for f in feedbacks if f.rating >= 4)
            negative_fb = sum(1 for f in feedbacks if f.rating <= 2)
            avg_rating = round(sum(f.rating for f in feedbacks) / fb_count, 2) if fb_count else None

        corpus_version = self.db.get_corpus_version()
        last_indexed_at = self.db.get_state("last_indexed_at", default="")

        return MetricsResponse(
            performance={
                "total_queries": total_queries,
                "avg_processing_time_ms": avg_processing_ms,
                "avg_retrieval_time_ms": avg_retrieval_ms,
                "avg_generation_time_ms": avg_generation_ms,
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
                "cache_hit_rate": cache_hit_rate,
                "errors_count": errors_count,
                "error_rate": error_rate,
            },
            knowledge={
                "corpus_version": corpus_version,
                "indexed_documents": len(indexed_docs),
                "total_chunks": total_chunks,
                "last_indexed_at": last_indexed_at or None,
                "unreadable_documents": len(unreadable_docs),
                "duplicate_documents_skipped": len(duplicate_docs),
                "queries_without_sufficient_evidence": insufficient_evidence_count,
                "most_consulted_documents": [
                    {"document": doc, "count": cnt} for doc, cnt in doc_counter.most_common(10)
                ],
                "most_requested_topics": [
                    {"topic": topic, "count": cnt} for topic, cnt in topic_counter.most_common(10)
                ],
            },
            cache={
                "enabled": self.settings.cache_enabled,
                "active_entries": active_cache_entries,
                "ttl_seconds": self.settings.cache_ttl_seconds,
                "max_entries": self.settings.cache_max_entries,
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
                "cache_hit_rate": cache_hit_rate,
            },
            user={
                "unique_users": len(user_counter),
                "queries_per_user": dict(user_counter),
                "feedback_count": fb_count,
                "positive_feedback_count": positive_fb,
                "negative_feedback_count": negative_fb,
                "avg_rating": avg_rating,
            },
            learning_readiness={
                "milestone_status": "history_collection_only",
                "topics_to_deepen_candidates": [
                    {"topic": t, "query_count": c} for t, c in topic_counter.most_common(5)
                ],
                "knowledge_gap_signals": [
                    {"topic": t, "escalation_count": c} for t, c in escalation_topics.most_common(5)
                ],
                "quiz_engine_enabled": False,
            },
        )

    def list_documents(self, status: str | None = None, limit: int = 200) -> list[DocumentInfoResponse]:
        """Return indexed/tracked document metadata records."""
        with self.db.session() as db:
            query = db.query(DocumentMetadata)
            if status:
                query = query.filter(DocumentMetadata.status == status)
            rows = query.order_by(DocumentMetadata.source.asc()).limit(limit).all()
            return [
                DocumentInfoResponse(
                    document_id=r.document_id,
                    source=r.source,
                    document_type=r.document_type,
                    area_name=r.area_name,
                    file_hash=r.file_hash,
                    chunk_count=r.chunk_count,
                    status=r.status,
                    indexed_at=r.indexed_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]
