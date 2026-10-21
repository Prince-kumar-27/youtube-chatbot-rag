"""FastAPI server used by the Chrome extension.

Run from the backend folder:
    uvicorn rag_chatbot.api:app --app-dir src --reload
"""

from __future__ import annotations

import hmac
import logging
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config
from .chunking import chunk_transcript
from .errors import explain_ai_error
from .generator import answer_question
from .models import Segment
from .retriever import Retriever
from .store import VideoEntry, VideoStore
from .summarizer import summarize
from .transcript import TranscriptError, fetch_transcript
from .utils import format_timestamp

logger = logging.getLogger("rag_chatbot")
VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]{11}$"

store = VideoStore(config.MAX_VIDEOS_IN_MEMORY)


app = FastAPI(title="YouTube RAG API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------- Request / response models ----------
class SegmentIn(BaseModel):
    text: str = Field(max_length=2000)
    start: float = Field(ge=0)


class PrepareRequest(BaseModel):
    video_id: str = Field(pattern=VIDEO_ID_PATTERN)
    # Transcript read in the user's browser. If missing, the server tries to fetch it itself.
    segments: Optional[List[SegmentIn]] = Field(default=None, max_length=50000)


class VideoRequest(BaseModel):
    video_id: str = Field(pattern=VIDEO_ID_PATTERN)


class AskRequest(VideoRequest):
    question: str = Field(min_length=1, max_length=1000)


class PrepareResponse(BaseModel):
    video_id: str
    chunk_count: int
    transcript_source: str
    cached: bool


class SummaryResponse(BaseModel):
    summary: str


class SourceOut(BaseModel):
    start: float
    timestamp: str
    text: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceOut]


# ---------- Helpers ----------
def check_token(x_api_token: Optional[str] = Header(default=None)) -> None:
    """If EXTENSION_TOKEN is set, every request must send it (stops strangers using your API key)."""
    expected = config.EXTENSION_TOKEN
    if expected and not hmac.compare_digest(x_api_token or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API token.")


def get_entry(video_id: str) -> VideoEntry:
    entry = store.get(video_id)
    if entry is None:
        # The extension looks for this exact text and re-sends the transcript
        raise HTTPException(status_code=404, detail="video_not_prepared")
    return entry


def llm_call(fn, *args):
    """Run an LLM-backed function and turn failures into clean HTTP errors."""
    try:
        return fn(*args)
    except RuntimeError as exc:  # e.g. missing API key
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        logger.exception("LLM call failed")
        raise HTTPException(status_code=502, detail="The AI service failed. Please try again.")


# ---------- Routes --------------------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "videos_in_memory": len(store)}


@app.post("/videos/prepare", response_model=PrepareResponse, dependencies=[Depends(check_token)])
def prepare(req: PrepareRequest):
    existing = store.get(req.video_id)
    if existing:
        return PrepareResponse(
            video_id=req.video_id,
            chunk_count=len(existing.retriever.chunks),
            transcript_source=existing.transcript_source,
            cached=True,
        )

    source = "extension"
    segments = [Segment(s.text.strip(), s.start) for s in (req.segments or []) if s.text.strip()]
    if not segments:
        source = "backend"
        try:
            segments = fetch_transcript(req.video_id)
        except TranscriptError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    chunks = chunk_transcript(segments, config.DEFAULT_CHUNK_SIZE, config.DEFAULT_OVERLAP)
    if not chunks:
        raise HTTPException(status_code=422, detail="The transcript is empty.")

    retriever = llm_call(Retriever, chunks)  # calls the embeddings API
    store.put(req.video_id, VideoEntry(segments, retriever, source))
    return PrepareResponse(
        video_id=req.video_id, chunk_count=len(chunks), transcript_source=source, cached=False
    )


@app.post("/videos/summary", response_model=SummaryResponse, dependencies=[Depends(check_token)])
def video_summary(req: VideoRequest):
    entry = get_entry(req.video_id)
    if entry.summary is None:
        entry.summary = llm_call(summarize, entry.segments)
    return SummaryResponse(summary=entry.summary)


@app.post("/videos/ask", response_model=AskResponse, dependencies=[Depends(check_token)])
def ask(req: AskRequest):
    entry = get_entry(req.video_id)
    result = llm_call(answer_question, entry.retriever, req.question.strip(), config.DEFAULT_TOP_K)
    sources = [
        SourceOut(
            start=c.start,
            timestamp=format_timestamp(c.start),
            text=c.text[:300],
            score=round(c.score, 3),
        )
        for c in result.sources
    ]
    return AskResponse(answer=result.text, sources=sources)
