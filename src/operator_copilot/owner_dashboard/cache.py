"""Thread-safe TTL cache for aggregated Owner Dashboard metrics."""

from __future__ import annotations

import threading
import time
from typing import Any


class OwnerMetricsCache:
    """In-memory per-tenant TTL cache avoiding repeated full scans on dashboard refreshes."""

    def __init__(self, ttl_seconds: int = 30) -> None:
        self.ttl_seconds = max(0, ttl_seconds)
        self._store: dict[tuple[str, str, tuple[tuple[str, Any], ...]], tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, tenant_id: str, section: str, params: dict[str, Any]) -> Any | None:
        if self.ttl_seconds <= 0:
            return None
        key = (tenant_id, section, tuple(sorted(params.items())))
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, payload = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return payload

    def set(self, tenant_id: str, section: str, params: dict[str, Any], value: Any) -> None:
        if self.ttl_seconds <= 0:
            return
        key = (tenant_id, section, tuple(sorted(params.items())))
        with self._lock:
            self._store[key] = (time.monotonic() + self.ttl_seconds, value)

    def invalidate_tenant(self, tenant_id: str) -> None:
        with self._lock:
            keys = [k for k in self._store if k[0] == tenant_id]
            for k in keys:
                del self._store[k]
