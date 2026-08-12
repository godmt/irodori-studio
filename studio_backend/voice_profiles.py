from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from studio_backend.models import VoiceProfileRequest


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate_voice_profile_store(legacy_path: Path, current_path: Path) -> bool:
    """Copy the legacy VOICEVOX-owned store into the shared voice library once."""
    if current_path.exists() or not legacy_path.is_file():
        return False
    current_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = current_path.with_suffix(".migration.tmp")
    shutil.copy2(legacy_path, temporary)
    temporary.replace(current_path)
    return True


class VoiceProfileStore:
    """Persistent, server-owned profiles shared by Studio and compatibility clients."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write({"schema_version": 1, "next_style_id": 1000, "profiles": []})

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"schema_version": 1, "next_style_id": 1000, "profiles": []}
        data.setdefault("schema_version", 1)
        data.setdefault("next_style_id", 1000)
        data.setdefault("profiles", [])
        return data

    def _write(self, data: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)

    @staticmethod
    def _validate_assets(request: VoiceProfileRequest) -> None:
        if not request.enabled:
            return
        if request.source_type == "speaker":
            if not request.ref_embed:
                raise ValueError("API公開するSpeaker Inversionファイルを選択してください")
            path = Path(request.ref_embed).expanduser()
            if not path.is_file() or path.suffix.lower() != ".safetensors":
                raise ValueError(f"Speaker embedding not found: {path}")
        elif request.source_type == "reference":
            if not request.ref_wavs:
                raise ValueError("API公開する参照音声を1件以上選択してください")
            for raw in request.ref_wavs:
                path = Path(raw).expanduser()
                if not path.is_file():
                    raise ValueError(f"Reference audio not found: {path}")
        if request.lora_adapter:
            path = Path(request.lora_adapter).expanduser()
            if not path.is_dir():
                raise ValueError(f"LoRA adapter not found: {path}")

    def list(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            profiles = [dict(item) for item in self._read()["profiles"]]
        if enabled_only:
            profiles = [profile for profile in profiles if profile.get("enabled")]
        return sorted(profiles, key=lambda item: (item.get("style_id", 0), item["name"]))

    def get(self, profile_id: str) -> dict[str, Any]:
        for profile in self.list():
            if profile["profile_id"] == profile_id:
                return profile
        raise KeyError(profile_id)

    def get_by_style_id(self, style_id: int, *, enabled_only: bool = True) -> dict[str, Any]:
        for profile in self.list(enabled_only=enabled_only):
            if int(profile["style_id"]) == int(style_id):
                return profile
        raise KeyError(style_id)

    def upsert(self, request: VoiceProfileRequest) -> dict[str, Any]:
        self._validate_assets(request)
        with self._lock:
            data = self._read()
            profiles = data["profiles"]
            existing_index = next(
                (
                    index
                    for index, profile in enumerate(profiles)
                    if request.profile_id
                    and profile["profile_id"] == request.profile_id
                ),
                None,
            )
            existing = profiles[existing_index] if existing_index is not None else None
            if request.profile_id and existing is None:
                raise KeyError(request.profile_id)

            profile_id = existing["profile_id"] if existing else uuid.uuid4().hex
            speaker_uuid = existing["speaker_uuid"] if existing else str(uuid.uuid4())
            if existing:
                style_id = int(existing["style_id"])
            else:
                style_id = int(data["next_style_id"])
                data["next_style_id"] = style_id + 1

            profile = {
                "profile_id": profile_id,
                "speaker_uuid": speaker_uuid,
                "style_id": style_id,
                **request.model_dump(exclude={"profile_id"}),
                "created_at": existing.get("created_at", utc_now()) if existing else utc_now(),
                "updated_at": utc_now(),
            }
            if existing_index is None:
                profiles.append(profile)
            else:
                profiles[existing_index] = profile
            self._write(data)
            return dict(profile)

    def delete(self, profile_id: str) -> None:
        with self._lock:
            data = self._read()
            before = len(data["profiles"])
            data["profiles"] = [
                profile for profile in data["profiles"] if profile["profile_id"] != profile_id
            ]
            if len(data["profiles"]) == before:
                raise KeyError(profile_id)
            self._write(data)
