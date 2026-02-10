from typing import Dict, Any
from app.content_department.ai_artists.base_artist import BaseArtist
from app.content_department.creation_tools.openai_image_query import OpenAIImageQuery
from app.content_department.creation_tools.xai_image_query import XAIImageQuery


class FRA1(BaseArtist):
    """
    FRA1 - Fall River Artist 1.
    Inherits shared functionality from BaseArtist and BaseCreator.
    Uses a fixed art style rather than randomizing.
    """

    # Fixed identity traits
    FIRST_NAME = "FR"
    LAST_NAME = "A1"
    FULL_NAME = f"{FIRST_NAME} {LAST_NAME}"
    NAME = FULL_NAME
    SLANT = "neutral"  # Artists stay apolitical
    STYLE = "urban_acrylic"  # Fixed style for FRA1

    # FRA1's signature style
    FIXED_STYLE = (
        "Modern urban acrylic illustration, digital ink and wash technique, "
        "soft pigment blooms, textured paper grain, loose but intentional brushwork, "
        "architectural realism with simplified details, atmospheric lighting, "
        "editorial art style, refined and timeless. "
        "Make sure the color goes to the edge of the image on all sides."
    )

    def generate_image(
        self, title: str, bullet_points: str = "", model: str = "gpt-image-1"
    ) -> Dict[str, Any]:
        """
        Generate an editorial illustration with FRA1's fixed style.

        Args:
            title (str): The article title.
            bullet_points (str): Summary bullet points to be condensed into a snippet.

        Returns:
            Dict containing image_url, prompt_used, snippet, artist info, or error.
        """
        personality = self.get_personality()

        # Generate a short snippet from bullet points to stay under 1024 char limit
        snippet = self.generate_snippet(bullet_points) if bullet_points else ""

        # Build prompt with FRA1's fixed style
        full_prompt = (
            f"Create an editorial illustration about: {title}. "
            f"Content: {snippet}. "
            f"IMPORTANT: Do NOT render the article title, headlines, or large text blocks in the image. "
            f"Small incidental words or signs that serve the visual composition are acceptable. "
            f"FOCUS ON TOPICS: Visualize the actual topics, issues, and subjects being discussed "
            f"(buildings, infrastructure, community concerns, events, etc.) rather than showing people "
            f"sitting in a meeting room. Prefer city streets, neighborhoods, buildings, and community "
            f"settings over council chambers or meeting rooms. Only show councilors or officials if "
            f"they are the central subject of the story itself. Don't show councilors sitting at a desk while in the community. "
            f"VISUAL VARIETY: Since these images will be displayed side by side, ensure each image has "
            f"a unique composition, perspective, color palette, and visual approach. Vary between close-ups, "
            f"wide shots, different angles, day/night scenes, and diverse focal points to avoid repetitive "
            f"or similar-looking images. "
            f"MOOD/TONE: This is for a newspaper, so keep the mood appropriate - not too dark, gloomy, or dystopian. "
            f"Even when covering serious topics, maintain a balanced, journalistic visual tone. "
            f"Avoid overly dramatic shadows, apocalyptic atmospheres, or depressing color palettes. "
            f"Do NOT include blood, gore, violence, or graphic imagery. "
            f"STYLE: {self.FIXED_STYLE}"
        )

        # Choose image client based on model
        if model == "grok-imagine-image":
            image_query = XAIImageQuery()
        else:
            image_query = OpenAIImageQuery()

        try:
            response = image_query.generate_image(
                prompt=full_prompt,
                medium="acrylic",
                aesthetic="urban_editorial",
                model=model,
            )

            if "error" in response:
                return {"image_url": None, "error": response["error"]}

            return {
                "image_url": response.get("image_url"),
                "prompt_used": full_prompt,
                "snippet": snippet,
                "artist": personality["name"],
                "medium": "acrylic",
                "aesthetic": "urban_editorial",
                "style": "urban_acrylic",
            }

        except Exception as e:
            return {"image_url": None, "error": f"Failed to generate image: {str(e)}"}
