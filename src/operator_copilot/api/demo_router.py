"""Controlled Demo Mode endpoints for User Switching in non-production environments."""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from operator_copilot.api.dependencies import create_demo_token
from operator_copilot.config.settings import Settings
from operator_copilot.db.models import (
    CourseQuizAttempt,
    CustomQuizAttempt,
    LessonCompletion,
    OrganizationUser,
    QueryHistory,
    UserKnowledgeProfile,
)
from operator_copilot.retrieval.rag_engine import RAGEngine


class DemoUserItem(BaseModel):
    user_id: str
    display_name: str
    amministrazione: str
    role: str
    softwares_used: list[str] = Field(default_factory=list)
    has_activity: bool = False


class DemoStatusResponse(BaseModel):
    demo_mode_enabled: bool
    app_env: str


class DemoSwitchRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)


class DemoSwitchResponse(BaseModel):
    token: str
    user: DemoUserItem
    tenant_id: str
    is_demo: bool = True
    expires_at: int


def _collect_tenant_demo_users(rag: RAGEngine, tenant_id: str) -> dict[str, DemoUserItem]:
    """Gather real persisted users within the caller's tenant_id only."""
    users: dict[str, DemoUserItem] = {}

    with rag.db.session() as db:
        org_rows = (
            db.query(OrganizationUser)
            .filter(OrganizationUser.tenant_id == tenant_id)
            .order_by(OrganizationUser.display_name.asc())
            .all()
        )
        for row in org_rows:
            users[row.user_id] = DemoUserItem(
                user_id=row.user_id,
                display_name=row.display_name,
                amministrazione=row.amministrazione,
                role=row.role or "operatore",
                softwares_used=[],
                has_activity=False,
            )

        prof_rows = (
            db.query(UserKnowledgeProfile.user_id, UserKnowledgeProfile.software)
            .filter(UserKnowledgeProfile.tenant_id == tenant_id)
            .all()
        )
        for uid, software in prof_rows:
            if uid not in users:
                users[uid] = DemoUserItem(
                    user_id=uid,
                    display_name=uid,
                    amministrazione="Predefinita",
                    role="operatore",
                    softwares_used=[],
                    has_activity=True,
                )
            item = users[uid]
            item.has_activity = True
            if software and software not in item.softwares_used:
                item.softwares_used.append(software)

        for model in (CourseQuizAttempt, CustomQuizAttempt, LessonCompletion):
            uid_rows = db.query(model.user_id).filter(model.tenant_id == tenant_id).distinct().all()
            for (uid,) in uid_rows:
                if not uid or uid == "anonymous":
                    continue
                if uid not in users:
                    users[uid] = DemoUserItem(
                        user_id=uid,
                        display_name=uid,
                        amministrazione="Predefinita",
                        role="operatore",
                        softwares_used=[],
                        has_activity=True,
                    )
                else:
                    users[uid].has_activity = True

        # Milestone 1 QueryHistory does not carry tenant_id; expose only on default tenant
        if tenant_id == "default":
            qh_rows = (
                db.query(QueryHistory.user_id)
                .filter(QueryHistory.user_id != "anonymous")
                .distinct()
                .all()
            )
            for (uid,) in qh_rows:
                if not uid:
                    continue
                if uid not in users:
                    users[uid] = DemoUserItem(
                        user_id=uid,
                        display_name=uid,
                        amministrazione="Predefinita",
                        role="operatore",
                        softwares_used=[],
                        has_activity=True,
                    )
                else:
                    users[uid].has_activity = True

    return users


def create_demo_router(
    *,
    get_rag_engine: Callable[[], RAGEngine],
    settings: Settings,
) -> APIRouter:
    """Create APIRouter for strictly non-production Demo Mode user switching."""
    router = APIRouter(prefix="/api/v1/demo", tags=["Demo Mode"])

    def _require_demo_active() -> None:
        if not settings.is_demo_mode_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La modalità demo è disabilitata in questo ambiente.",
            )

    @router.get("/status", response_model=DemoStatusResponse)
    def get_demo_status() -> DemoStatusResponse:
        return DemoStatusResponse(
            demo_mode_enabled=settings.is_demo_mode_active,
            app_env=settings.app_env,
        )

    @router.get("/users", response_model=list[DemoUserItem])
    def list_demo_users(
        x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[DemoUserItem]:
        _require_demo_active()
        tenant_id = x_tenant_id.strip() or "default"
        users = _collect_tenant_demo_users(rag, tenant_id)
        return sorted(users.values(), key=lambda u: (0 if u.role in {"owner", "learning_manager"} else 1, u.display_name.lower()))

    @router.post("/switch-user", response_model=DemoSwitchResponse)
    def switch_demo_user(
        payload: DemoSwitchRequest,
        x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> DemoSwitchResponse:
        _require_demo_active()
        tenant_id = x_tenant_id.strip() or "default"
        target_uid = payload.user_id.strip()
        users = _collect_tenant_demo_users(rag, tenant_id)
        target = users.get(target_uid)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Utente '{target_uid}' non trovato nel tenant '{tenant_id}'.",
            )

        token, expires_at = create_demo_token(
            settings,
            tenant_id=tenant_id,
            user_id=target.user_id,
            role=target.role,
            amministrazione=target.amministrazione,
        )
        return DemoSwitchResponse(
            token=token,
            user=target,
            tenant_id=tenant_id,
            is_demo=True,
            expires_at=expires_at,
        )

    return router
