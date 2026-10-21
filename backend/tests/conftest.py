import zlib

import pytest
from langchain_core.embeddings import Embeddings

from rag_chatbot import retriever


class FakeEmbeddings(Embeddings):
    """Tiny bag-of-words embeddings so tests run fast, offline and without an API key."""

    def _vector(self, text):
        values = [0.0] * 64
        for word in text.lower().split():
            values[zlib.crc32(word.encode()) % 64] += 1
        norm = sum(v * v for v in values) ** 0.5 or 1.0
        return [v / norm for v in values]

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


@pytest.fixture
def fake_embeddings():
    return FakeEmbeddings()


@pytest.fixture(autouse=True)
def _use_fake_embeddings(monkeypatch, fake_embeddings):
    monkeypatch.setattr(retriever, "_embeddings", fake_embeddings)
