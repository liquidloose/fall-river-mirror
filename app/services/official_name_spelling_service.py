git bran"""
Spelling check for Fall River official names in articles.
Catches both clear typos and fuzzier / wildly off misspellings (e.g. Kugan → Coogan).
Prioritizes catching official name errors; occasionally flagging a citizen name is acceptable.
"""
import difflib
import re
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Words that suggest official context (government rep mentioned)
OFFICIAL_CONTEXT_WORDS = frozenset(
    w.lower()
    for w in (
        "councilor",
        "council",
        "chair",
        "mayor",
        "vice",
        "president",
        "said",
        "voted",
        "motion",
        "committee",
        "commission",
        "board",
        "authority",
        "member",
        "members",
        "clerk",
        "director",
        "chairperson",
        "treasurer",
        "attorney",
        "sergeant",
        "reverend",
        "dr.",
        "esq.",
        "ex-officio",
    )
)

# Similarity thresholds: lower to catch fuzzier misspellings (e.g. Kugan → Coogan)
SIMILARITY_THRESHOLD = 0.78  # with official context
SIMILARITY_THRESHOLD_STRICT = 0.85  # without context (still catch more)
# Edit distance: flag when within this many edits (for short names / wildly off typos)
MAX_EDIT_DISTANCE = 2
# Max length to use edit-distance path (single token / last name)
MAX_LEN_FOR_EDIT_DISTANCE = 14
# Snippet context chars before/after
SNIPPET_PAD = 50


def _has_official_context(text: str, start: int, end: int) -> bool:
    """Return True if text around (start, end) contains official-context words."""
    window_start = max(0, start - 120)
    window_end = min(len(text), end + 120)
    window = text[window_start:window_end].lower()
    words = set(re.findall(r"[a-z']+", window))
    return bool(words & OFFICIAL_CONTEXT_WORDS)


def _is_likely_full_name(substring: str, canonical: str) -> bool:
    """True if substring looks like a full name (multiple words) and matches canonical structure."""
    parts = substring.split()
    return len(parts) >= 2 and len(canonical.split()) >= 2


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein (edit) distance between two strings."""
    a, b = a.lower(), b.lower()
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    # dp[i][j] = edit distance for a[:i], b[:j]
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i]
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[m]


def _extract_snippet(text: str, start: int, end: int) -> str:
    s = max(0, start - SNIPPET_PAD)
    e = min(len(text), end + SNIPPET_PAD)
    return text[s:e].strip()


def _should_flag(
    substring: str,
    canonical: str,
    has_context: bool,
) -> bool:
    """True if this substring should be flagged as a misspelling of canonical."""
    if substring.lower() == canonical.lower():
        return False
    ratio = _similarity(substring, canonical)
    # Similarity path: catch clear and fuzzier typos (lower thresholds)
    if has_context and ratio >= SIMILARITY_THRESHOLD:
        return True
    if _is_likely_full_name(substring, canonical) and ratio >= SIMILARITY_THRESHOLD_STRICT:
        return True
    # Edit-distance path: catch wildly off (e.g. Kugan → Coogan)
    if abs(len(substring) - len(canonical)) <= 3:
        if len(canonical) <= MAX_LEN_FOR_EDIT_DISTANCE or len(substring) <= MAX_LEN_FOR_EDIT_DISTANCE:
            dist = _edit_distance(substring, canonical)
            if dist <= MAX_EDIT_DISTANCE and (has_context or _is_likely_full_name(substring, canonical)):
                return True
    return False


def _build_canonical_index(canonical_names: List[str]) -> Dict[str, List[str]]:
    """Index canonicals by first letter (of first word) for fast candidate lookup."""
    index: Dict[str, List[str]] = {}
    for c in canonical_names:
        if not c or len(c) < 3:
            continue
        first = c.strip()[0].lower()
        index.setdefault(first, []).append(c)
    return index


def _get_candidate_canonicals(phrase: str, index: Dict[str, List[str]]) -> List[str]:
    """Return canonicals that might match this phrase (same first letter, similar length)."""
    if not phrase:
        return []
    first = phrase.strip()[0].lower()
    candidates = index.get(first, [])
    plen = len(phrase)
    return [c for c in candidates if abs(len(c) - plen) <= 5]


def _words_with_positions(text: str) -> List[Tuple[int, int, str]]:
    """Return list of (start, end, word) for each word in text."""
    return [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", text)]


def _find_misspellings_in_text(
    text: str,
    canonical_names: List[str],
) -> List[Dict[str, Any]]:
    """
    Find substrings in text that are likely misspellings of a canonical name.
    Word-based: only check contiguous word phrases (1-5 words), indexed by first letter.
    Much faster than character sliding.
    """
    if not text or not canonical_names:
        return []
    text_lower = text.lower()
    exact_canonicals = {c.lower() for c in canonical_names if c and len(c) >= 3}
    index = _build_canonical_index(canonical_names)
    words = _words_with_positions(text)
    issues: List[Dict[str, Any]] = []
    seen_found: set = set()

    # Consider phrases of 1 to 5 words
    max_phrase_words = 5
    for i in range(len(words)):
        for j in range(i, min(i + max_phrase_words, len(words))):
            start = words[i][0]
            end = words[j][1]
            phrase = text[start:end].strip()
            if len(phrase) < 3:
                continue
            phrase_lower = phrase.lower()
            if phrase_lower in exact_canonicals:
                continue
            candidates = _get_candidate_canonicals(phrase, index)
            if not candidates:
                continue
            has_context = _has_official_context(text, start, end)
            for canonical in candidates:
                if canonical.lower() == phrase_lower:
                    continue
                if not _should_flag(phrase, canonical, has_context):
                    continue
                key = (start, end, phrase_lower)
                if key in seen_found:
                    continue
                seen_found.add(key)
                issues.append(
                    {
                        "found": phrase,
                        "suggested": canonical,
                        "snippet": _extract_snippet(text, start, end),
                    }
                )
                break  # one suggestion per phrase
    return issues


def run_spelling_check(
    articles: List[Dict[str, Any]],
    canonical_names: List[str],
) -> Dict[str, Any]:
    """
    Scan all articles for official name misspellings (conservative).
    Returns report with articles_checked, total_issues, issues (list of issue dicts with article_id, field, snippet, found, suggested).
    """
    n_articles = len(articles)
    n_canonical = len(canonical_names)
    logger.info(f"Spelling check started: {n_articles} articles, {n_canonical} canonical names")
    issues: List[Dict[str, Any]] = []
    for idx, article in enumerate(articles):
        if (idx + 1) % 10 == 0 or idx == 0 or idx == n_articles - 1:
            logger.info(f"Spelling check progress: {idx + 1}/{n_articles} articles scanned so far")
        article_id = article.get("id")
        title = article.get("title") or ""
        content = article.get("content") or ""
        for field, text in [("title", title), ("content", content)]:
            if not text:
                continue
            for item in _find_misspellings_in_text(text, canonical_names):
                issues.append(
                    {
                        "article_id": article_id,
                        "field": field,
                        "snippet": item["snippet"],
                        "found": item["found"],
                        "suggested": item["suggested"],
                    }
                )
    logger.info(f"Spelling check finished: {len(issues)} issues in {n_articles} articles")
    return {
        "articles_checked": len(articles),
        "total_issues": len(issues),
        "issues": issues,
    }
