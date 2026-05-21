"""
Base class for AI journalist personalities.

This module defines :class:`BaseJournalist`, the shared scaffolding that every
journalist subclass (e.g. ``FRJ1``, ``AureliusStone``) inherits from. It layers
article-generation behavior on top of :class:`~app.agent_kit.agents.base_creator.BaseCreator`:

- **Identity** — fixed traits (``FIRST_NAME``, ``LAST_NAME``, ``SLANT``,
  ``STYLE``) come from ``BaseCreator``; journalists add ``DEFAULT_TONE`` and
  ``DEFAULT_ARTICLE_TYPE``, both of which can be overridden per-instance via
  the constructor.
- **Context loading** — :meth:`BaseJournalist.load_context` reads markdown
  snippets for the journalist's tone, article type, slant, and writing style
  from ``agent_kit/agents/journalists/context_files/`` (via the inherited
  ``_load_attribute_context`` and ``CONTEXT_FILES_ROLE = "journalists"``).
- **Prompt assembly** — :meth:`BaseJournalist.get_system_prompt` stitches the
  loaded context, the journalist's persona, the subclass-specific
  :meth:`BaseJournalist.get_guidelines`, and a fixed block of HTML format
  requirements into the system prompt sent to the LLM.
- **LLM calls** — :meth:`BaseJournalist.generate_article` and
  :meth:`BaseJournalist.generate_bullet_points` invoke
  :class:`~app.agent_kit.utility_classes.llm_text_query.LLMTextQuery` against
  xAI/Grok (``TextLLMProvider.XAI``) and normalize the response.

Error handling:

- ``generate_article`` raises :class:`ArticleGenerationError` for empty bodies
  or explicit API errors (``JSONResponse`` returned by the LLM helper).
- ``generate_bullet_points`` does **not** raise; it returns
  ``{"bullet_points": ..., "error": ...}`` so callers can render partial
  failures inline.
"""
import json
import logging
from typing import Dict, Any, Optional

from fastapi.responses import JSONResponse

from ....data.enum_classes import Tone, ArticleType, TextLLMProvider
from ..base_creator import BaseCreator
from app.agent_kit.utility_classes.llm_text_query import LLMTextQuery

logger = logging.getLogger(__name__)


class ArticleGenerationError(RuntimeError):
    """
    Raised by :meth:`BaseJournalist.generate_article` when the LLM call cannot
    produce a usable article body.

    Triggered when:

    - The xAI/Grok response has an empty ``response`` field (see
      :meth:`BaseJournalist._format_response`).
    - The LLM helper returns a :class:`fastapi.responses.JSONResponse`, which
      indicates an explicit API error rather than a successful completion.
    - Any other exception bubbles up from the LLM call; it is wrapped in this
      type with ``__cause__`` set to the original.

    :meth:`BaseJournalist.generate_bullet_points` does **not** raise this — it
    returns an ``{"bullet_points": None, "error": ...}`` payload instead.
    """


class BaseJournalist(BaseCreator):
    """
    Base class for AI journalists.

    Adds article-specific functionality on top of
    :class:`~app.agent_kit.agents.base_creator.BaseCreator`. Subclasses
    customize behavior by setting class-level identity traits and, optionally,
    overriding :meth:`get_guidelines`.

    Required class attributes (must be set by subclasses):

    - ``FIRST_NAME``, ``LAST_NAME``, ``FULL_NAME``, ``NAME`` — inherited from
      ``BaseCreator``; drive bio/description filename resolution.
    - ``SLANT`` (e.g. ``"libertarian"``) and ``STYLE`` (e.g. ``"journalistic"``)
      — inherited from ``BaseCreator``; map to ``slant/{value}.md`` and
      ``style/writing/{value}.md`` under ``context_files/``.
    - ``DEFAULT_TONE`` (:class:`~app.data.enum_classes.Tone`) and
      ``DEFAULT_ARTICLE_TYPE`` (:class:`~app.data.enum_classes.ArticleType`)
      — used when no per-instance overrides are passed to ``__init__``.

    Optional overrides:

    - :meth:`get_guidelines` — return a free-form string of bullet rules that
      will be inlined into the system prompt under a ``Guidelines:`` header.

    Context lookup root is fixed to
    ``agent_kit/agents/journalists/context_files/`` via
    ``CONTEXT_FILES_ROLE = "journalists"`` (consumed by
    ``BaseCreator._context_search_bases``).
    """

    CONTEXT_FILES_ROLE = "journalists"

    # Journalist-specific traits (must be defined by subclasses)
    DEFAULT_TONE: Tone
    DEFAULT_ARTICLE_TYPE: ArticleType

    def __init__(
        self, tone: Optional[Tone] = None, article_type: Optional[ArticleType] = None
    ):
        """
        Construct a journalist instance, optionally overriding tone/article type.

        Note that :class:`BaseCreator` enforces a singleton-per-subclass via
        ``__new__``, so a second ``FRJ1()`` call returns the existing instance
        — but ``__init__`` still runs and rewrites ``self.tone`` /
        ``self.article_type``. Pass arguments deliberately, or expect later
        constructions to clobber earlier per-instance overrides.

        Args:
            tone: Per-instance tone override. Defaults to ``self.DEFAULT_TONE``
                when ``None``.
            article_type: Per-instance article type override. Defaults to
                ``self.DEFAULT_ARTICLE_TYPE`` when ``None``.
        """
        self.tone = tone if tone is not None else self.DEFAULT_TONE
        self.article_type = (
            article_type if article_type is not None else self.DEFAULT_ARTICLE_TYPE
        )

    def get_personality(self) -> Dict[str, Any]:
        """
        Return the journalist's full personality dict for prompt assembly.

        Merges the base creator personality (``name``, ``slant``, ``style``)
        with the **per-instance** tone and article type (i.e. honoring any
        overrides passed to ``__init__``, not the class defaults).

        Returns:
            Dict with keys ``name``, ``slant``, ``style``, ``tone``,
            ``article_type``. All values are strings (enums are unwrapped via
            ``.value``).
        """
        base = self.get_base_personality()
        return {
            **base,
            "tone": self.tone.value,
            "article_type": self.article_type.value,
        }

    def get_full_profile(self) -> Dict[str, Any]:
        """
        Return a serializable profile of this journalist for API/UI consumers.

        Unlike :meth:`get_personality`, this method reports the **class-level
        defaults** for tone and article type (not per-instance overrides) and
        loads bio/description markdown from ``context_files/bios/`` and
        ``context_files/descriptions/`` via the inherited ``get_bio`` and
        ``get_description`` helpers.

        Returns:
            Dict with keys ``name``, ``first_name``, ``last_name``, ``bio``,
            ``description``, ``tone``, ``article_type``, ``slant``, ``style``.
        """
        return {
            "name": self.FULL_NAME,
            "first_name": self.FIRST_NAME,
            "last_name": self.LAST_NAME,
            "bio": self.get_bio(),
            "description": self.get_description(),
            "tone": self.DEFAULT_TONE.value,
            "article_type": self.DEFAULT_ARTICLE_TYPE.value,
            "slant": self.SLANT,
            "style": self.STYLE,
        }

    def load_context(
        self,
        base_path: Optional[str] = None,
        tone: Optional[Tone] = None,
        article_type: Optional[ArticleType] = None,
    ) -> str:
        """
        Load and concatenate the four markdown context blocks for a journalist.

        Pulls one file per dimension from ``context_files/``:

        - ``tone/{tone.value}.md``
        - ``article_types/{article_type.value}.md``
        - ``slant/{SLANT}.md``
        - ``style/writing/{STYLE}.md``

        Each block is prefixed with a labeled header (e.g.
        ``"Tone Context (analytical):\\n..."``) and the four blocks are joined
        with blank lines. Missing files do not raise; the underlying
        ``_load_attribute_context`` returns a placeholder string instead.

        Args:
            base_path: If provided, overrides the default
                ``agent_kit/agents/journalists/context_files`` root and reads
                from ``{base_path}/{attribute_type}/{value}.md``. Legacy
                escape hatch — leave as ``None`` for normal use.
            tone: Tone override for this call only. Falls back to
                ``self.tone`` (the per-instance value, possibly an
                ``__init__`` override of ``DEFAULT_TONE``).
            article_type: Article-type override for this call only. Falls
                back to ``self.article_type``.

        Returns:
            A single string suitable for prepending to the system prompt.
        """
        selected_tone = tone if tone is not None else self.tone
        selected_article_type = (
            article_type if article_type is not None else self.article_type
        )

        tone_content = self._load_attribute_context(
            "tone", selected_tone.value, base_path=base_path
        )
        article_type_content = self._load_attribute_context(
            "article_types", selected_article_type.value, base_path=base_path
        )
        slant_content = self._load_attribute_context(
            "slant", self.SLANT, base_path=base_path
        )
        style_content = self._load_attribute_context(
            "style/writing", self.STYLE, base_path=base_path
        )

        return (
            f"Tone Context ({selected_tone.value}):\n{tone_content}\n\n"
            f"Article Type Context ({selected_article_type.value}):\n{article_type_content}\n\n"
            f"Slant Context ({self.SLANT}):\n{slant_content}\n\n"
            f"Style Context ({self.STYLE}):\n{style_content}"
        )

    def get_guidelines(self) -> str:
        """
        Return journalist-specific guidelines for article generation.

        The returned string is injected verbatim into the system prompt under a
        ``Guidelines:`` header by :meth:`get_system_prompt`. Subclasses
        typically return a newline-joined bullet list (each line starting with
        ``"- "``); see ``FRJ1.get_guidelines`` and
        ``AureliusStone.get_guidelines`` for examples.

        Returns:
            Guidelines text, or an empty string when the subclass does not
            override this method.
        """
        return ""

    def get_system_prompt(self, context: str) -> str:
        """
        Assemble the full system prompt for an article-generation LLM call.

        Layout of the returned string (newline-joined):

        1. The provided ``context`` (typically the output of
           :meth:`load_context`, plus any transcript or upstream context).
        2. A persona sentence ("You are <name>, a <slant> journalist...").
        3. The article specification (tone, article type, style, slant).
        4. The subclass's :meth:`get_guidelines` text under ``Guidelines:``.
        5. A fixed ``FORMAT REQUIREMENTS:`` block restricting the model to
           body-only HTML (no ``<h1>``, no document-level tags, no markdown).

        The format block exists because the title is generated separately and
        the rendered output is wrapped in a semantic ``<article>`` tag by
        :meth:`_format_response`.

        Args:
            context: Caller-supplied context to prepend, usually built from
                :meth:`load_context` and a meeting transcript.

        Returns:
            The fully assembled system-prompt string.
        """
        personality = self.get_personality()
        guidelines = self.get_guidelines()

        prompt_parts = [
            context,
            "",
            f"You are {personality['name']}, a {personality['slant']} journalist with a {personality['style']} writing style.",
            "",
            "Write an article with the following characteristics:",
            "- Subject: The transcript content provided above",
            f"- Tone: {personality['tone']}",
            f"- Article Type: {personality['article_type']}",
            f"- Style: {personality['style']}",
            f"- Political Slant: {personality['slant']}",
            "",
            "Guidelines:",
            guidelines,
            "",
            "FORMAT REQUIREMENTS:",
            "- Do NOT include a title - just the article body content",
            "- Do NOT use <h1> tags - the title is handled separately",
            "- Use HTML paragraph tags (<p>...</p>) for paragraphs",
            "- You may use <h2>, <h3> for section headers within the article body",
            "- You may use <strong>, <em>, <blockquote>, <ul>, <li> for formatting",
            "- Do NOT include document-level HTML: no <!DOCTYPE>, <html>, <head>, <body>, <meta>, <title>, <style>, <script>",
            "- Do NOT wrap the article in <article> or <div> tags - just the content",
            "- Do NOT include markdown formatting - use HTML only",
        ]

        return "\n".join(prompt_parts)

    def _format_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a successful LLM payload into the publishable article shape.

        The model is expected to return ``{"response": <body>, "title": <str>}``.
        The body is wrapped in ``<article role="article">…</article>`` so the
        rendered output is WCAG-friendly and screen readers announce it as a
        semantic article landmark.

        Args:
            response: Decoded dict from :meth:`LLMTextQuery.get_response`. Only
                ``response`` and ``title`` are read; other keys are ignored.

        Returns:
            ``{"title": str, "content": str}`` where ``content`` is the
            article body wrapped in a semantic ``<article>`` tag.

        Raises:
            ArticleGenerationError: If ``response["response"]`` is missing,
                empty, or whitespace-only.
        """
        article_text = response.get("response", "")
        if not (article_text or "").strip():
            raise ArticleGenerationError(
                "Article body is empty after xAI response formatting"
            )
        title = response.get("title", "Untitled Article")

        # Wrap in semantic <article> tag for accessibility
        article_content = f'<article role="article">\n{article_text}\n</article>'

        return {"title": title, "content": article_content}

    def generate_article(self, context: str, user_content: str) -> Dict[str, Any]:
        """
        Generate an article body using the xAI/Grok API.

        Builds the system prompt via :meth:`get_system_prompt`, optionally
        appends ``user_content`` as an "Additional context:" user message,
        and dispatches the call through
        :class:`~app.agent_kit.utility_classes.llm_text_query.LLMTextQuery`
        with ``provider=TextLLMProvider.XAI``.

        If the LLM helper returns a :class:`fastapi.responses.JSONResponse`,
        that signals an explicit API error rather than a model completion;
        this method extracts ``error`` from the JSON body (falling back to a
        500-char raw slice) and raises :class:`ArticleGenerationError`.

        Args:
            context: Pre-built context string to feed into the system prompt
                (typically combines :meth:`load_context` output with the
                meeting transcript).
            user_content: Optional extra instructions/context for this run.
                When falsy, the user message degenerates to
                ``"Write the article now."``.

        Returns:
            ``{"title": str, "content": str}`` per :meth:`_format_response`.

        Raises:
            ArticleGenerationError: On empty bodies, explicit API errors, or
                any other exception bubbling up from the LLM call (original
                exception preserved as ``__cause__``).
        """
        personality = self.get_personality()
        system_prompt = self.get_system_prompt(context)

        if user_content:
            user_message = (
                f"Additional context: {user_content}\n\nWrite the article now."
            )
        else:
            user_message = "Write the article now."

        llm = LLMTextQuery(provider=TextLLMProvider.XAI)
        try:
            response = llm.get_response(
                context=system_prompt,
                message=user_message,
                article_type=personality["article_type"],
                tone=personality["tone"],
            )

            if isinstance(response, JSONResponse):
                try:
                    err = json.loads(response.body.decode()).get(
                        "error", "Unknown xAI API error"
                    )
                except Exception:
                    err = response.body.decode(errors="replace")[:500]
                raise ArticleGenerationError(err) from None

            return self._format_response(response)

        except ArticleGenerationError:
            raise
        except Exception as e:
            raise ArticleGenerationError(
                f"Failed to generate article: {str(e)}"
            ) from e

    def generate_bullet_points(self, article_content: str) -> Dict[str, Any]:
        """
        Generate a bullet-point summary of an already-written article.

        Loads ``article_types/bullet-point-summary.md`` for the article-type
        guidance, then asks xAI/Grok for a summary capped at 850 characters
        (with a dedicated bullet for citizen concerns / public comments /
        community feedback when present).

        Unlike :meth:`generate_article`, this method **does not raise** —
        errors are returned in the ``error`` field of the result so callers
        can render partial output.

        Args:
            article_content: The full article body to summarize (typically
                the ``content`` field returned by :meth:`generate_article`,
                including the ``<article>`` wrapper).

        Returns:
            ``{"bullet_points": str | None, "error": str | None}``. On
            success ``bullet_points`` is the model output and ``error`` is
            ``None``; on failure ``bullet_points`` is ``None`` and ``error``
            holds either ``"API error: ..."`` (for ``JSONResponse`` errors)
            or the raw exception message.
        """
        bullet_point_summary_context = self._load_attribute_context(
            "article_types", "bullet-point-summary"
        )
        context = (
            "You are writing this type of article: "
            + bullet_point_summary_context
            + "\n\n"
            + "Here is the article content that you will be summarizing: "
            + "\n"
            + article_content
        )
        message = "Now write a bullet point summary of the article content. Keep the summary under 850 characters. If there are any citizen concerns, public comments, or community feedback mentioned, include them as a dedicated bullet point."
        logger.info(f"Context: {context}")
        logger.info(f"Message: {message}")

        llm = LLMTextQuery(provider=TextLLMProvider.XAI)
        try:
            response = llm.get_response(
                context=context,
                message=message,
                article_type="bullet-point-summary",
                tone="neutral",
            )

            if isinstance(response, JSONResponse):
                try:
                    err = json.loads(response.body.decode()).get(
                        "error", "Unknown xAI API error"
                    )
                except Exception:
                    err = response.body.decode(errors="replace")[:500]
                return {
                    "bullet_points": None,
                    "error": f"API error: {err}",
                }

            bullet_points = response.get("response", "")
            return {"bullet_points": bullet_points, "error": None}

        except Exception as e:
            return {"bullet_points": None, "error": str(e)}
