"""Grounding and source traceability verifier for generated courses and lessons."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import joinedload

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.course_generator.prompts import SOURCE_VERIFICATION_PROMPT
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import Course, CourseModule, DocumentMetadata, Lesson
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.schemas.academy import GroundingCheckLLMOutput

_TOKEN_RE = re.compile(r"\b[a-z0-9]{4,}\b")


class GroundingVerifier:
    """Validates lesson citations, detects unsupported claims, outdated sources, and version conflicts."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.generator = generator

    @staticmethod
    def _lexical_overlap(claim_text: str, source_text: str) -> float:
        c_tokens = set(_TOKEN_RE.findall(claim_text.lower()))
        if not c_tokens:
            return 1.0
        s_tokens = set(_TOKEN_RE.findall(source_text.lower()))
        return len(c_tokens & s_tokens) / len(c_tokens)

    def verify_course(self, course_id: str, *, tenant_id: str = "default") -> dict[str, Any]:
        """Verify all lessons and sources of a course, persisting grounding_status and warnings."""
        current_year = datetime.now(timezone.utc).year
        lesson_reports: list[dict[str, Any]] = []
        global_warnings: list[str] = []
        unverified_count = 0

        with self.db.session() as db:
            course = (
                db.query(Course)
                .options(joinedload(Course.modules).joinedload(CourseModule.lessons).joinedload(Lesson.sources))
                .filter_by(id=course_id, tenant_id=tenant_id)
                .first()
            )
            if course is None:
                raise ValueError(f"Corso '{course_id}' non trovato per il tenant '{tenant_id}'.")

            all_doc_ids = {
                src.document_id
                for mod in course.modules
                for les in mod.lessons
                for src in les.sources
            }
            meta_rows = (
                db.query(DocumentMetadata).filter(DocumentMetadata.document_id.in_(all_doc_ids)).all()
                if all_doc_ids
                else []
            )
            meta_by_id = {m.document_id: m for m in meta_rows}
            years_seen = sorted({m.doc_year for m in meta_rows if m.doc_year is not None})

            if len(years_seen) > 1 and (max(years_seen) - min(years_seen)) >= 2:
                global_warnings.append(
                    f"Versioni/annualità differenti nelle fonti collegate ({years_seen[0]}..{years_seen[-1]}): verificare coerenza normativa/software."
                )

            for mod in course.modules:
                for lesson in mod.lessons:
                    warnings: list[str] = []
                    is_grounded = True

                    if not lesson.sources:
                        is_grounded = False
                        warnings.append("Lezione priva di fonti collegate (LessonSource assente).")
                    else:
                        combined_excerpts = " ".join(s.excerpt for s in lesson.sources)
                        combined_body = " ".join(
                            [lesson.explanation] + lesson.procedures + [lesson.summary]
                        )
                        overlap = self._lexical_overlap(combined_body, combined_excerpts)
                        if combined_excerpts.strip() and overlap < 0.15:
                            warnings.append(
                                f"Bassa corrispondenza lessicale ({overlap:.2f}) tra contenuto e passaggi sorgente: verificare possibili inferenze LLM."
                            )

                        # Check outdated / deleted / conflicting software versions
                        for src in lesson.sources:
                            m = meta_by_id.get(src.document_id)
                            if m is None and src.document_id:
                                warnings.append(f"Fonte '{src.source}' non presente nell'indice DocumentMetadata corrente.")
                            elif m is not None and m.doc_year is not None:
                                if (current_year - m.doc_year) >= self.settings.knowledge_obsolete_years:
                                    warnings.append(
                                        f"Fonte potenzialmente obsoleta: '{src.source}' (anno {m.doc_year})."
                                    )

                        if "cityware client" in combined_excerpts.lower() and "cwol" in combined_excerpts.lower():
                            warnings.append("Co-presenza di riferimenti Cityware Client e CWOL: verificare applicabilità alla versione attuale.")

                        # Optional semantic LLM source verification when active
                        if self.generator is not None and combined_excerpts.strip():
                            parsed, used_llm, _ = self.generator.invoke_structured(
                                SOURCE_VERIFICATION_PROMPT,
                                {
                                    "lesson_content": f"{lesson.title}\n{lesson.explanation}\n" + "\n".join(lesson.procedures),
                                    "context": combined_excerpts[:3500],
                                },
                                GroundingCheckLLMOutput,
                            )
                            if parsed is not None and used_llm:
                                if not parsed.is_grounded or parsed.unsupported_claims:
                                    is_grounded = False
                                    warnings.extend(
                                        [f"Affermazione non supportata: {c}" for c in parsed.unsupported_claims[:3]]
                                    )
                                if parsed.contradictions_detected:
                                    warnings.extend(
                                        [f"Contraddizione rilevata: {c}" for c in parsed.contradictions_detected[:3]]
                                    )

                    if not is_grounded:
                        unverified_count += 1

                    lesson.is_grounded = is_grounded
                    lesson.grounding_warnings = warnings
                    lesson_reports.append(
                        {
                            "lesson_id": lesson.id,
                            "lesson_title": lesson.title,
                            "sources_count": len(lesson.sources),
                            "is_grounded": is_grounded,
                            "warnings": warnings,
                        }
                    )

            if unverified_count > 0:
                course.grounding_status = "UNVERIFIED"
            elif global_warnings or any(r["warnings"] for r in lesson_reports):
                course.grounding_status = "WARNINGS"
            else:
                course.grounding_status = "VERIFIED"

            report = {
                "course_id": course.id,
                "grounding_status": course.grounding_status,
                "global_warnings": global_warnings,
                "lessons_checked": len(lesson_reports),
                "unverified_lessons": unverified_count,
                "lesson_reports": lesson_reports,
            }
            course.grounding_report = report
            db.commit()
            return report
