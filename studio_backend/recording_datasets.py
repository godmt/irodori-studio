from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from studio_backend.dataset_preprocessing import (
    DATASET_AUDIO_PIPELINE_VERSION,
    prepare_dataset_audio,
    preprocessing_is_current,
    sha256_file,
    valid_dataset_wav,
)
from studio_backend.path_utils import safe_stem
from studio_backend.text_utils import normalize_training_text
from studio_backend.time_utils import utc_now

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


class RecordingDatasetStore:
    """Server-owned recording datasets prepared for the Training workspace."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._migrate_human_readable_directories()
        self._migrate_imported_flac_clips()
        self._migrate_dataset_audio_pipeline()

    @staticmethod
    def _valid_pcm16_wav(path: Path) -> bool:
        return valid_dataset_wav(path)

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

    def _initial_directory(self, name: str) -> Path:
        """Adopt a user-created raw-only folder, otherwise allocate a collision-safe folder."""

        candidate = (self.directory / self._folder_stem(name)).resolve()
        if candidate.parent == self.directory and candidate.is_dir():
            children = list(candidate.iterdir())
            if children and all(child.name.casefold() == "raw" and child.is_dir() for child in children):
                return candidate
        return self._available_directory(name)

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

    def _migrate_imported_flac_clips(self) -> None:
        """Migrate the former dataset-FLAC layout to the WAV training contract."""

        with self._lock:
            for manifest in self.directory.glob("*/dataset.json"):
                created: list[Path] = []
                try:
                    dataset = json.loads(manifest.read_text(encoding="utf-8"))
                    recordings = dataset.get("recordings", {})
                    if not isinstance(recordings, dict):
                        continue
                    obsolete: list[Path] = []
                    changed = False
                    for recording in recordings.values():
                        if not isinstance(recording, dict):
                            continue
                        relative = Path(str(recording.get("audio") or ""))
                        if relative.suffix.casefold() != ".flac":
                            continue
                        source = (manifest.parent / relative).resolve()
                        wavs_directory = (manifest.parent / "wavs").resolve()
                        target = (wavs_directory / f"{recording['prompt_id']}.wav").resolve()
                        if source.parent != wavs_directory or target.parent != wavs_directory:
                            continue
                        if not source.is_file():
                            continue
                        preprocessing = prepare_dataset_audio(source, target)
                        created.append(target)
                        recording["audio"] = f"wavs/{target.name}"
                        recording["sampleRate"] = 48_000
                        recording["duration"] = preprocessing["processed_seconds"]
                        recording["preprocessing"] = preprocessing
                        obsolete.append(source)
                        changed = True
                    if not changed:
                        continue
                    dataset["schema_version"] = max(5, int(dataset.get("schema_version") or 1))
                    dataset["updated_at"] = utc_now()
                    try:
                        self._write(dataset, manifest.parent)
                    except Exception:
                        for path in created:
                            path.unlink(missing_ok=True)
                        raise
                    for path in obsolete:
                        path.unlink(missing_ok=True)
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                    # Leave both the legacy manifest and FLAC untouched for a later retry.
                    for path in created:
                        path.unlink(missing_ok=True)
                    continue

    def _migrate_dataset_audio_pipeline(self) -> None:
        """Upgrade derived WAVs while retaining their former bytes under raw/."""

        with self._lock:
            for manifest in self.directory.glob("*/dataset.json"):
                dataset: dict[str, Any] | None = None
                try:
                    dataset = json.loads(manifest.read_text(encoding="utf-8"))
                    recordings = dataset.get("recordings", {})
                    if not isinstance(recordings, dict):
                        continue
                    changed = False
                    for prompt_id, recording in recordings.items():
                        if not isinstance(recording, dict):
                            continue
                        target = (manifest.parent / str(recording.get("audio") or "")).resolve()
                        wavs_directory = (manifest.parent / "wavs").resolve()
                        if target.parent != wavs_directory or not target.is_file():
                            continue
                        if preprocessing_is_current(recording) and valid_dataset_wav(target):
                            expected_hash = str(
                                recording.get("preprocessing", {}).get("output_sha256")
                                or ""
                            )
                            if expected_hash and sha256_file(target) == expected_hash:
                                continue
                        raw_directory = (manifest.parent / "raw" / "legacy-clips").resolve()
                        raw_directory.mkdir(parents=True, exist_ok=True)
                        source = (raw_directory / f"{prompt_id}.wav").resolve()
                        if source.parent != raw_directory:
                            continue
                        if not source.is_file():
                            shutil.copy2(target, source)
                        preprocessing = prepare_dataset_audio(source, target)
                        recording["preprocessing"] = preprocessing
                        recording.pop("preprocessingError", None)
                        recording["duration"] = preprocessing["processed_seconds"]
                        recording["sampleRate"] = 48_000
                        changed = True
                    if changed:
                        dataset["schema_version"] = max(
                            5, int(dataset.get("schema_version") or 1)
                        )
                        dataset.pop("preprocessing_error", None)
                        dataset["updated_at"] = utc_now()
                        self._write(dataset, manifest.parent)
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                    # Keep the source and last usable derived WAV for a later retry.
                    try:
                        if dataset is None:
                            continue
                        dataset["preprocessing_error"] = str(exc)
                        self._write(dataset, manifest.parent)
                    except Exception:
                        pass

    def preserve_raw_sources(
        self, dataset_id: str, sources: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Copy selected source files into the dataset-owned immutable raw area."""

        with self._lock:
            dataset_directory = self.dataset_directory(dataset_id)
            raw_directory = (dataset_directory / "raw" / "imports").resolve()
            raw_directory.mkdir(parents=True, exist_ok=True)
            preserved: list[dict[str, Any]] = []
            for source in sources:
                original = Path(str(source["path"])).expanduser().resolve(strict=True)
                if dataset_directory / "raw" in original.parents:
                    target = original
                else:
                    stat = original.stat()
                    identity = "|".join(
                        (str(original).casefold(), str(stat.st_size), str(stat.st_mtime_ns))
                    )
                    suffix = original.suffix.casefold()
                    stem = safe_stem(original.stem, fallback="source")[:80]
                    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
                    target = (raw_directory / f"{stem}-{digest}{suffix}").resolve()
                    if target.parent != raw_directory:
                        raise ValueError("RAW音声の保存先が不正です")
                    if not target.is_file() or target.stat().st_size != stat.st_size:
                        temporary = target.with_name(f".{target.name}.copying")
                        temporary.unlink(missing_ok=True)
                        try:
                            shutil.copy2(original, temporary)
                            temporary.replace(target)
                        finally:
                            temporary.unlink(missing_ok=True)
                preserved.append(
                    {
                        **source,
                        "path": str(target),
                        "original_path": str(original),
                    }
                )
            return preserved

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
                    "preprocessing": recording.get("preprocessing"),
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
        processed = [item for item in recordings if preprocessing_is_current(item)]
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
            "processed": len(processed),
            "processing_ready": len(processed) == len(recordings),
            "processing_pipeline_version": DATASET_AUDIO_PIPELINE_VERSION,
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
            directory = self._initial_directory(normalized_name)
            created_at = utc_now()
            dataset = {
                "schema_version": 5,
                "id": dataset_id,
                "name": normalized_name,
                "created_at": created_at,
                "updated_at": created_at,
                "recordings": {},
            }
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "wavs").mkdir(exist_ok=False)
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
            dataset["updated_at"] = utc_now()
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
            raw_directory = directory / "raw" / "recordings"
            raw_directory.mkdir(parents=True, exist_ok=True)
            raw_path = raw_directory / f"{prompt_id}.wav"
            raw_candidate = raw_directory / f".{prompt_id}.source.tmp"
            audio_candidate = directory / "wavs" / f".{prompt_id}.dataset.tmp"
            raw_candidate.write_bytes(wav_bytes)
            preprocessing = prepare_dataset_audio(raw_candidate, audio_candidate)
            backups: list[tuple[Path, Path]] = []
            try:
                for current in (raw_path, audio_path):
                    if current.is_file():
                        backup = current.with_name(f".{current.name}.backup")
                        backup.unlink(missing_ok=True)
                        current.replace(backup)
                        backups.append((current, backup))
                raw_candidate.replace(raw_path)
                audio_candidate.replace(audio_path)
            except Exception:
                raw_candidate.unlink(missing_ok=True)
                audio_candidate.unlink(missing_ok=True)
                for current, backup in reversed(backups):
                    if backup.is_file():
                        backup.replace(current)
                raise
            recording = {
                "prompt_id": prompt_id,
                "audio": relative_audio,
                "duration": float(preprocessing["processed_seconds"]),
                "sampleRate": 48_000,
                "preview": list(metadata.get("preview") or [])[:256],
                "peak": float(metadata.get("peak") or 0),
                "rms": float(metadata.get("rms") or 0),
                "clippedRatio": float(metadata.get("clippedRatio") or 0),
                "accepted": bool(metadata.get("accepted")),
                "updatedAt": str(metadata.get("updatedAt") or utc_now()),
                "acceptedAt": metadata.get("acceptedAt"),
                "prompt": dict(metadata.get("prompt") or {}),
                "preprocessing": preprocessing,
            }
            dataset.setdefault("recordings", {})[prompt_id] = recording
            dataset["schema_version"] = max(5, int(dataset.get("schema_version") or 1))
            dataset["updated_at"] = utc_now()
            try:
                self._write(dataset)
            except Exception:
                raw_path.unlink(missing_ok=True)
                audio_path.unlink(missing_ok=True)
                for current, backup in reversed(backups):
                    if backup.is_file():
                        backup.replace(current)
                raise
            for _, backup in backups:
                backup.unlink(missing_ok=True)
        return recording

    def commit_import(
        self,
        dataset_id: str,
        candidates: list[dict[str, Any]],
        clips_directory: Path,
        *,
        import_job_id: str,
        overwrite_existing: bool = False,
    ) -> dict[str, int]:
        """Commit job-local clips as WAV, retaining FLAC only until the commit succeeds."""

        clips_directory = clips_directory.resolve()
        with self._lock:
            dataset = self._read(dataset_id)
            original_dataset = deepcopy(dataset)
            dataset_directory = self._dataset_directory(dataset_id)
            wavs_directory = (dataset_directory / "wavs").resolve()
            wavs_directory.mkdir(exist_ok=True)
            prepared: list[tuple[Path, Path, dict[str, Any], str]] = []
            existing = dataset.setdefault("recordings", {})
            for candidate in candidates:
                prompt_id = str(candidate.get("id") or "")
                if not _SAFE_IDENTIFIER.fullmatch(prompt_id):
                    raise ValueError(f"取り込み音声IDが不正です: {prompt_id}")
                source = (clips_directory / Path(str(candidate.get("audio_file") or "")).name).resolve()
                if source.parent != clips_directory or not source.is_file():
                    raise FileNotFoundError(source)
                if source.suffix.casefold() not in {".flac", ".wav"}:
                    raise ValueError(f"取り込み音声形式が不正です: {source.name}")
                target = (wavs_directory / f"{prompt_id}.wav").resolve()
                if target.parent != wavs_directory:
                    raise ValueError(f"取り込み先の音声が不正です: {target.name}")
                current_recording = existing.get(prompt_id)
                target_ready = (
                    isinstance(current_recording, dict)
                    and preprocessing_is_current(current_recording)
                    and self._valid_pcm16_wav(target)
                )
                if prompt_id in existing and target_ready and not overwrite_existing:
                    action = "skip"
                elif target.is_file() and not target_ready:
                    action = "repair"
                elif target_ready and overwrite_existing:
                    action = "overwrite"
                else:
                    action = "replace_metadata" if prompt_id in existing else "create"
                prepared.append((source, target, candidate, action))

            created: list[Path] = []
            backups: list[tuple[Path, Path]] = []
            try:
                for source, target, candidate, action in prepared:
                    if action == "skip":
                        continue
                    if action in {"overwrite", "repair"}:
                        backup = clips_directory / f".{target.name}.{import_job_id}.backup"
                        backup.unlink(missing_ok=True)
                        target.replace(backup)
                        backups.append((target, backup))
                    preprocessing = prepare_dataset_audio(source, target)
                    created.append(target)
                    accepted = bool(candidate.get("accepted"))
                    text = normalize_training_text(str(candidate.get("text") or ""))
                    prompt_id = str(candidate["id"])
                    rms_dbfs = (
                        float(candidate["rms_dbfs"])
                        if candidate.get("rms_dbfs") is not None
                        else -120.0
                    )
                    existing[prompt_id] = {
                        "prompt_id": prompt_id,
                        "audio": f"wavs/{target.name}",
                        "duration": float(preprocessing["processed_seconds"]),
                        "sampleRate": 48_000,
                        "preview": [],
                        "peak": float(candidate.get("peak") or 0.0),
                        "rms": 10.0 ** (rms_dbfs / 20.0),
                        "clippedRatio": float(candidate.get("clipping_ratio") or 0.0),
                        "accepted": accepted,
                        "updatedAt": utc_now(),
                        "acceptedAt": utc_now() if accepted else None,
                        "reviewState": str(candidate.get("review_state") or "needs_review"),
                        "preprocessing": preprocessing,
                        "prompt": {
                            "text": text,
                            "originalText": text,
                            "direction": "",
                            "category": "imported_audio",
                            "sourceId": prompt_id,
                            "sourceName": str(candidate.get("source_name") or ""),
                        },
                        "import": {
                            "jobId": import_job_id,
                            "sourceFile": str(candidate.get("source_file") or ""),
                            "sourceIndex": int(candidate.get("source_index") or 0),
                            "sourceStart": float(candidate.get("source_start") or 0.0),
                            "sourceEnd": float(candidate.get("source_end") or 0.0),
                            "qualityScore": float(candidate.get("quality_score") or 0.0),
                            "wordProbability": float(
                                candidate.get("word_probability") or 0.0
                            ),
                            "avgLogprob": (
                                float(candidate["avg_logprob"])
                                if candidate.get("avg_logprob") is not None
                                else -10.0
                            ),
                            "noSpeechProbability": float(
                                candidate["no_speech_probability"]
                                if candidate.get("no_speech_probability") is not None
                                else 1.0
                            ),
                            "compressionRatio": float(
                                candidate.get("compression_ratio") or 0.0
                            ),
                            "rmsDbfs": rms_dbfs,
                            "silenceRatio": float(
                                candidate["silence_ratio"]
                                if candidate.get("silence_ratio") is not None
                                else 1.0
                            ),
                            "estimatedSnrDb": float(
                                candidate.get("estimated_snr_db") or 0.0
                            ),
                            "rejectionReasons": list(candidate.get("rejection_reasons") or []),
                        },
                    }
                dataset["schema_version"] = max(5, int(dataset.get("schema_version") or 1))
                dataset["updated_at"] = utc_now()
                self._write(dataset)
            except Exception:
                for path in created:
                    path.unlink(missing_ok=True)
                for target, backup in reversed(backups):
                    if backup.exists():
                        backup.replace(target)
                try:
                    self._write(original_dataset)
                except Exception:
                    pass
                raise
            for _, backup in backups:
                backup.unlink(missing_ok=True)
            for source, _, _, _ in prepared:
                source.unlink(missing_ok=True)
        processed = [item for item in prepared if item[3] != "skip"]
        return {
            "imported": sum(action == "create" for _, _, _, action in prepared),
            "overwritten": sum(
                action in {"overwrite", "repair", "replace_metadata"}
                for _, _, _, action in prepared
            ),
            "skipped": sum(action == "skip" for _, _, _, action in prepared),
            "accepted": sum(bool(candidate.get("accepted")) for _, _, candidate, _ in processed),
        }

    def update_recording_review(
        self,
        dataset_id: str,
        prompt_id: str,
        *,
        text: str | None,
        accepted: bool | None,
    ) -> dict[str, Any]:
        if not _SAFE_IDENTIFIER.fullmatch(prompt_id):
            raise KeyError(prompt_id)
        with self._lock:
            dataset = self._read(dataset_id)
            recording = dataset.get("recordings", {}).get(prompt_id)
            if not isinstance(recording, dict):
                raise KeyError(prompt_id)
            prompt = recording.setdefault("prompt", {})
            if text is not None:
                prompt["text"] = normalize_training_text(text)
            normalized_text = str(prompt.get("text") or "").strip()
            if accepted is True and not normalized_text:
                raise ValueError("採用する音声には文字起こしが必要です")
            if accepted is not None:
                recording["accepted"] = accepted
                recording["acceptedAt"] = utc_now() if accepted else None
                recording["reviewState"] = "manual_accepted" if accepted else "excluded"
            recording["updatedAt"] = utc_now()
            dataset["updated_at"] = utc_now()
            self._write(dataset)
            return deepcopy(recording)

    def audio_path(self, dataset_id: str, prompt_id: str) -> Path:
        if not _SAFE_IDENTIFIER.fullmatch(prompt_id):
            raise KeyError(prompt_id)
        dataset = self._read(dataset_id)
        recording = dataset.get("recordings", {}).get(prompt_id)
        if not isinstance(recording, dict):
            raise KeyError(prompt_id)
        dataset_directory = self._dataset_directory(dataset_id)
        path = (dataset_directory / str(recording.get("audio") or "")).resolve()
        expected_parent = (dataset_directory / "wavs").resolve()
        if (
            path.parent != expected_parent
            or path.suffix.casefold() != ".wav"
            or not path.is_file()
        ):
            raise KeyError(prompt_id)
        return path

    def delete(self, dataset_id: str) -> None:
        directory = self._dataset_directory(dataset_id)
        with self._lock:
            if not (directory / "dataset.json").is_file():
                raise KeyError(dataset_id)
            if directory.parent != self.directory:
                raise ValueError("録音データセットの保存先が不正です")
            raw_directory = directory / "raw"
            if raw_directory.is_dir():
                shutil.rmtree(directory / "wavs", ignore_errors=True)
                for filename in (
                    "dataset.json",
                    "dataset.jsonl",
                    "dataset.tmp",
                    "dataset.jsonl.tmp",
                ):
                    (directory / filename).unlink(missing_ok=True)
            else:
                shutil.rmtree(directory)
