"""Owner Learning Analytics Service computing multi-tenant metrics, drill-downs, insights, and audit logs."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import func, select, union
from sqlalchemy.orm import Session, joinedload

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.course_generator.prompts import OWNER_INSIGHTS_PROMPT
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import (
    Course,
    CourseModule,
    CourseQuizAttempt,
    CustomQuiz,
    CustomQuizAttempt,
    LearningGap,
    LessonCompletion,
    OrganizationUser,
    OwnerAuditLog,
    UserKnowledgeProfile,
)
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.owner_dashboard.cache import OwnerMetricsCache
from operator_copilot.schemas.owner import (
    CourseProgressItem,
    OrganizationUserResponse,
    OwnerAuditLogItem,
    OwnerCustomQuizAnalyticsResponse,
    OwnerDashboardOverviewResponse,
    OwnerInsightItem,
    OwnerInsightsLLMOutput,
    OwnerInsightsResponse,
    OwnerTopicDrilldownResponse,
    OwnerTopicReviewItem,
    OwnerUserDetailResponse,
    OwnerUserGapDetailItem,
    OwnerUserLearningPerformance,
    OwnerUserOverviewItem,
    OwnerUsersPageResponse,
    TopicAffectedUserItem,
    TrendPoint,
    UserLearningHistoryEvent,
    UserQuizEvolutionPoint,
)


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    """Normalize datetimes for safe SQLite comparison and arithmetic."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _safe_avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _gap_criticality(priority: str, error_count: int) -> Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
    p = (priority or "").lower()
    if p == "high" and error_count >= 2:
        return "CRITICAL"
    if p == "high":
        return "HIGH"
    if p == "medium":
        return "MEDIUM"
    return "LOW"


class OwnerDashboardService:
    """Aggregates real DB learning metrics, drill-downs, and insights strictly within Owner scope."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
        generator: AnswerGenerator | None = None,
        cache: OwnerMetricsCache | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.generator = generator or AnswerGenerator(self.settings)
        self.cache = cache or OwnerMetricsCache(self.settings.owner_dashboard_cache_ttl_seconds)

    # ------------------------------------------------------------------
    # Audit & Organization Directory
    # ------------------------------------------------------------------

    def record_audit(
        self,
        *,
        tenant_id: str,
        owner_id: str,
        owner_role: str = "owner",
        action: str,
        resource: str,
        target_user_id: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> None:
        with self.db.session() as db:
            db.add(
                OwnerAuditLog(
                    tenant_id=tenant_id,
                    owner_id=owner_id,
                    owner_role=owner_role,
                    action=action,
                    resource=resource,
                    target_user_id=target_user_id,
                    filters=filters or {},
                )
            )
            db.commit()

    def list_audit_logs(
        self,
        *,
        tenant_id: str,
        limit: int = 100,
    ) -> list[OwnerAuditLogItem]:
        with self.db.session() as db:
            rows = (
                db.query(OwnerAuditLog)
                .filter(OwnerAuditLog.tenant_id == tenant_id)
                .order_by(OwnerAuditLog.created_at.desc(), OwnerAuditLog.id.desc())
                .limit(limit)
                .all()
            )
            return [
                OwnerAuditLogItem(
                    id=r.id,
                    tenant_id=r.tenant_id,
                    owner_id=r.owner_id,
                    owner_role=r.owner_role,
                    action=r.action,
                    resource=r.resource,
                    target_user_id=r.target_user_id,
                    filters=dict(r.filters or {}),
                    created_at=r.created_at,
                )
                for r in rows
            ]

    def upsert_organization_user(
        self,
        *,
        tenant_id: str,
        user_id: str,
        display_name: str,
        amministrazione: str = "Predefinita",
        role: str = "operatore",
    ) -> OrganizationUserResponse:
        now = datetime.now(timezone.utc)
        with self.db.session() as db:
            row = db.query(OrganizationUser).filter_by(tenant_id=tenant_id, user_id=user_id).first()
            if row is None:
                row = OrganizationUser(
                    id=f"orgu_{uuid.uuid4().hex[:12]}",
                    tenant_id=tenant_id,
                    user_id=user_id,
                    display_name=display_name,
                    amministrazione=amministrazione,
                    role=role,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.display_name = display_name
                row.amministrazione = amministrazione
                row.role = role
                row.updated_at = now
            db.commit()
            db.refresh(row)
            self.cache.invalidate_tenant(tenant_id)
            self.db.bump_owner_metrics_version(tenant_id)
            return OrganizationUserResponse(
                id=row.id,
                tenant_id=row.tenant_id,
                user_id=row.user_id,
                display_name=row.display_name,
                amministrazione=row.amministrazione,
                role=row.role,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    # ------------------------------------------------------------------
    # Shared Scoping & Period Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_directory(
        db: Session,
        *,
        tenant_id: str,
        allowed_administrations: list[str] | None = None,
        amministrazione_filter: str | None = None,
    ) -> tuple[dict[str, dict[str, str]], set[str]]:
        """Discover all tenant users from OrganizationUser & learning tables, applying admin scope."""
        org_rows = db.query(OrganizationUser).filter(OrganizationUser.tenant_id == tenant_id).all()
        directory: dict[str, dict[str, str]] = {}
        for o in org_rows:
            directory[o.user_id] = {
                "display_name": o.display_name,
                "amministrazione": o.amministrazione,
                "role": o.role,
            }

        # Include tenant users with existing learning/quiz records via single UNION query
        union_q = union(
            *[
                select(model.user_id).where(model.tenant_id == tenant_id)
                for model in (UserKnowledgeProfile, LearningGap, CustomQuiz, CustomQuizAttempt, CourseQuizAttempt)
            ]
        )
        for (uid,) in db.execute(union_q).all():
            if uid and uid not in directory:
                directory[uid] = {
                    "display_name": uid,
                    "amministrazione": "Predefinita",
                    "role": "operatore",
                }

        allowed_set = {a.lower() for a in (allowed_administrations or []) if a.strip()}
        scoped_ids: set[str] = set()
        for uid, meta in directory.items():
            adm_lower = meta["amministrazione"].lower()
            if allowed_set and adm_lower not in allowed_set:
                continue
            if amministrazione_filter and amministrazione_filter.lower() not in adm_lower:
                continue
            scoped_ids.add(uid)

        return directory, scoped_ids

    @staticmethod
    def _previous_window(
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        """Compute an equivalent preceding window for period-over-period evolution metrics."""
        d_from = _to_utc_naive(date_from)
        d_to = _to_utc_naive(date_to) or datetime.now(timezone.utc).replace(tzinfo=None)
        if d_from is None:
            # Compare last 14 days vs preceding 14 days by default
            curr_start = d_to - timedelta(days=14)
            return curr_start - timedelta(days=14), curr_start
        span = max(timedelta(hours=1), d_to - d_from)
        return d_from - span, d_from

    @staticmethod
    def _classify_topic_criticality(
        *,
        settings: Settings,
        error_rate: float,
        open_gaps: int,
        affected_users: int,
    ) -> Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        if error_rate >= settings.topic_critical_error_rate or (
            open_gaps >= settings.topic_critical_min_gaps and affected_users >= 2
        ):
            return "CRITICAL"
        if error_rate >= settings.topic_high_error_rate or open_gaps >= 2:
            return "HIGH"
        if error_rate >= settings.topic_medium_error_rate or open_gaps >= 1:
            return "MEDIUM"
        return "LOW"

    def _compute_topic_improvement_map(
        self,
        attempts: list[CustomQuizAttempt],
    ) -> dict[str, dict[str, list[float]]]:
        """Return {user_id: {topic: [chronological scores %]}} from completed CustomQuizAttempts."""
        out: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for att in sorted(attempts, key=lambda a: _to_utc_naive(a.completed_at) or datetime.min):
            q_fbs = (att.feedback or {}).get("question_feedback", [])
            per_t: dict[str, list[bool]] = defaultdict(list)
            for item in q_fbs:
                per_t[str(item.get("topic") or "Operatività generale")].append(bool(item.get("is_correct")))
            for topic, flags in per_t.items():
                pct = round(100.0 * sum(1 for f in flags if f) / len(flags), 2)
                out[att.user_id][topic].append(pct)
        return out

    @staticmethod
    def _user_learning_improvement(topic_series: dict[str, list[float]]) -> float | None:
        deltas = [scores[-1] - scores[0] for scores in topic_series.values() if len(scores) >= 2]
        return round(sum(deltas) / len(deltas), 2) if deltas else None

    @staticmethod
    def _overall_user_status(
        *,
        attempts_count: int,
        open_gaps: int,
        critical_gaps: int,
        avg_score: float,
        improvement: float | None,
    ) -> str:
        if critical_gaps > 0:
            return "ATTENZIONE_CRITICA"
        if attempts_count == 0 and open_gaps == 0:
            return "NESSUNA_ATTIVITA"
        if open_gaps > 0:
            if improvement is not None and improvement > 0:
                return "IN_MIGLIORAMENTO"
            return "SUPPORTO_NECESSARIO"
        if avg_score >= 75.0:
            return "COMPETENTE"
        return "ATTIVO"

    # ------------------------------------------------------------------
    # 1. Dashboard Generale (Overview)
    # ------------------------------------------------------------------

    def get_overview(
        self,
        *,
        tenant_id: str,
        allowed_administrations: list[str] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        software: str | None = None,
        module_name: str | None = None,
        amministrazione: str | None = None,
        bypass_cache: bool = False,
    ) -> OwnerDashboardOverviewResponse:
        d_from = _to_utc_naive(date_from)
        d_to = _to_utc_naive(date_to)
        cache_params = {
            "scope": ",".join(sorted(allowed_administrations or [])),
            "date_from": d_from.isoformat() if d_from else None,
            "date_to": d_to.isoformat() if d_to else None,
            "software": software,
            "module_name": module_name,
            "amministrazione": amministrazione,
        }
        cache_lookup_params = {**cache_params, "_ver": self.db.get_owner_metrics_version(tenant_id)}
        if not bypass_cache:
            cached = self.cache.get(tenant_id, "overview", cache_lookup_params)
            if cached is not None:
                return cached

        with self.db.session() as db:
            directory, scoped_ids = self._resolve_directory(
                db,
                tenant_id=tenant_id,
                allowed_administrations=allowed_administrations,
                amministrazione_filter=amministrazione,
            )

            all_courses_count = db.query(func.count(Course.id)).filter(Course.tenant_id == tenant_id).scalar() or 0

            # Available filter facets inside tenant + owner scope
            prof_rows = db.query(UserKnowledgeProfile).filter(UserKnowledgeProfile.tenant_id == tenant_id).all()
            scoped_profs = [p for p in prof_rows if p.user_id in scoped_ids]
            available_softwares = sorted({p.software for p in scoped_profs if p.software})
            available_modules = sorted({p.module_name for p in scoped_profs if p.module_name})
            available_admins = sorted({directory[uid]["amministrazione"] for uid in scoped_ids if uid in directory})

            if not scoped_ids:
                resp = OwnerDashboardOverviewResponse(
                    tenant_id=tenant_id,
                    filters=cache_params,
                    total_users=0,
                    active_users_in_period=0,
                    course_completion_rate=0.0,
                    avg_quiz_score=0.0,
                    avg_learning_improvement=None,
                    knowledge_gap_resolution_rate=0.0,
                    open_gaps_count=0,
                    users_with_critical_gaps=0,
                    improvement_vs_previous_period=None,
                    available_softwares=available_softwares,
                    available_modules=available_modules,
                    available_administrations=available_admins,
                    timeline=[],
                )
                self.cache.set(tenant_id, "overview", cache_lookup_params, resp)
                return resp

            # Load quizzes & attempts filtered at DB level by tenant + scoped users + dates
            cq_q = db.query(CustomQuizAttempt).join(CustomQuiz).filter(
                CustomQuizAttempt.tenant_id == tenant_id,
                CustomQuizAttempt.user_id.in_(scoped_ids),
            )
            if software:
                cq_q = cq_q.filter(CustomQuiz.software.ilike(f"%{software}%"))
            if module_name:
                cq_q = cq_q.filter(CustomQuiz.module_name.ilike(f"%{module_name}%"))
            all_cq_attempts = cq_q.order_by(CustomQuizAttempt.completed_at.asc()).all()

            cqa_q = db.query(CourseQuizAttempt).filter(
                CourseQuizAttempt.tenant_id == tenant_id,
                CourseQuizAttempt.user_id.in_(scoped_ids),
            )
            all_course_attempts = cqa_q.order_by(CourseQuizAttempt.completed_at.asc()).all()

            gap_q = db.query(LearningGap).filter(
                LearningGap.tenant_id == tenant_id,
                LearningGap.user_id.in_(scoped_ids),
            )
            if software:
                gap_q = gap_q.filter(LearningGap.software.ilike(f"%{software}%"))
            if module_name:
                gap_q = gap_q.filter(LearningGap.module_name.ilike(f"%{module_name}%"))
            all_gaps = gap_q.all()

        # Apply period boundaries consistently
        def _in_period(dt: datetime | None, start: datetime | None, end: datetime | None) -> bool:
            t = _to_utc_naive(dt)
            if t is None:
                return False
            if start and t < start:
                return False
            if end and t > end:
                return False
            return True

        period_cq = [a for a in all_cq_attempts if _in_period(a.completed_at, d_from, d_to)]
        period_cqa = [a for a in all_course_attempts if _in_period(a.completed_at, d_from, d_to)]
        period_gaps = [g for g in all_gaps if _in_period(g.detected_at, d_from, d_to) or g.status != "RESOLVED"]

        active_users = {a.user_id for a in period_cq} | {a.user_id for a in period_cqa}

        # Course completion rate: across scoped users x tenant courses (if courses exist)
        passed_pairs = {(a.user_id, a.course_id) for a in period_cqa if a.passed}
        if all_courses_count > 0:
            denom = max(1, len(scoped_ids) * all_courses_count)
            course_completion_rate = round((len(passed_pairs) / denom) * 100.0, 2)
        else:
            course_completion_rate = 0.0

        all_scores = [a.percentage for a in period_cq] + [a.percentage for a in period_cqa]
        avg_quiz_score = _safe_avg(all_scores)

        # Average Learning Improvement across scoped users
        topic_map = self._compute_topic_improvement_map(period_cq)
        user_improvements = [
            imp for imp in (self._user_learning_improvement(topic_map[u]) for u in scoped_ids) if imp is not None
        ]
        avg_learning_improvement = _safe_avg(user_improvements) if user_improvements else None

        # Gaps stats
        total_gaps = len(all_gaps)
        resolved_gaps = sum(1 for g in all_gaps if g.status == "RESOLVED")
        open_gaps = [g for g in all_gaps if g.status != "RESOLVED"]
        gap_resolution_rate = round((resolved_gaps / total_gaps) * 100.0, 2) if total_gaps > 0 else 0.0
        critical_users = {
            g.user_id for g in open_gaps if _gap_criticality(g.priority, g.repeated_error_count) in ("CRITICAL", "HIGH")
        }

        # Comparison vs previous equivalent period
        prev_start, prev_end = self._previous_window(d_from, d_to)
        curr_start = prev_end if d_from is None else d_from
        curr_scores = [
            a.percentage
            for a in (all_cq_attempts + all_course_attempts)
            if _in_period(a.completed_at, curr_start, d_to)
        ]
        prev_scores = [
            a.percentage
            for a in (all_cq_attempts + all_course_attempts)
            if _in_period(a.completed_at, prev_start, prev_end)
        ]
        improvement_vs_prev = (
            round(_safe_avg(curr_scores) - _safe_avg(prev_scores), 2)
            if curr_scores and prev_scores
            else None
        )

        # Timeline buckets by YYYY-MM-DD
        day_scores: dict[str, list[float]] = defaultdict(list)
        day_gaps_open: dict[str, int] = defaultdict(int)
        day_gaps_res: dict[str, int] = defaultdict(int)
        for att in period_cq + period_cqa:
            t = _to_utc_naive(att.completed_at)
            if t:
                day_scores[t.strftime("%Y-%m-%d")].append(att.percentage)
        for g in period_gaps:
            td = _to_utc_naive(g.detected_at)
            if td:
                day_gaps_open[td.strftime("%Y-%m-%d")] += 1
            tr = _to_utc_naive(g.resolved_at)
            if tr and g.status == "RESOLVED":
                day_gaps_res[tr.strftime("%Y-%m-%d")] += 1

        all_days = sorted(set(day_scores.keys()) | set(day_gaps_open.keys()) | set(day_gaps_res.keys()))
        timeline = [
            TrendPoint(
                period=day,
                attempts=len(day_scores[day]),
                avg_score=_safe_avg(day_scores[day]),
                gaps_opened=day_gaps_open[day],
                gaps_resolved=day_gaps_res[day],
            )
            for day in all_days[-30:]
        ]

        resp = OwnerDashboardOverviewResponse(
            tenant_id=tenant_id,
            filters=cache_params,
            total_users=len(scoped_ids),
            active_users_in_period=len(active_users),
            course_completion_rate=course_completion_rate,
            avg_quiz_score=avg_quiz_score,
            avg_learning_improvement=avg_learning_improvement,
            knowledge_gap_resolution_rate=gap_resolution_rate,
            open_gaps_count=len(open_gaps),
            users_with_critical_gaps=len(critical_users),
            improvement_vs_previous_period=improvement_vs_prev,
            available_softwares=available_softwares,
            available_modules=available_modules,
            available_administrations=available_admins,
            timeline=timeline,
        )
        self.cache.set(tenant_id, "overview", cache_lookup_params, resp)
        return resp

    # ------------------------------------------------------------------
    # 2. User Learning Overview (paginated, filterable, sortable)
    # ------------------------------------------------------------------

    def list_users(
        self,
        *,
        tenant_id: str,
        allowed_administrations: list[str] | None = None,
        search: str | None = None,
        amministrazione: str | None = None,
        software: str | None = None,
        learning_status: str | None = None,
        sort_by: Literal["display_name", "quiz_success_rate", "open_gaps_count", "last_activity_at", "courses_completed"] = "open_gaps_count",
        sort_dir: Literal["asc", "desc"] = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> OwnerUsersPageResponse:
        with self.db.session() as db:
            directory, scoped_ids = self._resolve_directory(
                db,
                tenant_id=tenant_id,
                allowed_administrations=allowed_administrations,
                amministrazione_filter=amministrazione,
            )
            if not scoped_ids:
                return OwnerUsersPageResponse(tenant_id=tenant_id, total=0, page=page, page_size=page_size, items=[])

            profiles = (
                db.query(UserKnowledgeProfile)
                .filter(UserKnowledgeProfile.tenant_id == tenant_id, UserKnowledgeProfile.user_id.in_(scoped_ids))
                .all()
            )
            gaps = (
                db.query(LearningGap)
                .filter(LearningGap.tenant_id == tenant_id, LearningGap.user_id.in_(scoped_ids))
                .all()
            )
            cq_attempts = (
                db.query(CustomQuizAttempt)
                .filter(CustomQuizAttempt.tenant_id == tenant_id, CustomQuizAttempt.user_id.in_(scoped_ids))
                .all()
            )
            cqa_attempts = (
                db.query(CourseQuizAttempt)
                .filter(CourseQuizAttempt.tenant_id == tenant_id, CourseQuizAttempt.user_id.in_(scoped_ids))
                .all()
            )
            lesson_completions = (
                db.query(LessonCompletion)
                .filter(LessonCompletion.tenant_id == tenant_id, LessonCompletion.user_id.in_(scoped_ids))
                .all()
            )
            tenant_courses = (
                db.query(Course)
                .options(joinedload(Course.modules).joinedload(CourseModule.lessons))
                .filter(Course.tenant_id == tenant_id)
                .all()
            )

        course_lesson_ids: dict[str, set[str]] = {
            c.id: {les.id for mod in c.modules for les in mod.lessons}
            for c in tenant_courses
        }
        completed_lessons_by_user: dict[str, set[str]] = defaultdict(set)
        lesson_ts_by_user: dict[str, list[datetime]] = defaultdict(list)
        for lc in lesson_completions:
            completed_lessons_by_user[lc.user_id].add(lc.lesson_id)
            if lc.completed_at is not None:
                lesson_ts_by_user[lc.user_id].append(lc.completed_at)

        prof_by_user: dict[str, list[UserKnowledgeProfile]] = defaultdict(list)
        for p in profiles:
            prof_by_user[p.user_id].append(p)
        gaps_by_user: dict[str, list[LearningGap]] = defaultdict(list)
        for g in gaps:
            gaps_by_user[g.user_id].append(g)
        cq_by_user: dict[str, list[CustomQuizAttempt]] = defaultdict(list)
        for a in cq_attempts:
            cq_by_user[a.user_id].append(a)
        cqa_by_user: dict[str, list[CourseQuizAttempt]] = defaultdict(list)
        for a in cqa_attempts:
            cqa_by_user[a.user_id].append(a)

        topic_map = self._compute_topic_improvement_map(cq_attempts)
        rows: list[OwnerUserOverviewItem] = []

        for uid in sorted(scoped_ids):
            meta = directory[uid]
            u_profs = prof_by_user[uid]
            u_gaps = gaps_by_user[uid]
            u_cqs = cq_by_user[uid]
            u_cqas = cqa_by_user[uid]

            softwares_used = sorted({p.software for p in u_profs if p.software} | {g.software for g in u_gaps if g.software})
            if software and not any(software.lower() in s.lower() for s in softwares_used):
                continue

            if search:
                needle = search.lower()
                if needle not in uid.lower() and needle not in meta["display_name"].lower() and needle not in meta["amministrazione"].lower():
                    continue

            passed_course_ids = {a.course_id for a in u_cqas if a.passed}
            u_completed_lessons = completed_lessons_by_user[uid]
            lesson_completed_course_ids = {
                cid
                for cid, lids in course_lesson_ids.items()
                if lids and lids.issubset(u_completed_lessons)
            }
            courses_completed = len(passed_course_ids | lesson_completed_course_ids)
            all_scores = [a.percentage for a in u_cqs] + [a.percentage for a in u_cqas]
            avg_success = _safe_avg(all_scores)
            open_gaps = [g for g in u_gaps if g.status != "RESOLVED"]
            crit_gaps = sum(
                1 for g in open_gaps if _gap_criticality(g.priority, g.repeated_error_count) in ("CRITICAL", "HIGH")
            )
            improvement = self._user_learning_improvement(topic_map.get(uid, {}))

            timestamps = [
                _to_utc_naive(dt)
                for dt in (
                    [a.completed_at for a in u_cqs]
                    + [a.completed_at for a in u_cqas]
                    + [p.updated_at for p in u_profs]
                    + lesson_ts_by_user[uid]
                )
                if dt is not None
            ]
            last_act = max(timestamps) if timestamps else None
            status_label = self._overall_user_status(
                attempts_count=len(all_scores),
                open_gaps=len(open_gaps),
                critical_gaps=crit_gaps,
                avg_score=avg_success,
                improvement=improvement,
            )
            if learning_status and learning_status.upper() != status_label:
                continue

            rows.append(
                OwnerUserOverviewItem(
                    user_id=uid,
                    display_name=meta["display_name"],
                    amministrazione=meta["amministrazione"],
                    softwares_used=softwares_used,
                    courses_completed=courses_completed,
                    quiz_success_rate=avg_success,
                    custom_quizzes_count=len(u_cqs),
                    learning_improvement=improvement,
                    open_gaps_count=len(open_gaps),
                    critical_gaps_count=crit_gaps,
                    last_activity_at=last_act,
                    overall_status=status_label,
                )
            )

        reverse = sort_dir == "desc"

        def _sort_key(item: OwnerUserOverviewItem) -> Any:
            val = getattr(item, sort_by)
            if val is None:
                return datetime.min if sort_by == "last_activity_at" else ""
            if isinstance(val, str):
                return val.lower()
            return val

        rows.sort(key=_sort_key, reverse=reverse)
        total = len(rows)
        start = (page - 1) * page_size
        return OwnerUsersPageResponse(
            tenant_id=tenant_id,
            total=total,
            page=page,
            page_size=page_size,
            items=rows[start : start + page_size],
        )

    # ------------------------------------------------------------------
    # 3. User Learning Profile (Dettaglio Completo)
    # ------------------------------------------------------------------

    def get_user_detail(
        self,
        *,
        tenant_id: str,
        user_id: str,
        allowed_administrations: list[str] | None = None,
    ) -> OwnerUserDetailResponse:
        with self.db.session() as db:
            directory, scoped_ids = self._resolve_directory(
                db,
                tenant_id=tenant_id,
                allowed_administrations=allowed_administrations,
            )
            if user_id not in scoped_ids:
                raise ValueError(f"Utente '{user_id}' non trovato nell'ambito autorizzato del tenant '{tenant_id}'.")

            meta = directory[user_id]
            profiles = (
                db.query(UserKnowledgeProfile)
                .filter(UserKnowledgeProfile.tenant_id == tenant_id, UserKnowledgeProfile.user_id == user_id)
                .all()
            )
            gaps = (
                db.query(LearningGap)
                .filter(LearningGap.tenant_id == tenant_id, LearningGap.user_id == user_id)
                .order_by(LearningGap.detected_at.desc())
                .all()
            )
            c_attempts = (
                db.query(CourseQuizAttempt)
                .filter(CourseQuizAttempt.tenant_id == tenant_id, CourseQuizAttempt.user_id == user_id)
                .order_by(CourseQuizAttempt.completed_at.asc())
                .all()
            )
            cq_attempts = (
                db.query(CustomQuizAttempt)
                .filter(CustomQuizAttempt.tenant_id == tenant_id, CustomQuizAttempt.user_id == user_id)
                .order_by(CustomQuizAttempt.completed_at.asc())
                .all()
            )
            courses = (
                db.query(Course)
                .options(joinedload(Course.modules).joinedload(CourseModule.lessons))
                .filter(Course.tenant_id == tenant_id)
                .all()
            )
            lesson_completions = (
                db.query(LessonCompletion)
                .filter(LessonCompletion.tenant_id == tenant_id, LessonCompletion.user_id == user_id)
                .all()
            )
            custom_quizzes = {
                q.id: q
                for q in db.query(CustomQuiz).filter(CustomQuiz.tenant_id == tenant_id, CustomQuiz.user_id == user_id).all()
            }

        course_title_by_id = {c.id: c.title for c in courses}

        # A. Learning Performance
        course_evo = [
            UserQuizEvolutionPoint(
                attempt_id=a.id,
                quiz_id=a.quiz_id,
                quiz_type="course_quiz",
                title=course_title_by_id.get(a.course_id, a.course_id),
                percentage=a.percentage,
                passed_or_outcome="PASSED" if a.passed else "FAILED",
                completed_at=a.completed_at,
            )
            for a in c_attempts
        ]
        custom_evo = [
            UserQuizEvolutionPoint(
                attempt_id=a.id,
                quiz_id=a.quiz_id,
                quiz_type="custom_quiz",
                title=(
                    f"Custom Quiz — {', '.join(custom_quizzes[a.quiz_id].topics_verified[:2])}"
                    if a.quiz_id in custom_quizzes and custom_quizzes[a.quiz_id].topics_verified
                    else f"Custom Quiz {a.quiz_id}"
                ),
                percentage=a.percentage,
                passed_or_outcome=a.outcome,
                completed_at=a.completed_at,
            )
            for a in cq_attempts
        ]

        # Competence over time & retention calculation
        topic_map = self._compute_topic_improvement_map(cq_attempts)
        u_topic_scores = topic_map.get(user_id, {})
        ret_checks = 0
        ret_ok = 0
        for scores in u_topic_scores.values():
            for i in range(len(scores) - 1):
                if scores[i] >= 70.0:
                    ret_checks += 1
                    if scores[i + 1] >= 70.0:
                        ret_ok += 1
        retention_rate = round((ret_ok / ret_checks) * 100.0, 2) if ret_checks > 0 else None

        by_day: dict[str, list[float]] = defaultdict(list)
        for ev in course_evo + custom_evo:
            t = _to_utc_naive(ev.completed_at)
            if t:
                by_day[t.strftime("%Y-%m-%d")].append(ev.percentage)
        comp_timeline = [
            TrendPoint(period=d, attempts=len(vals), avg_score=_safe_avg(vals))
            for d, vals in sorted(by_day.items())
        ]

        # Courses completed vs to complete
        course_best: dict[str, tuple[float, datetime | None, bool]] = {}
        for a in c_attempts:
            prev_pct, prev_dt, prev_pass = course_best.get(a.course_id, (-1.0, None, False))
            course_best[a.course_id] = (
                max(prev_pct, a.percentage),
                a.completed_at,
                prev_pass or a.passed,
            )

        completed_lesson_ids = {lc.lesson_id for lc in lesson_completions}
        last_lesson_by_course: dict[str, datetime] = {}
        for lc in lesson_completions:
            if lc.completed_at is not None:
                prev_dt = last_lesson_by_course.get(lc.course_id)
                if prev_dt is None or lc.completed_at > prev_dt:
                    last_lesson_by_course[lc.course_id] = lc.completed_at

        completed_courses: list[CourseProgressItem] = []
        todo_courses: list[CourseProgressItem] = []
        for c in courses:
            best_pct, last_dt, passed = course_best.get(c.id, (None, None, False))
            c_lesson_ids = {les.id for mod in c.modules for les in mod.lessons}
            all_lessons_done = bool(c_lesson_ids) and c_lesson_ids.issubset(completed_lesson_ids)
            is_completed = passed or all_lessons_done
            effective_dt = last_dt or (last_lesson_by_course.get(c.id) if all_lessons_done else None)
            item = CourseProgressItem(
                course_id=c.id,
                title=c.title,
                course_type=c.course_type,
                status="COMPLETATO" if is_completed else "DA_COMPLETARE",
                best_percentage=best_pct if best_pct is not None and best_pct >= 0 else None,
                last_attempt_at=effective_dt,
            )
            if is_completed:
                completed_courses.append(item)
            else:
                todo_courses.append(item)

        # B. Knowledge Gaps detail (including last result obtained per topic)
        prof_by_topic = {p.topic: p for p in profiles}
        gap_items: list[OwnerUserGapDetailItem] = []
        for g in gaps:
            prof = prof_by_topic.get(g.topic)
            t_scores = u_topic_scores.get(g.topic, [])
            last_res = t_scores[-1] if t_scores else None
            err_cnt = max(g.repeated_error_count, prof.error_count if prof else 0)
            gap_items.append(
                OwnerUserGapDetailItem(
                    gap_id=g.id,
                    topic=g.topic,
                    software=g.software,
                    module_name=g.module_name,
                    criticality=_gap_criticality(g.priority, err_cnt),
                    error_count=err_cnt,
                    last_difficulty_at=g.last_verified_at or g.detected_at,
                    verifications_count=max(g.positive_verifications, prof.verification_count if prof else 0),
                    status=g.status,  # type: ignore[arg-type]
                    last_result_percentage=last_res,
                )
            )

        # C. Unified Learning History
        history_events: list[UserLearningHistoryEvent] = []
        for ev in course_evo:
            history_events.append(
                UserLearningHistoryEvent(
                    event_type="course_quiz",
                    title=f"Quiz corso: {ev.title}",
                    result_summary=ev.passed_or_outcome,
                    percentage=ev.percentage,
                    occurred_at=ev.completed_at,
                )
            )
        for ev in custom_evo:
            history_events.append(
                UserLearningHistoryEvent(
                    event_type="custom_quiz",
                    title=ev.title,
                    result_summary=ev.passed_or_outcome,
                    percentage=ev.percentage,
                    occurred_at=ev.completed_at,
                )
            )
        for g in gaps:
            history_events.append(
                UserLearningHistoryEvent(
                    event_type="gap_transition",
                    title=f"Lacuna su '{g.topic}' -> stato {g.status}",
                    topic=g.topic,
                    result_summary=f"Verifiche positive: {g.positive_verifications}",
                    occurred_at=g.resolved_at or g.last_verified_at or g.detected_at,
                )
            )
        for topic_name, scores in u_topic_scores.items():
            if len(scores) >= 2 and scores[-1] > scores[0]:
                history_events.append(
                    UserLearningHistoryEvent(
                        event_type="topic_improvement",
                        title=f"Miglioramento registrato su '{topic_name}' (+{round(scores[-1] - scores[0], 1)}%)",
                        topic=topic_name,
                        result_summary=f"Da {scores[0]}% a {scores[-1]}%",
                        percentage=scores[-1],
                        occurred_at=cq_attempts[-1].completed_at,
                    )
                )

        history_events.sort(key=lambda e: _to_utc_naive(e.occurred_at) or datetime.min, reverse=True)

        open_gaps_cnt = sum(1 for g in gaps if g.status != "RESOLVED")
        crit_cnt = sum(1 for g in gap_items if g.status != "RESOLVED" and g.criticality in ("CRITICAL", "HIGH"))
        all_pcts = [e.percentage for e in course_evo + custom_evo]
        overall_status = self._overall_user_status(
            attempts_count=len(all_pcts),
            open_gaps=open_gaps_cnt,
            critical_gaps=crit_cnt,
            avg_score=_safe_avg(all_pcts),
            improvement=self._user_learning_improvement(u_topic_scores),
        )

        return OwnerUserDetailResponse(
            tenant_id=tenant_id,
            user_id=user_id,
            display_name=meta["display_name"],
            amministrazione=meta["amministrazione"],
            overall_status=overall_status,
            learning_performance=OwnerUserLearningPerformance(
                course_quiz_evolution=course_evo,
                custom_quiz_evolution=custom_evo,
                competence_over_time=comp_timeline,
                courses_completed=completed_courses,
                courses_to_complete=todo_courses,
                retention_rate=retention_rate,
            ),
            knowledge_gaps=gap_items,
            learning_history=history_events,
        )

    # ------------------------------------------------------------------
    # 4. Topic to Review & User Drill-down
    # ------------------------------------------------------------------

    def list_topics_to_review(
        self,
        *,
        tenant_id: str,
        allowed_administrations: list[str] | None = None,
        software: str | None = None,
        module_name: str | None = None,
        amministrazione: str | None = None,
        criticality: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[OwnerTopicReviewItem]:
        d_from = _to_utc_naive(date_from)
        d_to = _to_utc_naive(date_to)
        with self.db.session() as db:
            _, scoped_ids = self._resolve_directory(
                db,
                tenant_id=tenant_id,
                allowed_administrations=allowed_administrations,
                amministrazione_filter=amministrazione,
            )
            if not scoped_ids:
                return []

            gaps_q = db.query(LearningGap).filter(LearningGap.tenant_id == tenant_id, LearningGap.user_id.in_(scoped_ids))
            profs_q = db.query(UserKnowledgeProfile).filter(
                UserKnowledgeProfile.tenant_id == tenant_id,
                UserKnowledgeProfile.user_id.in_(scoped_ids),
            )
            if software:
                gaps_q = gaps_q.filter(LearningGap.software.ilike(f"%{software}%"))
                profs_q = profs_q.filter(UserKnowledgeProfile.software.ilike(f"%{software}%"))
            if module_name:
                gaps_q = gaps_q.filter(LearningGap.module_name.ilike(f"%{module_name}%"))
                profs_q = profs_q.filter(UserKnowledgeProfile.module_name.ilike(f"%{module_name}%"))

            gaps = gaps_q.all()
            profs = profs_q.all()
            cq_attempts = (
                db.query(CustomQuizAttempt)
                .filter(CustomQuizAttempt.tenant_id == tenant_id, CustomQuizAttempt.user_id.in_(scoped_ids))
                .all()
            )

        topic_agg: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "software": "Cityware / CWOL",
                "module_name": "Generale",
                "users": set(),
                "total_gaps": 0,
                "open_gaps": 0,
                "correct": 0,
                "errors": 0,
                "curr_errors": 0,
                "curr_total": 0,
                "prev_errors": 0,
                "prev_total": 0,
            }
        )

        for g in gaps:
            rec = topic_agg[g.topic]
            rec["software"] = g.software
            rec["module_name"] = g.module_name
            rec["users"].add(g.user_id)
            rec["total_gaps"] += 1
            if g.status != "RESOLVED":
                rec["open_gaps"] += 1

        for p in profs:
            if p.error_count == 0 and p.topic not in topic_agg:
                continue
            rec = topic_agg[p.topic]
            rec["software"] = p.software
            rec["module_name"] = p.module_name
            if p.error_count > 0:
                rec["users"].add(p.user_id)
            rec["correct"] += p.correct_count
            rec["errors"] += p.error_count

        prev_start, prev_end = self._previous_window(d_from, d_to)
        curr_start = prev_end if d_from is None else d_from

        for att in cq_attempts:
            t = _to_utc_naive(att.completed_at)
            if t is None:
                continue
            for qf in (att.feedback or {}).get("question_feedback", []):
                t_name = str(qf.get("topic") or "Operatività generale")
                if t_name not in topic_agg:
                    continue
                is_ok = bool(qf.get("is_correct"))
                if (not d_from or t >= curr_start) and (not d_to or t <= d_to):
                    topic_agg[t_name]["curr_total"] += 1
                    if not is_ok:
                        topic_agg[t_name]["curr_errors"] += 1
                elif prev_start and t >= prev_start and t < prev_end:
                    topic_agg[t_name]["prev_total"] += 1
                    if not is_ok:
                        topic_agg[t_name]["prev_errors"] += 1

        items: list[OwnerTopicReviewItem] = []
        for topic_name, rec in topic_agg.items():
            total_ans = rec["correct"] + rec["errors"]
            err_rate = round((rec["errors"] / total_ans) * 100.0, 2) if total_ans > 0 else (50.0 if rec["open_gaps"] > 0 else 0.0)
            crit = self._classify_topic_criticality(
                settings=self.settings,
                error_rate=err_rate,
                open_gaps=rec["open_gaps"],
                affected_users=len(rec["users"]),
            )
            if criticality and criticality.upper() != crit:
                continue

            evo = None
            if rec["curr_total"] > 0 and rec["prev_total"] > 0:
                curr_r = (rec["curr_errors"] / rec["curr_total"]) * 100.0
                prev_r = (rec["prev_errors"] / rec["prev_total"]) * 100.0
                evo = round(curr_r - prev_r, 2)  # Negative = error rate decreased (improvement)

            items.append(
                OwnerTopicReviewItem(
                    topic=topic_name,
                    software=rec["software"],
                    module_name=rec["module_name"],
                    affected_users_count=len(rec["users"]),
                    total_gaps_count=rec["total_gaps"],
                    open_gaps_count=rec["open_gaps"],
                    avg_error_rate=err_rate,
                    criticality=crit,
                    evolution_vs_previous_period=evo,
                )
            )

        rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        items.sort(key=lambda x: (rank[x.criticality], -x.open_gaps_count, -x.avg_error_rate))
        return items

    def get_topic_users_drilldown(
        self,
        *,
        tenant_id: str,
        topic: str,
        allowed_administrations: list[str] | None = None,
        amministrazione: str | None = None,
    ) -> OwnerTopicDrilldownResponse:
        topics = self.list_topics_to_review(
            tenant_id=tenant_id,
            allowed_administrations=allowed_administrations,
            amministrazione=amministrazione,
        )
        summary = next((t for t in topics if t.topic.lower() == topic.lower()), None)
        if summary is None:
            raise ValueError(f"Topic '{topic}' non trovato o non autorizzato per il tenant '{tenant_id}'.")

        with self.db.session() as db:
            directory, scoped_ids = self._resolve_directory(
                db,
                tenant_id=tenant_id,
                allowed_administrations=allowed_administrations,
                amministrazione_filter=amministrazione,
            )
            gaps = (
                db.query(LearningGap)
                .filter(
                    LearningGap.tenant_id == tenant_id,
                    LearningGap.topic == summary.topic,
                    LearningGap.user_id.in_(scoped_ids),
                )
                .all()
            )

        affected = [
            TopicAffectedUserItem(
                user_id=g.user_id,
                display_name=directory[g.user_id]["display_name"],
                amministrazione=directory[g.user_id]["amministrazione"],
                gap_status=g.status,
                priority=g.priority,
                repeated_error_count=g.repeated_error_count,
                last_verified_at=g.last_verified_at or g.detected_at,
            )
            for g in gaps
        ]
        return OwnerTopicDrilldownResponse(tenant_id=tenant_id, topic_summary=summary, affected_users=affected)

    # ------------------------------------------------------------------
    # 5. Custom Quiz Analytics
    # ------------------------------------------------------------------

    def get_custom_quiz_analytics(
        self,
        *,
        tenant_id: str,
        allowed_administrations: list[str] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        software: str | None = None,
        module_name: str | None = None,
        amministrazione: str | None = None,
    ) -> OwnerCustomQuizAnalyticsResponse:
        d_from = _to_utc_naive(date_from)
        d_to = _to_utc_naive(date_to)
        with self.db.session() as db:
            _, scoped_ids = self._resolve_directory(
                db,
                tenant_id=tenant_id,
                allowed_administrations=allowed_administrations,
                amministrazione_filter=amministrazione,
            )
            if not scoped_ids:
                return OwnerCustomQuizAnalyticsResponse(
                    tenant_id=tenant_id,
                    filters={},
                    total_generated=0,
                    total_completed=0,
                    avg_correct_percentage=0.0,
                    improvement_between_verifications=None,
                    gaps_resolved_via_followup=0,
                    persistent_gaps_count=0,
                    repeated_error_rate=0.0,
                    retention_rate=None,
                    timeline=[],
                )

            qz_q = db.query(CustomQuiz).filter(CustomQuiz.tenant_id == tenant_id, CustomQuiz.user_id.in_(scoped_ids))
            att_q = (
                db.query(CustomQuizAttempt)
                .join(CustomQuiz)
                .filter(CustomQuizAttempt.tenant_id == tenant_id, CustomQuizAttempt.user_id.in_(scoped_ids))
            )
            gap_q = db.query(LearningGap).filter(LearningGap.tenant_id == tenant_id, LearningGap.user_id.in_(scoped_ids))
            if software:
                qz_q = qz_q.filter(CustomQuiz.software.ilike(f"%{software}%"))
                att_q = att_q.filter(CustomQuiz.software.ilike(f"%{software}%"))
                gap_q = gap_q.filter(LearningGap.software.ilike(f"%{software}%"))
            if module_name:
                qz_q = qz_q.filter(CustomQuiz.module_name.ilike(f"%{module_name}%"))
                att_q = att_q.filter(CustomQuiz.module_name.ilike(f"%{module_name}%"))
                gap_q = gap_q.filter(LearningGap.module_name.ilike(f"%{module_name}%"))

            if d_from:
                qz_q = qz_q.filter(CustomQuiz.generated_at >= d_from)
                att_q = att_q.filter(CustomQuizAttempt.completed_at >= d_from)
            if d_to:
                qz_q = qz_q.filter(CustomQuiz.generated_at <= d_to)
                att_q = att_q.filter(CustomQuizAttempt.completed_at <= d_to)

            quizzes = qz_q.all()
            attempts = att_q.order_by(CustomQuizAttempt.completed_at.asc()).all()
            gaps = gap_q.all()

        topic_map = self._compute_topic_improvement_map(attempts)
        deltas: list[float] = []
        ret_checks = 0
        ret_ok = 0
        for u_topics in topic_map.values():
            for scores in u_topics.values():
                if len(scores) >= 2:
                    deltas.append(scores[-1] - scores[0])
                for i in range(len(scores) - 1):
                    if scores[i] >= 70.0:
                        ret_checks += 1
                        if scores[i + 1] >= 70.0:
                            ret_ok += 1

        total_q_answered = sum(a.total_questions for a in attempts)
        repeated_errors = 0
        seen_user_wrong_topic: set[tuple[str, str]] = set()
        for a in attempts:
            for qf in (a.feedback or {}).get("question_feedback", []):
                if not qf.get("is_correct"):
                    pair = (a.user_id, str(qf.get("topic") or "Generale"))
                    if pair in seen_user_wrong_topic:
                        repeated_errors += 1
                    seen_user_wrong_topic.add(pair)

        # Strict non-false-positive rule: only gaps with >= 2 positive verifications count as resolved
        resolved_via_followup = sum(1 for g in gaps if g.status == "RESOLVED" and g.positive_verifications >= 2)
        persistent_gaps = sum(1 for g in gaps if g.status != "RESOLVED" and (g.repeated_error_count > 0 or g.status in ("OPEN", "IN_PROGRESS")))

        by_day: dict[str, list[float]] = defaultdict(list)
        for a in attempts:
            t = _to_utc_naive(a.completed_at)
            if t:
                by_day[t.strftime("%Y-%m-%d")].append(a.percentage)

        return OwnerCustomQuizAnalyticsResponse(
            tenant_id=tenant_id,
            filters={
                "date_from": d_from.isoformat() if d_from else None,
                "date_to": d_to.isoformat() if d_to else None,
                "software": software,
                "module_name": module_name,
                "amministrazione": amministrazione,
            },
            total_generated=len(quizzes),
            total_completed=len(attempts),
            avg_correct_percentage=_safe_avg([a.percentage for a in attempts]),
            improvement_between_verifications=_safe_avg(deltas) if deltas else None,
            gaps_resolved_via_followup=resolved_via_followup,
            persistent_gaps_count=persistent_gaps,
            repeated_error_rate=round((repeated_errors / max(1, total_q_answered)) * 100.0, 2) if total_q_answered > 0 else 0.0,
            retention_rate=round((ret_ok / ret_checks) * 100.0, 2) if ret_checks > 0 else None,
            timeline=[TrendPoint(period=d, attempts=len(v), avg_score=_safe_avg(v)) for d, v in sorted(by_day.items())],
        )

    # ------------------------------------------------------------------
    # 6. Owner Insights (Deterministic Metrics + Optional Qwen Synthesis)
    # ------------------------------------------------------------------

    def get_insights(
        self,
        *,
        tenant_id: str,
        allowed_administrations: list[str] | None = None,
        software: str | None = None,
        module_name: str | None = None,
        amministrazione: str | None = None,
        use_llm_synthesis: bool = False,
    ) -> OwnerInsightsResponse:
        overview = self.get_overview(
            tenant_id=tenant_id,
            allowed_administrations=allowed_administrations,
            software=software,
            module_name=module_name,
            amministrazione=amministrazione,
        )
        topics = self.list_topics_to_review(
            tenant_id=tenant_id,
            allowed_administrations=allowed_administrations,
            software=software,
            module_name=module_name,
            amministrazione=amministrazione,
        )
        cq_analytics = self.get_custom_quiz_analytics(
            tenant_id=tenant_id,
            allowed_administrations=allowed_administrations,
            software=software,
            module_name=module_name,
            amministrazione=amministrazione,
        )

        # Course performance comparison from DB
        with self.db.session() as db:
            _, scoped_ids = self._resolve_directory(
                db,
                tenant_id=tenant_id,
                allowed_administrations=allowed_administrations,
                amministrazione_filter=amministrazione,
            )
            course_rows = db.query(Course).filter(Course.tenant_id == tenant_id).all()
            cqa_rows = (
                db.query(CourseQuizAttempt)
                .filter(CourseQuizAttempt.tenant_id == tenant_id, CourseQuizAttempt.user_id.in_(scoped_ids))
                .all()
                if scoped_ids
                else []
            )

        course_title_map = {c.id: c.title for c in course_rows}
        scores_by_course: dict[str, list[float]] = defaultdict(list)
        for a in cqa_rows:
            scores_by_course[a.course_id].append(a.percentage)

        insights: list[OwnerInsightItem] = []

        for top in topics[:4]:
            if top.criticality in ("CRITICAL", "HIGH"):
                insights.append(
                    OwnerInsightItem(
                        category="topic",
                        severity=top.criticality,
                        message=(
                            f"{top.affected_users_count} utenti presentano difficoltà su '{top.topic}' "
                            f"(modulo {top.module_name}, tasso errori {top.avg_error_rate}%)."
                        ),
                        recommended_action=(
                            f"Assegnare sessione di ripasso guidato e Custom Quiz mirato su '{top.topic}'."
                        ),
                        evidence_metrics={
                            "topic": top.topic,
                            "software": top.software,
                            "module_name": top.module_name,
                            "affected_users_count": top.affected_users_count,
                            "open_gaps_count": top.open_gaps_count,
                            "avg_error_rate": top.avg_error_rate,
                        },
                        source_engine="deterministic",
                    )
                )

        if len(scores_by_course) >= 1:
            avgs = [(cid, _safe_avg(vals), len(vals)) for cid, vals in scores_by_course.items()]
            avgs.sort(key=lambda x: x[1])
            worst_cid, worst_avg, worst_n = avgs[0]
            overall_c_avg = _safe_avg([s for vals in scores_by_course.values() for s in vals])
            if worst_avg < 70.0 or (len(avgs) >= 2 and worst_avg < overall_c_avg - 10.0):
                c_title = course_title_map.get(worst_cid, worst_cid)
                insights.append(
                    OwnerInsightItem(
                        category="course",
                        severity="HIGH" if worst_avg < 60.0 else "MEDIUM",
                        message=(
                            f"Il corso '{c_title}' registra risultati mediamente inferiori "
                            f"({worst_avg}% su {worst_n} tentativi vs media {overall_c_avg}%)."
                        ),
                        recommended_action="Revisionare le lezioni correlate o rafforzare le esercitazioni pratiche del corso.",
                        evidence_metrics={
                            "course_id": worst_cid,
                            "course_title": c_title,
                            "course_avg_score": worst_avg,
                            "benchmark_avg_score": overall_c_avg,
                            "attempts": worst_n,
                        },
                        source_engine="deterministic",
                    )
                )

        if overview.users_with_critical_gaps > 0:
            insights.append(
                OwnerInsightItem(
                    category="users",
                    severity="HIGH",
                    message=(
                        f"{overview.users_with_critical_gaps} utenti su {overview.total_users} hanno lacune "
                        f"critiche/alte ancora aperte ({overview.open_gaps_count} lacune totali aperte)."
                    ),
                    recommended_action="Monitorare gli utenti critici dalla vista Utenti e verificare il completamento dei Custom Quiz.",
                    evidence_metrics={
                        "users_with_critical_gaps": overview.users_with_critical_gaps,
                        "total_users": overview.total_users,
                        "open_gaps_count": overview.open_gaps_count,
                    },
                    source_engine="deterministic",
                )
            )

        if cq_analytics.total_completed > 0:
            imp = cq_analytics.improvement_between_verifications
            insights.append(
                OwnerInsightItem(
                    category="custom_quiz",
                    severity="INFO" if (imp is not None and imp > 0) else "MEDIUM",
                    message=(
                        f"I Custom Quiz mostrano una media del {cq_analytics.avg_correct_percentage}% su "
                        f"{cq_analytics.total_completed} completamenti"
                        + (f" con miglioramento medio di +{imp}% tra verifiche successive." if imp is not None else ".")
                    ),
                    recommended_action=(
                        "Mantenere il programma di verifiche distanziate per consolidare le lacune risolte."
                        if (imp is not None and imp > 0)
                        else "Pianificare una seconda verifica sui Custom Quiz per misurare la retention."
                    ),
                    evidence_metrics={
                        "total_completed": cq_analytics.total_completed,
                        "avg_correct_percentage": cq_analytics.avg_correct_percentage,
                        "improvement_between_verifications": imp,
                        "gaps_resolved_via_followup": cq_analytics.gaps_resolved_via_followup,
                    },
                    source_engine="deterministic",
                )
            )

        model_info = self.generator.get_model_info()
        model_label = f"deterministic(expected={model_info['configured_model']})"

        # Optional verifiable Qwen synthesis when active LLM is explicitly requested
        if use_llm_synthesis and model_info["llm_runtime_active"] and insights:
            facts_blob = json.dumps([i.model_dump() for i in insights], ensure_ascii=False, indent=2)
            llm_out, used_llm, _info = self.generator.invoke_structured(
                OWNER_INSIGHTS_PROMPT,
                {
                    "tenant_id": tenant_id,
                    "scope_summary": amministrazione or "Tutte le amministrazioni",
                    "context": facts_blob,
                },
                OwnerInsightsLLMOutput,
            )
            if used_llm and llm_out and llm_out.insights:
                model_label = f"{model_info['provider']}:{model_info['configured_model']}"
                for idx, item in enumerate(llm_out.insights[:5]):
                    base_ev = insights[idx].evidence_metrics if idx < len(insights) else {
                        "overview_total_users": overview.total_users,
                        "open_gaps_count": overview.open_gaps_count,
                    }
                    insights[idx if idx < len(insights) else -1] = OwnerInsightItem(
                        category=item.category,
                        severity=item.severity,
                        message=item.message,
                        recommended_action=item.recommended_action or "Verificare il dettaglio nel pannello analytics.",
                        evidence_metrics={**base_ev, "llm_cited_metric": item.supporting_metric},
                        source_engine="qwen_synthesized",
                    )

        return OwnerInsightsResponse(
            tenant_id=tenant_id,
            filters={
                "software": software,
                "module_name": module_name,
                "amministrazione": amministrazione,
            },
            model_used=model_label,
            insights=insights,
        )
