"""User Knowledge Profile management integrating RAG history and quiz outcomes."""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import (
    CourseQuizAttempt,
    CustomQuizAttempt,
    LearningGap,
    QueryFeedback,
    QueryHistory,
    UserKnowledgeProfile,
)

_SOFTWARE_HINTS: tuple[tuple[str, str], ...] = (
    ("cwol", "CWOL"),
    ("cityware", "Cityware Client"),
    ("otrs", "OTRS Ticketing"),
    ("siope", "SIOPE+"),
    ("pagopa", "PagoPA"),
    ("efil", "EFIL"),
    ("anpr", "ANPR"),
    ("ansc", "ANSC"),
)

_CLARIFICATION_MARKERS = (
    "non ho capito",
    "non capisco",
    "non riesco",
    "spiega",
    "chiarimento",
    "ancora errore",
    "di nuovo",
    "perché",
    "perche",
    "aiuto",
    "blocc",
)


def infer_software_and_module(text: str, sources: list[dict[str, Any]] | None = None, fallback_topic: str = "Generale") -> tuple[str, str]:
    """Infer primary software and applicative module strictly from text and retrieved source metadata."""
    blob = text.lower()
    area = ""
    if sources:
        for src in sources:
            if isinstance(src, dict):
                area = str(src.get("area") or area)
                blob += " " + str(src.get("document") or "") + " " + str(src.get("section") or "")
    blob_lower = blob.lower()

    software = "Cityware / CWOL"
    for needle, label in _SOFTWARE_HINTS:
        if needle in blob_lower:
            software = label
            break

    module_name = area.strip() if area.strip() else fallback_topic
    return software, module_name


def extract_canonical_topic(query_row: QueryHistory) -> str:
    """Derive specific operational topic from query metadata and document/section references."""
    norm = query_row.normalized_query or ""
    if query_row.sources:
        first = query_row.sources[0]
        if isinstance(first, dict):
            doc = str(first.get("document") or "")
            sec = str(first.get("section") or "")
            area = str(first.get("area") or "")
            if "assistenza" in doc.lower() or "ticket" in norm or "otrs" in norm:
                return "Richiesta assistenza e compilazione ticket"
            if sec:
                return sec.split(">")[-1].strip()[:120]
            if area:
                return area
    if query_row.topic:
        return query_row.topic
    if any(k in norm for k in ("ticket", "otrs", "assistenza")):
        return "Richiesta assistenza e compilazione ticket"
    if any(k in norm for k in ("siope", "pagopa", "iuv")):
        return "Gestione ordinativi SIOPE+ e PagoPA"
    words = [w for w in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", norm) if len(w) > 3]
    return " ".join(words[:4]).title() if words else "Operatività generale"


def is_difficulty_rag_signal(row: QueryHistory, repeated_topic_count: int, negative_feedback_ids: set[int]) -> bool:
    """Distinguish normal operational RAG usage from actual difficulty or clarification signals."""
    q_lower = row.query.lower()
    if row.id in negative_feedback_ids:
        return True
    if row.needs_escalation:
        return True
    if row.intent == "troubleshooting":
        return True
    if any(marker in q_lower for marker in _CLARIFICATION_MARKERS):
        return True
    # Repeated queries on same topic >= 3 within user's RAG usage also indicate friction
    return repeated_topic_count >= 3


class UserKnowledgeProfiler:
    """Builds and progressively updates individual UserKnowledgeProfile records in SQLite."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)

    @staticmethod
    def _compute_stage(
        *,
        correct_count: int,
        error_count: int,
        verification_count: int,
        has_open_gap: bool,
        gap_status: str | None,
    ) -> tuple[float, str]:
        """Estimate knowledge level (0..1) and stage without penalizing low activity."""
        if verification_count == 0 and error_count == 0:
            # Pure RAG usage without errors keeps neutral baseline
            stage = "LACUNA_INDIVIDUATA" if has_open_gap else "APPRENDIMENTO_IN_CORSO"
            return (0.45 if has_open_gap else 0.55), stage

        accuracy = correct_count / max(1, correct_count + error_count)
        level = round(max(0.10, min(0.98, 0.20 + 0.75 * accuracy)), 4)

        # Once LearningGapDetector promotes a gap to RESOLVED (2+ spaced positive verifications
        # with variant questions), the user's competence on this topic is consolidated even if
        # earlier exploratory attempts had errors.
        if gap_status == "RESOLVED" and verification_count >= 2:
            return max(level, 0.85), "COMPETENZA_CONSOLIDATA"
        if gap_status == "IMPROVING" or (accuracy >= 0.70 and verification_count >= 1 and error_count > 0):
            return level, "MIGLIORAMENTO_VERIFICATO"
        if has_open_gap or error_count > correct_count:
            return min(level, 0.50), "LACUNA_INDIVIDUATA"
        if accuracy >= 0.85 and verification_count >= 2:
            return level, "COMPETENZA_CONSOLIDATA"
        return level, "APPRENDIMENTO_IN_CORSO"

    def refresh_user_profile(
        self,
        user_id: str,
        *,
        tenant_id: str = "default",
    ) -> list[UserKnowledgeProfile]:
        """Recompute/update UserKnowledgeProfile rows from RAG history and quiz attempts."""
        with self.db.session() as db:
            rag_rows = (
                db.query(QueryHistory)
                .filter(QueryHistory.user_id == user_id)
                .order_by(QueryHistory.created_at.asc())
                .all()
            )
            neg_fb_ids = {
                fb.query_history_id
                for fb in db.query(QueryFeedback).filter(QueryFeedback.user_id == user_id, QueryFeedback.rating <= 2).all()
            }
            course_attempts = (
                db.query(CourseQuizAttempt)
                .filter(CourseQuizAttempt.user_id == user_id, CourseQuizAttempt.tenant_id == tenant_id)
                .order_by(CourseQuizAttempt.completed_at.asc())
                .all()
            )
            custom_attempts = (
                db.query(CustomQuizAttempt)
                .filter(CustomQuizAttempt.user_id == user_id, CustomQuizAttempt.tenant_id == tenant_id)
                .order_by(CustomQuizAttempt.completed_at.asc())
                .all()
            )
            gaps = (
                db.query(LearningGap)
                .filter(LearningGap.user_id == user_id, LearningGap.tenant_id == tenant_id)
                .all()
            )
            gap_by_topic = {g.topic: g for g in gaps}

            # Aggregate topic stats cleanly
            topic_queries: dict[str, list[QueryHistory]] = defaultdict(list)
            for r in rag_rows:
                topic_queries[extract_canonical_topic(r)].append(r)

            topic_stats: dict[str, dict[str, Any]] = {}

            def _ensure(topic_name: str) -> dict[str, Any]:
                if topic_name not in topic_stats:
                    topic_stats[topic_name] = {
                        "software": "Cityware / CWOL",
                        "module_name": "Generale",
                        "rag_count": 0,
                        "trouble_count": 0,
                        "verif_count": 0,
                        "correct": 0,
                        "errors": 0,
                        "questions": [],
                        "quiz_errors": [],
                        "cq_history": [],
                        "last_verified": None,
                    }
                return topic_stats[topic_name]

            for topic_name, rows in topic_queries.items():
                st = _ensure(topic_name)
                st["rag_count"] += len(rows)
                q_texts = [r.query for r in rows]
                top_qs = [q for q, _ in Counter(q_texts).most_common(5)]
                st["questions"] = top_qs
                for r in rows:
                    sw, mod = infer_software_and_module(r.query, r.sources, topic_name)
                    st["software"] = sw
                    st["module_name"] = mod
                    if is_difficulty_rag_signal(r, len(rows), neg_fb_ids):
                        st["trouble_count"] += 1

            for ca in course_attempts:
                wrong_set = list(dict.fromkeys(ca.wrong_topics or []))
                for wt in wrong_set:
                    st = _ensure(wt)
                    st["verif_count"] += 1
                    st["errors"] += 1
                    st["quiz_errors"].append(
                        {
                            "source": "course_quiz",
                            "attempt_id": ca.id,
                            "quiz_id": ca.quiz_id,
                            "wrong_question_ids": ca.wrong_question_ids,
                            "completed_at": ca.completed_at.isoformat(),
                        }
                    )
                    if st["last_verified"] is None or ca.completed_at > st["last_verified"]:
                        st["last_verified"] = ca.completed_at
                # Passed course quizzes without errors on topics already in profile
                if ca.passed and not wrong_set and ca.total_questions > 0:
                    for gap_t in gap_by_topic:
                        if gap_t in topic_stats:
                            topic_stats[gap_t]["verif_count"] += 1
                            topic_stats[gap_t]["correct"] += 1

            for cqa in custom_attempts:
                q_fb = (cqa.feedback or {}).get("question_feedback", [])
                per_topic_res: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
                for item in q_fb:
                    t = str(item.get("topic") or "Operatività generale")
                    ok, err = per_topic_res[t]
                    if item.get("is_correct"):
                        per_topic_res[t] = (ok + 1, err)
                    else:
                        per_topic_res[t] = (ok, err + 1)

                for t, (ok, err) in per_topic_res.items():
                    st = _ensure(t)
                    st["verif_count"] += 1
                    st["correct"] += ok
                    st["errors"] += err
                    st["cq_history"].append(
                        {
                            "attempt_id": cqa.id,
                            "quiz_id": cqa.quiz_id,
                            "correct": ok,
                            "errors": err,
                            "percentage": cqa.percentage,
                            "completed_at": cqa.completed_at.isoformat(),
                        }
                    )
                    if st["last_verified"] is None or cqa.completed_at > st["last_verified"]:
                        st["last_verified"] = cqa.completed_at

            # Also include topics tracked only as gaps so far
            for gap_topic, gap_obj in gap_by_topic.items():
                st = _ensure(gap_topic)
                if st["software"] == "Cityware / CWOL" and gap_obj.software:
                    st["software"] = gap_obj.software
                if st["module_name"] == "Generale" and gap_obj.module_name:
                    st["module_name"] = gap_obj.module_name

            existing_profiles = {
                p.topic: p
                for p in db.query(UserKnowledgeProfile)
                .filter(UserKnowledgeProfile.user_id == user_id, UserKnowledgeProfile.tenant_id == tenant_id)
                .all()
            }

            now = datetime.now(timezone.utc)
            saved_rows: list[UserKnowledgeProfile] = []
            for topic_name, st in topic_stats.items():
                gap_obj = gap_by_topic.get(topic_name)
                gap_status = gap_obj.status if gap_obj else None
                has_open = gap_status in ("OPEN", "IN_PROGRESS", "IMPROVING")
                est_lvl, stage = self._compute_stage(
                    correct_count=st["correct"],
                    error_count=st["errors"],
                    verification_count=st["verif_count"],
                    has_open_gap=has_open,
                    gap_status=gap_status,
                )

                row = existing_profiles.get(topic_name)
                if row is None:
                    row = UserKnowledgeProfile(
                        id=f"prof_{uuid.uuid4().hex[:12]}",
                        tenant_id=tenant_id,
                        user_id=user_id,
                        topic=topic_name,
                    )
                    db.add(row)

                row.software = st["software"]
                row.module_name = st["module_name"]
                row.estimated_level = est_lvl
                row.learning_stage = stage
                row.rag_query_count = st["rag_count"]
                row.troubleshooting_count = st["trouble_count"]
                row.verification_count = st["verif_count"]
                row.correct_count = st["correct"]
                row.error_count = st["errors"]
                row.frequent_questions = st["questions"]
                row.quiz_errors_summary = st["quiz_errors"][-10:]
                row.custom_quiz_history = st["cq_history"][-10:]
                row.last_verified_at = st["last_verified"]
                row.updated_at = now
                saved_rows.append(row)

            db.commit()
            for r in saved_rows:
                db.refresh(r)
            return saved_rows
