"""Document loaders and deterministic metadata extraction for Operator Copilot."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from operator_copilot.ingestion.normalizer import ContentNormalizer
from operator_copilot.ingestion.scanner import ScannedFile

logger = logging.getLogger("operator_copilot.ingestion.loaders")

_AREA_PREFIX_RE = re.compile(r"^(\d{2})\s*-\s*(.+)$")
_FILENAME_PREFIX_RE = re.compile(r"^\d{3}\s*-\s*")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_YEAR_PREFIX_RE = re.compile(r"(?:^|[/_\-\s])(20(?:1\d|2[0-6]))(?:[/_\-\s]|$)")


@dataclass
class LoadedDocument:
    """Loaded and normalized document with deterministic metadata."""

    document_id: str
    source: str
    content: str
    canonical_content: str
    file_hash: str
    normalized_hash: str
    metadata: dict[str, Any]


@dataclass
class LoadError:
    """Represents a file that could not be parsed or was empty."""

    source: str
    document_id: str
    file_hash: str
    error: str


class DocumentLoader:
    """Loads supported document formats and extracts metadata from paths and content."""

    def __init__(self, normalizer: ContentNormalizer | None = None) -> None:
        self.normalizer = normalizer or ContentNormalizer()

    @staticmethod
    def _read_text_with_fallback(path: Path) -> str:
        """Read text file using UTF-8 with CP1252 fallback."""
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="cp1252")

    @staticmethod
    def _format_csv(raw_text: str) -> str:
        """Convert CSV rows to readable Markdown table-like lines."""
        reader = csv.reader(io.StringIO(raw_text))
        rows = list(reader)
        if not rows:
            return ""
        lines = []
        header = rows[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    @staticmethod
    def _format_json(raw_text: str) -> str:
        """Convert JSON payload into clean indented text."""
        parsed = json.loads(raw_text)
        return json.dumps(parsed, indent=2, ensure_ascii=False)

    @classmethod
    def extract_path_metadata(cls, scanned: ScannedFile, content: str) -> dict[str, Any]:
        """Extract metadata strictly from actual directory layout, filename, and headings."""
        parts = Path(scanned.relative_path).parts
        filename = Path(scanned.relative_path).name
        stem = Path(scanned.relative_path).stem

        area_code: str | None = None
        area_name: str | None = None
        subcategory: str | None = None

        if len(parts) > 1:
            top_folder = parts[0]
            m = _AREA_PREFIX_RE.match(top_folder)
            if m:
                area_code = m.group(1)
                area_name = m.group(2).strip()
            else:
                area_name = top_folder

            if len(parts) > 2:
                subcategory = "/".join(parts[1:-1])

        # Infer document type strictly from folder/filename cues
        lower_rel = scanned.relative_path.lower()
        lower_name = filename.lower()
        if "comunicazioni" in lower_rel or re.match(r"^\d{4}_c\d+", lower_name):
            doc_type = "communication"
        elif "frequently asked" in lower_rel or "faq" in lower_name:
            doc_type = "faq"
        elif "webinar" in lower_rel:
            doc_type = "webinar"
        elif "slide" in lower_rel:
            doc_type = "slide"
        elif "cronologia rilasci" in lower_rel:
            doc_type = "release_note"
        elif "norme" in lower_rel:
            doc_type = "normative"
        elif "indice" in lower_name or filename.upper() == "INDEX.MD":
            doc_type = "index"
        else:
            doc_type = "manual"

        # Extract title from first H1 or cleaned filename
        h1_match = _H1_RE.search(content)
        if h1_match:
            title = h1_match.group(1).strip()
        else:
            title = _FILENAME_PREFIX_RE.sub("", stem).replace("_", " ").strip()

        # Extract document year if explicitly encoded in filename or subfolder
        doc_year: int | None = None
        yr_match = _YEAR_PREFIX_RE.search(scanned.relative_path)
        if yr_match:
            doc_year = int(yr_match.group(1))

        meta: dict[str, Any] = {
            "source": scanned.relative_path,
            "filename": filename,
            "document_id": scanned.document_id,
            "title": title,
            "document_type": doc_type,
            "file_hash": scanned.file_hash,
            "updated_at": scanned.updated_at,
        }
        if area_code is not None:
            meta["area_code"] = area_code
        if area_name is not None:
            meta["area_name"] = area_name
        if subcategory is not None:
            meta["subcategory"] = subcategory
        if doc_year is not None:
            meta["doc_year"] = doc_year

        return meta

    def load(self, scanned: ScannedFile) -> LoadedDocument | LoadError:
        """Load and normalize a single ScannedFile; returns LoadError on failure."""
        try:
            raw_text = self._read_text_with_fallback(scanned.absolute_path)
            if scanned.extension == ".csv":
                raw_text = self._format_csv(raw_text)
            elif scanned.extension == ".json":
                raw_text = self._format_json(raw_text)

            normalized = self.normalizer.normalize(raw_text)
            if not normalized:
                return LoadError(
                    source=scanned.relative_path,
                    document_id=scanned.document_id,
                    file_hash=scanned.file_hash,
                    error="Documento vuoto dopo normalizzazione.",
                )

            canon = self.normalizer.canonical_for_dedup(raw_text)
            norm_hash = self.normalizer.normalized_hash(raw_text)
            metadata = self.extract_path_metadata(scanned, normalized)

            return LoadedDocument(
                document_id=scanned.document_id,
                source=scanned.relative_path,
                content=normalized,
                canonical_content=canon,
                file_hash=scanned.file_hash,
                normalized_hash=norm_hash,
                metadata=metadata,
            )
        except Exception as exc:
            logger.warning("Failed to load %s: %s", scanned.relative_path, exc)
            return LoadError(
                source=scanned.relative_path,
                document_id=scanned.document_id,
                file_hash=scanned.file_hash,
                error=str(exc),
            )
