import pytest
import youtube_transcript_api

from rag_chatbot import transcript
from rag_chatbot.transcript import BLOCKED_MESSAGE, TranscriptError, fetch_transcript


class Snippet:
    def __init__(self, text, start):
        self.text, self.start = text, start


def install_fake_api(monkeypatch, fetch=None, list_=None):
    class FakeApi:
        def __init__(self, proxy_config=None):
            self.proxy_config = proxy_config

        def fetch(self, video_id, languages=("en",)):
            return fetch(video_id, languages)

        def list(self, video_id):
            return list_(video_id)

    monkeypatch.setattr(youtube_transcript_api, "YouTubeTranscriptApi", FakeApi)
    monkeypatch.setattr(transcript, "TRANSCRIPT_PROXY_URL", "")


def test_success_returns_segments(monkeypatch):
    install_fake_api(monkeypatch, fetch=lambda v, l: [Snippet("hello", 1.5), Snippet("  ", 2.0)])
    segments = fetch_transcript("dQw4w9WgXcQ")
    assert [(s.text, s.start) for s in segments] == [("hello", 1.5)]


def test_ip_block_gives_a_clear_message(monkeypatch):
    class IpBlocked(Exception):
        pass

    def blocked(*_args):
        raise IpBlocked()

    install_fake_api(monkeypatch, fetch=blocked, list_=blocked)
    with pytest.raises(TranscriptError) as info:
        fetch_transcript("dQw4w9WgXcQ")
    assert str(info.value) == BLOCKED_MESSAGE
    assert "VPN" in str(info.value)


def test_falls_back_to_any_available_language(monkeypatch):
    class Track:
        def fetch(self):
            return [Snippet("namaste", 0.0)]

    def preferred_missing(*_args):
        raise ValueError("no preferred language")

    install_fake_api(monkeypatch, fetch=preferred_missing, list_=lambda v: iter([Track()]))
    assert fetch_transcript("dQw4w9WgXcQ")[0].text == "namaste"


def test_captions_disabled_message(monkeypatch):
    class TranscriptsDisabled(Exception):
        pass

    def disabled(*_args):
        raise TranscriptsDisabled()

    install_fake_api(monkeypatch, fetch=disabled, list_=disabled)
    with pytest.raises(TranscriptError, match="turned captions off"):
        fetch_transcript("dQw4w9WgXcQ")


def test_unknown_error_mentions_its_type(monkeypatch):
    def boom(*_args):
        raise KeyError("x")

    install_fake_api(monkeypatch, fetch=boom, list_=boom)
    with pytest.raises(TranscriptError, match="KeyError"):
        fetch_transcript("dQw4w9WgXcQ")
