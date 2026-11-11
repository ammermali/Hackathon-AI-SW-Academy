"""Grounded answer generation with LangChain LCEL, citation mapping, and controlled fallback."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.generation.prompts import ABSTENTION_ANSWER, build_rag_prompt
from operator_copilot.ingestion.normalizer import strip_area_prefix
from operator_copilot.retrieval.retriever import RetrievedChunk
from operator_copilot.schemas.response import SourceCitation

_T = TypeVar("_T", bound=BaseModel)

logger = logging.getLogger("operator_copilot.generation.answer_generator")

_ABSTENTION_MARKERS = (
    "non contiene informazioni sufficienti",
    "documentazione non è sufficiente",
    "non dispongo di informazioni sufficienti",
    "non ci sono evidenze sufficienti",
)


@dataclass
class GenerationResult:
    """Structured output returned by AnswerGenerator."""

    answer: str
    sources: list[SourceCitation]
    needs_escalation: bool
    abstention_reason: str | None = None
    used_fallback: bool = False


class AnswerGenerator:
    """Generates strictly grounded Italian answers and real citations from retrieved chunks."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm: BaseChatModel | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._custom_llm = llm
        self.prompt = build_rag_prompt()

    def _build_llm(self) -> BaseChatModel | None:
        """Instantiate configured LangChain ChatModel or return None for extractive mode."""
        if self._custom_llm is not None:
            return self._custom_llm

        provider = self.settings.llm_provider
        if provider == "extractive":
            return None

        api_key = self.settings.llm_api_key.get_secret_value() if self.settings.llm_api_key else ""

        if provider in ("openai", "openai_compatible"):
            if not api_key and not self.settings.llm_base_url:
                logger.info("No LLM_API_KEY configured; falling back to grounded extractive generator.")
                return None
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.settings.llm_model,
                api_key=api_key or "not-required",
                base_url=self.settings.llm_base_url or None,
                temperature=self.settings.llm_temperature,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=1,
            )

        if provider == "ollama":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.settings.llm_model,
                api_key="ollama",
                base_url=self.settings.llm_base_url or "http://localhost:11434/v1",
                temperature=self.settings.llm_temperature,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=1,
            )

        return None

    _CF_RE = re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b")
    _IBAN_RE = re.compile(r"\bIT\d{2}[A-Z]\d{10}[0-9A-Z]{12}\b")
    _EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

    @staticmethod
    def _sanitize_context_text(text: str) -> str:
        """Neutralize delimiter tags inside documents to mitigate prompt injection."""
        return text.replace("</retrieved_context>", "[/retrieved_context]").replace(
            "<retrieved_context>", "[retrieved_context]"
        )

    @classmethod
    def redact_pii(cls, text: str) -> str:
        """Mask personal CF, IBAN, and personal-looking emails before external LLM calls."""
        masked = cls._CF_RE.sub("[CF_PROTETTO]", text)
        masked = cls._IBAN_RE.sub("[IBAN_PROTETTO]", masked)
        # Preserve official palitalsoft support addresses mentioned in operational guides; mask other emails
        def _mask_email(m: re.Match[str]) -> str:
            val = m.group(0)
            if val.lower().endswith("@palitalsoft.it") or val.lower().endswith("@palinformatica.it"):
                return val
            return "[EMAIL_PROTETTA]"
        return cls._EMAIL_RE.sub(_mask_email, masked)

    def get_model_info(self) -> dict[str, Any]:
        """Return centralized model configuration and Qwen verification metadata."""
        llm = self._build_llm()
        configured_model = self.settings.llm_model
        if self._custom_llm is not None:
            custom_name = getattr(self._custom_llm, "model_name", None) or getattr(self._custom_llm, "model", None)
            if isinstance(custom_name, str) and custom_name.strip():
                configured_model = custom_name.strip()

        expected = self.settings.llm_expected_model_family.lower()
        is_qwen = expected in configured_model.lower()
        return {
            "provider": self.settings.llm_provider,
            "configured_model": configured_model,
            "expected_family": self.settings.llm_expected_model_family,
            "is_qwen_configured": is_qwen,
            "base_url": self.settings.llm_base_url or (
                "http://localhost:11434/v1" if self.settings.llm_provider == "ollama" else None
            ),
            "llm_runtime_active": llm is not None,
            "active_mode": "llm" if llm is not None else "deterministic_fallback",
            "embedding_model": f"{self.settings.embedding_provider}:{self.settings.embedding_model}",
        }

    def invoke_structured(
        self,
        prompt_template: ChatPromptTemplate,
        variables: dict[str, Any],
        schema_cls: type[_T],
    ) -> tuple[_T | None, bool, dict[str, Any]]:
        """Invoke centralized LLM (Qwen) with structured Pydantic output and safe JSON fallback."""
        model_info = self.get_model_info()
        llm = self._build_llm()
        if llm is None:
            return None, False, model_info

        safe_vars = dict(variables)
        if "context" in safe_vars and isinstance(safe_vars["context"], str):
            ctx = self._sanitize_context_text(safe_vars["context"])
            if self.settings.pii_redact_before_llm:
                ctx = self.redact_pii(ctx)
            safe_vars["context"] = ctx

        # 1. Try native structured output when supported by chat model
        try:
            structured_llm = llm.with_structured_output(schema_cls)
            parsed = (prompt_template | structured_llm).invoke(safe_vars)
            if isinstance(parsed, schema_cls):
                return parsed, True, model_info
            if isinstance(parsed, dict):
                return schema_cls.model_validate(parsed), True, model_info
        except Exception as exc:
            logger.debug("with_structured_output unavailable/failed (%s); trying JSON text parse.", exc)

        # 2. Fallback: raw text chain + JSON object extraction
        try:
            raw_text = (prompt_template | llm | StrOutputParser()).invoke(safe_vars).strip()
            match = re.search(r"\{[\s\S]*\}", raw_text)
            json_str = match.group(0) if match else raw_text
            data = json.loads(json_str)
            return schema_cls.model_validate(data), True, model_info
        except Exception as exc:
            logger.warning("Structured LLM invocation failed (%s); falling back to deterministic engine.", exc)
            return None, False, model_info

    @staticmethod
    def build_citations(chunks: list[RetrievedChunk]) -> list[SourceCitation]:
        """Build SourceCitation objects strictly from real chunk metadata."""
        citations: list[SourceCitation] = []
        seen_chunk_ids: set[str] = set()
        for item in chunks:
            meta = item.document.metadata
            chunk_id = str(meta.get("chunk_id") or "")
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)

            doc_name = str(meta.get("source") or meta.get("filename") or meta.get("title") or "Documento sconosciuto")
            section = str(meta.get("heading_path") or meta.get("section") or "")
            raw_page = meta.get("page")
            page = int(raw_page) if isinstance(raw_page, int) else None
            area = str(meta["area_name"]) if meta.get("area_name") else None

            citations.append(
                SourceCitation(
                    document=doc_name,
                    section=section,
                    page=page,
                    chunk_id=chunk_id or "unknown_chunk",
                    area=area,
                    relevance_score=round(item.relevance_score, 4),
                )
            )
        return citations

    def _format_context(self, chunks: list[RetrievedChunk]) -> str:
        blocks: list[str] = []
        for idx, item in enumerate(chunks, start=1):
            meta = item.document.metadata
            source = meta.get("source", "unknown")
            section = meta.get("heading_path", meta.get("section", ""))
            chunk_id = meta.get("chunk_id", f"chunk_{idx}")
            body = self._sanitize_context_text(item.document.page_content)
            blocks.append(
                f"--- FONTE {idx} (document={source} | section={section} | chunk_id={chunk_id}) ---\n{body}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _strip_context_prefix(text: str) -> str:
        """Remove internal chunk header prefix before presenting extractive snippets."""
        return strip_area_prefix(text)

    @staticmethod
    def _format_extractive_snippet(raw_text: str, doc_label: str, section: str) -> str:
        """Clean chunk text, drop redundant title headings, demote subheadings, and truncate safely."""
        cleaned = strip_area_prefix(raw_text).strip()
        lines = cleaned.splitlines()

        leaf_section = section.split(">")[-1].strip().lower() if section else ""
        norm_label = doc_label.strip().lower()

        # Drop leading Markdown heading when it merely duplicates the source title/section
        if lines:
            m = re.match(r"^#{1,6}\s+(.+?)\s*$", lines[0].strip())
            if m:
                heading_text = m.group(1).strip().lower()
                if heading_text in {norm_label, leaf_section}:
                    lines = lines[1:]
                    while lines and not lines[0].strip():
                        lines = lines[1:]

        # Demote document headings outside code fences so ### source headers stay top-level
        demoted: list[str] = []
        in_fence = False
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                demoted.append(line)
                continue
            if not in_fence:
                line = re.sub(r"^#{1,3}(\s+)", r"####\1", line)
            demoted.append(line)

        snippet = "\n".join(demoted).strip()
        if len(snippet) > 750:
            cut = snippet[:750].rfind("\n")
            if cut < 250:
                cut = snippet[:750].rfind(". ")
            snippet = snippet[: cut if cut > 200 else 750].rstrip() + "..."
            if snippet.count("```") % 2 == 1:
                snippet += "\n```"
        return snippet

    def _extractive_fallback(self, query: str, chunks: list[RetrievedChunk]) -> str:
        """Produce a strictly grounded Italian procedural summary directly from retrieved chunks."""
        blocks = [
            f'In base alla documentazione recuperata per "{query}", risultano rilevanti le seguenti indicazioni operative:'
        ]
        source_sections: list[str] = []
        for idx, item in enumerate(chunks[:3], start=1):
            meta = item.document.metadata
            doc_label = str(meta.get("title") or meta.get("source") or "Documento").strip()
            section = str(meta.get("heading_path") or meta.get("section") or "").strip()
            snippet = self._format_extractive_snippet(item.document.page_content, doc_label, section)

            parts = [f"### {idx}. {doc_label}"]
            if section and section.lower() != doc_label.lower():
                parts.append(f"*Sezione: {section}*")
            if snippet:
                parts.append(snippet)
            source_sections.append("\n\n".join(parts))

        if source_sections:
            blocks.append("\n\n---\n\n".join(source_sections))

        blocks.append(
            "_Nota: sintesi estratta direttamente dai passaggi documentali recuperati senza elaborazione generativa esterna._"
        )
        return "\n\n".join(blocks)

    def generate(self, query: str, chunks: list[RetrievedChunk]) -> GenerationResult:
        """Generate grounded answer or abstain safely if evidence is missing."""
        if not chunks:
            return GenerationResult(
                answer=ABSTENTION_ANSWER,
                sources=[],
                needs_escalation=True,
                abstention_reason="Nessun documento sopra la soglia di rilevanza configurata.",
            )

        citations = self.build_citations(chunks)
        llm = self._build_llm()

        if llm is None:
            answer = self._extractive_fallback(query, chunks)
            return GenerationResult(
                answer=answer,
                sources=citations,
                needs_escalation=False,
                used_fallback=True,
            )

        context = self._format_context(chunks)
        chain = self.prompt | llm | StrOutputParser()
        try:
            answer = chain.invoke({"query": query, "context": context}).strip()
            needs_escalation = any(marker in answer.lower() for marker in _ABSTENTION_MARKERS)
            return GenerationResult(
                answer=answer,
                sources=citations if not needs_escalation else citations,
                needs_escalation=needs_escalation,
                abstention_reason="Evidenza documentale giudicata insufficiente dal modello." if needs_escalation else None,
            )
        except Exception as exc:
            logger.error("LLM provider error during generation (%s); using grounded fallback.", exc)
            fallback_answer = self._extractive_fallback(query, chunks)
            return GenerationResult(
                answer=fallback_answer,
                sources=citations,
                needs_escalation=False,
                used_fallback=True,
            )
