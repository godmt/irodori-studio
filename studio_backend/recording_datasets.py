from __future__ import annotations

import json
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from studio_backend.exporter import safe_stem

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
_WINDOWS_RESERVED_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RecordingDatasetStore:
    """Server-owned recording datasets prepared for the Training workspace."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._migrate_human_readable_directories()

    def _dataset_directory(self, dataset_id: str) -> Path:
        if not _SAFE_IDENTIFIER.fullmatch(dataset_id):
            raise KeyError(dataset_id)
        for manifest in self.directory.glob("*/dataset.json"):
            try:
                dataset = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if dataset.get("id") == dataset_id:
                path = manifest.parent.resolve()
                if path.parent == self.directory:
                    return path
        raise KeyError(dataset_id)

    @staticmethod
    def _folder_stem(name: str) -> str:
        stem = safe_stem(name, "録音データセット")
        if stem.casefold() in _WINDOWS_RESERVED_NAMES:
            stem = f"{stem}-dataset"
        return stem

    def _available_directory(self, name: str, *, current: Path | None = None) -> Path:
        base = self._folder_stem(name)
        occupied = {
            child.name.casefold()
            for child in self.directory.iterdir()
            if child.is_dir() and (current is None or child.resolve() != current.resolve())
        }
        candidate = base
        number = 2
        while candidate.casefold() in occupied:
            suffix = f"-{number}"
            candidate = f"{base[: max(1, 80 - len(suffix))]}{suffix}"
            number += 1
        path = (self.directory / candidate).resolve()
        if path.parent != self.directory:
            raise ValueError("録音データセットの保存先が不正です")
        return path

    def _migrate_human_readable_directories(self) -> None:
        with self._lock:
            manifests = list(self.directory.glob("*/dataset.json"))
            for manifest in manifests:
                try:
                    dataset = json.loads(manifest.read_text(encoding="utf-8"))
                    name = str(dataset["name"]).strip()
                except (KeyError, OSError, json.JSONDecodeError, TypeError):
                    continue
                current = manifest.parent.resolve()
                target = self._available_directory(name, current=current)
                if current.name == target.name:
                    continue
                try:
                    current.rename(target)
                except OSError:
                    # The dataset remains usable by ID even when another process locks it.
                    continue

    def _validate_name(self, name: str, *, exclude_id: str | None = None) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("データセット名を入力してください")
        if len(normalized_name) > 120:
            raise ValueError("データセット名は120文字以内にしてください")
        normalized_key = normalized_name.casefold()
        for manifest in self.directory.glob("*/dataset.json"):
            try:
                dataset = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if dataset.get("id") == exclude_id:
                continue
            if str(dataset.get("name") or "").strip().casefold() == normalized_key:
                raise ValueError("同じ名前の録音データセットが既にあります")
        return normalized_name

    def dataset_directory(self, dataset_id: str) -> Path:
        directory = self._dataset_directory(dataset_id)
        if not (directory / "dataset.json").is_file():
            raise KeyError(dataset_id)
        return directory

    def _manifest_path(self, dataset_id: str) -> Path:
        return self._dataset_directory(dataset_id) / "dataset.json"

    def _read(self, dataset_id: str) -> dict[str, Any]:
        path = self._manifest_path(dataset_id)
        if not path.is_file():
            raise KeyError(dataset_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, dataset: dict[str, Any], directory: Path | None = None) -> None:
        directory = directory or self._dataset_directory(str(dataset["id"]))
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "dataset.json"
        temporary = directory / "dataset.tmp"
        temporary.write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)
        self._write_training_manifest(dataset, directory)

    def _write_training_manifest(
        self, dataset: dict[str, Any], directory: Path | None = None
    ) -> None:
        directory = directory or self._dataset_directory(str(dataset["id"]))
        rows = []
        for recording in dataset.get("recordings", {}).values():
            if not recording.get("accepted"):
                continue
            prompt = recording.get("prompt", {})
            rows.append(
                {
                    "id": recording["prompt_id"],
                    "audio": recording["audio"],
                    "text": prompt.get("text", ""),
                    "caption": prompt.get("direction", ""),
                    "category": prompt.get("category"),
                    "style": prompt.get("style"),
                    "emotion": prompt.get("emotion"),
                    "intensity": prompt.get("intensity"),
                    "source_id": prompt.get("sourceId", recording["prompt_id"]),
                    "source_name": prompt.get("sourceName"),
                    "source_url": prompt.get("sourceUrl"),
                    "source_version": prompt.get("sourceVersion"),
                    "source_license": prompt.get("license"),
                    "duration": recording.get("duration"),
                    "sample_rate": recording.get("sampleRate"),
                    "accepted_at": recording.get("acceptedAt"),
                }
            )
        rows.sort(key=lambda row: row["id"])
        content = "".join(
            f"{json.dumps(row, ensure_ascii=False, separators=(',', ':'))}\n" for row in rows
        )
        temporary = directory / "dataset.jsonl.tmp"
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(directory / "dataset.jsonl")

    @staticmethod
    def _summary(
        dataset: dict[str, Any], updated_at: float, directory_name: str
    ) -> dict[str, Any]:
        recordings = list(dataset.get("recordings", {}).values())
        accepted = [item for item in recordings if item.get("accepted")]
        return {
            "id": dataset["id"],
            "name": dataset["name"],
            "created_at": dataset.get("created_at"),
            "updated_at": updated_at,
            "recorded": len(recordings),
            "accepted": len(accepted),
            "accepted_seconds": round(
                sum(float(item.get("duration") or 0) for item in accepted), 3
            ),
            "workspace_path": f"workspace/recordings/{directory_name}",
            "training_manifest": "dataset.jsonl",
        }

    def list(self) -> list[dict[str, Any]]:
        datasets = []
        with self._lock:
            paths = sorted(
                self.directory.glob("*/dataset.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            for path in paths:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    datasets.append(
                        self._summary(payload, path.stat().st_mtime, path.parent.name)
                    )
                except (KeyError, OSError, json.JSONDecodeError, TypeError, ValueError):
                    continue
        return datasets

    def create(self, name: str) -> dict[str, Any]:
        with self._lock:
            normalized_name = self._validate_name(name)
            dataset_id = uuid4().hex
            directory = self._available_directory(normalized_name)
            created_at = _now()
            dataset = {
                "schema_version": 2,
                "id": dataset_id,
                "name": normalized_name,
                "created_at": created_at,
                "updated_at": created_at,
                "recordings": {},
            }
            directory.mkdir(parents=True, exist_ok=False)
            (directory / "wavs").mkdir()
            self._write(dataset, directory)
        return self._summary(
            dataset, (directory / "dataset.json").stat().st_mtime, directory.name
        )

    def load(self, dataset_id: str) -> dict[str, Any]:
        with self._lock:
            dataset = self._read(dataset_id)
            manifest = self._manifest_path(dataset_id)
            summary = self._summary(dataset, manifest.stat().st_mtime, manifest.parent.name)
        return {**dataset, **summary}

    def rename(self, dataset_id: str, name: str) -> dict[str, Any]:
        with self._lock:
            current = self._dataset_directory(dataset_id)
            dataset = self._read(dataset_id)
            normalized_name = self._validate_name(name, exclude_id=dataset_id)
            target = self._available_directory(normalized_name, current=current)
            previous_name = str(dataset.get("name") or "")
            moved = target != current
            if moved:
                current.rename(target)
            dataset["name"] = normalized_name
            dataset["schema_version"] = max(2, int(dataset.get("schema_version") or 1))
            dataset["updated_at"] = _now()
            try:
                self._write(dataset, target)
            except Exception:
                dataset["name"] = previous_name
                if moved and target.exists() and not current.exists():
                    target.rename(current)
                raise
            manifest = target / "dataset.json"
            return self._summary(
                dataset, manifest.stat().st_mtime, target.name
            )

    def save_recording(
        self,
        dataset_id: str,
        prompt_id: str,
        wav_bytes: bytes,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if not _SAFE_IDENTIFIER.fullmatch(prompt_id):
            raise ValueError("録音文章IDが不正です")
        if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
            raise ValueError("PCM WAV音声を保存してください")
        with self._lock:
            dataset = self._read(dataset_id)
            directory = self._dataset_directory(dataset_id)
            relative_audio = f"wavs/{prompt_id}.wav"
            audio_path = directory / relative_audio
            temporary = directory / "wavs" / f"{prompt_id}.tmp"
            temporary.write_bytes(wav_bytes)
            temporary.replace(audio_path)
            recording = {
                "prompt_id": prompt_id,
                "audio": relative_audio,
                "duration": float(metadata.get("duration") or 0),
                "sampleRate": int(metadata.get("sampleRate") or 48_000),
                "preview": list(metadata.get("preview") or [])[:256],
                "peak": float(metadata.get("peak") or 0),
                "rms": float(metadata.get("rms") or 0),
                "clippedRatio": float(metadata.get("clippedRatio") or 0),
                "accepted": bool(metadata.get("accepted")),
                "updatedAt": str(metadata.get("updatedAt") or _now()),
                "acceptedAt": metadata.get("acceptedAt"),
                "prompt": dict(metadata.get("prompt") or {}),
            }
            dataset.setdefault("recordings", {})[prompt_id] = recording
            dataset["updated_at"] = _now()
            self._write(dataset)
        return recording

    def audio_path(self, dataset_id: str, prompt_id: str) -> Path:
        if not _SAFE_IDENTIFIER.fullmatch(prompt_id):
            raise KeyError(prompt_id)
        path = (self._dataset_directory(dataset_id) / "wavs" / f"{prompt_id}.wav").resolve()
        expected_parent = (self._dataset_directory(dataset_id) / "wavs").resolve()
        if path.parent != expected_parent or not path.is_file():
            raise KeyError(prompt_id)
        return path

    def delete(self, dataset_id: str) -> None:
        directory = self._dataset_directory(dataset_id)
        with self._lock:
            if not (directory / "dataset.json").is_file():
                raise KeyError(dataset_id)
            if directory.parent != self.directory:
                raise ValueError("録音データセットの保存先が不正です")
            shutil.rmtree(directory)
