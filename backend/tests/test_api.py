import pytest
from fastapi.testclient import TestClient

from rag_chatbot import api, config
from rag_chatbot.generator import Answer
from rag_chatbot.models import Chunk, Segment
from rag_chatbot.store import VideoStore
from rag_chatbot.transcript import TranscriptError

VIDEO = "dQw4w9WgXcQ"
SEGMENTS = [{"text": f"this part explains topic number {i} in some detail", "start": i * 6.0}
            for i in range(60)]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "store", VideoStore(5))
    monkeypatch.setattr(config, "EXTENSION_TOKEN", "")
    return TestClient(api.app)  # no "with": skips the startup model download


def prepare(client, **extra):
    return client.post("/videos/prepare", json={"video_id": VIDEO, "segments": SEGMENTS, **extra})


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_prepare_with_transcript_from_extension(client):
    body = prepare(client).json()
    assert body["transcript_source"] == "extension"
    assert body["chunk_count"] > 0 and body["cached"] is False


def test_prepare_twice_uses_cache(client):
    prepare(client)
    assert prepare(client).json()["cached"] is True


def test_prepare_falls_back_to_server_transcript(client, monkeypatch):
    monkeypatch.setattr(api, "fetch_transcript",
                        lambda vid: [Segment("hello from the server fallback", 0.0)])
    resp = client.post("/videos/prepare", json={"video_id": VIDEO})
    assert resp.status_code == 200 and resp.json()["transcript_source"] == "backend"


def test_prepare_without_any_captions_returns_404(client, monkeypatch):
    def boom(_vid):
        raise TranscriptError("no captions")

    monkeypatch.setattr(api, "fetch_transcript", boom)
    resp = client.post("/videos/prepare", json={"video_id": VIDEO})
    assert resp.status_code == 404 and "no captions" in resp.json()["detail"]


def test_invalid_video_id_is_rejected(client):
    assert client.post("/videos/prepare", json={"video_id": "bad id!"}).status_code == 422


def test_ask_before_prepare_returns_video_not_prepared(client):
    resp = client.post("/videos/ask", json={"video_id": VIDEO, "question": "hi"})
    assert resp.status_code == 404 and resp.json()["detail"] == "video_not_prepared"


def test_ask_returns_answer_and_timestamped_sources(client, monkeypatch):
    prepare(client)
    monkeypatch.setattr(api, "answer_question",
                        lambda retriever, q, k: Answer("It is explained at [01:05].",
                                                       [Chunk("some text", 65.0, 0.9)]))
    body = client.post("/videos/ask", json={"video_id": VIDEO, "question": "what?"}).json()
    assert body["answer"].startswith("It is explained")
    assert body["sources"][0]["timestamp"] == "01:05"


def test_summary_is_cached(client, monkeypatch):
    prepare(client)
    calls = []
    monkeypatch.setattr(api, "summarize", lambda segs: calls.append(1) or "the summary")
    for _ in range(2):
        assert client.post("/videos/summary", json={"video_id": VIDEO}).json()["summary"] == "the summary"
    assert len(calls) == 1


def test_llm_failure_becomes_502(client, monkeypatch):
    prepare(client)

    def boom(*_args):
        raise ValueError("provider exploded")

    monkeypatch.setattr(api, "answer_question", boom)
    resp = client.post("/videos/ask", json={"video_id": VIDEO, "question": "what?"})
    assert resp.status_code == 502


def test_token_is_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(config, "EXTENSION_TOKEN", "secret")
    assert prepare(client).status_code == 401
    ok = client.post("/videos/prepare", headers={"X-Api-Token": "secret"},
                     json={"video_id": VIDEO, "segments": SEGMENTS})
    assert ok.status_code == 200
