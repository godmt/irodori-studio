from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from studio_backend.exporter import safe_stem


def project_audio_files(project: dict[str, Any] | None) -> set[str]:
    """Return safe generated WAV basenames referenced by a project."""
    audio_files: set[str] = set()
    if not isinstance(project, dict):
        return audio_files
    for line in project.get("lines", []):
        if not isinstance(line, dict):
            continue
        candidates = [line.get("audioFile")]
        candidates.extend(
            take.get("audioFile")
            for take in line.get("takes", [])
            if isinstance(take, dict)
        )
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            name = Path(candidate).name
            if name == candidate and Path(name).suffix.lower() == ".wav":
                audio_files.add(name)
    return audio_files


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

    def rename(self, current_name: str, new_name: str) -> dict[str, Any]:
        current_path = self._path(current_name)
        target_path = self._path(new_name)
        with self._lock:
            if not current_path.is_file():
                raise KeyError(current_name)
            if target_path != current_path and target_path.exists():
                raise FileExistsError(target_path.stem)
            project = json.loads(current_path.read_text(encoding="utf-8"))
            project["title"] = new_name.strip()
            if target_path == current_path:
                self._write(current_path, project)
            else:
                self._write(target_path, project)
                current_path.unlink()
        return {"renamed": True, "name": target_path.stem, "project": project}

    def delete(self, name: str) -> dict[str, Any]:
        path = self._path(name)
        with self._lock:
            if not path.is_file():
                raise KeyError(name)
            try:
                project = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                project = {}
            path.unlink()
        return project

    def referenced_audio_files(self, *, exclude_name: str | None = None) -> set[str]:
        """Return audio still owned by saved projects other than an optional project."""
        excluded_path = self._path(exclude_name) if exclude_name else None
        referenced: set[str] = set()
        with self._lock:
            for path in self.directory.glob("*.json"):
                if excluded_path is not None and path == excluded_path:
                    continue
                try:
                    project = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                referenced.update(project_audio_files(project))
        return referenced
