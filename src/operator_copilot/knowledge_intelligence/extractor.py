"""Knowledge Extraction module reusing existing ChromaDB chunks and AnswerGenerator."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.course_generator.prompts import EXTRACTION_PROMPT
from operator_copilot.db.database import DatabaseManager, get_db_manager
from operator_copilot.db.models import DocumentMetadata, ExtractedTopic
from operator_copilot.generation.answer_generator import AnswerGenerator
from operator_copilot.ingestion.chunker import DocumentChunker
from operator_copilot.ingestion.loaders import DocumentLoader, LoadError
from operator_copilot.ingestion.normalizer import ContentNormalizer, strip_area_prefix
from operator_copilot.ingestion.scanner import DataScanner, ScannedFile
from operator_copilot.retrieval.retriever import HybridRetriever
from operator_copilot.schemas.academy import KnowledgeExtractionLLMOutput

logger = logging.getLogger("operator_copilot.knowledge_intelligence.extractor")

_NUMBERED_ITEM_RE = re.compile(r"^\s*\d+\.\s+(.+)$", re.MULTILINE)
_BULLET_ITEM_RE = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
_WARNING_RE = re.compile(r"^\s*>\s*(?:⚠️\s*)?(.+)$", re.MULTILINE)
_SUBHEADING_RE = re.compile(r"^(#{2,4})\s+(.+)$", re.MULTILINE)

_KNOWN_SOFTWARE_KEYWORDS = {
    "Cityware Online": "Cityware Online (CWOL)",
    "CWOL": "Cityware Online (CWOL)",
    "Cityware": "Cityware",
    "Cityfinancing": "Cityfinancing",
    "Citybase": "Citybase",
    "Cityfee": "Cityfee",
    "Citymedia": "Citymedia",
    "Citypeople": "Citypeople",
    "Cityportal": "Cityportal",
    "OTRS": "Sistema Ticketing OTRS",
    "PagoPA": "PagoPA",
    "SIOPE+": "SIOPE+",
    "ANPR": "ANPR",
    "ANSC": "ANSC",
    "EFIL": "EFIL",
}


@dataclass
class DocumentChunkBundle:
    """Chunks and metadata loaded from ChromaDB or on-demand for a single document."""

    document_id: str
    source: str
    file_hash: str
    title: str
    area_name: str | None
    doc_year: int | None
    document_type: str
    updated_at: str
    chunks: list[Document]


class KnowledgeExtractor:
    """Extracts structured training knowledge strictly from indexed documents or on-demand files."""

    def __init__(
        self,
        settings: Settings | None = None,
        db_manager: DatabaseManager | None = None,
        retriever: HybridRetriever | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)
        self.retriever = retriever or HybridRetriever(self.settings, self.db)
        self.generator = generator or AnswerGenerator(self.settings)

    def load_document_bundle(self, doc_ref: str) -> DocumentChunkBundle | None:
        """Load existing chunks from ChromaDB/SQLite, or parse on-demand if file exists in data_dir."""
        with self.db.session() as db:
            meta_row = (
                db.query(DocumentMetadata)
                .filter((DocumentMetadata.document_id == doc_ref) | (DocumentMetadata.source == doc_ref))
                .first()
            )
            if meta_row is None and "/" not in doc_ref and "\\" not in doc_ref:
                meta_row = (
                    db.query(DocumentMetadata)
                    .filter(DocumentMetadata.source.ilike(f"%{doc_ref}%"))
                    .first()
                )

        if meta_row is not None:
            vs = self.retriever._get_vectorstore()
            raw = vs.get(where={"document_id": meta_row.document_id}, include=["documents", "metadatas"])
            docs_txt = raw.get("documents") or []
            metas = raw.get("metadatas") or []
            chunks = [
                Document(page_content=txt, metadata=m or {})
                for txt, m in zip(docs_txt, metas)
            ]
            chunks.sort(key=lambda d: int(d.metadata.get("chunk_index", 0)))
            if chunks:
                first_meta = chunks[0].metadata
                return DocumentChunkBundle(
                    document_id=meta_row.document_id,
                    source=meta_row.source,
                    file_hash=meta_row.file_hash,
                    title=str(first_meta.get("title") or Path(meta_row.source).stem),
                    area_name=meta_row.area_name,
                    doc_year=meta_row.doc_year,
                    document_type=meta_row.document_type,
                    updated_at=str(first_meta.get("updated_at") or meta_row.updated_at.isoformat()),
                    chunks=chunks,
                )

        # Fallback: locate and chunk on-demand from data_dir without duplicating indexing
        candidate_path = self.settings.data_dir / doc_ref
        if not candidate_path.exists():
            matches = list(self.settings.data_dir.rglob(f"*{Path(doc_ref).name}*"))
            candidate_path = matches[0] if matches else candidate_path
        if not candidate_path.exists() or not candidate_path.is_file():
            return None

        scanner = DataScanner(self.settings.data_dir, skip_index_files=self.settings.skip_index_files)
        norm = ContentNormalizer()
        loader = DocumentLoader(norm)
        chunker = DocumentChunker(self.settings.chunk_size, self.settings.chunk_overlap)

        rel = candidate_path.relative_to(self.settings.data_dir).as_posix()
        f_hash = scanner.compute_file_hash(candidate_path)
        scanned = ScannedFile(
            absolute_path=candidate_path,
            relative_path=rel,
            extension=candidate_path.suffix.lower(),
            size_bytes=candidate_path.stat().st_size,
            file_hash=f_hash,
            document_id=scanner.compute_document_id(rel),
            updated_at=str(candidate_path.stat().st_mtime),
        )
        loaded = loader.load(scanned)
        if isinstance(loaded, LoadError):
            return None
        chunks = chunker.chunk_document(loaded)
        return DocumentChunkBundle(
            document_id=loaded.document_id,
            source=loaded.source,
            file_hash=loaded.file_hash,
            title=str(loaded.metadata.get("title") or Path(rel).stem),
            area_name=loaded.metadata.get("area_name"),
            doc_year=loaded.metadata.get("doc_year"),
            document_type=str(loaded.metadata.get("document_type") or "manual"),
            updated_at=str(loaded.metadata.get("updated_at") or ""),
            chunks=chunks,
        )

    @staticmethod
    def _clean_chunk_text(text: str) -> str:
        return strip_area_prefix(text)

    @classmethod
    def _detect_software_modules(cls, full_text: str, area_name: str | None) -> list[str]:
        found: list[str] = []
        lower = full_text.lower()
        for needle, label in _KNOWN_SOFTWARE_KEYWORDS.items():
            if needle.lower() in lower and label not in found:
                found.append(label)
        if area_name and area_name not in found and len(found) == 0:
            found.append(area_name)
        return found

    @staticmethod
    def _detect_target_roles(full_text: str, area_name: str | None) -> list[str]:
        roles = ["Operatore PA"]
        lower = full_text.lower()
        if any(k in lower for k in ("ragioneria", "financing", "mandati", "accertamento", "siope", "bilancio")):
            roles.append("Operatore Area Finanziaria / Ragioneria")
        if any(k in lower for k in ("anagrafe", "elettorale", "aire", "stato civile", "anpr")):
            roles.append("Operatore Servizi Demografici")
        if any(k in lower for k in ("protocollo", "conservazione", "determina", "delibera")):
            roles.append("Operatore Segreteria / Protocollo")
        if any(k in lower for k in ("verbale", "codice della strada", "ruolo")):
            roles.append("Operatore Polizia Locale")
        if any(k in lower for k in ("ticket", "assistenza", "amministratore", "account")):
            roles.append("Referente Applicativo / Utente Gestionale")
        if area_name and len(roles) == 1:
            roles.append(f"Operatore {area_name}")
        return roles

    def _deterministic_extract(self, bundle: DocumentChunkBundle) -> KnowledgeExtractionLLMOutput:
        """Deterministically extract structured procedures, rules, examples, and errors with zero hallucination."""
        full_parts: list[str] = []
        procedures: list[dict[str, Any]] = []
        rules: list[str] = []
        concepts: list[str] = []
        examples: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        constraints: list[str] = []

        for chunk in bundle.chunks:
            txt = self._clean_chunk_text(chunk.page_content)
            full_parts.append(txt)
            section = str(chunk.metadata.get("heading_path") or chunk.metadata.get("section") or bundle.title)

            # Section concepts from subheadings
            for _, heading in _SUBHEADING_RE.findall(txt):
                h_clean = heading.strip()
                if h_clean and h_clean not in concepts:
                    concepts.append(h_clean)

            # Detect numbered procedural steps
            num_steps = [m.strip() for m in _NUMBERED_ITEM_RE.findall(txt) if len(m.strip()) > 10]
            if num_steps:
                proc_title = section.split(">")[-1].strip() or bundle.title
                procedures.append({"title": proc_title, "steps": num_steps[:12], "section": section})

            # Detect bulleted rules / required items
            for b in _BULLET_ITEM_RE.findall(txt):
                b_clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", b).strip()
                if len(b_clean) < 10:
                    continue
                lower_b = b_clean.lower()
                if any(k in lower_b for k in ("evitare", "non ", "obbligatori", "sconsigliato", "errore", "imprescindibili")):
                    if b_clean not in constraints:
                        constraints.append(b_clean)
                elif b_clean not in rules:
                    rules.append(b_clean)

            # Warnings / constraints (> ⚠️ ...)
            for w in _WARNING_RE.findall(txt):
                w_clean = w.strip()
                if len(w_clean) > 12 and w_clean not in constraints:
                    constraints.append(w_clean)
                if any(k in w_clean.lower() for k in ("non verranno presi in carico", "errore", "chiuso", "blocc", "rischi")):
                    errors.append(
                        {
                            "error_or_antipattern": w_clean[:180],
                            "consequence_or_fix": f"Seguire quanto indicato nella sezione '{section}'.",
                            "section": section,
                        }
                    )

            # Examples (correct / incorrect blocks such as TICKET 1, TICKET 1 – ERRATO, [Schermata...])
            leaf_sec = section.split(">")[-1].strip()
            leaf_lower = leaf_sec.lower()
            txt_lower = txt.lower()
            is_errato = "errat" in leaf_lower or "errore" in leaf_lower or "– errato" in txt_lower
            is_esempio = "esemp" in leaf_lower or "#### ticket" in txt_lower or "[schermata" in txt_lower
            if is_esempio:
                label = leaf_sec
                excerpt = txt[:600].strip()
                examples.append(
                    {
                        "label": label,
                        "is_correct": not is_errato,
                        "content": excerpt,
                        "section": section,
                    }
                )
                if is_errato:
                    errors.append(
                        {
                            "error_or_antipattern": label,
                            "consequence_or_fix": excerpt[:280],
                            "section": section,
                        }
                    )

        full_text = "\n\n".join(full_parts)
        software_modules = self._detect_software_modules(full_text, bundle.area_name)
        target_roles = self._detect_target_roles(full_text, bundle.area_name)

        # Build concise grounded summary from intro paragraph
        intro_lines = [ln.strip() for ln in full_text.splitlines() if ln.strip() and not ln.strip().startswith("#") and not ln.strip().startswith("|")]
        summary = " ".join(intro_lines[:3])[:450] if intro_lines else bundle.title

        related = [c for c in concepts[:6] if c.lower() != bundle.title.lower()]
        return KnowledgeExtractionLLMOutput.model_validate(
            {
                "title": bundle.title,
                "summary": summary,
                "procedures": procedures[:10],
                "rules": rules[:15],
                "recurring_concepts": concepts[:12],
                "practical_examples": examples[:10],
                "frequent_errors": errors[:10],
                "constraints": constraints[:12],
                "related_topics": related,
                "software_modules": software_modules,
                "target_roles": target_roles,
            }
        )

    def extract_from_bundle(
        self,
        bundle: DocumentChunkBundle,
        *,
        category: str = "Procedure operative",
        tenant_id: str = "default",
        allowed_roles: list[str] | None = None,
        job_id: str | None = None,
        classifier: Any = None,
    ) -> ExtractedTopic:
        """Extract knowledge using centralized LLM (Qwen when configured) with grounded fallback."""
        context_blocks: list[str] = []
        source_passages: list[dict[str, Any]] = []
        doc_version = f"y{bundle.doc_year}" if bundle.doc_year else bundle.file_hash[:8]

        for idx, chunk in enumerate(bundle.chunks):
            txt = self._clean_chunk_text(chunk.page_content)
            cid = str(chunk.metadata.get("chunk_id") or f"{bundle.document_id}::c{idx:04d}")
            sec = str(chunk.metadata.get("heading_path") or chunk.metadata.get("section") or bundle.title)
            page = chunk.metadata.get("page")
            context_blocks.append(f"--- PASSAGGIO {idx + 1} (chunk_id={cid} | section={sec}) ---\n{txt}")
            source_passages.append(
                {
                    "document_id": bundle.document_id,
                    "document_title": bundle.title,
                    "document_version": doc_version,
                    "chunk_id": cid,
                    "page": page if isinstance(page, int) else None,
                    "section": sec,
                    "source": bundle.source,
                    "updated_at": bundle.updated_at,
                    "excerpt": txt[:350],
                }
            )

        combined_ctx = "\n\n".join(context_blocks[:16])
        parsed_llm, used_llm, model_info = self.generator.invoke_structured(
            EXTRACTION_PROMPT,
            {
                "source": bundle.source,
                "area_name": bundle.area_name or "Generale",
                "context": combined_ctx,
            },
            KnowledgeExtractionLLMOutput,
        )

        # Always compute deterministic structure as safety anchor and merge if LLM missed passages
        det = self._deterministic_extract(bundle)
        if parsed_llm is not None and used_llm:
            extracted = parsed_llm
            if not extracted.practical_examples and det.practical_examples:
                extracted.practical_examples = det.practical_examples
            if not extracted.software_modules and det.software_modules:
                extracted.software_modules = det.software_modules
            mode = "llm"
            model_used = f"{model_info['provider']}:{model_info['configured_model']}"
        else:
            extracted = det
            mode = "deterministic"
            model_used = "deterministic_fallback"

        if classifier is not None:
            category = classifier.classify(extracted, context_text=combined_ctx, bundle=bundle).category

        roles = allowed_roles or ["operatore", "admin"]
        topic_id = f"top_{uuid.uuid4().hex[:12]}"

        with self.db.session() as db:
            # Upsert by (document_id, tenant_id) to avoid duplicates on re-analysis
            existing = (
                db.query(ExtractedTopic)
                .filter_by(document_id=bundle.document_id, tenant_id=tenant_id)
                .first()
            )
            if existing is not None:
                existing.job_id = job_id
                existing.allowed_roles = roles
                existing.source = bundle.source
                existing.file_hash = bundle.file_hash
                existing.doc_year = bundle.doc_year
                existing.area_name = bundle.area_name
                existing.category = category
                existing.title = extracted.title or bundle.title
                existing.summary = extracted.summary
                existing.procedures = [p.model_dump() for p in extracted.procedures]
                existing.rules = extracted.rules
                existing.recurring_concepts = extracted.recurring_concepts
                existing.practical_examples = [e.model_dump() for e in extracted.practical_examples]
                existing.frequent_errors = [err.model_dump() for err in extracted.frequent_errors]
                existing.constraints = extracted.constraints
                existing.related_topics = extracted.related_topics
                existing.software_modules = extracted.software_modules
                existing.target_roles = extracted.target_roles
                existing.source_passages = source_passages
                existing.extraction_mode = mode
                existing.model_used = model_used
                db.commit()
                db.refresh(existing)
                return existing

            row = ExtractedTopic(
                id=topic_id,
                job_id=job_id,
                tenant_id=tenant_id,
                allowed_roles=roles,
                document_id=bundle.document_id,
                source=bundle.source,
                file_hash=bundle.file_hash,
                doc_year=bundle.doc_year,
                area_name=bundle.area_name,
                category=category,
                title=extracted.title or bundle.title,
                summary=extracted.summary,
                procedures=[p.model_dump() for p in extracted.procedures],
                rules=extracted.rules,
                recurring_concepts=extracted.recurring_concepts,
                practical_examples=[e.model_dump() for e in extracted.practical_examples],
                frequent_errors=[err.model_dump() for err in extracted.frequent_errors],
                constraints=extracted.constraints,
                related_topics=extracted.related_topics,
                software_modules=extracted.software_modules,
                target_roles=extracted.target_roles,
                source_passages=source_passages,
                extraction_mode=mode,
                model_used=model_used,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
