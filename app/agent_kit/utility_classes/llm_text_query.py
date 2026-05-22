# Standard library imports
import logging
import os
from typing import Any

# Third-party imports
from anthropic import Anthropic
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from xai_sdk import Client
from xai_sdk.chat import system as xai_system
from xai_sdk.chat import user as xai_user

from app.data.enum_classes import (
    DEFAULT_MODEL_FOR_PROVIDER,
    PROVIDER_TO_MODEL_ENUM,
    AnthropicModel,
    GeminiModel,
    TextLLMProvider,
    XaiModel,
)

from .context_manager import ContextManager

logger = logging.getLogger(__name__)


# Union type alias for any model enum value accepted by :class:`LLMTextQuery`.
ModelEnum = GeminiModel | XaiModel | AnthropicModel


class LLMTextQuery:
    """
    Routes a single system/user completion to xAI, Anthropic, or Gemini per
    explicit ``TextLLMProvider``.

    Model selection lives in typed enums (:class:`GeminiModel`,
    :class:`XaiModel`, :class:`AnthropicModel`), not environment variables —
    callers pass ``model=`` to pick a specific model, or omit it to get the
    per-provider default from
    :data:`~app.data.enum_classes.DEFAULT_MODEL_FOR_PROVIDER`. The ``model``
    enum must match the ``provider`` or :class:`ValueError` is raised at
    construction time.

    API keys still come from environment variables: ``XAI_API_KEY``,
    ``ANTHROPIC_API_KEY``, ``GEMINI_API_KEY``.

    Beyond the single-shot :meth:`get_raw_response` interface, this class
    also exposes Gemini-specific cache helpers (:meth:`gemini_create_cache`,
    :meth:`gemini_generate_with_cache`, :meth:`gemini_delete_cache`) used by
    multi-pass extractors that want to upload a long document once and run
    multiple cheap reads against it.
    """

    def __init__(
        self,
        provider: TextLLMProvider,
        model: ModelEnum | None = None,
        context_manager: ContextManager | None = None,
    ):
        self._provider = provider
        self._context_manager = context_manager or ContextManager()

        expected_enum = PROVIDER_TO_MODEL_ENUM[provider]
        if model is None:
            model = DEFAULT_MODEL_FOR_PROVIDER[provider]
        elif not isinstance(model, expected_enum):
            raise ValueError(
                f"Model enum {type(model).__name__}.{model.name} does not match "
                f"provider {provider.value}; expected a {expected_enum.__name__} value."
            )
        self._model: ModelEnum = model

        self._xai_api_key = os.getenv("XAI_API_KEY")
        self._anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self._gemini_api_key = os.getenv("GEMINI_API_KEY")

        self.model_id: str = self._model.value
        logger.info(
            f"LLMTextQuery init provider={provider.value} model={self.model_id} "
            f"xai_key_set={bool(self._xai_api_key)} "
            f"anthropic_key_set={bool(self._anthropic_api_key)} "
            f"gemini_key_set={bool(self._gemini_api_key)}"
        )

    @property
    def provider(self) -> TextLLMProvider:
        return self._provider

    @property
    def model(self) -> ModelEnum:
        return self._model

    def llm_metadata(self) -> dict[str, str]:
        return {"provider": self.provider.value, "model": self.model_id}

    def get_raw_response(self, context: str, message: str) -> str | JSONResponse:
        logger.debug(
            f"get_raw_response provider={self._provider.value} model={self.model_id} "
            f"context_chars={len(context or '')} message_chars={len(message or '')}"
        )
        if self._provider is TextLLMProvider.XAI:
            return self._xai_completion(context, message)
        if self._provider is TextLLMProvider.GEMINI:
            return self._gemini_completion(context, message)
        return self._anthropic_completion(context, message)

    def _xai_completion(self, context: str, message: str) -> str | JSONResponse:
        if not self._xai_api_key:
            logger.warning("xAI completion skipped: XAI_API_KEY not set")
            return JSONResponse(
                status_code=500,
                content={"error": "XAI_API_KEY environment variable is not set"},
            )
        model = self.model_id
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
        model = self.model_id
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

    # ---------------------------------------------------------------------
    # Gemini
    # ---------------------------------------------------------------------

    def _build_gemini_client(self) -> Any | JSONResponse:
        """Return a ``google.genai.Client`` or a 500 :class:`JSONResponse`.

        Imports the SDK lazily so the rest of :class:`LLMTextQuery` keeps
        working when ``google-genai`` is not installed (e.g. in environments
        that only use xAI / Anthropic).
        """
        if not self._gemini_api_key:
            logger.warning("Gemini call skipped: GEMINI_API_KEY not set")
            return JSONResponse(
                status_code=500,
                content={"error": "GEMINI_API_KEY environment variable is not set"},
            )
        try:
            from google import genai  # noqa: WPS433

            return genai.Client(api_key=self._gemini_api_key)
        except Exception as e:  # noqa: BLE001
            logger.exception("Gemini SDK import / client init failed")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to initialize Gemini client: {e!s}"},
            )

    def _gemini_completion(self, context: str, message: str) -> str | JSONResponse:
        """Single-shot Gemini call matching the ``get_raw_response`` contract.

        Used by the non-cached, non-structured legacy interface. Multi-pass
        extractors should use :meth:`gemini_generate_with_cache` instead.
        """
        client_or_err = self._build_gemini_client()
        if isinstance(client_or_err, JSONResponse):
            return client_or_err
        client = client_or_err
        model = self.model_id
        try:
            from google.genai import types  # noqa: WPS433

            logger.debug(f"Gemini generate_content starting model={model}")
            response = client.models.generate_content(
                model=model,
                contents=message,
                config=types.GenerateContentConfig(
                    system_instruction=context or None,
                ),
            )
            text = (getattr(response, "text", None) or "").strip()
            if not text:
                logger.warning("Gemini returned empty completion text")
            else:
                logger.info(f"Gemini completion ok model={model} chars={len(text)}")
            return text
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Gemini completion failed model={model}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get response from Gemini: {e!s}"},
            )

    def gemini_create_cache(
        self,
        transcript: str,
        *,
        ttl_seconds: int = 900,
        display_name: str | None = None,
        system_instruction: str | None = None,
    ) -> str | JSONResponse:
        """Upload ``transcript`` as ``CachedContent``; return the cache name.

        The returned name is opaque (Gemini-assigned, looks like
        ``cachedContents/...``) and is passed to subsequent
        :meth:`gemini_generate_with_cache` calls via the ``cache_name``
        argument. TTL minimum is 60s, maximum is 7 days; default is 900s
        which comfortably covers a 3-pass extraction.

        When ``system_instruction`` is set here, it is baked into the cache
        and must **not** be passed again on :meth:`gemini_generate_with_cache`
        (Gemini returns 400 if generate also sets system_instruction).

        Returns a :class:`JSONResponse` with status 500 on any failure so
        callers can branch on the type without try/except — matching the
        rest of this class.
        """
        client_or_err = self._build_gemini_client()
        if isinstance(client_or_err, JSONResponse):
            return client_or_err
        client = client_or_err
        try:
            from google.genai import types  # noqa: WPS433

            logger.debug(
                f"Gemini caches.create model={self.model_id} ttl={ttl_seconds}s "
                f"transcript_chars={len(transcript or '')} "
                f"system_instruction_chars={len(system_instruction or '')}"
            )
            cache_config: dict[str, Any] = {
                "contents": [
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=transcript or "")],
                    )
                ],
                "display_name": display_name,
                "ttl": f"{ttl_seconds}s",
            }
            if system_instruction:
                cache_config["system_instruction"] = system_instruction
            cached = client.caches.create(
                model=self.model_id,
                config=types.CreateCachedContentConfig(**cache_config),
            )
            cache_name = getattr(cached, "name", None)
            if not cache_name:
                logger.warning("Gemini caches.create returned no .name attribute")
                return JSONResponse(
                    status_code=500,
                    content={"error": "Gemini cache create returned no name"},
                )
            logger.info(f"Gemini cache created name={cache_name} ttl={ttl_seconds}s")
            return cache_name
        except Exception as e:  # noqa: BLE001
            logger.exception("Gemini cache create failed")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to create Gemini cache: {e!s}"},
            )

    @staticmethod
    def _cached_turn_contents(
        system_instruction: str | None, user_message: str
    ) -> str:
        """Build ``contents`` for a cached generate call.

        Gemini rejects ``system_instruction`` on ``GenerateContentConfig`` when
        ``cached_content`` is set — those fields must live on the cache at
        create time, but Gemma runs three passes with *different* system
        prompts against one transcript cache. We fold each pass's system
        prompt into the user turn instead (API-legal; transcript stays cached).
        """
        user = (user_message or "").strip()
        system = (system_instruction or "").strip()
        if system and user:
            return f"{system}\n\n---\n\n{user}"
        return system or user

    def gemini_generate_with_cache(
        self,
        cache_name: str,
        *,
        system_instruction: str | None,
        user_message: str,
        response_schema: type[BaseModel] | None = None,
    ) -> dict | str | JSONResponse:
        """Generate against an existing ``cached_content``.

        Returns:
            - A parsed ``dict`` when ``response_schema`` is given (Gemini's
              ``response.parsed`` Pydantic instance, dumped via
              ``model_dump()``).
            - The raw response text string when no schema is given.
            - A :class:`JSONResponse` with status 500 on any failure.

        ``cached_content`` is a token-prefix lookup of the transcript; it
        does NOT carry conversation memory from previous calls. Each call to
        this method is independent — the only shared state is the cached
        transcript itself.

        ``system_instruction`` is merged into the user ``contents`` string
        (see :meth:`_cached_turn_contents`) because the Gemini API forbids
        ``system_instruction`` on generate when ``cached_content`` is set.
        """
        client_or_err = self._build_gemini_client()
        if isinstance(client_or_err, JSONResponse):
            return client_or_err
        client = client_or_err
        try:
            from google.genai import types  # noqa: WPS433

            # System prompt is on the cache (create time) when callers pass
            # system_instruction=None. Only fold into contents as a fallback.
            turn_contents = (
                self._cached_turn_contents(system_instruction, user_message)
                if system_instruction
                else user_message
            )
            cfg_kwargs: dict[str, Any] = {
                "cached_content": cache_name,
            }
            if response_schema is not None:
                cfg_kwargs["response_mime_type"] = "application/json"
                cfg_kwargs["response_schema"] = response_schema

            logger.debug(
                f"Gemini generate_content cached cache={cache_name} "
                f"schema={response_schema.__name__ if response_schema else None} "
                f"turn_chars={len(turn_contents)}"
            )
            response = client.models.generate_content(
                model=self.model_id,
                contents=turn_contents,
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
            if response_schema is not None:
                parsed = getattr(response, "parsed", None)
                if parsed is None:
                    logger.warning(
                        "Gemini returned no .parsed attribute despite response_schema; "
                        "falling back to raw .text for caller-side parsing"
                    )
                    return (getattr(response, "text", None) or "").strip()
                if isinstance(parsed, BaseModel):
                    return parsed.model_dump()
                if isinstance(parsed, dict):
                    return parsed
                logger.warning(
                    f"Gemini .parsed has unexpected type {type(parsed).__name__}; "
                    "returning model_dump-style dict via __dict__"
                )
                return dict(getattr(parsed, "__dict__", {}))
            return (getattr(response, "text", None) or "").strip()
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Gemini cached generate failed cache={cache_name}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to generate from Gemini cache: {e!s}"},
            )

    def gemini_delete_cache(self, cache_name: str) -> None:
        """Best-effort cache cleanup. Failures are logged at WARN, never raised.

        Called from a ``finally`` block in extractor orchestration code, so
        an unrecoverable error here must not mask the actual extraction
        result.
        """
        if not cache_name:
            return
        client_or_err = self._build_gemini_client()
        if isinstance(client_or_err, JSONResponse):
            logger.warning(
                f"Gemini cache delete skipped (client unavailable) cache={cache_name}"
            )
            return
        client = client_or_err
        try:
            client.caches.delete(name=cache_name)
            logger.info(f"Gemini cache deleted name={cache_name}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Gemini cache delete failed cache={cache_name}: {e}")

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
