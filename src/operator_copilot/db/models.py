"""SQLAlchemy ORM models for Operator Copilot operational persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base SQLAlchemy declarative class."""


class QueryHistory(Base):
    """Stores every user query interaction for audit, metrics, and future personalization."""

    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    retrieved_doc_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_escalation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retrieval_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generation_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processing_time_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    feedbacks: Mapped[list[QueryFeedback]] = relationship(
        "QueryFeedback", back_populates="history_item", cascade="all, delete-orphan"
    )


class QueryFeedback(Base):
    """Stores operator feedback on generated answers."""

    __tablename__ = "query_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("query_history.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    history_item: Mapped[QueryHistory] = relationship("QueryHistory", back_populates="feedbacks")


class CacheEntry(Base):
    """Persistent exact question cache with TTL, version invalidation, and user isolation."""

    __tablename__ = "cache_entries"
    __table_args__ = (
        UniqueConstraint("query_hash", "user_scope", "owner_user_id", name="uq_cache_scope_hash"),
        Index("ix_cache_lookup", "query_hash", "corpus_version", "prompt_version", "model_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    normalized_query: Mapped[str] = mapped_column(Text, nullable=False)
    user_scope: Mapped[str] = mapped_column(String(16), default="public", nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(128), default="__public__", nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    retrieval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    corpus_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DocumentMetadata(Base):
    """Tracks indexed documents, file hashes for incremental updates, and ingestion status."""

    __tablename__ = "document_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), default="manual", nullable=False)
    area_name: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    doc_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="indexed", index=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SystemState(Base):
    """Key-value operational metadata such as active corpus_version and last ingestion timestamp."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
