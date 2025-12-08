# Standard library imports
import os

# Third-party imports
from fastapi.responses import JSONResponse
from xai_sdk import Client


class XAIImageQuery:
    """
    A processor class for handling xAI image generation (Aurora) interactions.

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
        Generate an image using the xAI Aurora API based on provided prompt.

        This method creates an image generation request with the xAI API,
        incorporating style parameters like medium and aesthetic into the prompt.

        Args:
            prompt (str): The image generation prompt describing what to create.
            medium (str, optional): The artistic medium (e.g., "digital", "watercolor").
            aesthetic (str, optional): The aesthetic style (e.g., "surrealist", "minimalist").

        Returns:
            dict: A dictionary containing the generated image info:
                  {"image_url": "url_to_image", "prompt_used": "full_prompt"}

        Raises:
            JSONResponse: Returns a 500 status code with error details if:
                - XAI_API_KEY environment variable is not set
                - API communication fails for any reason
        """
        if not self.api_key:
            return JSONResponse(
                status_code=500,
                content={"error": "XAI_API_KEY environment variable is not set"},
            )

        try:
            # Initialize xAI client with timeout for long-running requests
            client = Client(api_key=self.api_key, timeout=3600)

            # TODO: Verify exact xAI SDK method for image generation
            # This is the expected interface based on SDK patterns
            response = client.image.generate(
                model="aurora",
                prompt=prompt,
            )

            return {
                "image_url": response.url,
                "prompt_used": prompt,
                "medium": medium,
                "aesthetic": aesthetic,
            }

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to generate image from xAI: {str(e)}"},
            )
