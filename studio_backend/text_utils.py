from __future__ import annotations

import re
import unicodedata


def normalize_training_text(text: str) -> str:
    """Return the canonical text persisted for Studio training datasets."""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    japanese = r"\u3040-\u30ff\u3400-\u9fff\u3000-\u303f"
    return re.sub(rf"(?<=[{japanese}]) (?=[{japanese}])", "", normalized)
