from typing import Dict, Any, Optional
import os
from ...data.enum_classes import Tone, ArticleType
from .base_journalist import BaseJournalist
from ..creation_tools.xai_processor import XAIProcessor


class AureliusStone(BaseJournalist):
    FIRST_NAME = "Aurelius"
    LAST_NAME = "Stone"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME  # Required by BaseJournalist
    DEFAULT_TONE = Tone.ANALYTICAL  # Change from CRITICAL to FORMAL
    DEFAULT_ARTICLE_TYPE = ArticleType.OP_ED  # Change from OPINION to OP_ED
    SLANT = "unbiased"
    STYLE = "conversational"

    def __init__(
        self, tone: Optional[Tone] = None, article_type: Optional[ArticleType] = None
    ):
        """
        Constructor to allow instance-specific mutable attributes.
        """
        self.tone = tone if tone is not None else self.DEFAULT_TONE
        self.article_type = (
            article_type if article_type is not None else self.DEFAULT_ARTICLE_TYPE
        )

    def load_context(
        self,
        base_path: str = "./app/context_files",
        tone: Optional[Tone] = None,
        article_type: Optional[ArticleType] = None,
    ) -> str:
        """
        Load and concatenate context files for all attributes, using provided or instance values.
        """

        # Use provided values or fall back to instance values
        selected_tone = tone
        selected_article_type = (
            article_type if article_type is not None else self.article_type
        )

        personality = {
            "name": self.NAME,
            "tone": selected_tone.value,
            "article_type": selected_article_type.value,
            "slant": self.SLANT,
            "style": self.STYLE,
        }

        tone_content = self._load_attribute_context(
            base_path, "tone", personality["tone"]
        )
        article_type_content = self._load_attribute_context(
            base_path, "article_types", personality["article_type"]
        )
        slant_content = self._load_attribute_context(
            base_path, "slant", personality["slant"]
        )
        style_content = self._load_attribute_context(
            base_path, "style", personality["style"]
        )

        # Concatenate the contents with clear separators
        concatenated_context = (
            f"Tone Context ({personality['tone']}):\n{tone_content}\n\n"
            f"Article Type Context ({personality['article_type']}):\n{article_type_content}\n\n"
            f"Slant Context ({personality['slant']}):\n{slant_content}\n\n"
            f"Style Context ({personality['style']}):\n{style_content}"
        )

        return concatenated_context

    def get_bio(self) -> str:
        """Load and return the journalist's biographical information."""
        bio_filename = f"{self.FIRST_NAME.lower()}_{self.LAST_NAME.lower()}_bio.txt"
        # Navigate to context_files/bios from the ai_journalists directory
        context_files_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "context_files", "bios"
        )
        bio_path = os.path.join(context_files_path, bio_filename)
        try:
            with open(bio_path, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            return f"Bio file not found for {self.FULL_NAME}: {bio_path}"
        except Exception as e:
            return f"Error loading bio: {str(e)}"

    def get_description(self) -> str:
        """Load and return the journalist's professional description."""
        description_filename = (
            f"{self.FIRST_NAME.lower()}_{self.LAST_NAME.lower()}_description.txt"
        )
        # Navigate to context_files/descriptions from the ai_journalists directory
        context_files_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "context_files", "descriptions"
        )
        description_path = os.path.join(context_files_path, description_filename)
        try:
            with open(description_path, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            return (
                f"Description file not found for {self.FULL_NAME}: {description_path}"
            )
        except Exception as e:
            return f"Error loading description: {str(e)}"

    def get_full_profile(self) -> Dict[str, str]:
        """Return a complete profile including bio, description, and basic info."""
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

    def _load_attribute_context(
        self, base_path: str, attribute_type: str, attribute_value: str
    ) -> str:
        """
        Helper method to load context content for a specific attribute.
        """
        file_name = f"{attribute_value.lower().replace(' ', '_')}.txt"
        file_path = os.path.join(base_path, attribute_type, file_name)
        print(f"DEBUG: Trying to open: {file_path}")  # Add this debug line
        try:
            with open(file_path, "r") as file:
                return file.read()
        except FileNotFoundError:
            return f"Context file not found for {attribute_type}: {attribute_value} - Looking for: {file_path} the base_path is {base_path}"

    def generate_article(
        self,
        context: str,
        user_content: str,
    ) -> str:
        """
        Generate the actual article content using XAI/Grok API.
        """
        personality = self.get_personality()

        # Create the system prompt with context and personality
        system_prompt = f"""
{context}

You are {personality['name']}, a {personality['slant']} journalist with a {personality['style']} writing style.

Write an article with the following characteristics:
- Subject: The transcript content provided above
- Tone: {personality['tone']}
- Article Type: {personality['article_type']}
- Style: {personality['style']}
- Political Slant: {personality['slant']}

Guidelines:
- Don't introduce yourself in the article.
- Write a comprehensive, factual account of what was discussed and decided in the meeting
- Use proper journalistic formatting with headline, lead paragraph, and body
- Maintain the specified tone and style throughout
- Report what happened without expressing opinions about whether decisions are good or bad
- Provide factual context and background for decisions and discussions
- Explain what was decided, who said what, and what the outcomes were
- Focus on the key points, decisions, and discussions from the transcript
- If there are any emergencies, mention them in the article and explain why they are scheduled and when they are happening.
- Explain what issues were discussed and note public participation to show local engagement
- Write at least 500-800 words with substantial detail about what transpired
- Include multiple paragraphs with thorough coverage of the meeting's content
- Present information objectively without bias or commentary on the merits of decisions
- Do not mention procedural details like roll call, reading of decorum rules, agenda approvals, or other routine administrative housekeeping
- Focus exclusively on substantive content, decisions, debates, and outcomes
- Do not use generic, repetitive openings like "Ever wonder how..." or "Let's break down..." - start directly with the specific content and decisions from this meeting
- Write as if this is one of many articles about the same city, so avoid explaining basic concepts about how city government works
"""

        # Create the user message
        user_message = f"""
Please write a complete article based on the provided context.

{f"Additional context from user: {user_content}" if user_content else ""}

Write a full article that would be suitable for publication.
"""

        # Initialize XAI processor and get response
        xai_processor = XAIProcessor()

        try:
            response = xai_processor.get_response(
                context=system_prompt,
                message=user_message,
                article_type=personality["article_type"],
                tone=personality["tone"],
            )

            # Check if response is an error (JSONResponse)
            if hasattr(response, "status_code"):
                return {
                    "title": "Error",
                    "content": f"Error generating article: {response.content}",
                }

            # Get the generated article content
            article_text = response.get("response", "No article content generated")

            # Get the AI-generated title
            title = response.get("title", "Untitled Article")

            # Use the article text as-is for content
            raw_content = article_text

            # Format content with WCAG compliant HTML
            # Split content into paragraphs and wrap each in <p> tags
            paragraphs = [p.strip() for p in raw_content.split("\n\n") if p.strip()]
            formatted_paragraphs = [f"<p>{paragraph}</p>" for paragraph in paragraphs]

            # Create WCAG compliant article structure
            article_content = f"""<article role="article" aria-labelledby="article-title">
    <header>
        <h1 id="article-title">{title}</h1>
    </header>
    <div class="article-body">
        {chr(10).join(f"        {p}" for p in formatted_paragraphs)}
    </div>
</article>"""

            # Return structured response
            return {"title": title, "content": article_content}

        except Exception as e:
            return f"Failed to generate article: {str(e)}"

    def get_personality(self) -> Dict[str, str]:
        """
        Instance method to get the current personality settings.
        """
        return {
            "name": self.NAME,
            "slant": self.SLANT,
            "style": self.STYLE,
            "tone": self.tone,
            "article_type": self.article_type,
        }
