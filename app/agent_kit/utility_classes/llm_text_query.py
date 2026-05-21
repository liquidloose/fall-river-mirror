# Standard library imports
import logging
import os
from typing import Any

# Third-party imports
from anthropic import Anthropic
from fastapi.responses import JSONResponse
from xai_sdk import Client
from xai_sdk.chat import system as xai_system
from xai_sdk.chat import user as xai_user

from app.data.enum_classes import TextLLMProvider

from .context_manager import ContextManager

logger = logging.getLogger(__name__)


class LLMTextQuery:
    """
    Routes a single system/user completion to xAI or Anthropic per explicit
    ``TextLLMProvider``. API keys come from ``XAI_API_KEY`` /
    ``ANTHROPIC_API_KEY`` respectively. For xAI completions, set ``XAI_MODEL`` to
    the chat model id (no default in code). Override the Anthropic model with
    ``ANTHROPIC_MODEL`` when needed.
    """

    def __init__(
        self,
        provider: TextLLMProvider,
        context_manager: ContextManager | None = None,
    ):
        self._provider = provider
        self._context_manager = context_manager or ContextManager()
        self._xai_api_key = os.getenv("XAI_API_KEY")
        self._xai_model = (os.getenv("XAI_MODEL") or "").strip()
        self._anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self._anthropic_model = (
            os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022") or ""
        ).strip()
        self._gemini_api_key = os.getenv("GEMINI_API_KEY")
        self._gemini_model = (os.getenv("GEMINI_MODEL") or "").strip()
        self.model_id: str = {
            TextLLMProvider.XAI: self._xai_model,
            TextLLMProvider.GEMINI: self._gemini_model,
            TextLLMProvider.ANTHROPIC: self._anthropic_model,
        }[provider]
        logger.info(
            f"LLMTextQuery init provider={provider.value} xai_key_set={bool(self._xai_api_key)} "
            f"xai_model={self._xai_model or '(unset)'} anthropic_key_set={bool(self._anthropic_api_key)} "
            f"anthropic_model={self._anthropic_model or '(default)'} "
            f"gemini_key_set={bool(self._gemini_api_key)} gemini_model={self._gemini_model or '(unset)'}"
        )

    @property
    def provider(self) -> TextLLMProvider:
        return self._provider

    def llm_metadata(self) -> dict[str, str]:
        return {"provider": self.provider.value, "model": self.model_id}

    def get_raw_response(self, context: str, message: str) -> str | JSONResponse:
        logger.debug(
            f"get_raw_response provider={self._provider.value} context_chars={len(context or '')} "
            f"message_chars={len(message or '')}"
        )
        if self._provider is TextLLMProvider.XAI:
            return self._xai_completion(context, message)
        if self._provider is TextLLMProvider.GEMINI:
            logger.warning(
                "Gemini provider selected but the integration is not yet implemented"
            )
            return JSONResponse(
                status_code=501,
                content={
                    "error": (
                        "Gemini provider is selected but not yet implemented in LLMTextQuery. "
                        "Wire up _gemini_completion before calling extractors/agents configured with TextLLMProvider.GEMINI."
                    )
                },
            )
        return self._anthropic_completion(context, message)

    def _xai_completion(self, context: str, message: str) -> str | JSONResponse:
        if not self._xai_api_key:
            logger.warning("xAI completion skipped: XAI_API_KEY not set")
            return JSONResponse(
                status_code=500,
                content={"error": "XAI_API_KEY environment variable is not set"},
            )
        if not self._xai_model:
            logger.warning("xAI completion skipped: XAI_MODEL not set")
            return JSONResponse(
                status_code=500,
                content={"error": "XAI_MODEL environment variable is not set"},
            )
        model = self._xai_model
        try:
            logger.debug(f"xAI chat.sample starting model={model}")
            client = Client(api_key=self._xai_api_key, timeout=3600)
            chat = client.chat.create(model=model)
            chat.append(xai_system(context))
            chat.append(xai_user(message))
            response = chat.sample()
            text = response.content or ""
            if not (text.strip()):
                logger.warning("xAI returned empty completion text")
            else:
                logger.info(f"xAI completion ok model={model} chars={len(text)}")
            return text
        except Exception as e:  # noqa: BLE001
            logger.exception(f"xAI completion failed model={model}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get response from xAI: {e!s}"},
            )

    @staticmethod
    def _anthropic_concat_text(message: object) -> str:
        """Join Anthropic ``messages.create`` reply content blocks into one string.

        The API returns ``content`` as a list of typed blocks (e.g. ``TextBlock`` with
        ``type='text'`` and ``text=...``), not a single completion string—unlike Grok/xAI where
        the SDK gives one text body. Handles both SDK objects and dict-shaped blocks.
        """

        parts: list[str] = []
        for block in getattr(message, "content", ()) or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                parts.append(getattr(block, "text", "") or "")
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        flattened = "".join(parts).strip()
        return flattened

    def _anthropic_completion(self, context: str, message: str) -> str | JSONResponse:
        if not self._anthropic_api_key:
            logger.warning("Anthropic completion skipped: ANTHROPIC_API_KEY not set")
            return JSONResponse(
                status_code=500,
                content={"error": "ANTHROPIC_API_KEY environment variable is not set"},
            )
        model = self._anthropic_model or "claude-3-5-sonnet-20241022"
        try:
            logger.debug(f"Anthropic messages.create starting model={model}")
            client = Anthropic(api_key=self._anthropic_api_key)
            msg = client.messages.create(
                model=model,
                max_tokens=8192,
                system=context,
                messages=[{"role": "user", "content": message}],
            )
            out = self._anthropic_concat_text(msg)
            if not out:
                logger.warning(
                    "Anthropic returned empty text after concatenating content blocks"
                )
            else:
                logger.info(f"Anthropic completion ok model={model} chars={len(out)}")
            return out
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Anthropic completion failed model={model}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get response from Anthropic: {e!s}"},
            )

    def _complete_headline(self, article_body: str) -> str | JSONResponse:
        system = self._context_manager.read_context_file(
            "headline", "headline.md", role="journalists"
        )
        return self.get_raw_response(system, f"Article content:\n\n{article_body}")

    def get_response(
        self,
        context: str | None = None,
        message: str | None = None,
        committee: str | None = None,
        article_type: Any = None,
        tone: Any = None,
    ) -> dict[str, Any] | JSONResponse:
        body_out = self.get_raw_response(context or "", message or "")
        if isinstance(body_out, JSONResponse):
            return body_out
        body = (body_out or "").strip()
        if not body:
            return JSONResponse(
                status_code=500,
                content={
                    "error": (
                        "LLM returned empty article body (main completion had no text). "
                        "Retry the request; if it persists, check model limits or transcript size."
                    ),
                },
            )
        headline_out = self._complete_headline(body)
        if isinstance(headline_out, JSONResponse):
            return headline_out
        title = (headline_out or "").strip()
        committee_val = committee if committee is not None else ""
        return {
            "title": title,
            "article_type": article_type,
            "tone": tone,
            "committee": committee_val,
            "context": context,
            "prompt": message,
            "response": body,
            "content": body,
        }
