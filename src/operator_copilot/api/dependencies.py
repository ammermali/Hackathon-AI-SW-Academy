"""Shared FastAPI caller-context, anti-spoofing, and user-isolation dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Callable

from fastapi import Header, HTTPException, status

from operator_copilot.config.settings import Settings


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def create_demo_token(
    settings: Settings,
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    amministrazione: str = "Predefinita",
    allowed_administrations: list[str] | None = None,
    ttl_seconds: int = 86400,
) -> tuple[str, int]:
    """Create a server-signed HMAC-SHA256 demo session token (non-production only)."""
    if not settings.is_demo_mode_active:
        raise RuntimeError("Modalità demo non attiva.")
    expires_at = int(time.time()) + ttl_seconds
    payload = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "role": role.strip().lower() or "operatore",
        "amministrazione": amministrazione,
        "allowed_administrations": allowed_administrations or [],
        "demo": True,
        "exp": expires_at,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    secret = settings.demo_session_secret.get_secret_value().encode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(sig)}", expires_at


def verify_demo_token(settings: Settings, token: str, *, expected_tenant: str) -> dict[str, Any]:
    """Verify server-signed demo token integrity, expiration, and tenant isolation."""
    if not settings.is_demo_mode_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Modalità demo disabilitata in questo ambiente.",
        )
    parts = token.strip().split(".")
    if len(parts) != 2:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token demo non valido.")
    payload_b64, sig_b64 = parts
    secret = settings.demo_session_secret.get_secret_value().encode("utf-8")
    expected_sig = _b64url_encode(hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest())
    if not secrets.compare_digest(sig_b64, expected_sig):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Firma del token demo non valida.")
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token demo corrotto.") from exc
    if not isinstance(payload, dict) or not payload.get("demo"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token demo non valido.")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessione demo scaduta.")
    token_tenant = str(payload.get("tenant_id") or "default").strip() or "default"
    if token_tenant != expected_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token demo non valido per il tenant selezionato.",
        )
    return payload


def build_caller_context_dependency(settings: Settings) -> Callable[..., dict[str, str]]:
    """Build reusable dependency extracting X-Tenant-ID, X-User-Role, and X-User-ID with anti-spoofing."""

    def get_caller_context(
        x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
        x_user_role: str = Header(default="operatore", alias="X-User-Role"),
        x_user_id: str = Header(default="anonymous", alias="X-User-ID"),
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
        x_demo_token: str | None = Header(default=None, alias="X-Demo-Token"),
    ) -> dict[str, str]:
        tenant_id = x_tenant_id.strip() or "default"
        if x_demo_token:
            claims = verify_demo_token(settings, x_demo_token, expected_tenant=tenant_id)
            return {
                "tenant_id": tenant_id,
                "role": str(claims.get("role") or "operatore"),
                "user_id": str(claims.get("user_id") or "anonymous"),
                "is_demo_verified": "true",
            }

        role = x_user_role.strip().lower() or "operatore"
        if role == "admin":
            expected = settings.admin_api_key.get_secret_value()
            if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Ruolo 'admin' richiede un header X-Admin-Key valido.",
                )
        return {
            "tenant_id": tenant_id,
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


def build_owner_context_dependency(settings: Settings) -> Callable[..., dict[str, Any]]:
    """Enforce exclusive Owner role access + X-Owner-Key (or verified Demo Token) anti-spoofing + tenant/admin scope."""

    def get_owner_context(
        x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
        x_user_role: str = Header(default="operatore", alias="X-User-Role"),
        x_user_id: str = Header(default="anonymous", alias="X-User-ID"),
        x_owner_key: str | None = Header(default=None, alias="X-Owner-Key"),
        x_owner_scope: str | None = Header(default=None, alias="X-Owner-Scope"),
        x_demo_token: str | None = Header(default=None, alias="X-Demo-Token"),
    ) -> dict[str, Any]:
        tenant_id = x_tenant_id.strip() or "default"
        if x_demo_token and not x_owner_key:
            claims = verify_demo_token(settings, x_demo_token, expected_tenant=tenant_id)
            demo_role = str(claims.get("role") or "operatore").strip().lower()
            demo_uid = str(claims.get("user_id") or "anonymous").strip()
            if demo_role != "owner" or demo_uid == "anonymous":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Accesso riservato esclusivamente ad utenti autenticati con ruolo 'owner'.",
                )
            return {
                "tenant_id": tenant_id,
                "role": demo_role,
                "user_id": demo_uid,
                "allowed_administrations": list(claims.get("allowed_administrations") or []),
            }

        role = x_user_role.strip().lower() or "operatore"
        owner_id = x_user_id.strip() or "anonymous"
        if role != "owner" or owner_id == "anonymous":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accesso riservato esclusivamente ad utenti autenticati con ruolo 'owner'.",
            )
        expected = settings.owner_api_key.get_secret_value()
        if not x_owner_key or not secrets.compare_digest(x_owner_key, expected):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ruolo 'owner' richiede un header X-Owner-Key valido.",
            )
        allowed_admins = [
            item.strip()
            for item in (x_owner_scope or "").split(",")
            if item.strip()
        ]
        return {
            "tenant_id": tenant_id,
            "role": role,
            "user_id": owner_id,
            "allowed_administrations": allowed_admins,
        }

    return get_owner_context


def build_knowledge_manager_context_dependency(settings: Settings) -> Callable[..., dict[str, str]]:
    """Enforce Knowledge Manager role access via signed Demo Token or X-Admin-Key."""

    def get_knowledge_manager_context(
        x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
        x_demo_token: str | None = Header(default=None, alias="X-Demo-Token"),
        x_user_id: str = Header(default="anonymous", alias="X-User-ID"),
    ) -> dict[str, str]:
        tenant_id = x_tenant_id.strip() or "default"
        if x_admin_key:
            expected = settings.admin_api_key.get_secret_value()
            if secrets.compare_digest(x_admin_key, expected):
                return {
                    "tenant_id": tenant_id,
                    "role": "admin",
                    "user_id": x_user_id.strip() or "admin",
                }
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Header X-Admin-Key non valido.",
            )

        if x_demo_token:
            claims = verify_demo_token(settings, x_demo_token, expected_tenant=tenant_id)
            demo_role = str(claims.get("role") or "operatore").strip().lower()
            demo_uid = str(claims.get("user_id") or "anonymous").strip()
            if demo_role not in {"knowledge_manager", "admin"} or demo_uid == "anonymous":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Accesso riservato al ruolo 'knowledge_manager'.",
                )
            return {
                "tenant_id": tenant_id,
                "role": demo_role,
                "user_id": demo_uid,
            }

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accesso riservato al ruolo 'knowledge_manager' autenticato.",
        )

    return get_knowledge_manager_context
