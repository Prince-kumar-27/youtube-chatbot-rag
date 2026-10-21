"""Central configuration. Change settings and prompts here, not inside the pipeline code."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# --- Models (OpenAI, used through LangChain) ---
# --- Models (used through LangChain) ---
PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()  # "gemini" (free tier) or "openai"
_DEFAULT_MODELS = {
    "gemini": {"llm": "gemini-3.1-flash-lite", "embed": "gemini-embedding-001"},
    "openai": {"llm": "gpt-4o-mini", "embed": "text-embedding-3-small"},
}
if PROVIDER not in _DEFAULT_MODELS:
    raise ValueError("LLM_PROVIDER must be 'gemini' or 'openai'")
LLM_MODEL = os.getenv("LLM_MODEL", _DEFAULT_MODELS[PROVIDER]["llm"])
EMBED_MODEL = os.getenv("EMBED_MODEL", _DEFAULT_MODELS[PROVIDER]["embed"])
TEMPERATURE = 0.2  # used for OpenAI only (Google recommends the default for Gemini 3 models)
MAX_TOKENS = 600
SUMMARY_MAX_TOKENS = 900

# --- Retrieval ---
DEFAULT_CHUNK_SIZE = 800   # characters per chunk
DEFAULT_OVERLAP = 150      # characters shared between neighbouring chunks
DEFAULT_TOP_K = 4

# --- Summaries (map-reduce for long videos) ---
SUMMARY_BATCH_CHARS = 12000
SUMMARY_MAX_ROUNDS = 3

# --- Server ---
EXTENSION_TOKEN = os.getenv("EXTENSION_TOKEN", "")  # optional shared secret
MAX_VIDEOS_IN_MEMORY = 20
ALLOWED_ORIGINS = ["https://www.youtube.com"]
TRANSCRIPT_PROXY_URL = os.getenv("TRANSCRIPT_PROXY_URL", "")  # optional, e.g. http://user:pass@host:port
TRANSCRIPT_LANGUAGES = ("en", "hi")  # preferred caption languages for the server-side fallback

# --- Prompts ---
NO_ANSWER_TEXT = "This isn't covered in the video."

QA_SYSTEM_PROMPT = (
    "You answer questions about a YouTube video using ONLY the transcript excerpts provided.\n"
    "Each excerpt starts with its timestamp, like [12:45]. The transcript may be auto-generated "
    "and can contain mistakes, so use context to interpret it.\n"
    f"- If the answer is not in the excerpts, reply exactly: \"{NO_ANSWER_TEXT}\"\n"
    "- Be concise.\n"
    "- When you state something, cite the timestamp(s) where it appears, like [12:45].\n"
    "- Never invent details."
)

MAP_PROMPT = (
    "The user message is one part of a YouTube video transcript. Each line starts with a "
    "timestamp like [12:45]. Write concise bullet-point notes of the key points in this part. "
    "Keep the timestamp at the start of each bullet. Use only what the transcript says."
)

FINAL_PROMPT = (
    "You are summarizing a YouTube video from its transcript (or from notes taken on it). "
    "Timestamps look like [12:45]. Write:\n"
    "1. A short **TL;DR** of 2-3 sentences.\n"
    "2. **Key points** as bullets, each starting with the [mm:ss] timestamp where it begins.\n"
    "Be faithful to the transcript and do not add information that is not in it."
)
