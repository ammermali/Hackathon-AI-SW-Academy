"""Comprehensive tests for Milestone 3 – Adaptive Learning & Custom Quiz Engine."""

from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from operator_copilot.api.main import create_app
from operator_copilot.config.settings import Settings
from operator_copilot.course_generator.generator import AICourseGenerator
from operator_copilot.customquiz import CustomQuizEngine
from operator_copilot.db.database import DatabaseManager
from operator_copilot.db.models import (
    CourseQuizAttempt,
    CustomQuiz,
    CustomQuizAttempt,
    CustomQuizQuestion,
    LearningGap,
    QuizQuestion,
    UserKnowledgeProfile,
)
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.ingestion.indexer import DocumentIndexer
from operator_copilot.knowledge_intelligence.classifier import TopicClassifier
from operator_copilot.knowledge_intelligence.extractor import KnowledgeExtractor
from operator_copilot.knowledge_intelligence.opportunities import OpportunityAggregator
from operator_copilot.knowledge_intelligence.scorer import RelevanceScorer
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.query import RAGQueryRequest


REAL_SUPPORT_GUIDE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "01 - Informazioni Generali"
    / "2024_c07_modalita_corretta_richiesta_assistenza_clienti.md"
)


class QwenMockChatModel(FakeListChatModel):
    """Fake LangChain ChatModel reporting Qwen model_name for structured JSON tests."""

    model_name: str = "qwen2.5:7b-instruct"


@pytest.fixture()
def cq_data_dir(tmp_path: Path) -> Path:
    data_root = tmp_path / "cq_data"
    gen_dir = data_root / "01 - Informazioni Generali"
    rag_dir = data_root / "02 - Ragioneria"
    gen_dir.mkdir(parents=True)
    rag_dir.mkdir(parents=True)

    if REAL_SUPPORT_GUIDE.exists():
        shutil.copy2(REAL_SUPPORT_GUIDE, gen_dir / REAL_SUPPORT_GUIDE.name)
    else:
        (gen_dir / "2024_c07_modalita_corretta_richiesta_assistenza_clienti.md").write_text(
            "# Comunicazione n. 7/2024 – Modalità corretta di richiesta assistenza da parte dei Clienti\n\n"
            "## 1.1 – Canali ufficiali OTRS\n"
            "Le richieste devono essere inviate tramite il sistema OTRS scrivendo a supporto@palitalsoft.it.\n"
            "Per problemi critici o bloccanti è attivo il numero telefonico dedicato al supporto clienti.\n\n"
            "## 2.2 – Tipologie di richiesta\n"
            "1. Assistenza tecnica ordinaria su anomalie applicative.\n"
            "2. Modifiche normative o adeguamenti di legge.\n"
            "3. Assistenza straordinaria fuori canone.\n\n"
            "## 2.3 – Campi obbligatori del ticket\n"
            "- OGGETTO chiaro con applicativo e sintesi del problema.\n"
            "- CORPO dettagliato con descrizione passo-passo, schermate ed eventuali codici errore.\n"
            "- FIRMA comprensiva di ente, nominativo dell'operatore e numero di telefono.\n",
            encoding="utf-8",
        )

    (rag_dir / "2025_c10_siope_pagopa.md").write_text(
        "# Gestione ordinativi SIOPE+ e PagoPA su CWOL\n\n"
        "## Verifica codici IUV su CWOL\n"
        "1. Accedere al modulo Ragioneria su CWOL.\n"
        "2. Controllare che il codice IUV sia associato all'avviso PagoPA attivo prima dell'invio al nodo.\n"
        "3. Verificare l'esito ACK/NACK nella sezione Flussi Tesoreria.\n",
        encoding="utf-8",
    )
    return data_root


@pytest.fixture()
def cq_settings(tmp_path: Path, cq_data_dir: Path) -> Settings:
    cfg = Settings(
        app_env="test",
        llm_provider="extractive",
        llm_model="qwen2.5:7b-instruct",
        llm_expected_model_family="qwen",
        embedding_provider="hashing",
        embedding_model="hashing-128",
        vectorstore_type="chroma",
        vectorstore_path=tmp_path / "storage" / "vectorstore",
        collection_name=f"cq_col_{tmp_path.name}",
        data_dir=cq_data_dir,
        database_url=f"sqlite:///{(tmp_path / 'storage' / 'customquiz.db').as_posix()}",
        admin_api_key="cq-secret-admin",
        pii_redact_before_llm=True,
        learning_retention_min_hours=24.0,
        custom_quiz_reuse_hours=24,
        log_level="WARNING",
    )
    cfg.ensure_directories()
    return cfg


@pytest.fixture()
def cq_rag_engine(cq_settings: Settings) -> RAGEngine:
    db = DatabaseManager(cq_settings.database_url)
    indexer = DocumentIndexer(settings=cq_settings, db_manager=db)
    indexer.run_ingestion(rebuild=True)
    return RAGEngine(settings=cq_settings, db_manager=db)


def _create_support_course_with_quiz(rag: RAGEngine, tenant_id: str = "tenant_pa") -> tuple[str, str]:
    """Helper generating a real Milestone 2 course + traditional quiz on 2024_c07."""
    extractor = KnowledgeExtractor(
        settings=rag.settings,
        db_manager=rag.db,
        retriever=rag.retriever,
        generator=rag.generator,
    )
    classifier = TopicClassifier(generator=rag.generator)
    scorer = RelevanceScorer(db_manager=rag.db, generator=rag.generator)
    aggregator = OpportunityAggregator(db_manager=rag.db, retriever=rag.retriever)
    course_gen = AICourseGenerator(
        settings=rag.settings,
        db_manager=rag.db,
        extractor=extractor,
        generator=rag.generator,
    )

    bundle = extractor.load_document_bundle("2024_c07_modalita_corretta_richiesta_assistenza_clienti.md")
    assert bundle is not None
    topic = extractor.extract_from_bundle(bundle, tenant_id=tenant_id, classifier=classifier)
    scorer.score_topic(topic, persist=True)
    opp = aggregator.build_opportunity_from_topics([topic], tenant_id=tenant_id, persist=True)
    course = course_gen.generate_from_opportunity(opp.id, tenant_id=tenant_id, created_by="tester")
    quiz = course_gen.generate_quiz(course.id, tenant_id=tenant_id, num_questions=4)
    return course.id, quiz.id


def test_longitudinal_adaptive_learning_scenario_end_to_end(cq_rag_engine: RAGEngine) -> None:
    """Mandatory longitudinal scenario: RAG difficulty + course quiz errors -> custom quiz -> resolution & metrics."""
    app = create_app(engine=cq_rag_engine, settings=cq_rag_engine.settings)
    client = TestClient(app)
    cq = CustomQuizEngine(cq_rag_engine)
    tenant = "tenant_pa"
    user_id = "op_maria"
    headers = {"X-Tenant-ID": tenant, "X-User-ID": user_id, "X-User-Role": "operatore"}

    # Step 1: Course & traditional Quiz exist on 2024_c07 support guide
    course_id, course_quiz_id = _create_support_course_with_quiz(cq_rag_engine, tenant_id=tenant)

    # Step 2: Normal operational RAG usage (not a difficulty signal) + repeated trouble RAG queries
    normal_res = cq_rag_engine.answer_query(
        RAGQueryRequest(query="Come verifico i codici IUV PagoPA su CWOL?", user_id=user_id, session_id="s1")
    )
    assert normal_res.history_id is not None

    q1 = cq_rag_engine.answer_query(
        RAGQueryRequest(
            query="Non riesco ad aprire un ticket su OTRS, aiuto quali campi servono?",
            user_id=user_id,
            session_id="s1",
        )
    )
    q2 = cq_rag_engine.answer_query(
        RAGQueryRequest(
            query="Ho avuto ancora errore durante l'invio ticket OTRS per assistenza clienti",
            user_id=user_id,
            session_id="s1",
        )
    )
    assert q1.history_id is not None
    assert q2.history_id is not None

    # Explicit negative feedback (rating=1 <= 2) on q1 via RAG feedback API
    fb_resp = client.post(
        "/api/v1/rag/feedback",
        json={
            "query_history_id": q1.history_id,
            "user_id": user_id,
            "rating": 1,
            "comment": "Non ho capito quali campi obbligatori inserire",
        },
        headers=headers,
    )
    assert fb_resp.status_code == 200

    # Step 3: Submit traditional Course Quiz with intentional errors on 2+ questions
    course_resp = client.get(f"/api/v1/academy/courses/{course_id}", headers=headers)
    assert course_resp.status_code == 200
    with cq_rag_engine.db.session() as db:
        qqs = db.query(QuizQuestion).filter_by(quiz_id=course_quiz_id).order_by(QuizQuestion.order_index).all()
        assert len(qqs) >= 2
        course_answers = {
            qq.id: ("Risposta errata test" if idx < 2 else qq.correct_answer)
            for idx, qq in enumerate(qqs)
        }

    submit_course_resp = client.post(
        f"/api/v1/academy/courses/{course_id}/quizzes/{course_quiz_id}/submit",
        json={"user_id": user_id, "answers": course_answers},
        headers=headers,
    )
    assert submit_course_resp.status_code == 200
    course_res_data = submit_course_resp.json()
    assert course_res_data["total_questions"] == len(qqs)
    assert len(course_res_data["wrong_topics"]) >= 1

    # Step 4: Verify Gap Detection & User Knowledge Profile reflect friction/errors without penalizing normal IUV query
    gaps_resp = client.post(f"/api/v1/customquiz/user/{user_id}/analyze-gaps", json={}, headers=headers)
    assert gaps_resp.status_code == 200
    gaps_list = gaps_resp.json()
    assert len(gaps_list) >= 1
    assert any(g["priority"] == "high" and g["status"] == "OPEN" for g in gaps_list)
    assert not any("iuv" in g["topic"].lower() for g in gaps_list), "Normal operational query must not trigger a gap"

    prof_resp = client.get(f"/api/v1/customquiz/user/{user_id}/learning-profile", headers=headers)
    assert prof_resp.status_code == 200
    prof_data = prof_resp.json()
    assert prof_data["user_id"] == user_id
    assert len(prof_data["difficulty_topics"]) >= 1
    assert len(prof_data["open_gaps"]) >= 1

    # Step 5: Generate Custom Quiz #1 via HTTP API -> verify 4 options (A-D), grounding, & answer hiding
    gen1_resp = client.post(
        "/api/v1/customquiz/generate",
        json={"user_id": user_id, "num_questions": 4},
        headers=headers,
    )
    assert gen1_resp.status_code == 200
    quiz1_data = gen1_resp.json()
    assert quiz1_data["status"] == "READY"
    assert len(quiz1_data["questions"]) == 4

    get_q1_resp = client.get(f"/api/v1/customquiz/{quiz1_data['id']}", headers=headers)
    assert get_q1_resp.status_code == 200
    public_quiz1 = get_q1_resp.json()
    for q in public_quiz1["questions"]:
        opts = q["options"]
        assert [o["id"] for o in opts] == ["A", "B", "C", "D"], "Every Custom Quiz question MUST have strictly 4 options A-D"
        assert "correct_option_id" not in q
        assert "correct_answer" not in q
        assert len(q["sources"]) >= 1

    # Inspect ground truth in SQLite directly for submitting deterministic answers
    with cq_rag_engine.db.session() as db:
        q1_rows = (
            db.query(CustomQuizQuestion)
            .filter_by(quiz_id=quiz1_data["id"])
            .order_by(CustomQuizQuestion.order_index)
            .all()
        )
        assert all(r.correct_option_id in ("A", "B", "C", "D") for r in q1_rows)
        # First attempt: deliberate low score (1 right, 3 wrong -> NEEDS_PRACTICE)
        wrong_ans = {
            r.id: (r.correct_option_id if i == 0 else ("B" if r.correct_option_id != "B" else "A"))
            for i, r in enumerate(q1_rows)
        }
        q1_hashes = {r.question_hash for r in q1_rows}

    sub1_resp = client.post(
        f"/api/v1/customquiz/{quiz1_data['id']}/submit",
        json={"user_id": user_id, "answers": wrong_ans, "duration_seconds": 95},
        headers=headers,
    )
    assert sub1_resp.status_code == 200
    sub1 = sub1_resp.json()
    assert sub1["correct_count"] == 1
    assert sub1["percentage"] == 25.0
    assert sub1["outcome"] == "NEEDS_PRACTICE"
    assert len(sub1["topics_to_improve"]) >= 1
    assert len(sub1["recommended_lessons"]) >= 1, "Weak topics should link back to Academy lessons"
    assert all(len(fb["sources"]) >= 1 for fb in sub1["question_feedback"])

    # Step 6: Generate Custom Quiz #2 immediately & pass 100% -> Gap should become IMPROVING, NOT RESOLVED yet!
    t_base = datetime.now(timezone.utc)
    quiz2 = cq.generate(user_id=user_id, tenant_id=tenant, num_questions=4, force_new=True)
    with cq_rag_engine.db.session() as db:
        q2_rows = db.query(CustomQuizQuestion).filter_by(quiz_id=quiz2.id).order_by(CustomQuizQuestion.order_index).all()
        q2_answers = {r.id: r.correct_option_id for r in q2_rows}
        q2_hashes = {r.question_hash for r in q2_rows}

    sub2 = cq.submit(
        quiz_id=quiz2.id,
        user_id=user_id,
        answers=q2_answers,
        tenant_id=tenant,
        duration_seconds=55,
        completed_at=t_base,
    )
    assert sub2.percentage == 100.0
    assert sub2.outcome == "PASSED"
    assert any(u["new_status"] == "IMPROVING" for u in sub2.updated_gaps)
    assert not any(u["new_status"] == "RESOLVED" for u in sub2.updated_gaps), "Single pass must not immediately resolve a gap"

    # Step 7: After retention interval (+30h > 24h), generate Custom Quiz #3 -> different questions & gap RESOLVED!
    quiz3 = cq.generate(user_id=user_id, tenant_id=tenant, num_questions=4, force_new=True)
    with cq_rag_engine.db.session() as db:
        q3_rows = db.query(CustomQuizQuestion).filter_by(quiz_id=quiz3.id).order_by(CustomQuizQuestion.order_index).all()
        q3_answers = {r.id: r.correct_option_id for r in q3_rows}
        q3_hashes = {r.question_hash for r in q3_rows}
        assert q3_hashes != q1_hashes or q3_hashes != q2_hashes

    sub3 = cq.submit(
        quiz_id=quiz3.id,
        user_id=user_id,
        answers=q3_answers,
        tenant_id=tenant,
        duration_seconds=42,
        completed_at=t_base + timedelta(hours=30),
    )
    assert sub3.percentage == 100.0
    assert any(u["new_status"] == "RESOLVED" for u in sub3.updated_gaps)

    # Check stored DB states & profile stage progression
    with cq_rag_engine.db.session() as db:
        assert db.query(CourseQuizAttempt).filter_by(user_id=user_id, tenant_id=tenant).count() == 1
        assert db.query(CustomQuiz).filter_by(user_id=user_id, tenant_id=tenant).count() == 3
        assert db.query(CustomQuizAttempt).filter_by(user_id=user_id, tenant_id=tenant).count() == 3
        resolved_gaps = db.query(LearningGap).filter_by(user_id=user_id, tenant_id=tenant, status="RESOLVED").all()
        assert len(resolved_gaps) >= 1
        profiles = db.query(UserKnowledgeProfile).filter_by(user_id=user_id, tenant_id=tenant).all()
        assert any(p.learning_stage == "COMPETENZA_CONSOLIDATA" for p in profiles)

    # Step 8: Longitudinal Learning Metrics via HTTP API
    metrics_resp = client.get(f"/api/v1/customquiz/user/{user_id}/learning-metrics", headers=headers)
    assert metrics_resp.status_code == 200
    m = metrics_resp.json()
    assert m["attempts_count"] == 3
    assert m["quiz_accuracy"] > 50.0
    assert m["learning_improvement"] is not None and m["learning_improvement"] > 0.0
    assert m["knowledge_gap_resolution_rate"] > 0.0
    assert m["retention_rate"] == 100.0
    assert m["learning_progress"] > 0.0
    assert len(m["per_topic_evolution"]) >= 1

    # Results retrieval endpoint check for quiz3
    res3_resp = client.get(f"/api/v1/customquiz/{quiz3.id}/results", headers=headers)
    assert res3_resp.status_code == 200
    assert res3_resp.json()["percentage"] == 100.0


def test_idempotency_and_async_custom_quiz_generation(cq_rag_engine: RAGEngine) -> None:
    """Verify idempotency reuse window and ThreadPoolExecutor async generation mode."""
    cq = CustomQuizEngine(cq_rag_engine)
    cq_rag_engine.answer_query(
        RAGQueryRequest(query="Non riesco ad inviare i ticket su OTRS, aiuto", user_id="op_async", session_id="s_async")
    )

    q_first = cq.generate(user_id="op_async", tenant_id="t1", num_questions=4, force_new=False)
    q_reuse = cq.generate(user_id="op_async", tenant_id="t1", num_questions=4, force_new=False)
    assert q_reuse.id == q_first.id

    q_async = cq.generate(user_id="op_async", tenant_id="t1", num_questions=4, force_new=True, run_async=True)
    assert q_async.id != q_first.id
    final = None
    for _ in range(30):
        current = cq.get_quiz(q_async.id, tenant_id="t1", user_id="op_async")
        if current and current.status == "READY":
            final = current
            break
        time.sleep(0.1)
    assert final is not None
    assert final.status == "READY"
    assert len(final.questions) == 4


def test_learning_metrics_filtering_and_zero_history_safety(cq_rag_engine: RAGEngine) -> None:
    """Verify topic/software/module/date filters on metrics and safe handling of users with zero activity."""
    app = create_app(engine=cq_rag_engine, settings=cq_rag_engine.settings)
    client = TestClient(app)
    headers_empty = {"X-Tenant-ID": "default", "X-User-ID": "op_nuovo", "X-User-Role": "operatore"}

    # Zero-history user gets clean profile & 0 metrics with no negative penalty
    prof = client.get("/api/v1/customquiz/user/op_nuovo/learning-profile", headers=headers_empty)
    assert prof.status_code == 200
    assert prof.json()["open_gaps"] == []
    assert prof.json()["difficulty_topics"] == []

    metrics = client.get("/api/v1/customquiz/user/op_nuovo/learning-metrics", headers=headers_empty)
    assert metrics.status_code == 200
    assert metrics.json()["attempts_count"] == 0
    assert metrics.json()["quiz_accuracy"] == 0.0

    # Generate fails gracefully with 404 when no evidence exists
    gen = client.post("/api/v1/customquiz/generate", json={"user_id": "op_nuovo"}, headers=headers_empty)
    assert gen.status_code == 404

    # Filtered metrics check on an active user
    cq = CustomQuizEngine(cq_rag_engine)
    cq_rag_engine.answer_query(
        RAGQueryRequest(query="Non riesco a gestire i codici IUV PagoPA su CWOL, errore", user_id="op_filt", session_id="s_f")
    )
    q = cq.generate(user_id="op_filt", tenant_id="default", num_questions=4, software="CWOL")
    with cq_rag_engine.db.session() as db:
        rows = db.query(CustomQuizQuestion).filter_by(quiz_id=q.id).all()
        ans = {r.id: r.correct_option_id for r in rows}
    cq.submit(quiz_id=q.id, user_id="op_filt", answers=ans, tenant_id="default")

    m_cwol = cq.get_learning_metrics("op_filt", tenant_id="default", software="CWOL")
    assert m_cwol.attempts_count == 1
    assert m_cwol.quiz_accuracy == 100.0

    m_other = cq.get_learning_metrics("op_filt", tenant_id="default", software="SoftwareInesistente")
    assert m_other.attempts_count == 0

    future_from = datetime.now(timezone.utc) + timedelta(days=7)
    m_future = cq.get_learning_metrics("op_filt", tenant_id="default", date_from=future_from)
    assert m_future.attempts_count == 0


def test_user_tenant_isolation_rbac_and_gdpr_delete(cq_rag_engine: RAGEngine) -> None:
    """Verify strict user isolation, admin spoofing defense, cross-tenant block, and GDPR deletion."""
    app = create_app(engine=cq_rag_engine, settings=cq_rag_engine.settings)
    client = TestClient(app)

    cq = CustomQuizEngine(cq_rag_engine)
    cq_rag_engine.answer_query(
        RAGQueryRequest(query="Non riesco ad aprire ticket OTRS, aiuto", user_id="user_a", session_id="s_a")
    )
    quiz_a = cq.generate(user_id="user_a", tenant_id="tenant_1", num_questions=4)

    # Anonymous user denied
    anon = client.get("/api/v1/customquiz/user/user_a/learning-profile", headers={"X-Tenant-ID": "tenant_1"})
    assert anon.status_code == 403

    # user_b cannot view user_a's profile, quiz, or delete user_a's data
    headers_b = {"X-Tenant-ID": "tenant_1", "X-User-ID": "user_b", "X-User-Role": "operatore"}
    assert client.get("/api/v1/customquiz/user/user_a/learning-profile", headers=headers_b).status_code == 403
    assert client.get(f"/api/v1/customquiz/{quiz_a.id}", headers=headers_b).status_code == 403
    assert client.delete("/api/v1/customquiz/user/user_a/data", headers=headers_b).status_code == 403

    # Spoofed admin without valid X-Admin-Key stays 'operatore' -> 403
    spoof_admin = {
        "X-Tenant-ID": "tenant_1",
        "X-User-ID": "attacker",
        "X-User-Role": "admin",
        "X-Admin-Key": "wrong-key",
    }
    assert client.get("/api/v1/customquiz/user/user_a/learning-profile", headers=spoof_admin).status_code == 403

    # Cross-tenant isolation even for user_a if calling under tenant_2
    cross_tenant = {"X-Tenant-ID": "tenant_2", "X-User-ID": "user_a", "X-User-Role": "operatore"}
    assert client.get(f"/api/v1/customquiz/{quiz_a.id}", headers=cross_tenant).status_code == 404

    # Owner deletes their own learning data -> all tables cleaned
    headers_a = {"X-Tenant-ID": "tenant_1", "X-User-ID": "user_a", "X-User-Role": "operatore"}
    del_resp = client.delete("/api/v1/customquiz/user/user_a/data", headers=headers_a)
    assert del_resp.status_code == 200
    assert del_resp.json()["custom_quizzes"] == 1
    assert client.get(f"/api/v1/customquiz/{quiz_a.id}", headers=headers_a).status_code == 404


def test_qwen_structured_custom_quiz_generation_and_prompt_security(cq_settings: Settings, cq_rag_engine: RAGEngine) -> None:
    """Verify Qwen-compatible structured output produces 4-option Custom Quizzes and keeps prompt isolation."""
    from operator_copilot.course_generator.prompts import CUSTOM_QUIZ_PROMPT

    assert any("<retrieved_context>" in m.prompt.template for m in CUSTOM_QUIZ_PROMPT.messages)
    assert any("</retrieved_context>" in m.prompt.template for m in CUSTOM_QUIZ_PROMPT.messages)

    structured_payload = {
        "questions": [
            {
                "question_text": "Quale canale ufficiale va usato per inviare un ticket di assistenza secondo Comunicazione 7/2024?",
                "options": [
                    "Sistema OTRS all'indirizzo supporto@palitalsoft.it",
                    "Messaggio privato su chat non tracciata",
                    "Email personale dell'operatore senza oggetto",
                    "Foglio cartaceo interno",
                ],
                "correct_option_index": 0,
                "explanation": "La Comunicazione n. 7/2024 indica il sistema OTRS (supporto@palitalsoft.it).",
                "topic": "Richiesta assistenza e compilazione ticket",
                "difficulty": "base",
                "source_section": "1.1 - Canali ufficiali",
            },
            {
                "question_text": "Quali elementi strutturali sono obbligatori nel ticket OTRS?",
                "options": [
                    "Solo allegato ZIP anonimo",
                    "OGGETTO, CORPO dettagliato e FIRMA con telefono",
                    "Unicamente il codice fiscale del cliente",
                    "Solo la data di invio",
                ],
                "correct_option_index": 1,
                "explanation": "La sezione 2.3 richiede OGGETTO, CORPO e FIRMA con recapito telefonico.",
                "topic": "Richiesta assistenza e compilazione ticket",
                "difficulty": "intermediate",
                "source_section": "2.3 - Struttura del ticket",
            },
        ]
    }
    qwen_settings = cq_settings.model_copy(update={"llm_provider": "ollama", "llm_model": "qwen2.5:7b-instruct"})
    qwen_gen = AnswerGenerator(qwen_settings, llm=QwenMockChatModel(responses=[json.dumps(structured_payload)]))
    assert qwen_gen.get_model_info()["configured_model"] == "qwen2.5:7b-instruct"

    cq_rag_engine.answer_query(
        RAGQueryRequest(query="Non riesco ad aprire un ticket su OTRS, aiuto", user_id="op_qwen", session_id="s_qwen")
    )
    cq = CustomQuizEngine(cq_rag_engine)
    cq.service.generator = qwen_gen
    cq.service.quiz_gen.generator = qwen_gen

    quiz = cq.generate(user_id="op_qwen", tenant_id="default", num_questions=2)
    assert quiz.status == "READY"
    assert quiz.model_used == "ollama:qwen2.5:7b-instruct"
    assert len(quiz.questions) == 2
    for q in quiz.questions:
        assert [o.id for o in q.options] == ["A", "B", "C", "D"]
