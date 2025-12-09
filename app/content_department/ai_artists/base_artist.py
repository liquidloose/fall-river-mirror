from typing import Dict, Any, Optional
from ..creation_tools.base_creator import BaseCreator
from ..creation_tools.xai_image_query import XAIImageQuery


class BaseArtist(BaseCreator):
    """
    Base class for AI artists.
    Adds image-specific functionality on top of BaseCreator.
    """

    # Artist-specific traits (must be defined by subclasses)
    DEFAULT_MEDIUM: str  # e.g., "digital", "watercolor", "oil"
    DEFAULT_AESTHETIC: str  # e.g., "surrealist", "minimalist", "photorealistic"

    def __init__(self, medium: Optional[str] = None, aesthetic: Optional[str] = None):
        """Constructor to allow instance-specific mutable attributes."""
        self.medium = medium if medium is not None else self.DEFAULT_MEDIUM
        self.aesthetic = aesthetic if aesthetic is not None else self.DEFAULT_AESTHETIC

    def get_personality(self) -> Dict[str, Any]:
        """Get full personality including artist-specific traits."""
        base = self.get_base_personality()
        return {
            **base,
            "medium": self.medium,
            "aesthetic": self.aesthetic,
        }

    def get_full_profile(self) -> Dict[str, Any]:
        """Return complete artist profile."""
        return {
            "name": self.FULL_NAME,
            "first_name": self.FIRST_NAME,
            "last_name": self.LAST_NAME,
            "bio": self.get_bio(),
            "description": self.get_description(),
            "medium": self.DEFAULT_MEDIUM,
            "aesthetic": self.DEFAULT_AESTHETIC,
            "slant": self.SLANT,
            "style": self.STYLE,
        }

    def load_context(
        self,
        base_path: str = "./app/content_department/creation_tools/context_files",
        medium: Optional[str] = None,
        aesthetic: Optional[str] = None,
    ) -> str:
        """Load and concatenate context files for artist attributes."""
        selected_medium = medium if medium is not None else self.medium
        selected_aesthetic = aesthetic if aesthetic is not None else self.aesthetic

        medium_content = self._load_attribute_context(
            base_path, "medium", selected_medium
        )
        aesthetic_content = self._load_attribute_context(
            base_path, "aesthetic", selected_aesthetic
        )
        slant_content = self._load_attribute_context(base_path, "slant", self.SLANT)
        style_content = self._load_attribute_context(base_path, "style", self.STYLE)

        return (
            f"Medium Context ({selected_medium}):\n{medium_content}\n\n"
            f"Aesthetic Context ({selected_aesthetic}):\n{aesthetic_content}\n\n"
            f"Slant Context ({self.SLANT}):\n{slant_content}\n\n"
            f"Style Context ({self.STYLE}):\n{style_content}"
        )

    def generate_image(self, context: str, prompt: str) -> Dict[str, Any]:
        """
        Generate image content using xAI Aurora.
        Uses the artist's personality and style guidelines.

        Args:
            context (str): Context information for the image generation.
            prompt (str): The user's image generation request.

        Returns:
            Dict containing image_url, prompt_used, artist info, or error.
        """
        personality = self.get_personality()

        # Build styled prompt incorporating artist traits
        full_prompt = (
            f"{prompt}, "
            f"{personality['medium']} medium, "
            f"{personality['aesthetic']} aesthetic, "
            f"{personality['style']} style"
        )

        xai_image_query = XAIImageQuery()  # Initialize the XAIImageQuery class

        try:
            response = xai_image_query.generate_image(
                prompt=full_prompt,
                medium=personality["medium"],
                aesthetic=personality["aesthetic"],
            )

            if "error" in response:
                return {"image_url": None, "error": response["error"]}

            return {
                "image_url": response.get("image_url"),
                "prompt_used": full_prompt,
                "context": context,
                "artist": personality["name"],
                "medium": personality["medium"],
                "aesthetic": personality["aesthetic"],
            }

        except Exception as e:
            return {"image_url": None, "error": f"Failed to generate image: {str(e)}"}
