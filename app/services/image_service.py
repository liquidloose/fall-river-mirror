"""
Image utility service: decode image data from base64 data URLs or HTTP URLs.
"""

import base64
from typing import Optional

import requests
from fastapi import HTTPException, status


class ImageService:
    """
    Decodes image data from either a base64 data URL or a regular HTTP URL.
    """

    def decode_url(self, image_url: str) -> bytes:
        """
        Decode image data from either a base64 data URL or a regular URL.

        Args:
            image_url: Either a base64 data URL (data:image/...) or HTTP URL

        Returns:
            bytes: The raw image data

        Raises:
            HTTPException: If URL download fails
        """
        if image_url.startswith("data:image"):
            header, base64_data = image_url.split(",", 1)
            return base64.b64decode(base64_data)
        response = requests.get(image_url)
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to download image: {response.status_code}",
            )
        return response.content
