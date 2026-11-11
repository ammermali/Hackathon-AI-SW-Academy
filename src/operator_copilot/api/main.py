"""FastAPI application exposing Operator Copilot Milestone 1 RAG endpoints."""

from __future__ import annotations

import secrets
from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status

from operator_copilot import __version__
from operator_copilot.api.academy_router import create_academy_router
from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.query import FeedbackRequest, IngestRequest, RAGQueryRequest
from operator_copilot.schemas.response import (
    DocumentInfoResponse,
    FeedbackResponse,
    HistoryResponse,
    IngestResponse,
    MetricsResponse,
    RAGResponse,
)


@lru_cache
def _default_engine() -> RAGEngine:
    return RAGEngine(settings=get_settings())


def create_app(engine: RAGEngine | None = None, settings: Settings | None = None) -> FastAPI:
    """Application factory enabling isolated test injection."""
    cfg = settings or get_settings()

    app = FastAPI(
        title="Operator Copilot — RAG Engine API",
        version=__version__,
        description=(
            "API REST per il motore RAG aziendale (Milestone 1): interrogazione in linguaggio naturale, "
            "citazioni dalle fonti reali, smart caching, storico ricerche e metriche operative."
        ),
    )

    def get_rag_engine() -> RAGEngine:
        return engine or _default_engine()

    def verify_admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
        expected = cfg.admin_api_key.get_secret_value()
        if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso non autorizzato all'operazione amministrativa di ingestion.",
            )

    @app.get("/health", tags=["System"])
    def health_check(rag: RAGEngine = Depends(get_rag_engine)) -> dict[str, str]:
        """Verify service health and active corpus version."""
        return {
            "status": "ok",
            "version": __version__,
            "corpus_version": rag.db.get_corpus_version(),
        }

    @app.post(
        "/api/v1/rag/query",
        response_model=RAGResponse,
        tags=["RAG"],
        summary="Interroga la knowledge base aziendale tramite RAG",
    )
    def query_rag(
        payload: RAGQueryRequest,
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> RAGResponse:
        """Esegue cache lookup, retrieval ibrido, generazione ancorata alle fonti e salvataggio storico."""
        return rag.answer_query(payload)

    @app.get(
        "/api/v1/rag/history/{user_id}",
        response_model=HistoryResponse,
        tags=["History"],
        summary="Recupera le ultime N ricerche di un utente raggruppate per argomento",
    )
    def get_user_history(
        user_id: str,
        limit: int = Query(default=20, ge=1, le=200),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> HistoryResponse:
        return rag.history.get_user_history(user_id=user_id, limit=limit)

    @app.delete(
        "/api/v1/rag/history/{user_id}",
        tags=["History"],
        summary="Cancella lo storico ricerche di un utente (minimizzazione/privacy)",
    )
    def delete_user_history(
        user_id: str,
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> dict[str, int | str]:
        deleted = rag.history.delete_user_history(user_id=user_id)
        return {"user_id": user_id, "deleted_records": deleted}

    @app.get(
        "/api/v1/rag/metrics",
        response_model=MetricsResponse,
        tags=["Analytics"],
        summary="Restituisce le metriche complessive del motore RAG",
    )
    def get_metrics(rag: RAGEngine = Depends(get_rag_engine)) -> MetricsResponse:
        return rag.metrics.collect_metrics()

    @app.get(
        "/api/v1/rag/documents",
        response_model=list[DocumentInfoResponse],
        tags=["Knowledge Base"],
        summary="Elenca i documenti tracciati nella knowledge base",
    )
    def list_documents(
        doc_status: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=200, ge=1, le=2000),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[DocumentInfoResponse]:
        return rag.metrics.list_documents(status=doc_status, limit=limit)

    @app.post(
        "/api/v1/rag/feedback",
        response_model=FeedbackResponse,
        tags=["History"],
        summary="Registra il feedback dell'operatore su una risposta RAG",
    )
    def submit_feedback(
        payload: FeedbackRequest,
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> FeedbackResponse:
        try:
            return rag.history.add_feedback(
                query_history_id=payload.query_history_id,
                user_id=payload.user_id,
                rating=payload.rating,
                comment=payload.comment,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post(
        "/api/v1/rag/ingest",
        response_model=IngestResponse,
        tags=["Knowledge Base"],
        summary="Avvia ingestion controllata dei documenti (richiede header X-Admin-Key)",
        dependencies=[Depends(verify_admin_key)],
    )
    def trigger_ingest(
        payload: IngestRequest,
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> IngestResponse:
        return rag.indexer.run_ingestion(rebuild=payload.rebuild, max_files=payload.max_files)

    app.include_router(
        create_academy_router(
            get_rag_engine=get_rag_engine,
            verify_admin_key=verify_admin_key,
            settings=cfg,
        )
    )

    return app


app = create_app()
