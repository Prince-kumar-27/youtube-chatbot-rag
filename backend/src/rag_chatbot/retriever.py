"""Step 2: embed chunks, store them in a FAISS vector store (LangChain), and search by meaning."""
from __future__ import annotations

import os

from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document

from .config import EMBED_MODEL, PROVIDER
from .models import Chunk

_embeddings = None


def get_embeddings():
    """Create the embedding client once (lazy, so tests never need an API key)."""
    global _embeddings
    if _embeddings is None:
        if PROVIDER == "gemini":
            key = os.getenv("GOOGLE_API_KEY")
            if not key:
                from .llm import GEMINI_KEY_HELP

                raise RuntimeError(GEMINI_KEY_HELP)
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            _embeddings = GoogleGenerativeAIEmbeddings(model=f"models/{EMBED_MODEL}", google_api_key=key)
        else:
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY not found. Copy .env.example to .env and add your key.")
            from langchain_openai import OpenAIEmbeddings

            _embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
    return _embeddings


class Retriever:
    def __init__(self, chunks: list[Chunk], embeddings=None):
        if not chunks:
            raise ValueError("No transcript text to index.")
        self.chunks = chunks
        documents = [Document(page_content=c.text, metadata={"start": c.start}) for c in chunks]
        # Embeddings have length 1, so inner product == cosine similarity (higher = closer)
        self.vector_store = FAISS.from_documents(
            documents,
            embeddings or get_embeddings(),
            distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
        )

    def search(self, question: str, k: int = 4) -> list[Chunk]:
        """Return the k chunks most similar in meaning to the question."""
        k = min(k, len(self.chunks))
        results = self.vector_store.similarity_search_with_score(question, k=k)
        return [
            Chunk(text=doc.page_content, start=doc.metadata["start"], score=float(score))
            for doc, score in results
        ]