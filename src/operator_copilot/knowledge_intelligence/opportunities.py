"""Aggregates single or correlated topics into structured Training Opportunities."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import ExtractedTopic, KnowledgeGap, TopicRelevanceScore, TrainingOpportunity
from operator_copilot.retrieval.retriever import HybridRetriever


class OpportunityAggregator:
    """Creates TrainingOpportunity proposals from single documents or correlated clusters."""

    def __init__(
        self,
        db_manager: DatabaseManager | None = None,
        retriever: HybridRetriever | None = None,
    ) -> None:
        self.db = db_manager or get_db_manager()
        self.retriever = retriever

    @staticmethod
    def _infer_course_type(topics: list[ExtractedTopic]) -> str:
        """Distinguish 'documental' (rules, communications, support, admin) vs 'applicative' (software workflows)."""
        if all(
            t.category in ("Assistenza tecnica", "Normativa e regolamenti", "Best practice operative")
            for t in topics
        ):
            return "documental"
        has_ui_proc = any(
            t.category in (
                "Utilizzo del software",
                "Gestione documentale",
                "Gestione degli errori",
                "Procedure operative",
                "Amministrazione e contabilità",
            )
            and len(t.procedures) > 0
            for t in topics
        )
        return "applicative" if has_ui_proc else "documental"

    @staticmethod
    def _derive_opportunity_title(topics: list[ExtractedTopic], group_label: str | None = None) -> str:
        if len(topics) == 1:
            t = topics[0]
            lower_title = f"{t.title} {t.source}".lower()
            if "richiesta" in lower_title and "assistenza" in lower_title:
                return "Come richiedere correttamente assistenza su un software gestionale"
            if t.category == "Assistenza tecnica":
                return f"Gestione corretta dell'assistenza: {t.title}"
            return f"Corso operativo: {t.title}"

        if group_label:
            return f"Percorso formativo {group_label}: procedure ed errori frequenti"
        return f"Percorso integrato: {topics[0].title}"

    def build_opportunity_from_topics(
        self,
        topics: list[ExtractedTopic],
        *,
        tenant_id: str = "default",
        job_id: str | None = None,
        group_label: str | None = None,
        persist: bool = True,
    ) -> TrainingOpportunity:
        """Synthesize one TrainingOpportunity from 1 or N correlated ExtractedTopic records."""
        if not topics:
            raise ValueError("Almeno un argomento estratto è necessario per generare una proposta formativa.")

        with self.db.session() as db:
            topic_ids = [t.id for t in topics]
            scores = (
                db.query(TopicRelevanceScore)
                .filter(TopicRelevanceScore.topic_id.in_(topic_ids), TopicRelevanceScore.tenant_id == tenant_id)
                .all()
            )
            gaps = (
                db.query(KnowledgeGap)
                .filter(KnowledgeGap.tenant_id == tenant_id)
                .all()
            )

        score_map = {s.topic_id: s for s in scores}
        rel_values = [score_map[tid].overall_score for tid in topic_ids if tid in score_map]
        avg_rel = round(sum(rel_values) / len(rel_values), 4) if rel_values else 0.65

        completeness_vals = [
            float(score_map[tid].factors.get("completeness", 0.6))
            for tid in topic_ids
            if tid in score_map and isinstance(score_map[tid].factors, dict)
        ]
        avg_comp = round(sum(completeness_vals) / len(completeness_vals), 4) if completeness_vals else 0.60

        source_docs = [
            {
                "document_id": t.document_id,
                "source": t.source,
                "title": t.title,
                "doc_year": t.doc_year,
                "file_hash": t.file_hash,
            }
            for t in topics
        ]
        doc_ids_set = {t.document_id for t in topics}

        criticalities: list[str] = []
        for g in gaps:
            gap_doc_ids = {d.get("document_id") for d in g.analyzed_documents}
            if gap_doc_ids & doc_ids_set:
                criticalities.append(f"[{g.gap_type.upper()}] {g.reason}")

        software_mods = list(dict.fromkeys(m for t in topics for m in t.software_modules))
        audience = list(dict.fromkeys(r for t in topics for r in t.target_roles)) or ["Operatore PA"]
        allowed_roles = list(dict.fromkeys(r for t in topics for r in t.allowed_roles)) or ["operatore", "admin"]

        total_steps = sum(len(p.get("steps", [])) for t in topics for p in t.procedures)
        if total_steps >= 10 or len(topics) >= 4:
            difficulty = "advanced"
        elif total_steps >= 4 or len(topics) >= 2:
            difficulty = "intermediate"
        else:
            difficulty = "base"

        course_type = self._infer_course_type(topics)
        title = self._derive_opportunity_title(topics, group_label=group_label)
        topic_names = list(dict.fromkeys([t.title for t in topics] + [c for t in topics for c in t.recurring_concepts[:3]]))[:10]

        description = (
            f"Proposta formativa di tipo {'documentale' if course_type == 'documental' else 'applicativo'} "
            f"basata su {len(topics)} documento/i reale/i ({topics[0].area_name or topics[0].category}). "
            f"{topics[0].summary[:240]}"
        )
        learning_obj = (
            f"Consentire agli operatori ({', '.join(audience[:2])}) di applicare correttamente "
            f"regole, procedure ed evitare gli errori documentati su: {topics[0].title}."
        )
        rationale = (
            f"Aggregazione basata su area/categoria '{topics[0].category}' con relevance score {avg_rel:.2f} "
            f"e completezza documentale {avg_comp:.2f}."
        )

        opp = TrainingOpportunity(
            id=f"opp_{uuid.uuid4().hex[:12]}",
            job_id=job_id,
            tenant_id=tenant_id,
            allowed_roles=allowed_roles,
            title=title,
            description=description,
            learning_objective=learning_obj,
            course_type=course_type,
            topic_ids=topic_ids,
            topics=topic_names,
            source_documents=source_docs,
            software_modules=software_mods,
            suggested_audience=audience,
            difficulty=difficulty,
            relevance_score=avg_rel,
            completeness_score=avg_comp,
            criticalities=criticalities[:6],
            rationale=rationale,
            status="PROPOSED",
        )
        if persist:
            with self.db.session() as db:
                db.add(opp)
                db.commit()
                db.refresh(opp)
        return opp

    def build_opportunities_from_clusters(
        self,
        topics: list[ExtractedTopic],
        *,
        tenant_id: str = "default",
        job_id: str | None = None,
    ) -> list[TrainingOpportunity]:
        """Cluster correlated topics by (area_name, category) and emit opportunities."""
        if not topics:
            return []
        if len(topics) == 1:
            return [self.build_opportunity_from_topics(topics, tenant_id=tenant_id, job_id=job_id)]

        clusters: dict[tuple[str, str], list[ExtractedTopic]] = defaultdict(list)
        for t in topics:
            # Correlate operational docs sharing the same area and software module (e.g. procedures + error troubleshooting on CWOL)
            secondary_key = (
                t.software_modules[0]
                if (t.software_modules and t.category != "Assistenza tecnica")
                else t.category
            )
            key = (t.area_name or "Generale", secondary_key)
            clusters[key].append(t)

        opportunities: list[TrainingOpportunity] = []
        for (area, cat), group in clusters.items():
            # Split large clusters into manageable chunks of <= 5 correlated docs
            for idx in range(0, len(group), 5):
                sub = group[idx : idx + 5]
                label = f"{area} – {cat}" if len(sub) > 1 else None
                opp = self.build_opportunity_from_topics(
                    sub,
                    tenant_id=tenant_id,
                    job_id=job_id,
                    group_label=label,
                )
                opportunities.append(opp)
        return opportunities

    def find_correlated_documents(self, query_text: str, *, area_name: str | None = None, top_k: int = 5) -> list[str]:
        """Optionally use existing HybridRetriever to discover semantically correlated document IDs."""
        if self.retriever is None:
            return []
        filters: dict[str, Any] | None = {"area_name": area_name} if area_name else None
        chunks = self.retriever.retrieve(query_text, top_k=top_k, filters=filters, score_threshold=0.35)
        return list(dict.fromkeys(str(c.document.metadata.get("document_id")) for c in chunks if c.document.metadata.get("document_id")))
