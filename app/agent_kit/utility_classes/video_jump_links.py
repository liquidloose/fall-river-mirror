"""Repair journalist HTML when YouTube links wrap prose instead of bracket timestamps."""

from __future__ import annotations

import re
from typing import List, Tuple

from app.agent_kit.utility_classes.prompt_utilities import (
    VIDEO_JUMP_LINK_CLASS,
    format_bracket_timestamp,
)

_BRACKET_TS_RE = re.compile(r"^\[\d{2}:\d{2}(:\d{2})?\]$")
_YT_A_TAG_RE = re.compile(
    r'<a\b([^>]*?)href="(https?://(?:www\.)?youtube\.com/watch\?[^"]*?&t=(\d+)s)"([^>]*?)>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_PARAGRAPH_RE = re.compile(r"(<p\b[^>]*>)(.*?)(</p>)", re.IGNORECASE | re.DOTALL)


def _bracket_label_from_seconds(seconds: int) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _build_jump_link(href: str, seconds: int) -> str:
    label = _bracket_label_from_seconds(seconds)
    bracket = format_bracket_timestamp(seconds)
    return (
        f'<a class="{VIDEO_JUMP_LINK_CLASS}" href="{href}" '
        f'aria-label="Jump to video at {label}">{bracket}</a>'
    )


def _sentence_has_trailing_bracket_link(sentence: str) -> bool:
    trimmed = sentence.rstrip()
    matches = list(_YT_A_TAG_RE.finditer(trimmed))
    if not matches:
        return False
    last = matches[-1]
    tail = trimmed[last.end() :].strip()
    if tail not in ("", "."):
        return False
    return bool(_BRACKET_TS_RE.match(last.group(5).strip()))


def _repair_sentence(sentence: str) -> str:
    if not _YT_A_TAG_RE.search(sentence):
        return sentence

    removed: List[Tuple[str, int]] = []
    rebuilt: List[str] = []
    last_end = 0

    for match in _YT_A_TAG_RE.finditer(sentence):
        rebuilt.append(sentence[last_end : match.start()])
        inner = match.group(5).strip()
        href = match.group(2)
        seconds = int(match.group(3))
        if _BRACKET_TS_RE.match(inner):
            rebuilt.append(match.group(0))
        else:
            removed.append((href, seconds))
            rebuilt.append(inner)
        last_end = match.end()

    rebuilt.append(sentence[last_end:])
    fixed = "".join(rebuilt)

    if removed and not _sentence_has_trailing_bracket_link(fixed):
        href, seconds = removed[-1]
        link = _build_jump_link(href, seconds)
        trimmed = fixed.rstrip()
        if trimmed.endswith("."):
            fixed = f"{trimmed[:-1].rstrip()} {link}."
        else:
            fixed = f"{trimmed} {link}"

    return fixed


def _repair_paragraph_inner(html: str) -> str:
    chunks = re.split(r"(\.)", html)
    if len(chunks) == 1:
        return _repair_sentence(html)

    out: List[str] = []
    buffer = ""
    for chunk in chunks:
        buffer += chunk
        if chunk == ".":
            out.append(_repair_sentence(buffer))
            buffer = ""
    if buffer:
        out.append(_repair_sentence(buffer))
    return "".join(out)


def repair_video_jump_links(html: str) -> str:
    """Normalize YouTube timestamp links to bracket citations at sentence ends."""
    if not html or "youtube.com/watch" not in html:
        return html

    def repl(match: re.Match[str]) -> str:
        open_tag, inner, close_tag = match.groups()
        return f"{open_tag}{_repair_paragraph_inner(inner)}{close_tag}"

    return _PARAGRAPH_RE.sub(repl, html)
