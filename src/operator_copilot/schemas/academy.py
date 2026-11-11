"""Pydantic v2 schemas for Knowledge Intelligence Engine and AI Course Generator."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_swagger_opt_str(value: str | None) -> str | None:
    """Ignore empty strings or Swagger UI's default 'string' placeholder."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() == "string":
        return None
    return cleaned


def _clean_roles_list(roles: list[str] | None) -> list[str]:
    """Normalize allowed_roles, falling back to ['operatore', 'admin'] if Swagger left ['string']."""
    if not roles:
        return ["operatore", "admin"]
    cleaned = [r.strip().lower() for r in roles if isinstance(r, str) and r.strip() and r.strip().lower() != "string"]
    return cleaned or ["operatore", "admin"]


# ---------------------------------------------------------------------------
# Structured LLM Output Models
# ---------------------------------------------------------------------------


class ExtractedProcedureLLM(BaseModel):
    title: str
    steps: list[str] = Field(default_factory=list)
    section: str = ""


class ExtractedExampleLLM(BaseModel):
    label: str
    is_correct: bool = True
    content: str
    section: str = ""


class ExtractedErrorLLM(BaseModel):
    error_or_antipattern: str
    consequence_or_fix: str
    section: str = ""


class KnowledgeExtractionLLMOutput(BaseModel):
    title: str
    summary: str
    procedures: list[ExtractedProcedureLLM] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    recurring_concepts: list[str] = Field(default_factory=list)
    practical_examples: list[ExtractedExampleLLM] = Field(default_factory=list)
    frequent_errors: list[ExtractedErrorLLM] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    software_modules: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)


class TopicClassificationLLMOutput(BaseModel):
    category: str
    secondary_categories: list[str] = Field(default_factory=list)
    rationale: str = ""


class RelevanceScoringLLMOutput(BaseModel):
    llm_relevance_score: float = Field(..., ge=0.0, le=1.0)
    operational_importance_note: str = ""
    error_criticality_note: str = ""
    rationale: str = ""


class GapDetectionLLMOutput(BaseModel):
    gaps_found: list[dict[str, str]] = Field(default_factory=list)


class CurriculumLessonPlanLLM(BaseModel):
    title: str
    objective: str
    source_sections: list[str] = Field(default_factory=list)


class CurriculumModulePlanLLM(BaseModel):
    title: str
    description: str
    learning_objective: str
    lessons: list[CurriculumLessonPlanLLM] = Field(default_factory=list)


class CurriculumLLMOutput(BaseModel):
    title: str
    description: str
    learning_objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    modules: list[CurriculumModulePlanLLM] = Field(default_factory=list)
    summary: str = ""


class LessonGenerationLLMOutput(BaseModel):
    title: str
    objective: str
    explanation: str
    procedures: list[str] = Field(default_factory=list)
    practical_examples: list[dict[str, Any]] = Field(default_factory=list)
    frequent_errors: list[dict[str, Any]] = Field(default_factory=list)
    exercises: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class QuizQuestionLLM(BaseModel):
    question_type: Literal["multiple_choice", "true_false", "scenario"] = "multiple_choice"
    question_text: str
    options: list[str] = Field(default_factory=list)
    correct_answer: str
    explanation: str = ""
    source_section: str = ""


class QuizGenerationLLMOutput(BaseModel):
    title: str
    questions: list[QuizQuestionLLM] = Field(default_factory=list)


class GroundingCheckLLMOutput(BaseModel):
    is_grounded: bool = True
    unsupported_claims: list[str] = Field(default_factory=list)
    contradictions_detected: list[str] = Field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# API Request & Response Schemas
# ---------------------------------------------------------------------------


class AnalysisJobRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "scope_type": "document",
                "scope_value": "2024_c07_modalita_corretta_richiesta_assistenza_clienti.md",
                "allowed_roles": ["operatore", "admin"],
                "run_async": False,
            }
        }
    )

    scope_type: Literal["full", "document", "category", "area"] = "full"
    scope_value: str | None = Field(
        default=None,
        description="Relative document path/document_id, category name, or area_name according to scope_type",
    )
    max_documents: int | None = Field(default=None, ge=1, le=5000)
    force_reanalyze: bool = False
    allowed_roles: list[str] = Field(default_factory=lambda: ["operatore", "admin"])
    run_async: bool = True

    @field_validator("scope_value")
    @classmethod
    def _sanitize_scope_value(cls, v: str | None) -> str | None:
        return _clean_swagger_opt_str(v)

    @field_validator("allowed_roles")
    @classmethod
    def _sanitize_roles(cls, v: list[str]) -> list[str]:
        return _clean_roles_list(v)


class AnalysisJobResponse(BaseModel):
    id: str
    scope_type: str
    scope_value: str | None = None
    tenant_id: str
    status: str
    total_documents: int
    processed_documents: int
    skipped_unchanged: int
    failed_documents: int
    last_processed_source: str | None = None
    corpus_version: str
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class TopicResponse(BaseModel):
    id: str
    tenant_id: str
    document_id: str
    source: str
    doc_year: int | None = None
    area_name: str | None = None
    category: str
    title: str
    summary: str
    procedures: list[dict[str, Any]] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    recurring_concepts: list[str] = Field(default_factory=list)
    practical_examples: list[dict[str, Any]] = Field(default_factory=list)
    frequent_errors: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    software_modules: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    source_passages: list[dict[str, Any]] = Field(default_factory=list)
    extraction_mode: str
    model_used: str


class RelevanceScoreResponse(BaseModel):
    id: str
    topic_id: str
    overall_score: float
    algorithmic_score: float
    llm_score: float | None = None
    factors: dict[str, Any] = Field(default_factory=dict)
    unverifiable_factors: list[str] = Field(default_factory=list)
    rationale: str
    scored_by_model: str


class KnowledgeGapResponse(BaseModel):
    id: str
    topic: str
    gap_type: str
    available_info: str
    missing_info: str
    analyzed_documents: list[dict[str, Any]] = Field(default_factory=list)
    reason: str
    suggested_addition: str
    severity: str
    created_at: datetime


class OpportunityBuildRequest(BaseModel):
    document_source: str | None = Field(
        default=None, description="Optional single document source or document_id to build an opportunity"
    )
    area_name: str | None = None
    allowed_roles: list[str] = Field(default_factory=lambda: ["operatore", "admin"])

    @field_validator("document_source", "area_name")
    @classmethod
    def _sanitize_strings(cls, v: str | None) -> str | None:
        return _clean_swagger_opt_str(v)

    @field_validator("allowed_roles")
    @classmethod
    def _sanitize_roles(cls, v: list[str]) -> list[str]:
        return _clean_roles_list(v)


class TrainingOpportunityResponse(BaseModel):
    id: str
    tenant_id: str
    title: str
    description: str
    learning_objective: str
    course_type: str
    topic_ids: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    source_documents: list[dict[str, Any]] = Field(default_factory=list)
    software_modules: list[str] = Field(default_factory=list)
    suggested_audience: list[str] = Field(default_factory=list)
    difficulty: str
    relevance_score: float
    completeness_score: float
    criticalities: list[str] = Field(default_factory=list)
    rationale: str
    status: str


class CourseGenerateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_source": "2024_c07_modalita_corretta_richiesta_assistenza_clienti.md",
                "course_type": "documental",
                "allowed_roles": ["operatore", "admin"],
            }
        }
    )

    opportunity_id: str | None = None
    document_source: str | None = None
    course_type: Literal["documental", "applicative"] | None = None
    allowed_roles: list[str] = Field(default_factory=lambda: ["operatore", "admin"])

    @field_validator("opportunity_id", "document_source")
    @classmethod
    def _sanitize_ids(cls, v: str | None) -> str | None:
        return _clean_swagger_opt_str(v)

    @field_validator("allowed_roles")
    @classmethod
    def _sanitize_roles(cls, v: list[str]) -> list[str]:
        return _clean_roles_list(v)


class LessonUpdateRequest(BaseModel):
    title: str | None = None
    objective: str | None = None
    explanation: str | None = None
    procedures: list[str] | None = None
    summary: str | None = None
    change_summary: str = "Modifica manuale contenuti lezione"


class QuizGenerateRequest(BaseModel):
    lesson_id: str | None = None
    num_questions: int = Field(default=5, ge=1, le=20)

    @field_validator("lesson_id")
    @classmethod
    def _sanitize_lesson_id(cls, v: str | None) -> str | None:
        return _clean_swagger_opt_str(v)


class LifecycleActionRequest(BaseModel):
    target_status: Literal["UNDER_REVIEW", "APPROVED", "REJECTED", "PUBLISHED"]
    notes: str = ""


class LessonSourceResponse(BaseModel):
    document_id: str
    document_title: str
    document_version: str
    chunk_id: str
    page: int | None = None
    section: str
    source: str
    updated_at: str
    excerpt: str = ""


class LessonResponse(BaseModel):
    id: str
    module_id: str
    order_index: int
    title: str
    objective: str
    explanation: str
    procedures: list[str] = Field(default_factory=list)
    practical_examples: list[dict[str, Any]] = Field(default_factory=list)
    frequent_errors: list[dict[str, Any]] = Field(default_factory=list)
    exercises: list[dict[str, Any]] = Field(default_factory=list)
    summary: str
    is_grounded: bool
    grounding_warnings: list[str] = Field(default_factory=list)
    sources: list[LessonSourceResponse] = Field(default_factory=list)


class ModuleResponse(BaseModel):
    id: str
    order_index: int
    title: str
    description: str
    learning_objective: str
    lessons: list[LessonResponse] = Field(default_factory=list)


class QuizQuestionResponse(BaseModel):
    id: str
    order_index: int
    question_type: str
    question_text: str
    options: list[str] = Field(default_factory=list)
    correct_answer: str
    explanation: str
    source_document_id: str
    source_chunk_id: str
    source_section: str


class QuizResponse(BaseModel):
    id: str
    course_id: str
    lesson_id: str | None = None
    title: str
    passing_score: int
    questions: list[QuizQuestionResponse] = Field(default_factory=list)


class CourseResponse(BaseModel):
    id: str
    opportunity_id: str | None = None
    tenant_id: str
    allowed_roles: list[str] = Field(default_factory=list)
    title: str
    description: str
    course_type: str
    learning_objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    target_audience: list[str] = Field(default_factory=list)
    difficulty: str
    summary: str
    lifecycle_status: str
    current_version: int
    corpus_version_at_generation: str
    grounding_status: str
    grounding_report: dict[str, Any] = Field(default_factory=dict)
    model_used: str
    modules: list[ModuleResponse] = Field(default_factory=list)
    quizzes: list[QuizResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
