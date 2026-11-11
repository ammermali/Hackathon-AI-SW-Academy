"""Integration tests for FastAPI endpoints using TestClient."""

from __future__ import annotations

from fastapi.testclient import TestClient

from operator_copilot.api.main import create_app
from operator_copilot.config.settings import Settings
from operator_copilot.retrieval.rag_engine import RAGEngine


def test_api_endpoints_end_to_end(indexed_engine: RAGEngine, test_settings: Settings) -> None:
    app = create_app(engine=indexed_engine, settings=test_settings)
    client = TestClient(app)

    # 1. Health
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    # 2. Query RAG (miss -> hit)
    q_resp1 = client.post(
        "/api/v1/rag/query",
        json={
            "query": "Come si rimuove un verbale da un ruolo con F7?",
            "user_id": "demo_user",
            "session_id": "session_001",
        },
    )
    assert q_resp1.status_code == 200
    data1 = q_resp1.json()
    assert data1["cached"] is False
    assert data1["needs_escalation"] is False
    assert len(data1["sources"]) >= 1
    hist_id = data1["history_id"]
    assert hist_id is not None

    q_resp2 = client.post(
        "/api/v1/rag/query",
        json={
            "query": "Come si rimuove un verbale da un ruolo con F7?",
            "user_id": "demo_user",
            "session_id": "session_001",
        },
    )
    assert q_resp2.status_code == 200
    assert q_resp2.json()["cached"] is True

    # 3. History
    hist_resp = client.get("/api/v1/rag/history/demo_user?limit=10")
    assert hist_resp.status_code == 200
    assert hist_resp.json()["total_returned"] == 2

    # 4. Feedback (valid + 404 on missing id)
    fb_resp = client.post(
        "/api/v1/rag/feedback",
        json={"query_history_id": hist_id, "user_id": "demo_user", "rating": 5, "comment": "Perfetto"},
    )
    assert fb_resp.status_code == 200
    assert fb_resp.json()["rating"] == 5

    fb_missing = client.post(
        "/api/v1/rag/feedback",
        json={"query_history_id": 999999, "user_id": "demo_user", "rating": 3},
    )
    assert fb_missing.status_code == 404

    # 5. Documents & Metrics
    docs_resp = client.get("/api/v1/rag/documents?status=indexed")
    assert docs_resp.status_code == 200
    assert len(docs_resp.json()) == 3

    metrics_resp = client.get("/api/v1/rag/metrics")
    assert metrics_resp.status_code == 200
    m = metrics_resp.json()
    assert m["performance"]["total_queries"] == 2
    assert m["performance"]["cache_hit_rate"] == 0.5

    # 6. Admin-protected /ingest endpoint
    unauth_ingest = client.post("/api/v1/rag/ingest", json={"rebuild": False})
    assert unauth_ingest.status_code == 403

    auth_ingest = client.post(
        "/api/v1/rag/ingest",
        headers={"X-Admin-Key": "test-secret-admin"},
        json={"rebuild": False},
    )
    assert auth_ingest.status_code == 200
    assert auth_ingest.json()["files_skipped_unchanged"] == 3


def test_api_ignores_swagger_placeholder_filters(indexed_engine: RAGEngine, test_settings: Settings) -> None:
    app = create_app(engine=indexed_engine, settings=test_settings)
    client = TestClient(app)

    resp = client.post(
        "/api/v1/rag/query",
        json={
            "query": "Come si rimuove un verbale da un ruolo con F7?",
            "filters": {"additionalProp1": {}},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["needs_escalation"] is False
    assert len(body["sources"]) >= 1
