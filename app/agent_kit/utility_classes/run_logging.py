"""Per-video run logging + timing/token metrics.

Centralizes where extractor passes and journalist steps drop their debug
logs and their timing/token metrics. Everything for one video lands in a
single folder keyed by the YouTube id::

    logs/<youtube_id>/
      <ts>_extract_<pass>_r<run_id>.json   # full extraction call payloads
      <ts>_article_<step>.json             # full article-creation payloads
      metrics.json                         # merged timing + token breakdown

``metrics.json`` accumulates across pipeline stages (extraction runs at one
point, article writing later) and across reruns. A fresh extraction
``run_id`` replaces the prior extraction section; re-writing an article
replaces the matching article step entry.

Every write here is best-effort: a logging failure is logged at WARNING and
swallowed, because observability must never break the pipeline.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

LOG_ROOT = Path("logs")

# Normalized token fields used everywhere downstream.
_TOKEN_FIELDS = ("prompt", "cached", "output", "total")


def _safe(component: Optional[str], fallback: str = "unknown") -> str:
    """Make a path/filename component filesystem-safe (no separators)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (component or "").strip())
    return cleaned or fallback


def video_log_dir(youtube_id: Optional[str]) -> Path:
    """Return (and create) ``logs/<youtube_id>/`` for this video."""
    path = LOG_ROOT / _safe(youtube_id, "unknown")
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Token-usage normalization
# ---------------------------------------------------------------------------


def empty_usage() -> Dict[str, int]:
    """A zeroed token-usage dict with the canonical fields."""
    return {field: 0 for field in _TOKEN_FIELDS}


def add_usage(
    a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]
) -> Dict[str, int]:
    """Field-wise sum of two usage dicts (missing fields treated as 0)."""
    a = a or {}
    b = b or {}
    return {
        field: int(a.get(field, 0) or 0) + int(b.get(field, 0) or 0)
        for field in _TOKEN_FIELDS
    }


def normalize_gemini_usage(response: Any) -> Optional[Dict[str, int]]:
    """Pull ``usage_metadata`` off a google-genai response into our shape.

    ``cached`` is the slice of prompt tokens served from cached content
    (cheaper, and the bulk of each cached extraction pass). Returns ``None``
    when the response carries no usage metadata.
    """
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return None
    prompt = getattr(meta, "prompt_token_count", None) or 0
    cached = getattr(meta, "cached_content_token_count", None) or 0
    output = getattr(meta, "candidates_token_count", None) or 0
    total = getattr(meta, "total_token_count", None) or 0
    return {
        "prompt": int(prompt),
        "cached": int(cached),
        "output": int(output),
        "total": int(total),
    }


def normalize_xai_usage(response: Any) -> Optional[Dict[str, int]]:
    """Pull token usage off an xAI ``chat.sample()`` response.

    The xAI SDK shape is less stable than google-genai's, so fields are read
    defensively, tolerating OpenAI-compatible aliases. Returns ``None`` when
    no usage object is present.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt = (
        getattr(usage, "prompt_tokens", None)
        or getattr(usage, "input_tokens", None)
        or 0
    )
    output = (
        getattr(usage, "completion_tokens", None)
        or getattr(usage, "output_tokens", None)
        or 0
    )
    total = getattr(usage, "total_tokens", None) or 0
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", None) or 0
    if not total:
        total = int(prompt) + int(output)
    return {
        "prompt": int(prompt),
        "cached": int(cached),
        "output": int(output),
        "total": int(total),
    }


def normalize_anthropic_usage(message: Any) -> Optional[Dict[str, int]]:
    """Pull token usage off an Anthropic ``messages.create`` response."""
    usage = getattr(message, "usage", None)
    if usage is None:
        return None
    prompt = getattr(usage, "input_tokens", None) or 0
    output = getattr(usage, "output_tokens", None) or 0
    cached = getattr(usage, "cache_read_input_tokens", None) or 0
    return {
        "prompt": int(prompt),
        "cached": int(cached),
        "output": int(output),
        "total": int(prompt) + int(output),
    }


# ---------------------------------------------------------------------------
# File + metric writers
# ---------------------------------------------------------------------------


def write_call_log(
    youtube_id: Optional[str],
    kind: str,
    label: str,
    started_at: Optional[str],
    payload: Dict[str, Any],
) -> Optional[Path]:
    """Write a full per-call debug payload into the video folder.

    Filename: ``<safe_started_at>_<kind>_<label>.json`` (``:`` in the ISO
    timestamp replaced with ``-`` for cross-platform safety).
    """
    try:
        directory = video_log_dir(youtube_id)
        ts = started_at or datetime.now(timezone.utc).isoformat()
        safe_ts = ts.replace(":", "-")
        filename = f"{safe_ts}_{_safe(kind, 'call')}_{_safe(label, 'main')}.json"
        path = directory / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        return path
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "write_call_log failed yt=%s kind=%s label=%s: %s",
            youtube_id,
            kind,
            label,
            e,
        )
        return None


def append_metric(
    youtube_id: Optional[str],
    section: str,
    entry: Dict[str, Any],
    *,
    section_meta: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Merge one timing/token ``entry`` into ``logs/<youtube_id>/metrics.json``.

    ``section`` is ``"extraction"`` or ``"article"``. Entries land in
    ``section["passes"]`` (extraction) or ``section["steps"]`` (article), and
    ``section["totals"]`` is recomputed from the list each time.

    Idempotency / rerun behavior:

    - ``section_meta`` (e.g. ``{"run_id": ...}``) is merged onto the section.
      For extraction, a *new* ``run_id`` clears the prior passes so a re-run
      replaces rather than appends.
    - Within a section, an entry with the same label (``pass`` for extraction,
      ``step`` for article) replaces the existing one instead of duplicating.

    Best-effort: returns the metrics path on success, ``None`` on failure.
    """
    list_key = "passes" if section == "extraction" else "steps"
    label_key = "pass" if section == "extraction" else "step"
    try:
        directory = video_log_dir(youtube_id)
        path = directory / "metrics.json"

        data: Dict[str, Any] = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception:  # noqa: BLE001
                data = {}
        if not isinstance(data, dict):
            data = {}

        data.setdefault("youtube_id", _safe(youtube_id, "unknown"))

        sec = data.get(section)
        if not isinstance(sec, dict):
            sec = {}

        # A new extraction run replaces the previous section's passes.
        new_run_id = (section_meta or {}).get("run_id")
        if new_run_id and sec.get("run_id") and sec.get("run_id") != new_run_id:
            sec = {}
        if section_meta:
            sec.update(section_meta)

        items = sec.get(list_key)
        if not isinstance(items, list):
            items = []
        label_val = entry.get(label_key)
        items = [it for it in items if it.get(label_key) != label_val]
        items.append(entry)
        sec[list_key] = items

        total_elapsed = 0.0
        total_tokens = empty_usage()
        for it in items:
            total_elapsed += float(it.get("elapsed_seconds") or 0)
            total_tokens = add_usage(total_tokens, it.get("tokens"))
        sec["totals"] = {
            "elapsed_seconds": round(total_elapsed, 3),
            "tokens": total_tokens,
        }

        data[section] = sec
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return path
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "append_metric failed yt=%s section=%s: %s", youtube_id, section, e
        )
        return None
