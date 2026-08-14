from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> str:
    """Return the current UTC timestamp in the persistent ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()
