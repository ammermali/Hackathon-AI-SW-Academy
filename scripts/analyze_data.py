"""
Data Analysis Script for Operator Copilot.
Recursively scans `data/`, verifies readability, detects duplicates,
analyzes structural patterns, checks for PII/sensitive data, and outputs
a structured summary for `docs/DATA_ANALYSIS.md`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path


DATA_DIR = Path("data")

# Regex patterns for PII / sensitive data detection (for audit only, values are masked)
PII_PATTERNS = {
    "email": re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),
    "codice_fiscale": re.compile(
        r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b"
    ),
    "iban": re.compile(r"\bIT\d{2}[A-Z]\d{10}[0-9A-Z]{12}\b"),
    "ipv4": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"),
    "phone": re.compile(r"(?:\+39\s?)?0\d{1,3}[\s.-]?\d{5,8}\b"),
    "url": re.compile(r"https?://[^\s\)\]>\"']+"),
    "password_mention": re.compile(r"\b(password|pwd|credenziali|token|chiave\s+privata|pin)\b", re.IGNORECASE),
}

SCREENSHOT_RE = re.compile(r"\[(Schermata|Screenshot|Immagine|Figura)[^\]]*\]", re.IGNORECASE)
MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
BREADCRUMB_RE = re.compile(r"[⇒→▶]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
TABLE_LINE_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
YEAR_RE = re.compile(r"\b(20(?:1\d|2[0-6]))\b")


def analyze_directory(data_dir: Path) -> dict:
    if not data_dir.exists():
        return {"exists": False}

    ext_counts = Counter()
    ext_bytes = defaultdict(int)
    top_folders = Counter()
    all_subdirs = set()

    readable_files = []
    unreadable_files = []
    empty_files = []
    encoding_issues = []

    hashes = defaultdict(list)
    normalized_hashes = defaultdict(list)

    lengths_chars = []
    lengths_words = []
    lengths_lines = []

    files_with_tables = []
    predominantly_tabular = []
    files_with_screenshots = 0
    total_screenshot_placeholders = 0
    md_image_links = []
    files_with_breadcrumbs = 0
    files_with_headings = 0
    heading_counts = []
    index_files = []
    years_found = Counter()

    pii_findings = defaultdict(list)
    doc_types_guess = Counter()
    samples = {}

    for root, dirs, files in os.walk(data_dir):
        root_path = Path(root)
        for d in dirs:
            rel_d = (root_path / d).relative_to(data_dir)
            all_subdirs.add(str(rel_d))

        for fname in sorted(files):
            fpath = root_path / fname
            rel_path = fpath.relative_to(data_dir)
            top_folder = rel_path.parts[0] if len(rel_path.parts) > 1 else "(root)"
            top_folders[top_folder] += 1

            ext = fpath.suffix.lower() or "(no_ext)"
            size = fpath.stat().st_size
            ext_counts[ext] += 1
            ext_bytes[ext] += size

            if size == 0:
                empty_files.append(str(rel_path))
                continue

            # Try reading as UTF-8, fallback to cp1252/latin-1
            text = None
            encoding_used = "utf-8"
            try:
                text = fpath.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    text = fpath.read_text(encoding="cp1252")
                    encoding_used = "cp1252"
                    encoding_issues.append((str(rel_path), "cp1252"))
                except Exception as exc:
                    unreadable_files.append((str(rel_path), str(exc)))
                    continue
            except Exception as exc:
                unreadable_files.append((str(rel_path), str(exc)))
                continue

            if not text.strip():
                empty_files.append(str(rel_path))
                continue

            readable_files.append((str(rel_path), size, encoding_used))

            # Hashes for duplicate detection
            raw_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            hashes[raw_hash].append(str(rel_path))

            norm_text = re.sub(r"\s+", " ", text.strip().lower())
            norm_hash = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()
            normalized_hashes[norm_hash].append(str(rel_path))

            # Lengths
            n_chars = len(text)
            n_words = len(text.split())
            lines = text.splitlines()
            n_lines = len(lines)
            lengths_chars.append(n_chars)
            lengths_words.append(n_words)
            lengths_lines.append(n_lines)

            # Structural features
            table_lines = TABLE_LINE_RE.findall(text)
            if table_lines:
                files_with_tables.append((str(rel_path), len(table_lines), n_lines))
                non_empty_lines = [l for l in lines if l.strip()]
                if non_empty_lines and (len(table_lines) / len(non_empty_lines)) >= 0.45:
                    predominantly_tabular.append(
                        (str(rel_path), len(table_lines), len(non_empty_lines))
                    )

            scr_matches = SCREENSHOT_RE.findall(text)
            if scr_matches:
                files_with_screenshots += 1
                total_screenshot_placeholders += len(scr_matches)

            img_matches = MD_IMAGE_RE.findall(text)
            if img_matches:
                md_image_links.append((str(rel_path), len(img_matches)))

            if BREADCRUMB_RE.search(text):
                files_with_breadcrumbs += 1

            headings = HEADING_RE.findall(text)
            if headings:
                files_with_headings += 1
                heading_counts.append(len(headings))

            lower_name = fname.lower()
            lower_rel = str(rel_path).lower()
            if "indice" in lower_name or fname.upper() == "INDEX.MD":
                index_files.append(str(rel_path))

            # Years
            for y in YEAR_RE.findall(text):
                years_found[y] += 1

            # Category / Doc type heuristics from path
            if "comunicazioni" in lower_rel:
                doc_types_guess["comunicazione"] += 1
            elif "faq" in lower_rel or "frequently asked" in lower_rel:
                doc_types_guess["faq"] += 1
            elif "webinar" in lower_rel:
                doc_types_guess["webinar"] += 1
            elif "slide" in lower_rel:
                doc_types_guess["slide"] += 1
            elif "cronologia" in lower_rel or "rilasci" in lower_rel:
                doc_types_guess["release_note"] += 1
            elif "norme" in lower_rel:
                doc_types_guess["normativa"] += 1
            elif "indice" in lower_name or fname.upper() == "INDEX.MD":
                doc_types_guess["indice"] += 1
            else:
                doc_types_guess["manuale_procedura"] += 1

            # PII checks
            for pii_key, pat in PII_PATTERNS.items():
                matches = pat.findall(text)
                if matches:
                    if pii_key == "url":
                        # Only track count, not every url
                        if len(pii_findings[pii_key]) < 15:
                            pii_findings[pii_key].append((str(rel_path), matches[0]))
                    else:
                        # Mask sensitive part if CF/IBAN/email
                        sample_val = matches[0] if isinstance(matches[0], str) else str(matches[0])
                        pii_findings[pii_key].append((str(rel_path), len(matches), sample_val))

            # Collect representative samples
            if "index_root" not in samples and fname.upper() == "INDEX.MD":
                samples["index_root"] = (str(rel_path), text[:800])
            if "short" not in samples and 300 <= n_chars <= 500:
                samples["short"] = (str(rel_path), text[:600])
            if "tabular" not in samples and len(table_lines) >= 10:
                samples["tabular"] = (str(rel_path), text[:1000])
            if "procedural" not in samples and BREADCRUMB_RE.search(text) and scr_matches:
                samples["procedural"] = (str(rel_path), text[:1000])
            if "long_manual" not in samples and n_chars > 40000 and fname.upper() != "INDEX.MD":
                samples["long_manual"] = (str(rel_path), text[:1000])

    exact_dups = {h: paths for h, paths in hashes.items() if len(paths) > 1}
    norm_dups = {h: paths for h, paths in normalized_hashes.items() if len(paths) > 1}

    # Summarize PII counts
    pii_summary = {}
    for k, items in pii_findings.items():
        if k == "url":
            pii_summary[k] = {"sample_files": len(items), "examples": items[:5]}
        else:
            unique_vals = list({it[2] for it in items})
            pii_summary[k] = {
                "files_count": len(items),
                "total_matches": sum(it[1] for it in items),
                "sample_values": unique_vals[:10],
                "sample_files": [it[0] for it in items[:5]],
            }

    lengths_chars.sort()
    lengths_words.sort()

    def pct(arr, p):
        if not arr:
            return 0
        idx = min(len(arr) - 1, int(len(arr) * p))
        return arr[idx]

    return {
        "exists": True,
        "total_files": sum(ext_counts.values()),
        "total_bytes": sum(ext_bytes.values()),
        "total_subdirs": len(all_subdirs),
        "top_folders": dict(sorted(top_folders.items())),
        "extensions": {k: {"count": ext_counts[k], "bytes": ext_bytes[k]} for k in ext_counts},
        "readable_count": len(readable_files),
        "unreadable_files": unreadable_files,
        "empty_files": empty_files,
        "encoding_issues": encoding_issues,
        "exact_duplicate_groups": list(exact_dups.values()),
        "normalized_duplicate_groups": list(norm_dups.values()),
        "char_stats": {
            "min": min(lengths_chars),
            "p25": pct(lengths_chars, 0.25),
            "median": statistics.median(lengths_chars),
            "mean": round(statistics.mean(lengths_chars), 1),
            "p75": pct(lengths_chars, 0.75),
            "p95": pct(lengths_chars, 0.95),
            "max": max(lengths_chars),
        },
        "word_stats": {
            "min": min(lengths_words),
            "median": statistics.median(lengths_words),
            "mean": round(statistics.mean(lengths_words), 1),
            "p95": pct(lengths_words, 0.95),
            "max": max(lengths_words),
        },
        "files_with_tables_count": len(files_with_tables),
        "predominantly_tabular_count": len(predominantly_tabular),
        "predominantly_tabular_examples": predominantly_tabular[:15],
        "files_with_screenshots": files_with_screenshots,
        "total_screenshot_placeholders": total_screenshot_placeholders,
        "md_image_links_count": len(md_image_links),
        "md_image_links_examples": md_image_links[:10],
        "files_with_breadcrumbs": files_with_breadcrumbs,
        "files_with_headings": files_with_headings,
        "avg_headings_per_file": round(statistics.mean(heading_counts), 1) if heading_counts else 0,
        "index_files": index_files,
        "years_top": dict(years_found.most_common(17)),
        "doc_types_guess": dict(doc_types_guess),
        "pii_summary": pii_summary,
        "samples": samples,
    }


if __name__ == "__main__":
    report = analyze_directory(DATA_DIR)
    print(json.dumps(report, indent=2, ensure_ascii=False))
