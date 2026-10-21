"""Small data classes shared across the pipeline."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    text: str
    start: float  # seconds from the start of the video


@dataclass(frozen=True)
class Chunk:
    text: str
    start: float  # start time of the first segment in the chunk
    score: float = 0.0  # similarity score, filled in by the retriever
