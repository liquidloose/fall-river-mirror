"""Deterministic transcript timestamps for factual anchors."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class TranscriptSnippet:
    """One YouTube caption snippet with a whole-second start offset."""

    start_seconds: int
    text: str


def parse_youtube_transcript_snippets(content: str) -> list[TranscriptSnippet]:
    """Parse stored YouTube transcript JSON into ordered snippets."""
    raw = (content or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    snippet_rows: Optional[list[Any]] = None
    if isinstance(data, dict):
        maybe = data.get("snippets")
        if isinstance(maybe, list):
            snippet_rows = maybe
    elif isinstance(data, list):
        snippet_rows = data

    if not snippet_rows:
        return []

    snippets: list[TranscriptSnippet] = []
    for row in snippet_rows:
        if not isinstance(row, dict):
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        start = row.get("start")
        if start is None:
            continue
        try:
            sec = int(float(start))
        except (TypeError, ValueError):
            continue
        if sec < 0:
            sec = 0
        snippets.append(TranscriptSnippet(start_seconds=sec, text=text))
    return snippets


def _significant_tokens(text: str) -> set[str]:
    tokens = {
        token
        for token in _TOKEN_RE.findall((text or "").lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }
    return tokens


def match_anchor_start_seconds(
    anchor: Mapping[str, Any],
    snippets: Sequence[TranscriptSnippet],
    *,
    window_size: int = 4,
    min_overlap_tokens: int = 2,
    min_overlap_ratio: float = 0.12,
) -> Optional[int]:
    """Return the snippet start time that best matches an anchor's wording."""
    headline = (anchor.get("anchor_headline") or "").strip()
    body = (anchor.get("anchor_text") or "").strip()
    query_tokens = _significant_tokens(f"{headline} {body}")
    if not query_tokens or not snippets:
        return None

    best_score = 0.0
    best_start: Optional[int] = None

    for index in range(len(snippets)):
        window_text = " ".join(
            snippet.text for snippet in snippets[index : index + window_size]
        )
        overlap = query_tokens & _significant_tokens(window_text)
        if len(overlap) < min_overlap_tokens:
            continue
        score = len(overlap) / len(query_tokens)
        if score < min_overlap_ratio:
            continue
        start = snippets[index].start_seconds
        if score > best_score or (
            score == best_score
            and best_start is not None
            and start < best_start
        ):
            best_score = score
            best_start = start

    return best_start


def resolve_anchor_timestamp_seconds(
    anchor: Mapping[str, Any],
    transcript: str,
    *,
    parse_clock_timestamp: Callable[[Optional[str]], Optional[int]],
) -> tuple[Optional[int], bool]:
    """Resolve anchor seconds from transcript snippets, with clock-string fallback.

    Returns:
        ``(seconds, matched_from_snippets)`` where ``matched_from_snippets`` is
        ``True`` when the value came from deterministic snippet alignment.
    """
    snippets = parse_youtube_transcript_snippets(transcript)
    if snippets:
        matched = match_anchor_start_seconds(anchor, snippets)
        if matched is not None:
            return matched, True
    parsed = parse_clock_timestamp(anchor.get("timestamp_string"))
    return parsed, False
