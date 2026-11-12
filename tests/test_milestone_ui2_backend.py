"""Tests for minimal Milestone UI 2 backend extensions (Demo Mode Switcher + Lesson Completion + User Learning Overview)."""

from __future__ import annotations

from pathlib import Path
import uuid

from fastapi.testclient import TestClient

from operator_copilot.api.main import create_app
from operator_copilot.config.settings import Settings
from operator_copilot.course_generator.generator import AICourseGenerator
from operator_copilot.db.models import OrganizationUser
from operator_copilot.knowledge_intelligence.classifier import TopicClassifier
from operator_copilot.knowledge_intelligence.extractor import KnowledgeExtractor
from operator_copilot.knowledge_intelligence.opportunities import OpportunityAggregator
from operator_copilot.knowledge_intelligence.scorer import RelevanceScorer
from operator_copilot.retrieval.rag_engine import RAGEngine


def _setup_demo_app(tmp_path: Path, *, app_env: str = "development", demo_mode_enabled: bool = True) -> tuple[RAGEngine, TestClient, str, str]:
    data_dir = tmp_path / "data"
    area_dir = data_dir / "01 - Generali"
    area_dir.mkdir(parents=True)
    doc_name = "2024_assistenza.md"
    (area_dir / doc_name).write_text(
        "# Guida Assistenza OTRS\n\n"
        "## Apertura Ticket\n"
        "1. Accedere a OTRS.\n"
        "2. Inserire oggetto, descrizione e firma.\n",
        encoding="utf-8",
    )

    cfg = Settings(
        app_env=app_env,  # type: ignore[arg-type]
        demo_mode_enabled=demo_mode_enabled,
        llm_provider="extractive",
        embedding_provider="hashing",
        embedding_model="hashing-128",
        vectorstore_type="chroma",
        vectorstore_path=tmp_path / "vectorstore",
        collection_name=f"ui2_{tmp_path.name}",
        data_dir=data_dir,
        database_url=f"sqlite:///{(tmp_path / 'ui2.db').as_posix()}",
        retrieval_score_threshold=0.18,
        admin_api_key="adm-key",
        owner_api_key="own-key",
        log_level="WARNING",
    )
    cfg.ensure_directories()
    rag = RAGEngine(settings=cfg)
    rag.indexer.run_ingestion(rebuild=True)

    # Seed OrganizationUser records in tenant_alfa + tenant_beta
    with rag.db.session() as db:
        db.add(
            OrganizationUser(
                id=f"orgu_{uuid.uuid4().hex[:8]}",
                tenant_id="tenant_alfa",
                user_id="op_maria",
                display_name="Maria Rossi",
                amministrazione="Comune Alfa",
                role="operatore",
            )
        )
        db.add(
            OrganizationUser(
                id=f"orgu_{uuid.uuid4().hex[:8]}",
                tenant_id="tenant_alfa",
                user_id="owner_alfa",
                display_name="Elena Owner",
                amministrazione="Comune Alfa",
                role="owner",
            )
        )
        db.add(
            OrganizationUser(
                id=f"orgu_{uuid.uuid4().hex[:8]}",
                tenant_id="tenant_beta",
                user_id="op_esterno",
                display_name="Utente Beta",
                amministrazione="Comune Beta",
                role="operatore",
            )
        )
        db.commit()

    # Create one course with quiz in tenant_alfa
    extractor = KnowledgeExtractor(settings=cfg, db_manager=rag.db, retriever=rag.retriever, generator=rag.generator)
    classifier = TopicClassifier(generator=rag.generator)
    scorer = RelevanceScorer(db_manager=rag.db, generator=rag.generator)
    aggregator = OpportunityAggregator(db_manager=rag.db, retriever=rag.retriever)
    course_gen = AICourseGenerator(settings=cfg, db_manager=rag.db, extractor=extractor, generator=rag.generator)

    bundle = extractor.load_document_bundle(doc_name)
    assert bundle is not None
    topic = extractor.extract_from_bundle(bundle, tenant_id="tenant_alfa", classifier=classifier)
    scorer.score_topic(topic, persist=True)
    opp = aggregator.build_opportunity_from_topics([topic], tenant_id="tenant_alfa", persist=True)
    course = course_gen.generate_from_opportunity(opp.id, tenant_id="tenant_alfa", created_by="setup")
    lesson_id = course.modules[0].lessons[0].id

    app = create_app(engine=rag, settings=cfg)
    return rag, TestClient(app), course.id, lesson_id


def test_demo_switcher_security_isolation_and_lesson_progress(tmp_path: Path) -> None:
    rag, client, course_id, lesson_id = _setup_demo_app(tmp_path)

    # 1. Demo status active in development
    st = client.get("/api/v1/demo/status")
    assert st.status_code == 200
    assert st.json()["demo_mode_enabled"] is True

    # 2. Listing users is tenant-isolated (op_esterno NEVER appears in tenant_alfa)
    users_resp = client.get("/api/v1/demo/users", headers={"X-Tenant-ID": "tenant_alfa"})
    assert users_resp.status_code == 200
    user_ids = {u["user_id"] for u in users_resp.json()}
    assert user_ids == {"op_maria", "owner_alfa"}
    assert "op_esterno" not in user_ids

    # 3. Switching to unknown or cross-tenant user fails 404
    bad_switch = client.post(
        "/api/v1/demo/switch-user",
        json={"user_id": "op_esterno"},
        headers={"X-Tenant-ID": "tenant_alfa"},
    )
    assert bad_switch.status_code == 404

    # 4. Switch to operatore -> receives signed demo token; CANNOT access Owner APIs (403)
    op_switch = client.post(
        "/api/v1/demo/switch-user",
        json={"user_id": "op_maria"},
        headers={"X-Tenant-ID": "tenant_alfa"},
    )
    assert op_switch.status_code == 200
    op_token = op_switch.json()["token"]

    assert (
        client.get(
            "/api/v1/owner/overview",
            headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": op_token},
        ).status_code
        == 403
    )

    # 5. Tampered / cross-tenant token fails 403
    assert (
        client.get(
            "/api/v1/academy/courses",
            headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": op_token + "tamper"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/academy/courses",
            headers={"X-Tenant-ID": "tenant_beta", "X-Demo-Token": op_token},
        ).status_code
        == 403
    )

    # 6. Operator marks lesson completed and queries own learning-overview (cannot read another user's overview)
    cmp_resp = client.post(
        f"/api/v1/academy/courses/{course_id}/lessons/{lesson_id}/complete",
        headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": op_token},
    )
    assert cmp_resp.status_code == 200
    assert cmp_resp.json()["completed"] is True

    ov_resp = client.get(
        "/api/v1/academy/users/op_maria/learning-overview",
        headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": op_token},
    )
    assert ov_resp.status_code == 200
    ov = ov_resp.json()
    assert lesson_id in ov["completed_lesson_ids"]
    assert ov["course_progress"][0]["completed_lessons"] == 1

    # Isolation: op_maria cannot access owner_alfa's overview
    assert (
        client.get(
            "/api/v1/academy/users/owner_alfa/learning-overview",
            headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": op_token},
        ).status_code
        == 403
    )

    # 7. Switch to Owner -> server-signed demo token authorizes Owner Dashboard AND Learning Area courses
    own_switch = client.post(
        "/api/v1/demo/switch-user",
        json={"user_id": "owner_alfa"},
        headers={"X-Tenant-ID": "tenant_alfa"},
    )
    assert own_switch.status_code == 200
    own_token = own_switch.json()["token"]

    owner_ov = client.get(
        "/api/v1/owner/overview",
        headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": own_token},
    )
    assert owner_ov.status_code == 200
    assert owner_ov.json()["tenant_id"] == "tenant_alfa"

    owner_courses = client.get(
        "/api/v1/academy/courses",
        headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": own_token},
    )
    assert owner_courses.status_code == 200
    assert len(owner_courses.json()) == 1


def test_demo_mode_disabled_in_production(tmp_path: Path) -> None:
    _rag, client, _cid, _lid = _setup_demo_app(tmp_path, app_env="production", demo_mode_enabled=True)

    st = client.get("/api/v1/demo/status")
    assert st.status_code == 200
    assert st.json()["demo_mode_enabled"] is False

    assert client.get("/api/v1/demo/users", headers={"X-Tenant-ID": "tenant_alfa"}).status_code == 403
    assert (
        client.post(
            "/api/v1/demo/switch-user",
            json={"user_id": "op_maria"},
            headers={"X-Tenant-ID": "tenant_alfa"},
        ).status_code
        == 403
    )


def test_quiz_helpers_clean_markdown_natural_focus_and_shuffle() -> None:
    from operator_copilot.course_generator.quiz_helpers import (
        build_natural_focus,
        clean_markdown_to_plain,
        deterministic_shuffle_options,
        short_document_label,
        truncate_at_boundary,
    )

    cleaned = clean_markdown_to_plain("### 1.2 Chi contattare? **CWOL** usa `supporto@ente.it`")
    assert "#" not in cleaned
    assert "**" not in cleaned
    assert "1.2 Chi contattare? CWOL usa supporto@ente.it" == cleaned

    bounded = truncate_at_boundary("Parola lunga prima della fine della frase operativa completa.", max_len=36)
    assert not bounded.endswith(" dell…")
    assert bounded.endswith("…")

    assert short_document_label("01 - Info/2024_c07_doc.md") == "2024_c07_doc.md"
    assert (
        build_natural_focus("Comunicazione 01 > 1.1 Info", "Comunicazione 01")
        == "1.1 Info (Comunicazione 01)"
    )
    assert build_natural_focus("Ruoli", "Ruoli") == "Ruoli"

    positions = {
        deterministic_shuffle_options("Risposta esatta", ["D1", "D2", "D3"], seed_key=f"seed_{i}")[1]
        for i in range(12)
    }
    assert len(positions) > 1


def test_owner_course_authoring_and_rbac(tmp_path: Path) -> None:
    _rag, client, cid, lid = _setup_demo_app(tmp_path)

    op_token = client.post(
        "/api/v1/demo/switch-user",
        json={"user_id": "op_maria"},
        headers={"X-Tenant-ID": "tenant_alfa"},
    ).json()["token"]
    own_token = client.post(
        "/api/v1/demo/switch-user",
        json={"user_id": "owner_alfa"},
        headers={"X-Tenant-ID": "tenant_alfa"},
    ).json()["token"]

    # Operator cannot edit courses/lessons or change lifecycle
    assert (
        client.patch(
            f"/api/v1/academy/courses/{cid}",
            json={"title": "Titolo non autorizzato"},
            headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": op_token},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/academy/courses/generate",
            json={"document_source": "manuale_test.md"},
            headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": op_token},
        ).status_code
        == 403
    )
    # Spoofed owner without X-Demo-Token or X-Owner-Key rejected
    assert (
        client.patch(
            f"/api/v1/academy/courses/{cid}",
            json={"title": "Spoofed"},
            headers={"X-Tenant-ID": "tenant_alfa", "X-User-Role": "owner", "X-User-ID": "owner_elena"},
        ).status_code
        == 403
    )

    # Authenticated Owner can update course metadata & lesson content (version increments)
    patch_course = client.patch(
        f"/api/v1/academy/courses/{cid}",
        json={"title": "Corso Ruoli Rivisto", "difficulty": "intermedio", "change_summary": "Revisione Owner"},
        headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": own_token},
    )
    assert patch_course.status_code == 200
    assert patch_course.json()["title"] == "Corso Ruoli Rivisto"
    assert patch_course.json()["difficulty"] == "intermedio"
    assert patch_course.json()["current_version"] >= 1

    patch_lesson = client.patch(
        f"/api/v1/academy/courses/{cid}/lessons/{lid}",
        json={"summary": "Sintesi aggiornata dall'Owner"},
        headers={"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": own_token},
    )
    assert patch_lesson.status_code == 200
    assert patch_lesson.json()["summary"] == "Sintesi aggiornata dall'Owner"


def test_retrieval_query_normalization_and_dense_fallback(tmp_path: Path, monkeypatch) -> None:
    from operator_copilot.retrieval.reranker import normalize_retrieval_query

    assert (
        normalize_retrieval_query("yo bro come apro una richiesta di assistenza clienti??")
        == "come apro una richiesta di assistenza clienti?"
    )
    assert normalize_retrieval_query("Come si rimuove un verbale da un ruolo?") == "Come si rimuove un verbale da un ruolo?"

    data_dir = tmp_path / "data_ret"
    area_dir = data_dir / "15 - Codice della Strada"
    area_dir.mkdir(parents=True)
    (area_dir / "ruoli_verbale.md").write_text(
        "# Rimuovere un verbale da un ruolo\n"
        "Apri il ruolo interessato in Gestione Ruoli, individua il verbale nella griglia e usa F7 - Cancella per rimuovere l'associazione.\n\n"
        "# Aggiungere manualmente un verbale a un ruolo\n"
        "Menu: 30. Polizia Locale -> 10. Codice della Strada -> 30. Ruoli.\n",
        encoding="utf-8",
    )
    (data_dir / "01 - Generali").mkdir(parents=True)
    (data_dir / "01 - Generali" / "richiesta_assistenza.md").write_text(
        "# Modalita corretta richiesta assistenza clienti\n"
        "Per aprire una richiesta di assistenza clienti inviare un ticket via e-mail a supporto@cityware.it indicando oggetto ed ente.\n",
        encoding="utf-8",
    )
    (data_dir / "01 - Generali" / "altri_tributi.md").write_text(
        "# Gestione TARI e tributi locali\nCalcolo delle aliquote comunali e stampa avvisi di pagamento.\n",
        encoding="utf-8",
    )
    (data_dir / "01 - Generali" / "anagrafe.md").write_text(
        "# Servizi demografici e certificati\nEmissione certificati di residenza e stato di famiglia.\n",
        encoding="utf-8",
    )

    cfg = Settings(
        app_env="development",
        demo_mode_enabled=True,
        llm_provider="extractive",
        embedding_provider="hashing",
        embedding_model="hashing-128",
        vectorstore_type="chroma",
        vectorstore_path=tmp_path / "vectorstore_ret",
        collection_name=f"ret_{tmp_path.name}",
        data_dir=data_dir,
        database_url=f"sqlite:///{(tmp_path / 'ret.db').as_posix()}",
        dense_top_k=5,
        bm25_top_k=5,
        final_top_k=5,
        retrieval_score_threshold=0.18,
        log_level="WARNING",
    )
    cfg.ensure_directories()
    engine = RAGEngine(settings=cfg)
    engine.indexer.run_ingestion(rebuild=True)

    # Simulate partial/corrupt Chroma HNSW index: HNSW query misses docs and include=["embeddings"] raises InternalError
    real_vs = engine.retriever._get_vectorstore()
    real_get = real_vs._collection.get
    monkeypatch.setattr(
        real_vs._collection,
        "query",
        lambda *args, **kwargs: {"documents": [[]], "metadatas": [[]], "distances": [[]]},
    )

    def _broken_get(*args, **kwargs):
        if kwargs.get("include") == ["embeddings"]:
            raise RuntimeError("Internal error: Error finding id")
        return real_get(*args, **kwargs)

    monkeypatch.setattr(real_vs._collection, "get", _broken_get)
    monkeypatch.setattr(engine.retriever, "_get_vectorstore", lambda: real_vs)

    ruoli_hits = engine.retriever.retrieve("Come si rimuove un verbale da un ruolo?")
    assert len(ruoli_hits) >= 1
    assert "ruoli_verbale.md" in ruoli_hits[0].document.metadata["source"]
    assert ruoli_hits[0].dense_score > 0.0

    colloquial_hits = engine.retriever.retrieve("yo bro come apro una richiesta di assistenza clienti??")
    clean_hits = engine.retriever.retrieve("come apro una richiesta di assistenza clienti?")
    assert len(colloquial_hits) >= 1
    assert "richiesta_assistenza.md" in colloquial_hits[0].document.metadata["source"]
    assert colloquial_hits[0].dense_score > 0.0
    assert colloquial_hits[0].document.metadata["source"] == clean_hits[0].document.metadata["source"]
    assert colloquial_hits[0].relevance_score == clean_hits[0].relevance_score


def test_traditional_course_quiz_uses_contextual_distractors_without_ticket_filler(tmp_path: Path) -> None:
    from operator_copilot.course_generator.quiz_helpers import (
        build_contextual_distractors,
        truncate_at_boundary,
    )

    assert truncate_at_boundary("Seguire la guida '2. Ticket > 2.5 Esempio corretto operazione'", max_len=36) != "Seguire la guida '2."
    assert not truncate_at_boundary("Seguire la guida '2. Ticket > 2.5 Esempio'", max_len=24).endswith("2.")

    distractors = build_contextual_distractors(
        correct_option="Usare F7 - Cancella nella griglia di Gestione Ruoli per sbloccare il verbale dal ruolo.",
        focus="Rimuovere un verbale da un ruolo",
        mode="correct_rule",
    )
    assert len(distractors) == 3
    joined = " | ".join(distractors).lower()
    assert "sms" not in joined
    assert "mail automatica" not in joined
    assert "verbale" in joined or "ruolo" in joined

    data_dir = tmp_path / "data_quiz"
    area_dir = data_dir / "15 - Codice della Strada"
    area_dir.mkdir(parents=True)
    doc_name = "3.md"
    (area_dir / doc_name).write_text(
        "# Rimuovere un verbale da un ruolo\n"
        "Apri il ruolo interessato in Gestione Ruoli, quindi passa a Visualizza Ruolo.\n"
        "1. Individua il verbale nella griglia e aprilo con un doppio clic verificando gli estremi della posizione.\n"
        "2. Usa F7 - Cancella e conferma la cancellazione dal ruolo per sbloccare il verbale.\n\n"
        "Attenzione: se il ruolo e gia stato notificato all'esattore, l'operazione di cancellazione viene bloccata dal sistema.\n",
        encoding="utf-8",
    )

    cfg = Settings(
        app_env="development",
        demo_mode_enabled=True,
        llm_provider="extractive",
        embedding_provider="hashing",
        embedding_model="hashing-128",
        vectorstore_type="chroma",
        vectorstore_path=tmp_path / "vectorstore_quiz",
        collection_name=f"quiz_{tmp_path.name}",
        data_dir=data_dir,
        database_url=f"sqlite:///{(tmp_path / 'quiz.db').as_posix()}",
        retrieval_score_threshold=0.18,
        log_level="WARNING",
    )
    cfg.ensure_directories()
    rag = RAGEngine(settings=cfg)
    rag.indexer.run_ingestion(rebuild=True)

    extractor = KnowledgeExtractor(settings=cfg, db_manager=rag.db, retriever=rag.retriever, generator=rag.generator)
    classifier = TopicClassifier(generator=rag.generator)
    scorer = RelevanceScorer(db_manager=rag.db, generator=rag.generator)
    aggregator = OpportunityAggregator(db_manager=rag.db, retriever=rag.retriever)
    course_gen = AICourseGenerator(settings=cfg, db_manager=rag.db, extractor=extractor, generator=rag.generator)

    bundle = extractor.load_document_bundle(doc_name)
    assert bundle is not None
    topic = extractor.extract_from_bundle(bundle, tenant_id="tenant_alfa", classifier=classifier)
    scorer.score_topic(topic, persist=True)
    opp = aggregator.build_opportunity_from_topics([topic], tenant_id="tenant_alfa", persist=True)
    course = course_gen.generate_from_opportunity(opp.id, tenant_id="tenant_alfa", created_by="setup")
    lesson_id = course.modules[0].lessons[0].id

    quiz = course_gen.generate_quiz(course.id, tenant_id="tenant_alfa", lesson_id=lesson_id, num_questions=4)
    assert len(quiz.questions) >= 1
    for q in quiz.questions:
        opts = q.options
        assert len(opts) == 4
        assert len({o.lower() for o in opts}) == 4
        for opt in opts:
            low = opt.lower()
            assert "sms o chiamata telefonica" not in low
            assert "mail automatica" not in low
            assert not opt.rstrip().endswith(":")


def test_owner_users_counts_lesson_completed_courses_and_quiz_returns_feedback(tmp_path: Path) -> None:
    _rag, client, cid, _lid = _setup_demo_app(tmp_path)

    own_token = client.post(
        "/api/v1/demo/switch-user",
        json={"user_id": "owner_alfa"},
        headers={"X-Tenant-ID": "tenant_alfa"},
    ).json()["token"]
    headers = {"X-Tenant-ID": "tenant_alfa", "X-Demo-Token": own_token}

    # Complete all lessons of the course as Owner without submitting the quiz yet
    course_resp = client.get(f"/api/v1/academy/courses/{cid}", headers=headers)
    assert course_resp.status_code == 200
    course_data = course_resp.json()
    for mod in course_data["modules"]:
        for les in mod["lessons"]:
            comp = client.post(f"/api/v1/academy/courses/{cid}/lessons/{les['id']}/complete", headers=headers)
            assert comp.status_code == 200

    users_resp = client.get("/api/v1/owner/users", headers=headers)
    assert users_resp.status_code == 200
    owner_row = next(u for u in users_resp.json()["items"] if u["user_id"] == "owner_alfa")
    assert owner_row["courses_completed"] >= 1

    detail_resp = client.get("/api/v1/owner/users/owner_alfa", headers=headers)
    assert detail_resp.status_code == 200
    completed_ids = {c["course_id"] for c in detail_resp.json()["learning_performance"]["courses_completed"]}
    assert cid in completed_ids

    # Submit the traditional course quiz and verify per-question feedback includes correct_answer
    quiz = course_data["quizzes"][0]
    answers = {q["id"]: q["options"][0] for q in quiz["questions"]}
    submit_resp = client.post(
        f"/api/v1/academy/courses/{cid}/quizzes/{quiz['id']}/submit",
        json={"user_id": "owner_alfa", "answers": answers},
        headers=headers,
    )
    assert submit_resp.status_code == 200
    body = submit_resp.json()
    assert len(body["question_feedback"]) == len(quiz["questions"])
    assert all(fb["correct_answer"] for fb in body["question_feedback"])



