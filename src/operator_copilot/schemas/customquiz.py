"""Pydantic v2 schemas for Adaptive Learning & Custom Quiz Engine (Milestone 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from operator_copilot.schemas.academy import _clean_swagger_opt_str


# ---------------------------------------------------------------------------
# Structured LLM Output Schemas
# ---------------------------------------------------------------------------


class CustomQuizQuestionLLM(BaseModel):
    """Single personalized multiple-choice question with strictly 4 options."""

    question_text: str
    options: list[str] = Field(..., min_length=4, max_length=4)
    correct_option_index: int = Field(..., ge=0, le=3)
    explanation: str
    topic: str
    difficulty: Literal["base", "intermediate", "advanced"] = "intermediate"
    source_section: str = ""

    @model_validator(mode="after")
    def _ensure_four_distinct_options(self) -> CustomQuizQuestionLLM:
        cleaned = [opt.strip() for opt in self.options if isinstance(opt, str) and opt.strip()]
        if len(cleaned) != 4:
            raise ValueError("Ogni domanda del Custom Quiz deve avere esattamente 4 opzioni valide.")
        self.options = cleaned
        return self


class CustomQuizGenerationLLM(BaseModel):
    """LLM structured payload for generating a personalized Custom Quiz."""

    questions: list[CustomQuizQuestionLLM] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API Request Schemas (with Swagger placeholder sanitization)
# ---------------------------------------------------------------------------


class AnalyzeGapsRequest(BaseModel):
    software: str | None = None
    module_name: str | None = None

    @field_validator("software", "module_name")
    @classmethod
    def _sanitize(cls, v: str | None) -> str | None:
        return _clean_swagger_opt_str(v)


class CustomQuizGenerateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "operatore_01",
                "num_questions": 4,
                "software": "CWOL",
                "module_name": "Assistenza",
                "force_new": False,
                "run_async": False,
            }
        }
    )

    user_id: str = Field(..., min_length=1, max_length=128)
    num_questions: int = Field(default=4, ge=1, le=20)
    software: str | None = None
    module_name: str | None = None
    focus_topic: str | None = None
    force_new: bool = False
    run_async: bool = False

    @field_validator("user_id")
    @classmethod
    def _sanitize_uid(cls, v: str) -> str:
        cleaned = _clean_swagger_opt_str(v)
        if not cleaned:
            raise ValueError("Il campo 'user_id' è obbligatorio.")
        return cleaned

    @field_validator("software", "module_name", "focus_topic")
    @classmethod
    def _sanitize_opt(cls, v: str | None) -> str | None:
        return _clean_swagger_opt_str(v)


class CustomQuizSubmitRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "operatore_01",
                "answers": {"cqq_1": "A", "cqq_2": "B"},
                "duration_seconds": 95,
            }
        }
    )

    user_id: str = Field(..., min_length=1, max_length=128)
    answers: dict[str, str] = Field(..., description="Mappa {question_id: 'A'|'B'|'C'|'D' o testo opzione}")
    duration_seconds: int = Field(default=60, ge=0, le=86400)


class CourseQuizSubmitRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    answers: dict[str, str] = Field(..., description="Mappa {question_id: risposta dell'utente}")


# ---------------------------------------------------------------------------
# API Response Schemas
# ---------------------------------------------------------------------------


class QuizOptionPublic(BaseModel):
    id: Literal["A", "B", "C", "D"]
    text: str


class CustomQuizQuestionPublicResponse(BaseModel):
    """Question schema omitting correct answers while quiz is not completed."""

    id: str
    order_index: int
    question_text: str
    options: list[QuizOptionPublic]
    topic: str
    difficulty: str
    gap_id: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)


class CustomQuizResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    software: str
    module_name: str
    status: str
    num_questions: int
    topics_verified: list[str] = Field(default_factory=list)
    gap_ids: list[str] = Field(default_factory=list)
    model_used: str
    prompt_version: str
    error_message: str | None = None
    generated_at: datetime
    completed_at: datetime | None = None
    questions: list[CustomQuizQuestionPublicResponse] = Field(default_factory=list)


class QuestionFeedbackItem(BaseModel):
    question_id: str
    topic: str
    user_answer: str
    is_correct: bool
    correct_option_id: str
    correct_answer: str
    explanation: str
    sources: list[dict[str, Any]] = Field(default_factory=list)


class RecommendedLessonItem(BaseModel):
    course_id: str
    course_title: str
    lesson_id: str | None = None
    lesson_title: str | None = None
    topic: str
    reason: str


class CustomQuizResultResponse(BaseModel):
    attempt_id: str
    quiz_id: str
    user_id: str
    correct_count: int
    total_questions: int
    score: float
    percentage: float
    duration_seconds: int
    outcome: str
    topics_understood: list[str] = Field(default_factory=list)
    topics_to_improve: list[str] = Field(default_factory=list)
    question_feedback: list[QuestionFeedbackItem] = Field(default_factory=list)
    recommended_lessons: list[RecommendedLessonItem] = Field(default_factory=list)
    updated_gaps: list[dict[str, Any]] = Field(default_factory=list)
    completed_at: datetime


class LearningGapResponse(BaseModel):
    id: str
    user_id: str
    topic: str
    software: str
    module_name: str
    evidences: list[dict[str, Any]] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)
    priority: str
    confidence: float
    status: str
    positive_verifications: int
    repeated_error_count: int
    detected_at: datetime
    last_verified_at: datetime | None = None
    resolved_at: datetime | None = None


class TopicProfileItem(BaseModel):
    topic: str
    software: str
    module_name: str
    estimated_level: float
    learning_stage: str
    rag_query_count: int
    troubleshooting_count: int
    verification_count: int
    correct_count: int
    error_count: int
    frequent_questions: list[str] = Field(default_factory=list)
    quiz_errors_summary: list[dict[str, Any]] = Field(default_factory=list)
    custom_quiz_history: list[dict[str, Any]] = Field(default_factory=list)
    last_verified_at: datetime | None = None


class UserLearningProfileResponse(BaseModel):
    user_id: str
    tenant_id: str
    softwares_used: list[str] = Field(default_factory=list)
    modules_used: list[str] = Field(default_factory=list)
    known_topics: list[str] = Field(default_factory=list)
    difficulty_topics: list[str] = Field(default_factory=list)
    frequent_questions: list[str] = Field(default_factory=list)
    topic_profiles: list[TopicProfileItem] = Field(default_factory=list)
    open_gaps: list[LearningGapResponse] = Field(default_factory=list)


class LearningMetricsResponse(BaseModel):
    user_id: str
    tenant_id: str
    filters: dict[str, Any] = Field(default_factory=dict)
    quiz_accuracy: float
    learning_improvement: float | None = None
    knowledge_gap_resolution_rate: float
    retention_rate: float | None = None
    repeated_error_rate: float
    learning_progress: float
    attempts_count: int
    gaps_summary: dict[str, int] = Field(default_factory=dict)
    learning_stages_summary: dict[str, int] = Field(default_factory=dict)
    per_topic_evolution: list[dict[str, Any]] = Field(default_factory=list)


class CourseQuizSubmitResponse(BaseModel):
    attempt_id: str
    quiz_id: str
    course_id: str
    user_id: str
    correct_count: int
    total_questions: int
    percentage: float
    passed: bool
    wrong_topics: list[str] = Field(default_factory=list)
    gaps_updated: int = 0
    completed_at: datetime
