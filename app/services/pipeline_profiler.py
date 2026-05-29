"""Pipeline run profiler.

A small, stateful helper that times a single ``POST /pipeline/run`` invocation:

- **Startup latency** — from request received until the first stage begins.
- **Per-stage timings** — start/end/duration/status for each pipeline step.
- **Total run duration** — request received until the run finishes.

On :meth:`PipelineProfiler.finish` the profiler appends one JSONL row per run
to a log file (mirroring the WordPress ``frm-hook-profiler`` pattern) and
returns a summary dict for inclusion in the pipeline's JSON response. The file
write is best-effort: permission/IO errors are swallowed so profiling never
breaks a pipeline run, but the timing summary is always returned.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = "logs/app/pipeline-profile.log"


def _profiler_enabled() -> bool:
    """Return whether profiling is enabled (env ``PIPELINE_PROFILER_ENABLED``)."""
    return os.environ.get("PIPELINE_PROFILER_ENABLED", "true").strip().lower() not in (
        "false",
        "0",
        "no",
        "off",
    )


def _profiler_log_path() -> str:
    """Resolve the JSONL destination for profiler rows.

    Honors ``PIPELINE_PROFILER_LOG_PATH``; otherwise writes alongside the app
    log (``APP_LOG_PATH``'s directory), falling back to ``logs/app``.
    """
    explicit = os.environ.get("PIPELINE_PROFILER_LOG_PATH")
    if explicit:
        return explicit
    app_log_path = os.environ.get("APP_LOG_PATH")
    if app_log_path:
        log_dir = os.path.dirname(app_log_path)
        if log_dir:
            return os.path.join(log_dir, "pipeline-profile.log")
    return _DEFAULT_LOG_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineProfiler:
    """Times one pipeline run and writes a JSONL summary row on finish."""

    def __init__(
        self,
        pipeline_run_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.pipeline_run_id = pipeline_run_id
        self.params = params or {}
        self.requested_at: Optional[str] = None
        self.first_stage_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.startup_latency_ms: Optional[int] = None
        self.total_duration_ms: Optional[int] = None
        self.success: Optional[bool] = None
        self.stages: Dict[str, Dict[str, Any]] = {}
        self._received_perf: Optional[float] = None
        self._stage_perf: Dict[str, float] = {}

    def mark_received(self) -> None:
        """Capture the moment the request was accepted (timing baseline)."""
        self._received_perf = time.perf_counter()
        self.requested_at = _now_iso()

    def mark_ready(self) -> None:
        """Mark the point just before the first stage begins.

        Computes startup latency relative to :meth:`mark_received`. A no-op if
        already called (the first stage that runs wins).
        """
        if self.first_stage_at is not None:
            return
        self.first_stage_at = _now_iso()
        if self._received_perf is not None:
            self.startup_latency_ms = int(
                (time.perf_counter() - self._received_perf) * 1000
            )

    def begin_stage(self, name: str) -> None:
        """Record the start of a pipeline stage."""
        self._stage_perf[name] = time.perf_counter()
        self.stages[name] = {
            "started_at": _now_iso(),
            "ended_at": None,
            "duration_ms": None,
            "status": "running",
        }

    def end_stage(self, name: str, status: str) -> None:
        """Record the end + duration + status of a previously begun stage."""
        stage = self.stages.get(name)
        if stage is None:
            # Defensive: end without begin should not happen, but never raise.
            self.stages[name] = {
                "started_at": None,
                "ended_at": _now_iso(),
                "duration_ms": None,
                "status": status,
            }
            return
        stage["ended_at"] = _now_iso()
        stage["status"] = status
        started_perf = self._stage_perf.get(name)
        if started_perf is not None:
            stage["duration_ms"] = int((time.perf_counter() - started_perf) * 1000)

    def finish(self, success: bool) -> Dict[str, Any]:
        """Finalize timings, append a JSONL row if enabled, return the summary."""
        self.success = success
        self.completed_at = _now_iso()
        if self._received_perf is not None:
            self.total_duration_ms = int(
                (time.perf_counter() - self._received_perf) * 1000
            )

        row = {
            "event": "pipeline_run",
            "pipeline_run_id": self.pipeline_run_id,
            "requested_at": self.requested_at,
            "first_stage_at": self.first_stage_at,
            "completed_at": self.completed_at,
            "startup_latency_ms": self.startup_latency_ms,
            "total_duration_ms": self.total_duration_ms,
            "success": self.success,
            "params": self.params,
            "stages": self.stages,
        }

        if _profiler_enabled():
            self._write_row(row)

        return {
            "pipeline_run_id": self.pipeline_run_id,
            "startup_latency_ms": self.startup_latency_ms,
            "total_duration_ms": self.total_duration_ms,
            "stages": self.stages,
        }

    @staticmethod
    def _write_row(row: Dict[str, Any]) -> None:
        """Append one JSON line to the profiler log (best-effort)."""
        path = _profiler_log_path()
        try:
            log_dir = os.path.dirname(path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        except (OSError, PermissionError) as e:
            logger.warning("PipelineProfiler: could not write profile row: %s", e)
