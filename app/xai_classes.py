import os
from enum import Enum
from fastapi.responses import JSONResponse
from xai_sdk import Client
from xai_sdk.chat import user, system
from .utils import read_context_file


class ArticleType(str, Enum):
    SUMMARY = "summary"
    OP_ED = "op-ed"


class Tone(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"


class XAIProcessor:
    def __init__(self):
        self.api_key = os.getenv("XAI_API_KEY")

    def get_response(self, context: str, message: str):
        if not self.api_key:
            return JSONResponse(
                status_code=500,
                content={"error": "XAI_API_KEY environment variable is not set"},
            )

        try:
            client = Client(api_key=self.api_key, timeout=3600)
            chat = client.chat.create(model="grok-4")
            chat.append(system(context))
            chat.append(user(message))
            response = chat.sample()
            # The response.content is already a string, not an object with .text
            return {"response": response.content}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to get response from xAI: {str(e)}"},
            )
