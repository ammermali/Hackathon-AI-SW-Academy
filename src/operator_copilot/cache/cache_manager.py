"""SQLite-backed Smart Question Cache Manager with TTL, version invalidation, and isolation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from operator_copilot.cache.cache_policy import CachePolicy
from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import CacheEntry
from operator_copilot.schemas.response import SourceCitation

logger = logging.getLogger("operator_copilot.cache.cache_manager")


@dataclass
class CacheLookupResult:
    """Result returned on cache lookup."""

    hit: bool
    answer: str | None = None
    sources: list[SourceCitation] | None = None
    retrieval_score: float | None = None


class CacheManager:
    """Manages exact question caching with versioned invalidation and LRU/oldest eviction."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.policy = CachePolicy(
            ttl_seconds=self.settings.cache_ttl_seconds,
            max_entries=self.settings.cache_max_entries,
        )

    def _model_version(self) -> str:
        return f"{self.settings.llm_provider}:{self.settings.llm_model}"

    def get(
        self,
        query: str,
        *,
        user_id: str,
        user_scope: str = "public",
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> CacheLookupResult:
        """Look up exact cache entry matching query, scope, corpus_version, prompt_version, and model."""
        if not self.settings.cache_enabled:
            return CacheLookupResult(hit=False)

        query_hash = self.policy.compute_query_hash(query, filters=filters, top_k=top_k)
        owner = self.policy.resolve_owner(user_scope, user_id)
        corpus_version = self.db.get_corpus_version()
        prompt_version = self.settings.prompt_version
        model_version = self._model_version()
        now = datetime.now(timezone.utc)

        with self.db.session() as db:
            entry = (
                db.query(CacheEntry)
                .filter_by(
                    query_hash=query_hash,
                    user_scope=user_scope,
                    owner_user_id=owner,
                )
                .first()
            )
            if entry is None:
                return CacheLookupResult(hit=False)

            # Version invalidation check
            if (
                entry.corpus_version != corpus_version
                or entry.prompt_version != prompt_version
                or entry.model_version != model_version
            ):
                logger.info("Cache invalidated due to version mismatch for hash=%s", query_hash[:10])
                db.delete(entry)
                db.commit()
                return CacheLookupResult(hit=False)

            # TTL expiration check
            if self.policy.is_expired(entry.expires_at, now=now):
                logger.info("Cache entry expired for hash=%s", query_hash[:10])
                db.delete(entry)
                db.commit()
                return CacheLookupResult(hit=False)

            # Update usage statistics
            entry.hit_count += 1
            entry.last_accessed_at = now
            sources = [SourceCitation(**s) for s in (entry.sources or [])]
            answer = entry.answer
            retrieval_score = entry.retrieval_score
            db.commit()

            return CacheLookupResult(
                hit=True,
                answer=answer,
                sources=sources,
                retrieval_score=retrieval_score,
            )

    def put(
        self,
        query: str,
        *,
        answer: str,
        sources: list[SourceCitation],
        retrieval_score: float | None,
        needs_escalation: bool,
        user_id: str,
        user_scope: str = "public",
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> bool:
        """Persist a verified positive answer in cache, enforcing max_entries eviction."""
        if not self.settings.cache_enabled:
            return False

        if not self.policy.should_cache(needs_escalation, len(sources), answer):
            return False

        query_hash = self.policy.compute_query_hash(query, filters=filters, top_k=top_k)
        norm_query = self.policy.normalize_query(query)
        owner = self.policy.resolve_owner(user_scope, user_id)
        corpus_version = self.db.get_corpus_version()
        prompt_version = self.settings.prompt_version
        model_version = self._model_version()
        now = datetime.now(timezone.utc)
        expires_at = self.policy.compute_expiry(now)
        serialized_sources = [s.model_dump() for s in sources]

        with self.db.session() as db:
            # Purge expired entries opportunistically
            db.query(CacheEntry).filter(CacheEntry.expires_at <= now).delete()

            existing = (
                db.query(CacheEntry)
                .filter_by(
                    query_hash=query_hash,
                    user_scope=user_scope,
                    owner_user_id=owner,
                )
                .first()
            )
            if existing is not None:
                existing.normalized_query = norm_query
                existing.answer = answer
                existing.sources = serialized_sources
                existing.retrieval_score = retrieval_score
                existing.corpus_version = corpus_version
                existing.prompt_version = prompt_version
                existing.model_version = model_version
                existing.created_at = now
                existing.expires_at = expires_at
                existing.last_accessed_at = now
            else:
                # Evict oldest-accessed entries if at capacity
                total_entries = db.query(CacheEntry).count()
                if total_entries >= self.policy.max_entries:
                    to_evict = (total_entries - self.policy.max_entries) + 1
                    oldest = (
                        db.query(CacheEntry)
                        .order_by(CacheEntry.last_accessed_at.asc())
                        .limit(to_evict)
                        .all()
                    )
                    for item in oldest:
                        db.delete(item)

                db.add(
                    CacheEntry(
                        query_hash=query_hash,
                        normalized_query=norm_query,
                        user_scope=user_scope,
                        owner_user_id=owner,
                        answer=answer,
                        sources=serialized_sources,
                        retrieval_score=retrieval_score,
                        corpus_version=corpus_version,
                        prompt_version=prompt_version,
                        model_version=model_version,
                        hit_count=0,
                        created_at=now,
                        expires_at=expires_at,
                        last_accessed_at=now,
                    )
                )
            db.commit()
        return True

    def invalidate_all(self) -> int:
        """Delete all cache entries and return number of removed entries."""
        with self.db.session() as db:
            count = db.query(CacheEntry).delete()
            db.commit()
            return count
