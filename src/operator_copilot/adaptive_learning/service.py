"""Facade service orchestrating Adaptive Learning, Course Quiz Tracking, and Custom Quiz lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import joinedload

from operator_copilot.adaptive_learning.gap_detector import LearningGapDetector
from operator_copilot.adaptive_learning.metrics import LearningMetricsService
from operator_copilot.adaptive_learning.personalizer import PersonalizationEngine
from operator_copilot.adaptive_learning.profiler import UserKnowledgeProfiler
from operator_copilot.adaptive_learning.quiz_generator import CustomQuizGenerator
from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import (
    Course,
    CourseModule,
    CourseQuizAttempt,
    CustomQuiz,
    CustomQuizAttempt,
    LearningGap,
    QueryHistory,
    Quiz,
    UserKnowledgeProfile,
)
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.retrieval.retriever import HybridRetriever
from operator_copilot.schemas.customquiz import (
    CourseQuizQuestionFeedback,
    CourseQuizSubmitResponse,
    CustomQuizQuestionPublicResponse,
    CustomQuizResponse,
    CustomQuizResultResponse,
    LearningGapResponse,
    QuestionFeedbackItem,
    QuizOptionPublic,
    RecommendedLessonItem,
    TopicProfileItem,
    UserLearningProfileResponse,
)


class AdaptiveLearningService:
    """Integrates profiling, gap detection, personalization, Custom Quiz generation, and metrics."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
        retriever: HybridRetriever | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.retriever = retriever
        self.generator = generator or AnswerGenerator(self.settings)
        self.profiler = UserKnowledgeProfiler(self.settings, self.db)
        self.gap_detector = LearningGapDetector(self.settings, self.db)
        self.personalizer = PersonalizationEngine(self.db)
        self.quiz_gen = CustomQuizGenerator(
            settings=self.settings,
            db_manager=self.db,
            retriever=self.retriever,
            generator=self.generator,
        )
        self.metrics_svc = LearningMetricsService(self.db)

    @staticmethod
    def _serialize_quiz(quiz: CustomQuiz) -> CustomQuizResponse:
        """Serialize CustomQuiz publicly without revealing correct answers prior to submission."""
        return CustomQuizResponse(
            id=quiz.id,
            tenant_id=quiz.tenant_id,
            user_id=quiz.user_id,
            software=quiz.software,
            module_name=quiz.module_name,
            status=quiz.status,
            num_questions=quiz.num_questions,
            topics_verified=list(quiz.topics_verified or []),
            gap_ids=list(quiz.gap_ids or []),
            model_used=quiz.model_used,
            prompt_version=quiz.prompt_version,
            error_message=quiz.error_message,
            generated_at=quiz.generated_at,
            completed_at=quiz.completed_at,
            questions=[
                CustomQuizQuestionPublicResponse(
                    id=q.id,
                    order_index=q.order_index,
                    question_text=q.question_text,
                    options=[QuizOptionPublic(id=o["id"], text=o["text"]) for o in q.options],
                    topic=q.topic,
                    difficulty=q.difficulty,
                    gap_id=q.gap_id,
                    sources=list(q.sources or []),
                )
                for q in quiz.questions
            ],
        )

    @staticmethod
    def _serialize_gap(g: LearningGap) -> LearningGapResponse:
        return LearningGapResponse(
            id=g.id,
            user_id=g.user_id,
            topic=g.topic,
            software=g.software,
            module_name=g.module_name,
            evidences=list(g.evidences or []),
            evidence_sources=list(g.evidence_sources or []),
            priority=g.priority,
            confidence=g.confidence,
            status=g.status,
            positive_verifications=g.positive_verifications,
            repeated_error_count=g.repeated_error_count,
            detected_at=g.detected_at,
            last_verified_at=g.last_verified_at,
            resolved_at=g.resolved_at,
        )

    def analyze_user_gaps(
        self,
        user_id: str,
        *,
        tenant_id: str = "default",
        software: str | None = None,
        module_name: str | None = None,
    ) -> list[LearningGapResponse]:
        gaps = self.gap_detector.analyze_user_gaps(
            user_id,
            tenant_id=tenant_id,
            software_filter=software,
            module_filter=module_name,
        )
        self.profiler.refresh_user_profile(user_id, tenant_id=tenant_id)
        return [self._serialize_gap(g) for g in gaps]

    def submit_traditional_course_quiz(
        self,
        *,
        course_id: str,
        quiz_id: str,
        tenant_id: str = "default",
        user_id: str,
        answers: dict[str, str],
    ) -> CourseQuizSubmitResponse:
        """Evaluate & persist user answers on a traditional course Quiz and feed Adaptive Learning."""
        with self.db.session() as db:
            course = db.query(Course).filter_by(id=course_id, tenant_id=tenant_id).first()
            if course is None:
                raise ValueError(f"Corso '{course_id}' non trovato.")
            quiz = (
                db.query(Quiz)
                .options(joinedload(Quiz.questions))
                .filter_by(id=quiz_id, course_id=course_id)
                .first()
            )
            if quiz is None:
                raise ValueError(f"Quiz '{quiz_id}' non trovato nel corso '{course_id}'.")

            wrong_q_ids: list[str] = []
            wrong_topics: list[str] = []
            question_feedback: list[CourseQuizQuestionFeedback] = []
            correct = 0
            ordered_questions = sorted(quiz.questions, key=lambda q: q.order_index)
            total = len(ordered_questions)

            for qq in ordered_questions:
                given = str(answers.get(qq.id) or "").strip()
                expected = qq.correct_answer.strip()
                is_ok = given.lower() == expected.lower()
                if is_ok:
                    correct += 1
                else:
                    wrong_q_ids.append(qq.id)
                    raw_topic = qq.source_section.split(">")[-1].strip() if qq.source_section else course.title
                    topic_label = raw_topic.rstrip("?").strip() or course.title
                    if topic_label and topic_label not in wrong_topics:
                        wrong_topics.append(topic_label)
                question_feedback.append(
                    CourseQuizQuestionFeedback(
                        question_id=qq.id,
                        question_text=qq.question_text,
                        user_answer=given,
                        is_correct=is_ok,
                        correct_answer=expected,
                        explanation=qq.explanation or "",
                        source_section=qq.source_section or "",
                    )
                )

            pct = round((correct / total) * 100.0, 2) if total > 0 else 0.0
            passed = pct >= float(quiz.passing_score)
            now = datetime.now(timezone.utc)
            attempt_id = f"cqa_{uuid.uuid4().hex[:12]}"
            attempt = CourseQuizAttempt(
                id=attempt_id,
                quiz_id=quiz_id,
                course_id=course_id,
                tenant_id=tenant_id,
                user_id=user_id,
                answers=answers,
                wrong_question_ids=wrong_q_ids,
                wrong_topics=wrong_topics,
                correct_count=correct,
                total_questions=total,
                score=float(correct),
                percentage=pct,
                passed=passed,
                completed_at=now,
            )
            db.add(attempt)
            db.commit()

        updated_gaps = self.gap_detector.analyze_user_gaps(user_id, tenant_id=tenant_id)
        self.profiler.refresh_user_profile(user_id, tenant_id=tenant_id)
        self.db.bump_owner_metrics_version(tenant_id)
        return CourseQuizSubmitResponse(
            attempt_id=attempt_id,
            quiz_id=quiz_id,
            course_id=course_id,
            user_id=user_id,
            correct_count=correct,
            total_questions=total,
            percentage=pct,
            passed=passed,
            wrong_topics=wrong_topics,
            question_feedback=question_feedback,
            gaps_updated=len(updated_gaps),
            completed_at=now,
        )

    def generate_custom_quiz(
        self,
        *,
        tenant_id: str = "default",
        user_id: str,
        num_questions: int = 4,
        software: str | None = None,
        module_name: str | None = None,
        focus_topic: str | None = None,
        force_new: bool = False,
        run_async: bool = False,
    ) -> CustomQuizResponse:
        # Analyze latest gaps & refresh profile before building personalized plan
        self.gap_detector.analyze_user_gaps(
            user_id,
            tenant_id=tenant_id,
            software_filter=software,
            module_filter=module_name,
        )
        self.profiler.refresh_user_profile(user_id, tenant_id=tenant_id)

        plan = self.personalizer.build_target_plan(
            user_id=user_id,
            tenant_id=tenant_id,
            software=software,
            module_name=module_name,
            focus_topic=focus_topic,
        )
        quiz = self.quiz_gen.generate_quiz(
            tenant_id=tenant_id,
            user_id=user_id,
            plan=plan,
            num_questions=num_questions,
            software=software,
            module_name=module_name,
            force_new=force_new,
            run_async=run_async,
        )
        return self._serialize_quiz(quiz)

    def get_quiz(self, quiz_id: str, *, tenant_id: str, user_id: str | None = None) -> CustomQuizResponse | None:
        with self.db.session() as db:
            q = (
                db.query(CustomQuiz)
                .options(joinedload(CustomQuiz.questions))
                .filter(CustomQuiz.id == quiz_id, CustomQuiz.tenant_id == tenant_id)
            )
            if user_id is not None:
                q = q.filter(CustomQuiz.user_id == user_id)
            quiz = q.first()
            return self._serialize_quiz(quiz) if quiz else None

    def list_user_quizzes(self, user_id: str, *, tenant_id: str = "default") -> list[CustomQuizResponse]:
        with self.db.session() as db:
            rows = (
                db.query(CustomQuiz)
                .options(joinedload(CustomQuiz.questions))
                .filter(CustomQuiz.tenant_id == tenant_id, CustomQuiz.user_id == user_id)
                .order_by(CustomQuiz.generated_at.desc())
                .all()
            )
            return [self._serialize_quiz(r) for r in rows]

    def _find_recommended_lessons(
        self,
        *,
        tenant_id: str,
        topics_to_improve: list[str],
    ) -> list[RecommendedLessonItem]:
        """Match weak topics against existing Academy Courses & Lessons for targeted study hints."""
        if not topics_to_improve:
            return []
        recs: list[RecommendedLessonItem] = []
        with self.db.session() as db:
            courses = (
                db.query(Course)
                .options(joinedload(Course.modules).joinedload(CourseModule.lessons))
                .filter(Course.tenant_id == tenant_id)
                .order_by(Course.created_at.desc())
                .limit(20)
                .all()
            )
        for weak in topics_to_improve:
            weak_tokens = {tok for tok in weak.lower().split() if len(tok) > 3}
            matched = False
            for c in courses:
                for mod in c.modules:
                    for les in mod.lessons:
                        hay = f"{c.title} {les.title} {les.objective}".lower()
                        if weak.lower() in hay or (weak_tokens and any(tok in hay for tok in weak_tokens)):
                            recs.append(
                                RecommendedLessonItem(
                                    course_id=c.id,
                                    course_title=c.title,
                                    lesson_id=les.id,
                                    lesson_title=les.title,
                                    topic=weak,
                                    reason=f"Approfondimento consigliato su '{les.title}' nel corso '{c.title}'.",
                                )
                            )
                            matched = True
                            break
                    if matched:
                        break
                if matched:
                    break
        return recs[:5]

    def submit_custom_quiz(
        self,
        *,
        quiz_id: str,
        tenant_id: str = "default",
        user_id: str,
        answers: dict[str, str],
        duration_seconds: int = 60,
        completed_at: datetime | None = None,
    ) -> CustomQuizResultResponse:
        now = completed_at or datetime.now(timezone.utc)
        with self.db.session() as db:
            quiz = (
                db.query(CustomQuiz)
                .options(joinedload(CustomQuiz.questions))
                .filter(CustomQuiz.id == quiz_id, CustomQuiz.tenant_id == tenant_id, CustomQuiz.user_id == user_id)
                .first()
            )
            if quiz is None:
                raise ValueError(f"Custom Quiz '{quiz_id}' non trovato per l'utente '{user_id}'.")
            if quiz.status != "READY" and quiz.status != "COMPLETED":
                raise ValueError(f"Custom Quiz '{quiz_id}' non è pronto (stato attuale: {quiz.status}).")

            feedback_items: list[QuestionFeedbackItem] = []
            question_outcomes: list[dict[str, Any]] = []
            per_topic_stats: dict[str, tuple[int, int]] = {}
            correct_count = 0

            for q in quiz.questions:
                raw_ans = str(answers.get(q.id) or "").strip()
                # Accept either option letter ("A".."D") or exact option text
                chosen_letter = raw_ans.upper() if raw_ans.upper() in ("A", "B", "C", "D") else ""
                if not chosen_letter:
                    for opt in q.options:
                        if opt["text"].strip().lower() == raw_ans.lower():
                            chosen_letter = opt["id"]
                            break

                is_ok = (chosen_letter == q.correct_option_id) or (raw_ans.lower() == q.correct_answer.strip().lower())
                if is_ok:
                    correct_count += 1

                ok_c, err_c = per_topic_stats.get(q.topic, (0, 0))
                per_topic_stats[q.topic] = (ok_c + (1 if is_ok else 0), err_c + (0 if is_ok else 1))

                feedback_items.append(
                    QuestionFeedbackItem(
                        question_id=q.id,
                        topic=q.topic,
                        user_answer=chosen_letter or raw_ans or "(nessuna risposta)",
                        is_correct=is_ok,
                        correct_option_id=q.correct_option_id,
                        correct_answer=q.correct_answer,
                        explanation=q.explanation,
                        sources=list(q.sources or []),
                    )
                )
                question_outcomes.append(
                    {
                        "question_id": q.id,
                        "question_hash": q.question_hash,
                        "topic": q.topic,
                        "software": quiz.software,
                        "module_name": quiz.module_name,
                        "is_correct": is_ok,
                    }
                )

            total_q = len(quiz.questions)
            pct = round((correct_count / total_q) * 100.0, 2) if total_q > 0 else 0.0
            outcome = "PASSED" if pct >= 75.0 else ("IMPROVING" if pct >= 50.0 else "NEEDS_PRACTICE")

            topics_understood = [t for t, (ok, err) in per_topic_stats.items() if ok > 0 and err == 0]
            topics_to_improve = [t for t, (_, err) in per_topic_stats.items() if err > 0]

        recommended_lessons = self._find_recommended_lessons(
            tenant_id=tenant_id,
            topics_to_improve=topics_to_improve,
        )
        updated_gaps = self.gap_detector.update_gaps_from_custom_quiz(
            tenant_id=tenant_id,
            user_id=user_id,
            question_outcomes=question_outcomes,
            completed_at=now,
        )

        attempt_id = f"cqa_{uuid.uuid4().hex[:12]}"
        payload_feedback = {
            "topics_understood": topics_understood,
            "topics_to_improve": topics_to_improve,
            "question_feedback": [f.model_dump() for f in feedback_items],
            "recommended_lessons": [r.model_dump() for r in recommended_lessons],
            "updated_gaps": updated_gaps,
        }

        with self.db.session() as db:
            quiz_row = db.get(CustomQuiz, quiz_id)
            assert quiz_row is not None
            quiz_row.status = "COMPLETED"
            quiz_row.completed_at = now

            att = CustomQuizAttempt(
                id=attempt_id,
                quiz_id=quiz_id,
                tenant_id=tenant_id,
                user_id=user_id,
                answers=answers,
                correct_count=correct_count,
                total_questions=total_q,
                score=float(correct_count),
                percentage=pct,
                duration_seconds=duration_seconds,
                outcome=outcome,
                feedback=payload_feedback,
                completed_at=now,
            )
            db.add(att)
            db.commit()

        self.profiler.refresh_user_profile(user_id, tenant_id=tenant_id)
        self.db.bump_owner_metrics_version(tenant_id)
        return CustomQuizResultResponse(
            attempt_id=attempt_id,
            quiz_id=quiz_id,
            user_id=user_id,
            correct_count=correct_count,
            total_questions=total_q,
            score=float(correct_count),
            percentage=pct,
            duration_seconds=duration_seconds,
            outcome=outcome,
            topics_understood=topics_understood,
            topics_to_improve=topics_to_improve,
            question_feedback=feedback_items,
            recommended_lessons=recommended_lessons,
            updated_gaps=updated_gaps,
            completed_at=now,
        )

    def get_quiz_results(self, quiz_id: str, *, tenant_id: str, user_id: str) -> CustomQuizResultResponse:
        with self.db.session() as db:
            att = (
                db.query(CustomQuizAttempt)
                .filter_by(quiz_id=quiz_id, tenant_id=tenant_id, user_id=user_id)
                .order_by(CustomQuizAttempt.completed_at.desc())
                .first()
            )
            if att is None:
                raise ValueError(f"Nessun risultato completato trovato per il Custom Quiz '{quiz_id}'.")
            fb = att.feedback or {}
            return CustomQuizResultResponse(
                attempt_id=att.id,
                quiz_id=att.quiz_id,
                user_id=att.user_id,
                correct_count=att.correct_count,
                total_questions=att.total_questions,
                score=att.score,
                percentage=att.percentage,
                duration_seconds=att.duration_seconds,
                outcome=att.outcome,
                topics_understood=list(fb.get("topics_understood") or []),
                topics_to_improve=list(fb.get("topics_to_improve") or []),
                question_feedback=[QuestionFeedbackItem(**item) for item in fb.get("question_feedback") or []],
                recommended_lessons=[RecommendedLessonItem(**r) for r in fb.get("recommended_lessons") or []],
                updated_gaps=list(fb.get("updated_gaps") or []),
                completed_at=att.completed_at,
            )

    def get_user_learning_profile(self, user_id: str, *, tenant_id: str = "default") -> UserLearningProfileResponse:
        profiles = self.profiler.refresh_user_profile(user_id, tenant_id=tenant_id)
        with self.db.session() as db:
            open_gaps = (
                db.query(LearningGap)
                .filter(
                    LearningGap.tenant_id == tenant_id,
                    LearningGap.user_id == user_id,
                    LearningGap.status != "RESOLVED",
                )
                .all()
            )

        softwares = sorted({p.software for p in profiles if p.software})
        modules = sorted({p.module_name for p in profiles if p.module_name})
        known = [p.topic for p in profiles if p.learning_stage in ("COMPETENZA_CONSOLIDATA", "MIGLIORAMENTO_VERIFICATO")]
        difficulty = [p.topic for p in profiles if p.learning_stage == "LACUNA_INDIVIDUATA" or p.error_count > 0]
        frequent_qs = list(dict.fromkeys(q for p in profiles for q in (p.frequent_questions or [])))[:15]

        return UserLearningProfileResponse(
            user_id=user_id,
            tenant_id=tenant_id,
            softwares_used=softwares,
            modules_used=modules,
            known_topics=known,
            difficulty_topics=difficulty,
            frequent_questions=frequent_qs,
            topic_profiles=[
                TopicProfileItem(
                    topic=p.topic,
                    software=p.software,
                    module_name=p.module_name,
                    estimated_level=p.estimated_level,
                    learning_stage=p.learning_stage,
                    rag_query_count=p.rag_query_count,
                    troubleshooting_count=p.troubleshooting_count,
                    verification_count=p.verification_count,
                    correct_count=p.correct_count,
                    error_count=p.error_count,
                    frequent_questions=list(p.frequent_questions or []),
                    quiz_errors_summary=list(p.quiz_errors_summary or []),
                    custom_quiz_history=list(p.custom_quiz_history or []),
                    last_verified_at=p.last_verified_at,
                )
                for p in profiles
            ],
            open_gaps=[self._serialize_gap(g) for g in open_gaps],
        )

    def delete_user_learning_data(self, user_id: str, *, tenant_id: str = "default") -> dict[str, int]:
        """GDPR-oriented deletion of all individual profile, gap, attempt, and custom quiz records."""
        with self.db.session() as db:
            c_attempts = db.query(CustomQuizAttempt).filter_by(tenant_id=tenant_id, user_id=user_id).delete()
            c_quizzes = db.query(CustomQuiz).filter_by(tenant_id=tenant_id, user_id=user_id).delete()
            c_gaps = db.query(LearningGap).filter_by(tenant_id=tenant_id, user_id=user_id).delete()
            c_profs = db.query(UserKnowledgeProfile).filter_by(tenant_id=tenant_id, user_id=user_id).delete()
            c_course_att = db.query(CourseQuizAttempt).filter_by(tenant_id=tenant_id, user_id=user_id).delete()
            c_hist = db.query(QueryHistory).filter_by(user_id=user_id).delete()
            db.commit()
        self.db.bump_owner_metrics_version(tenant_id)
        return {
            "custom_quiz_attempts": c_attempts,
            "custom_quizzes": c_quizzes,
            "learning_gaps": c_gaps,
            "knowledge_profiles": c_profs,
            "course_quiz_attempts": c_course_att,
            "rag_query_history": c_hist,
        }
