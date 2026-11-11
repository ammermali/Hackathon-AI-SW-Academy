"""Longitudinal learning metrics engine measuring knowledge acquisition over time."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import joinedload

from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import CustomQuizAttempt, LearningGap, UserKnowledgeProfile
from operator_copilot.schemas.customquiz import LearningMetricsResponse


class LearningMetricsService:
    """Computes longitudinal learning effectiveness indicators with flexible filtering."""

    def __init__(self, db_manager: DatabaseManager | None = None) -> None:
        self.db = db_manager or get_db_manager()

    def compute_metrics(
        self,
        *,
        user_id: str,
        tenant_id: str = "default",
        topic: str | None = None,
        software: str | None = None,
        module_name: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> LearningMetricsResponse:
        """Compute Accuracy, Improvement, Gap Resolution Rate, Retention Rate, Repeated Error Rate, and Progress."""
        with self.db.session() as db:
            attempts_q = (
                db.query(CustomQuizAttempt)
                .options(joinedload(CustomQuizAttempt.quiz))
                .filter(CustomQuizAttempt.tenant_id == tenant_id, CustomQuizAttempt.user_id == user_id)
            )
            if date_from is not None:
                attempts_q = attempts_q.filter(CustomQuizAttempt.completed_at >= date_from)
            if date_to is not None:
                attempts_q = attempts_q.filter(CustomQuizAttempt.completed_at <= date_to)

            all_attempts = attempts_q.order_by(CustomQuizAttempt.completed_at.asc()).all()

            gaps_q = db.query(LearningGap).filter(LearningGap.tenant_id == tenant_id, LearningGap.user_id == user_id)
            if topic:
                gaps_q = gaps_q.filter(LearningGap.topic.ilike(f"%{topic}%"))
            if software:
                gaps_q = gaps_q.filter(LearningGap.software.ilike(f"%{software}%"))
            if module_name:
                gaps_q = gaps_q.filter(LearningGap.module_name.ilike(f"%{module_name}%"))
            gaps = gaps_q.all()

            prof_q = db.query(UserKnowledgeProfile).filter(
                UserKnowledgeProfile.tenant_id == tenant_id, UserKnowledgeProfile.user_id == user_id
            )
            if topic:
                prof_q = prof_q.filter(UserKnowledgeProfile.topic.ilike(f"%{topic}%"))
            if software:
                prof_q = prof_q.filter(UserKnowledgeProfile.software.ilike(f"%{software}%"))
            if module_name:
                prof_q = prof_q.filter(UserKnowledgeProfile.module_name.ilike(f"%{module_name}%"))
            profiles = prof_q.all()

        # Filter attempts by software / module / topic if requested
        filtered_items: list[tuple[CustomQuizAttempt, dict[str, Any]]] = []
        per_topic_scores: dict[str, list[tuple[datetime, float]]] = defaultdict(list)

        total_correct = 0
        total_questions = 0
        repeated_errors = 0
        error_total = 0
        seen_wrong_topics: set[str] = set()

        for att in all_attempts:
            quiz = att.quiz
            if software and (not quiz or software.lower() not in quiz.software.lower()):
                continue
            if module_name and (not quiz or module_name.lower() not in quiz.module_name.lower()):
                continue

            q_fbs = (att.feedback or {}).get("question_feedback", [])
            matching_fbs = [
                qf for qf in q_fbs
                if not topic or topic.lower() in str(qf.get("topic") or "").lower()
            ]
            if topic and not matching_fbs:
                continue

            filtered_items.append((att, {"matching_fbs": matching_fbs}))
            by_t: dict[str, list[bool]] = defaultdict(list)
            for qf in matching_fbs:
                t_name = str(qf.get("topic") or "Operatività generale")
                is_ok = bool(qf.get("is_correct"))
                total_questions += 1
                if is_ok:
                    total_correct += 1
                else:
                    error_total += 1
                    if t_name in seen_wrong_topics:
                        repeated_errors += 1
                    seen_wrong_topics.add(t_name)
                by_t[t_name].append(is_ok)

            for t_name, bools in by_t.items():
                pct = round(100.0 * sum(1 for b in bools if b) / len(bools), 2)
                per_topic_scores[t_name].append((att.completed_at, pct))

        # A. Quiz Accuracy (%)
        quiz_accuracy = round((total_correct / total_questions) * 100.0, 2) if total_questions > 0 else 0.0

        # B. Learning Improvement (latest vs earlier score across same topics)
        improvements: list[float] = []
        retention_checks = 0
        retained_ok = 0
        evolution_list: list[dict[str, Any]] = []

        for t_name, series in per_topic_scores.items():
            scores_only = [s for _, s in series]
            delta = round(scores_only[-1] - scores_only[0], 2) if len(scores_only) >= 2 else None
            if delta is not None:
                improvements.append(delta)
            # Retention: when topic reached >= 70% earlier and was re-tested later
            for i in range(len(scores_only) - 1):
                if scores_only[i] >= 70.0:
                    retention_checks += 1
                    if scores_only[i + 1] >= 70.0:
                        retained_ok += 1
            evolution_list.append(
                {
                    "topic": t_name,
                    "attempts": len(series),
                    "first_score": scores_only[0],
                    "latest_score": scores_only[-1],
                    "delta": delta,
                }
            )

        learning_improvement = round(sum(improvements) / len(improvements), 2) if improvements else None
        retention_rate = round((retained_ok / retention_checks) * 100.0, 2) if retention_checks > 0 else None

        # C. Knowledge Gap Resolution Rate (%)
        gap_counts = {"OPEN": 0, "IN_PROGRESS": 0, "IMPROVING": 0, "RESOLVED": 0}
        for g in gaps:
            gap_counts[g.status] = gap_counts.get(g.status, 0) + 1
        total_gaps = len(gaps)
        resolution_rate = round((gap_counts["RESOLVED"] / total_gaps) * 100.0, 2) if total_gaps > 0 else 0.0

        # E. Repeated Error Rate (%)
        repeated_error_rate = round((repeated_errors / max(1, total_questions)) * 100.0, 2) if total_questions > 0 else 0.0

        # F. Learning Progress & Stages
        stages_summary = {
            "LACUNA_INDIVIDUATA": 0,
            "APPRENDIMENTO_IN_CORSO": 0,
            "MIGLIORAMENTO_VERIFICATO": 0,
            "COMPETENZA_CONSOLIDATA": 0,
        }
        for p in profiles:
            stages_summary[p.learning_stage] = stages_summary.get(p.learning_stage, 0) + 1

        if profiles:
            avg_level = sum(p.estimated_level for p in profiles) / len(profiles)
            learning_progress = round(min(100.0, max(0.0, avg_level * 100.0)), 2)
        else:
            learning_progress = round(quiz_accuracy, 2)

        return LearningMetricsResponse(
            user_id=user_id,
            tenant_id=tenant_id,
            filters={
                "topic": topic,
                "software": software,
                "module_name": module_name,
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            },
            quiz_accuracy=quiz_accuracy,
            learning_improvement=learning_improvement,
            knowledge_gap_resolution_rate=resolution_rate,
            retention_rate=retention_rate,
            repeated_error_rate=repeated_error_rate,
            learning_progress=learning_progress,
            attempts_count=len(filtered_items),
            gaps_summary=gap_counts,
            learning_stages_summary=stages_summary,
            per_topic_evolution=evolution_list,
        )
