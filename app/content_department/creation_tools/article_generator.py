import logging
from typing import Dict, Any
from fastapi.responses import JSONResponse
from .xai_text_query import XAITextQuery
from ...data.enum_classes import ArticleType, Tone
from .context_manager import ContextManager

logger = logging.getLogger(__name__)


class ArticleGenerator:
    """Generates article content based on context, prompts, and parameters."""

    def __init__(self, context_manager: ContextManager = None):
        self.context_manager = context_manager or ContextManager()
        self.xai_processor = XAITextQuery()

    def write_article(
        self,
        context: str,
        prompt: str,
        article_type: ArticleType,
        tone: Tone,
        committee: str,
        x,
    ) -> Dict[str, Any] | JSONResponse:
        """
        Generate article content based on context and parameters.

        Args:
            context (str): The base context for the article
            prompt (str): The user's specific writing prompt
            article_type (ArticleType): Type of article to generate
            tone (Tone): Writing tone to use
            committee (Committee): Committee type for the article

        Returns:
            Dict[str, Any] | JSONResponse: Generated article content or error response
        """
        try:
            # Build context based on article type
            final_context = self._build_article_context(context, article_type)

            # Build context based on tone
            final_context = self._build_tone_context(final_context, tone)

            # Log the request details for debugging
            logger.info(
                f"Processing article: type={article_type}, tone={tone}, committee={committee}"
            )

            # Create the full prompt
            full_prompt = f"This is the type of article: {article_type.value} This is the tone: {tone.value} This is the context: {context}. This is the user's prompt: {prompt}"
            logger.info(f"Full prompt: {full_prompt}")

            # Generate response using the XAI processor
            response = self.xai_processor.get_response(
                final_context,
                full_prompt,
                committee.value,
                article_type.value,
                tone.value,
            )
            logger.debug(f"Response generated successfully")
            return response

        except Exception as e:
            logger.error(f"Failed to generate article: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to generate article: {str(e)}"},
            )

    def _build_article_context(self, context: str, article_type: ArticleType) -> str:
        """Build context based on article type."""
        final_context = context
        match article_type:
            case ArticleType.OP_ED:
                final_context = context + self.context_manager.read_context_file(
                    "article_types", "op_ed.txt"
                )
            case ArticleType.SUMMARY:
                final_context = context + self.context_manager.read_context_file(
                    "article_types", "summary.txt"
                )
        return final_context

    def _build_tone_context(self, context: str, tone: Tone) -> str:
        """Build context based on writing tone."""
        final_context = context
        match tone:
            case Tone.FRIENDLY:
                final_context = context + self.context_manager.read_context_file(
                    "tone", "friendly.txt"
                )
            case Tone.PROFESSIONAL:
                final_context = context + self.context_manager.read_context_file(
                    "tone", "professional.txt"
                )
            case Tone.CASUAL:
                final_context = context + self.context_manager.read_context_file(
                    "tone", "casual.txt"
                )
            case Tone.FORMAL:
                final_context = context + self.context_manager.read_context_file(
                    "tone", "formal.txt"
                )
        return final_context
