"""Course publication lifecycle, revision snapshots, and source-change impact tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import joinedload

from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import (
    Course,
    CourseApprovalEvent,
    CourseModule,
    CourseRevision,
    DocumentMetadata,
)

# Valid transitions for the governance workflow:
# PROPOSED -> GENERATED -> UNDER_REVIEW -> APPROVED -> PUBLISHED
VALID_TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"GENERATED"},
    "GENERATED": {"UNDER_REVIEW", "REJECTED"},
    "UNDER_REVIEW": {"APPROVED", "REJECTED", "GENERATED"},
    "APPROVED": {"PUBLISHED", "UNDER_REVIEW", "REJECTED"},
    "PUBLISHED": {"UNDER_REVIEW", "NEEDS_UPDATE"},
    "NEEDS_UPDATE": {"UNDER_REVIEW", "GENERATED"},
    "REJECTED": {"UNDER_REVIEW", "GENERATED"},
}


class CourseLifecycleManager:
    """Enforces human-gated course approval, revision snapshots, and source impact detection."""

    def __init__(self, db_manager: DatabaseManager | None = None) -> None:
        self.db = db_manager or get_db_manager()

    @staticmethod
    def build_snapshot(course: Course) -> dict[str, Any]:
        """Serialize current Course structure for immutable revision history."""
        return {
            "title": course.title,
            "description": course.description,
            "course_type": course.course_type,
            "lifecycle_status": course.lifecycle_status,
            "modules": [
                {
                    "id": m.id,
                    "title": m.title,
                    "lessons": [
                        {
                            "id": les.id,
                            "title": les.title,
                            "explanation": les.explanation,
                            "procedures": les.procedures,
                            "summary": les.summary,
                        }
                        for les in m.lessons
                    ],
                }
                for m in course.modules
            ],
        }

    def record_revision(
        self,
        course_id: str,
        *,
        change_summary: str,
        changed_by: str = "system",
    ) -> CourseRevision:
        """Increment version_number and persist an immutable CourseRevision snapshot."""
        with self.db.session() as db:
            course = (
                db.query(Course)
                .options(joinedload(Course.modules).joinedload(CourseModule.lessons))
                .filter_by(id=course_id)
                .first()
            )
            if course is None:
                raise ValueError(f"Corso '{course_id}' non trovato.")

            existing_count = db.query(CourseRevision).filter_by(course_id=course_id).count()
            next_ver = existing_count + 1
            course.current_version = next_ver
            rev = CourseRevision(
                course_id=course_id,
                version_number=next_ver,
                change_summary=change_summary,
                snapshot=self.build_snapshot(course),
                changed_by=changed_by,
            )
            db.add(rev)
            db.commit()
            db.refresh(rev)
            return rev

    def transition(
        self,
        course_id: str,
        *,
        target_status: str,
        tenant_id: str = "default",
        actor_id: str = "reviewer",
        actor_role: str = "admin",
        notes: str = "",
    ) -> Course:
        """Perform validated lifecycle state transition with full audit event logging."""
        with self.db.session() as db:
            course = db.query(Course).filter_by(id=course_id, tenant_id=tenant_id).first()
            if course is None:
                raise ValueError(f"Corso '{course_id}' non trovato per il tenant '{tenant_id}'.")

            current = course.lifecycle_status
            allowed = VALID_TRANSITIONS.get(current, set())
            if target_status not in allowed:
                raise ValueError(
                    f"Transizione non consentita da '{current}' a '{target_status}'. Consentite: {sorted(allowed)}."
                )

            if target_status == "PUBLISHED" and course.grounding_status == "UNVERIFIED":
                raise ValueError(
                    "Impossibile pubblicare un corso con stato di grounding 'UNVERIFIED': verificare o rigenerare le fonti prima."
                )

            action_map = {
                "UNDER_REVIEW": "SUBMIT_REVIEW",
                "APPROVED": "APPROVE",
                "REJECTED": "REJECT",
                "PUBLISHED": "PUBLISH",
                "GENERATED": "GENERATE",
            }
            course.lifecycle_status = target_status
            if target_status == "PUBLISHED":
                course.published_at = datetime.now(timezone.utc)

            event = CourseApprovalEvent(
                course_id=course.id,
                from_status=current,
                to_status=target_status,
                action=action_map.get(target_status, target_status),
                actor_id=actor_id,
                actor_role=actor_role,
                notes=notes,
            )
            db.add(event)
            db.commit()
            db.refresh(course)
            return course

    def detect_impacted_courses(
        self,
        *,
        tenant_id: str = "default",
        mark_needs_update: bool = True,
    ) -> list[dict[str, Any]]:
        """Identify courses whose underlying DocumentMetadata hashes changed or were deleted."""
        impacted: list[dict[str, Any]] = []
        with self.db.session() as db:
            courses = db.query(Course).filter_by(tenant_id=tenant_id).all()
            meta_rows = db.query(DocumentMetadata).all()
            current_hashes = {m.document_id: m.file_hash for m in meta_rows if m.status == "indexed"}

            for c in courses:
                if not c.source_hashes:
                    continue
                changed_docs: list[str] = []
                deleted_docs: list[str] = []
                for doc_id, old_hash in c.source_hashes.items():
                    cur = current_hashes.get(doc_id)
                    if cur is None:
                        deleted_docs.append(doc_id)
                    elif cur != old_hash:
                        changed_docs.append(doc_id)

                if changed_docs or deleted_docs:
                    prev_status = c.lifecycle_status
                    if mark_needs_update and prev_status != "NEEDS_UPDATE":
                        c.lifecycle_status = "NEEDS_UPDATE"
                        db.add(
                            CourseApprovalEvent(
                                course_id=c.id,
                                from_status=prev_status,
                                to_status="NEEDS_UPDATE",
                                action="FLAG_SOURCE_CHANGE",
                                actor_id="system",
                                actor_role="system",
                                notes=f"Fonti modificate: {changed_docs}; rimosse: {deleted_docs}",
                            )
                        )
                    impacted.append(
                        {
                            "course_id": c.id,
                            "title": c.title,
                            "previous_status": prev_status,
                            "current_status": c.lifecycle_status,
                            "changed_document_ids": changed_docs,
                            "deleted_document_ids": deleted_docs,
                        }
                    )
            db.commit()
        return impacted
