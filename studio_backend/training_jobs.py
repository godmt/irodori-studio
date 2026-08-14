from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from studio_backend.dataset_preprocessing import (
    DATASET_AUDIO_PIPELINE_VERSION,
    preprocessing_is_current,
    sha256_file,
    valid_dataset_wav,
)
from studio_backend.time_utils import utc_now

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
_STEP_PATTERN = re.compile(r"(?:step=|\|\s*)(\d+)(?:/|\s)")
_LOSS_PATTERN = re.compile(r"loss=([0-9.eE+-]+)")
_SPEAKER_CHECKPOINT_PATTERN = re.compile(r"^checkpoint_(\d+)\.speaker\.safetensors$")
_LORA_CHECKPOINT_PATTERN = re.compile(r"^checkpoint_(\d+)$")
ACTIVE_TRAINING_STATUSES = {"queued", "preparing", "training", "cancelling"}


class TrainingJobError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        title: str,
        summary: str,
        action: str,
        details: str = "",
    ) -> None:
        super().__init__(summary)
        self.failure = {
            "schema_version": 1,
            "code": code,
            "title": title,
            "summary": summary,
            "action": action,
            "details": details,
        }


def _safe_slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-_")
    return (normalized or "model")[:64]


class TrainingJobManager:
    """Runs the external Irodori-TTS trainer while Studio owns job metadata and outputs."""

    def __init__(
        self,
        *,
        workspace: Path,
        irodori_root: Path,
        recording_store: Any,
        default_checkpoint: str,
    ) -> None:
        self.workspace = workspace.resolve()
        self.irodori_root = irodori_root.resolve()
        self.recording_store = recording_store
        self.default_checkpoint = default_checkpoint
        self.training_directory = self.workspace / "training"
        self.model_directory = self.workspace / "models"
        self.speaker_directory = self.model_directory / "speaker-embeddings"
        self.lora_directory = self.model_directory / "lora"
        for directory in (
            self.training_directory,
            self.speaker_directory,
            self.lora_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._recover_interrupted_jobs()

    def _recover_interrupted_jobs(self) -> None:
        for path in self.training_directory.glob("*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                changed = False
                if job.get("status") in {"queued", "preparing", "training", "cancelling"}:
                    job["status"] = "interrupted"
                    job["stage"] = "interrupted"
                    job["message"] = "Studioの前回終了時に学習が中断されました"
                    job["updated_at"] = utc_now()
                    changed = True
                stored_failure = job.get("failure")
                failure_schema = (
                    int(stored_failure.get("schema_version") or 0)
                    if isinstance(stored_failure, dict)
                    else 0
                )
                if job.get("status") == "failed" and failure_schema < 1:
                    failure = self._failure_from_exception(
                        RuntimeError(str(job.get("message") or "学習に失敗しました")),
                        path.parent,
                    )
                    job["failure"] = failure
                    job["message"] = failure["summary"]
                    changed = True
                if changed:
                    self._write(job)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue

    @staticmethod
    def _log_excerpt(path: Path, *, max_lines: int = 80, max_chars: int = 12_000) -> str:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        excerpt = "\n".join(lines[-max_lines:])
        return excerpt[-max_chars:]

    def _failure_from_exception(
        self, exc: Exception, job_directory: Path
    ) -> dict[str, Any]:
        log_excerpt = self._log_excerpt(job_directory / "training.log")
        if isinstance(exc, TrainingJobError):
            failure = dict(exc.failure)
            detail_parts = [str(failure.get("details") or "").strip()]
            if log_excerpt:
                detail_parts.append(f"--- training.log ---\n{log_excerpt}")
            failure["details"] = "\n\n".join(part for part in detail_parts if part)
            return failure

        details = str(exc)
        if log_excerpt:
            details = f"{details}\n\n--- training.log ---\n{log_excerpt}"

        diagnostic = f"{exc}\n{log_excerpt}".casefold()
        if "cuda out of memory" in diagnostic or "outofmemoryerror" in diagnostic:
            return {
                "schema_version": 1,
                "code": "gpu_out_of_memory",
                "title": "GPUメモリが不足しました",
                "summary": "学習に必要なGPUメモリを確保できず、処理を停止しました。",
                "action": "他のGPU処理を終了するか、学習設定の精度・方式を見直してから再開してください。",
                "details": details,
            }
        if (
            "dataset_iter_error" in diagnostic
            and ("written=0" in diagnostic or "no valid samples" in diagnostic)
        ):
            return {
                "schema_version": 1,
                "code": "audio_decoder_unavailable",
                "title": "Irodori-TTSへ音声を渡せませんでした",
                "summary": "Studioの前処理済みWAVは正常ですが、Irodori-TTS側の音声読込で全件が除外されました。",
                "action": "この履歴の再開を実行してください。Studioの互換読込が使用されます。",
                "details": details,
            }
        return {
            "schema_version": 1,
            "code": "unexpected_training_error",
            "title": "学習処理を完了できませんでした",
            "summary": str(exc) or "予期しない理由で学習処理が停止しました。",
            "action": "技術情報を確認し、入力や学習設定を直してから再開してください。",
            "details": details,
        }

    def paths(self) -> dict[str, str]:
        return {
            "speaker_embeddings": "workspace/models/speaker-embeddings",
            "lora_adapters": "workspace/models/lora",
            "training_jobs": "workspace/training",
        }

    def models(self) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        for root in (self.speaker_directory, self.lora_directory):
            for path in root.glob("*/studio-model.json"):
                try:
                    models.append(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue
        return sorted(models, key=lambda model: model.get("created_at", ""), reverse=True)

    def _model_manifest(self, model_id: str) -> tuple[Path, dict[str, Any]]:
        if not _SAFE_IDENTIFIER.fullmatch(model_id):
            raise KeyError(model_id)
        for root in (self.speaker_directory, self.lora_directory):
            for path in root.glob("*/studio-model.json"):
                try:
                    model = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue
                if str(model.get("id")) == model_id:
                    return path, model
        raise KeyError(model_id)

    def model(self, model_id: str) -> dict[str, Any]:
        with self._lock:
            _, model = self._model_manifest(model_id)
            return dict(model)

    def rename_model(self, model_id: str, name: str) -> dict[str, Any]:
        normalized = name.strip()
        if not normalized:
            raise ValueError("モデル名を入力してください")
        with self._lock:
            if any(
                str(model.get("id")) != model_id
                and str(model.get("name", "")).casefold() == normalized.casefold()
                for model in self.models()
            ):
                raise ValueError("同じ名前の学習済みモデルがすでにあります")
            manifest, model = self._model_manifest(model_id)
            model["name"] = normalized
            model["updated_at"] = utc_now()
            temporary = manifest.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(manifest)
            try:
                job = self._read(model_id)
                job["name"] = normalized
                job["updated_at"] = utc_now()
                self._write(job)
            except KeyError:
                pass
            return dict(model)

    def delete_model(self, model_id: str) -> None:
        with self._lock:
            manifest, _ = self._model_manifest(model_id)
            directory = manifest.parent.resolve()
            allowed_roots = {
                self.speaker_directory.resolve(),
                self.lora_directory.resolve(),
            }
            if directory.parent not in allowed_roots:
                raise ValueError("学習済みモデルの保存先が不正です")
            shutil.rmtree(directory)

    def _job_directory(self, job_id: str) -> Path:
        if not _SAFE_IDENTIFIER.fullmatch(job_id):
            raise KeyError(job_id)
        path = (self.training_directory / job_id).resolve()
        if path.parent != self.training_directory:
            raise KeyError(job_id)
        return path

    def _metadata_path(self, job_id: str) -> Path:
        return self._job_directory(job_id) / "job.json"

    def _read(self, job_id: str) -> dict[str, Any]:
        path = self._metadata_path(job_id)
        if not path.is_file():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, job: dict[str, Any]) -> None:
        directory = self._job_directory(str(job["id"]))
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "job.json"
        temporary = directory / "job.tmp"
        temporary.write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(target)

    @staticmethod
    def _summary(
        job: dict[str, Any], *, include_failure_details: bool = True
    ) -> dict[str, Any]:
        summary = {key: value for key, value in job.items() if key != "command"}
        failure = summary.get("failure")
        if isinstance(failure, dict) and not include_failure_details:
            summary["failure"] = {
                key: value for key, value in failure.items() if key != "details"
            }
        return summary

    def list(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        with self._lock:
            paths = sorted(
                self.training_directory.glob("*/job.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            for path in paths:
                try:
                    job = json.loads(path.read_text(encoding="utf-8"))
                    jobs.append(self._summary(job, include_failure_details=False))
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                    continue
        return jobs

    def load(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._summary(self._read(job_id))

    def has_active_job(self) -> bool:
        return any(job.get("status") in ACTIVE_TRAINING_STATUSES for job in self.list())

    def _snapshot_dataset_rows(
        self,
        dataset_id: str,
        job_directory: Path,
        *,
        overwrite_existing: bool = False,
    ) -> dict[str, Any]:
        dataset = self.recording_store.load(dataset_id)
        source_root = self.recording_store.dataset_directory(dataset_id)
        accepted = [
            recording
            for recording in dataset.get("recordings", {}).values()
            if recording.get("accepted")
        ]
        if not accepted:
            raise ValueError("採用済みの録音がないため学習を開始できません")
        rows: list[dict[str, Any]] = []
        snapshot_directory = job_directory / "dataset-snapshot"
        snapshot_directory.mkdir(parents=True, exist_ok=True)
        file_results: list[dict[str, Any]] = []
        fingerprint_rows: list[dict[str, Any]] = []
        for recording in sorted(accepted, key=lambda item: str(item.get("prompt_id") or "")):
            prompt = recording.get("prompt", {})
            source_audio = (source_root / recording["audio"]).resolve()
            if not preprocessing_is_current(recording) or not valid_dataset_wav(source_audio):
                raise TrainingJobError(
                    code="dataset_audio_not_ready",
                    title="学習データセットの音声を使用できません",
                    summary=f"「{recording['prompt_id']}」の共通音声加工が完了していません。",
                    action="データセットの音声を再処理してから学習を再開してください。",
                    details=f"source={source_audio}",
                )
            preprocessing = recording["preprocessing"]
            source_hash = sha256_file(source_audio)
            if source_hash != str(preprocessing.get("output_sha256") or ""):
                raise TrainingJobError(
                    code="dataset_audio_changed",
                    title="学習データセットの音声が変更されています",
                    summary=f"「{recording['prompt_id']}」が加工記録と一致しません。",
                    action="データセットの音声を再処理してから学習を再開してください。",
                    details=f"source={source_audio}",
                )

            snapshot_audio = (
                snapshot_directory / f"{recording['prompt_id']}.wav"
            ).resolve()
            reused = (
                not overwrite_existing
                and valid_dataset_wav(snapshot_audio)
                and sha256_file(snapshot_audio) == source_hash
            )
            snapshot_method = "reused"
            if not reused:
                temporary = snapshot_audio.with_suffix(".tmp")
                temporary.unlink(missing_ok=True)
                try:
                    try:
                        os.link(source_audio, temporary)
                        snapshot_method = "hardlink"
                    except OSError:
                        shutil.copy2(source_audio, temporary)
                        snapshot_method = "copy"
                    temporary.replace(snapshot_audio)
                finally:
                    temporary.unlink(missing_ok=True)
            file_results.append(
                {
                    "prompt_id": recording["prompt_id"],
                    "source_audio": str(source_audio),
                    "snapshot_audio": str(snapshot_audio),
                    "output_sha256": source_hash,
                    "snapshot_method": snapshot_method,
                    "pipeline_version": DATASET_AUDIO_PIPELINE_VERSION,
                }
            )
            row = {
                "audio": str(snapshot_audio),
                "text": prompt.get("text", ""),
                "caption": prompt.get("direction", ""),
            }
            rows.append(row)
            fingerprint_rows.append(
                {
                    "prompt_id": recording["prompt_id"],
                    "output_sha256": source_hash,
                    "pipeline_version": DATASET_AUDIO_PIPELINE_VERSION,
                    "text": row["text"],
                    "caption": row["caption"],
                }
            )
        dataset_jsonl = job_directory / "source-dataset.jsonl"
        dataset_jsonl.write_text(
            "".join(
                f"{json.dumps(row, ensure_ascii=False, separators=(',', ':'))}\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        summary = {
            "schema_version": 1,
            "files": len(rows),
            "dataset_fingerprint": hashlib.sha256(
                json.dumps(
                    fingerprint_rows,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "pipeline_version": DATASET_AUDIO_PIPELINE_VERSION,
            "reused_files": sum(
                result["snapshot_method"] == "reused" for result in file_results
            ),
            "transformations_applied": False,
            "source_dataset_modified": False,
            "results": file_results,
        }
        (job_directory / "dataset-snapshot.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return summary

    @staticmethod
    def _manifest_marker_path(job_directory: Path) -> Path:
        return job_directory / "manifest-ready.json"

    def _manifest_is_reusable(
        self, job_directory: Path, fingerprint: str, expected_count: int
    ) -> bool:
        manifest = job_directory / "prepared-manifest.jsonl"
        marker = self._manifest_marker_path(job_directory)
        if not manifest.is_file() or not marker.is_file():
            return False
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
            if metadata.get("dataset_fingerprint") != fingerprint:
                return False
            rows = [
                json.loads(line)
                for line in manifest.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if not rows:
                return False
            if len(rows) != expected_count:
                return False
            base = manifest.parent.resolve()
            for row in rows:
                latent = (base / str(row["latent_path"])).resolve()
                if base not in latent.parents or not latent.is_file():
                    return False
            return True
        except (OSError, TypeError, KeyError, json.JSONDecodeError):
            return False

    @staticmethod
    def _validate_prepared_manifest(
        manifest: Path, *, expected_count: int
    ) -> int:
        try:
            raw_lines = manifest.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise TrainingJobError(
                code="manifest_missing",
                title="学習データの受け渡しに失敗しました",
                summary="Irodori-TTSから学習用データが返されませんでした。",
                action="技術情報を確認してから学習を再開してください。",
                details=str(exc),
            ) from exc

        rows: list[dict[str, Any]] = []
        try:
            rows = [json.loads(line) for line in raw_lines if line.strip()]
        except (TypeError, json.JSONDecodeError) as exc:
            raise TrainingJobError(
                code="manifest_invalid",
                title="学習データの受け渡しに失敗しました",
                summary="Irodori-TTSが返した学習用データを読み取れませんでした。",
                action="技術情報を確認し、最初からやり直してください。",
                details=str(exc),
            ) from exc

        if not rows:
            raise TrainingJobError(
                code="manifest_empty",
                title="学習可能な音声を準備できませんでした",
                summary=(
                    f"{expected_count}件の前処理済みWAVから、学習用データが1件も生成されませんでした。"
                ),
                action="技術情報で音声読込またはモデル初期化の原因を確認し、再開してください。",
            )
        if len(rows) != expected_count:
            raise TrainingJobError(
                code="manifest_incomplete",
                title="一部の音声を学習用に準備できませんでした",
                summary=(
                    f"{expected_count}件中{len(rows)}件だけが学習可能な状態になりました。"
                ),
                action="欠けた音声を黙って無視せず停止しました。技術情報を確認してから再開してください。",
            )

        base = manifest.parent.resolve()
        for index, row in enumerate(rows, start=1):
            try:
                latent = (base / str(row["latent_path"])).resolve()
            except (KeyError, TypeError) as exc:
                raise TrainingJobError(
                    code="latent_missing",
                    title="学習用データが不完全です",
                    summary=f"{index}件目の音声特徴データを特定できませんでした。",
                    action="最初からやり直して学習用データを再生成してください。",
                    details=str(exc),
                ) from exc
            if base not in latent.parents or not latent.is_file():
                raise TrainingJobError(
                    code="latent_missing",
                    title="学習用データが不完全です",
                    summary=f"{index}件目の音声特徴データが見つかりません。",
                    action="最初からやり直して学習用データを再生成してください。",
                    details=str(latent),
                )
        return len(rows)

    def _mark_manifest_ready(
        self, job_directory: Path, fingerprint: str, row_count: int
    ) -> None:
        marker = self._manifest_marker_path(job_directory)
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "dataset_fingerprint": fingerprint,
                    "rows": row_count,
                    "created_at": utc_now(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(marker)

    @staticmethod
    def _latest_resume_checkpoint(method: str, output_directory: Path) -> Path | None:
        checkpoints: list[tuple[int, int, Path]] = []
        if not output_directory.is_dir():
            return None
        if method == "speaker_inversion":
            for path in output_directory.rglob("checkpoint_*.speaker.safetensors"):
                match = _SPEAKER_CHECKPOINT_PATTERN.fullmatch(path.name)
                if match:
                    checkpoints.append((int(match.group(1)), path.stat().st_mtime_ns, path))
        else:
            for path in output_directory.rglob("checkpoint_*"):
                match = _LORA_CHECKPOINT_PATTERN.fullmatch(path.name)
                if match and path.is_dir() and (path / "adapter_config.json").is_file():
                    checkpoints.append((int(match.group(1)), path.stat().st_mtime_ns, path))
        return max(checkpoints, key=lambda item: (item[0], item[1]))[2] if checkpoints else None

    def _reset_generated_artifacts(
        self, job_directory: Path, output_directory: Path
    ) -> None:
        if job_directory.parent.resolve() != self.training_directory:
            raise ValueError("学習ジョブの保存先が不正です")
        if output_directory.parent.resolve() not in {
            self.speaker_directory.resolve(),
            self.lora_directory.resolve(),
        }:
            raise ValueError("学習済みモデルの保存先が不正です")
        for name in ("dataset-snapshot", "prepared-audio", "latents"):
            path = (job_directory / name).resolve()
            if path.parent == job_directory:
                shutil.rmtree(path, ignore_errors=True)
        for name in (
            "source-dataset.jsonl",
            "dataset-snapshot.json",
            "preprocessing.json",
            "prepared-manifest.jsonl",
            "manifest-ready.json",
            "training.log",
        ):
            (job_directory / name).unlink(missing_ok=True)
        if output_directory.is_dir():
            shutil.rmtree(output_directory)

    def _config_path(self, method: str) -> Path:
        config_name = (
            "train_v4_small_speaker_inversion.yaml"
            if method == "speaker_inversion"
            else "train_v4_small_lora.yaml"
        )
        path = self.irodori_root / "configs" / config_name
        if not path.is_file():
            raise FileNotFoundError(f"Irodori-TTSの学習設定が見つかりません: {config_name}")
        return path

    def create(self, payload: Any) -> dict[str, Any]:
        name = payload.name.strip()
        if not name:
            raise ValueError("モデル名を入力してください")
        dataset = self.recording_store.load(payload.dataset_id)
        if int(dataset.get("accepted") or 0) <= 0:
            raise ValueError("採用済みの録音がないため学習を開始できません")
        if not (self.irodori_root / "train.py").is_file():
            raise FileNotFoundError("Irodori-TTSのtrain.pyが見つかりません")
        if self.has_active_job():
            raise ValueError("別の学習が実行中です。完了または停止してから開始してください")

        method = payload.method
        job_id = uuid4().hex
        job_directory = self._job_directory(job_id)
        job_directory.mkdir(parents=True, exist_ok=False)
        slug = _safe_slug(name)
        output_root = self.speaker_directory if method == "speaker_inversion" else self.lora_directory
        output_directory = (output_root / f"{slug}-{job_id[:8]}").resolve()
        config_path = self._config_path(method)

        created_at = utc_now()
        job = {
            "schema_version": 1,
            "id": job_id,
            "name": name,
            "method": method,
            "dataset_id": payload.dataset_id,
            "dataset_name": dataset["name"],
            "accepted": dataset["accepted"],
            "accepted_seconds": dataset["accepted_seconds"],
            "checkpoint": payload.checkpoint or self.default_checkpoint,
            "device": payload.device,
            "precision": payload.precision,
            "max_steps": payload.max_steps,
            "status": "queued",
            "stage": "queued",
            "step": 0,
            "progress": 0,
            "loss": None,
            "message": "学習開始を待っています",
            "created_at": created_at,
            "updated_at": created_at,
            "completed_at": None,
            "output_path": str(output_directory),
            "asset_path": None,
            "failure": None,
            "dataset_snapshot": None,
            "log_path": str((job_directory / "training.log").resolve()),
            "command": [],
            "attempt": 1,
            "resume_mode": "new",
            "run_output_path": str(output_directory),
        }
        with self._lock:
            self._write(job)
        thread = threading.Thread(
            target=self._run,
            args=(job_id, config_path, output_directory, output_directory),
            kwargs={"resume": False, "overwrite_existing": False},
            daemon=True,
            name=f"training-{job_id[:8]}",
        )
        thread.start()
        return self._summary(job)

    def _update(self, job_id: str, **patch: Any) -> dict[str, Any]:
        with self._lock:
            job = self._read(job_id)
            job.update(patch)
            job["updated_at"] = utc_now()
            self._write(job)
            return job

    def _run(
        self,
        job_id: str,
        config_path: Path,
        output_directory: Path,
        run_output_directory: Path,
        *,
        resume: bool,
        overwrite_existing: bool,
    ) -> None:
        job_directory = self._job_directory(job_id)
        log_path = job_directory / "training.log"
        try:
            job = self._read(job_id)
            if job.get("status") in {"cancelled", "cancelling"}:
                return
            dataset_snapshot = self._snapshot_dataset_rows(
                job["dataset_id"],
                job_directory,
                overwrite_existing=overwrite_existing,
            )
            if self._read(job_id).get("status") in {"cancelled", "cancelling"}:
                self._update(
                    job_id,
                    status="cancelled",
                    stage="cancelled",
                    message="学習を中止しました",
                    completed_at=utc_now(),
                )
                return
            row_count = int(dataset_snapshot["files"])
            dataset_snapshot_summary = {
                key: value for key, value in dataset_snapshot.items() if key != "results"
            }
            prepared_manifest = job_directory / "prepared-manifest.jsonl"
            latent_directory = job_directory / "latents"
            latent_directory.mkdir(exist_ok=True)
            manifest_reused = (
                resume
                and not overwrite_existing
                and self._manifest_is_reusable(
                    job_directory,
                    str(dataset_snapshot["dataset_fingerprint"]),
                    row_count,
                )
            )
            resume_checkpoint = (
                self._latest_resume_checkpoint(job["method"], output_directory)
                if resume and not overwrite_existing
                else None
            )
            previous_snapshot = job.get("dataset_snapshot") or job.get("preprocessing") or {}
            previous_fingerprint = previous_snapshot.get(
                "dataset_fingerprint"
            )
            if (
                resume_checkpoint is not None
                and previous_fingerprint
                and previous_fingerprint != dataset_snapshot["dataset_fingerprint"]
            ):
                raise ValueError(
                    "中断後に学習データが変更されています。全上書きで最初からやり直してください"
                )

            python = Path(sys.executable).resolve()
            prepare_runner = Path(__file__).with_name("irodori_prepare_runner.py").resolve()
            prepare_command = [
                str(python),
                str(prepare_runner),
                "--script",
                str(self.irodori_root / "prepare_manifest.py"),
                "--audio-root",
                str(job_directory / "dataset-snapshot"),
                "--dataset",
                "json",
                "--data-files",
                f"train={job_directory / 'source-dataset.jsonl'}",
                "--split",
                "train",
                "--audio-column",
                "audio",
                "--text-column",
                "text",
                "--caption-column",
                "caption",
                "--output-manifest",
                str(prepared_manifest),
                "--latent-dir",
                str(latent_directory),
                "--normalize-db",
                "none",
                "--device",
                job["device"],
            ]
            train_command = [
                str(python),
                str(self.irodori_root / "train.py"),
                "--config",
                str(config_path),
                "--manifest",
                str(prepared_manifest),
                "--output-dir",
                str(run_output_directory),
                "--init-checkpoint",
                job["checkpoint"],
                "--device",
                job["device"],
                "--precision",
                job["precision"],
                "--max-steps",
                str(job["max_steps"]),
                "--no-wandb",
                "--no-progress",
            ]
            if resume_checkpoint is not None:
                if job["method"] == "speaker_inversion":
                    train_command.extend(
                        ["--speaker-inversion-init-embedding", str(resume_checkpoint)]
                    )
                else:
                    train_command.extend(["--resume", str(resume_checkpoint)])
            self._update(
                job_id,
                status="preparing",
                stage="preparing",
                message=(
                    f"{row_count}件の加工済み音声を学習用に固定しています"
                ),
                dataset_snapshot=dataset_snapshot_summary,
                preprocessing=None,
                command=[prepare_command, train_command],
                resume_checkpoint=(
                    str(resume_checkpoint) if resume_checkpoint is not None else None
                ),
                manifest_reused=manifest_reused,
                run_output_path=str(run_output_directory),
            )
            with log_path.open("a", encoding="utf-8") as log:
                log.write(
                    f"[studio] model={job['name']} method={job['method']} "
                    f"attempt={job.get('attempt', 1)} resume={resume} "
                    f"overwrite={overwrite_existing}\n"
                )
                if manifest_reused:
                    log.write("[studio] reusable manifest and latents found; skipped\n")
                else:
                    prepared_manifest.unlink(missing_ok=True)
                    self._manifest_marker_path(job_directory).unlink(missing_ok=True)
                    shutil.rmtree(latent_directory, ignore_errors=True)
                    latent_directory.mkdir(exist_ok=True)
                    self._execute(job_id, prepare_command, log, stage="preparing")
                    if self._read(job_id).get("status") == "cancelled":
                        return
                    prepared_rows = self._validate_prepared_manifest(
                        prepared_manifest, expected_count=row_count
                    )
                    self._mark_manifest_ready(
                        job_directory,
                        str(dataset_snapshot["dataset_fingerprint"]),
                        prepared_rows,
                    )
                if self._read(job_id).get("status") == "cancelled":
                    return
                self._update(
                    job_id,
                    status="training",
                    stage="training",
                    message="モデルを学習しています",
                )
                run_output_directory.mkdir(parents=True, exist_ok=True)
                self._execute(job_id, train_command, log, stage="training")
            if self._read(job_id).get("status") == "cancelled":
                return
            asset_path = self._final_asset(job["method"], run_output_directory)
            model = {
                "schema_version": 1,
                "id": job_id,
                "name": job["name"],
                "method": job["method"],
                "dataset_id": job["dataset_id"],
                "dataset_name": job["dataset_name"],
                "checkpoint": job["checkpoint"],
                "created_at": utc_now(),
                "asset_path": str(asset_path),
                "output_path": str(output_directory),
                "run_output_path": str(run_output_directory),
            }
            (output_directory / "studio-model.json").write_text(
                json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._update(
                job_id,
                status="completed",
                stage="completed",
                step=job["max_steps"],
                progress=100,
                message="学習が完了しました",
                completed_at=utc_now(),
                asset_path=str(asset_path),
                failure=None,
            )
        except Exception as exc:
            try:
                job = self._read(job_id)
                if job.get("status") != "cancelled":
                    failure = self._failure_from_exception(exc, job_directory)
                    self._update(
                        job_id,
                        status="failed",
                        stage="failed",
                        message=failure["summary"],
                        failure=failure,
                        completed_at=utc_now(),
                    )
            except Exception:
                pass
        finally:
            with self._lock:
                self._processes.pop(job_id, None)

    def _execute(
        self,
        job_id: str,
        command: list[str],
        log: Any,
        *,
        stage: str,
    ) -> None:
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(
            command,
            cwd=self.irodori_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=environment,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0
            ),
        )
        with self._lock:
            self._processes[job_id] = process
        assert process.stdout is not None
        try:
            for line in process.stdout:
                log.write(line)
                log.flush()
                if stage != "training":
                    continue
                job = self._read(job_id)
                step_match = _STEP_PATTERN.search(line)
                loss_match = _LOSS_PATTERN.search(line)
                patch: dict[str, Any] = {}
                if step_match:
                    step = int(step_match.group(1))
                    patch.update(
                        step=step,
                        progress=min(
                            99,
                            round(step / max(1, int(job["max_steps"])) * 100, 1),
                        ),
                    )
                if loss_match:
                    patch["loss"] = float(loss_match.group(1))
                if patch:
                    self._update(job_id, **patch)
        finally:
            process.stdout.close()
        return_code = process.wait()
        current = self._read(job_id)
        if current.get("status") == "cancelling":
            self._update(
                job_id,
                status="cancelled",
                stage="cancelled",
                message="学習を中止しました",
                completed_at=utc_now(),
            )
            return
        if return_code != 0:
            raise RuntimeError(f"Irodori-TTSの{stage}処理が終了コード{return_code}で停止しました")

    @staticmethod
    def _final_asset(method: str, output_directory: Path) -> Path:
        if method == "speaker_inversion":
            path = output_directory / "checkpoint_final.speaker.safetensors"
            if not path.is_file():
                raise FileNotFoundError("Speaker Inversionの最終ファイルが生成されませんでした")
            return path.resolve()
        path = output_directory / "checkpoint_final"
        if not (path / "adapter_config.json").is_file():
            raise FileNotFoundError("LoRAの最終アダプターが生成されませんでした")
        return path.resolve()

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._read(job_id)
            if job.get("status") not in {"queued", "preparing", "training"}:
                return self._summary(job)
            job.update(
                status="cancelling",
                message="安全に停止しています",
                updated_at=utc_now(),
            )
            self._write(job)
            process = self._processes.get(job_id)
            if process and process.poll() is None:
                process.terminate()
            elif job.get("stage") == "queued":
                job.update(
                    status="cancelled",
                    stage="cancelled",
                    message="学習を中止しました",
                    completed_at=utc_now(),
                )
                self._write(job)
            return self._summary(job)

    def resume(
        self, job_id: str, *, overwrite_existing: bool = False
    ) -> dict[str, Any]:
        with self._lock:
            job = self._read(job_id)
            if job.get("status") not in {"cancelled", "failed", "interrupted"}:
                raise ValueError("中断・失敗・停止した学習だけ再開できます")
            if self.has_active_job():
                raise ValueError("別の学習が実行中です。完了または停止してから再開してください")
            output_directory = Path(str(job["output_path"])).resolve()
            job_directory = self._job_directory(job_id)
            attempt = int(job.get("attempt") or 1) + 1
            if overwrite_existing:
                self._reset_generated_artifacts(job_directory, output_directory)
                run_output_directory = output_directory
                resume_mode = "overwrite"
                step = 0
                progress = 0
                loss = None
            else:
                run_output_directory = (
                    output_directory / "resume-runs" / f"{attempt:03d}"
                ).resolve()
                if output_directory not in run_output_directory.parents:
                    raise ValueError("学習再開先が不正です")
                resume_mode = "skip_existing"
                step = int(job.get("step") or 0)
                progress = float(job.get("progress") or 0)
                loss = job.get("loss")
            job.update(
                status="queued",
                stage="queued",
                message=(
                    "既存成果物を削除して最初からやり直します"
                    if overwrite_existing
                    else "既存成果物を再利用して学習を再開します"
                ),
                completed_at=None,
                attempt=attempt,
                resume_mode=resume_mode,
                run_output_path=str(run_output_directory),
                step=step,
                progress=progress,
                loss=loss,
                asset_path=None,
                failure=None,
                updated_at=utc_now(),
            )
            self._write(job)
            config_path = self._config_path(str(job["method"]))
        thread = threading.Thread(
            target=self._run,
            args=(
                job_id,
                config_path,
                output_directory,
                run_output_directory,
            ),
            kwargs={
                "resume": not overwrite_existing,
                "overwrite_existing": overwrite_existing,
            },
            daemon=True,
            name=f"training-{job_id[:8]}-resume-{attempt}",
        )
        thread.start()
        return self._summary(job)

    def delete(self, job_id: str) -> None:
        with self._lock:
            job = self._read(job_id)
            if job.get("status") in {"queued", "preparing", "training", "cancelling"}:
                raise ValueError("実行中の学習は削除できません。先に停止してください")
            directory = self._job_directory(job_id)
            if directory.parent != self.training_directory:
                raise ValueError("学習ジョブの保存先が不正です")
            shutil.rmtree(directory)
