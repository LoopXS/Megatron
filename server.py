import uvicorn
import os
import requests
import json
import base64
import re
import logging
from pydantic import BaseModel
from typing import Union, Annotated, Optional, List, Dict, Any
from base64 import b64decode
from gpytranslate import SyncTranslator

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Response, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.ERROR)

app = FastAPI()

app.mount("/", StaticFiles(directory="static", html=True), name="static")

class SuccessResponse(BaseModel):
    status: str
    rootx: Dict[str, Any]

class ErrorResponse(BaseModel):
    status: str
    detail: str

class ErrorStatus(BaseModel):
    status: str
    message: str

class ChatBots(BaseModel):
    query: str
    user_id: Optional[int] = None
    bot_name: Optional[str] = None
    bot_username: Optional[str] = None

class TranslateCustom(BaseModel):
    text: str
    setlang: str

@app.get("/")
def index() -> FileResponse:
    return FileResponse(path="/Megatron/static/index.html", media_type="text/html")

@app.get("/rootx/chatbot", response_model=SuccessResponse, responses={422: {"model": ErrorStatus}})
def chatbot(item: ChatBots):
    api_url = b64decode("aHR0cHM6Ly9hcGkuc2Fmb25lLmRldi9jaGF0Ym90").decode("utf-8")
    params = {
        "query": item.query,
        "user_id": item.user_id,
        "bot_name": item.bot_name,
        "bot_master": item.bot_username
    }
    x = requests.get(f"{api_url}", params=params)
    if x.status_code != 200:
        return "Error api request"
    try:
        y = x.json()
        response = y["response"]
        return SuccessResponse( 
            status="True",
            rootx={"message": response})
    except:
        return {"status": "false", "message": "Error response."}
        
@app.get("/rootx/translate", response_model=SuccessResponse, responses={422: {"model": ErrorStatus}})
def get_translate(
    item: TranslateCustom,
):
    trans = SyncTranslator()
    try:
        source = trans.detect(item.text)
        translation = trans(item.text, sourcelang=source, targetlang=item.setlang)
        return SuccessResponse(
            status="True",
            rootx={
                "translation": translation.text,
                "translation_original": item.text
            }
        )
    except:
        return SuccessResponse(
            status="True",
            rootx={"message": "Error not responding"})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
