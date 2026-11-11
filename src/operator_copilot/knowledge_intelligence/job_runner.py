"""Incremental, resumable asynchronous Knowledge Analysis Job Runner."""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import DocumentMetadata, ExtractedTopic, KnowledgeAnalysisJob
from operator_copilot.knowledge_intelligence.classifier import TopicClassifier
from operator_copilot.knowledge_intelligence.extractor import KnowledgeExtractor
from operator_copilot.knowledge_intelligence.gap_detector import KnowledgeGapDetector
from operator_copilot.knowledge_intelligence.opportunities import OpportunityAggregator
from operator_copilot.knowledge_intelligence.scorer import RelevanceScorer

logger = logging.getLogger("operator_copilot.knowledge_intelligence.job_runner")


class KnowledgeJobRunner:
    """Executes incremental knowledge analysis jobs in background threads with resume support."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
        extractor: KnowledgeExtractor | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.extractor = extractor or KnowledgeExtractor(self.settings, self.db)
        self.classifier = TopicClassifier(generator=self.extractor.generator)
        self.scorer = RelevanceScorer(self.db, generator=self.extractor.generator)
        self.gap_detector = KnowledgeGapDetector(self.settings, self.db, generator=self.extractor.generator)
        self.aggregator = OpportunityAggregator(self.db, retriever=self.extractor.retriever)
        self._executor = ThreadPoolExecutor(
            max_workers=self.settings.analysis_max_workers,
            thread_name_prefix="knowledge-job",
        )

    def _select_target_documents(
        self,
        *,
        scope_type: str,
        scope_value: str | None,
        max_documents: int | None,
    ) -> list[DocumentMetadata]:
        with self.db.session() as db:
            query = db.query(DocumentMetadata).filter(DocumentMetadata.status == "indexed")
            if scope_type == "document" and scope_value:
                query = query.filter(
                    (DocumentMetadata.document_id == scope_value)
                    | (DocumentMetadata.source == scope_value)
                    | (DocumentMetadata.source.ilike(f"%{scope_value}%"))
                )
            elif scope_type == "area" and scope_value:
                query = query.filter(DocumentMetadata.area_name.ilike(f"%{scope_value}%"))
            elif scope_type == "category" and scope_value:
                query = query.filter(DocumentMetadata.document_type.ilike(f"%{scope_value}%"))

            rows = query.order_by(DocumentMetadata.source.asc()).all()
            if max_documents is not None:
                rows = rows[:max_documents]
            return rows

    def create_and_start_job(
        self,
        *,
        scope_type: str = "full",
        scope_value: str | None = None,
        tenant_id: str = "default",
        allowed_roles: list[str] | None = None,
        max_documents: int | None = None,
        force_reanalyze: bool = False,
        run_async: bool = True,
    ) -> KnowledgeAnalysisJob:
        """Create a persisted job record and execute synchronously or in ThreadPoolExecutor."""
        targets = self._select_target_documents(
            scope_type=scope_type,
            scope_value=scope_value,
            max_documents=max_documents,
        )
        # Allow single-document analysis directly from data_dir even if not yet in DocumentMetadata
        total = len(targets) if targets else (1 if scope_type == "document" and scope_value else 0)
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = KnowledgeAnalysisJob(
            id=job_id,
            scope_type=scope_type,
            scope_value=scope_value,
            tenant_id=tenant_id,
            allowed_roles=allowed_roles or ["operatore", "admin"],
            status="PENDING",
            total_documents=total,
            corpus_version=self.db.get_corpus_version(),
        )
        with self.db.session() as db:
            db.add(job)
            db.commit()
            db.refresh(job)

        if run_async:
            self._executor.submit(self._execute_job, job_id, force_reanalyze, max_documents)
        else:
            self._execute_job(job_id, force_reanalyze, max_documents)

        with self.db.session() as db:
            return db.get(KnowledgeAnalysisJob, job_id) or job

    def resume_job(self, job_id: str, *, run_async: bool = True) -> KnowledgeAnalysisJob:
        """Resume an interrupted or failed analysis job from processed_sources checkpoint."""
        with self.db.session() as db:
            job = db.get(KnowledgeAnalysisJob, job_id)
            if job is None:
                raise ValueError(f"Job '{job_id}' non trovato.")
            if job.status == "COMPLETED":
                return job
            job.status = "PENDING"
            job.error_message = None
            db.commit()

        if run_async:
            self._executor.submit(self._execute_job, job_id, False, None)
        else:
            self._execute_job(job_id, False, None)

        with self.db.session() as db:
            return db.get(KnowledgeAnalysisJob, job_id)  # type: ignore[return-value]

    def _execute_job(self, job_id: str, force_reanalyze: bool, max_documents: int | None = None) -> None:
        with self.db.session() as db:
            job = db.get(KnowledgeAnalysisJob, job_id)
            if job is None:
                return
            job.status = "RUNNING"
            db.commit()
            scope_type = job.scope_type
            scope_value = job.scope_value
            tenant_id = job.tenant_id
            allowed_roles = list(job.allowed_roles)
            already_done = set(job.processed_sources or [])

        try:
            targets = self._select_target_documents(
                scope_type=scope_type,
                scope_value=scope_value,
                max_documents=max_documents,
            )
            target_refs = [t.document_id for t in targets]
            if not target_refs and scope_type == "document" and scope_value:
                target_refs = [scope_value]

            produced_topics: list[ExtractedTopic] = []

            for ref in target_refs:
                bundle = self.extractor.load_document_bundle(ref)
                if bundle is None:
                    self._increment_job(job_id, failed=True, source=ref)
                    continue

                if bundle.source in already_done and not force_reanalyze:
                    continue

                # Incremental cache check: skip unchanged file_hash for this tenant
                if not force_reanalyze:
                    with self.db.session() as db:
                        cached_topic = (
                            db.query(ExtractedTopic)
                            .filter_by(
                                document_id=bundle.document_id,
                                tenant_id=tenant_id,
                                file_hash=bundle.file_hash,
                            )
                            .first()
                        )
                    if cached_topic is not None:
                        produced_topics.append(cached_topic)
                        self._increment_job(job_id, skipped=True, source=bundle.source)
                        continue

                topic = self.extractor.extract_from_bundle(
                    bundle,
                    tenant_id=tenant_id,
                    allowed_roles=allowed_roles,
                    job_id=job_id,
                    classifier=self.classifier,
                )
                self.scorer.score_topic(topic, persist=True)
                produced_topics.append(topic)
                self._increment_job(job_id, processed=True, source=bundle.source)

            # Detect knowledge gaps & build training opportunities for job topics
            if produced_topics:
                self.gap_detector.detect_for_topics(
                    produced_topics,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    persist=True,
                )
                self.aggregator.build_opportunities_from_clusters(
                    produced_topics,
                    tenant_id=tenant_id,
                    job_id=job_id,
                )

            with self.db.session() as db:
                job = db.get(KnowledgeAnalysisJob, job_id)
                if job is not None:
                    job.status = "COMPLETED"
                    job.completed_at = datetime.now(timezone.utc)
                    db.commit()
        except Exception as exc:
            logger.exception("Knowledge analysis job %s failed: %s", job_id, exc)
            with self.db.session() as db:
                job = db.get(KnowledgeAnalysisJob, job_id)
                if job is not None:
                    job.status = "FAILED"
                    job.error_message = str(exc)
                    db.commit()

    def _increment_job(
        self,
        job_id: str,
        *,
        processed: bool = False,
        skipped: bool = False,
        failed: bool = False,
        source: str | None = None,
    ) -> None:
        with self.db.session() as db:
            job = db.get(KnowledgeAnalysisJob, job_id)
            if job is None:
                return
            if processed:
                job.processed_documents += 1
            if skipped:
                job.skipped_unchanged += 1
            if failed:
                job.failed_documents += 1
            if source:
                job.last_processed_source = source
                sources_list = list(job.processed_sources or [])
                if source not in sources_list:
                    sources_list.append(source)
                    job.processed_sources = sources_list
            db.commit()
