from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class InferenceSettingsStore:
    """Atomically persists the last successfully loaded inference runtime selection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any] | None:
        with self._lock:
            if not self.path.is_file():
                return None
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        settings = payload.get("settings") if isinstance(payload, dict) else None
        return dict(settings) if isinstance(settings, dict) else None

    def save(self, settings: dict[str, Any]) -> None:
        payload = {"schema_version": 1, "settings": settings}
        temporary = self.path.with_suffix(".tmp")
        with self._lock:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(self.path)
