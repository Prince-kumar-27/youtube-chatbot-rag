import pytest

from rag_chatbot import config
from rag_chatbot.models import Segment
from rag_chatbot.summarizer import batch_lines, segments_to_lines, summarize


def make_segments(n):
    return [Segment("word " * 10, i * 4.0) for i in range(n)]


def test_lines_start_with_timestamps():
    lines = segments_to_lines(make_segments(30), line_chars=100)
    assert lines[0].startswith("[00:00]")
    assert all(line.startswith("[") for line in lines)


def test_batches_respect_max_size():
    lines = ["x" * 100] * 10
    assert all(len(b) <= 250 for b in batch_lines(lines, max_chars=250))


def test_short_video_needs_one_call():
    calls = []

    def fake(system, user, *_):
        calls.append(system)
        return "summary"

    assert summarize(make_segments(5), complete_fn=fake) == "summary"
    assert calls == [config.FINAL_PROMPT]


def test_long_video_uses_map_reduce():
    calls = []

    def fake(system, user, *_):
        calls.append(system)
        return "note"

    summarize(make_segments(200), complete_fn=fake, batch_chars=600)
    assert calls[-1] == config.FINAL_PROMPT
    assert calls.count(config.MAP_PROMPT) >= 2
    assert calls.count(config.FINAL_PROMPT) == 1


def test_empty_transcript_raises():
    with pytest.raises(ValueError):
        summarize([], complete_fn=lambda *a: "x")
