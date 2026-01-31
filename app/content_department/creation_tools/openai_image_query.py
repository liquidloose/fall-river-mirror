# Standard library imports
import os
import logging
import base64

# Third-party imports
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIImageQuery:
    """
    A processor class for handling OpenAI image generation interactions.

    This class provides functionality to communicate with the OpenAI API for generating
    AI-powered images using the gpt-image-1 model. It handles authentication,
    prompt formatting, and error handling for the OpenAI image service.

    Attributes:
        api_key (str): The API key for OpenAI authentication, loaded from environment variables
    """

    def __init__(self):
        """
        Initialize the OpenAIImageQuery with API key from environment variables.

        The API key should be set in the OPENAI_API_KEY environment variable.
        If not set, the processor will return error responses when attempting to use the API.
        """
        self.api_key = os.getenv("OPENAI_API_KEY")

    def generate_image(
        self,
        prompt: str,
        medium: str = None,
        aesthetic: str = None,
        model: str = "gpt-image-1",
        size: str = "1536x1024",  # Landscape aspect ratio for featured images
    ) -> dict:
        """
        Generate an image using the OpenAI gpt-image-1 API.

        This method creates an image generation request with the OpenAI API,
        incorporating style parameters like medium and aesthetic into the prompt.

        Args:
            prompt (str): The image generation prompt describing what to create.
            medium (str, optional): The artistic medium (e.g., "digital", "watercolor").
            aesthetic (str, optional): The aesthetic style (e.g., "surrealist", "minimalist").
            model (str): The OpenAI model to use (default: "gpt-image-1").
            size (str): Image dimensions. Options: "1024x1024" (square),
                       "1536x1024" (landscape), "1024x1536" (portrait).
                       Default: "1536x1024" for featured image use.

        Returns:
            dict: A dictionary containing either:
                  - Success: {"image_url": "url" or "data:image/png;base64,...", "prompt_used": "prompt", ...}
                  - Error: {"error": "error message"}
        """
        if not self.api_key:
            return {"error": "OPENAI_API_KEY environment variable is not set"}

        try:
            client = OpenAI(api_key=self.api_key)

            # Log the full prompt before sending to OpenAI
            logger.info(f"=== OPENAI IMAGE PROMPT ({len(prompt)} chars) ===")
            logger.info(f"FULL PROMPT: {prompt}")
            logger.info(f"=== END PROMPT ===")

            response = client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size=size,
            )

            # Extract the image URL or base64 data
            if response.data:
                # Prefer URL if available (Swagger can display URLs)
                if hasattr(response.data[0], "url") and response.data[0].url:
                    image_url = response.data[0].url
                elif (
                    hasattr(response.data[0], "b64_json") and response.data[0].b64_json
                ):
                    # Fall back to base64 if URL not available
                    image_base64 = response.data[0].b64_json
                    image_url = f"data:image/png;base64,{image_base64}"
                else:
                    return {"error": "No image data returned from OpenAI"}

                return {
                    "image_url": image_url,
                    "prompt_used": prompt,
                    "medium": medium,
                    "aesthetic": aesthetic,
                }
            else:
                return {"error": "No image data returned from OpenAI"}

        except Exception as e:
            return {"error": f"Failed to generate image from OpenAI: {str(e)}"}
