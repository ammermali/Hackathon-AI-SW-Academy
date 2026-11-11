"""AI Course Generator converting TrainingOpportunities into grounded courses, lessons, and quizzes."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy.orm import joinedload

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.course_generator.grounding_verifier import GroundingVerifier
from operator_copilot.course_generator.lifecycle import CourseLifecycleManager
from operator_copilot.course_generator.prompts import CURRICULUM_PROMPT, LESSON_PROMPT, QUIZ_PROMPT
from operator_copilot.course_generator.quiz_helpers import (
    build_contextual_distractors,
    build_natural_focus,
    clean_markdown_to_plain,
    deterministic_shuffle_options,
    extract_natural_quiz_statements,
    is_usable_quiz_text,
    short_document_label,
    short_section_label,
    truncate_at_boundary,
)
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import (
    Course,
    CourseApprovalEvent,
    CourseModule,
    ExtractedTopic,
    Lesson,
    LessonSource,
    Quiz,
    QuizQuestion,
    TrainingOpportunity,
)
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.ingestion.normalizer import strip_area_prefix
from operator_copilot.knowledge_intelligence.classifier import TopicClassifier
from operator_copilot.knowledge_intelligence.extractor import KnowledgeExtractor
from operator_copilot.knowledge_intelligence.opportunities import OpportunityAggregator
from operator_copilot.knowledge_intelligence.scorer import RelevanceScorer
from operator_copilot.schemas.academy import (
    CurriculumLLMOutput,
    LessonGenerationLLMOutput,
    QuizGenerationLLMOutput,
)

logger = logging.getLogger("operator_copilot.course_generator.generator")


class AICourseGenerator:
    """Transforms TrainingOpportunities or documents into grounded courses, modules, lessons, and quizzes."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
        extractor: KnowledgeExtractor | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.generator = generator or AnswerGenerator(self.settings)
        self.extractor = extractor or KnowledgeExtractor(self.settings, self.db, generator=self.generator)
        self.verifier = GroundingVerifier(self.settings, self.db, generator=self.generator)
        self.lifecycle = CourseLifecycleManager(self.db)

    @staticmethod
    def _clean_text(text: str) -> str:
        return strip_area_prefix(text)

    def _load_topics_for_opportunity(self, opp: TrainingOpportunity) -> list[ExtractedTopic]:
        with self.db.session() as db:
            if opp.topic_ids:
                topics = (
                    db.query(ExtractedTopic)
                    .filter(ExtractedTopic.id.in_(opp.topic_ids), ExtractedTopic.tenant_id == opp.tenant_id)
                    .all()
                )
                if topics:
                    return topics
            doc_ids = [d.get("document_id") for d in opp.source_documents if d.get("document_id")]
            if doc_ids:
                return (
                    db.query(ExtractedTopic)
                    .filter(ExtractedTopic.document_id.in_(doc_ids), ExtractedTopic.tenant_id == opp.tenant_id)
                    .all()
                )
        return []

    def generate_from_document(
        self,
        doc_ref: str,
        *,
        tenant_id: str = "default",
        allowed_roles: list[str] | None = None,
        course_type: str | None = None,
        created_by: str = "system",
    ) -> Course:
        """Analyze a single document if needed, propose an opportunity, and generate a Course."""
        bundle = self.extractor.load_document_bundle(doc_ref)
        if bundle is None:
            raise ValueError(f"Documento '{doc_ref}' non trovato nella knowledge base o in data/.")

        classifier = TopicClassifier(generator=self.generator)
        scorer = RelevanceScorer(self.db, generator=self.generator)
        aggregator = OpportunityAggregator(self.db, retriever=self.extractor.retriever)

        topic = self.extractor.extract_from_bundle(
            bundle,
            tenant_id=tenant_id,
            allowed_roles=allowed_roles,
            classifier=classifier,
        )
        scorer.score_topic(topic, persist=True)
        opp = aggregator.build_opportunity_from_topics([topic], tenant_id=tenant_id, persist=True)
        return self.generate_from_opportunity(
            opp.id,
            tenant_id=tenant_id,
            course_type=course_type,
            created_by=created_by,
        )

    def generate_from_opportunity(
        self,
        opportunity_id: str,
        *,
        tenant_id: str = "default",
        course_type: str | None = None,
        created_by: str = "system",
    ) -> Course:
        """Transform an existing TrainingOpportunity into a persisted Course (never auto-published)."""
        with self.db.session() as db:
            opp = db.query(TrainingOpportunity).filter_by(id=opportunity_id, tenant_id=tenant_id).first()
            if opp is None:
                raise ValueError(f"Proposta formativa '{opportunity_id}' non trovata per il tenant '{tenant_id}'.")

        topics = self._load_topics_for_opportunity(opp)
        if not topics:
            raise ValueError("Nessun contenuto estratto disponibile per la proposta formativa selezionata.")

        effective_type = course_type or opp.course_type or "documental"
        model_info = self.generator.get_model_info()
        model_label = (
            f"{model_info['provider']}:{model_info['configured_model']}"
            if model_info["llm_runtime_active"]
            else f"deterministic_fallback(expected={model_info['configured_model']})"
        )

        all_passages = [p for t in topics for p in t.source_passages]
        source_hashes = {t.document_id: t.file_hash for t in topics}
        context_preview = "\n\n".join(
            f"[{p.get('source')} | section={p.get('section')} | chunk_id={p.get('chunk_id')}]: {p.get('excerpt', '')}"
            for p in all_passages[:14]
        )

        # 1. Curriculum generation via centralized LLM (Qwen) with grounded fallback
        curriculum_llm, used_llm, _ = self.generator.invoke_structured(
            CURRICULUM_PROMPT,
            {
                "course_type": "documentale" if effective_type == "documental" else "applicativo",
                "opportunity_title": opp.title,
                "learning_objective": opp.learning_objective,
                "context": context_preview,
            },
            CurriculumLLMOutput,
        )

        course_id = f"crs_{uuid.uuid4().hex[:12]}"
        course = Course(
            id=course_id,
            opportunity_id=opp.id,
            tenant_id=tenant_id,
            allowed_roles=list(opp.allowed_roles or ["operatore", "admin"]),
            title=curriculum_llm.title if (curriculum_llm and used_llm) else opp.title,
            description=curriculum_llm.description if (curriculum_llm and used_llm) else opp.description,
            course_type=effective_type,
            learning_objectives=(
                curriculum_llm.learning_objectives
                if (curriculum_llm and used_llm and curriculum_llm.learning_objectives)
                else [
                    opp.learning_objective,
                    *[f"Applicare le indicazioni di '{t.title}' evitando gli errori documentati." for t in topics[:2]],
                ]
            ),
            prerequisites=(
                curriculum_llm.prerequisites
                if (curriculum_llm and used_llm and curriculum_llm.prerequisites)
                else [
                    f"Accesso operativo ai moduli: {', '.join(opp.software_modules[:3])}"
                    if opp.software_modules
                    else "Conoscenza base dell'operatività d'ufficio PA."
                ]
            ),
            target_audience=list(opp.suggested_audience or ["Operatore PA"]),
            difficulty=opp.difficulty,
            summary=(
                curriculum_llm.summary
                if (curriculum_llm and used_llm and curriculum_llm.summary)
                else f"Percorso basato su {len(topics)} documento/i verificato/i ({', '.join(t.source for t in topics[:3])})."
            ),
            lifecycle_status="GENERATED",
            current_version=1,
            corpus_version_at_generation=self.db.get_corpus_version(),
            source_hashes=source_hashes,
            grounding_status="VERIFIED",
            model_used=model_label,
            created_by=created_by,
        )

        modules_data = self._build_modules_payload(
            topics=topics,
            course_type=effective_type,
            curriculum_llm=curriculum_llm if used_llm else None,
        )

        with self.db.session() as db:
            db.add(course)
            for m_idx, mod_spec in enumerate(modules_data, start=1):
                mod_id = f"mod_{uuid.uuid4().hex[:12]}"
                mod_row = CourseModule(
                    id=mod_id,
                    course_id=course_id,
                    order_index=m_idx,
                    title=mod_spec["title"],
                    description=mod_spec["description"],
                    learning_objective=mod_spec["learning_objective"],
                )
                db.add(mod_row)

                for l_idx, les_spec in enumerate(mod_spec["lessons"], start=1):
                    les_id = f"les_{uuid.uuid4().hex[:12]}"
                    les_row = Lesson(
                        id=les_id,
                        module_id=mod_id,
                        course_id=course_id,
                        order_index=l_idx,
                        title=les_spec["title"],
                        objective=les_spec["objective"],
                        explanation=les_spec["explanation"],
                        procedures=les_spec["procedures"],
                        practical_examples=les_spec["practical_examples"],
                        frequent_errors=les_spec["frequent_errors"],
                        exercises=les_spec["exercises"],
                        summary=les_spec["summary"],
                    )
                    db.add(les_row)
                    for src in les_spec["sources"]:
                        db.add(
                            LessonSource(
                                lesson_id=les_id,
                                document_id=str(src["document_id"]),
                                document_title=str(src["document_title"]),
                                document_version=str(src.get("document_version") or "unknown"),
                                chunk_id=str(src["chunk_id"]),
                                page=src.get("page"),
                                section=str(src.get("section") or ""),
                                source=str(src["source"]),
                                updated_at=str(src.get("updated_at") or ""),
                                excerpt=str(src.get("excerpt") or ""),
                            )
                        )

            opp_row = db.get(TrainingOpportunity, opp.id)
            if opp_row is not None:
                opp_row.status = "CONVERTED"

            db.add(
                CourseApprovalEvent(
                    course_id=course_id,
                    from_status="PROPOSED",
                    to_status="GENERATED",
                    action="GENERATE",
                    actor_id=created_by,
                    actor_role="system",
                    notes=f"Generazione iniziale da proposta '{opp.id}' ({model_label}).",
                )
            )
            db.commit()

        # Generate grounded assessment quiz, initial revision snapshot, and verify grounding
        self.generate_quiz(course_id, tenant_id=tenant_id, num_questions=min(6, max(3, len(all_passages))))
        self.verifier.verify_course(course_id, tenant_id=tenant_id)
        self.lifecycle.record_revision(
            course_id,
            change_summary="Versione iniziale generata dal motore AI Knowledge-to-Course.",
            changed_by=created_by,
        )

        return self.get_course(course_id, tenant_id=tenant_id)  # type: ignore[return-value]

    def _build_modules_payload(
        self,
        *,
        topics: list[ExtractedTopic],
        course_type: str,
        curriculum_llm: CurriculumLLMOutput | None,
    ) -> list[dict[str, Any]]:
        """Construct non-repetitive curriculum modules and grounded lessons strictly from source passages."""
        all_passages = [p for t in topics for p in t.source_passages]
        modules_out: list[dict[str, Any]] = []

        if curriculum_llm is not None and curriculum_llm.modules:
            for mod_plan in curriculum_llm.modules:
                lessons_out: list[dict[str, Any]] = []
                for les_plan in mod_plan.lessons:
                    matched_passages = self._match_passages(les_plan.source_sections, all_passages)
                    lessons_out.append(
                        self._synthesize_lesson(
                            title=les_plan.title,
                            objective=les_plan.objective,
                            passages=matched_passages,
                            topics=topics,
                            course_type=course_type,
                        )
                    )
                if lessons_out:
                    modules_out.append(
                        {
                            "title": mod_plan.title,
                            "description": mod_plan.description,
                            "learning_objective": mod_plan.learning_objective,
                            "lessons": lessons_out,
                        }
                    )
            if modules_out:
                return modules_out

        # Deterministic structured curriculum directly driven by real document sections
        for t in topics:
            passages = t.source_passages
            if not passages:
                continue
            grouped = self._group_passages_by_theme(passages)
            lessons_for_topic: list[dict[str, Any]] = []
            for group_title, group_passages in grouped:
                lessons_for_topic.append(
                    self._synthesize_lesson(
                        title=group_title,
                        objective=f"Comprendere e applicare correttamente i contenuti della sezione '{group_title}'.",
                        passages=group_passages,
                        topics=[t],
                        course_type=course_type,
                    )
                )
            if lessons_for_topic:
                modules_out.append(
                    {
                        "title": f"{t.title}",
                        "description": f"Modulo basato su '{t.source}' ({t.category}).",
                        "learning_objective": f"Padroneggiare regole, procedure ed errori relativi a: {t.title}.",
                        "lessons": lessons_for_topic,
                    }
                )
        return modules_out

    @staticmethod
    def _group_passages_by_theme(passages: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
        """Group real chunks by top-level section H2 without fabricating artificial extra lessons."""
        buckets: dict[str, list[dict[str, Any]]] = {}
        for p in passages:
            sec = str(p.get("section") or "Contenuti principali")
            parts = [s.strip() for s in sec.split(">") if s.strip()]
            key = parts[1] if len(parts) >= 2 else parts[0]
            buckets.setdefault(key, []).append(p)
        return list(buckets.items())[:6]

    @staticmethod
    def _match_passages(section_hints: list[str], passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not section_hints:
            return passages[:3]
        matched: list[dict[str, Any]] = []
        for p in passages:
            sec_l = str(p.get("section") or "").lower()
            if any(h.lower() in sec_l for h in section_hints):
                matched.append(p)
        return matched or passages[:3]

    def _synthesize_lesson(
        self,
        *,
        title: str,
        objective: str,
        passages: list[dict[str, Any]],
        topics: list[ExtractedTopic],
        course_type: str,
    ) -> dict[str, Any]:
        """Generate one autonomous grounded lesson via LLM (Qwen) or deterministic synthesis."""
        ctx = "\n\n".join(
            f"[Fonte={p['source']} | Sezione={p['section']} | Chunk={p['chunk_id']}]\n{p.get('excerpt', '')}"
            for p in passages
        )
        parsed_llm, used_llm, _ = self.generator.invoke_structured(
            LESSON_PROMPT,
            {"lesson_title": title, "lesson_objective": objective, "context": ctx},
            LessonGenerationLLMOutput,
        )
        if parsed_llm is not None and used_llm:
            return {
                "title": parsed_llm.title or title,
                "objective": parsed_llm.objective or objective,
                "explanation": parsed_llm.explanation,
                "procedures": parsed_llm.procedures,
                "practical_examples": parsed_llm.practical_examples,
                "frequent_errors": parsed_llm.frequent_errors,
                "exercises": parsed_llm.exercises,
                "summary": parsed_llm.summary,
                "sources": passages,
            }

        # Deterministic strictly grounded synthesis from source passages & extracted artifacts
        pass_sections = {str(p.get("section") or "").lower() for p in passages}
        relevant_procs: list[str] = []
        relevant_examples: list[dict[str, Any]] = []
        relevant_errors: list[dict[str, Any]] = []
        relevant_rules: list[str] = []

        for t in topics:
            for proc in t.procedures:
                if not pass_sections or any(s in str(proc.get("section", "")).lower() or str(proc.get("section", "")).lower() in s for s in pass_sections):
                    for step in proc.get("steps", []):
                        if step not in relevant_procs:
                            relevant_procs.append(step)
            for ex in t.practical_examples:
                ex_sec = str(ex.get("section", "")).lower()
                if any(ex_sec in s or s in ex_sec for s in pass_sections) or "esemp" in title.lower():
                    relevant_examples.append(ex)
            for err in t.frequent_errors:
                err_sec = str(err.get("section", "")).lower()
                if any(err_sec in s or s in err_sec for s in pass_sections) or "err" in title.lower() or "ticket" in title.lower():
                    relevant_errors.append(err)
            relevant_rules.extend(t.rules[:4])

        excerpts_text = "\n\n".join(
            f"**{p.get('section') or p.get('document_title')}** (`{p.get('chunk_id')}`):\n{p.get('excerpt', '')}"
            for p in passages[:4]
        )
        mode_label = "procedura applicativa" if course_type == "applicative" else "norma e procedura operativa"
        explanation = (
            f"Questa lezione illustra la {mode_label} relativa a **{title}**, sulla base esclusiva delle fonti documentali collegate:\n\n"
            f"{excerpts_text}"
        )

        exercises: list[dict[str, Any]] = []
        if relevant_procs or relevant_rules or relevant_examples:
            exercises.append(
                {
                    "title": f"Esercitazione pratica: {title}",
                    "scenario": f"Applicare le indicazioni della sezione '{passages[0].get('section')}' in un caso operativo reale.",
                    "expected_steps": relevant_procs[:4] if relevant_procs else relevant_rules[:4],
                    "source_section": passages[0].get("section", ""),
                }
            )

        summary = (
            f"Riepilogo verificato su {len(passages)} passaggi sorgente ({passages[0].get('source')}, sezione '{passages[0].get('section')}'). "
            + (f"Punti chiave: {'; '.join(relevant_rules[:2])}." if relevant_rules else "")
        ).strip()

        return {
            "title": title,
            "objective": objective,
            "explanation": explanation,
            "procedures": relevant_procs[:10],
            "practical_examples": relevant_examples[:6],
            "frequent_errors": relevant_errors[:6],
            "exercises": exercises,
            "summary": summary,
            "sources": passages,
        }

    def regenerate_lesson(
        self,
        course_id: str,
        lesson_id: str,
        *,
        tenant_id: str = "default",
        actor_id: str = "system",
    ) -> Lesson:
        """Regenerate one existing lesson from its linked sources and record a CourseRevision."""
        with self.db.session() as db:
            course = db.query(Course).filter_by(id=course_id, tenant_id=tenant_id).first()
            if course is None:
                raise ValueError(f"Corso '{course_id}' non trovato.")
            lesson = (
                db.query(Lesson)
                .options(joinedload(Lesson.sources))
                .filter_by(id=lesson_id, course_id=course_id)
                .first()
            )
            if lesson is None:
                raise ValueError(f"Lezione '{lesson_id}' non trovata nel corso '{course_id}'.")

            passages = [
                {
                    "document_id": s.document_id,
                    "document_title": s.document_title,
                    "document_version": s.document_version,
                    "chunk_id": s.chunk_id,
                    "page": s.page,
                    "section": s.section,
                    "source": s.source,
                    "updated_at": s.updated_at,
                    "excerpt": s.excerpt,
                }
                for s in lesson.sources
            ]
            doc_ids = list({s.document_id for s in lesson.sources})
            topics = (
                db.query(ExtractedTopic)
                .filter(ExtractedTopic.document_id.in_(doc_ids), ExtractedTopic.tenant_id == tenant_id)
                .all()
                if doc_ids
                else []
            )
            synth = self._synthesize_lesson(
                title=lesson.title,
                objective=lesson.objective,
                passages=passages,
                topics=topics,
                course_type=course.course_type,
            )
            lesson.explanation = synth["explanation"]
            lesson.procedures = synth["procedures"]
            lesson.practical_examples = synth["practical_examples"]
            lesson.frequent_errors = synth["frequent_errors"]
            lesson.exercises = synth["exercises"]
            lesson.summary = synth["summary"]
            db.commit()

        self.verifier.verify_course(course_id, tenant_id=tenant_id)
        self.lifecycle.record_revision(
            course_id,
            change_summary=f"Rigenerata lezione '{lesson_id}'.",
            changed_by=actor_id,
        )
        with self.db.session() as db:
            return (
                db.query(Lesson)
                .options(joinedload(Lesson.sources))
                .filter_by(id=lesson_id)
                .first()
            )  # type: ignore[return-value]

    def generate_quiz(
        self,
        course_id: str,
        *,
        tenant_id: str = "default",
        lesson_id: str | None = None,
        num_questions: int = 5,
    ) -> Quiz:
        """Generate grounded quiz questions linked strictly to LessonSources."""
        with self.db.session() as db:
            course = (
                db.query(Course)
                .options(joinedload(Course.modules).joinedload(CourseModule.lessons).joinedload(Lesson.sources))
                .filter_by(id=course_id, tenant_id=tenant_id)
                .first()
            )
            if course is None:
                raise ValueError(f"Corso '{course_id}' non trovato.")

            target_lessons = [
                les
                for mod in course.modules
                for les in mod.lessons
                if lesson_id is None or les.id == lesson_id
            ]
            sources = [s for les in target_lessons for s in les.sources]
            lesson_procedures = [
                (les.title, step)
                for les in target_lessons
                for step in (les.procedures or [])
                if isinstance(step, str) and step.strip()
            ]
            lesson_errors = [
                (les.title, err)
                for les in target_lessons
                for err in (les.frequent_errors or [])
                if isinstance(err, dict)
            ]
            target_title = target_lessons[0].title if (lesson_id and target_lessons) else course.title

        ctx = "\n\n".join(
            f"[Doc={s.document_id} | Sezione={s.section} | Chunk={s.chunk_id}]\n{s.excerpt}"
            for s in sources[:8]
        )
        parsed_llm, used_llm, _ = self.generator.invoke_structured(
            QUIZ_PROMPT,
            {"target_title": target_title, "num_questions": num_questions, "context": ctx},
            QuizGenerationLLMOutput,
        )

        questions_payload: list[dict[str, Any]] = []
        if parsed_llm is not None and used_llm and parsed_llm.questions:
            for q in parsed_llm.questions[:num_questions]:
                matched_src = next(
                    (s for s in sources if q.source_section and q.source_section.lower() in s.section.lower()),
                    sources[0] if sources else None,
                )
                questions_payload.append(
                    {
                        "question_type": q.question_type,
                        "question_text": clean_markdown_to_plain(q.question_text),
                        "options": [clean_markdown_to_plain(opt) for opt in q.options],
                        "correct_answer": clean_markdown_to_plain(q.correct_answer),
                        "explanation": clean_markdown_to_plain(q.explanation),
                        "source_document_id": matched_src.document_id if matched_src else "",
                        "source_chunk_id": matched_src.chunk_id if matched_src else "",
                        "source_section": matched_src.section if matched_src else q.source_section,
                    }
                )
        else:
            # Deterministic grounded quiz builder using real course errors, cross-section procedures, and shuffled options
            seen_q: set[str] = set()
            seen_answers: set[str] = set()
            course_antipatterns = [
                clean_markdown_to_plain(str(err_item.get("error_or_antipattern") or ""))
                for _, err_item in lesson_errors
                if is_usable_quiz_text(
                    clean_markdown_to_plain(str(err_item.get("error_or_antipattern") or "")),
                    min_len=30,
                )
            ]
            course_fixes = [
                clean_markdown_to_plain(str(err_item.get("consequence_or_fix") or ""))
                for _, err_item in lesson_errors
                if is_usable_quiz_text(
                    clean_markdown_to_plain(str(err_item.get("consequence_or_fix") or "")),
                    min_len=25,
                )
            ] + [
                clean_markdown_to_plain(step)
                for _, step in lesson_procedures
                if is_usable_quiz_text(clean_markdown_to_plain(step), min_len=25)
            ]
            section_stmts: list[tuple[str, str]] = []
            for src in sources:
                for st in extract_natural_quiz_statements(src.excerpt, min_len=35, max_len=165):
                    section_stmts.append((src.section, st))

            # 1. Prioritize real frequent errors when available
            for idx, (les_title, err_item) in enumerate(lesson_errors):
                if len(questions_payload) >= num_questions:
                    break
                err_text = truncate_at_boundary(str(err_item.get("error_or_antipattern") or ""), max_len=165)
                if not is_usable_quiz_text(err_text, min_len=30):
                    continue
                if err_text.lower() in seen_answers:
                    continue
                err_sec = str(err_item.get("section") or "").strip()
                matched_src = (
                    next((s for s in sources if err_sec and err_sec.lower() in s.section.lower()), None)
                    or (sources[idx % len(sources)] if sources else None)
                )
                focus = build_natural_focus(err_sec or (matched_src.section if matched_src else ""), les_title)
                doc_short = short_document_label(matched_src.source if matched_src else "")
                q_text = f"In riferimento a «{focus}», quale comportamento o anomalia va evitata perché causa un blocco? (Fonte: {doc_short})"
                if q_text.lower() in seen_q:
                    continue
                seen_q.add(q_text.lower())
                seen_answers.add(err_text.lower())
                err_fix = clean_markdown_to_plain(str(err_item.get("consequence_or_fix") or ""))
                prioritized_fixes = ([err_fix] if len(err_fix) >= 25 else []) + course_fixes
                distractors = build_contextual_distractors(
                    correct_option=err_text,
                    focus=focus,
                    mode="avoid_error",
                    domain_wrong_pool=prioritized_fixes,
                    other_section_pool=[st for _, st in section_stmts],
                )
                opts, _ = deterministic_shuffle_options(
                    err_text,
                    distractors,
                    seed_key=f"{course_id}:err:{idx}:{err_text[:40]}",
                )
                questions_payload.append(
                    {
                        "question_type": "multiple_choice",
                        "question_text": q_text,
                        "options": opts,
                        "correct_answer": err_text,
                        "explanation": f"Regola operativa tratta da «{focus}» ({doc_short}).",
                        "source_document_id": matched_src.document_id if matched_src else "",
                        "source_chunk_id": matched_src.chunk_id if matched_src else "",
                        "source_section": matched_src.section if matched_src else les_title,
                    }
                )

            # 2. Extract clean factual statements from lesson sources (natural phrasing + contextual distractors)
            for idx, src in enumerate(sources):
                if len(questions_payload) >= num_questions:
                    break
                stmts = extract_natural_quiz_statements(src.excerpt, min_len=40, max_len=165)
                if not stmts:
                    continue
                stmt = next((s for s in stmts if s.lower() not in seen_answers), None)
                if stmt is None:
                    continue
                focus = build_natural_focus(src.section, src.document_title)
                doc_short = short_document_label(src.source)
                other_sec_stmts = [st for sec, st in section_stmts if sec != src.section]

                if idx % 2 == 0:
                    q_text = f"Nell'ambito di «{focus}», quale indicazione operativa occorre seguire? (Fonte: {doc_short})"
                    if q_text.lower() in seen_q:
                        continue
                    seen_q.add(q_text.lower())
                    seen_answers.add(stmt.lower())
                    distractors = build_contextual_distractors(
                        correct_option=stmt,
                        focus=focus,
                        mode="correct_rule",
                        domain_wrong_pool=course_antipatterns,
                        other_section_pool=other_sec_stmts,
                    )
                    opts, _ = deterministic_shuffle_options(
                        stmt,
                        distractors,
                        seed_key=f"{course_id}:{src.chunk_id}:{idx}",
                    )
                    questions_payload.append(
                        {
                            "question_type": "multiple_choice",
                            "question_text": q_text,
                            "options": opts,
                            "correct_answer": stmt,
                            "explanation": f"Verifica diretta nella sezione «{short_section_label(src.section)}» ({doc_short}).",
                            "source_document_id": src.document_id,
                            "source_chunk_id": src.chunk_id,
                            "source_section": src.section,
                        }
                    )
                else:
                    q_text = f"Vero o Falso — Riguardo a «{focus}», vale questa regola: \"{stmt}\" (Fonte: {doc_short})"
                    if q_text.lower() in seen_q:
                        continue
                    seen_q.add(q_text.lower())
                    questions_payload.append(
                        {
                            "question_type": "true_false",
                            "question_text": q_text,
                            "options": ["Vero", "Falso"],
                            "correct_answer": "Vero",
                            "explanation": f"Confermato nella sezione «{short_section_label(src.section)}» ({doc_short}).",
                            "source_document_id": src.document_id,
                            "source_chunk_id": src.chunk_id,
                            "source_section": src.section,
                        }
                    )

            # 3. Top up remaining slots from lesson procedures if sources were sparse
            for idx, (les_title, raw_step) in enumerate(lesson_procedures):
                if len(questions_payload) >= num_questions:
                    break
                if "seguire quanto indicato nella sezione" in raw_step.lower():
                    continue
                stmt = truncate_at_boundary(raw_step, max_len=165)
                if len(stmt) < 35 or stmt.lower() in seen_answers:
                    continue
                matched_src = sources[idx % len(sources)] if sources else None
                doc_short = short_document_label(matched_src.source if matched_src else "")
                focus = build_natural_focus(matched_src.section if matched_src else "", les_title)
                q_text = f"Quale regola operativa si applica durante «{focus}»? (Fonte: {doc_short})"
                if q_text.lower() in seen_q:
                    continue
                seen_q.add(q_text.lower())
                seen_answers.add(stmt.lower())
                distractors = build_contextual_distractors(
                    correct_option=stmt,
                    focus=focus,
                    mode="correct_rule",
                    domain_wrong_pool=course_antipatterns,
                    other_section_pool=[st for _, st in section_stmts],
                )
                opts, _ = deterministic_shuffle_options(
                    stmt,
                    distractors,
                    seed_key=f"{course_id}:proc:{idx}",
                )
                questions_payload.append(
                    {
                        "question_type": "multiple_choice",
                        "question_text": q_text,
                        "options": opts,
                        "correct_answer": stmt,
                        "explanation": f"Procedura documentata per «{les_title}» ({doc_short}).",
                        "source_document_id": matched_src.document_id if matched_src else "",
                        "source_chunk_id": matched_src.chunk_id if matched_src else "",
                        "source_section": matched_src.section if matched_src else les_title,
                    }
                )

        quiz_id = f"quiz_{uuid.uuid4().hex[:12]}"
        with self.db.session() as db:
            quiz_row = Quiz(
                id=quiz_id,
                course_id=course_id,
                lesson_id=lesson_id,
                title=parsed_llm.title if (parsed_llm and used_llm) else f"Verifica finale: {target_title}",
                passing_score=70,
            )
            db.add(quiz_row)
            for idx, q in enumerate(questions_payload, start=1):
                db.add(
                    QuizQuestion(
                        id=f"qq_{uuid.uuid4().hex[:12]}",
                        quiz_id=quiz_id,
                        order_index=idx,
                        question_type=q["question_type"],
                        question_text=q["question_text"],
                        options=q["options"],
                        correct_answer=q["correct_answer"],
                        explanation=q["explanation"],
                        source_document_id=q["source_document_id"],
                        source_chunk_id=q["source_chunk_id"],
                        source_section=q["source_section"],
                    )
                )
            db.commit()
            return (
                db.query(Quiz)
                .options(joinedload(Quiz.questions))
                .filter_by(id=quiz_id)
                .first()
            )  # type: ignore[return-value]

    def get_course(self, course_id: str, *, tenant_id: str = "default") -> Course | None:
        with self.db.session() as db:
            return (
                db.query(Course)
                .options(
                    joinedload(Course.modules).joinedload(CourseModule.lessons).joinedload(Lesson.sources),
                    joinedload(Course.quizzes).joinedload(Quiz.questions),
                )
                .filter_by(id=course_id, tenant_id=tenant_id)
                .first()
            )
