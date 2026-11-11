"""Structure-aware Markdown and text chunking using LangChain text splitters."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from operator_copilot.ingestion.loaders import LoadedDocument

_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)


class DocumentChunker:
    """Splits LoadedDocuments respecting Markdown heading hierarchy and tables."""

    HEADERS_TO_SPLIT_ON = [
        ("#", "h1"),
        ("##", "h2"),
        ("###", "h3"),
    ]

    def __init__(self, chunk_size: int = 1200, chunk_overlap: int = 180) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.HEADERS_TO_SPLIT_ON,
            strip_headers=False,
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n### ", "\n## ", "\n", ". ", " ", ""],
            length_function=len,
        )

    @staticmethod
    def _build_heading_path(header_meta: dict[str, str], fallback_title: str) -> tuple[str, str]:
        """Return (leaf_section, full_heading_path) from Markdown header metadata."""
        levels = [header_meta[k].strip() for k in ("h1", "h2", "h3") if k in header_meta and header_meta[k].strip()]
        if not levels:
            return fallback_title, fallback_title
        return levels[-1], " > ".join(levels)

    def _split_preserving_tables(self, text: str) -> list[str]:
        """Split long sections while attempting not to break small/medium Markdown tables."""
        if len(text) <= self.chunk_size:
            return [text]

        # Split by paragraph blocks first so cohesive tables <= chunk_size stay intact
        blocks = text.split("\n\n")
        chunks: list[str] = []
        current = ""

        for block in blocks:
            candidate = f"{current}\n\n{block}" if current else block
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                    current = ""

                if len(block) <= self.chunk_size:
                    current = block
                else:
                    # Single block (e.g. a huge table or very long paragraph) exceeds chunk_size
                    sub_chunks = self.text_splitter.split_text(block)
                    chunks.extend(sub_chunks)

        if current:
            chunks.append(current)

        return chunks

    def chunk_document(self, loaded: LoadedDocument) -> list[Document]:
        """Split a LoadedDocument into LangChain Document chunks with inherited metadata."""
        is_markdown = loaded.metadata.get("filename", "").lower().endswith(".md")
        title = str(loaded.metadata.get("title") or loaded.source)
        area = str(loaded.metadata.get("area_name") or "Generale")

        if is_markdown:
            header_docs = self.md_splitter.split_text(loaded.content)
        else:
            header_docs = [Document(page_content=loaded.content, metadata={})]

        if not header_docs:
            header_docs = [Document(page_content=loaded.content, metadata={})]

        result_chunks: list[Document] = []
        chunk_idx = 0

        for hdoc in header_docs:
            section, heading_path = self._build_heading_path(hdoc.metadata, title)
            pieces = self._split_preserving_tables(hdoc.page_content.strip())

            for piece in pieces:
                piece_clean = piece.strip()
                if not piece_clean:
                    continue

                chunk_id = f"{loaded.document_id}::c{chunk_idx:04d}"
                has_table = bool(_TABLE_ROW_RE.search(piece_clean))

                # Contextualize chunk text so standalone retrieval keeps document & section anchors
                prefix = f"[Area: {area} | Documento: {title} | Sezione: {heading_path}]\n"
                contextualized_text = prefix + piece_clean

                chunk_meta: dict[str, Any] = {
                    **loaded.metadata,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_idx,
                    "section": section,
                    "heading_path": heading_path,
                    "has_table": has_table,
                }
                # Ensure Chroma-compatible primitive types only
                sanitized_meta = {
                    k: v for k, v in chunk_meta.items() if isinstance(v, (str, int, float, bool))
                }

                result_chunks.append(
                    Document(page_content=contextualized_text, metadata=sanitized_meta)
                )
                chunk_idx += 1

        return result_chunks
