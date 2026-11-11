"""Pydantic request schemas for Operator Copilot RAG API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


_SWAGGER_PLACEHOLDER_KEYS = {"additionalProp1", "additionalProp2", "additionalProp3"}


class RAGQueryRequest(BaseModel):
    """Input payload for POST /api/v1/rag/query."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Come si apre correttamente una richiesta di assistenza clienti per Cityware Online?",
                "user_id": "operatore_01",
                "session_id": "session_001",
                "top_k": 5,
                "filters": None,
                "user_scope": "public",
            }
        }
    )

    query: str = Field(..., min_length=2, max_length=2000, description="Domanda in linguaggio naturale")
    user_id: str = Field(default="anonymous", min_length=1, max_length=128)
    session_id: str = Field(default="default_session", min_length=1, max_length=128)
    top_k: int | None = Field(default=None, ge=1, le=20, description="Override numero documenti recuperati")
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Filtri metadata opzionali (es. area_name, document_type, doc_year)",
    )
    user_scope: Literal["public", "private"] = Field(
        default="public",
        description="Isolamento cache: 'public' condivisibile su corpus comune, 'private' isolato per user_id",
    )

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("La query deve contenere almeno 2 caratteri non vuoti.")
        return cleaned

    @field_validator("filters")
    @classmethod
    def sanitize_filters(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Drop empty values and Swagger UI placeholder keys (e.g. additionalProp1)."""
        if not v:
            return None
        cleaned = {
            k: val
            for k, val in v.items()
            if k not in _SWAGGER_PLACEHOLDER_KEYS
            and isinstance(val, (str, int, float, bool))
            and val != ""
        }
        return cleaned or None


class FeedbackRequest(BaseModel):
    """Input payload for POST /api/v1/rag/feedback."""

    query_history_id: int = Field(..., ge=1)
    user_id: str = Field(default="anonymous", min_length=1, max_length=128)
    rating: int = Field(..., ge=1, le=5, description="Valutazione da 1 (negativo) a 5 (molto utile)")
    comment: str | None = Field(default=None, max_length=1000)


class IngestRequest(BaseModel):
    """Input payload for POST /api/v1/rag/ingest."""

    rebuild: bool = Field(default=False, description="Se True ricostruisce l'intero indice da zero")
    max_files: int | None = Field(default=None, ge=1, description="Limite opzionale file per test/debug")
