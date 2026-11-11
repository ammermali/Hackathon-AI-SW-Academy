"""Centralized configuration and structured logging for Operator Copilot."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "staging", "production", "test"] = "development"

    # LLM
    llm_provider: Literal["openai", "openai_compatible", "ollama", "extractive"] = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: int = Field(default=30, ge=1, le=300)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    # Embeddings
    embedding_provider: Literal["huggingface", "openai", "hashing"] = "huggingface"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # Vector store
    vectorstore_type: Literal["chroma", "faiss"] = "chroma"
    vectorstore_path: Path = Path("./storage/vectorstore")
    collection_name: str = "operator_copilot_docs"

    # Ingestion & Chunking
    data_dir: Path = Path("./data")
    chunk_size: int = Field(default=1200, ge=200, le=8000)
    chunk_overlap: int = Field(default=180, ge=0, le=2000)
    skip_index_files: bool = True
    dedup_near_duplicates: bool = True
    near_dup_threshold: float = Field(default=0.90, ge=0.5, le=1.0)

    # Database
    database_url: str = "sqlite:///./storage/operator_copilot.db"

    # Cache
    cache_enabled: bool = True
    cache_ttl_seconds: int = Field(default=3600, ge=1)
    cache_max_entries: int = Field(default=500, ge=1)
    semantic_cache_enabled: bool = False
    semantic_cache_threshold: float = Field(default=0.95, ge=0.5, le=1.0)

    # Retrieval & Prompts
    retrieval_top_k: int = Field(default=5, ge=1, le=30)
    retrieval_score_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    hybrid_bm25_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    reranker_enabled: bool = True
    prompt_version: str = "v1.0"

    # History & Security
    history_retention_days: int = Field(default=90, ge=1)
    admin_api_key: SecretStr = SecretStr("dev-admin-key-change-me")
    log_level: str = "INFO"

    def ensure_directories(self) -> None:
        """Create required local storage directories if missing."""
        self.vectorstore_path.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path_str = self.database_url.replace("sqlite:///", "", 1)
            if db_path_str and db_path_str != ":memory:":
                Path(db_path_str).parent.mkdir(parents=True, exist_ok=True)


class SensitiveDataLogFilter(logging.Filter):
    """Mask potential PII (Codice Fiscale, IBAN) and secret tokens in log messages."""

    _CF_RE = re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b")
    _IBAN_RE = re.compile(r"\bIT\d{2}[A-Z]\d{10}[0-9A-Z]{12}\b")
    _KEY_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{10,}|Bearer\s+[A-Za-z0-9._\-]{10,})")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = self._CF_RE.sub("[CF_REDACTED]", record.msg)
            msg = self._IBAN_RE.sub("[IBAN_REDACTED]", msg)
            msg = self._KEY_RE.sub("[SECRET_REDACTED]", msg)
            record.msg = msg
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure structured application logging with sensitive-data redaction."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger("operator_copilot")
    root.setLevel(numeric_level)

    if not root.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt='{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataLogFilter())
        root.addHandler(handler)
    else:
        for h in root.handlers:
            h.setLevel(numeric_level)


@lru_cache
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    settings = Settings()
    settings.ensure_directories()
    configure_logging(settings.log_level)
    return settings
