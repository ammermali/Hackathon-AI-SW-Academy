"""Real-time analytics and KPI collector for Operator Copilot."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import case, func

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import (
    CacheEntry,
    CustomQuiz,
    DocumentMetadata,
    LearningGap,
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
            # 1. SQL-level aggregate KPIs on QueryHistory (avoids loading large answer/query blobs)
            agg = db.query(
                func.count(QueryHistory.id),
                func.sum(case((QueryHistory.cache_hit.is_(True), 1), else_=0)),
                func.sum(case((QueryHistory.error.is_not(None), 1), else_=0)),
                func.sum(case((QueryHistory.needs_escalation.is_(True), 1), else_=0)),
                func.avg(QueryHistory.processing_time_ms),
                func.avg(case((QueryHistory.cache_hit.is_(False), QueryHistory.retrieval_time_ms), else_=None)),
                func.avg(case((QueryHistory.cache_hit.is_(False), QueryHistory.generation_time_ms), else_=None)),
            ).one()

            total_queries = int(agg[0] or 0)
            if total_queries > 0:
                cache_hits = int(agg[1] or 0)
                cache_misses = total_queries - cache_hits
                cache_hit_rate = round(cache_hits / total_queries, 4)
                errors_count = int(agg[2] or 0)
                error_rate = round(errors_count / total_queries, 4)
                insufficient_evidence_count = int(agg[3] or 0)
                avg_processing_ms = round(float(agg[4] or 0.0), 2)
                avg_retrieval_ms = round(float(agg[5] or 0.0), 2)
                avg_generation_ms = round(float(agg[6] or 0.0), 2)
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

            # 2. Slim projection for document/topic/user frequency counters
            doc_counter: Counter[str] = Counter()
            topic_counter: Counter[str] = Counter()
            user_counter: Counter[str] = Counter()
            escalation_topics: Counter[str] = Counter()

            slim_rows = db.query(
                QueryHistory.user_id,
                QueryHistory.topic,
                QueryHistory.retrieved_doc_ids,
                QueryHistory.needs_escalation,
            ).all()
            for uid, topic, doc_ids, escalated in slim_rows:
                user_counter[uid] += 1
                if topic:
                    topic_counter[topic] += 1
                    if escalated:
                        escalation_topics[topic] += 1
                for doc_src in doc_ids or []:
                    doc_counter[doc_src] += 1

            # 3. Knowledge base SQL aggregation by status
            doc_rows = (
                db.query(
                    DocumentMetadata.status,
                    func.count(DocumentMetadata.id),
                    func.coalesce(func.sum(DocumentMetadata.chunk_count), 0),
                )
                .group_by(DocumentMetadata.status)
                .all()
            )
            doc_counts = {st: int(cnt or 0) for st, cnt, _ in doc_rows}
            doc_chunks = {st: int(ch or 0) for st, _, ch in doc_rows}
            indexed_docs_cnt = doc_counts.get("indexed", 0)
            unreadable_docs_cnt = doc_counts.get("unreadable", 0)
            duplicate_docs_cnt = doc_counts.get("skipped_duplicate", 0)
            total_chunks = doc_chunks.get("indexed", 0)

            # 4. Active cache entries & Feedback SQL aggregations
            active_cache_entries = db.query(func.count(CacheEntry.id)).filter(CacheEntry.expires_at > now).scalar() or 0

            fb_agg = db.query(
                func.count(QueryFeedback.id),
                func.sum(case((QueryFeedback.rating >= 4, 1), else_=0)),
                func.sum(case((QueryFeedback.rating <= 2, 1), else_=0)),
                func.avg(QueryFeedback.rating),
            ).one()
            fb_count = int(fb_agg[0] or 0)
            positive_fb = int(fb_agg[1] or 0)
            negative_fb = int(fb_agg[2] or 0)
            avg_rating = round(float(fb_agg[3]), 2) if fb_count and fb_agg[3] is not None else None

            custom_quizzes_total = db.query(func.count(CustomQuiz.id)).scalar() or 0
            open_learning_gaps = (
                db.query(func.count(LearningGap.id)).filter(LearningGap.status != "RESOLVED").scalar() or 0
            )

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
                "indexed_documents": indexed_docs_cnt,
                "total_chunks": total_chunks,
                "last_indexed_at": last_indexed_at or None,
                "unreadable_documents": unreadable_docs_cnt,
                "duplicate_documents_skipped": duplicate_docs_cnt,
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
                "milestone_status": "adaptive_learning_and_custom_quiz_enabled",
                "topics_to_deepen_candidates": [
                    {"topic": t, "query_count": c} for t, c in topic_counter.most_common(5)
                ],
                "knowledge_gap_signals": [
                    {"topic": t, "escalation_count": c} for t, c in escalation_topics.most_common(5)
                ],
                "quiz_engine_enabled": True,
                "custom_quizzes_generated": custom_quizzes_total,
                "open_learning_gaps": open_learning_gaps,
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
