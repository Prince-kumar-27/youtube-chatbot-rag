"""Summaries of long videos using map-reduce.

A long video does not fit in one prompt, so we (1) split the transcript into batches,
(2) take notes on each batch, and (3) combine the notes into one final summary.
"""
from __future__ import annotations

from .config import (
    FINAL_PROMPT, MAP_PROMPT, SUMMARY_BATCH_CHARS, SUMMARY_MAX_ROUNDS, SUMMARY_MAX_TOKENS,
)
from .llm import complete
from .models import Segment
from .utils import format_timestamp


def segments_to_lines(segments: list[Segment], line_chars: int = 250) -> list[str]:
    """Merge short caption segments into readable lines that start with a timestamp."""
    lines: list[str] = []
    parts: list[str] = []
    length = 0
    start = 0.0
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if not parts:
            start = seg.start
        parts.append(text)
        length += len(text) + 1
        if length >= line_chars:
            lines.append(f"[{format_timestamp(start)}] {' '.join(parts)}")
            parts, length = [], 0
    if parts:
        lines.append(f"[{format_timestamp(start)}] {' '.join(parts)}")
    return lines


def batch_lines(lines: list[str], max_chars: int) -> list[str]:
    """Group lines into batches of at most about `max_chars` characters."""
    batches: list[str] = []
    current: list[str] = []
    size = 0
    for line in lines:
        if current and size + len(line) + 1 > max_chars:
            batches.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        batches.append("\n".join(current))
    return batches


def summarize(segments: list[Segment], complete_fn=complete,
              batch_chars: int = SUMMARY_BATCH_CHARS) -> str:
    lines = segments_to_lines(segments)
    if not lines:
        raise ValueError("Transcript is empty.")

    batches = batch_lines(lines, batch_chars)
    rounds = 0
    while len(batches) > 1 and rounds < SUMMARY_MAX_ROUNDS:
        notes = [complete_fn(MAP_PROMPT, batch, SUMMARY_MAX_TOKENS) for batch in batches]
        batches = batch_lines(notes, batch_chars)
        rounds += 1

    return complete_fn(FINAL_PROMPT, "\n\n".join(batches), SUMMARY_MAX_TOKENS)
