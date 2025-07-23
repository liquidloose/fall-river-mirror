from typing import Union
import os
import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from xai_sdk import Client
from xai_sdk.chat import user, system


app = FastAPI()


@app.get("/")
def read_root():
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        return JSONResponse(
            status_code=500,
            content={"error": "XAI_API_KEY environment variable is not set"},
        )

    try:
        client = Client(api_key=api_key, timeout=3600)
        chat = client.chat.create(model="grok-4")
        chat.append(system("You are Grok, a highly intelligent, helpful AI assistant."))
        chat.append(user("What is the meaning of life, the universe, and everything?"))
        response = chat.sample()

        # The response.content is already a string, not an object with .text
        return {"response": response.content}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get response from xAI: {str(e)}"},
        )


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):

    return {"item_id": item_id, "q": q}


from datetime import datetime


@app.get("/experiments/")
def experiments():
    response = JSONResponse(
        content={"message": "YEAAAA  asdasfasfasfBOOYYYYEEEEE"},
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
    return response
