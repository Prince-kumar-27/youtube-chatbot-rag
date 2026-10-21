"""Server-side fallback for fetching captions.

The extension normally sends the transcript itself (read in the user's browser). This module is
used only when it could not, so a video still works whenever captions exist.
"""
from __future__ import annotations

from .config import TRANSCRIPT_LANGUAGES, TRANSCRIPT_PROXY_URL
from .models import Segment


class TranscriptError(Exception):
    """Raised when no transcript could be fetched for a video."""


BLOCKED_MESSAGE = (
    "YouTube is blocking this server's IP address, and the extension could not read the "
    "transcript in your browser either. Turn off any VPN or try another network. You can also "
    "turn on captions (CC) in the player, or open the transcript under the video "
    "(description > Show transcript), then ask again."
)

# Library exception name -> message we show to the user
FRIENDLY_ERRORS = {
    "IpBlocked": BLOCKED_MESSAGE,
    "RequestBlocked": BLOCKED_MESSAGE,
    "PoTokenRequired": BLOCKED_MESSAGE,
    "TranscriptsDisabled": "The owner of this video has turned captions off.",
    "NoTranscriptFound": "This video has no captions in a supported language.",
    "VideoUnavailable": "This video is unavailable.",
    "VideoUnplayable": "This video cannot be played, so no transcript is available.",
    "AgeRestricted": "This video is age-restricted, so its transcript cannot be fetched.",
}


def _make_api():
    from youtube_transcript_api import YouTubeTranscriptApi

    if TRANSCRIPT_PROXY_URL:
        from youtube_transcript_api.proxies import GenericProxyConfig

        proxy = GenericProxyConfig(http_url=TRANSCRIPT_PROXY_URL, https_url=TRANSCRIPT_PROXY_URL)
        return YouTubeTranscriptApi(proxy_config=proxy)
    return YouTubeTranscriptApi()


def fetch_transcript(video_id: str, languages=TRANSCRIPT_LANGUAGES) -> list[Segment]:
    api = _make_api()
    try:
        try:
            fetched = api.fetch(video_id, languages=list(languages))
        except Exception:
            # Preferred languages missing: take whichever transcript the video has
            fetched = next(iter(api.list(video_id))).fetch()
    except Exception as exc:
        name = type(exc).__name__
        message = FRIENDLY_ERRORS.get(name) or (
            f"Could not get a transcript for this video ({name}). It may have no captions."
        )
        raise TranscriptError(message) from exc

    segments = [Segment(text=s.text, start=float(s.start)) for s in fetched if s.text.strip()]
    if not segments:
        raise TranscriptError("The transcript for this video is empty.")
    return segments
