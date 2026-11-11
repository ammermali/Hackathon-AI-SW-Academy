"""Shared FastAPI caller-context, anti-spoofing, and user-isolation dependencies."""

from __future__ import annotations

import secrets
from typing import Callable

from fastapi import Header, HTTPException, status

from operator_copilot.config.settings import Settings


def build_caller_context_dependency(settings: Settings) -> Callable[..., dict[str, str]]:
    """Build reusable dependency extracting X-Tenant-ID, X-User-Role, and X-User-ID with admin anti-spoofing."""

    def get_caller_context(
        x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
        x_user_role: str = Header(default="operatore", alias="X-User-Role"),
        x_user_id: str = Header(default="anonymous", alias="X-User-ID"),
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    ) -> dict[str, str]:
        role = x_user_role.strip().lower() or "operatore"
        if role == "admin":
            expected = settings.admin_api_key.get_secret_value()
            if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Ruolo 'admin' richiede un header X-Admin-Key valido.",
                )
        return {
            "tenant_id": x_tenant_id.strip() or "default",
            "role": role,
            "user_id": x_user_id.strip() or "anonymous",
        }

    return get_caller_context


def assert_user_access(ctx: dict[str, str], target_user_id: str) -> None:
    """Enforce strict user data isolation unless caller is authenticated admin."""
    if ctx["role"] == "admin":
        return
    if ctx["user_id"] == "anonymous" or ctx["user_id"] != target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accesso negato: non puoi accedere o modificare dati di apprendimento di un altro utente.",
        )
