# Standard library imports
import os
import logging
import base64

# Third-party imports
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIImageQuery:
    """
    A processor class for handling OpenAI GPT-5.1 image generation interactions.

    This class provides functionality to communicate with the OpenAI API for generating
    AI-powered images using the GPT-5.1 Responses API. It handles authentication,
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
    ) -> dict:
        """
        Generate an image using the OpenAI GPT-5.1 Responses API.

        This method creates an image generation request with the OpenAI API,
        incorporating style parameters like medium and aesthetic into the prompt.

        Args:
            prompt (str): The image generation prompt describing what to create.
            medium (str, optional): The artistic medium (e.g., "digital", "watercolor").
            aesthetic (str, optional): The aesthetic style (e.g., "surrealist", "minimalist").

        Returns:
            dict: A dictionary containing either:
                  - Success: {"image_url": "data:image/png;base64,...", "prompt_used": "prompt", ...}
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

            response = client.responses.create(
                model="gpt-5.1",
                input=prompt,
                tools=[{"type": "image_generation"}],
            )

            # Extract the base64-encoded image data
            image_data = [
                output.result
                for output in response.output
                if output.type == "image_generation_call"
            ]

            if image_data:
                image_base64 = image_data[0]
                # Return as data URL for direct use in img tags
                image_url = f"data:image/png;base64,{image_base64}"

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

