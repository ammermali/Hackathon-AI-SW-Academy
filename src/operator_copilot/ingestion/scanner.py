"""Recursive directory scanner for Operator Copilot document ingestion."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("operator_copilot.ingestion.scanner")

SUPPORTED_EXTENSIONS = {".md", ".txt", ".json", ".csv"}


@dataclass(frozen=True)
class ScannedFile:
    """Represents a discovered file candidate in the knowledge base directory."""

    absolute_path: Path
    relative_path: str
    extension: str
    size_bytes: int
    file_hash: str
    updated_at: str
    document_id: str


class DataScanner:
    """Scans the configured data directory for supported documents."""

    def __init__(self, data_dir: Path, skip_index_files: bool = True) -> None:
        self.data_dir = data_dir
        self.skip_index_files = skip_index_files

    @staticmethod
    def compute_file_hash(path: Path) -> str:
        """Compute SHA-256 hash of raw file bytes."""
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def compute_document_id(relative_path: str) -> str:
        """Generate a stable document ID from the POSIX relative path."""
        return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]

    def scan(self, max_files: int | None = None) -> list[ScannedFile]:
        """Recursively scan data_dir and return sorted list of ScannedFile objects."""
        if not self.data_dir.exists():
            logger.warning("Data directory does not exist: %s", self.data_dir)
            return []

        results: list[ScannedFile] = []
        for path in sorted(self.data_dir.rglob("*")):
            if not path.is_file():
                continue

            ext = path.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                logger.debug("Skipping unsupported file extension: %s", path.name)
                continue

            rel_posix = path.relative_to(self.data_dir).as_posix()

            # Exclude global INDEX.md if configured (prevents noisy summary retrieval)
            if self.skip_index_files and path.name.upper() == "INDEX.MD":
                logger.info("Skipping root index catalog file: %s", rel_posix)
                continue

            stat = path.stat()
            mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            file_hash = self.compute_file_hash(path)

            results.append(
                ScannedFile(
                    absolute_path=path,
                    relative_path=rel_posix,
                    extension=ext,
                    size_bytes=stat.st_size,
                    file_hash=file_hash,
                    updated_at=mtime_iso,
                    document_id=self.compute_document_id(rel_posix),
                )
            )

            if max_files is not None and len(results) >= max_files:
                break

        logger.info("Scanned %d supported files in %s", len(results), self.data_dir)
        return results
