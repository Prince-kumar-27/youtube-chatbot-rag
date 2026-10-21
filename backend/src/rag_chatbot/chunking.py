"""Step 1: group transcript segments into overlapping, timestamped chunks."""
from __future__ import annotations

import re

from .config import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from .models import Chunk, Segment


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _to_chunk(buffer: list[Segment]) -> Chunk:
    return Chunk(text=" ".join(s.text for s in buffer), start=buffer[0].start)


def _overlap_tail(buffer: list[Segment], overlap: int) -> tuple[list[Segment], int]:
    """Keep the last few segments (up to `overlap` characters) to start the next chunk."""
    tail: list[Segment] = []
    length = 0
    for seg in reversed(buffer):
        if length + len(seg.text) + 1 > overlap:
            break
        tail.insert(0, seg)
        length += len(seg.text) + 1
    return tail, length


def chunk_transcript(
    segments: list[Segment],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Combine consecutive segments until a chunk reaches `chunk_size` characters.

    Whole segments are never cut in half, and each chunk remembers the time at which it starts,
    so answers can point to the right moment in the video.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    chunks: list[Chunk] = []
    buffer: list[Segment] = []
    length = 0
    fresh = 0  # segments added since the last chunk was emitted

    for seg in segments:
        text = _clean(seg.text)
        if not text:
            continue
        buffer.append(Segment(text, seg.start))
        length += len(text) + 1
        fresh += 1
        if length >= chunk_size:
            chunks.append(_to_chunk(buffer))
            buffer, length = _overlap_tail(buffer, overlap)
            fresh = 0

    if fresh:
        chunks.append(_to_chunk(buffer))
    return chunks
