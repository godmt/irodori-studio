from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from studio_backend.exporter import safe_stem


class ProjectStore:
    """Atomic, server-owned persistence for Studio projects."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, name: str) -> Path:
        return self.directory / f"{safe_stem(name)}.json"

    def _write(self, path: Path, project: dict[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

    def list(self) -> list[dict[str, Any]]:
        projects = []
        with self._lock:
            paths = sorted(
                self.directory.glob("*.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            for path in paths:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    payload = {}
                projects.append(
                    {
                        "name": str(payload.get("title") or path.stem),
                        "storage_name": path.stem,
                        "filename": path.name,
                        "updated_at": path.stat().st_mtime,
                    }
                )
        return projects

    def load(self, name: str) -> dict[str, Any]:
        path = self._path(name)
        with self._lock:
            if not path.is_file():
                raise KeyError(name)
            return json.loads(path.read_text(encoding="utf-8"))

    def create(self, name: str, project: dict[str, Any]) -> dict[str, Any]:
        path = self._path(name)
        with self._lock:
            if path.exists():
                raise FileExistsError(path.stem)
            self._write(path, project)
        return {"saved": True, "name": path.stem}

    def save(self, name: str, project: dict[str, Any]) -> dict[str, Any]:
        path = self._path(name)
        with self._lock:
            self._write(path, project)
        return {"saved": True, "name": path.stem}

    def delete(self, name: str) -> None:
        path = self._path(name)
        with self._lock:
            if not path.is_file():
                raise KeyError(name)
            path.unlink()
