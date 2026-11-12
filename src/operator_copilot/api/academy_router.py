"""FastAPI router exposing AI Knowledge-to-Course Engine endpoints."""

from __future__ import annotations

import secrets
from typing import Any, Callable
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import joinedload

from operator_copilot.api.dependencies import assert_user_access, build_caller_context_dependency
from operator_copilot.config.settings import Settings
from operator_copilot.customquiz import CustomQuizEngine
from operator_copilot.course_generator.generator import AICourseGenerator
from operator_copilot.course_generator.grounding_verifier import GroundingVerifier
from operator_copilot.course_generator.lifecycle import CourseLifecycleManager
from operator_copilot.db.models import (
    Course,
    CourseApprovalEvent,
    CourseModule,
    CourseQuizAttempt,
    CourseRevision,
    CustomQuiz,
    CustomQuizAttempt,
    ExtractedTopic,
    KnowledgeAnalysisJob,
    KnowledgeGap,
    Lesson,
    LessonCompletion,
    Quiz,
    TopicRelevanceScore,
    TrainingOpportunity,
)
from operator_copilot.knowledge_intelligence.extractor import KnowledgeExtractor
from operator_copilot.knowledge_intelligence.job_runner import KnowledgeJobRunner
from operator_copilot.knowledge_intelligence.opportunities import OpportunityAggregator
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.academy import (
    AnalysisJobRequest,
    AnalysisJobResponse,
    CourseGenerateRequest,
    CourseProgressOverviewItem,
    CourseQuizAttemptSummaryItem,
    CourseResponse,
    CourseUpdateRequest,
    CustomQuizAttemptSummaryItem,
    KnowledgeGapResponse,
    LessonCompletionResponse,
    LessonResponse,
    LessonSourceResponse,
    LessonUpdateRequest,
    LifecycleActionRequest,
    ModuleResponse,
    OpportunityBuildRequest,
    QuizGenerateRequest,
    QuizQuestionResponse,
    QuizResponse,
    RelevanceScoreResponse,
    TopicResponse,
    TrainingOpportunityResponse,
    UserLearningOverviewResponse,
)
from operator_copilot.schemas.customquiz import CourseQuizSubmitRequest, CourseQuizSubmitResponse


def _serialize_course(course: Course) -> CourseResponse:
    return CourseResponse(
        id=course.id,
        opportunity_id=course.opportunity_id,
        tenant_id=course.tenant_id,
        allowed_roles=list(course.allowed_roles or []),
        title=course.title,
        description=course.description,
        course_type=course.course_type,
        learning_objectives=list(course.learning_objectives or []),
        prerequisites=list(course.prerequisites or []),
        target_audience=list(course.target_audience or []),
        difficulty=course.difficulty,
        summary=course.summary,
        lifecycle_status=course.lifecycle_status,
        current_version=course.current_version,
        corpus_version_at_generation=course.corpus_version_at_generation,
        grounding_status=course.grounding_status,
        grounding_report=dict(course.grounding_report or {}),
        model_used=course.model_used,
        modules=[
            ModuleResponse(
                id=m.id,
                order_index=m.order_index,
                title=m.title,
                description=m.description,
                learning_objective=m.learning_objective,
                lessons=[
                    LessonResponse(
                        id=les.id,
                        module_id=les.module_id,
                        order_index=les.order_index,
                        title=les.title,
                        objective=les.objective,
                        explanation=les.explanation,
                        procedures=list(les.procedures or []),
                        practical_examples=list(les.practical_examples or []),
                        frequent_errors=list(les.frequent_errors or []),
                        exercises=list(les.exercises or []),
                        summary=les.summary,
                        is_grounded=les.is_grounded,
                        grounding_warnings=list(les.grounding_warnings or []),
                        sources=[
                            LessonSourceResponse(
                                document_id=s.document_id,
                                document_title=s.document_title,
                                document_version=s.document_version,
                                chunk_id=s.chunk_id,
                                page=s.page,
                                section=s.section,
                                source=s.source,
                                updated_at=s.updated_at,
                                excerpt=s.excerpt,
                            )
                            for s in les.sources
                        ],
                    )
                    for les in m.lessons
                ],
            )
            for m in course.modules
        ],
        quizzes=[
            QuizResponse(
                id=q.id,
                course_id=q.course_id,
                lesson_id=q.lesson_id,
                title=q.title,
                passing_score=q.passing_score,
                questions=[
                    QuizQuestionResponse(
                        id=qq.id,
                        order_index=qq.order_index,
                        question_type=qq.question_type,
                        question_text=qq.question_text,
                        options=list(qq.options or []),
                        correct_answer=qq.correct_answer,
                        explanation=qq.explanation,
                        source_document_id=qq.source_document_id,
                        source_chunk_id=qq.source_chunk_id,
                        source_section=qq.source_section,
                    )
                    for qq in q.questions
                ],
            )
            for q in course.quizzes
        ],
        created_at=course.created_at,
        updated_at=course.updated_at,
        published_at=course.published_at,
    )


def _has_role_access(allowed_roles: list[str] | None, caller_role: str) -> bool:
    if not allowed_roles:
        return True
    if caller_role == "admin":
        return True
    if caller_role in {"owner", "learning_manager"}:
        return "owner" in allowed_roles or "learning_manager" in allowed_roles or "operatore" in allowed_roles
    return caller_role in allowed_roles


def create_academy_router(
    *,
    get_rag_engine: Callable[[], RAGEngine],
    verify_admin_key: Callable[..., None],
    settings: Settings,
) -> APIRouter:
    """Create modular APIRouter for Knowledge Intelligence & AI Course Generator."""
    router = APIRouter(prefix="/api/v1/academy", tags=["Knowledge-to-Course Academy"])
    get_caller_context = build_caller_context_dependency(settings)

    def verify_course_authoring_access(
        ctx: dict[str, str] = Depends(get_caller_context),
        x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
        x_owner_key: str | None = Header(default=None, alias="X-Owner-Key"),
    ) -> dict[str, str]:
        """Allow authenticated Admin (X-Admin-Key) or verified Owner (demo token or X-Owner-Key)."""
        expected_admin = settings.admin_api_key.get_secret_value()
        if x_admin_key and secrets.compare_digest(x_admin_key, expected_admin):
            return ctx
        if ctx["role"] in {"owner", "learning_manager"}:
            expected_owner = settings.owner_api_key.get_secret_value()
            if ctx.get("is_demo_verified") == "true" or (
                x_owner_key and secrets.compare_digest(x_owner_key, expected_owner)
            ):
                return ctx
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operazione riservata esclusivamente ad utenti Owner o Admin autenticati.",
        )

    def _services(rag: RAGEngine) -> tuple[KnowledgeJobRunner, AICourseGenerator, GroundingVerifier, CourseLifecycleManager]:
        extractor = KnowledgeExtractor(
            settings=rag.settings,
            db_manager=rag.db,
            retriever=rag.retriever,
            generator=rag.generator,
        )
        runner = KnowledgeJobRunner(rag.settings, rag.db, extractor=extractor)
        course_gen = AICourseGenerator(rag.settings, rag.db, extractor=extractor, generator=rag.generator)
        verifier = GroundingVerifier(rag.settings, rag.db, generator=rag.generator)
        lifecycle = CourseLifecycleManager(rag.db)
        return runner, course_gen, verifier, lifecycle

    @router.get("/llm-status", summary="Verifica configurazione modello LLM (Qwen) attiva")
    def get_llm_status(rag: RAGEngine = Depends(get_rag_engine)) -> dict[str, Any]:
        return rag.generator.get_model_info()

    @router.post(
        "/analysis/jobs",
        response_model=AnalysisJobResponse,
        summary="Avvia analisi incrementale della knowledge base (globale/documento/categoria/area)",
        dependencies=[Depends(verify_admin_key)],
    )
    def start_analysis_job(
        payload: AnalysisJobRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> KnowledgeAnalysisJob:
        runner, _, _, _ = _services(rag)
        return runner.create_and_start_job(
            scope_type=payload.scope_type,
            scope_value=payload.scope_value,
            tenant_id=ctx["tenant_id"],
            allowed_roles=payload.allowed_roles,
            max_documents=payload.max_documents,
            force_reanalyze=payload.force_reanalyze,
            run_async=payload.run_async,
        )

    @router.post(
        "/analysis/jobs/{job_id}/resume",
        response_model=AnalysisJobResponse,
        summary="Riprende un job di analisi interrotto o fallito",
        dependencies=[Depends(verify_admin_key)],
    )
    def resume_analysis_job(
        job_id: str,
        run_async: bool = Query(default=False),
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> KnowledgeAnalysisJob:
        with rag.db.session() as db:
            job = db.get(KnowledgeAnalysisJob, job_id)
            if job is None or job.tenant_id != ctx["tenant_id"]:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job non trovato.")
        runner, _, _, _ = _services(rag)
        return runner.resume_job(job_id, run_async=run_async)

    @router.get("/analysis/jobs/{job_id}", response_model=AnalysisJobResponse)
    def get_analysis_job(
        job_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> KnowledgeAnalysisJob:
        with rag.db.session() as db:
            job = db.get(KnowledgeAnalysisJob, job_id)
            if job is None or job.tenant_id != ctx["tenant_id"]:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job non trovato.")
            return job

    @router.get("/topics", response_model=list[TopicResponse], summary="Elenca argomenti estratti dalla KB")
    def list_topics(
        category: str | None = Query(default=None),
        area_name: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[ExtractedTopic]:
        with rag.db.session() as db:
            q = db.query(ExtractedTopic).filter(ExtractedTopic.tenant_id == ctx["tenant_id"])
            if category:
                q = q.filter(ExtractedTopic.category == category)
            if area_name:
                q = q.filter(ExtractedTopic.area_name.ilike(f"%{area_name}%"))
            rows = q.order_by(ExtractedTopic.updated_at.desc()).limit(limit).all()
            return [r for r in rows if _has_role_access(r.allowed_roles, ctx["role"])]

    @router.get(
        "/topics/{topic_id}/score",
        response_model=RelevanceScoreResponse,
        summary="Restituisce il relevance score dettagliato di un argomento",
    )
    def get_topic_score(
        topic_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> TopicRelevanceScore:
        with rag.db.session() as db:
            topic = db.get(ExtractedTopic, topic_id)
            if topic is None or topic.tenant_id != ctx["tenant_id"] or not _has_role_access(topic.allowed_roles, ctx["role"]):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Argomento non trovato.")
            score = (
                db.query(TopicRelevanceScore)
                .filter_by(topic_id=topic_id, tenant_id=ctx["tenant_id"])
                .order_by(TopicRelevanceScore.created_at.desc())
                .first()
            )
            if score is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Score non ancora calcolato.")
            return score

    @router.get("/gaps", response_model=list[KnowledgeGapResponse], summary="Elenca i knowledge gap rilevati")
    def list_gaps(
        gap_type: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[KnowledgeGap]:
        with rag.db.session() as db:
            q = db.query(KnowledgeGap).filter(KnowledgeGap.tenant_id == ctx["tenant_id"])
            if gap_type:
                q = q.filter(KnowledgeGap.gap_type == gap_type)
            rows = q.order_by(KnowledgeGap.created_at.desc()).limit(limit).all()
            return [r for r in rows if _has_role_access(r.allowed_roles, ctx["role"])]

    @router.get(
        "/opportunities",
        response_model=list[TrainingOpportunityResponse],
        summary="Consulta le proposte formative individuate",
    )
    def list_opportunities(
        limit: int = Query(default=100, ge=1, le=500),
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[TrainingOpportunity]:
        with rag.db.session() as db:
            rows = (
                db.query(TrainingOpportunity)
                .filter(TrainingOpportunity.tenant_id == ctx["tenant_id"])
                .order_by(TrainingOpportunity.relevance_score.desc())
                .limit(limit)
                .all()
            )
            return [r for r in rows if _has_role_access(r.allowed_roles, ctx["role"])]

    @router.post(
        "/opportunities/build",
        response_model=list[TrainingOpportunityResponse],
        summary="Aggrega documenti/argomenti correlati in proposte formative",
        dependencies=[Depends(verify_admin_key)],
    )
    def build_opportunities(
        payload: OpportunityBuildRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[TrainingOpportunity]:
        runner, _, _, _ = _services(rag)
        if payload.document_source:
            job = runner.create_and_start_job(
                scope_type="document",
                scope_value=payload.document_source,
                tenant_id=ctx["tenant_id"],
                allowed_roles=payload.allowed_roles,
                run_async=False,
            )
            with rag.db.session() as db:
                return db.query(TrainingOpportunity).filter_by(job_id=job.id, tenant_id=ctx["tenant_id"]).all()

        with rag.db.session() as db:
            q = db.query(ExtractedTopic).filter(ExtractedTopic.tenant_id == ctx["tenant_id"])
            if payload.area_name:
                q = q.filter(ExtractedTopic.area_name.ilike(f"%{payload.area_name}%"))
            topics = q.all()
        if not topics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nessun argomento estratto disponibile per generare proposte.",
            )
        aggregator = OpportunityAggregator(rag.db, retriever=rag.retriever)
        return aggregator.build_opportunities_from_clusters(topics, tenant_id=ctx["tenant_id"])

    @router.post(
        "/courses/generate",
        response_model=CourseResponse,
        summary="Genera un corso strutturato (non pubblicato automaticamente)",
        dependencies=[Depends(verify_course_authoring_access)],
    )
    def generate_course(
        payload: CourseGenerateRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> CourseResponse:
        _, course_gen, _, _ = _services(rag)
        try:
            if payload.opportunity_id:
                course = course_gen.generate_from_opportunity(
                    payload.opportunity_id,
                    tenant_id=ctx["tenant_id"],
                    course_type=payload.course_type,
                    created_by=ctx["user_id"],
                )
            elif payload.document_source:
                course = course_gen.generate_from_document(
                    payload.document_source,
                    tenant_id=ctx["tenant_id"],
                    allowed_roles=payload.allowed_roles,
                    course_type=payload.course_type,
                    created_by=ctx["user_id"],
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Specificare 'opportunity_id' oppure 'document_source'.",
                )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return _serialize_course(course)

    @router.patch(
        "/courses/{course_id}",
        response_model=CourseResponse,
        summary="Modifica metadati del corso creando una nuova revisione",
        dependencies=[Depends(verify_course_authoring_access)],
    )
    def update_course(
        course_id: str,
        payload: CourseUpdateRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> CourseResponse:
        with rag.db.session() as db:
            course = db.query(Course).filter_by(id=course_id, tenant_id=ctx["tenant_id"]).first()
            if course is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corso non trovato.")
            if payload.title is not None and payload.title.strip():
                course.title = payload.title.strip()
            if payload.description is not None and payload.description.strip():
                course.description = payload.description.strip()
            if payload.summary is not None:
                course.summary = payload.summary.strip()
            if payload.difficulty is not None and payload.difficulty.strip():
                course.difficulty = payload.difficulty.strip()
            if payload.allowed_roles is not None and len(payload.allowed_roles) > 0:
                cleaned_roles = [r.strip().lower() for r in payload.allowed_roles if r.strip()]
                if cleaned_roles:
                    course.allowed_roles = cleaned_roles
            db.commit()

        _, course_gen, _, lifecycle = _services(rag)
        lifecycle.record_revision(course_id, change_summary=payload.change_summary, changed_by=ctx["user_id"])
        updated = course_gen.get_course(course_id, tenant_id=ctx["tenant_id"])
        assert updated is not None
        return _serialize_course(updated)

    @router.get("/courses", response_model=list[CourseResponse], summary="Elenca corsi del tenant accessibili")
    def list_courses(
        lifecycle_status: str | None = Query(default=None),
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[CourseResponse]:
        with rag.db.session() as db:
            q = (
                db.query(Course)
                .options(
                    joinedload(Course.modules).joinedload(CourseModule.lessons).joinedload(Lesson.sources),
                    joinedload(Course.quizzes).joinedload(Quiz.questions),
                )
                .filter(Course.tenant_id == ctx["tenant_id"])
            )
            if lifecycle_status:
                q = q.filter(Course.lifecycle_status == lifecycle_status)
            rows = q.order_by(Course.created_at.desc()).all()
            return [_serialize_course(c) for c in rows if _has_role_access(c.allowed_roles, ctx["role"])]

    @router.get("/courses/impact-check", summary="Identifica corsi impattati da modifiche alle fonti")
    def check_impacted_courses(
        mark_needs_update: bool = Query(default=True),
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> list[dict[str, Any]]:
        _, _, _, lifecycle = _services(rag)
        return lifecycle.detect_impacted_courses(tenant_id=ctx["tenant_id"], mark_needs_update=mark_needs_update)

    @router.get("/courses/{course_id}", response_model=CourseResponse)
    def get_course(
        course_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> CourseResponse:
        _, course_gen, _, _ = _services(rag)
        course = course_gen.get_course(course_id, tenant_id=ctx["tenant_id"])
        if course is None or not _has_role_access(course.allowed_roles, ctx["role"]):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corso non trovato.")
        return _serialize_course(course)

    @router.patch(
        "/courses/{course_id}/lessons/{lesson_id}",
        response_model=LessonResponse,
        summary="Modifica manualmente una lezione creando una nuova revisione",
        dependencies=[Depends(verify_course_authoring_access)],
    )
    def update_lesson(
        course_id: str,
        lesson_id: str,
        payload: LessonUpdateRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> LessonResponse:
        with rag.db.session() as db:
            course = db.query(Course).filter_by(id=course_id, tenant_id=ctx["tenant_id"]).first()
            if course is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corso non trovato.")
            lesson = (
                db.query(Lesson)
                .options(joinedload(Lesson.sources))
                .filter_by(id=lesson_id, course_id=course_id)
                .first()
            )
            if lesson is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lezione non trovata.")
            if payload.title is not None:
                lesson.title = payload.title
            if payload.objective is not None:
                lesson.objective = payload.objective
            if payload.explanation is not None:
                lesson.explanation = payload.explanation
            if payload.procedures is not None:
                lesson.procedures = payload.procedures
            if payload.summary is not None:
                lesson.summary = payload.summary
            db.commit()

        _, _, verifier, lifecycle = _services(rag)
        verifier.verify_course(course_id, tenant_id=ctx["tenant_id"])
        lifecycle.record_revision(course_id, change_summary=payload.change_summary, changed_by=ctx["user_id"])

        with rag.db.session() as db:
            les = db.query(Lesson).options(joinedload(Lesson.sources)).filter_by(id=lesson_id).first()
            assert les is not None
            return LessonResponse(
                id=les.id,
                module_id=les.module_id,
                order_index=les.order_index,
                title=les.title,
                objective=les.objective,
                explanation=les.explanation,
                procedures=list(les.procedures or []),
                practical_examples=list(les.practical_examples or []),
                frequent_errors=list(les.frequent_errors or []),
                exercises=list(les.exercises or []),
                summary=les.summary,
                is_grounded=les.is_grounded,
                grounding_warnings=list(les.grounding_warnings or []),
                sources=[
                    LessonSourceResponse(
                        document_id=s.document_id,
                        document_title=s.document_title,
                        document_version=s.document_version,
                        chunk_id=s.chunk_id,
                        page=s.page,
                        section=s.section,
                        source=s.source,
                        updated_at=s.updated_at,
                        excerpt=s.excerpt,
                    )
                    for s in les.sources
                ],
            )

    @router.post(
        "/courses/{course_id}/lessons/{lesson_id}/regenerate",
        response_model=LessonResponse,
        summary="Rigenera una lezione dalle fonti originali",
        dependencies=[Depends(verify_course_authoring_access)],
    )
    def regenerate_lesson(
        course_id: str,
        lesson_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> LessonResponse:
        _, course_gen, _, _ = _services(rag)
        try:
            les = course_gen.regenerate_lesson(
                course_id,
                lesson_id,
                tenant_id=ctx["tenant_id"],
                actor_id=ctx["user_id"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return LessonResponse(
            id=les.id,
            module_id=les.module_id,
            order_index=les.order_index,
            title=les.title,
            objective=les.objective,
            explanation=les.explanation,
            procedures=list(les.procedures or []),
            practical_examples=list(les.practical_examples or []),
            frequent_errors=list(les.frequent_errors or []),
            exercises=list(les.exercises or []),
            summary=les.summary,
            is_grounded=les.is_grounded,
            grounding_warnings=list(les.grounding_warnings or []),
            sources=[
                LessonSourceResponse(
                    document_id=s.document_id,
                    document_title=s.document_title,
                    document_version=s.document_version,
                    chunk_id=s.chunk_id,
                    page=s.page,
                    section=s.section,
                    source=s.source,
                    updated_at=s.updated_at,
                    excerpt=s.excerpt,
                )
                for s in les.sources
            ],
        )

    @router.post(
        "/courses/{course_id}/quizzes/generate",
        response_model=QuizResponse,
        summary="Genera quiz verificati per un corso o una singola lezione",
        dependencies=[Depends(verify_course_authoring_access)],
    )
    def generate_quiz(
        course_id: str,
        payload: QuizGenerateRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> QuizResponse:
        _, course_gen, _, _ = _services(rag)
        try:
            quiz = course_gen.generate_quiz(
                course_id,
                tenant_id=ctx["tenant_id"],
                lesson_id=payload.lesson_id,
                num_questions=payload.num_questions,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return QuizResponse(
            id=quiz.id,
            course_id=quiz.course_id,
            lesson_id=quiz.lesson_id,
            title=quiz.title,
            passing_score=quiz.passing_score,
            questions=[
                QuizQuestionResponse(
                    id=qq.id,
                    order_index=qq.order_index,
                    question_type=qq.question_type,
                    question_text=qq.question_text,
                    options=list(qq.options or []),
                    correct_answer=qq.correct_answer,
                    explanation=qq.explanation,
                    source_document_id=qq.source_document_id,
                    source_chunk_id=qq.source_chunk_id,
                    source_section=qq.source_section,
                )
                for qq in quiz.questions
            ],
        )

    @router.post(
        "/courses/{course_id}/quizzes/{quiz_id}/submit",
        response_model=CourseQuizSubmitResponse,
        summary="Registra le risposte utente su un quiz tradizionale del corso alimentando l'Adaptive Learning",
    )
    def submit_course_quiz(
        course_id: str,
        quiz_id: str,
        payload: CourseQuizSubmitRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> CourseQuizSubmitResponse:
        assert_user_access(ctx, payload.user_id)
        try:
            return CustomQuizEngine(rag).submit_course_quiz(
                course_id=course_id,
                quiz_id=quiz_id,
                user_id=payload.user_id,
                answers=payload.answers,
                tenant_id=ctx["tenant_id"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @router.post(
        "/courses/{course_id}/validate",
        summary="Valida grounding, fonti, versioni obsolete e contraddizioni del corso",
    )
    def validate_course(
        course_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> dict[str, Any]:
        _, _, verifier, _ = _services(rag)
        try:
            return verifier.verify_course(course_id, tenant_id=ctx["tenant_id"])
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @router.post(
        "/courses/{course_id}/lifecycle",
        response_model=CourseResponse,
        summary="Gestisce il workflow di revisione, approvazione, rifiuto e pubblicazione",
        dependencies=[Depends(verify_course_authoring_access)],
    )
    def transition_course_lifecycle(
        course_id: str,
        payload: LifecycleActionRequest,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> CourseResponse:
        _, course_gen, _, lifecycle = _services(rag)
        try:
            lifecycle.transition(
                course_id,
                target_status=payload.target_status,
                tenant_id=ctx["tenant_id"],
                actor_id=ctx["user_id"],
                actor_role=ctx["role"],
                notes=payload.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        course = course_gen.get_course(course_id, tenant_id=ctx["tenant_id"])
        assert course is not None
        return _serialize_course(course)

    @router.get("/courses/{course_id}/sources", summary="Mostra tutte le fonti originali per ogni lezione del corso")
    def get_course_sources(
        course_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> dict[str, Any]:
        _, course_gen, _, _ = _services(rag)
        course = course_gen.get_course(course_id, tenant_id=ctx["tenant_id"])
        if course is None or not _has_role_access(course.allowed_roles, ctx["role"]):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corso non trovato.")
        return {
            "course_id": course.id,
            "title": course.title,
            "lessons": [
                {
                    "lesson_id": les.id,
                    "lesson_title": les.title,
                    "sources": [
                        {
                            "document_id": s.document_id,
                            "document_title": s.document_title,
                            "document_version": s.document_version,
                            "chunk_id": s.chunk_id,
                            "page": s.page,
                            "section": s.section,
                            "source": s.source,
                            "updated_at": s.updated_at,
                        }
                        for s in les.sources
                    ],
                }
                for m in course.modules
                for les in m.lessons
            ],
        }

    @router.get("/courses/{course_id}/revisions", summary="Storico revisioni ed eventi di approvazione del corso")
    def get_course_revisions(
        course_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> dict[str, Any]:
        with rag.db.session() as db:
            course = db.query(Course).filter_by(id=course_id, tenant_id=ctx["tenant_id"]).first()
            if course is None or not _has_role_access(course.allowed_roles, ctx["role"]):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corso non trovato.")
            revs = db.query(CourseRevision).filter_by(course_id=course_id).order_by(CourseRevision.version_number.asc()).all()
            events = db.query(CourseApprovalEvent).filter_by(course_id=course_id).order_by(CourseApprovalEvent.id.asc()).all()
            return {
                "course_id": course_id,
                "current_version": course.current_version,
                "revisions": [
                    {
                        "version_number": r.version_number,
                        "change_summary": r.change_summary,
                        "changed_by": r.changed_by,
                        "created_at": r.created_at,
                    }
                    for r in revs
                ],
                "approval_events": [
                    {
                        "from_status": e.from_status,
                        "to_status": e.to_status,
                        "action": e.action,
                        "actor_id": e.actor_id,
                        "actor_role": e.actor_role,
                        "notes": e.notes,
                        "created_at": e.created_at,
                    }
                    for e in events
                ],
            }

    @router.post(
        "/courses/{course_id}/lessons/{lesson_id}/complete",
        response_model=LessonCompletionResponse,
        summary="Segna una lezione come completata per l'utente corrente",
    )
    def complete_lesson(
        course_id: str,
        lesson_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> LessonCompletionResponse:
        if ctx["user_id"] == "anonymous":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="È necessario un utente identificato per registrare il completamento della lezione.",
            )
        with rag.db.session() as db:
            course = db.query(Course).filter_by(id=course_id, tenant_id=ctx["tenant_id"]).first()
            if course is None or not _has_role_access(course.allowed_roles, ctx["role"]):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Corso non trovato.")
            lesson = db.query(Lesson).filter_by(id=lesson_id, course_id=course_id).first()
            if lesson is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lezione non trovata.")

            existing = (
                db.query(LessonCompletion)
                .filter_by(tenant_id=ctx["tenant_id"], user_id=ctx["user_id"], lesson_id=lesson_id)
                .first()
            )
            if existing is None:
                existing = LessonCompletion(
                    id=f"lcmp_{uuid.uuid4().hex[:12]}",
                    tenant_id=ctx["tenant_id"],
                    user_id=ctx["user_id"],
                    course_id=course_id,
                    lesson_id=lesson_id,
                )
                db.add(existing)
                db.commit()
                db.refresh(existing)
                rag.db.bump_owner_metrics_version(ctx["tenant_id"])

            return LessonCompletionResponse(
                lesson_id=existing.lesson_id,
                course_id=existing.course_id,
                user_id=existing.user_id,
                completed=True,
                completed_at=existing.completed_at,
            )

    @router.get(
        "/users/{user_id}/learning-overview",
        response_model=UserLearningOverviewResponse,
        summary="Stato avanzamento corsi, lezioni completate e storico quiz dell'utente",
    )
    def get_user_learning_overview(
        user_id: str,
        ctx: dict[str, str] = Depends(get_caller_context),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> UserLearningOverviewResponse:
        assert_user_access(ctx, user_id)
        tenant_id = ctx["tenant_id"]
        with rag.db.session() as db:
            courses = (
                db.query(Course)
                .options(
                    joinedload(Course.modules).joinedload(CourseModule.lessons),
                    joinedload(Course.quizzes),
                )
                .filter(Course.tenant_id == tenant_id)
                .order_by(Course.created_at.desc())
                .all()
            )
            accessible_courses = [c for c in courses if _has_role_access(c.allowed_roles, ctx["role"])]

            completions = (
                db.query(LessonCompletion)
                .filter_by(tenant_id=tenant_id, user_id=user_id)
                .order_by(LessonCompletion.completed_at.desc())
                .all()
            )
            completed_lesson_ids = [c.lesson_id for c in completions]
            completion_set = set(completed_lesson_ids)
            last_lesson_by_course: dict[str, Any] = {}
            for cmp_row in completions:
                if cmp_row.course_id not in last_lesson_by_course:
                    last_lesson_by_course[cmp_row.course_id] = cmp_row.completed_at

            course_attempts = (
                db.query(CourseQuizAttempt)
                .filter_by(tenant_id=tenant_id, user_id=user_id)
                .order_by(CourseQuizAttempt.completed_at.desc())
                .all()
            )
            course_map = {c.id: c for c in courses}
            quiz_map = {q.id: q for c in courses for q in c.quizzes}

            attempts_by_course: dict[str, list[CourseQuizAttempt]] = {}
            for att in course_attempts:
                attempts_by_course.setdefault(att.course_id, []).append(att)

            course_progress: list[CourseProgressOverviewItem] = []
            for course in accessible_courses:
                lesson_ids = [les.id for mod in course.modules for les in mod.lessons]
                total_lessons = len(lesson_ids)
                done_lessons = sum(1 for lid in lesson_ids if lid in completion_set)
                c_attempts = attempts_by_course.get(course.id, [])
                best_pct = max((a.percentage for a in c_attempts), default=None)
                any_passed = any(a.passed for a in c_attempts)

                if total_lessons > 0 and done_lessons >= total_lessons:
                    c_status = "COMPLETED"
                elif total_lessons == 0 and any_passed:
                    c_status = "COMPLETED"
                elif done_lessons > 0 or len(c_attempts) > 0:
                    c_status = "IN_PROGRESS"
                else:
                    c_status = "NOT_STARTED"

                timestamps = [a.completed_at for a in c_attempts]
                if course.id in last_lesson_by_course:
                    timestamps.append(last_lesson_by_course[course.id])
                last_act = max(timestamps) if timestamps else None
                pct = (
                    round((done_lessons / total_lessons) * 100.0, 1)
                    if total_lessons > 0
                    else (100.0 if any_passed else 0.0)
                )

                course_progress.append(
                    CourseProgressOverviewItem(
                        course_id=course.id,
                        completed_lessons=done_lessons,
                        total_lessons=total_lessons,
                        completion_percentage=pct,
                        status=c_status,
                        best_quiz_percentage=round(best_pct, 1) if best_pct is not None else None,
                        last_activity_at=last_act,
                    )
                )

            course_quiz_items = [
                CourseQuizAttemptSummaryItem(
                    attempt_id=a.id,
                    quiz_id=a.quiz_id,
                    quiz_title=quiz_map[a.quiz_id].title if a.quiz_id in quiz_map else "Quiz didattico",
                    course_id=a.course_id,
                    course_title=course_map[a.course_id].title if a.course_id in course_map else "Corso",
                    lesson_id=quiz_map[a.quiz_id].lesson_id if a.quiz_id in quiz_map else None,
                    percentage=round(a.percentage, 1),
                    passed=a.passed,
                    wrong_topics=list(a.wrong_topics or []),
                    completed_at=a.completed_at,
                )
                for a in course_attempts
            ]

            cq_attempts = (
                db.query(CustomQuizAttempt, CustomQuiz)
                .join(CustomQuiz, CustomQuiz.id == CustomQuizAttempt.quiz_id)
                .filter(CustomQuizAttempt.tenant_id == tenant_id, CustomQuizAttempt.user_id == user_id)
                .order_by(CustomQuizAttempt.completed_at.desc())
                .all()
            )
            custom_quiz_items = [
                CustomQuizAttemptSummaryItem(
                    attempt_id=att.id,
                    quiz_id=att.quiz_id,
                    software=cq.software,
                    module_name=cq.module_name,
                    topics_verified=list(cq.topics_verified or []),
                    correct_count=att.correct_count,
                    total_questions=att.total_questions,
                    percentage=round(att.percentage, 1),
                    outcome=att.outcome,
                    duration_seconds=att.duration_seconds,
                    completed_at=att.completed_at,
                )
                for att, cq in cq_attempts
            ]

            return UserLearningOverviewResponse(
                user_id=user_id,
                tenant_id=tenant_id,
                completed_lesson_ids=completed_lesson_ids,
                course_progress=course_progress,
                course_quiz_attempts=course_quiz_items,
                custom_quiz_attempts=custom_quiz_items,
            )

    return router
