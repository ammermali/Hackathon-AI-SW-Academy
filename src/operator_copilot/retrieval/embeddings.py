"""Embedding provider factory for Operator Copilot."""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from langchain_core.embeddings import Embeddings

from operator_copilot.config.settings import Settings, get_settings


class DeterministicHashingEmbeddings(Embeddings):
    """Lightweight deterministic L2-normalized bag-of-ngrams embeddings for fast tests."""

    def __init__(self, dimension: int = 128) -> None:
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        tokens = re.findall(r"\b\w{2,}\b", text.lower()) or ["empty"]
        for i, tok in enumerate(tokens):
            idx1 = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:4], "little") % self.dimension
            vec[idx1] += 1.0
            if i + 1 < len(tokens):
                bg = f"{tok}_{tokens[i + 1]}"
                idx2 = int.from_bytes(hashlib.md5(bg.encode("utf-8")).digest()[:4], "little") % self.dimension
                vec[idx2] += 1.5
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def build_embeddings(settings: Settings | None = None) -> Embeddings:
    """Instantiate configured LangChain Embeddings provider."""
    cfg = settings or get_settings()
    if cfg.embedding_provider == "hashing":
        return DeterministicHashingEmbeddings()
    if cfg.embedding_provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        api_key = cfg.llm_api_key.get_secret_value() if cfg.llm_api_key else None
        return OpenAIEmbeddings(
            model=cfg.embedding_model,
            api_key=api_key,
            base_url=cfg.llm_base_url or None,
        )

    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=cfg.embedding_model,
        encode_kwargs={"normalize_embeddings": True},
    )


@lru_cache(maxsize=4)
def get_cached_embeddings(provider: str, model_name: str) -> Embeddings:
    """Cache heavy embedding model instances across calls."""
    cfg = get_settings()
    if cfg.embedding_provider == provider and cfg.embedding_model == model_name:
        return build_embeddings(cfg)
    temp_cfg = cfg.model_copy(update={"embedding_provider": provider, "embedding_model": model_name})
    return build_embeddings(temp_cfg)
