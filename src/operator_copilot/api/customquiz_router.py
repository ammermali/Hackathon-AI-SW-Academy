"""FastAPI router for the mandatory 'customquiz' entry point (/api/v1/customquiz/*)."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status

from operator_copilot.api.dependencies import assert_user_access, build_caller_context_dependency
from operator_copilot.config.settings import Settings
from operator_copilot.customquiz import CustomQuizEngine
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.customquiz import (
    AnalyzeGapsRequest,
    CustomQuizGenerateRequest,
    CustomQuizResponse,
    CustomQuizResultResponse,
    CustomQuizSubmitRequest,
    LearningGapResponse,
    LearningMetricsResponse,
    UserLearningProfileResponse,
)


def create_customquiz_router(
    *,
    get_rag_engine: Callable[[], RAGEngine],
    settings: Settings,
) -> APIRouter:
    """Create modular APIRouter exposing Adaptive Learning & Custom Quiz endpoints under /api/v1/customquiz."""
    router = APIRouter(prefix="/api/v1/customquiz", tags=["Adaptive Learning & Custom Quiz"])
    get_caller_context = build_caller_context_dependency(settings)

    def _cq(rag: RAGEngine) -> CustomQuizEngine:
        return CustomQuizEngine(rag)

    @router.post(
        "/user/{user_id}/analyze-gaps",
        response_model=list[LearningGapResponse],
        summary="Analizza storico RAG ed errori nei quiz per individuare le lacune dell'utente",
    )
    def analyze_user_gaps(
        user_id: str,
        payload: AnalyzeGapsRequest | None = None,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[LearningGapResponse]:
        assert_user_access(ctx, user_id)
        req = payload or AnalyzeGapsRequest()
        return _cq(rag).analyze_gaps(
            user_id,
            tenant_id=ctx["tenant_id"],
            software=req.software,
            module_name=req.module_name,
        )

    @router.post(
        "/generate",
        response_model=CustomQuizResponse,
        summary="Genera o riutilizza un Custom Quiz personalizzato a 4 opzioni per l'utente",
    )
    def generate_custom_quiz(
        payload: CustomQuizGenerateRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> CustomQuizResponse:
        assert_user_access(ctx, payload.user_id)
        try:
            return _cq(rag).generate(
                user_id=payload.user_id,
                tenant_id=ctx["tenant_id"],
                num_questions=payload.num_questions,
                software=payload.software,
                module_name=payload.module_name,
                focus_topic=payload.focus_topic,
                force_new=payload.force_new,
                run_async=payload.run_async,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @router.get(
        "/user/{user_id}",
        response_model=list[CustomQuizResponse],
        summary="Elenca i Custom Quiz generati per uno specifico utente",
    )
    def list_user_custom_quizzes(
        user_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[CustomQuizResponse]:
        assert_user_access(ctx, user_id)
        return _cq(rag).list_user_quizzes(user_id, tenant_id=ctx["tenant_id"])

    @router.get(
        "/user/{user_id}/learning-profile",
        response_model=UserLearningProfileResponse,
        summary="Restituisce il profilo conoscitivo individuale dell'utente",
    )
    def get_learning_profile(
        user_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> UserLearningProfileResponse:
        assert_user_access(ctx, user_id)
        return _cq(rag).get_learning_profile(user_id, tenant_id=ctx["tenant_id"])

    @router.get(
        "/user/{user_id}/learning-metrics",
        response_model=LearningMetricsResponse,
        summary="Calcola metriche longitudinali di apprendimento (accuracy, improvement, retention, gap resolution)",
    )
    def get_learning_metrics(
        user_id: str,
        topic: str | None = Query(default=None),
        software: str | None = Query(default=None),
        module_name: str | None = Query(default=None),
        date_from: datetime | None = Query(default=None),
        date_to: datetime | None = Query(default=None),
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> LearningMetricsResponse:
        assert_user_access(ctx, user_id)
        return _cq(rag).get_learning_metrics(
            user_id,
            tenant_id=ctx["tenant_id"],
            topic=topic,
            software=software,
            module_name=module_name,
            date_from=date_from,
            date_to=date_to,
        )

    @router.delete(
        "/user/{user_id}/data",
        summary="Cancella profilo conoscitivo, lacune, tentativi, Custom Quiz e storico RAG dell'utente",
    )
    def delete_user_learning_data(
        user_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> dict[str, int | str]:
        assert_user_access(ctx, user_id)
        deleted = _cq(rag).delete_user_data(user_id, tenant_id=ctx["tenant_id"])
        return {"user_id": user_id, **deleted}

    @router.get(
        "/{quiz_id}",
        response_model=CustomQuizResponse,
        summary="Recupera un Custom Quiz (senza esporre le risposte corrette)",
    )
    def get_custom_quiz(
        quiz_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> CustomQuizResponse:
        quiz = _cq(rag).get_quiz(quiz_id, tenant_id=ctx["tenant_id"])
        if quiz is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom Quiz non trovato.")
        assert_user_access(ctx, quiz.user_id)
        return quiz

    @router.post(
        "/{quiz_id}/submit",
        response_model=CustomQuizResultResponse,
        summary="Registra le risposte del Custom Quiz, aggiorna lacune/profilo e restituisce feedback didattico",
    )
    def submit_custom_quiz(
        quiz_id: str,
        payload: CustomQuizSubmitRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> CustomQuizResultResponse:
        assert_user_access(ctx, payload.user_id)
        try:
            return _cq(rag).submit(
                quiz_id=quiz_id,
                user_id=payload.user_id,
                answers=payload.answers,
                tenant_id=ctx["tenant_id"],
                duration_seconds=payload.duration_seconds,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @router.get(
        "/{quiz_id}/results",
        response_model=CustomQuizResultResponse,
        summary="Restituisce l'esito dettagliato e il feedback didattico di un Custom Quiz completato",
    )
    def get_custom_quiz_results(
        quiz_id: str,
        user_id: str | None = Query(default=None),
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> CustomQuizResultResponse:
        target_uid = user_id or ctx["user_id"]
        assert_user_access(ctx, target_uid)
        try:
            return _cq(rag).get_results(quiz_id, user_id=target_uid, tenant_id=ctx["tenant_id"])
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return router
