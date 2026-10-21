"""Small helpers."""


def format_timestamp(seconds: float) -> str:
    """75 -> '01:15', 3725 -> '1:02:05'."""
    total = max(int(seconds), 0)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
