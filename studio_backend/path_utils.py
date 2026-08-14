from __future__ import annotations

import re


def safe_stem(value: str, fallback: str = "irodori-project") -> str:
    """Return a human-readable filename stem without path punctuation."""
    cleaned = re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠々ー_-]+", "-", value.strip())
    cleaned = cleaned.strip("-_.")
    return cleaned[:80] or fallback
