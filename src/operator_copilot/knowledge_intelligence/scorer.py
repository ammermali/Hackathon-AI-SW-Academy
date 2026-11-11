"""Multi-factor Relevance Scoring distinguishing calculated metrics from LLM evaluations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from operator_copilot.course_generator.prompts import RELEVANCE_PROMPT
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import DocumentMetadata, ExtractedTopic, TopicRelevanceScore
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.schemas.academy import RelevanceScoringLLMOutput


class RelevanceScorer:
    """Computes transparent multi-factor training relevance scores without relying solely on frequency."""

    def __init__(
        self,
        db_manager: DatabaseManager | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        self.db = db_manager or get_db_manager()
        self.generator = generator

    def score_topic(self, topic: ExtractedTopic, *, persist: bool = True) -> TopicRelevanceScore:
        """Evaluate training relevance across 8 explicit factors with clear provenance."""
        # 1. Frequency recurrence (strictly capped at 10% weight so frequency never drives score alone)
        with self.db.session() as db:
            total_area_docs = 1
            if topic.area_name:
                total_area_docs = max(
                    1,
                    db.query(DocumentMetadata).filter_by(area_name=topic.area_name, status="indexed").count(),
                )
            similar_title_count = (
                db.query(ExtractedTopic)
                .filter(ExtractedTopic.tenant_id == topic.tenant_id, ExtractedTopic.category == topic.category)
                .count()
            )

        doc_frequency_score = min(1.0, (1 + len(topic.related_topics) + min(similar_title_count, 5)) / 10.0)

        # 2. Operational importance (procedures + rules + constraints)
        proc_count = len(topic.procedures)
        rules_count = len(topic.rules) + len(topic.constraints)
        operational_importance = min(1.0, 0.30 + 0.15 * min(proc_count, 3) + 0.05 * min(rules_count, 5))

        # 3. Error criticality (explicit error scenarios, SLA warnings, payment/compliance risk)
        err_count = len(topic.frequent_errors) + len(topic.constraints)
        critical_terms = ("non verranno presi in carico", "errore", "blocco", "chiuso", "pagamento", "sla", "obbligatori")
        text_blob = f"{topic.title} {topic.summary} {' '.join(topic.constraints)}".lower()
        critical_hits = sum(1 for t in critical_terms if t in text_blob)
        error_criticality = min(1.0, 0.20 + 0.12 * min(err_count, 4) + 0.08 * min(critical_hits, 4))

        # 4. Complexity (number of steps + concepts + conditions)
        total_steps = sum(len(p.get("steps", [])) for p in topic.procedures)
        complexity = min(1.0, 0.25 + 0.06 * min(total_steps, 8) + 0.04 * min(len(topic.recurring_concepts), 6))

        # 5. Operator autonomy utility (procedures + examples + software applicability)
        has_examples = 1.0 if topic.practical_examples else 0.0
        operator_autonomy = min(1.0, 0.30 + 0.35 * (1.0 if proc_count > 0 or rules_count > 0 else 0.0) + 0.35 * has_examples)

        # 6. Completeness of source information
        completeness_parts = [
            bool(topic.summary and len(topic.summary) > 40),
            bool(proc_count > 0 or rules_count > 0),
            bool(topic.practical_examples),
            bool(topic.frequent_errors or topic.constraints),
            bool(topic.source_passages),
        ]
        completeness = sum(1.0 for ok in completeness_parts if ok) / len(completeness_parts)

        # 7. Source recency
        current_year = datetime.now(timezone.utc).year
        if topic.doc_year is None:
            source_recency = 0.55
            recency_verifiable = False
        else:
            age = max(0, current_year - topic.doc_year)
            source_recency = max(0.25, round(1.0 - 0.10 * min(age, 7), 4))
            recency_verifiable = True

        # 8. Applicability to specific software, modules, and roles
        software_app = min(1.0, 0.30 + 0.20 * min(len(topic.software_modules), 2) + 0.15 * min(len(topic.target_roles), 2))

        # Weighted algorithmic composite (frequency is only 10%!)
        algorithmic_score = round(
            0.22 * operational_importance
            + 0.10 * doc_frequency_score
            + 0.18 * error_criticality
            + 0.10 * complexity
            + 0.15 * operator_autonomy
            + 0.10 * completeness
            + 0.07 * source_recency
            + 0.08 * software_app,
            4,
        )

        unverifiable: list[str] = []
        if not recency_verifiable:
            unverifiable.append("Anno di revisione del documento non esplicitato nel nome o nel frontespizio.")

        # Optional LLM evaluation (kept strictly separate from algorithmic_score)
        llm_score: float | None = None
        scored_by_model = "algorithmic_only"
        llm_note = ""

        if self.generator is not None:
            ctx = f"Procedure: {proc_count}, Regole: {rules_count}, Esempi: {len(topic.practical_examples)}, Errori: {len(topic.frequent_errors)}\n{topic.summary}"
            parsed, used_llm, model_info = self.generator.invoke_structured(
                RELEVANCE_PROMPT,
                {"title": topic.title, "category": topic.category, "context": ctx},
                RelevanceScoringLLMOutput,
            )
            if parsed is not None and used_llm:
                llm_score = round(parsed.llm_relevance_score, 4)
                scored_by_model = f"{model_info['provider']}:{model_info['configured_model']}"
                llm_note = parsed.rationale
            else:
                unverifiable.append("Valutazione qualitativa LLM non attiva nell'ambiente corrente (usato calcolo algoritmico).")
        else:
            unverifiable.append("Valutazione qualitativa LLM non eseguita (scorer inizializzato senza LLM).")

        overall = round(0.65 * algorithmic_score + 0.35 * llm_score, 4) if llm_score is not None else algorithmic_score

        factors = {
            "operational_importance": round(operational_importance, 4),
            "doc_frequency_capped_10pct": round(doc_frequency_score, 4),
            "error_criticality": round(error_criticality, 4),
            "complexity": round(complexity, 4),
            "operator_autonomy": round(operator_autonomy, 4),
            "completeness": round(completeness, 4),
            "source_recency": round(source_recency, 4),
            "software_role_applicability": round(software_app, 4),
            "area_document_pool": total_area_docs,
        }

        rationale = (
            f"Score algoritmico={algorithmic_score:.2f} (rilevanza operativa={operational_importance:.2f}, "
            f"criticità errori={error_criticality:.2f}, completezza={completeness:.2f}, frequenza pesata al 10%={doc_frequency_score:.2f}). "
            + (f"Valutazione LLM ({scored_by_model})={llm_score:.2f}: {llm_note}" if llm_score is not None else "Nessuna stima LLM sovrapposta.")
        )

        row = TopicRelevanceScore(
            id=f"rel_{uuid.uuid4().hex[:12]}",
            topic_id=topic.id,
            tenant_id=topic.tenant_id,
            overall_score=overall,
            algorithmic_score=algorithmic_score,
            llm_score=llm_score,
            factors=factors,
            unverifiable_factors=unverifiable,
            rationale=rationale,
            scored_by_model=scored_by_model,
        )
        if persist:
            with self.db.session() as db:
                db.query(TopicRelevanceScore).filter_by(topic_id=topic.id, tenant_id=topic.tenant_id).delete()
                db.add(row)
                db.commit()
                db.refresh(row)
        return row
