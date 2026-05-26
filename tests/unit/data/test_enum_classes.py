"""Unit tests for enum-class model resolution helpers."""

import pytest

from app.data.enum_classes import GeminiModel, TextModel, resolve_gemini_text_model


def test_resolve_gemini_text_model_accepts_gemini_enum() -> None:
    """Direct Gemini enum values pass through unchanged."""
    resolved = resolve_gemini_text_model(GeminiModel.GEMINI_2_5_FLASH)
    assert resolved == GeminiModel.GEMINI_2_5_FLASH


def test_resolve_gemini_text_model_accepts_unified_gemini_model() -> None:
    """Unified TextModel values resolve when they belong to Gemini."""
    resolved = resolve_gemini_text_model(TextModel.GEMINI_2_5_FLASH)
    assert resolved == GeminiModel.GEMINI_2_5_FLASH


def test_resolve_gemini_text_model_rejects_non_gemini_model() -> None:
    """Extractor-specific helper rejects non-Gemini provider values."""
    with pytest.raises(ValueError):
        resolve_gemini_text_model(TextModel.CLAUDE_HAIKU_4_5)
