"""Text normalization and canonicalization utilities for ingestion."""

from __future__ import annotations

import hashlib
import re

_AREA_PREFIX_RE = re.compile(r"^\[Area:[^\]]+\]\n")


def strip_area_prefix(text: str) -> str:
    """Remove internal [Area: ...] chunk header prefix consistently across engines."""
    return _AREA_PREFIX_RE.sub("", text).strip()


class ContentNormalizer:
    """Normalizes Markdown/text documents while preserving semantic structure and UI cues."""

    _BROKEN_PLACEHOLDER_IMG_RE = re.compile(r"!\[[^\]]*\]\(placeholder\)", re.IGNORECASE)
    _LINK_UTILI_RE = re.compile(r"^\*\*Link utili:\*\*.*$", re.MULTILINE | re.IGNORECASE)
    _MULTI_BLANK_RE = re.compile(r"\n{3,}")
    _TRAIL_SPACE_RE = re.compile(r"[ \t]+$", re.MULTILINE)

    def normalize(self, text: str) -> str:
        """Clean formatting noise while keeping [Schermata: ...], tables, and headings intact."""
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = self._BROKEN_PLACEHOLDER_IMG_RE.sub("", cleaned)
        cleaned = self._TRAIL_SPACE_RE.sub("", cleaned)
        cleaned = self._MULTI_BLANK_RE.sub("\n\n", cleaned)
        return cleaned.strip()

    def canonical_for_dedup(self, text: str) -> str:
        """Produce canonicalized text stripping wiki navigation links and whitespace for dedup."""
        canon = self.normalize(text)
        canon = self._LINK_UTILI_RE.sub("", canon)
        canon = re.sub(r"\s+", " ", canon).strip().lower()
        return canon

    def normalized_hash(self, text: str) -> str:
        """Compute SHA-256 hash of canonicalized text."""
        canon = self.canonical_for_dedup(text)
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    @staticmethod
    def word_shingles(text: str, k: int = 5) -> set[int]:
        """Compute hashed k-word shingles for fast near-duplicate Jaccard comparison."""
        tokens = re.findall(r"\w+", text.lower())
        if len(tokens) < k:
            return {hash(" ".join(tokens))} if tokens else set()
        return {hash(" ".join(tokens[i : i + k])) for i in range(len(tokens) - k + 1)}

    @classmethod
    def jaccard_similarity(cls, text_a: str, text_b: str, k: int = 5) -> float:
        """Compute k-shingle Jaccard similarity in [0.0, 1.0]."""
        s_a = cls.word_shingles(text_a, k=k)
        s_b = cls.word_shingles(text_b, k=k)
        if not s_a or not s_b:
            return 0.0
        inter = len(s_a & s_b)
        union = len(s_a | s_b)
        return inter / union if union else 0.0
