"""Shared helpers for clean, natural, Markdown-free quiz phrasing and option shuffling."""

from __future__ import annotations

import hashlib
import random
import re

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_INLINE_HEADING_RE = re.compile(r"(?:^|\s)#{1,6}\s+")
_BOLD_ITALIC_RE = re.compile(r"(\*{1,3}|_{1,3})(.+?)\1")
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BULLET_PREFIX_RE = re.compile(r"^[\s\-*>•⚠️]+")


def clean_markdown_to_plain(text: str) -> str:
    """Strip Markdown headings, emphasis, links, and decorative symbols into readable prose."""
    if not text:
        return ""
    cleaned = _MD_LINK_RE.sub(r"\1", text)
    cleaned = _HEADING_RE.sub("", cleaned)
    cleaned = _INLINE_HEADING_RE.sub(" ", cleaned)
    for _ in range(2):
        cleaned = _BOLD_ITALIC_RE.sub(r"\2", cleaned)
    cleaned = _CODE_SPAN_RE.sub(r"\1", cleaned)
    # Remove stray unmatched emphasis markers or table pipes
    cleaned = cleaned.replace("**", "").replace("|", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def is_usable_quiz_text(text: str, min_len: int = 25) -> bool:
    """Reject Markdown tables, screenshot alt-captions, trailing colons, and broken fragments."""
    s = (text or "").strip()
    if len(s) < min_len:
        return False
    low = s.lower()
    if s.rstrip().endswith(":"):
        return False
    if s.startswith(">") or "[screenshot" in low or "[immagine" in low:
        return False
    if re.search(r"-{3,}", s):
        return False
    if s[0].islower():
        return False
    if "seguire quanto indicato nella sezione" in low:
        return False
    return True


def truncate_at_boundary(text: str, max_len: int = 165) -> str:
    """Truncate text cleanly at sentence or word boundaries without cutting mid-word."""
    cleaned = clean_markdown_to_plain(text)
    if len(cleaned) <= max_len:
        return cleaned

    slice_part = cleaned[:max_len].rstrip()
    # Prefer ending on real sentence punctuation (skip numbered prefixes like "2. ", abbreviations like "es.", or unclosed parentheses)
    for sep in (". ", "; ", ": "):
        search_from = len(slice_part)
        while search_from > 0:
            pos = slice_part.rfind(sep, 0, search_from)
            if pos < int(max_len * 0.55):
                break
            candidate = slice_part[: pos + 1].strip()
            if sep == ". ":
                before = slice_part[:pos].rstrip()
                # Reject abbreviations ("n.", "es.", "ecc."), digits ("2."), or unbalanced parentheses
                if not re.search(r"[a-zA-ZÀ-ÿ]{4,}$", before) or candidate.count("(") > candidate.count(")"):
                    search_from = pos
                    continue
            if candidate.count("(") > candidate.count(")"):
                search_from = pos
                continue
            return candidate

    last_space = slice_part.rfind(" ")
    if last_space >= int(max_len * 0.45):
        trimmed = slice_part[:last_space].rstrip(" ,;:-")
        if trimmed.count("(") > trimmed.count(")"):
            trimmed = re.sub(r"\s*\([^)]*$", "", trimmed).rstrip(" ,;:-")
        return trimmed + "…"
    return slice_part + "…"


def short_document_label(source: str | None) -> str:
    """Return only the clean filename without folder prefixes."""
    raw = (source or "").strip().replace("\\", "/")
    if not raw:
        return "Documentazione operativa"
    return raw.rsplit("/", 1)[-1].strip() or raw


def short_section_label(section: str | None, fallback: str = "Operatività") -> str:
    """Extract the most specific leaf section from a 'A > B > C' breadcrumb."""
    raw = clean_markdown_to_plain(section or "")
    if not raw:
        return fallback
    parts = [p.strip() for p in raw.split(">") if p.strip()]
    leaf = parts[-1] if parts else raw
    return leaf[:90] + ("…" if len(leaf) > 90 else "")


def build_natural_focus(section: str | None, topic: str | None) -> str:
    """Combine section leaf and topic cleanly without repeating identical text."""
    sec_short = short_section_label(section, fallback="")
    topic_clean = clean_markdown_to_plain(topic or "")
    if sec_short and topic_clean:
        if sec_short.lower() in topic_clean.lower():
            return topic_clean
        if topic_clean.lower() in sec_short.lower():
            return sec_short
        return f"{sec_short} ({topic_clean})"
    return sec_short or topic_clean or "la procedura operativa"


_BOILERPLATE_PREFIX_RE = re.compile(
    r"^(?:scopo\s*:|obiettivo\s*:|con il seguente documento|il presente documento|in questo documento|indice\b|\d{4}\s*[–-]\s*modalit)",
    re.IGNORECASE,
)


def extract_natural_quiz_statements(
    passage_text: str,
    *,
    min_len: int = 35,
    max_len: int = 185,
) -> list[str]:
    """Extract readable factual sentences from documentation, prioritizing concrete rules over intro text."""
    concrete: list[str] = []
    boilerplate: list[str] = []
    seen: set[str] = set()

    def _add_candidate(raw_text: str) -> None:
        bounded = truncate_at_boundary(raw_text, max_len=max_len)
        key = bounded.lower()
        if not is_usable_quiz_text(bounded, min_len=min_len) or key in seen:
            return
        if "scopo: con il seguente documento" in key or "vengono illustrate le corrette modalit" in key:
            boilerplate.append(bounded)
            seen.add(key)
            return
        seen.add(key)
        if _BOILERPLATE_PREFIX_RE.match(bounded):
            boilerplate.append(bounded)
        else:
            concrete.append(bounded)

    kept_lines: list[str] = []
    for raw_line in passage_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("---"):
            continue
        no_bullet = _BULLET_PREFIX_RE.sub("", stripped)
        line = clean_markdown_to_plain(no_bullet)
        if line:
            kept_lines.append(line)
        if len(line) >= min_len:
            _add_candidate(line)

    if not concrete and kept_lines:
        plain_all = " ".join(kept_lines)
        for sent in re.split(r"(?<=[.!?])\s+", plain_all):
            s = sent.strip()
            if len(s) >= min_len:
                _add_candidate(s)
            if len(concrete) >= 4:
                break

    return [*concrete, *boilerplate]


def _token_jaccard(a: str, b: str) -> float:
    ta = {t for t in re.findall(r"[a-z0-9]{3,}", a.lower())}
    tb = {t for t in re.findall(r"[a-z0-9]{3,}", b.lower())}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


_DOMAIN_STOPWORDS = {
    "questo", "questa", "questi", "quello", "della", "dello", "delle", "degli",
    "nella", "nelle", "nello", "negli", "sulla", "sul", "essere", "avere", "viene",
    "vengono", "attraverso", "tramite", "sempre", "prima", "dopo", "secondo",
    "modalita", "modalità", "operazione", "procedura", "sistema", "manuale",
}


def _extract_domain_phrase(text: str, max_words: int = 3) -> str:
    words = [
        w.lower()
        for w in re.findall(r"[a-zA-ZÀ-ÿ0-9]{4,}", clean_markdown_to_plain(text))
        if w.lower() not in _DOMAIN_STOPWORDS
    ]
    unique: list[str] = []
    for w in words:
        if w not in unique:
            unique.append(w)
        if len(unique) >= max_words:
            break
    return ", ".join(unique)


def _is_policy_warning_not_action(text: str) -> bool:
    low = text.strip().lower()
    return low.startswith(("non verr", "non è possibile", "non e possibile", "è vietato", "e vietato"))


def build_contextual_distractors(
    *,
    correct_option: str,
    focus: str,
    mode: str = "correct_rule",
    domain_wrong_pool: list[str] | None = None,
    other_section_pool: list[str] | None = None,
    max_len: int = 165,
) -> list[str]:
    """Build 3 plausible, topic-centered distractors strictly non-contradictory with the correct option."""
    chosen: list[str] = []
    corr_clean = truncate_at_boundary(correct_option, max_len=max_len)
    seen_keys: set[str] = {corr_clean.lower()}
    focus_short = short_section_label(focus, fallback="questa operazione")
    focus_compact = focus_short[:55].rstrip() + ("…" if len(focus_short) > 55 else "")
    domain_terms = _extract_domain_phrase(f"{correct_option} {focus_short}")

    def _try_add(raw: str, *, check_overlap: bool = True) -> None:
        if len(chosen) >= 3:
            return
        if not is_usable_quiz_text(raw, min_len=25):
            return
        cand = truncate_at_boundary(raw, max_len=max_len)
        key = cand.lower()
        if not is_usable_quiz_text(cand, min_len=25) or key in seen_keys:
            return
        if check_overlap and (
            _token_jaccard(corr_clean, cand) >= 0.55
            or key in corr_clean.lower()
            or corr_clean.lower() in key
        ):
            return
        seen_keys.add(key)
        chosen.append(cand)

    if mode == "avoid_error":
        # Correct answer is an error/antipattern -> distractors must be genuine good practices from the course
        for item in domain_wrong_pool or []:
            _try_add(item, check_overlap=True)
            if len(chosen) >= 2:
                break
        for item in other_section_pool or []:
            if _is_policy_warning_not_action(item):
                continue
            _try_add(item, check_overlap=True)
            if len(chosen) >= 3:
                break
        contextual_fallbacks = [
            f"Verificare prerequisiti e dati relativi a {domain_terms or focus_compact} prima di confermare.",
            f"Seguire la sequenza operativa documentata per «{focus_compact}» controllando eventuali avvisi.",
            f"Applicare le verifiche previste nella guida per «{focus_compact}» prima di procedere.",
        ]
    else:
        # Correct answer is a valid rule -> NEVER mix in other true statements from the manual as distractors!
        for item in domain_wrong_pool or []:
            if _is_policy_warning_not_action(item):
                continue
            _try_add(item, check_overlap=True)
            if len(chosen) >= 2:
                break
        kw_note = f" su {domain_terms}" if domain_terms else ""
        contextual_fallbacks = [
            f"Saltare i controlli preliminari previsti in «{focus_compact}»{kw_note} e forzare subito il salvataggio.",
            f"Ignorare i requisiti indicati per «{focus_compact}»{kw_note} adottando un flusso non ufficiale.",
            f"Procedere su «{focus_compact}» senza verificare lo stato corrente e i parametri richiesti.",
        ]

    for fb in contextual_fallbacks:
        _try_add(fb, check_overlap=False)

    return chosen[:3]


def deterministic_shuffle_options(
    correct_option: str,
    distractors: list[str],
    *,
    seed_key: str,
) -> tuple[list[str], int]:
    """Deterministically place the correct answer at a non-fixed position among options."""
    options = [correct_option, *distractors[:3]]
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:12], 16))
    rng.shuffle(options)
    return options, options.index(correct_option)
