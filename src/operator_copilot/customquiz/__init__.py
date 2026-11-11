"""Dedicated 'customquiz' logical entry point integrated with RAGEngine and Adaptive Learning Engine."""

from __future__ import annotations

from datetime import datetime

from operator_copilot.adaptive_learning.service import AdaptiveLearningService
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.customquiz import (
    CourseQuizSubmitResponse,
    CustomQuizResponse,
    CustomQuizResultResponse,
    LearningGapResponse,
    LearningMetricsResponse,
    UserLearningProfileResponse,
)


class CustomQuizEngine:
    """High-level entry point 'customquiz' reusing an existing RAGEngine (retrieval, DB, Qwen LLM)."""

    def __init__(self, rag_engine: RAGEngine) -> None:
        self.rag = rag_engine
        self.service = AdaptiveLearningService(
            settings=rag_engine.settings,
            db_manager=rag_engine.db,
            retriever=rag_engine.retriever,
            generator=rag_engine.generator,
        )

    def analyze_gaps(
        self,
        user_id: str,
        *,
        tenant_id: str = "default",
        software: str | None = None,
        module_name: str | None = None,
    ) -> list[LearningGapResponse]:
        return self.service.analyze_user_gaps(
            user_id,
            tenant_id=tenant_id,
            software=software,
            module_name=module_name,
        )

    def generate(
        self,
        *,
        user_id: str,
        tenant_id: str = "default",
        num_questions: int = 4,
        software: str | None = None,
        module_name: str | None = None,
        focus_topic: str | None = None,
        force_new: bool = False,
        run_async: bool = False,
    ) -> CustomQuizResponse:
        return self.service.generate_custom_quiz(
            tenant_id=tenant_id,
            user_id=user_id,
            num_questions=num_questions,
            software=software,
            module_name=module_name,
            focus_topic=focus_topic,
            force_new=force_new,
            run_async=run_async,
        )

    def get_quiz(self, quiz_id: str, *, tenant_id: str = "default", user_id: str | None = None) -> CustomQuizResponse | None:
        return self.service.get_quiz(quiz_id, tenant_id=tenant_id, user_id=user_id)

    def list_user_quizzes(self, user_id: str, *, tenant_id: str = "default") -> list[CustomQuizResponse]:
        return self.service.list_user_quizzes(user_id, tenant_id=tenant_id)

    def submit(
        self,
        *,
        quiz_id: str,
        user_id: str,
        answers: dict[str, str],
        tenant_id: str = "default",
        duration_seconds: int = 60,
        completed_at: datetime | None = None,
    ) -> CustomQuizResultResponse:
        return self.service.submit_custom_quiz(
            quiz_id=quiz_id,
            tenant_id=tenant_id,
            user_id=user_id,
            answers=answers,
            duration_seconds=duration_seconds,
            completed_at=completed_at,
        )

    def submit_course_quiz(
        self,
        *,
        course_id: str,
        quiz_id: str,
        user_id: str,
        answers: dict[str, str],
        tenant_id: str = "default",
    ) -> CourseQuizSubmitResponse:
        return self.service.submit_traditional_course_quiz(
            course_id=course_id,
            quiz_id=quiz_id,
            tenant_id=tenant_id,
            user_id=user_id,
            answers=answers,
        )

    def get_results(self, quiz_id: str, *, user_id: str, tenant_id: str = "default") -> CustomQuizResultResponse:
        return self.service.get_quiz_results(quiz_id, tenant_id=tenant_id, user_id=user_id)

    def get_learning_profile(self, user_id: str, *, tenant_id: str = "default") -> UserLearningProfileResponse:
        return self.service.get_user_learning_profile(user_id, tenant_id=tenant_id)

    def get_learning_metrics(
        self,
        user_id: str,
        *,
        tenant_id: str = "default",
        topic: str | None = None,
        software: str | None = None,
        module_name: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> LearningMetricsResponse:
        return self.service.metrics_svc.compute_metrics(
            user_id=user_id,
            tenant_id=tenant_id,
            topic=topic,
            software=software,
            module_name=module_name,
            date_from=date_from,
            date_to=date_to,
        )

    def delete_user_data(self, user_id: str, *, tenant_id: str = "default") -> dict[str, int]:
        return self.service.delete_user_learning_data(user_id, tenant_id=tenant_id)


__all__ = ["CustomQuizEngine"]
