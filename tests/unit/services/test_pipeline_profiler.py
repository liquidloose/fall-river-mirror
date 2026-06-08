"""Unit tests for the pipeline run profiler timing and JSONL output."""

import json

from app.services.pipeline_profiler import PipelineProfiler


def test_startup_latency_measured_between_received_and_ready() -> None:
    """mark_ready computes startup latency relative to mark_received."""
    profiler = PipelineProfiler(pipeline_run_id="run-1")
    profiler.mark_received()
    profiler.mark_ready()

    assert profiler.startup_latency_ms is not None
    assert profiler.startup_latency_ms >= 0
    assert profiler.first_stage_at is not None


def test_mark_ready_is_idempotent() -> None:
    """Only the first mark_ready call sets the first-stage timestamp."""
    profiler = PipelineProfiler(pipeline_run_id="run-1")
    profiler.mark_received()
    profiler.mark_ready()
    first = profiler.first_stage_at
    profiler.mark_ready()

    assert profiler.first_stage_at == first


def test_stage_timings_and_status_recorded() -> None:
    """begin_stage/end_stage record duration and the provided status."""
    profiler = PipelineProfiler(pipeline_run_id="run-1")
    profiler.mark_received()
    profiler.mark_ready()
    profiler.begin_stage("transcript_fetch")
    profiler.end_stage("transcript_fetch", "success")

    stage = profiler.stages["transcript_fetch"]
    assert stage["status"] == "success"
    assert stage["duration_ms"] is not None
    assert stage["duration_ms"] >= 0
    assert stage["started_at"] is not None
    assert stage["ended_at"] is not None


def test_finish_returns_expected_summary_keys() -> None:
    """finish returns the response-facing summary with total duration."""
    profiler = PipelineProfiler(
        pipeline_run_id="run-1",
        params={"amount": 2, "queue_mode": "Use Whisper"},
    )
    profiler.mark_received()
    profiler.mark_ready()
    profiler.begin_stage("queue_build")
    profiler.end_stage("queue_build", "skipped")

    summary = profiler.finish(success=True)

    assert summary["pipeline_run_id"] == "run-1"
    assert summary["startup_latency_ms"] is not None
    assert summary["total_duration_ms"] is not None
    assert "queue_build" in summary["stages"]


def test_finish_writes_one_jsonl_row(tmp_path, monkeypatch) -> None:
    """When enabled, finish appends exactly one JSON line to the log path."""
    log_path = tmp_path / "pipeline-profile.log"
    monkeypatch.setenv("PIPELINE_PROFILER_ENABLED", "true")
    monkeypatch.setenv("PIPELINE_PROFILER_LOG_PATH", str(log_path))

    profiler = PipelineProfiler(pipeline_run_id="run-jsonl")
    profiler.mark_received()
    profiler.mark_ready()
    profiler.begin_stage("transcript_fetch")
    profiler.end_stage("transcript_fetch", "success")
    profiler.finish(success=True)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event"] == "pipeline_run"
    assert row["pipeline_run_id"] == "run-jsonl"
    assert row["success"] is True
    assert row["stages"]["transcript_fetch"]["status"] == "success"


def test_disabled_profiler_skips_file_write_but_returns_summary(
    tmp_path, monkeypatch
) -> None:
    """A disabled profiler writes no file yet still returns the summary."""
    log_path = tmp_path / "pipeline-profile.log"
    monkeypatch.setenv("PIPELINE_PROFILER_ENABLED", "false")
    monkeypatch.setenv("PIPELINE_PROFILER_LOG_PATH", str(log_path))

    profiler = PipelineProfiler(pipeline_run_id="run-off")
    profiler.mark_received()
    profiler.mark_ready()
    summary = profiler.finish(success=True)

    assert not log_path.exists()
    assert summary["pipeline_run_id"] == "run-off"
    assert summary["total_duration_ms"] is not None
