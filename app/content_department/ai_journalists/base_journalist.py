from typing import Dict, Any, Optional
from ...data.enum_classes import Tone, ArticleType
from ..creation_tools.base_creator import BaseCreator
from ..creation_tools.xai_text_query import XAITextQuery


class BaseJournalist(BaseCreator):
    """
    Base class for AI journalists.
    Adds article-specific functionality on top of BaseCreator.
    """

    # Journalist-specific traits (must be defined by subclasses)
    DEFAULT_TONE: Tone
    DEFAULT_ARTICLE_TYPE: ArticleType

    def __init__(
        self, tone: Optional[Tone] = None, article_type: Optional[ArticleType] = None
    ):
        """Constructor to allow instance-specific mutable attributes."""
        self.tone = tone if tone is not None else self.DEFAULT_TONE
        self.article_type = (
            article_type if article_type is not None else self.DEFAULT_ARTICLE_TYPE
        )

    def get_personality(self) -> Dict[str, Any]:
        """Get full personality including journalist-specific traits."""
        base = self.get_base_personality()
        return {
            **base,
            "tone": self.tone.value,
            "article_type": self.article_type.value,
        }

    def get_full_profile(self) -> Dict[str, Any]:
        """Return complete journalist profile."""
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
        base_path: str = "./app/content_department/creation_tools/context_files",
        tone: Optional[Tone] = None,
        article_type: Optional[ArticleType] = None,
    ) -> str:
        """Load and concatenate context files for journalist attributes."""
        selected_tone = tone if tone is not None else self.tone
        selected_article_type = (
            article_type if article_type is not None else self.article_type
        )

        tone_content = self._load_attribute_context(
            base_path, "tone", selected_tone.value
        )
        article_type_content = self._load_attribute_context(
            base_path, "article_types", selected_article_type.value
        )
        slant_content = self._load_attribute_context(base_path, "slant", self.SLANT)
        style_content = self._load_attribute_context(base_path, "style", self.STYLE)

        return (
            f"Tone Context ({selected_tone.value}):\n{tone_content}\n\n"
            f"Article Type Context ({selected_article_type.value}):\n{article_type_content}\n\n"
            f"Slant Context ({self.SLANT}):\n{slant_content}\n\n"
            f"Style Context ({self.STYLE}):\n{style_content}"
        )

    def get_guidelines(self) -> str:
        """
        Return journalist-specific guidelines for article generation.
        Override in subclasses to provide custom guidelines.
        """
        return ""

    def get_system_prompt(self, context: str) -> str:
        """Build the system prompt for article generation."""
        personality = self.get_personality()
        guidelines = self.get_guidelines()

        return f"""{context}

You are {personality['name']}, a {personality['slant']} journalist with a {personality['style']} writing style.

Write an article with the following characteristics:
- Subject: The transcript content provided above
- Tone: {personality['tone']}
- Article Type: {personality['article_type']}
- Style: {personality['style']}
- Political Slant: {personality['slant']}

Guidelines:
{guidelines}"""

    def _format_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Format the API response into article HTML."""
        article_text = response.get("response", "No article content generated")
        title = response.get("title", "Untitled Article")

        paragraphs = [p.strip() for p in article_text.split("\n\n") if p.strip()]
        formatted_paragraphs = [f"<p>{paragraph}</p>" for paragraph in paragraphs]

        article_content = f"""<article role="article" aria-labelledby="article-title">
    <header>
        <h1 id="article-title">{title}</h1>
    </header>
    <div class="article-body">
        {chr(10).join(f"        {p}" for p in formatted_paragraphs)}
    </div>
</article>"""

        return {"title": title, "content": article_content}

    def generate_article(self, context: str, user_content: str) -> Dict[str, Any]:
        """
        Generate article content using XAI/Grok API.
        Uses the journalist's personality and guidelines.
        """
        personality = self.get_personality()
        system_prompt = self.get_system_prompt(context)

        user_message = f"""Please write a complete article based on the provided context.

{f"Additional context from user: {user_content}" if user_content else ""}

Write a full article that would be suitable for publication."""

        xai_text_query = XAITextQuery()  # Initialize the XAITextQuery class
        try:
            response = xai_text_query.get_response(
                context=system_prompt,
                message=user_message,
                article_type=personality["article_type"],
                tone=personality["tone"],
            )

            if hasattr(response, "status_code"):
                return {
                    "title": "Error",
                    "content": f"Error generating article: {response.content}",
                }

            return self._format_response(response)

        except Exception as e:
            return {
                "title": "Error",
                "content": f"Failed to generate article: {str(e)}",
            }
