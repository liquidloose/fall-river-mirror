from typing import Union
import os
import requests
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    xai_api_key = os.getenv("XAI_API_KEY")
    url = "http://192.168.1.17:9004/wp-json/fr-mirror/v2/create-article"

    payload = "title=THIS%20IS%20RONALD&content=%3Cdiv%3E%20Hello%2C%20worlllllld!%20%3C%2Fdiv%3E&status=draft"
    headers = {
        "Authorization": f"Bearer {xai_api_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.text)

    return {"response": response.text}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):

    return {"item_id": item_id, "q": q}
