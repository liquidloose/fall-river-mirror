from datetime import datetime
from enum import Enum
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi
from .utils import XAIProcessor, ArticleType, Tone

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler("app.log"),  # File output
    ],
)
logger = logging.getLogger(__name__)

app = FastAPI()
xai_processor = XAIProcessor()

logger.info("FastAPI app initialized!")


@app.get("/")
def health_check():
    logger.info("Health check endpoint called!")
    return {"status": "ok", "message": "Server is running"}


@app.get("/article/writer/{context}/{prompt}")
def read_root(
    context: str,
    prompt: str,
    article_type: ArticleType = ArticleType.SUMMARY,
    tone: Tone = Tone.FORMAL,
):
    logger.info(
        f"Received request: context={context}, prompt={prompt}, type={article_type}, tone={tone}"
    )
    xai_processor = XAIProcessor()
    full_prompt = f"Write a {article_type.value} article in {tone.value} tone. Context: {context}. Prompt: {prompt}"
    logger.debug(f"Full prompt: {full_prompt}")
    response = xai_processor.get_response(context, full_prompt)
    logger.debug(f"Response: {response}")
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
