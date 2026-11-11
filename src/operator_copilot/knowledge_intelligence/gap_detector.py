"""Knowledge Gap Detection identifying insufficient, incomplete, outdated, or contradictory docs."""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.course_generator.prompts import GAP_DETECTION_PROMPT
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import ExtractedTopic, KnowledgeGap
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.schemas.academy import GapDetectionLLMOutput

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PDF_REF_RE = re.compile(r"\b[\w\-]+\.pdf\b", re.IGNORECASE)
_DAYS_OR_NUM_RE = re.compile(r"\b(\d{1,3})\s+(giorni|ore|tentativi|mesi|minuti)\b", re.IGNORECASE)


class KnowledgeGapDetector:
    """Detects real documentation gaps and contradictions without inventing missing procedures."""

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
    def _normalize_topic_key(title: str) -> str:
        cleaned = unicodedata.normalize("NFKD", title.lower()).encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r"comunicazione\s+n\.?\s*\d+/\d{4}\s*[–-]?\s*", "", cleaned)
        cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
        stop = {"di", "da", "su", "per", "del", "della", "dei", "con", "alle", "sui", "parte"}
        tokens = [t for t in cleaned.split() if len(t) > 2 and t not in stop]
        return " ".join(tokens[:3])

    def detect_for_topics(
        self,
        topics: list[ExtractedTopic],
        *,
        tenant_id: str = "default",
        job_id: str | None = None,
        persist: bool = True,
    ) -> list[KnowledgeGap]:
        """Inspect extracted topics for insufficient, incomplete, outdated, and contradictory evidence."""
        gaps: list[KnowledgeGap] = []
        current_year = datetime.now(timezone.utc).year

        for t in topics:
            passages_txt = " ".join(str(p.get("excerpt", "")) for p in t.source_passages)
            full_text = f"{t.summary} {' '.join(t.rules)} {' '.join(t.constraints)} {passages_txt}"
            doc_ref = [{"document_id": t.document_id, "source": t.source, "doc_year": t.doc_year}]

            # 1. Insufficient evidence (very sparse rules & procedures)
            if not t.procedures and len(t.rules) < 2 and len(full_text.strip()) < 280:
                gaps.append(
                    KnowledgeGap(
                        id=f"gap_{uuid.uuid4().hex[:12]}",
                        job_id=job_id,
                        tenant_id=tenant_id,
                        allowed_roles=t.allowed_roles,
                        topic=t.title,
                        gap_type="insufficient",
                        available_info=t.summary[:300] or "Solo titolo/breve nota.",
                        missing_info="Mancano passaggi operativi numerati, prerequisiti ed esempi applicativi verificabili.",
                        analyzed_documents=doc_ref,
                        reason="Documento troppo sintetico per generare una lezione operativa completa senza inferenze.",
                        suggested_addition="Integrare manuale con procedura passo-passo e casi d'uso reali.",
                        severity="high",
                    )
                )

            # 2. Incomplete (external missing PDF references or procedures without error handling)
            pdf_refs = _PDF_REF_RE.findall(full_text)
            if pdf_refs:
                gaps.append(
                    KnowledgeGap(
                        id=f"gap_{uuid.uuid4().hex[:12]}",
                        job_id=job_id,
                        tenant_id=tenant_id,
                        allowed_roles=t.allowed_roles,
                        topic=t.title,
                        gap_type="incomplete",
                        available_info=f"Il documento cita allegati esterni: {', '.join(sorted(set(pdf_refs))[:5])}.",
                        missing_info="Contenuto dei file PDF esterni referenziati non presente nel corpus Markdown.",
                        analyzed_documents=doc_ref,
                        reason="Riferimenti a documenti PDF esterni non indicizzati nella knowledge base.",
                        suggested_addition="Convertire e indicizzare i PDF referenziati nella cartella data/.",
                        severity="medium",
                    )
                )
            elif t.procedures and not t.frequent_errors and not t.practical_examples:
                gaps.append(
                    KnowledgeGap(
                        id=f"gap_{uuid.uuid4().hex[:12]}",
                        job_id=job_id,
                        tenant_id=tenant_id,
                        allowed_roles=t.allowed_roles,
                        topic=t.title,
                        gap_type="incomplete",
                        available_info=f"Presenti {len(t.procedures)} procedure operative.",
                        missing_info="Assenti esempi pratici reali ed elenco degli errori frequenti / comportamenti da evitare.",
                        analyzed_documents=doc_ref,
                        reason="La copertura procedurale è presente ma mancano casi pratici e troubleshooting.",
                        suggested_addition="Aggiungere almeno 1 esempio compilato e i messaggi di errore più comuni.",
                        severity="low",
                    )
                )

            # 3. Outdated check
            if t.doc_year is not None and (current_year - t.doc_year) >= self.settings.knowledge_obsolete_years:
                gaps.append(
                    KnowledgeGap(
                        id=f"gap_{uuid.uuid4().hex[:12]}",
                        job_id=job_id,
                        tenant_id=tenant_id,
                        allowed_roles=t.allowed_roles,
                        topic=t.title,
                        gap_type="outdated",
                        available_info=f"Documento datato {t.doc_year} ({t.source}).",
                        missing_info=f"Nessuna verifica di validità recente nell'ultimo quadriennio ({current_year - self.settings.knowledge_obsolete_years}-{current_year}).",
                        analyzed_documents=doc_ref,
                        reason=f"Fonte precedente di oltre {self.settings.knowledge_obsolete_years} anni rispetto all'anno corrente ({current_year}).",
                        suggested_addition="Verificare con il referente applicativo se la procedura è ancora valida su CWOL attuale.",
                        severity="medium",
                    )
                )

        # 4. Contradiction detection across grouped topics (different docs on same topic)
        by_key: dict[str, list[ExtractedTopic]] = defaultdict(list)
        for t in topics:
            key = self._normalize_topic_key(t.title)
            if key:
                by_key[key].append(t)

        for key, group in by_key.items():
            if len(group) < 2:
                continue
            emails_by_doc: dict[str, set[str]] = {}
            limits_by_doc: dict[str, set[str]] = {}
            for t in group:
                blob = f"{t.summary} {' '.join(t.rules)} {' '.join(t.constraints)} " + " ".join(
                    str(p.get("excerpt", "")) for p in t.source_passages
                )
                emails = {e.lower() for e in _EMAIL_RE.findall(blob)}
                if emails:
                    emails_by_doc[t.source] = emails
                nums = {f"{n} {u.lower()}" for n, u in _DAYS_OR_NUM_RE.findall(blob)}
                if nums:
                    limits_by_doc[t.source] = nums

            all_emails = set().union(*emails_by_doc.values()) if emails_by_doc else set()
            all_nums = set().union(*limits_by_doc.values()) if limits_by_doc else set()
            doc_refs = [{"document_id": x.document_id, "source": x.source, "doc_year": x.doc_year} for x in group]

            contradiction_reasons: list[str] = []
            if len(emails_by_doc) >= 2 and len(all_emails) > 1:
                contradiction_reasons.append(f"Indirizzi/canali differenti tra versioni ({', '.join(sorted(all_emails)[:4])}).")
            if len(limits_by_doc) >= 2 and len(all_nums) > 1:
                contradiction_reasons.append(f"Soglie/valori numerici differenti tra documenti ({', '.join(sorted(all_nums)[:4])}).")

            # Optional LLM contradiction check when active
            if self.generator is not None and not contradiction_reasons:
                ctx = "\n\n".join(
                    f"[{x.source} | anno={x.doc_year}]: {x.summary} | Regole: {'; '.join(x.rules[:4])}"
                    for x in group[:4]
                )
                parsed, used_llm, _ = self.generator.invoke_structured(
                    GAP_DETECTION_PROMPT,
                    {"topic": group[0].title, "context": ctx},
                    GapDetectionLLMOutput,
                )
                if parsed is not None and used_llm and parsed.gaps_found:
                    for gf in parsed.gaps_found[:2]:
                        contradiction_reasons.append(gf.get("reason") or gf.get("missing_info") or "Divergenza rilevata tra fonti.")

            if contradiction_reasons:
                gaps.append(
                    KnowledgeGap(
                        id=f"gap_{uuid.uuid4().hex[:12]}",
                        job_id=job_id,
                        tenant_id=tenant_id,
                        allowed_roles=group[0].allowed_roles,
                        topic=group[0].title,
                        gap_type="contradictory",
                        available_info=f"Confrontati {len(group)} documenti sull'argomento '{group[0].title}'.",
                        missing_info="Manca un'indicazione univoca sulla fonte/versione attualmente vigente.",
                        analyzed_documents=doc_refs,
                        reason=" ".join(contradiction_reasons),
                        suggested_addition="Consolidare o archiviare le versioni superate mantenendo una sola fonte autorevole.",
                        severity="high",
                    )
                )

        if persist and gaps:
            with self.db.session() as db:
                for g in gaps:
                    db.add(g)
                db.commit()

        return gaps
