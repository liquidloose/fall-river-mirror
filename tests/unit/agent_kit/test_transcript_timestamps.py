"""Tests for deterministic transcript timestamp alignment."""

import json

from app.agent_kit.utility_classes.transcript_timestamps import (
    match_anchor_start_seconds,
    parse_youtube_transcript_snippets,
    resolve_anchor_timestamp_seconds,
)


def _sample_transcript() -> str:
    snippets = [
        {"text": "Clerk calling roll. Bailey present, Das present.", "start": 2.1},
        {"text": "Recognition awards for Nadia Kazamel and Reagan Melo.", "start": 56.0},
        {"text": "No citizens input scheduled for tonight.", "start": 1149.5},
        {
            "text": "Facilities subcommittee report on October thirtieth meeting.",
            "start": 1154.0,
        },
    ]
    return json.dumps({"snippets": snippets})


def test_parse_youtube_transcript_snippets():
    parsed = parse_youtube_transcript_snippets(_sample_transcript())
    assert [snippet.start_seconds for snippet in parsed] == [2, 56, 1149, 1154]


def test_match_anchor_start_seconds_finds_roll_call():
    snippets = parse_youtube_transcript_snippets(_sample_transcript())
    anchor = {
        "anchor_headline": "Committee conducts opening attendance roll call.",
        "anchor_text": "The clerk called the attendance roll. Bailey and Das were present.",
    }
    assert match_anchor_start_seconds(anchor, snippets) == 2


def test_match_anchor_start_seconds_finds_recognition_awards():
    snippets = parse_youtube_transcript_snippets(_sample_transcript())
    anchor = {
        "anchor_headline": "School Committee recognizes outstanding students.",
        "anchor_text": "Recognition awards went to Nadia Kazamel and Reagan Melo.",
    }
    assert match_anchor_start_seconds(anchor, snippets) == 56


def test_resolve_prefers_snippet_match_over_bad_model_timestamp():
    anchor = {
        "timestamp_string": "1912:88",
        "anchor_headline": "No public comment presented.",
        "anchor_text": "There was no citizens input scheduled for the meeting.",
    }

    def parse_clock(_: str | None) -> int | None:
        return 99999

    seconds, from_snippets = resolve_anchor_timestamp_seconds(
        anchor,
        _sample_transcript(),
        parse_clock_timestamp=parse_clock,
    )
    assert from_snippets is True
    assert seconds == 1149


def test_resolve_falls_back_to_clock_parse_for_plain_text():
    anchor = {"timestamp_string": "01:36", "anchor_text": "Plain transcript only."}

    def parse_clock(ts: str | None) -> int | None:
        assert ts == "01:36"
        return 96

    seconds, from_snippets = resolve_anchor_timestamp_seconds(
        anchor,
        "This is a whisper transcript without json markers.",
        parse_clock_timestamp=parse_clock,
    )
    assert from_snippets is False
    assert seconds == 96
