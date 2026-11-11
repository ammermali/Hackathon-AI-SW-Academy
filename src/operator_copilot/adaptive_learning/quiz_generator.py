"""Personalized Custom Quiz Generator grounded in existing RAG retrieval and Qwen."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import joinedload

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.course_generator.prompts import CUSTOM_QUIZ_PROMPT
from operator_copilot.course_generator.quiz_helpers import (
    build_natural_focus,
    clean_markdown_to_plain,
    extract_natural_quiz_statements,
    short_document_label,
    short_section_label,
)
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import CustomQuiz, CustomQuizAttempt, CustomQuizQuestion, ExtractedTopic
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.ingestion.normalizer import strip_area_prefix
from operator_copilot.retrieval.retriever import HybridRetriever
from operator_copilot.schemas.customquiz import CustomQuizGenerationLLM

logger = logging.getLogger("operator_copilot.adaptive_learning.quiz_generator")

_LETTERS = ("A", "B", "C", "D")


def _normalize_question_hash(text: str) -> str:
    norm = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


class CustomQuizGenerator:
    """Generates and persists 4-option user-specific Custom Quizzes with idempotency & Qwen support."""

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
        self._executor = ThreadPoolExecutor(
            max_workers=self.settings.analysis_max_workers,
            thread_name_prefix="customquiz-gen",
        )

    def _collect_grounded_passages(
        self,
        *,
        targets: list[dict[str, Any]],
        tenant_id: str,
        software: str,
        module_name: str,
    ) -> list[dict[str, Any]]:
        """Retrieve verifiable passages from existing HybridRetriever and ExtractedTopic sources."""
        passages: list[dict[str, Any]] = []
        seen_chunks: set[str] = set()

        for target in targets:
            topic_str = str(target.get("topic") or "")
            query_hints = " ".join(str(q) for q in (target.get("rag_queries") or [])[:2])
            query_text = f"{topic_str} {software} {module_name} {query_hints}".strip()

            if self.retriever is not None and query_text:
                # Try first with area filter if module looks like an area, fallback unfiltered
                chunks = self.retriever.retrieve(query_text, top_k=6, score_threshold=0.05)
                for item in chunks:
                    meta = item.document.metadata
                    cid = str(meta.get("chunk_id") or "")
                    if cid in seen_chunks:
                        continue
                    seen_chunks.add(cid)
                    clean_txt = strip_area_prefix(item.document.page_content)
                    passages.append(
                        {
                            "topic": topic_str,
                            "gap_id": target.get("gap_id"),
                            "document_id": str(meta.get("document_id") or ""),
                            "document": str(meta.get("source") or meta.get("title") or "Documento ufficiale"),
                            "section": str(meta.get("heading_path") or meta.get("section") or ""),
                            "chunk_id": cid or f"chunk_{len(passages)+1}",
                            "text": clean_txt,
                        }
                    )

        # Fallback to ExtractedTopic passages if vector search returned sparse results
        if len(passages) < 4:
            with self.db.session() as db:
                extracted = (
                    db.query(ExtractedTopic)
                    .filter(ExtractedTopic.tenant_id == tenant_id)
                    .limit(15)
                    .all()
                )
                for ext in extracted:
                    for p in ext.source_passages or []:
                        cid = str(p.get("chunk_id") or "")
                        if cid in seen_chunks:
                            continue
                        seen_chunks.add(cid)
                        passages.append(
                            {
                                "topic": targets[0]["topic"] if targets else ext.title,
                                "gap_id": targets[0].get("gap_id") if targets else None,
                                "document_id": ext.document_id,
                                "document": ext.source,
                                "section": str(p.get("section") or ext.title),
                                "chunk_id": cid or f"ext_{len(passages)+1}",
                                "text": str(p.get("excerpt") or ""),
                            }
                        )
        return passages

    @staticmethod
    def _extract_factual_statements(passage_text: str) -> list[str]:
        """Extract concise factual operational rules/statements directly from document text."""
        return extract_natural_quiz_statements(passage_text, min_len=30, max_len=210)

    def _build_deterministic_questions(
        self,
        *,
        passages: list[dict[str, Any]],
        targets: list[dict[str, Any]],
        num_questions: int,
        previous_hashes: set[str],
        iteration: int,
    ) -> list[dict[str, Any]]:
        """Build strictly 4-option grounded questions, varying phrasing across iterations."""
        questions: list[dict[str, Any]] = []
        target_gap_id = targets[0].get("gap_id") if targets else None
        primary_topic = targets[0]["topic"] if targets else "Operatività aziendale"

        distractor_bank = [
            "Contattare direttamente il singolo collaboratore tramite email personale o telefono privato senza aprire tracciamento.",
            "Inviare la segnalazione priva di oggetto descrittivo, ente di appartenenza e recapito di contatto.",
            "Saltare la verifica dei dati obbligatori e riutilizzare la vecchia mail automatica per qualsiasi problema diverso.",
            "Allegare file non pertinenti omettendo il modulo software interessato e la descrizione dell'errore.",
            "Ignorare i messaggi di validazione del sistema e procedere senza compilare i campi richiesti.",
            "Trasmettere la richiesta esclusivamente al di fuori dei canali ufficiali documentati.",
        ]

        prompts_variants = [
            "In riferimento a «{focus}», quale comportamento operativo è corretto adottare? (Fonte: {doc_short})",
            "Cosa occorre fare per gestire correttamente «{focus}»? (Fonte: {doc_short})",
            "Durante un'attività che riguarda «{focus}», quale regola va applicata? (Fonte: {doc_short})",
            "Per evitare errori operativi su «{focus}», quale indicazione bisogna seguire? (Fonte: {doc_short})",
        ]

        # Rotate passages and variant styles based on user attempt iteration
        ordered_passages = passages[(iteration - 1) % max(1, len(passages)) :] + passages[: (iteration - 1) % max(1, len(passages))]

        stmt_pool: list[tuple[dict[str, Any], str]] = []
        for p in ordered_passages:
            for stmt in self._extract_factual_statements(p["text"]):
                stmt_pool.append((p, stmt))

        for idx, (p, stmt) in enumerate(stmt_pool):
            if len(questions) >= num_questions:
                break

            doc_short = short_document_label(p["document"])
            focus = build_natural_focus(p["section"], str(p.get("topic") or primary_topic))
            var_style = prompts_variants[(idx + iteration - 1) % len(prompts_variants)]
            q_text = var_style.format(focus=focus, doc_short=doc_short)
            q_hash = _normalize_question_hash(f"{q_text}::{stmt[:60]}")
            if q_hash in previous_hashes:
                # Re-angle question to ensure a genuinely distinct verification item
                sec_short = short_section_label(p["section"], fallback=primary_topic)
                q_text = f"Caso pratico #{iteration} su «{sec_short}»: quale procedura consente di procedere correttamente? (Fonte: {doc_short})"
                q_hash = _normalize_question_hash(f"{q_text}::{stmt[:80]}::{iteration}")
                if q_hash in previous_hashes:
                    continue

            previous_hashes.add(q_hash)
            correct_pos = (idx + iteration) % 4
            d_offset = (idx + iteration) % len(distractor_bank)
            wrong_choices = [
                distractor_bank[(d_offset + k) % len(distractor_bank)]
                for k in range(3)
            ]
            raw_opts: list[str] = []
            w_ptr = 0
            for pos in range(4):
                if pos == correct_pos:
                    raw_opts.append(stmt)
                else:
                    raw_opts.append(wrong_choices[w_ptr])
                    w_ptr += 1

            formatted_opts = [{"id": _LETTERS[i], "text": raw_opts[i]} for i in range(4)]
            correct_letter = _LETTERS[correct_pos]
            est_lvl = float(targets[0].get("estimated_level", 0.5)) if targets else 0.5
            diff = "base" if est_lvl < 0.4 else ("advanced" if est_lvl >= 0.75 else "intermediate")

            questions.append(
                {
                    "question_hash": q_hash,
                    "question_text": q_text,
                    "options": formatted_opts,
                    "correct_option_id": correct_letter,
                    "correct_answer": stmt,
                    "explanation": f"Fonte: {doc_short} — {short_section_label(p['section'])}. {stmt}",
                    "topic": str(p.get("topic") or primary_topic),
                    "difficulty": diff,
                    "sources": [
                        {
                            "document_id": p["document_id"],
                            "document": p["document"],
                            "section": p["section"],
                            "chunk_id": p["chunk_id"],
                        }
                    ],
                    "gap_id": p.get("gap_id") or target_gap_id,
                }
            )

        return questions

    def generate_quiz(
        self,
        *,
        tenant_id: str = "default",
        user_id: str,
        plan: dict[str, Any],
        num_questions: int = 4,
        software: str | None = None,
        module_name: str | None = None,
        force_new: bool = False,
        run_async: bool = False,
    ) -> CustomQuiz:
        """Create or reuse a persistent CustomQuiz grounded in documentation and user history."""
        targets = plan.get("targets") or []
        if not targets:
            raise ValueError(
                f"Nessuna evidenza o argomento disponibile per generare un Custom Quiz per l'utente '{user_id}'."
            )

        eff_software = software or str(targets[0].get("software") or "Cityware / CWOL")
        eff_module = module_name or str(targets[0].get("module_name") or "Generale")
        target_topics = [str(t["topic"]) for t in targets]
        gap_ids = [str(t["gap_id"]) for t in targets if t.get("gap_id")]

        with self.db.session() as db:
            completed_count = (
                db.query(CustomQuizAttempt)
                .filter(CustomQuizAttempt.tenant_id == tenant_id, CustomQuizAttempt.user_id == user_id)
                .count()
            )
            idem_raw = f"{tenant_id}|{user_id}|{'|'.join(sorted(target_topics))}|{num_questions}|attempt:{completed_count}"
            idem_key = hashlib.sha256(idem_raw.encode("utf-8")).hexdigest()[:32]

            if not force_new:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=self.settings.custom_quiz_reuse_hours)
                reusable = (
                    db.query(CustomQuiz)
                    .options(joinedload(CustomQuiz.questions))
                    .filter(
                        CustomQuiz.tenant_id == tenant_id,
                        CustomQuiz.user_id == user_id,
                        CustomQuiz.idempotency_key == idem_key,
                        CustomQuiz.status == "READY",
                        CustomQuiz.generated_at >= cutoff,
                    )
                    .order_by(CustomQuiz.generated_at.desc())
                    .first()
                )
                if reusable is not None:
                    return reusable

        model_info = self.generator.get_model_info()
        model_label = (
            f"{model_info['provider']}:{model_info['configured_model']}"
            if model_info["llm_runtime_active"]
            else f"deterministic_fallback(expected={model_info['configured_model']})"
        )

        quiz_id = f"cquiz_{uuid.uuid4().hex[:12]}"
        with self.db.session() as db:
            quiz_row = CustomQuiz(
                id=quiz_id,
                tenant_id=tenant_id,
                user_id=user_id,
                software=eff_software,
                module_name=eff_module,
                status="GENERATING",
                num_questions=num_questions,
                topics_verified=target_topics,
                gap_ids=gap_ids,
                idempotency_key=idem_key,
                model_used=model_label,
                prompt_version=self.settings.custom_quiz_prompt_version,
            )
            db.add(quiz_row)
            db.commit()

        if run_async:
            self._executor.submit(
                self._populate_quiz_questions,
                quiz_id=quiz_id,
                tenant_id=tenant_id,
                user_id=user_id,
                plan=plan,
                num_questions=num_questions,
                software=eff_software,
                module_name=eff_module,
            )
            with self.db.session() as db:
                return (
                    db.query(CustomQuiz)
                    .options(joinedload(CustomQuiz.questions))
                    .filter_by(id=quiz_id)
                    .first()
                )  # type: ignore[return-value]

        self._populate_quiz_questions(
            quiz_id=quiz_id,
            tenant_id=tenant_id,
            user_id=user_id,
            plan=plan,
            num_questions=num_questions,
            software=eff_software,
            module_name=eff_module,
        )
        with self.db.session() as db:
            return (
                db.query(CustomQuiz)
                .options(joinedload(CustomQuiz.questions))
                .filter_by(id=quiz_id)
                .first()
            )  # type: ignore[return-value]

    def _populate_quiz_questions(
        self,
        *,
        quiz_id: str,
        tenant_id: str,
        user_id: str,
        plan: dict[str, Any],
        num_questions: int,
        software: str,
        module_name: str,
    ) -> None:
        try:
            targets = plan["targets"]
            previous_hashes = set(plan.get("previous_question_hashes") or set())
            previous_texts = plan.get("previous_question_texts") or []
            iteration = int(plan.get("attempt_iteration") or 1)

            passages = self._collect_grounded_passages(
                targets=targets,
                tenant_id=tenant_id,
                software=software,
                module_name=module_name,
            )
            if not passages:
                raise ValueError("Nessun passaggio documentale verificabile disponibile per generare le domande.")

            ctx = "\n\n".join(
                f"[Doc={p['document']} | DocID={p['document_id']} | Sezione={p['section']} | Chunk={p['chunk_id']}]\n{p['text'][:700]}"
                for p in passages[:8]
            )

            questions_data: list[dict[str, Any]] = []
            parsed, used_llm, model_info = self.generator.invoke_structured(
                CUSTOM_QUIZ_PROMPT,
                {
                    "user_id": user_id,
                    "software": software,
                    "module_name": module_name,
                    "num_questions": num_questions,
                    "estimated_level": plan.get("estimated_level", 0.5),
                    "target_topics": ", ".join(t["topic"] for t in targets),
                    "gaps_summary": "; ".join(f"{t['topic']} ({t.get('gap_status') or 'profilo'})" for t in targets),
                    "previous_questions": " | ".join(previous_texts[:5]) or "nessuna precedente",
                    "context": ctx,
                },
                CustomQuizGenerationLLM,
            )

            if parsed is not None and used_llm and parsed.questions:
                for q in parsed.questions[:num_questions]:
                    qh = _normalize_question_hash(q.question_text)
                    if qh in previous_hashes:
                        continue
                    previous_hashes.add(qh)
                    matched_p = next(
                        (p for p in passages if q.source_section and q.source_section.lower() in p["section"].lower()),
                        passages[0],
                    )
                    clean_q_text = clean_markdown_to_plain(q.question_text)
                    clean_opts = [clean_markdown_to_plain(opt) for opt in q.options]
                    opts = [{"id": _LETTERS[i], "text": clean_opts[i]} for i in range(4)]
                    c_letter = _LETTERS[q.correct_option_index]
                    questions_data.append(
                        {
                            "question_hash": qh,
                            "question_text": clean_q_text,
                            "options": opts,
                            "correct_option_id": c_letter,
                            "correct_answer": clean_opts[q.correct_option_index],
                            "explanation": clean_markdown_to_plain(q.explanation),
                            "topic": q.topic or targets[0]["topic"],
                            "difficulty": q.difficulty,
                            "sources": [
                                {
                                    "document_id": matched_p["document_id"],
                                    "document": matched_p["document"],
                                    "section": matched_p["section"],
                                    "chunk_id": matched_p["chunk_id"],
                                }
                            ],
                            "gap_id": next((t.get("gap_id") for t in targets if t["topic"].lower() in q.topic.lower()), targets[0].get("gap_id")),
                        }
                    )

            if len(questions_data) < num_questions:
                det_qs = self._build_deterministic_questions(
                    passages=passages,
                    targets=targets,
                    num_questions=num_questions - len(questions_data),
                    previous_hashes=previous_hashes,
                    iteration=iteration,
                )
                questions_data.extend(det_qs)

            with self.db.session() as db:
                quiz = db.get(CustomQuiz, quiz_id)
                if quiz is None:
                    return
                if used_llm and parsed is not None:
                    quiz.model_used = f"{model_info['provider']}:{model_info['configured_model']}"
                quiz.num_questions = len(questions_data)
                for idx, q in enumerate(questions_data, start=1):
                    # Enforce strict invariant: exactly 4 options
                    assert len(q["options"]) == 4
                    db.add(
                        CustomQuizQuestion(
                            id=f"cqq_{uuid.uuid4().hex[:12]}",
                            quiz_id=quiz_id,
                            order_index=idx,
                            question_hash=q["question_hash"],
                            question_text=q["question_text"],
                            options=q["options"],
                            correct_option_id=q["correct_option_id"],
                            correct_answer=q["correct_answer"],
                            explanation=q["explanation"],
                            topic=q["topic"],
                            difficulty=q["difficulty"],
                            sources=q["sources"],
                            gap_id=q.get("gap_id"),
                        )
                    )
                quiz.status = "READY" if questions_data else "FAILED"
                if not questions_data:
                    quiz.error_message = "Impossibile generare domande non duplicate dalle fonti disponibili."
                db.commit()
        except Exception as exc:
            logger.exception("Custom Quiz generation %s failed: %s", quiz_id, exc)
            with self.db.session() as db:
                quiz = db.get(CustomQuiz, quiz_id)
                if quiz is not None:
                    quiz.status = "FAILED"
                    quiz.error_message = str(exc)
                    db.commit()
