"""Tests for query history recording, topic grouping, feedback, retention, and metrics KPIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from operator_copilot.config.settings import Settings
from operator_copilot.db.database import DatabaseManager
from operator_copilot.db.models import QueryHistory
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.query import RAGQueryRequest


def test_metrics_handle_zero_queries_safely(test_settings: Settings, test_db: DatabaseManager) -> None:
    engine = RAGEngine(settings=test_settings, db_manager=test_db)
    metrics = engine.metrics.collect_metrics()
    assert metrics.performance["total_queries"] == 0
    assert metrics.performance["cache_hit_rate"] == 0.0
    assert metrics.performance["error_rate"] == 0.0
    assert metrics.cache["cache_hit_rate"] == 0.0


def test_history_recording_grouping_feedback_and_metrics(indexed_engine: RAGEngine) -> None:
    r1 = indexed_engine.answer_query(
        RAGQueryRequest(query="Come rimuovere un verbale da un ruolo con F7?", user_id="mario", session_id="s1")
    )
    r2 = indexed_engine.answer_query(
        RAGQueryRequest(query="Come rimuovere un verbale da un ruolo con F7?", user_id="mario", session_id="s1")
    )
    assert r1.history_id is not None
    assert r2.history_id is not None
    assert r2.cached is True

    hist = indexed_engine.history.get_user_history("mario", limit=10)
    assert hist.total_returned == 2
    assert hist.items[0].processing_time_ms >= 0
    assert "Codice della Strada" in hist.topics_summary

    fb = indexed_engine.history.add_feedback(
        query_history_id=r1.history_id,
        user_id="mario",
        rating=5,
        comment="Chiarissimo!",
    )
    assert fb.rating == 5

    metrics = indexed_engine.metrics.collect_metrics()
    assert metrics.performance["total_queries"] == 2
    assert metrics.performance["cache_hits"] == 1
    assert metrics.performance["cache_misses"] == 1
    assert metrics.performance["cache_hit_rate"] == 0.5
    assert metrics.user["feedback_count"] == 1
    assert metrics.user["positive_feedback_count"] == 1
    assert metrics.knowledge["indexed_documents"] == 3


def test_history_retention_and_user_deletion(indexed_engine: RAGEngine) -> None:
    indexed_engine.answer_query(
        RAGQueryRequest(query="Quale modalità usare per PagoPA su SIOPE+?", user_id="giulia")
    )
    # Age record manually beyond retention
    with indexed_engine.db.session() as db:
        row = db.query(QueryHistory).filter_by(user_id="giulia").first()
        assert row is not None
        row.created_at = datetime.now(timezone.utc) - timedelta(days=120)
        db.commit()

    purged = indexed_engine.history.purge_expired_history(retention_days=90)
    assert purged == 1
    assert indexed_engine.history.get_user_history("giulia").total_returned == 0

    # User explicit deletion
    indexed_engine.answer_query(
        RAGQueryRequest(query="Come funziona la pratica per irreperibilità?", user_id="luca")
    )
    assert indexed_engine.history.get_user_history("luca").total_returned == 1
    deleted = indexed_engine.history.delete_user_history("luca")
    assert deleted == 1
    assert indexed_engine.history.get_user_history("luca").total_returned == 0
