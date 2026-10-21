from rag_chatbot.models import Chunk
from rag_chatbot.retriever import Retriever
from rag_chatbot.store import VideoEntry, VideoStore


def entry():
    return VideoEntry([], Retriever([Chunk("some text", 0.0)]), "extension")


def test_get_returns_none_for_unknown_video():
    assert VideoStore().get("nope") is None


def test_oldest_video_is_evicted():
    store = VideoStore(max_items=2)
    store.put("a", entry())
    store.put("b", entry())
    store.put("c", entry())
    assert store.get("a") is None
    assert store.get("b") and store.get("c")


def test_recently_used_video_is_kept():
    store = VideoStore(max_items=2)
    store.put("a", entry())
    store.put("b", entry())
    store.get("a")          # touch "a" so "b" becomes the oldest
    store.put("c", entry())
    assert store.get("a") is not None
    assert store.get("b") is None
