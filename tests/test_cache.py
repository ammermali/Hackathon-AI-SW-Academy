"""Tests for Smart Question Cache: miss/hit, TTL expiration, invalidation, and user isolation."""

from __future__ import annotations

import time
from pathlib import Path

from operator_copilot.config.settings import Settings
from operator_copilot.db.database import DatabaseManager
from operator_copilot.ingestion.indexer import DocumentIndexer
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.query import RAGQueryRequest


def test_cache_miss_then_hit_with_normalization(indexed_engine: RAGEngine) -> None:
    q1 = RAGQueryRequest(query="Come rimuovere un verbale da un ruolo con F7?", user_id="u1")
    r1 = indexed_engine.answer_query(q1)
    assert r1.cached is False

    # Same question with extra whitespace and different casing
    q2 = RAGQueryRequest(query="   come   rimuovere UN verbale da un RUOLO con f7?  ", user_id="u2")
    r2 = indexed_engine.answer_query(q2)
    assert r2.cached is True
    assert r2.answer == r1.answer
    assert r2.sources == r1.sources


def test_cache_ttl_expiration(test_settings: Settings, test_db: DatabaseManager) -> None:
    short_ttl_settings = test_settings.model_copy(update={"cache_ttl_seconds": 1})
    indexer = DocumentIndexer(settings=short_ttl_settings, db_manager=test_db)
    indexer.run_ingestion(rebuild=True)
    engine = RAGEngine(settings=short_ttl_settings, db_manager=test_db)

    req = RAGQueryRequest(query="Quale modalità usare per PagoPA su SIOPE+?", user_id="u1")
    first = engine.answer_query(req)
    assert first.cached is False

    second = engine.answer_query(req)
    assert second.cached is True

    time.sleep(1.15)

    third = engine.answer_query(req)
    assert third.cached is False


def test_cache_invalidated_when_knowledge_base_or_prompt_changes(
    test_settings: Settings,
    test_db: DatabaseManager,
    sample_data_dir: Path,
) -> None:
    indexer = DocumentIndexer(settings=test_settings, db_manager=test_db)
    indexer.run_ingestion(rebuild=True)
    engine = RAGEngine(settings=test_settings, db_manager=test_db)

    req = RAGQueryRequest(query="Come funziona la pratica per irreperibilità?", user_id="u1")
    assert engine.answer_query(req).cached is False
    assert engine.answer_query(req).cached is True

    # Modify document and re-ingest -> corpus_version changes -> cache must invalidate
    target = sample_data_dir / "03 - SERVIZI DEMOGRAFICI" / "067 - Cancellazione, la pratica resta in corso.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\n\nAggiornamento procedurale 2026.",
        encoding="utf-8",
    )
    engine.indexer.run_ingestion(rebuild=False)

    after_kb_change = engine.answer_query(req)
    assert after_kb_change.cached is False
    assert engine.answer_query(req).cached is True

    # Change prompt_version -> cache must invalidate
    v2_settings = test_settings.model_copy(update={"prompt_version": "v2.0"})
    engine_v2 = RAGEngine(settings=v2_settings, db_manager=test_db)
    after_prompt_change = engine_v2.answer_query(req)
    assert after_prompt_change.cached is False


def test_cache_user_isolation_private_vs_public(indexed_engine: RAGEngine) -> None:
    priv_u1 = RAGQueryRequest(
        query="Come rimuovere un verbale con F7?",
        user_id="alice",
        user_scope="private",
    )
    priv_u2 = RAGQueryRequest(
        query="Come rimuovere un verbale con F7?",
        user_id="bob",
        user_scope="private",
    )

    assert indexed_engine.answer_query(priv_u1).cached is False
    # Bob must NOT receive Alice's private cache entry
    assert indexed_engine.answer_query(priv_u2).cached is False
    # Alice repeating her own private query DOES hit cache
    assert indexed_engine.answer_query(priv_u1).cached is True


def test_abstention_responses_are_never_cached(test_settings: Settings, test_db: DatabaseManager) -> None:
    strict = test_settings.model_copy(update={"retrieval_score_threshold": 0.90})
    DocumentIndexer(settings=strict, db_manager=test_db).run_ingestion(rebuild=True)
    engine = RAGEngine(settings=strict, db_manager=test_db)

    req = RAGQueryRequest(query="Domanda fuori contesto assoluto xyz123", user_id="u1")
    r1 = engine.answer_query(req)
    assert r1.needs_escalation is True
    assert r1.cached is False

    r2 = engine.answer_query(req)
    assert r2.cached is False
