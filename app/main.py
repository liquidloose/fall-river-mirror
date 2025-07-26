from datetime import datetime
from enum import Enum
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from youtube_transcript_api import YouTubeTranscriptApi

from app.utils import read_context_file
from .xai_classes import XAIProcessor, ArticleType, Tone

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

    # if article_type is op-ed, then here's op_ed.txt
    if article_type == ArticleType.OP_ED:
        final_context = context + read_context_file("article_types", "op_ed.txt")
    else:
        final_context = context

    logger.info(
        f"Received request: context={context},final_context={final_context}, prompt={prompt}, type={article_type}, tone={tone}"
    )
    xai_processor = XAIProcessor()
    full_prompt = f"This is the type of article: {article_type.value} This is the tone: {tone.value} This is the context: {context}. This is the user's prompt: {prompt}"
    logger.debug(f"Full prompt: {full_prompt}")
    response = xai_processor.get_response(final_context, full_prompt)
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
