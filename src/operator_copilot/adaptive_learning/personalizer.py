"""Personalization Engine selecting priority topics and avoiding identical repeated questions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import joinedload

from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import CustomQuiz, LearningGap, UserKnowledgeProfile


class PersonalizationEngine:
    """Ranks target topics for Custom Quiz generation based on unresolved gaps, repeated errors, and recency."""

    def __init__(self, db_manager: DatabaseManager | None = None) -> None:
        self.db = db_manager or get_db_manager()

    def build_target_plan(
        self,
        *,
        user_id: str,
        tenant_id: str = "default",
        software: str | None = None,
        module_name: str | None = None,
        focus_topic: str | None = None,
        max_topics: int = 3,
    ) -> dict[str, Any]:
        """Select prioritized topics, gap references, estimated user level, and already-asked question hashes."""
        now = datetime.now(timezone.utc)
        with self.db.session() as db:
            gaps = (
                db.query(LearningGap)
                .filter(LearningGap.user_id == user_id, LearningGap.tenant_id == tenant_id)
                .all()
            )
            profiles = (
                db.query(UserKnowledgeProfile)
                .filter(UserKnowledgeProfile.user_id == user_id, UserKnowledgeProfile.tenant_id == tenant_id)
                .all()
            )
            prior_quizzes = (
                db.query(CustomQuiz)
                .options(joinedload(CustomQuiz.questions))
                .filter(CustomQuiz.user_id == user_id, CustomQuiz.tenant_id == tenant_id)
                .order_by(CustomQuiz.generated_at.desc())
                .limit(10)
                .all()
            )
            previous_hashes: set[str] = set()
            previous_texts: list[str] = []
            for g in gaps:
                previous_hashes.update(g.asked_question_hashes or [])
            for cq in prior_quizzes:
                for q in cq.questions:
                    previous_hashes.add(q.question_hash)
                    previous_texts.append(q.question_text)

        prof_by_topic = {p.topic: p for p in profiles}

        scored_candidates: list[tuple[float, dict[str, Any]]] = []

        # 1. Score unresolved & improving gaps highest
        for g in gaps:
            if software and software.lower() not in g.software.lower():
                continue
            if module_name and module_name.lower() not in g.module_name.lower():
                continue
            if focus_topic and focus_topic.lower() not in g.topic.lower():
                continue

            prof = prof_by_topic.get(g.topic)
            days_since = (
                (now - g.last_verified_at.replace(tzinfo=timezone.utc if g.last_verified_at.tzinfo is None else g.last_verified_at.tzinfo)).total_seconds() / 86400.0
                if g.last_verified_at
                else 7.0
            )
            status_weight = {"OPEN": 40.0, "IN_PROGRESS": 35.0, "IMPROVING": 28.0, "RESOLVED": 5.0}.get(g.status, 20.0)
            prio_weight = {"high": 20.0, "medium": 12.0, "low": 5.0}.get(g.priority, 10.0)
            score = status_weight + prio_weight + 8.0 * g.repeated_error_count + min(15.0, days_since)
            if prof:
                score += min(10.0, prof.rag_query_count * 1.5)

            scored_candidates.append(
                (
                    score,
                    {
                        "topic": g.topic,
                        "software": g.software,
                        "module_name": g.module_name,
                        "gap_id": g.id,
                        "gap_status": g.status,
                        "estimated_level": prof.estimated_level if prof else 0.4,
                        "evidence_sources": g.evidence_sources,
                        "rag_queries": prof.frequent_questions if prof else [],
                    },
                )
            )

        # 2. Fallback/addition: operational topics from profile not yet in gaps
        gap_topics = {g.topic for g in gaps}
        for prof in profiles:
            if prof.topic in gap_topics:
                continue
            if software and software.lower() not in prof.software.lower():
                continue
            if module_name and module_name.lower() not in prof.module_name.lower():
                continue
            if focus_topic and focus_topic.lower() not in prof.topic.lower():
                continue
            score = 10.0 + min(15.0, prof.rag_query_count * 2.0) + 10.0 * prof.error_count
            scored_candidates.append(
                (
                    score,
                    {
                        "topic": prof.topic,
                        "software": prof.software,
                        "module_name": prof.module_name,
                        "gap_id": None,
                        "gap_status": None,
                        "estimated_level": prof.estimated_level,
                        "evidence_sources": [],
                        "rag_queries": prof.frequent_questions,
                    },
                )
            )

        # 3. Explicit focus_topic if caller targeted a specific subject with no history yet
        if focus_topic and not scored_candidates:
            scored_candidates.append(
                (
                    15.0,
                    {
                        "topic": focus_topic,
                        "software": software or "Cityware / CWOL",
                        "module_name": module_name or focus_topic,
                        "gap_id": None,
                        "gap_status": None,
                        "estimated_level": 0.5,
                        "evidence_sources": [],
                        "rag_queries": [],
                    },
                )
            )

        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        selected = [c for _, c in scored_candidates[:max_topics]]

        avg_level = round(
            sum(float(c["estimated_level"]) for c in selected) / max(1, len(selected)),
            2,
        )
        return {
            "targets": selected,
            "estimated_level": avg_level,
            "previous_question_hashes": previous_hashes,
            "previous_question_texts": previous_texts[:10],
            "attempt_iteration": len(prior_quizzes) + 1,
        }
