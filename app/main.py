from typing import Union
import os
import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()


@app.get("/")
def read_root():
   

    return {"response"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):

    return {"item_id": item_id, "q": q}


from datetime import datetime


@app.get("/experiments/")
def experiments():
    response = JSONResponse(
        content={"message": "THIS IS RONALDSsSs API ENDPOINTsss  DUDEsss", "timestamp": datetime.now().isoformat()},
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
    return response
