from typing import Dict, Any, Optional
import os
from ..data.data_classes import Tone, Category
from app.ai_journalists.base_journalist import BaseJournalist


class AureliusStone(BaseJournalist):
    FIRST_NAME = "Aurelius"
    LAST_NAME = "Stone"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME  # Required by BaseJournalist
    DEFAULT_TONE = Tone.FORMAL  # Change from CRITICAL to FORMAL
    DEFAULT_ARTICLE_TYPE = Category.OP_ED  # Change from OPINION to OP_ED
    SLANT = "conservative"
    STYLE = "conversational"

    def __init__(
        self, tone: Optional[Tone] = None, article_type: Optional[Category] = None
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
        article_type: Optional[Category] = None,
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
        context_files_path = os.path.join(os.path.dirname(__file__), '..', 'context_files', 'bios')
        bio_path = os.path.join(context_files_path, bio_filename)
        try:
            with open(bio_path, 'r', encoding='utf-8') as file:
                return file.read().strip()
        except FileNotFoundError:
            return f"Bio file not found for {self.FULL_NAME}: {bio_path}"
        except Exception as e:
            return f"Error loading bio: {str(e)}"

    def get_description(self) -> str:
        """Load and return the journalist's professional description."""
        description_filename = f"{self.FIRST_NAME.lower()}_{self.LAST_NAME.lower()}_description.txt"
        # Navigate to context_files/descriptions from the ai_journalists directory
        context_files_path = os.path.join(os.path.dirname(__file__), '..', 'context_files', 'descriptions')
        description_path = os.path.join(context_files_path, description_filename)
        try:
            with open(description_path, 'r', encoding='utf-8') as file:
                return file.read().strip()
        except FileNotFoundError:
            return f"Description file not found for {self.FULL_NAME}: {description_path}"
        except Exception as e:
            return f"Error loading description: {str(e)}"

    def get_full_profile(self) -> Dict[str, str]:
        """Return a complete profile including bio, description, and basic info."""
        return {
            'name': self.FULL_NAME,
            'first_name': self.FIRST_NAME,
            'last_name': self.LAST_NAME,
            'bio': self.get_bio(),
            'description': self.get_description(),
            'tone': self.DEFAULT_TONE.value,
            'article_type': self.DEFAULT_ARTICLE_TYPE.value,
            'slant': self.SLANT,
            'style': self.STYLE
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
        Generate the actual article content based on context and user input.
        This is a placeholder for actual AI generation logic.
        """
        personality = self.get_personality()
        # Placeholder for article generation logic
        generated_content = (
            f"Generated Article by {personality['name']}:\n\n"
            f"Based on the following context:\n{context[:100]}...\n\n"
            f"User Input: {user_content if user_content else 'No user content provided.'}\n\n"
            f"This is a placeholder article written in a {personality['tone'].lower()} tone "
            f"about {personality['article_type'].lower()} with a {personality['slant'].lower()} slant "
            f"and a {personality['style'].lower()} style."
        )
        return generated_content

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

