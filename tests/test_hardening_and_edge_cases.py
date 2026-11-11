"""Hardening, validation, concurrency, cache invalidation, and regression tests (D5 + C2/C3/C4/D2)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from operator_copilot.api.main import create_app
from operator_copilot.config.settings import Settings
from operator_copilot.course_generator.generator import AICourseGenerator
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import CustomQuizQuestion, QuizQuestion
from operator_copilot.ingestion.normalizer import strip_area_prefix
from operator_copilot.knowledge_intelligence.classifier import TopicClassifier
from operator_copilot.knowledge_intelligence.extractor import KnowledgeExtractor
from operator_copilot.knowledge_intelligence.opportunities import OpportunityAggregator
from operator_copilot.knowledge_intelligence.scorer import RelevanceScorer
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.query import RAGQueryRequest


def _make_admin_headers(tenant_id: str = "t_hardening") -> dict[str, str]:
    return {
        "X-Tenant-ID": tenant_id,
        "X-User-ID": "admin_1",
        "X-User-Role": "admin",
        "X-Admin-Key": "test-secret-admin",
    }


def _make_owner_headers(tenant_id: str = "t_hardening", key: str = "owner-secret") -> dict[str, str]:
    return {
        "X-Tenant-ID": tenant_id,
        "X-User-ID": "owner_1",
        "X-User-Role": "owner",
        "X-Owner-Key": key,
    }


def test_http_validation_errors_and_edge_cases(indexed_engine: RAGEngine, test_settings: Settings) -> None:
    """Verify HTTP 400/422/404 input validation across RAG, Academy, CustomQuiz, and Owner APIs."""
    app = create_app(engine=indexed_engine, settings=test_settings)
    client = TestClient(app)

    admin_hdrs = _make_admin_headers()
    op_hdrs = {"X-Tenant-ID": "t_hardening", "X-User-ID": "op_edge", "X-User-Role": "operatore"}
    owner_secret = test_settings.owner_api_key.get_secret_value() if test_settings.owner_api_key else "dev-owner-key-change-me"
    owner_hdrs = _make_owner_headers(key=owner_secret)

    # 1. RAG query validation (whitespace query, out-of-range top_k, invalid user_scope) -> 422
    assert client.post("/api/v1/rag/query", json={"query": "   "}).status_code == 422
    assert client.post("/api/v1/rag/query", json={"query": "Come fare IUV?", "top_k": 99}).status_code == 422
    assert (
        client.post(
            "/api/v1/rag/query",
            json={"query": "Come fare IUV?", "user_scope": "invalid_scope"},
        ).status_code
        == 422
    )

    # 2. RAG feedback validation (rating bounds, query_history_id < 1) -> 422
    assert (
        client.post(
            "/api/v1/rag/feedback",
            json={"query_history_id": 1, "user_id": "op_edge", "rating": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/rag/feedback",
            json={"query_history_id": 1, "user_id": "op_edge", "rating": 6},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/rag/feedback",
            json={"query_history_id": 0, "user_id": "op_edge", "rating": 3},
        ).status_code
        == 422
    )

    # 3. Academy course generation edge cases (empty / Swagger 'string' placeholders) -> 400
    resp_empty = client.post("/api/v1/academy/courses/generate", json={}, headers=admin_hdrs)
    assert resp_empty.status_code == 400
    resp_swagger = client.post(
        "/api/v1/academy/courses/generate",
        json={"opportunity_id": "string", "document_source": "string"},
        headers=admin_hdrs,
    )
    assert resp_swagger.status_code == 400

    # 4. Academy course lifecycle invalid target_status -> 422
    resp_lc = client.post(
        "/api/v1/academy/courses/nonexistent-course/lifecycle",
        json={"target_status": "BOGUS_STATE", "note": "test"},
        headers=admin_hdrs,
    )
    assert resp_lc.status_code == 422

    # 5. Custom Quiz generation validation (422 bounds) and unknown user with zero history (404)
    assert (
        client.post(
            "/api/v1/customquiz/generate",
            json={"user_id": "op_edge", "num_questions": 0},
            headers=op_hdrs,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/customquiz/generate",
            json={"user_id": "op_edge", "num_questions": 25},
            headers=op_hdrs,
        ).status_code
        == 422
    )
    resp_no_hist = client.post(
        "/api/v1/customquiz/generate",
        json={"user_id": "op_edge", "num_questions": 3},
        headers=op_hdrs,
    )
    assert resp_no_hist.status_code == 404

    # 6. Owner Dashboard pagination / enum validation -> 422
    assert client.get("/api/v1/owner/users?page=0", headers=owner_hdrs).status_code == 422
    assert client.get("/api/v1/owner/users?page_size=500", headers=owner_hdrs).status_code == 422
    assert client.get("/api/v1/owner/users?sort_by=not_a_column", headers=owner_hdrs).status_code == 422
    assert client.get("/api/v1/owner/topics-to-review?criticality=INVALID", headers=owner_hdrs).status_code == 422


def test_settings_removed_options_and_strip_area_prefix(tmp_path: Path) -> None:
    """Verify C4 settings cleanup (only chroma supported, legacy flags ignored cleanly) and C2 strip_area_prefix."""
    # 'faiss' was removed from vectorstore_type Literal
    with pytest.raises(ValidationError):
        Settings(vectorstore_type="faiss")  # type: ignore[arg-type]

    # Legacy removed settings passed from old .env dicts are ignored safely via extra='ignore'
    cfg = Settings.model_validate(
        {
            "app_env": "test",
            "vectorstore_type": "chroma",
            "semantic_cache_enabled": True,
            "semantic_cache_threshold": 0.9,
            "data_dir": tmp_path,
        }
    )
    assert cfg.vectorstore_type == "chroma"
    assert not hasattr(cfg, "semantic_cache_enabled")

    # C2 shared helper strip_area_prefix removes leading [Area: ...]\n only
    raw = "[Area: 03 - SERVIZI DEMOGRAFICI]\nProcedura di cancellazione.\nTesto successivo."
    assert strip_area_prefix(raw) == "Procedura di cancellazione.\nTesto successivo."
    assert strip_area_prefix("Nessun prefisso") == "Nessun prefisso"


def test_thread_safety_db_manager_and_hybrid_retriever(indexed_engine: RAGEngine, test_settings: Settings) -> None:
    """Verify D2 thread-safety of get_db_manager and HybridRetriever.retrieve under parallel load."""
    # Clear global cache entry for this test DB URL if present to stress double-checked lock
    from operator_copilot.db import database as db_mod

    with db_mod._db_manager_lock:
        db_mod._db_manager_cache.pop(test_settings.database_url, None)

    def _get_mgr(_: int) -> DatabaseManager:
        return get_db_manager(test_settings)

    with ThreadPoolExecutor(max_workers=6) as pool:
        managers = list(pool.map(_get_mgr, range(12)))
    assert len({id(m) for m in managers}) == 1

    # Reset BM25 internal state so all 6 threads race to rebuild/read it concurrently
    indexed_engine.retriever._bm25 = None
    indexed_engine.retriever._bm25_docs = []

    def _run_retrieve(i: int) -> int:
        chunks = indexed_engine.retriever.retrieve("rimuovere verbale ruolo F7", top_k=2)
        return len(chunks)

    with ThreadPoolExecutor(max_workers=6) as pool:
        counts = list(pool.map(_run_retrieve, range(12)))
    assert all(c >= 1 for c in counts)
    assert len(set(counts)) == 1


def test_async_custom_quiz_generation_and_owner_cache_invalidation(tmp_path: Path) -> None:
    """Verify D5 run_async=true Custom Quiz lifecycle and C3 automatic Owner cache invalidation."""
    data_dir = tmp_path / "data"
    rag_dir = data_dir / "02 - Ragioneria"
    rag_dir.mkdir(parents=True)
    doc_name = "2025_c10_siope_pagopa.md"
    (rag_dir / doc_name).write_text(
        "# Gestione PagoPA e SIOPE+\n\n"
        "## Verifica codici IUV\n"
        "1. Aprire il modulo Ragioneria e selezionare la sezione Ordinativi.\n"
        "2. Inserire il codice IUV associato all'avviso PagoPA prima della trasmissione.\n"
        "3. Verificare ACK/NACK nel flusso SIOPE+ dentro Flussi Tesoreria.\n"
        "4. In caso di scarto controllare l'IBAN beneficiario e la causale di versamento.\n",
        encoding="utf-8",
    )

    cfg = Settings(
        app_env="test",
        llm_provider="extractive",
        embedding_provider="hashing",
        embedding_model="hashing-128",
        vectorstore_type="chroma",
        vectorstore_path=tmp_path / "vectorstore",
        collection_name=f"hardening_{tmp_path.name}",
        data_dir=data_dir,
        database_url=f"sqlite:///{(tmp_path / 'hardening.db').as_posix()}",
        retrieval_score_threshold=0.18,
        owner_api_key="owner-secret",
        admin_api_key="admin-secret",
        owner_dashboard_cache_ttl_seconds=300,
        log_level="WARNING",
    )
    cfg.ensure_directories()

    rag = RAGEngine(settings=cfg)
    rag.indexer.run_ingestion(rebuild=True)
    app = create_app(engine=rag, settings=cfg)
    client = TestClient(app)

    tenant = "tenant_cache_test"
    owner_hdrs = _make_owner_headers(tenant_id=tenant, key="owner-secret")
    op_hdrs = {"X-Tenant-ID": tenant, "X-User-ID": "op_async", "X-User-Role": "operatore"}

    # Seed one course + quiz so the user can submit both course quiz and custom quiz
    extractor = KnowledgeExtractor(settings=cfg, db_manager=rag.db, retriever=rag.retriever, generator=rag.generator)
    classifier = TopicClassifier(generator=rag.generator)
    scorer = RelevanceScorer(db_manager=rag.db, generator=rag.generator)
    aggregator = OpportunityAggregator(db_manager=rag.db, retriever=rag.retriever)
    course_gen = AICourseGenerator(settings=cfg, db_manager=rag.db, extractor=extractor, generator=rag.generator)

    bundle = extractor.load_document_bundle(doc_name)
    assert bundle is not None
    topic = extractor.extract_from_bundle(bundle, tenant_id=tenant, classifier=classifier)
    scorer.score_topic(topic, persist=True)
    opp = aggregator.build_opportunity_from_topics([topic], tenant_id=tenant, persist=True)
    course = course_gen.generate_from_opportunity(opp.id, tenant_id=tenant, created_by="setup")
    course_quiz = course_gen.generate_quiz(course.id, tenant_id=tenant, num_questions=2)

    # Create RAG history with negative signal so Custom Quiz can be generated
    q_res = rag.answer_query(
        RAGQueryRequest(query="Non riesco a trovare il codice IUV PagoPA in SIOPE+", user_id="op_async", session_id="s1")
    )
    assert q_res.history_id is not None

    # 1. Warm Owner overview cache BEFORE quiz submissions (total_users == 0)
    ov_before = client.get("/api/v1/owner/overview", headers=owner_hdrs)
    assert ov_before.status_code == 200
    before_data = ov_before.json()
    assert before_data["total_users"] == 0
    assert "_ver" not in before_data["filters"]

    # 2. Submit traditional Course Quiz -> C3 must bump owner cache version automatically
    with rag.db.session() as db:
        cq_rows = db.query(QuizQuestion).filter_by(quiz_id=course_quiz.id).order_by(QuizQuestion.order_index).all()
        wrong_answers = {r.id: "Risposta sbagliata di test" for r in cq_rows}
    sub_course = client.post(
        f"/api/v1/academy/courses/{course.id}/quizzes/{course_quiz.id}/submit",
        json={"user_id": "op_async", "answers": wrong_answers},
        headers=op_hdrs,
    )
    assert sub_course.status_code == 200

    # Query /owner/overview WITHOUT refresh=true -> must reflect the new attempt immediately (not stale 0!)
    ov_after_course = client.get("/api/v1/owner/overview", headers=owner_hdrs)
    assert ov_after_course.status_code == 200
    after_course_data = ov_after_course.json()
    assert after_course_data["total_users"] == 1
    assert after_course_data["active_users_in_period"] == 1
    assert after_course_data["open_gaps_count"] >= 1
    assert "_ver" not in after_course_data["filters"]

    # 3. Trigger async Custom Quiz generation (run_async=True) and poll until READY
    gen_resp = client.post(
        "/api/v1/customquiz/generate",
        json={"user_id": "op_async", "num_questions": 3, "run_async": True, "force_new": True},
        headers=op_hdrs,
    )
    assert gen_resp.status_code == 200
    gen_json = gen_resp.json()
    quiz_id = gen_json["id"]
    assert gen_json["status"] in {"GENERATING", "READY"}

    final_quiz = gen_json
    deadline = time.monotonic() + 10.0
    while final_quiz["status"] == "GENERATING" and time.monotonic() < deadline:
        time.sleep(0.05)
        poll = client.get(f"/api/v1/customquiz/{quiz_id}", headers=op_hdrs)
        assert poll.status_code == 200
        final_quiz = poll.json()

    assert final_quiz["status"] == "READY"
    assert len(final_quiz["questions"]) == 3
    for q in final_quiz["questions"]:
        assert len(q["options"]) == 4

    # 4. Submit Custom Quiz -> C3 bumps owner cache version again -> overview avg_quiz_score updates without refresh=true
    with rag.db.session() as db:
        q_rows = db.query(CustomQuizQuestion).filter_by(quiz_id=quiz_id).order_by(CustomQuizQuestion.order_index).all()
        correct_answers = {r.id: r.correct_option_id for r in q_rows}
    sub_cq = client.post(
        f"/api/v1/customquiz/{quiz_id}/submit",
        json={"user_id": "op_async", "answers": correct_answers, "duration_seconds": 30},
        headers=op_hdrs,
    )
    assert sub_cq.status_code == 200

    ov_after_cq = client.get("/api/v1/owner/overview", headers=owner_hdrs)
    assert ov_after_cq.status_code == 200
    after_cq_data = ov_after_cq.json()
    assert after_cq_data["avg_quiz_score"] > 0.0

    # 5. GDPR delete also bumps owner cache version automatically
    del_resp = client.delete("/api/v1/customquiz/user/op_async/data", headers=op_hdrs)
    assert del_resp.status_code == 200
    ov_after_del = client.get("/api/v1/owner/overview", headers=owner_hdrs)
    assert ov_after_del.status_code == 200
    assert ov_after_del.json()["avg_quiz_score"] == 0.0


def test_strict_cors_configuration_and_preflight(indexed_engine: RAGEngine, test_settings: Settings) -> None:
    """Verify explicit CORS whitelist for React UI and rejection of wildcard '*'."""
    with pytest.raises(ValidationError):
        Settings(cors_allowed_origins=["*"])

    app = create_app(engine=indexed_engine, settings=test_settings)
    client = TestClient(app)

    allowed = client.options(
        "/api/v1/rag/query",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    blocked = client.options(
        "/api/v1/rag/query",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert blocked.headers.get("access-control-allow-origin") is None

