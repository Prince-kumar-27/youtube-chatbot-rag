"""In-memory store of prepared videos (so follow-up questions reuse the index)."""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from .models import Segment
from .retriever import Retriever


@dataclass
class VideoEntry:
    segments: list[Segment]
    retriever: Retriever
    transcript_source: str  # "extension" or "backend"
    summary: Optional[str] = None


class VideoStore:
    """Keeps the most recently used videos and drops the oldest ones."""

    def __init__(self, max_items: int = 20):
        self.max_items = max_items
        self._items: "OrderedDict[str, VideoEntry]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, video_id: str) -> Optional[VideoEntry]:
        with self._lock:
            entry = self._items.get(video_id)
            if entry is not None:
                self._items.move_to_end(video_id)
            return entry

    def put(self, video_id: str, entry: VideoEntry) -> None:
        with self._lock:
            self._items[video_id] = entry
            self._items.move_to_end(video_id)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)
