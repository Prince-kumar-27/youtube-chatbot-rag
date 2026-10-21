import pytest

from rag_chatbot.models import Chunk
from rag_chatbot.retriever import Retriever

CHUNKS = [
    Chunk("gradient descent updates the weights using the loss gradient", 10.0),
    Chunk("the speaker talks about his favourite pizza toppings", 95.0),
    Chunk("a neural network has layers of connected neurons", 200.0),
]


def test_search_returns_most_relevant_chunk_first(fake_embeddings):
    retriever = Retriever(CHUNKS, embeddings=fake_embeddings)
    results = retriever.search("how does gradient descent update weights", k=2)
    assert results[0].start == 10.0
    assert results[0].score >= results[1].score


def test_k_is_capped_at_number_of_chunks():
    assert len(Retriever(CHUNKS).search("anything", k=10)) == len(CHUNKS)


def test_empty_chunks_raise():
    with pytest.raises(ValueError):
        Retriever([])


def test_missing_api_key_gives_clear_error(monkeypatch):
    from rag_chatbot import retriever as retriever_module

    monkeypatch.setattr(retriever_module, "_embeddings", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        retriever_module.get_embeddings()
