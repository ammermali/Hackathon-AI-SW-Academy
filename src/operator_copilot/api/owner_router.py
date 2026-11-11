"""FastAPI router for Milestone 4 — Owner Learning Dashboard & Analytics (/api/v1/owner/* + /owner)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from operator_copilot.api.dependencies import build_owner_context_dependency
from operator_copilot.config.settings import Settings
from operator_copilot.owner_dashboard.cache import OwnerMetricsCache
from operator_copilot.owner_dashboard.service import OwnerDashboardService
from operator_copilot.owner_dashboard.ui import render_owner_dashboard_html
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.academy import _clean_swagger_opt_str
from operator_copilot.schemas.owner import (
    OrganizationUserResponse,
    OrganizationUserUpsertRequest,
    OwnerAuditLogItem,
    OwnerCustomQuizAnalyticsResponse,
    OwnerDashboardOverviewResponse,
    OwnerInsightsResponse,
    OwnerTopicDrilldownResponse,
    OwnerTopicReviewItem,
    OwnerUserDetailResponse,
    OwnerUserGapDetailItem,
    OwnerUsersPageResponse,
)


def create_owner_router(
    *,
    get_rag_engine: Callable[[], RAGEngine],
    settings: Settings,
) -> APIRouter:
    """Create modular APIRouter for Owner Dashboard APIs and UI shell."""
    router = APIRouter(tags=["Owner Learning Dashboard"])
    get_owner_context = build_owner_context_dependency(settings)
    shared_cache = OwnerMetricsCache(settings.owner_dashboard_cache_ttl_seconds)

    def _svc(rag: RAGEngine) -> OwnerDashboardService:
        return OwnerDashboardService(
            settings=rag.settings,
            db_manager=rag.db,
            generator=rag.generator,
            cache=shared_cache,
        )

    @router.get("/owner", response_class=HTMLResponse, include_in_schema=False)
    def owner_dashboard_ui() -> HTMLResponse:
        """Serve Owner Dashboard UI shell (data fetched strictly via authenticated /api/v1/owner/* APIs)."""
        return HTMLResponse(content=render_owner_dashboard_html())

    @router.get(
        "/api/v1/owner/overview",
        response_model=OwnerDashboardOverviewResponse,
        summary="Metriche aggregate della Dashboard Generale riservata agli Owner",
    )
    def get_owner_overview(
        date_from: datetime | None = Query(default=None),
        date_to: datetime | None = Query(default=None),
        software: str | None = Query(default=None),
        module_name: str | None = Query(default=None),
        amministrazione: str | None = Query(default=None),
        refresh: bool = Query(default=False),
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> OwnerDashboardOverviewResponse:
        svc = _svc(rag)
        sw = _clean_swagger_opt_str(software)
        mod = _clean_swagger_opt_str(module_name)
        adm = _clean_swagger_opt_str(amministrazione)
        svc.record_audit(
            tenant_id=ctx["tenant_id"],
            owner_id=ctx["user_id"],
            owner_role=ctx["role"],
            action="READ_OVERVIEW",
            resource="/api/v1/owner/overview",
            filters={"software": sw, "module_name": mod, "amministrazione": adm},
        )
        return svc.get_overview(
            tenant_id=ctx["tenant_id"],
            allowed_administrations=ctx["allowed_administrations"],
            date_from=date_from,
            date_to=date_to,
            software=sw,
            module_name=mod,
            amministrazione=adm,
            bypass_cache=refresh,
        )

    @router.get(
        "/api/v1/owner/users",
        response_model=OwnerUsersPageResponse,
        summary="Elenco utenti filtrabile, ordinabile e paginato (User Learning Overview)",
    )
    def list_owner_users(
        search: str | None = Query(default=None),
        amministrazione: str | None = Query(default=None),
        software: str | None = Query(default=None),
        learning_status: str | None = Query(default=None),
        sort_by: Literal[
            "display_name", "quiz_success_rate", "open_gaps_count", "last_activity_at", "courses_completed"
        ] = Query(default="open_gaps_count"),
        sort_dir: Literal["asc", "desc"] = Query(default="desc"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=200),
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> OwnerUsersPageResponse:
        svc = _svc(rag)
        srch = _clean_swagger_opt_str(search)
        adm = _clean_swagger_opt_str(amministrazione)
        sw = _clean_swagger_opt_str(software)
        st = _clean_swagger_opt_str(learning_status)
        svc.record_audit(
            tenant_id=ctx["tenant_id"],
            owner_id=ctx["user_id"],
            owner_role=ctx["role"],
            action="LIST_USERS",
            resource="/api/v1/owner/users",
            filters={"search": srch, "amministrazione": adm, "software": sw, "learning_status": st},
        )
        return svc.list_users(
            tenant_id=ctx["tenant_id"],
            allowed_administrations=ctx["allowed_administrations"],
            search=srch,
            amministrazione=adm,
            software=sw,
            learning_status=st,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )

    @router.post(
        "/api/v1/owner/users",
        response_model=OrganizationUserResponse,
        summary="Censisce o aggiorna nome e amministrazione di un utente del tenant (Owner)",
    )
    def upsert_owner_user(
        payload: OrganizationUserUpsertRequest,
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> OrganizationUserResponse:
        if ctx["allowed_administrations"] and payload.amministrazione.lower() not in {
            a.lower() for a in ctx["allowed_administrations"]
        }:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Amministrazione esterna al perimetro autorizzativo dell'Owner.",
            )
        svc = _svc(rag)
        svc.record_audit(
            tenant_id=ctx["tenant_id"],
            owner_id=ctx["user_id"],
            owner_role=ctx["role"],
            action="UPSERT_USER",
            resource="/api/v1/owner/users",
            target_user_id=payload.user_id,
            filters={"amministrazione": payload.amministrazione},
        )
        return svc.upsert_organization_user(
            tenant_id=ctx["tenant_id"],
            user_id=payload.user_id,
            display_name=payload.display_name,
            amministrazione=payload.amministrazione,
            role=payload.role,
        )

    @router.get(
        "/api/v1/owner/users/{user_id}",
        response_model=OwnerUserDetailResponse,
        summary="Scheda di dettaglio completa del profilo formativo di un utente (Owner)",
    )
    def get_owner_user_detail(
        user_id: str,
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> OwnerUserDetailResponse:
        svc = _svc(rag)
        svc.record_audit(
            tenant_id=ctx["tenant_id"],
            owner_id=ctx["user_id"],
            owner_role=ctx["role"],
            action="READ_USER_DETAIL",
            resource=f"/api/v1/owner/users/{user_id}",
            target_user_id=user_id,
        )
        try:
            return svc.get_user_detail(
                tenant_id=ctx["tenant_id"],
                user_id=user_id,
                allowed_administrations=ctx["allowed_administrations"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @router.get(
        "/api/v1/owner/users/{user_id}/gaps",
        response_model=list[OwnerUserGapDetailItem],
        summary="Recupera le lacune formative dettagliate per uno specifico utente (Owner)",
    )
    def get_owner_user_gaps(
        user_id: str,
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[OwnerUserGapDetailItem]:
        svc = _svc(rag)
        svc.record_audit(
            tenant_id=ctx["tenant_id"],
            owner_id=ctx["user_id"],
            owner_role=ctx["role"],
            action="READ_USER_GAPS",
            resource=f"/api/v1/owner/users/{user_id}/gaps",
            target_user_id=user_id,
        )
        try:
            return svc.get_user_detail(
                tenant_id=ctx["tenant_id"],
                user_id=user_id,
                allowed_administrations=ctx["allowed_administrations"],
            ).knowledge_gaps
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @router.get(
        "/api/v1/owner/topics-to-review",
        response_model=list[OwnerTopicReviewItem],
        summary="Elenco aggregato degli argomenti critici da ripassare (CRITICAL/HIGH/MEDIUM/LOW)",
    )
    def list_owner_topics_to_review(
        software: str | None = Query(default=None),
        module_name: str | None = Query(default=None),
        amministrazione: str | None = Query(default=None),
        criticality: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] | None = Query(default=None),
        date_from: datetime | None = Query(default=None),
        date_to: datetime | None = Query(default=None),
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[OwnerTopicReviewItem]:
        svc = _svc(rag)
        sw = _clean_swagger_opt_str(software)
        mod = _clean_swagger_opt_str(module_name)
        adm = _clean_swagger_opt_str(amministrazione)
        svc.record_audit(
            tenant_id=ctx["tenant_id"],
            owner_id=ctx["user_id"],
            owner_role=ctx["role"],
            action="LIST_TOPICS_TO_REVIEW",
            resource="/api/v1/owner/topics-to-review",
            filters={"software": sw, "module_name": mod, "amministrazione": adm, "criticality": criticality},
        )
        return svc.list_topics_to_review(
            tenant_id=ctx["tenant_id"],
            allowed_administrations=ctx["allowed_administrations"],
            software=sw,
            module_name=mod,
            amministrazione=adm,
            criticality=criticality,
            date_from=date_from,
            date_to=date_to,
        )

    @router.get(
        "/api/v1/owner/topics-to-review/{topic:path}/users",
        response_model=OwnerTopicDrilldownResponse,
        summary="Drill-down degli utenti che presentano lacuna sullo specifico topic critico",
    )
    def drilldown_topic_users(
        topic: str,
        amministrazione: str | None = Query(default=None),
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> OwnerTopicDrilldownResponse:
        svc = _svc(rag)
        adm = _clean_swagger_opt_str(amministrazione)
        svc.record_audit(
            tenant_id=ctx["tenant_id"],
            owner_id=ctx["user_id"],
            owner_role=ctx["role"],
            action="DRILLDOWN_TOPIC",
            resource=f"/api/v1/owner/topics-to-review/{topic}/users",
            filters={"topic": topic, "amministrazione": adm},
        )
        try:
            return svc.get_topic_users_drilldown(
                tenant_id=ctx["tenant_id"],
                topic=topic,
                allowed_administrations=ctx["allowed_administrations"],
                amministrazione=adm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @router.get(
        "/api/v1/owner/customquiz-analytics",
        response_model=OwnerCustomQuizAnalyticsResponse,
        summary="Analisi di efficacia dei Custom Quiz personalizzati e risoluzione lacune",
    )
    def get_owner_customquiz_analytics(
        date_from: datetime | None = Query(default=None),
        date_to: datetime | None = Query(default=None),
        software: str | None = Query(default=None),
        module_name: str | None = Query(default=None),
        amministrazione: str | None = Query(default=None),
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> OwnerCustomQuizAnalyticsResponse:
        svc = _svc(rag)
        sw = _clean_swagger_opt_str(software)
        mod = _clean_swagger_opt_str(module_name)
        adm = _clean_swagger_opt_str(amministrazione)
        svc.record_audit(
            tenant_id=ctx["tenant_id"],
            owner_id=ctx["user_id"],
            owner_role=ctx["role"],
            action="READ_CUSTOMQUIZ_ANALYTICS",
            resource="/api/v1/owner/customquiz-analytics",
            filters={"software": sw, "module_name": mod, "amministrazione": adm},
        )
        return svc.get_custom_quiz_analytics(
            tenant_id=ctx["tenant_id"],
            allowed_administrations=ctx["allowed_administrations"],
            date_from=date_from,
            date_to=date_to,
            software=sw,
            module_name=mod,
            amministrazione=adm,
        )

    @router.get(
        "/api/v1/owner/insights",
        response_model=OwnerInsightsResponse,
        summary="Suggerimenti formativi basati su metriche effettive (con eventuale sintesi Qwen verificabile)",
    )
    def get_owner_insights(
        software: str | None = Query(default=None),
        module_name: str | None = Query(default=None),
        amministrazione: str | None = Query(default=None),
        use_llm_synthesis: bool = Query(default=False),
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> OwnerInsightsResponse:
        svc = _svc(rag)
        sw = _clean_swagger_opt_str(software)
        mod = _clean_swagger_opt_str(module_name)
        adm = _clean_swagger_opt_str(amministrazione)
        svc.record_audit(
            tenant_id=ctx["tenant_id"],
            owner_id=ctx["user_id"],
            owner_role=ctx["role"],
            action="READ_INSIGHTS",
            resource="/api/v1/owner/insights",
            filters={"software": sw, "module_name": mod, "amministrazione": adm, "use_llm_synthesis": use_llm_synthesis},
        )
        return svc.get_insights(
            tenant_id=ctx["tenant_id"],
            allowed_administrations=ctx["allowed_administrations"],
            software=sw,
            module_name=mod,
            amministrazione=adm,
            use_llm_synthesis=use_llm_synthesis,
        )

    @router.get(
        "/api/v1/owner/audit-logs",
        response_model=list[OwnerAuditLogItem],
        summary="Storico audit delle consultazioni e operazioni effettuate dagli Owner",
    )
    def get_owner_audit_logs(
        limit: int = Query(default=100, ge=1, le=500),
        ctx: dict[str, Any] = Depends(get_owner_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[OwnerAuditLogItem]:
        svc = _svc(rag)
        return svc.list_audit_logs(tenant_id=ctx["tenant_id"], limit=limit)

    return router
