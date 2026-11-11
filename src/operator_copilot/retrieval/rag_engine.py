"""Main RAG Engine orchestrating cache, hybrid retrieval, grounded generation, and history."""

from __future__ import annotations

import logging
import time

from langchain_core.language_models.chat_models import BaseChatModel

from operator_copilot.analytics.metrics import MetricsCollector
from operator_copilot.cache.cache_manager import CacheManager
from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.history.query_history import QueryHistoryManager
from operator_copilot.ingestion.indexer import DocumentIndexer
from operator_copilot.retrieval.retriever import HybridRetriever
from operator_copilot.schemas.query import RAGQueryRequest
from operator_copilot.schemas.response import (
    RAGResponse,
    ResponseMetadata,
    RetrievalInfo,
)

logger = logging.getLogger("operator_copilot.retrieval.rag_engine")


class RAGEngine:
    """High-level facade coordinating all Operator Copilot Milestone 1 components."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
        llm: BaseChatModel | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.indexer = DocumentIndexer(self.settings, self.db)
        self.retriever = HybridRetriever(self.settings, self.db)
        self.generator = AnswerGenerator(self.settings, llm=llm)
        self.cache = CacheManager(self.settings, self.db)
        self.history = QueryHistoryManager(self.settings, self.db)
        self.metrics = MetricsCollector(self.settings, self.db)

    def answer_query(self, request: RAGQueryRequest) -> RAGResponse:
        """Process an operator natural-language query end-to-end."""
        t_start = time.perf_counter()
        corpus_version = self.db.get_corpus_version()

        # 1. Smart Question Cache Lookup
        cache_res = self.cache.get(
            request.query,
            user_id=request.user_id,
            user_scope=request.user_scope,
            filters=request.filters,
            top_k=request.top_k,
        )
        if cache_res.hit and cache_res.answer is not None:
            total_ms = int((time.perf_counter() - t_start) * 1000)
            sources = cache_res.sources or []
            history_id = self.history.record_query(
                user_id=request.user_id,
                session_id=request.session_id,
                query=request.query,
                answer=cache_res.answer,
                sources=sources,
                cache_hit=True,
                needs_escalation=False,
                retrieval_time_ms=0,
                generation_time_ms=0,
                processing_time_ms=total_ms,
            )
            return RAGResponse(
                query=request.query,
                answer=cache_res.answer,
                sources=sources,
                retrieval=RetrievalInfo(
                    documents_found=len(sources),
                    relevance_score=cache_res.retrieval_score,
                ),
                metadata=ResponseMetadata(
                    cached=True,
                    processing_time_ms=total_ms,
                    needs_escalation=False,
                    history_id=history_id,
                    corpus_version=corpus_version,
                    prompt_version=self.settings.prompt_version,
                ),
                cached=True,
                processing_time_ms=total_ms,
                needs_escalation=False,
                history_id=history_id,
            )

        # 2. Hybrid Retrieval
        t_ret0 = time.perf_counter()
        error_msg: str | None = None
        try:
            chunks = self.retriever.retrieve(
                request.query,
                top_k=request.top_k,
                filters=request.filters,
            )
        except Exception as exc:
            logger.exception("Retrieval failed: %s", exc)
            chunks = []
            error_msg = f"Retrieval error: {exc}"
        retrieval_ms = int((time.perf_counter() - t_ret0) * 1000)

        top_relevance = round(max(c.relevance_score for c in chunks), 4) if chunks else None

        # 3. Grounded Answer Generation
        t_gen0 = time.perf_counter()
        gen = self.generator.generate(request.query, chunks)
        generation_ms = int((time.perf_counter() - t_gen0) * 1000)

        total_ms = int((time.perf_counter() - t_start) * 1000)

        # 4. Cache Storage (only positive supported answers)
        self.cache.put(
            request.query,
            answer=gen.answer,
            sources=gen.sources,
            retrieval_score=top_relevance,
            needs_escalation=gen.needs_escalation,
            user_id=request.user_id,
            user_scope=request.user_scope,
            filters=request.filters,
            top_k=request.top_k,
        )

        # 5. Record Query History
        history_id = self.history.record_query(
            user_id=request.user_id,
            session_id=request.session_id,
            query=request.query,
            answer=gen.answer,
            sources=gen.sources,
            cache_hit=False,
            needs_escalation=gen.needs_escalation,
            retrieval_time_ms=retrieval_ms,
            generation_time_ms=generation_ms,
            processing_time_ms=total_ms,
            error=error_msg,
        )

        return RAGResponse(
            query=request.query,
            answer=gen.answer,
            sources=gen.sources,
            retrieval=RetrievalInfo(
                documents_found=len(gen.sources),
                relevance_score=top_relevance,
            ),
            metadata=ResponseMetadata(
                cached=False,
                processing_time_ms=total_ms,
                needs_escalation=gen.needs_escalation,
                history_id=history_id,
                corpus_version=corpus_version,
                prompt_version=self.settings.prompt_version,
                abstention_reason=gen.abstention_reason,
            ),
            cached=False,
            processing_time_ms=total_ms,
            needs_escalation=gen.needs_escalation,
            history_id=history_id,
        )
