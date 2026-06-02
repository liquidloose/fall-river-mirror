"""Tests for GemmaNye timestamp parsing and normalization."""

from app.agent_kit.agents.extractors.gemma_nye import GemmaNye


def test_parse_timestamp_to_seconds_decimal_truncates():
    assert GemmaNye.parse_timestamp_to_seconds("12.96") == 12
    assert GemmaNye.parse_timestamp_to_seconds("0.0") == 0
    assert GemmaNye.parse_timestamp_to_seconds("108.92") == 108


def test_parse_timestamp_to_seconds_colon_formats():
    assert GemmaNye.parse_timestamp_to_seconds("2:45") == 165
    assert GemmaNye.parse_timestamp_to_seconds("02:45") == 165
    assert GemmaNye.parse_timestamp_to_seconds("1:08:44") == 4124


def test_parse_timestamp_to_seconds_plain_integers():
    assert GemmaNye.parse_timestamp_to_seconds("165") == 165
    assert GemmaNye.parse_timestamp_to_seconds("165s") == 165


def test_parse_timestamp_to_seconds_invalid():
    assert GemmaNye.parse_timestamp_to_seconds("") is None
    assert GemmaNye.parse_timestamp_to_seconds(None) is None
    assert GemmaNye.parse_timestamp_to_seconds("not-a-time") is None


def test_format_timestamp_colon():
    assert GemmaNye.format_timestamp_colon(12) == "00:12"
    assert GemmaNye.format_timestamp_colon(165) == "02:45"
    assert GemmaNye.format_timestamp_colon(4124) == "1:08:44"


def test_format_timestamp_bracket():
    assert GemmaNye.format_timestamp_bracket(12) == "[00:12]"
    assert GemmaNye.format_timestamp_bracket(165) == "[02:45]"


def test_stitch_anchor_normalizes_decimal_timestamp():
    extractor = GemmaNye()
    raw = {
        "timestamp_string": "12.96",
        "anchor_headline": "Board calls for public input.",
        "anchor_text": "No public comments.",
    }
    stitched = extractor._stitch_anchor(raw, "2026-05-11", "License Board")
    assert stitched["timestamp_seconds"] == 12
    assert stitched["timestamp_string"] == "00:12"
    assert "text_to_embed" in stitched
