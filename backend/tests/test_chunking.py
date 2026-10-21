import pytest

from rag_chatbot.chunking import chunk_transcript
from rag_chatbot.models import Segment


def make_segments(n=20):
    # each segment is 24 characters: "s00 " + 20 x's
    return [Segment(f"s{i:02d} " + "x" * 20, i * 5.0) for i in range(n)]


def test_chunk_starts_at_first_segment_time():
    chunks = chunk_transcript(make_segments(), chunk_size=100, overlap=0)
    assert chunks[0].start == 0.0
    assert chunks[1].start > chunks[0].start


def test_overlap_repeats_last_segment_in_next_chunk():
    segments = make_segments()
    chunks = chunk_transcript(segments, chunk_size=100, overlap=30)
    assert chunks[0].text.endswith(segments[3].text)
    assert chunks[1].text.startswith(segments[3].text)
    assert chunks[1].start == segments[3].start


def test_no_overlap_means_no_repeated_text():
    chunks = chunk_transcript(make_segments(8), chunk_size=100, overlap=0)
    joined = " ".join(c.text for c in chunks)
    assert joined.count("s03") == 1


def test_all_text_is_covered_and_no_duplicate_final_chunk():
    segments = make_segments(9)
    chunks = chunk_transcript(segments, chunk_size=100, overlap=0)
    assert " ".join(c.text for c in chunks) == " ".join(s.text for s in segments)


def test_whitespace_normalised_and_blank_segments_skipped():
    chunks = chunk_transcript([Segment("a   b\n c", 1.0), Segment("   ", 2.0)], 100, 0)
    assert len(chunks) == 1 and chunks[0].text == "a b c"


def test_empty_input_gives_no_chunks():
    assert chunk_transcript([], 100, 10) == []


@pytest.mark.parametrize("size,overlap", [(0, 0), (100, 100), (100, -1)])
def test_invalid_settings_raise(size, overlap):
    with pytest.raises(ValueError):
        chunk_transcript(make_segments(), size, overlap)
