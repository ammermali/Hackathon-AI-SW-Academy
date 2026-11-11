"""Learning Gap Detection tracking RAG friction, quiz errors, and longitudinal resolution."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from operator_copilot.adaptive_learning.profiler import (
    extract_canonical_topic,
    infer_software_and_module,
    is_difficulty_rag_signal,
)
from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import (
    CourseQuizAttempt,
    CustomQuizAttempt,
    LearningGap,
    QueryFeedback,
    QueryHistory,
)


class LearningGapDetector:
    """Identifies, scores, and updates individual user LearningGap lifecycle states."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)

    def analyze_user_gaps(
        self,
        user_id: str,
        *,
        tenant_id: str = "default",
        software_filter: str | None = None,
        module_filter: str | None = None,
    ) -> list[LearningGap]:
        """Inspect RAG history, negative feedback, course quiz errors, and custom quiz outcomes."""
        now = datetime.now(timezone.utc)

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

            topic_signals: dict[str, dict[str, Any]] = defaultdict(
                lambda: {
                    "evidences": [],
                    "sources": set(),
                    "software": "Cityware / CWOL",
                    "module_name": "Generale",
                    "severity_points": 0,
                    "error_count": 0,
                }
            )

            # A. RAG signals: only repeated queries (>=2 same topic + trouble/clarification or escalation or feedback<=2)
            rag_by_topic: dict[str, list[QueryHistory]] = defaultdict(list)
            for row in rag_rows:
                rag_by_topic[extract_canonical_topic(row)].append(row)

            for topic, rows in rag_by_topic.items():
                trouble_rows = [r for r in rows if is_difficulty_rag_signal(r, len(rows), neg_fb_ids)]
                # Normal isolated curiosity queries without friction do NOT generate gaps
                if len(trouble_rows) >= 1 and (len(rows) >= 2 or any(r.needs_escalation or r.id in neg_fb_ids for r in trouble_rows)):
                    sig = topic_signals[topic]
                    sample = trouble_rows[-1]
                    sw, mod = infer_software_and_module(sample.query, sample.sources, topic)
                    sig["software"] = sw
                    sig["module_name"] = mod
                    sig["severity_points"] += min(3, len(trouble_rows))
                    sig["evidences"].append(
                        {
                            "type": "rag_history",
                            "query_count": len(rows),
                            "friction_count": len(trouble_rows),
                            "sample_queries": [r.query for r in rows[-3:]],
                        }
                    )
                    for r in rows:
                        for src in r.sources or []:
                            if isinstance(src, dict) and src.get("document"):
                                sig["sources"].add(str(src["document"]))

            # B. Traditional course quiz errors (strong evidence of missing skill)
            for ca in course_attempts:
                if ca.wrong_question_ids or ca.wrong_topics:
                    targets = list(dict.fromkeys(ca.wrong_topics or ["Competenze corso"]))
                    for topic in targets:
                        sig = topic_signals[topic]
                        err_n = max(1, len(ca.wrong_question_ids))
                        sig["error_count"] += err_n
                        sig["severity_points"] += 2 * err_n
                        sig["evidences"].append(
                            {
                                "type": "course_quiz_error",
                                "quiz_id": ca.quiz_id,
                                "course_id": ca.course_id,
                                "wrong_questions": ca.wrong_question_ids,
                                "percentage": ca.percentage,
                                "completed_at": ca.completed_at.isoformat(),
                            }
                        )
                        sig["sources"].add(f"course_quiz:{ca.quiz_id}")

            # C. Custom Quiz errors that persisted
            for cqa in custom_attempts:
                for qf in (cqa.feedback or {}).get("question_feedback", []):
                    if not qf.get("is_correct"):
                        topic = str(qf.get("topic") or "Operatività generale")
                        sig = topic_signals[topic]
                        sig["error_count"] += 1
                        sig["severity_points"] += 2
                        sig["evidences"].append(
                            {
                                "type": "custom_quiz_error",
                                "quiz_id": cqa.quiz_id,
                                "question_id": qf.get("question_id"),
                                "completed_at": cqa.completed_at.isoformat(),
                            }
                        )
                        sig["sources"].add(f"custom_quiz:{cqa.quiz_id}")

            existing_gaps = {
                g.topic: g
                for g in db.query(LearningGap)
                .filter(LearningGap.user_id == user_id, LearningGap.tenant_id == tenant_id)
                .all()
            }

            result: list[LearningGap] = []
            for topic, sig in topic_signals.items():
                if software_filter and software_filter.lower() not in sig["software"].lower():
                    continue
                if module_filter and module_filter.lower() not in sig["module_name"].lower():
                    continue

                pts = sig["severity_points"]
                priority = "high" if pts >= 4 or sig["error_count"] >= 2 else ("medium" if pts >= 2 else "low")
                confidence = round(min(0.96, 0.45 + 0.12 * pts), 2)

                gap = existing_gaps.get(topic)
                if gap is None:
                    gap = LearningGap(
                        id=f"lgap_{uuid.uuid4().hex[:12]}",
                        tenant_id=tenant_id,
                        user_id=user_id,
                        topic=topic,
                        software=sig["software"],
                        module_name=sig["module_name"],
                        evidences=sig["evidences"][-10:],
                        evidence_sources=sorted(sig["sources"])[:10],
                        priority=priority,
                        confidence=confidence,
                        status="OPEN",
                        repeated_error_count=max(0, sig["error_count"] - 1),
                        detected_at=now,
                    )
                    db.add(gap)
                else:
                    gap.software = sig["software"]
                    gap.module_name = sig["module_name"]
                    gap.evidences = sig["evidences"][-10:]
                    gap.evidence_sources = sorted(set(gap.evidence_sources) | sig["sources"])[:10]
                    gap.priority = priority
                    gap.confidence = max(gap.confidence, confidence)
                    gap.repeated_error_count = max(gap.repeated_error_count, max(0, sig["error_count"] - 1))
                    # Reopen if new errors occurred after earlier resolution
                    if gap.status == "RESOLVED" and any(e["type"] == "custom_quiz_error" for e in sig["evidences"]):
                        # Keep RESOLVED unless error happened AFTER resolved_at
                        resolved_naive = gap.resolved_at.replace(tzinfo=None) if gap.resolved_at else None
                        if resolved_naive and any(
                            datetime.fromisoformat(e["completed_at"]).replace(tzinfo=None) > resolved_naive
                            for e in sig["evidences"]
                            if "completed_at" in e
                        ):
                            gap.status = "IN_PROGRESS"
                            gap.resolved_at = None
                result.append(gap)

            # Include previously detected gaps that did not receive new friction signals in this scan
            seen_topics = {g.topic for g in result}
            for t, g in existing_gaps.items():
                if t not in seen_topics:
                    if software_filter and software_filter.lower() not in g.software.lower():
                        continue
                    if module_filter and module_filter.lower() not in g.module_name.lower():
                        continue
                    result.append(g)

            db.commit()
            for g in result:
                db.refresh(g)
            return result

    def update_gaps_from_custom_quiz(
        self,
        *,
        tenant_id: str,
        user_id: str,
        question_outcomes: list[dict[str, Any]],
        completed_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Transition LearningGap states based on longitudinal performance & variant questions."""
        ts = completed_at or datetime.now(timezone.utc)
        min_hours = self.settings.learning_retention_min_hours

        per_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in question_outcomes:
            per_topic[str(item.get("topic") or "Operatività generale")].append(item)

        updates: list[dict[str, Any]] = []
        with self.db.session() as db:
            gaps = {
                g.topic: g
                for g in db.query(LearningGap)
                .filter(LearningGap.tenant_id == tenant_id, LearningGap.user_id == user_id)
                .all()
            }

            for topic, outcomes in per_topic.items():
                gap = gaps.get(topic)
                if gap is None:
                    # Only create gap automatically if the user made errors on a topic without prior gap
                    errors_here = [o for o in outcomes if not o["is_correct"]]
                    if not errors_here:
                        continue
                    gap = LearningGap(
                        id=f"lgap_{uuid.uuid4().hex[:12]}",
                        tenant_id=tenant_id,
                        user_id=user_id,
                        topic=topic,
                        software=str(errors_here[0].get("software") or "Cityware / CWOL"),
                        module_name=str(errors_here[0].get("module_name") or topic),
                        evidences=[{"type": "custom_quiz_error", "completed_at": ts.isoformat()}],
                        evidence_sources=[],
                        priority="medium",
                        confidence=0.70,
                        status="OPEN",
                        detected_at=ts,
                    )
                    db.add(gap)
                    gaps[topic] = gap

                prev_status = gap.status
                total = len(outcomes)
                correct = sum(1 for o in outcomes if o["is_correct"])
                accuracy = correct / max(1, total)

                prev_hashes = set(gap.asked_question_hashes or [])
                new_hashes = [str(o.get("question_hash") or "") for o in outcomes if o.get("question_hash")]
                used_different_questions = any(h not in prev_hashes for h in new_hashes) or len(prev_hashes) == 0
                gap.asked_question_hashes = list(dict.fromkeys((gap.asked_question_hashes or []) + new_hashes))[-30:]

                ts_utc = ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
                if gap.last_verified_at is not None:
                    last_utc = (
                        gap.last_verified_at.astimezone(timezone.utc)
                        if gap.last_verified_at.tzinfo
                        else gap.last_verified_at.replace(tzinfo=timezone.utc)
                    )
                    hours_since_last = (ts_utc - last_utc).total_seconds() / 3600.0
                else:
                    hours_since_last = 0.0

                if accuracy < 0.70:
                    gap.repeated_error_count += (total - correct)
                    gap.status = "IN_PROGRESS" if prev_status in ("OPEN", "IN_PROGRESS") else "OPEN"
                    gap.positive_verifications = 0
                else:
                    gap.positive_verifications += 1
                    if prev_status in ("OPEN", "IN_PROGRESS") and gap.positive_verifications < 2:
                        # Require a second positive verification later before declaring RESOLVED
                        gap.status = "IMPROVING"
                    elif gap.positive_verifications >= 2 and used_different_questions and hours_since_last >= min_hours:
                        gap.status = "RESOLVED"
                        gap.resolved_at = ts
                    else:
                        gap.status = "IMPROVING"

                gap.last_verified_at = ts
                updates.append(
                    {
                        "gap_id": gap.id,
                        "topic": gap.topic,
                        "previous_status": prev_status,
                        "new_status": gap.status,
                        "positive_verifications": gap.positive_verifications,
                        "accuracy": round(accuracy * 100.0, 2),
                    }
                )

            db.commit()
        return updates
