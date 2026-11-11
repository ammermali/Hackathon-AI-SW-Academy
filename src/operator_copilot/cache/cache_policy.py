"""Cache normalization, hashing, TTL, version invalidation, and user isolation policies."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any


class CachePolicy:
    """Defines query normalization, key hashing, TTL expiration, and user isolation rules."""

    PUBLIC_OWNER_SENTINEL = "__public__"

    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_entries: int = 500,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

    @staticmethod
    def normalize_query(query: str) -> str:
        """Trim, lowercase, and collapse internal whitespace."""
        return re.sub(r"\s+", " ", query.strip().lower())

    @classmethod
    def compute_query_hash(
        cls,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> str:
        """Compute deterministic SHA-256 hash of normalized query and retrieval constraints."""
        norm = cls.normalize_query(query)
        clean_filters = {k: v for k, v in (filters or {}).items() if v is not None and v != ""}
        payload = json.dumps(
            {
                "q": norm,
                "filters": clean_filters,
                "top_k": top_k,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def resolve_owner(cls, user_scope: str, user_id: str) -> str:
        """Isolate private queries to user_id while allowing shared public docs cache."""
        if user_scope == "private":
            return user_id
        return cls.PUBLIC_OWNER_SENTINEL

    def compute_expiry(self, now: datetime | None = None) -> datetime:
        """Compute expiration timestamp from TTL."""
        base = now or datetime.now(timezone.utc)
        return base + timedelta(seconds=self.ttl_seconds)

    @staticmethod
    def is_expired(expires_at: datetime, now: datetime | None = None) -> bool:
        """Check whether an entry has expired (handles naive SQLite datetimes safely)."""
        current = now or datetime.now(timezone.utc)
        exp = expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=timezone.utc)
        return exp <= current

    @staticmethod
    def should_cache(needs_escalation: bool, sources_count: int, answer: str) -> bool:
        """Refuse to cache unsupported, empty, or abstention responses."""
        if needs_escalation:
            return False
        if sources_count <= 0:
            return False
        if not answer.strip():
            return False
        return True
