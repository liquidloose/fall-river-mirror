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


def format_duration(seconds: Optional[float]) -> str:
    """Render a duration as ``MM:SS`` (or ``HH:MM:SS`` once it reaches an hour)."""
    total = int(round(float(seconds or 0)))
    if total < 0:
        total = 0
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


# Canonical ordering used when rendering the stages map so metrics.json reads
# top-to-bottom in pipeline order regardless of which stage wrote last.
_STAGE_ORDER = (
    "transcript_fetch",
    "extraction",
    "article_writing",
    "bullet_points",
    "image_generation",
    "wordpress_sync",
)


def _load_metrics(path: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:  # noqa: BLE001
            data = {}
    if not isinstance(data, dict):
        data = {}
    return data


def _ordered_stages(stages: Dict[str, Any]) -> Dict[str, Any]:
    ordered: Dict[str, Any] = {}
    for key in _STAGE_ORDER:
        if key in stages:
            ordered[key] = stages[key]
    for key, value in stages.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _recompute_totals(data: Dict[str, Any]) -> None:
    """Recompute ``totals`` from every stage's elapsed time and tokens."""
    stages = data.get("stages") or {}
    total_elapsed = 0.0
    total_tokens = empty_usage()
    for stage in stages.values():
        if not isinstance(stage, dict):
            continue
        total_elapsed += float(stage.get("elapsed_seconds") or 0)
        total_tokens = add_usage(total_tokens, stage.get("tokens"))
    data["totals"] = {
        "duration": format_duration(total_elapsed),
        "elapsed_seconds": round(total_elapsed, 3),
        "tokens": total_tokens,
    }


def _write_metrics(
    youtube_id: Optional[str], mutate
) -> Optional[Path]:
    """Read-modify-write ``logs/<youtube_id>/metrics.json`` under ``mutate``.

    ``mutate(data)`` edits the dict in place; this helper handles load,
    youtube_id seeding, stage ordering, totals recompute, and the write. All
    best-effort: a failure is logged at WARNING and ``None`` is returned.
    """
    try:
        directory = video_log_dir(youtube_id)
        path = directory / "metrics.json"
        data = _load_metrics(path)
        data.setdefault("youtube_id", _safe(youtube_id, "unknown"))
        if not isinstance(data.get("stages"), dict):
            data["stages"] = {}

        mutate(data)

        data["stages"] = _ordered_stages(data["stages"])
        _recompute_totals(data)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return path
    except Exception as e:  # noqa: BLE001
        logger.warning("metrics write failed yt=%s: %s", youtube_id, e)
        return None


def record_stage(
    youtube_id: Optional[str],
    stage_key: str,
    label: str,
    elapsed_seconds: float,
    *,
    model: Optional[str] = None,
    tokens: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Create or replace a single-shot pipeline stage in metrics.json.

    Used for stages that are one timed unit per video (transcript fetch,
    article body, bullet points, image generation, WordPress sync). Re-running
    a stage replaces its prior entry.
    """
    def mutate(data: Dict[str, Any]) -> None:
        stage: Dict[str, Any] = {
            "label": label,
            "duration": format_duration(elapsed_seconds),
            "elapsed_seconds": round(float(elapsed_seconds or 0), 3),
        }
        if model is not None:
            stage["model"] = model
        if tokens is not None:
            stage["tokens"] = tokens
        if extra:
            stage.update(extra)
        data["stages"][stage_key] = stage

    return _write_metrics(youtube_id, mutate)


def record_extraction_pass(
    youtube_id: Optional[str],
    pass_entry: Dict[str, Any],
    *,
    run_id: str,
    model: Optional[str] = None,
    label: str = "Anchor extraction (Gemma Nye, 4-pass)",
) -> Optional[Path]:
    """Append one extractor pass into the ``extraction`` stage.

    Passes accumulate under ``stages.extraction.passes`` and the stage's token
    totals are recomputed from them. A new ``run_id`` clears prior passes so a
    re-extraction replaces rather than appends. The stage-level
    ``elapsed_seconds``/``duration`` (full wall time) is owned by
    :func:`set_stage_duration` and is not overwritten here.
    """
    def mutate(data: Dict[str, Any]) -> None:
        stage = data["stages"].get("extraction")
        if not isinstance(stage, dict):
            stage = {}
        # A new run replaces the previous run's passes.
        if stage.get("run_id") and stage.get("run_id") != run_id:
            stage = {}
        stage["label"] = label
        stage["run_id"] = run_id
        if model is not None:
            stage["model"] = model

        passes = stage.get("passes")
        if not isinstance(passes, list):
            passes = []
        pass_name = pass_entry.get("pass")
        passes = [p for p in passes if p.get("pass") != pass_name]
        passes.append(pass_entry)
        stage["passes"] = passes

        stage_tokens = empty_usage()
        for p in passes:
            stage_tokens = add_usage(stage_tokens, p.get("tokens"))
        stage["tokens"] = stage_tokens
        # Seed an elapsed from the passes until the stage timer sets the real
        # wall time; never shrink an already-set wall time.
        passes_elapsed = round(
            sum(float(p.get("elapsed_seconds") or 0) for p in passes), 3
        )
        if float(stage.get("elapsed_seconds") or 0) < passes_elapsed:
            stage["elapsed_seconds"] = passes_elapsed
            stage["duration"] = format_duration(passes_elapsed)

        data["stages"]["extraction"] = stage

    return _write_metrics(youtube_id, mutate)


def set_stage_duration(
    youtube_id: Optional[str],
    stage_key: str,
    label: str,
    elapsed_seconds: float,
) -> Optional[Path]:
    """Set/override a stage's wall-clock duration without touching its detail.

    Used for the extraction stage so its ``elapsed_seconds`` reflects the full
    four-pass run (including Gemini cache create/delete overhead), while the
    nested per-pass timings stay intact.
    """
    def mutate(data: Dict[str, Any]) -> None:
        stage = data["stages"].get(stage_key)
        if not isinstance(stage, dict):
            stage = {}
        stage["label"] = label
        stage["elapsed_seconds"] = round(float(elapsed_seconds or 0), 3)
        stage["duration"] = format_duration(elapsed_seconds)
        data["stages"][stage_key] = stage

    return _write_metrics(youtube_id, mutate)
