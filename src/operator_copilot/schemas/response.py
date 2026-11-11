"""Pydantic response schemas for Operator Copilot RAG API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    """Real citation derived strictly from indexed chunk metadata."""

    document: str = Field(..., description="Nome/titolo o path relativo del documento")
    section: str = Field(default="", description="Sezione / heading path nel documento")
    page: int | None = Field(default=None, description="Numero di pagina se disponibile nel formato")
    chunk_id: str = Field(..., description="Identificativo univoco del chunk")
    area: str | None = Field(default=None, description="Area tematica del documento")
    relevance_score: float | None = Field(default=None, description="Score di similarità/rilevanza (non è una probabilità)")


class RetrievalInfo(BaseModel):
    """Metadata summarizing the retrieval phase."""

    documents_found: int = 0
    relevance_score: float | None = None


class ResponseMetadata(BaseModel):
    """Operational metadata attached to a RAG response."""

    cached: bool = False
    processing_time_ms: int = 0
    needs_escalation: bool = False
    history_id: int | None = None
    corpus_version: str = ""
    prompt_version: str = ""
    abstention_reason: str | None = None


class RAGResponse(BaseModel):
    """Structured RAG response schema."""

    query: str
    answer: str
    sources: list[SourceCitation] = Field(default_factory=list)
    retrieval: RetrievalInfo = Field(default_factory=RetrievalInfo)
    metadata: ResponseMetadata = Field(default_factory=ResponseMetadata)

    # Top-level convenience fields aligned with /api/v1/rag/query contract
    cached: bool = False
    processing_time_ms: int = 0
    needs_escalation: bool = False
    history_id: int | None = None


class HistoryItem(BaseModel):
    """Single historical query record for a user."""

    id: int
    user_id: str
    session_id: str
    query: str
    intent: str | None = None
    topic: str | None = None
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    cache_hit: bool
    processing_time_ms: int
    needs_escalation: bool
    created_at: datetime


class HistoryResponse(BaseModel):
    """User query history response with topic grouping for future personalization."""

    user_id: str
    total_returned: int
    items: list[HistoryItem]
    topics_summary: dict[str, int] = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    """Response after storing query feedback."""

    id: int
    query_history_id: int
    rating: int
    comment: str | None = None
    created_at: datetime


class DocumentInfoResponse(BaseModel):
    """Document metadata entry returned by GET /api/v1/rag/documents."""

    document_id: str
    source: str
    document_type: str
    area_name: str | None = None
    file_hash: str
    chunk_count: int
    status: str
    indexed_at: datetime
    updated_at: datetime


class IngestResponse(BaseModel):
    """Summary returned by POST /api/v1/rag/ingest."""

    status: str
    corpus_version: str
    files_scanned: int
    files_indexed: int
    files_skipped_unchanged: int
    files_skipped_duplicate: int
    files_failed: int
    chunks_created: int
    processing_time_ms: int


class MetricsResponse(BaseModel):
    """Aggregated performance, knowledge, cache, and user metrics."""

    performance: dict[str, Any]
    knowledge: dict[str, Any]
    cache: dict[str, Any]
    user: dict[str, Any]
    learning_readiness: dict[str, Any]
