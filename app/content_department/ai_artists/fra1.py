import os
import logging
from typing import Dict, Any
from app.content_department.ai_artists.base_artist import BaseArtist
from app.content_department.creation_tools.openai_image_query import OpenAIImageQuery
from app.content_department.creation_tools.xai_image_query import XAIImageQuery

logger = logging.getLogger(__name__)


class FRA1(BaseArtist):
    """
    FRA1 - Fall River Artist 1.
    An AI artist with fixed watercolor-based editorial sci-fi style.
    Uses literal translation methodology - only depicts explicit meeting content.
    """

    # Fixed identity traits
    FIRST_NAME = "FR"
    LAST_NAME = "A1"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME
    SLANT = "neutral"  # Artists stay apolitical
    STYLE = "watercolor-based editorial sci-fi"  # Fixed style, not randomized

    def _get_trait_by_name(self, trait_type: str, trait_name: str) -> Dict[str, str]:
        """
        Get a specific trait by name from a context folder.

        Args:
            trait_type: Folder name (e.g., "aesthetic", "style/art")
            trait_name: Name of the trait file (without .txt extension)

        Returns:
            Dict with 'name' and 'description' (file contents)
        """
        base_path = "./app/content_department/creation_tools/context_files"
        folder = os.path.join(base_path, trait_type)
        file_path = os.path.join(folder, f"{trait_name}.txt")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                description = f.read().strip()
            return {"name": trait_name, "description": description}
        except FileNotFoundError:
            logger.warning(f"Trait file not found: {file_path}")
            return {"name": trait_name, "description": ""}
        except Exception as e:
            logger.warning(f"Error loading trait {trait_name}: {str(e)}")
            return {"name": trait_name, "description": ""}

    def generate_image(
        self, title: str, bullet_points: str = "", model: str = "gpt-image-1"
    ) -> Dict[str, Any]:
        """
        Generate an editorial illustration using FRA1's fixed style.
        Uses literal translation methodology - only explicit meeting content.

        Args:
            title (str): The article title.
            bullet_points (str): Summary bullet points to be condensed into a snippet.

        Returns:
            Dict containing image_url, prompt_used, snippet, artist info, or error.
        """
        personality = self.get_personality()

        # Fixed traits - no randomization
        medium_name = "watercolor"
        aesthetic_name = "editorial_sci_fi"
        style_name = "editorial_sci_fi"

        # Load aesthetic and art style from context files
        aesthetic = self._get_trait_by_name("aesthetic", aesthetic_name)
        art_style = self._get_trait_by_name("style/art", style_name)

        # Combine aesthetic and art style descriptions
        style_description = f"{art_style['description']} {aesthetic['description']}"

        # Generate a short snippet from bullet points
        snippet = self.generate_snippet(bullet_points) if bullet_points else ""

        # Build prompt with FRA1's literal translation methodology
        full_prompt = (
            f"Create an editorial illustration about: {title}. "
            f"Content: {snippet}. "
            f"LITERAL TRANSLATION METHODOLOGY: Only depict subjects, objects, and environments explicitly "
            f"referenced in the meeting content. Do not add "
            f"inferred meaning. Visual elements must directly correspond to what was discussed or presented. "
            f"Spatial hierarchy and framing are governed by informational relevance, "
            f"to suggest importance, failure, tension, or success. "
            f"CHRONOLOGICAL INTEGRITY: Visuals reflect the sequence and scope of discussion. "
            f"IMPORTANT: Do NOT render the article title, headlines, or large text blocks in the image. "
            f"Small incidental words or signs that serve the visual composition are acceptable. "
            f"FOCUS ON TOPICS: Visualize the actual topics, issues, and subjects being discussed "
            f"(buildings, infrastructure, community concerns, events, etc.) rather than showing people "
            f"sitting in a meeting room. Prefer city streets, neighborhoods, buildings, and community "
            f"settings over council chambers or meeting rooms. Only show councilors or officials if "
            f"they are the central subject of the story itself. "
            f"Keep it pg-13"
            f"VISUAL STYLE: {style_description} "
            f"Follow these style requirements strictly."
        )

        # Use OpenAI if model is OpenAI, otherwise use xAI (Grok) as default
        if model.startswith("gpt-"):
            image_query = OpenAIImageQuery()
        else:
            image_query = XAIImageQuery()

        try:
            response = image_query.generate_image(
                prompt=full_prompt,
                medium=medium_name,
                aesthetic=aesthetic_name,
                model=model,
            )

            if "error" in response:
                return {"image_url": None, "error": response["error"]}

            return {
                "image_url": response.get("image_url"),
                "prompt_used": full_prompt,
                "snippet": snippet,
                "artist": personality["name"],
                "medium": medium_name,
                "aesthetic": aesthetic_name,
                "style": style_name,
            }

        except Exception as e:
            return {"image_url": None, "error": f"Failed to generate image: {str(e)}"}
