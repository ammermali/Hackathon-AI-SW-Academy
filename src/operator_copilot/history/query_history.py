"""Query history persistence, topic grouping, retention cleanup, and feedback tracking."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from operator_copilot.cache.cache_policy import CachePolicy
from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import QueryFeedback, QueryHistory
from operator_copilot.schemas.response import (
    FeedbackResponse,
    HistoryItem,
    HistoryResponse,
    SourceCitation,
)

logger = logging.getLogger("operator_copilot.history.query_history")


class QueryHistoryManager:
    """Persists and queries operator search history and feedback in SQLite."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)

    @staticmethod
    def infer_intent(query: str) -> str:
        """Heuristically classify operator intent from query wording."""
        q = query.lower()
        if any(w in q for w in ("errore", "blocco", "non funziona", "fallit", "anomalia", "risolvere", "problema")):
            return "troubleshooting"
        if any(w in q for w in ("differenz", "confront", "meglio", "tra ")):
            return "comparison"
        if any(w in q for w in ("dove ", "percorso", "menu", "schermata", "trovo")):
            return "navigation"
        if any(w in q for w in ("come ", "passaggi", "procedura", "eseguire", "completare", "creare", "inserire")):
            return "procedure"
        return "general_info"

    @staticmethod
    def infer_topic(sources: list[SourceCitation]) -> str | None:
        """Derive dominant topic area strictly from retrieved source metadata."""
        areas = [s.area for s in sources if s.area]
        if not areas:
            return None
        return Counter(areas).most_common(1)[0][0]

    def record_query(
        self,
        *,
        user_id: str,
        session_id: str,
        query: str,
        answer: str,
        sources: list[SourceCitation],
        cache_hit: bool,
        needs_escalation: bool,
        retrieval_time_ms: int,
        generation_time_ms: int,
        processing_time_ms: int,
        error: str | None = None,
    ) -> int:
        """Store a single query interaction and return its record ID."""
        norm_q = CachePolicy.normalize_query(query)
        intent = self.infer_intent(query)
        topic = self.infer_topic(sources)
        serialized_sources = [s.model_dump() for s in sources]
        doc_ids = list(dict.fromkeys(s.document for s in sources))

        with self.db.session() as db:
            record = QueryHistory(
                user_id=user_id,
                session_id=session_id,
                query=query,
                normalized_query=norm_q,
                intent=intent,
                topic=topic,
                answer=answer,
                sources=serialized_sources,
                retrieved_doc_ids=doc_ids,
                cache_hit=cache_hit,
                needs_escalation=needs_escalation,
                retrieval_time_ms=retrieval_time_ms,
                generation_time_ms=generation_time_ms,
                processing_time_ms=processing_time_ms,
                error=error,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.id

    def get_user_history(self, user_id: str, limit: int = 20) -> HistoryResponse:
        """Retrieve latest N queries for a user along with topic frequency grouping."""
        with self.db.session() as db:
            rows = (
                db.query(QueryHistory)
                .filter(QueryHistory.user_id == user_id)
                .order_by(QueryHistory.created_at.desc(), QueryHistory.id.desc())
                .limit(limit)
                .all()
            )

            items: list[HistoryItem] = []
            topic_counter: Counter[str] = Counter()

            for r in rows:
                if r.topic:
                    topic_counter[r.topic] += 1
                items.append(
                    HistoryItem(
                        id=r.id,
                        user_id=r.user_id,
                        session_id=r.session_id,
                        query=r.query,
                        intent=r.intent,
                        topic=r.topic,
                        answer=r.answer,
                        sources=r.sources or [],
                        cache_hit=r.cache_hit,
                        processing_time_ms=r.processing_time_ms,
                        needs_escalation=r.needs_escalation,
                        created_at=r.created_at,
                    )
                )

            return HistoryResponse(
                user_id=user_id,
                total_returned=len(items),
                items=items,
                topics_summary=dict(topic_counter),
            )

    def add_feedback(
        self,
        *,
        query_history_id: int,
        user_id: str,
        rating: int,
        comment: str | None = None,
    ) -> FeedbackResponse:
        """Attach feedback to an existing QueryHistory entry."""
        with self.db.session() as db:
            parent = db.get(QueryHistory, query_history_id)
            if parent is None:
                raise ValueError(f"QueryHistory record {query_history_id} not found.")

            fb = QueryFeedback(
                query_history_id=query_history_id,
                user_id=user_id,
                rating=rating,
                comment=comment,
            )
            db.add(fb)
            db.commit()
            db.refresh(fb)
            return FeedbackResponse(
                id=fb.id,
                query_history_id=fb.query_history_id,
                rating=fb.rating,
                comment=fb.comment,
                created_at=fb.created_at,
            )

    def purge_expired_history(self, retention_days: int | None = None) -> int:
        """Delete query history records older than configured retention period."""
        days = retention_days or self.settings.history_retention_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self.db.session() as db:
            deleted = db.query(QueryHistory).filter(QueryHistory.created_at < cutoff).delete()
            db.commit()
            return deleted

    def delete_user_history(self, user_id: str) -> int:
        """Delete all history and cascading feedback for a given user_id."""
        with self.db.session() as db:
            deleted = db.query(QueryHistory).filter(QueryHistory.user_id == user_id).delete()
            db.commit()
            return deleted
