"""Comprehensive tests for Milestone 4 – Owner Learning Dashboard & Analytics."""

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
    CustomQuizQuestion,
    OrganizationUser,
    OwnerAuditLog,
)
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
    """Fake LangChain ChatModel reporting Qwen model_name for structured JSON insights tests."""

    model_name: str = "qwen2.5:7b-instruct"


@pytest.fixture()
def owner_data_dir(tmp_path: Path) -> Path:
    data_root = tmp_path / "owner_data"
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
def owner_settings(tmp_path: Path, owner_data_dir: Path) -> Settings:
    cfg = Settings(
        app_env="test",
        llm_provider="extractive",
        llm_model="qwen2.5:7b-instruct",
        llm_expected_model_family="qwen",
        embedding_provider="hashing",
        embedding_model="hashing-128",
        vectorstore_type="chroma",
        vectorstore_path=tmp_path / "storage" / "vectorstore",
        collection_name=f"owner_col_{tmp_path.name}",
        data_dir=owner_data_dir,
        database_url=f"sqlite:///{(tmp_path / 'storage' / 'owner_dashboard.db').as_posix()}",
        admin_api_key="admin-secret",
        owner_api_key="owner-secret",
        owner_dashboard_cache_ttl_seconds=30,
        topic_critical_error_rate=40.0,
        topic_critical_min_gaps=2,
        topic_high_error_rate=20.0,
        topic_medium_error_rate=10.0,
        learning_retention_min_hours=24.0,
        custom_quiz_reuse_hours=24,
        log_level="WARNING",
    )
    cfg.ensure_directories()
    return cfg


@pytest.fixture()
def owner_rag_engine(owner_settings: Settings) -> RAGEngine:
    db = DatabaseManager(owner_settings.database_url)
    indexer = DocumentIndexer(settings=owner_settings, db_manager=db)
    indexer.run_ingestion(rebuild=True)
    return RAGEngine(settings=owner_settings, db_manager=db)


def _create_course_with_quiz(rag: RAGEngine, *, doc_filename: str, tenant_id: str) -> tuple[str, str]:
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
    bundle = extractor.load_document_bundle(doc_filename)
    assert bundle is not None
    topic = extractor.extract_from_bundle(bundle, tenant_id=tenant_id, classifier=classifier)
    scorer.score_topic(topic, persist=True)
    opp = aggregator.build_opportunity_from_topics([topic], tenant_id=tenant_id, persist=True)
    course = course_gen.generate_from_opportunity(opp.id, tenant_id=tenant_id, created_by="owner_setup")
    quiz = course_gen.generate_quiz(course.id, tenant_id=tenant_id, num_questions=4)
    return course.id, quiz.id


def _submit_course_quiz(
    rag: RAGEngine,
    client: TestClient,
    *,
    tenant_id: str,
    user_id: str,
    course_id: str,
    course_quiz_id: str,
    pass_quiz: bool,
) -> None:
    headers = {"X-Tenant-ID": tenant_id, "X-User-ID": user_id, "X-User-Role": "operatore"}
    from operator_copilot.db.models import QuizQuestion

    with rag.db.session() as db:
        q_rows = db.query(QuizQuestion).filter_by(quiz_id=course_quiz_id).order_by(QuizQuestion.order_index).all()
        assert len(q_rows) > 0
        if pass_quiz:
            ans = {r.id: r.correct_answer for r in q_rows}
        else:
            ans = {r.id: "Risposta errata intenzionale per test" for r in q_rows}

    sub = client.post(
        f"/api/v1/academy/courses/{course_id}/quizzes/{course_quiz_id}/submit",
        json={"user_id": user_id, "answers": ans},
        headers=headers,
    )
    assert sub.status_code == 200


def _seed_owner_learning_dataset(rag: RAGEngine, client: TestClient) -> dict[str, str]:
    """Build deterministic multi-user, multi-administration, multi-tenant dataset via real engines."""
    cq = CustomQuizEngine(rag)
    tenant_a = "tenant_alfa"
    tenant_b = "tenant_beta"

    owner_headers_a = {
        "X-Tenant-ID": tenant_a,
        "X-User-ID": "owner_alfa",
        "X-User-Role": "owner",
        "X-Owner-Key": "owner-secret",
    }
    owner_headers_b = {
        "X-Tenant-ID": tenant_b,
        "X-User-ID": "owner_beta",
        "X-User-Role": "owner",
        "X-Owner-Key": "owner-secret",
    }

    # Courses in tenant_alfa (OTRS support + CWOL SIOPE+/PagoPA) and tenant_beta
    c_otrs, q_otrs = _create_course_with_quiz(
        rag,
        doc_filename="2024_c07_modalita_corretta_richiesta_assistenza_clienti.md",
        tenant_id=tenant_a,
    )
    c_cwol, q_cwol = _create_course_with_quiz(
        rag,
        doc_filename="2025_c10_siope_pagopa.md",
        tenant_id=tenant_a,
    )
    _c_beta, _q_beta = _create_course_with_quiz(
        rag,
        doc_filename="2025_c10_siope_pagopa.md",
        tenant_id=tenant_b,
    )

    # Register users in Organization Directory across administrations
    for hdrs, payload in [
        (owner_headers_a, {"user_id": "op_maria", "display_name": "Maria Rossi", "amministrazione": "Comune Alfa"}),
        (owner_headers_a, {"user_id": "op_luca", "display_name": "Luca Bianchi", "amministrazione": "Comune Alfa"}),
        (owner_headers_a, {"user_id": "op_giulia", "display_name": "Giulia Verdi", "amministrazione": "Comune Beta"}),
        (owner_headers_a, {"user_id": "op_zero", "display_name": "Operatore Zero", "amministrazione": "Comune Alfa"}),
        (owner_headers_b, {"user_id": "op_esterno", "display_name": "Utente Tenant B", "amministrazione": "Provincia Gamma"}),
    ]:
        r = client.post("/api/v1/owner/users", json=payload, headers=hdrs)
        assert r.status_code == 200

    now = datetime.now(timezone.utc)

    # --- 1. op_maria (Comune Alfa): Pass CWOL course, fail OTRS course, trouble RAG on OTRS -> CQ1 fail -> CQ2 pass -> CQ3 (+30h) pass => RESOLVED ---
    _submit_course_quiz(
        rag,
        client,
        tenant_id=tenant_a,
        user_id="op_maria",
        course_id=c_cwol,
        course_quiz_id=q_cwol,
        pass_quiz=True,
    )
    _submit_course_quiz(
        rag,
        client,
        tenant_id=tenant_a,
        user_id="op_maria",
        course_id=c_otrs,
        course_quiz_id=q_otrs,
        pass_quiz=False,
    )
    rag.answer_query(
        RAGQueryRequest(
            query="Non riesco ad aprire ticket OTRS assistenza clienti, errore campi obbligatori",
            user_id="op_maria",
            tenant_id=tenant_a,
        )
    )
    cq_m1 = cq.generate(user_id="op_maria", tenant_id=tenant_a, num_questions=4, force_new=True)
    with rag.db.session() as db:
        rows = db.query(CustomQuizQuestion).filter_by(quiz_id=cq_m1.id).order_by(CustomQuizQuestion.order_index).all()
        ans_fail = {
            r.id: (r.correct_option_id if i == 0 else ("B" if r.correct_option_id != "B" else "A"))
            for i, r in enumerate(rows)
        }
    cq.submit(
        quiz_id=cq_m1.id,
        user_id="op_maria",
        answers=ans_fail,
        tenant_id=tenant_a,
        duration_seconds=80,
        completed_at=now - timedelta(hours=36),
    )
    cq_m2 = cq.generate(user_id="op_maria", tenant_id=tenant_a, num_questions=4, force_new=True)
    with rag.db.session() as db:
        rows = db.query(CustomQuizQuestion).filter_by(quiz_id=cq_m2.id).order_by(CustomQuizQuestion.order_index).all()
        ans_ok = {r.id: r.correct_option_id for r in rows}
    cq.submit(
        quiz_id=cq_m2.id,
        user_id="op_maria",
        answers=ans_ok,
        tenant_id=tenant_a,
        duration_seconds=50,
        completed_at=now - timedelta(hours=32),
    )
    cq_m3 = cq.generate(user_id="op_maria", tenant_id=tenant_a, num_questions=4, force_new=True)
    with rag.db.session() as db:
        rows = db.query(CustomQuizQuestion).filter_by(quiz_id=cq_m3.id).order_by(CustomQuizQuestion.order_index).all()
        ans_ok3 = {r.id: r.correct_option_id for r in rows}
    sub_m3 = cq.submit(
        quiz_id=cq_m3.id,
        user_id="op_maria",
        answers=ans_ok3,
        tenant_id=tenant_a,
        duration_seconds=40,
        completed_at=now,
    )
    assert any(u["new_status"] == "RESOLVED" for u in sub_m3.updated_gaps)

    # --- 2. op_luca (Comune Alfa): Single pass only -> IMPROVING (must NOT count as RESOLVED!) ---
    _submit_course_quiz(
        rag,
        client,
        tenant_id=tenant_a,
        user_id="op_luca",
        course_id=c_otrs,
        course_quiz_id=q_otrs,
        pass_quiz=False,
    )
    cq_l1 = cq.generate(user_id="op_luca", tenant_id=tenant_a, num_questions=4, force_new=True)
    with rag.db.session() as db:
        rows = db.query(CustomQuizQuestion).filter_by(quiz_id=cq_l1.id).order_by(CustomQuizQuestion.order_index).all()
        ans_fail_l = {r.id: ("B" if r.correct_option_id != "B" else "A") for r in rows}
    cq.submit(
        quiz_id=cq_l1.id,
        user_id="op_luca",
        answers=ans_fail_l,
        tenant_id=tenant_a,
        completed_at=now - timedelta(hours=5),
    )
    cq_l2 = cq.generate(user_id="op_luca", tenant_id=tenant_a, num_questions=4, force_new=True)
    with rag.db.session() as db:
        rows = db.query(CustomQuizQuestion).filter_by(quiz_id=cq_l2.id).order_by(CustomQuizQuestion.order_index).all()
        ans_ok_l = {r.id: r.correct_option_id for r in rows}
    sub_l2 = cq.submit(
        quiz_id=cq_l2.id,
        user_id="op_luca",
        answers=ans_ok_l,
        tenant_id=tenant_a,
        completed_at=now - timedelta(hours=4),
    )
    assert not any(u["new_status"] == "RESOLVED" for u in sub_l2.updated_gaps)

    # --- 3. op_giulia (Comune Beta): Repeated errors -> CRITICAL open gap ---
    _submit_course_quiz(
        rag,
        client,
        tenant_id=tenant_a,
        user_id="op_giulia",
        course_id=c_cwol,
        course_quiz_id=q_cwol,
        pass_quiz=False,
    )
    _submit_course_quiz(
        rag,
        client,
        tenant_id=tenant_a,
        user_id="op_giulia",
        course_id=c_otrs,
        course_quiz_id=q_otrs,
        pass_quiz=False,
    )
    rag.answer_query(
        RAGQueryRequest(
            query="Errore blocco invio SIOPE+ IUV su CWOL aiuto urgente",
            user_id="op_giulia",
            tenant_id=tenant_a,
        )
    )
    for delta_h in (6, 2):
        cq_g = cq.generate(user_id="op_giulia", tenant_id=tenant_a, num_questions=4, force_new=True)
        with rag.db.session() as db:
            rows = db.query(CustomQuizQuestion).filter_by(quiz_id=cq_g.id).order_by(CustomQuizQuestion.order_index).all()
            ans_g = {r.id: ("C" if r.correct_option_id != "C" else "D") for r in rows}
        cq.submit(
            quiz_id=cq_g.id,
            user_id="op_giulia",
            answers=ans_g,
            tenant_id=tenant_a,
            completed_at=now - timedelta(hours=delta_h),
        )

    # --- 4. op_esterno in tenant_beta (must NEVER leak into tenant_alfa) ---
    rag.answer_query(
        RAGQueryRequest(
            query="Errore critico isolato solo in tenant_beta su CWOL",
            user_id="op_esterno",
            tenant_id=tenant_b,
        )
    )

    return {"course_otrs": c_otrs, "course_cwol": c_cwol}


def test_owner_access_control_and_anti_spoofing(owner_rag_engine: RAGEngine) -> None:
    """Only verified Owner headers (role=owner + valid X-Owner-Key + non-anonymous) can access Owner APIs."""
    app = create_app(engine=owner_rag_engine, settings=owner_rag_engine.settings)
    client = TestClient(app)

    # Anonymous / Operator / Admin without owner credentials -> 403
    bad_header_sets = [
        {},
        {"X-Tenant-ID": "default", "X-User-ID": "op1", "X-User-Role": "operatore"},
        {"X-Tenant-ID": "default", "X-User-ID": "admin1", "X-User-Role": "admin", "X-Admin-Key": "admin-secret"},
        {"X-Tenant-ID": "default", "X-User-ID": "anonymous", "X-User-Role": "owner", "X-Owner-Key": "owner-secret"},
        {"X-Tenant-ID": "default", "X-User-ID": "owner1", "X-User-Role": "owner", "X-Owner-Key": "wrong-key"},
        {"X-Tenant-ID": "default", "X-User-ID": "owner1", "X-User-Role": "owner"},
    ]

    for hdrs in bad_header_sets:
        assert client.get("/api/v1/owner/overview", headers=hdrs).status_code == 403
        assert client.get("/api/v1/owner/users", headers=hdrs).status_code == 403
        assert client.get("/api/v1/owner/topics-to-review", headers=hdrs).status_code == 403
        assert client.get("/api/v1/owner/customquiz-analytics", headers=hdrs).status_code == 403
        assert client.get("/api/v1/owner/insights", headers=hdrs).status_code == 403

    # Valid Owner credentials succeed
    ok_headers = {
        "X-Tenant-ID": "default",
        "X-User-ID": "owner_main",
        "X-User-Role": "owner",
        "X-Owner-Key": "owner-secret",
    }
    resp = client.get("/api/v1/owner/overview", headers=ok_headers)
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "default"


def test_owner_dashboard_metrics_isolation_drilldowns_and_ui(owner_rag_engine: RAGEngine) -> None:
    """Full Milestone 4 verification: KPIs, filters, zero-history user, multi-tenant + scope isolation, analytics, insights, UI."""
    app = create_app(engine=owner_rag_engine, settings=owner_rag_engine.settings)
    client = TestClient(app)
    _seed_owner_learning_dataset(owner_rag_engine, client)

    owner_alfa = {
        "X-Tenant-ID": "tenant_alfa",
        "X-User-ID": "owner_alfa",
        "X-User-Role": "owner",
        "X-Owner-Key": "owner-secret",
    }
    scoped_comune_alfa = {**owner_alfa, "X-Owner-Scope": "Comune Alfa"}
    owner_beta = {
        "X-Tenant-ID": "tenant_beta",
        "X-User-ID": "owner_beta",
        "X-User-Role": "owner",
        "X-Owner-Key": "owner-secret",
    }

    # 1. HTML UI page accessible and wired to /api/v1/owner/*
    ui_resp = client.get("/owner")
    assert ui_resp.status_code == 200
    assert "Owner Dashboard" in ui_resp.text
    assert "/api/v1/owner/overview" in ui_resp.text
    assert "Topic da ripassare" in ui_resp.text
    assert "Custom Quiz Performance" in ui_resp.text

    # 2. Overview metrics computed from real SQLite data (refresh=true)
    ov_resp = client.get("/api/v1/owner/overview?refresh=true", headers=owner_alfa)
    assert ov_resp.status_code == 200
    ov = ov_resp.json()
    assert ov["total_users"] == 4  # op_maria, op_luca, op_giulia, op_zero (NEVER op_esterno!)
    assert ov["active_users_in_period"] == 3
    assert ov["open_gaps_count"] >= 2
    assert ov["users_with_critical_gaps"] >= 1
    assert ov["knowledge_gap_resolution_rate"] > 0.0
    assert "Comune Alfa" in ov["available_administrations"]
    assert "Comune Beta" in ov["available_administrations"]
    assert "Provincia Gamma" not in ov["available_administrations"]

    # Cache hit check + speed benchmark
    t0 = time.perf_counter()
    ov_cached = client.get("/api/v1/owner/overview", headers=owner_alfa)
    t1 = time.perf_counter()
    assert ov_cached.status_code == 200
    assert ov_cached.json()["total_users"] == 4
    assert (t1 - t0) < 0.5

    # Administration filter + Scoped Owner isolation
    ov_scoped = client.get("/api/v1/owner/overview?refresh=true", headers=scoped_comune_alfa).json()
    assert ov_scoped["total_users"] == 3  # op_maria, op_luca, op_zero (op_giulia excluded!)
    assert ov_scoped["available_administrations"] == ["Comune Alfa"]

    # Attempting to upsert user outside X-Owner-Scope fails 403
    bad_upsert = client.post(
        "/api/v1/owner/users",
        json={"user_id": "op_illegal", "display_name": "Illegal", "amministrazione": "Comune Beta"},
        headers=scoped_comune_alfa,
    )
    assert bad_upsert.status_code == 403

    # Multi-tenant isolation: tenant_alfa cannot see tenant_beta user
    assert client.get("/api/v1/owner/users/op_esterno", headers=owner_alfa).status_code == 404
    # Scoped Comune Alfa owner cannot access op_giulia (Comune Beta)
    assert client.get("/api/v1/owner/users/op_giulia", headers=scoped_comune_alfa).status_code == 404
    # tenant_beta sees strictly 1 user
    ov_beta = client.get("/api/v1/owner/overview?refresh=true", headers=owner_beta).json()
    assert ov_beta["total_users"] == 1

    # 3. User Learning Overview: search, status filter, pagination, sorting, zero-history user
    u_page1 = client.get(
        "/api/v1/owner/users?page=1&page_size=2&sort_by=open_gaps_count&sort_dir=desc",
        headers=owner_alfa,
    )
    assert u_page1.status_code == 200
    p1 = u_page1.json()
    assert p1["total"] == 4
    assert len(p1["items"]) == 2
    assert p1["items"][0]["open_gaps_count"] >= p1["items"][1]["open_gaps_count"]

    u_giulia = client.get("/api/v1/owner/users?search=Giulia&learning_status=ATTENZIONE_CRITICA", headers=owner_alfa).json()
    assert u_giulia["total"] == 1
    assert u_giulia["items"][0]["user_id"] == "op_giulia"
    assert u_giulia["items"][0]["overall_status"] == "ATTENZIONE_CRITICA"

    u_zero = client.get("/api/v1/owner/users/op_zero", headers=owner_alfa)
    assert u_zero.status_code == 200
    zd = u_zero.json()
    assert zd["learning_performance"]["custom_quiz_evolution"] == []
    assert zd["learning_performance"]["course_quiz_evolution"] == []
    assert zd["learning_performance"]["courses_completed"] == []
    assert zd["knowledge_gaps"] == []

    # Check op_maria summary row includes learning_improvement > 0
    u_maria_row = client.get("/api/v1/owner/users?search=Maria", headers=owner_alfa).json()
    assert u_maria_row["total"] == 1
    assert u_maria_row["items"][0]["learning_improvement"] > 0.0
    assert u_maria_row["items"][0]["custom_quizzes_count"] == 3

    # 4. Individual User Detail & Gaps (op_maria completed 1 course and improved on Custom Quizzes)
    maria_detail = client.get("/api/v1/owner/users/op_maria", headers=owner_alfa)
    assert maria_detail.status_code == 200
    md = maria_detail.json()
    assert md["display_name"] == "Maria Rossi"
    assert md["amministrazione"] == "Comune Alfa"
    assert len(md["learning_performance"]["courses_completed"]) >= 1
    assert len(md["learning_performance"]["custom_quiz_evolution"]) == 3
    assert len(md["learning_performance"]["competence_over_time"]) >= 1
    assert len(md["knowledge_gaps"]) >= 1
    assert any(g["status"] == "RESOLVED" for g in md["knowledge_gaps"])
    assert len(md["learning_history"]) >= 4

    maria_gaps = client.get("/api/v1/owner/users/op_maria/gaps", headers=owner_alfa)
    assert maria_gaps.status_code == 200
    assert len(maria_gaps.json()) >= 1

    # 5. Topics to Review & Drill-down
    topics_resp = client.get("/api/v1/owner/topics-to-review", headers=owner_alfa)
    assert topics_resp.status_code == 200
    topics = topics_resp.json()
    assert len(topics) >= 1
    target_topic = topics[0]["topic"]
    assert topics[0]["affected_users_count"] >= 1
    assert topics[0]["criticality"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW")

    drill_resp = client.get(f"/api/v1/owner/topics-to-review/{target_topic}/users", headers=owner_alfa)
    assert drill_resp.status_code == 200
    drill = drill_resp.json()
    assert drill["topic_summary"]["topic"] == target_topic
    assert len(drill["affected_users"]) >= 1

    # 6. Custom Quiz Analytics (only op_maria resolved after >= 2 spaced verifications; op_luca must NOT count)
    cq_resp = client.get("/api/v1/owner/customquiz-analytics", headers=owner_alfa)
    assert cq_resp.status_code == 200
    cqa = cq_resp.json()
    assert cqa["total_generated"] == 7  # Maria 3 + Luca 2 + Giulia 2
    assert cqa["total_completed"] == 7
    assert cqa["gaps_resolved_via_followup"] >= 1
    assert cqa["persistent_gaps_count"] >= 1
    # Check Comune Alfa vs Beta scope on Custom Quiz analytics
    cqa_beta_filter = client.get("/api/v1/owner/customquiz-analytics?amministrazione=Comune Beta", headers=owner_alfa).json()
    assert cqa_beta_filter["total_completed"] == 2
    assert cqa_beta_filter["gaps_resolved_via_followup"] == 0

    # 7. Insights deterministic mode
    ins_resp = client.get("/api/v1/owner/insights", headers=owner_alfa)
    assert ins_resp.status_code == 200
    ins = ins_resp.json()
    assert len(ins["insights"]) >= 1
    assert all(item["source_engine"] == "deterministic" for item in ins["insights"])
    assert all(isinstance(item["evidence_metrics"], dict) and len(item["evidence_metrics"]) > 0 for item in ins["insights"])

    # 8. Audit logs persisted in SQLite for tenant_alfa only
    audit_resp = client.get("/api/v1/owner/audit-logs?limit=20", headers=owner_alfa)
    assert audit_resp.status_code == 200
    logs = audit_resp.json()
    assert len(logs) >= 5
    assert all(l["tenant_id"] == "tenant_alfa" for l in logs)
    with owner_rag_engine.db.session() as db:
        assert db.query(OwnerAuditLog).filter_by(tenant_id="tenant_alfa").count() >= 5


def test_owner_insights_qwen_synthesis_mode(owner_settings: Settings, owner_rag_engine: RAGEngine) -> None:
    """When Qwen LLM runtime is active and use_llm_synthesis=true, insights are synthesized without inventing metrics."""
    from operator_copilot.generation.answer_generator import AnswerGenerator

    app = create_app(engine=owner_rag_engine, settings=owner_rag_engine.settings)
    client = TestClient(app)
    _seed_owner_learning_dataset(owner_rag_engine, client)

    qwen_payload = json.dumps(
        {
            "insights": [
                {
                    "category": "topic",
                    "severity": "CRITICAL",
                    "message": "Il topic OTRS presenta un tasso di errore elevato sugli operatori analizzati.",
                    "recommended_action": "Organizzare un micro-modulo di ripasso sui campi obbligatori OTRS.",
                    "supporting_metric": "open_gaps_count >= 2",
                }
            ]
        },
        ensure_ascii=False,
    )
    qwen_settings = owner_settings.model_copy(update={"llm_provider": "ollama", "llm_model": "qwen2.5:7b-instruct"})
    owner_rag_engine.generator = AnswerGenerator(
        qwen_settings,
        llm=QwenMockChatModel(responses=[qwen_payload]),
    )

    owner_alfa = {
        "X-Tenant-ID": "tenant_alfa",
        "X-User-ID": "owner_alfa",
        "X-User-Role": "owner",
        "X-Owner-Key": "owner-secret",
    }
    resp = client.get("/api/v1/owner/insights?use_llm_synthesis=true", headers=owner_alfa)
    assert resp.status_code == 200
    data = resp.json()
    assert "qwen2.5:7b-instruct" in data["model_used"]
    assert any(item["source_engine"] == "qwen_synthesized" for item in data["insights"])
