import os
import random
import logging
from typing import Dict, Any, Optional
from ..creation_tools.base_creator import BaseCreator
from ..creation_tools.xai_image_query import XAIImageQuery
from ..creation_tools.xai_text_query import XAITextQuery

logger = logging.getLogger(__name__)


class BaseArtist(BaseCreator):
    """
    Base class for AI artists.
    Adds image-specific functionality on top of BaseCreator.
    Traits (medium, aesthetic, style) are randomized per image generation.
    """

    def load_context(self, base_path: str = "./context_files") -> str:
        """
        Artists don't pre-load context - traits are randomized per generation.
        This satisfies the abstract method requirement.
        """
        return ""

    def get_personality(self) -> Dict[str, Any]:
        """Get base personality for the artist."""
        return self.get_base_personality()

    def get_full_profile(self) -> Dict[str, Any]:
        """Return complete artist profile."""
        return {
            "name": self.FULL_NAME,
            "first_name": self.FIRST_NAME,
            "last_name": self.LAST_NAME,
            "bio": self.get_bio(),
            "description": self.get_description(),
        }

    def get_random_trait(self, trait_type: str) -> str:
        """
        Pick a random trait from a context folder.

        Args:
            trait_type: Folder name (e.g., "medium", "aesthetic", "style/art")

        Returns:
            Random trait name (filename without .txt)
        """
        base_path = "./app/content_department/creation_tools/context_files"
        folder = os.path.join(base_path, trait_type)
        try:
            files = [
                f.replace(".txt", "")
                for f in os.listdir(folder)
                if f.endswith(".txt") and f != "readme.txt"
            ]
            return random.choice(files) if files else trait_type
        except FileNotFoundError:
            return trait_type

    def generate_snippet(self, bullet_points: str) -> str:
        """
        Generate a short summary snippet from bullet points for image prompts.

        Args:
            bullet_points (str): The full bullet points to summarize.

        Returns:
            str: A concise summary (~200-300 chars) suitable for image prompts.
        """
        if not bullet_points or len(bullet_points) <= 300:
            return bullet_points

        xai_text_query = XAITextQuery()

        try:
            response = xai_text_query.get_response(
                context="You are a concise summarizer. Create a very brief visual description suitable for an image generation prompt. Focus on key visual elements, themes, and mood. Maximum 250 characters. Return ONLY the summary text, no explanations.",
                message=f"Summarize these bullet points into a brief visual description:\n\n{bullet_points}",
            )

            if hasattr(response, "status_code"):
                logger.warning(f"Snippet generation failed: {response.content}")
                return bullet_points[:300]

            snippet = response.get("content", response.get("response", ""))
            if snippet:
                return snippet[:300]

            return bullet_points[:300]

        except Exception as e:
            logger.warning(f"Snippet generation error: {str(e)}")
            return bullet_points[:300]

    def generate_image(self, title: str, bullet_points: str = "") -> Dict[str, Any]:
        """
        Generate an editorial illustration for an article.

        Args:
            title (str): The article title.
            bullet_points (str): Summary bullet points to be condensed into a snippet.

        Returns:
            Dict containing image_url, prompt_used, snippet, artist info, or error.
        """
        personality = self.get_personality()

        # Randomize traits for this generation (no slant - art stays apolitical)
        medium = self.get_random_trait("medium")
        aesthetic = self.get_random_trait("aesthetic")
        style = self.get_random_trait("style/art")

        # Generate a short snippet from bullet points to stay under 1024 char limit
        snippet = self.generate_snippet(bullet_points) if bullet_points else ""

        # Build prompt with explicit style instructions
        full_prompt = (
            f"Create an editorial illustration for: {title}. "
            f"Content: {snippet}. "
            f"Style requirements: Use {medium} medium, {aesthetic} aesthetic, {style} art style. "
            f"Follow these style requirements strictly."
        )

        xai_image_query = XAIImageQuery()

        try:
            response = xai_image_query.generate_image(
                prompt=full_prompt,
                medium=medium,
                aesthetic=aesthetic,
            )

            if "error" in response:
                return {"image_url": None, "error": response["error"]}

            return {
                "image_url": response.get("image_url"),
                "prompt_used": full_prompt,
                "snippet": snippet,
                "artist": personality["name"],
                "medium": medium,
                "aesthetic": aesthetic,
                "style": style,
            }

        except Exception as e:
            return {"image_url": None, "error": f"Failed to generate image: {str(e)}"}
