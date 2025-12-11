# Standard library imports
import os
import logging

# Third-party imports
from xai_sdk import Client

logger = logging.getLogger(__name__)


class XAIImageQuery:
    """
    A processor class for handling xAI image generation (grok-2-image) interactions.

    This class provides functionality to communicate with the xAI API for generating
    AI-powered images. It handles authentication, prompt formatting, and error
    handling for the xAI image service.

    Attributes:
        api_key (str): The API key for xAI authentication, loaded from environment variables
    """

    def __init__(self):
        """
        Initialize the XAIImageProcessor with API key from environment variables.

        The API key should be set in the XAI_API_KEY environment variable.
        If not set, the processor will return error responses when attempting to use the API.
        """
        self.api_key = os.getenv("XAI_API_KEY")

    def generate_image(
        self,
        prompt: str,
        medium: str = None,
        aesthetic: str = None,
    ) -> dict:
        """
        Generate an image using the xAI grok-2-image model.

        This method creates an image generation request with the xAI API,
        incorporating style parameters like medium and aesthetic into the prompt.

        Args:
            prompt (str): The image generation prompt describing what to create.
            medium (str, optional): The artistic medium (e.g., "digital", "watercolor").
            aesthetic (str, optional): The aesthetic style (e.g., "surrealist", "minimalist").

        Returns:
            dict: A dictionary containing either:
                  - Success: {"image_url": "url", "prompt_used": "prompt", ...}
                  - Error: {"error": "error message"}
        """
        if not self.api_key:
            return {"error": "XAI_API_KEY environment variable is not set"}

        try:
            client = Client(api_key=self.api_key)

            # Log the full prompt before sending to xAI
            logger.info(f"=== XAI IMAGE PROMPT ({len(prompt)} chars) ===")
            logger.info(f"FULL PROMPT: {prompt}")
            logger.info(f"=== END PROMPT ===")

            response = client.image.sample(
                model="grok-2-image",
                prompt=prompt,
                image_format="url",
            )

            return {
                "image_url": response.url,
                "prompt_used": prompt,
                "medium": medium,
                "aesthetic": aesthetic,
            }

        except Exception as e:
            return {"error": f"Failed to generate image from xAI: {str(e)}"}
