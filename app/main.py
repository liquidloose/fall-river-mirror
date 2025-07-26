from datetime import datetime
from enum import Enum
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi
from .utils import XAIProcessor, ArticleType, Tone


app = FastAPI()
xai_processor = XAIProcessor()


@app.get("/article/writer/{context}/{prompt}")
def read_root(
    context: str,
    prompt: str,
    article_type: ArticleType = ArticleType.SUMMARY,
    tone: Tone = Tone.FORMAL,
):
    print(
        f"Received request: context={context}, prompt={prompt}, type={article_type}, tone={tone}"
    )
    xai_processor = XAIProcessor()
    full_prompt = f"Write a {article_type.value} article in {tone.value} tone. Context: {context}. Prompt: {prompt}"
    print(f"Full prompt: {full_prompt}")
    response = xai_processor.get_response(full_prompt)
    print(f"Response: {response}")
    return response


@app.get("/experiments/")
def get_transcript(video_id: str = "VjaU4DAxP6s"):

    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get transcript from YouTube: {str(e)}"},
        )

    return transcript
