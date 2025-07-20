from typing import Union
import os
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    x = 5555555555555555555555555555555555555555555555555555555
    xai_api_key = os.getenv("XAI_API_KEY")
    return {"XAI_API_KEY": f"{xai_api_key}"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):

    return {"item_id": item_id, "q": q}
