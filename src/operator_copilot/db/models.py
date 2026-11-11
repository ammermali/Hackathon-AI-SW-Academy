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


# ---------------------------------------------------------------------------
# AI Knowledge-to-Course Engine Entities
# ---------------------------------------------------------------------------


class KnowledgeAnalysisJob(Base):
    """Asynchronous incremental job tracking knowledge analysis progress and resume state."""

    __tablename__ = "knowledge_analysis_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="full", nullable=False)  # full|document|category|area
    scope_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    allowed_roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True, nullable=False)
    total_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_unchanged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_processed_source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    processed_sources: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    corpus_version: Mapped[str] = mapped_column(String(64), default="v0", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExtractedTopic(Base):
    """Structured operational & training knowledge extracted from an indexed document."""

    __tablename__ = "extracted_topics"
    __table_args__ = (
        Index("ix_topic_doc_tenant", "document_id", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("knowledge_analysis_jobs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    allowed_roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    doc_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_name: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    category: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    procedures: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    rules: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    recurring_concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    practical_examples: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    frequent_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    constraints: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    related_topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    software_modules: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    target_roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_passages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    extraction_mode: Mapped[str] = mapped_column(String(32), default="deterministic", nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), default="deterministic_fallback", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    relevance_scores: Mapped[list[TopicRelevanceScore]] = relationship(
        "TopicRelevanceScore", back_populates="topic", cascade="all, delete-orphan"
    )


class TopicRelevanceScore(Base):
    """Multi-factor training relevance evaluation distinguishing algorithmic vs LLM vs unverifiable."""

    __tablename__ = "topic_relevance_scores"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("extracted_topics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    algorithmic_score: Mapped[float] = mapped_column(Float, nullable=False)
    llm_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    unverifiable_factors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    scored_by_model: Mapped[str] = mapped_column(String(128), default="algorithmic_only", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    topic: Mapped[ExtractedTopic] = relationship("ExtractedTopic", back_populates="relevance_scores")


class KnowledgeGap(Base):
    """Detected insufficient, incomplete, outdated, or contradictory knowledge areas."""

    __tablename__ = "knowledge_gaps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("knowledge_analysis_jobs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    allowed_roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    topic: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    gap_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # insufficient|incomplete|contradictory|outdated
    available_info: Mapped[str] = mapped_column(Text, nullable=False)
    missing_info: Mapped[str] = mapped_column(Text, nullable=False)
    analyzed_documents: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_addition: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TrainingOpportunity(Base):
    """Aggregated training course proposal derived from one or more correlated documents."""

    __tablename__ = "training_opportunities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("knowledge_analysis_jobs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    allowed_roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    learning_objective: Mapped[str] = mapped_column(Text, nullable=False)
    course_type: Mapped[str] = mapped_column(String(32), default="documental", nullable=False)  # documental|applicative
    topic_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_documents: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    software_modules: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    suggested_audience: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), default="base", nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    completeness_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    criticalities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PROPOSED", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Course(Base):
    """Structured training course generated from a TrainingOpportunity with lifecycle workflow."""

    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("training_opportunities.id", ondelete="SET NULL"), index=True, nullable=True
    )
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True, nullable=False)
    allowed_roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    course_type: Mapped[str] = mapped_column(String(32), default="documental", nullable=False)
    learning_objectives: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    prerequisites: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    target_audience: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), default="base", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="GENERATED", index=True, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    corpus_version_at_generation: Mapped[str] = mapped_column(String(64), default="v0", nullable=False)
    source_hashes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    grounding_status: Mapped[str] = mapped_column(String(32), default="VERIFIED", nullable=False)
    grounding_report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    model_used: Mapped[str] = mapped_column(String(128), default="deterministic_fallback", nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    modules: Mapped[list[CourseModule]] = relationship(
        "CourseModule", back_populates="course", cascade="all, delete-orphan", order_by="CourseModule.order_index"
    )
    quizzes: Mapped[list[Quiz]] = relationship(
        "Quiz", back_populates="course", cascade="all, delete-orphan"
    )
    revisions: Mapped[list[CourseRevision]] = relationship(
        "CourseRevision", back_populates="course", cascade="all, delete-orphan", order_by="CourseRevision.version_number"
    )
    approval_events: Mapped[list[CourseApprovalEvent]] = relationship(
        "CourseApprovalEvent", back_populates="course", cascade="all, delete-orphan", order_by="CourseApprovalEvent.id"
    )


class CourseModule(Base):
    """Curriculum module belonging to a Course."""

    __tablename__ = "course_modules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    learning_objective: Mapped[str] = mapped_column(Text, default="", nullable=False)

    course: Mapped[Course] = relationship("Course", back_populates="modules")
    lessons: Mapped[list[Lesson]] = relationship(
        "Lesson", back_populates="module", cascade="all, delete-orphan", order_by="Lesson.order_index"
    )


class Lesson(Base):
    """Autonomous lesson grounded in verifiable document chunks."""

    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    module_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("course_modules.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    objective: Mapped[str] = mapped_column(Text, default="", nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    procedures: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    practical_examples: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    frequent_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    exercises: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    grounding_warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_grounded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    module: Mapped[CourseModule] = relationship("CourseModule", back_populates="lessons")
    sources: Mapped[list[LessonSource]] = relationship(
        "LessonSource", back_populates="lesson", cascade="all, delete-orphan"
    )


class LessonSource(Base):
    """Explicit traceability mapping between a Lesson and exact source document/chunk metadata."""

    __tablename__ = "lesson_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lesson_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("lessons.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    document_title: Mapped[str] = mapped_column(String(512), nullable=False)
    document_version: Mapped[str] = mapped_column(String(128), default="unknown", nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)

    lesson: Mapped[Lesson] = relationship("Lesson", back_populates="sources")


class Quiz(Base):
    """Assessment quiz attached to a Course (and optionally a specific Lesson)."""

    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    course_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lesson_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    passing_score: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    course: Mapped[Course] = relationship("Course", back_populates="quizzes")
    questions: Mapped[list[QuizQuestion]] = relationship(
        "QuizQuestion", back_populates="quiz", cascade="all, delete-orphan", order_by="QuizQuestion.order_index"
    )


class QuizQuestion(Base):
    """Individual quiz question linked to source document and chunk."""

    __tablename__ = "quiz_questions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quiz_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("quizzes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(String(32), default="multiple_choice", nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_document_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    source_chunk_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    source_section: Mapped[str] = mapped_column(String(512), default="", nullable=False)

    quiz: Mapped[Quiz] = relationship("Quiz", back_populates="questions")


class CourseRevision(Base):
    """Versioned snapshot of Course edits and regenerations."""

    __tablename__ = "course_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    changed_by: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    course: Mapped[Course] = relationship("Course", back_populates="revisions")


class CourseApprovalEvent(Base):
    """Audit trail of publication workflow transitions."""

    __tablename__ = "course_approval_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    course: Mapped[Course] = relationship("Course", back_populates="approval_events")
