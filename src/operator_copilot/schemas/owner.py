"""Pydantic v2 schemas for Owner Learning Dashboard & Analytics (Milestone 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from operator_copilot.schemas.academy import _clean_swagger_opt_str


# ---------------------------------------------------------------------------
# Structured LLM Output for Owner Insights (Qwen)
# ---------------------------------------------------------------------------


class OwnerInsightLLMItem(BaseModel):
    category: Literal["users", "topic", "module", "course", "custom_quiz"] = "topic"
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"] = "MEDIUM"
    message: str
    recommended_action: str = ""
    supporting_metric: str = ""


class OwnerInsightsLLMOutput(BaseModel):
    insights: list[OwnerInsightLLMItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# User Directory Upsert
# ---------------------------------------------------------------------------


class OrganizationUserUpsertRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=256)
    amministrazione: str = Field(default="Predefinita", min_length=1, max_length=256)
    role: str = Field(default="operatore", min_length=1, max_length=48)

    @field_validator("user_id", "display_name", "amministrazione", "role")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        cleaned = _clean_swagger_opt_str(v)
        if not cleaned:
            raise ValueError("Campo obbligatorio non valido.")
        return cleaned


class OrganizationUserResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    display_name: str
    amministrazione: str
    role: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Section 3: Dashboard Generale (Overview)
# ---------------------------------------------------------------------------


class TrendPoint(BaseModel):
    period: str
    attempts: int = 0
    avg_score: float = 0.0
    gaps_opened: int = 0
    gaps_resolved: int = 0


class OwnerDashboardOverviewResponse(BaseModel):
    tenant_id: str
    filters: dict[str, Any] = Field(default_factory=dict)
    total_users: int
    active_users_in_period: int
    course_completion_rate: float
    avg_quiz_score: float
    avg_learning_improvement: float | None = None
    knowledge_gap_resolution_rate: float
    open_gaps_count: int
    users_with_critical_gaps: int
    improvement_vs_previous_period: float | None = None
    available_softwares: list[str] = Field(default_factory=list)
    available_modules: list[str] = Field(default_factory=list)
    available_administrations: list[str] = Field(default_factory=list)
    timeline: list[TrendPoint] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Section 4: User Learning Overview
# ---------------------------------------------------------------------------


class OwnerUserOverviewItem(BaseModel):
    user_id: str
    display_name: str
    amministrazione: str
    softwares_used: list[str] = Field(default_factory=list)
    courses_completed: int
    quiz_success_rate: float
    custom_quizzes_count: int
    learning_improvement: float | None = None
    open_gaps_count: int
    critical_gaps_count: int = 0
    last_activity_at: datetime | None = None
    overall_status: str


class OwnerUsersPageResponse(BaseModel):
    tenant_id: str
    total: int
    page: int
    page_size: int
    items: list[OwnerUserOverviewItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Section 5: User Learning Profile (Dettaglio Utente)
# ---------------------------------------------------------------------------


class UserQuizEvolutionPoint(BaseModel):
    attempt_id: str
    quiz_id: str
    quiz_type: Literal["course_quiz", "custom_quiz"]
    title: str
    percentage: float
    passed_or_outcome: str
    completed_at: datetime


class CourseProgressItem(BaseModel):
    course_id: str
    title: str
    course_type: str
    status: Literal["COMPLETATO", "DA_COMPLETARE"]
    best_percentage: float | None = None
    last_attempt_at: datetime | None = None


class OwnerUserGapDetailItem(BaseModel):
    gap_id: str
    topic: str
    software: str
    module_name: str
    criticality: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    error_count: int
    last_difficulty_at: datetime | None = None
    verifications_count: int
    status: Literal["OPEN", "IN_PROGRESS", "IMPROVING", "RESOLVED"]
    last_result_percentage: float | None = None


class UserLearningHistoryEvent(BaseModel):
    event_type: Literal["course_quiz", "custom_quiz", "gap_transition", "topic_improvement"]
    title: str
    topic: str | None = None
    result_summary: str
    percentage: float | None = None
    occurred_at: datetime


class OwnerUserLearningPerformance(BaseModel):
    course_quiz_evolution: list[UserQuizEvolutionPoint] = Field(default_factory=list)
    custom_quiz_evolution: list[UserQuizEvolutionPoint] = Field(default_factory=list)
    competence_over_time: list[TrendPoint] = Field(default_factory=list)
    courses_completed: list[CourseProgressItem] = Field(default_factory=list)
    courses_to_complete: list[CourseProgressItem] = Field(default_factory=list)
    retention_rate: float | None = None


class OwnerUserDetailResponse(BaseModel):
    tenant_id: str
    user_id: str
    display_name: str
    amministrazione: str
    overall_status: str
    learning_performance: OwnerUserLearningPerformance
    knowledge_gaps: list[OwnerUserGapDetailItem] = Field(default_factory=list)
    learning_history: list[UserLearningHistoryEvent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Section 6: Topic to Review
# ---------------------------------------------------------------------------


class TopicAffectedUserItem(BaseModel):
    user_id: str
    display_name: str
    amministrazione: str
    gap_status: str
    priority: str
    repeated_error_count: int
    last_verified_at: datetime | None = None


class OwnerTopicReviewItem(BaseModel):
    topic: str
    software: str
    module_name: str
    affected_users_count: int
    total_gaps_count: int
    open_gaps_count: int
    avg_error_rate: float
    criticality: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    evolution_vs_previous_period: float | None = None


class OwnerTopicDrilldownResponse(BaseModel):
    tenant_id: str
    topic_summary: OwnerTopicReviewItem
    affected_users: list[TopicAffectedUserItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Section 7: Custom Quiz Analytics
# ---------------------------------------------------------------------------


class OwnerCustomQuizAnalyticsResponse(BaseModel):
    tenant_id: str
    filters: dict[str, Any] = Field(default_factory=dict)
    total_generated: int
    total_completed: int
    avg_correct_percentage: float
    improvement_between_verifications: float | None = None
    gaps_resolved_via_followup: int
    persistent_gaps_count: int
    repeated_error_rate: float
    retention_rate: float | None = None
    timeline: list[TrendPoint] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Section 8: Owner Insights & Audit
# ---------------------------------------------------------------------------


class OwnerInsightItem(BaseModel):
    category: Literal["users", "topic", "module", "course", "custom_quiz"]
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    message: str
    recommended_action: str
    evidence_metrics: dict[str, Any] = Field(default_factory=dict)
    source_engine: Literal["deterministic", "qwen_synthesized"] = "deterministic"


class OwnerInsightsResponse(BaseModel):
    tenant_id: str
    filters: dict[str, Any] = Field(default_factory=dict)
    model_used: str
    insights: list[OwnerInsightItem] = Field(default_factory=list)


class OwnerAuditLogItem(BaseModel):
    id: int
    tenant_id: str
    owner_id: str
    owner_role: str
    action: str
    resource: str
    target_user_id: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
