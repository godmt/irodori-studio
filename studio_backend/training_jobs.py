from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from studio_backend.audio_preprocessing import (
    EDGE_SILENCE_PADDING_MS,
    EDGE_SILENCE_THRESHOLD_DBFS,
    EDGE_SILENCE_WINDOW_MS,
    TRAINING_LOUDNESS_DB,
    trim_wav_edge_silence,
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
_STEP_PATTERN = re.compile(r"(?:step=|\|\s*)(\d+)(?:/|\s)")
_LOSS_PATTERN = re.compile(r"loss=([0-9.eE+-]+)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
                if job.get("status") in {"queued", "preparing", "training", "cancelling"}:
                    job["status"] = "interrupted"
                    job["stage"] = "interrupted"
                    job["message"] = "Studioの前回終了時に学習が中断されました"
                    job["updated_at"] = _now()
                    self._write(job)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue

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
            model["updated_at"] = _now()
            temporary = manifest.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(manifest)
            try:
                job = self._read(model_id)
                job["name"] = normalized
                job["updated_at"] = _now()
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
    def _summary(job: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in job.items() if key != "command"}

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
                    jobs.append(self._summary(job))
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                    continue
        return jobs

    def load(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._summary(self._read(job_id))

    def _dataset_rows(self, dataset_id: str, job_directory: Path) -> dict[str, Any]:
        dataset = self.recording_store.load(dataset_id)
        source_root = self.recording_store.dataset_directory(dataset_id)
        accepted = [
            recording
            for recording in dataset.get("recordings", {}).values()
            if recording.get("accepted")
        ]
        if not accepted:
            raise ValueError("採用済みの録音がないため学習を開始できません")
        rows = []
        audio_directory = job_directory / "prepared-audio"
        audio_directory.mkdir(parents=True, exist_ok=True)
        file_results = []
        for recording in accepted:
            prompt = recording.get("prompt", {})
            source_audio = (source_root / recording["audio"]).resolve()
            prepared_audio = (audio_directory / f"{recording['prompt_id']}.wav").resolve()
            result = trim_wav_edge_silence(source_audio, prepared_audio)
            file_results.append(
                {
                    "prompt_id": recording["prompt_id"],
                    "source_audio": str(source_audio),
                    "prepared_audio": str(prepared_audio),
                    **result,
                }
            )
            rows.append(
                {
                    "audio": str(prepared_audio),
                    "text": prompt.get("text", ""),
                    "caption": prompt.get("direction", ""),
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
            "trimmed_files": sum(result["status"] == "trimmed" for result in file_results),
            "unchanged_files": sum(result["status"] == "unchanged" for result in file_results),
            "no_activity_files": sum(result["status"] == "no_activity" for result in file_results),
            "unsupported_files": sum(result["status"] in {"unsupported", "empty"} for result in file_results),
            "trimmed_seconds": round(sum(result["trimmed_seconds"] for result in file_results), 6),
            "edge_silence": {
                "threshold_dbfs": EDGE_SILENCE_THRESHOLD_DBFS,
                "window_ms": EDGE_SILENCE_WINDOW_MS,
                "padding_ms": EDGE_SILENCE_PADDING_MS,
                "internal_silence": "preserved",
            },
            "loudness_target_db": TRAINING_LOUDNESS_DB,
            "source_recordings_modified": False,
            "results": file_results,
        }
        (job_directory / "preprocessing.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return summary

    def create(self, payload: Any) -> dict[str, Any]:
        name = payload.name.strip()
        if not name:
            raise ValueError("モデル名を入力してください")
        dataset = self.recording_store.load(payload.dataset_id)
        if int(dataset.get("accepted") or 0) <= 0:
            raise ValueError("採用済みの録音がないため学習を開始できません")
        if not (self.irodori_root / "train.py").is_file():
            raise FileNotFoundError("Irodori-TTSのtrain.pyが見つかりません")
        if any(
            job.get("status") in {"queued", "preparing", "training", "cancelling"}
            for job in self.list()
        ):
            raise ValueError("別の学習が実行中です。完了または停止してから開始してください")

        method = payload.method
        job_id = uuid4().hex
        job_directory = self._job_directory(job_id)
        job_directory.mkdir(parents=True, exist_ok=False)
        slug = _safe_slug(name)
        output_root = self.speaker_directory if method == "speaker_inversion" else self.lora_directory
        output_directory = (output_root / f"{slug}-{job_id[:8]}").resolve()
        config_name = (
            "train_v4_small_speaker_inversion.yaml"
            if method == "speaker_inversion"
            else "train_v4_small_lora.yaml"
        )
        config_path = self.irodori_root / "configs" / config_name
        if not config_path.is_file():
            raise FileNotFoundError(f"Irodori-TTSの学習設定が見つかりません: {config_name}")

        created_at = _now()
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
            "preprocessing": None,
            "log_path": str((job_directory / "training.log").resolve()),
            "command": [],
        }
        with self._lock:
            self._write(job)
        thread = threading.Thread(
            target=self._run,
            args=(job_id, config_path, output_directory),
            daemon=True,
            name=f"training-{job_id[:8]}",
        )
        thread.start()
        return self._summary(job)

    def _update(self, job_id: str, **patch: Any) -> dict[str, Any]:
        with self._lock:
            job = self._read(job_id)
            job.update(patch)
            job["updated_at"] = _now()
            self._write(job)
            return job

    def _run(self, job_id: str, config_path: Path, output_directory: Path) -> None:
        job_directory = self._job_directory(job_id)
        log_path = job_directory / "training.log"
        try:
            job = self._read(job_id)
            preprocessing = self._dataset_rows(job["dataset_id"], job_directory)
            row_count = int(preprocessing["files"])
            preprocessing_summary = {
                key: value for key, value in preprocessing.items() if key != "results"
            }
            prepared_manifest = job_directory / "prepared-manifest.jsonl"
            latent_directory = job_directory / "latents"
            latent_directory.mkdir(exist_ok=True)

            python = Path(sys.executable).resolve()
            prepare_command = [
                str(python),
                str(self.irodori_root / "prepare_manifest.py"),
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
                str(TRAINING_LOUDNESS_DB),
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
                str(output_directory),
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
            self._update(
                job_id,
                status="preparing",
                stage="preparing",
                message=(
                    f"{row_count}件を準備中 · "
                    f"{preprocessing['trimmed_files']}件の前後無音を調整"
                ),
                preprocessing=preprocessing_summary,
                command=[prepare_command, train_command],
            )
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"[studio] model={job['name']} method={job['method']}\n")
                self._execute(job_id, prepare_command, log, stage="preparing")
                if self._read(job_id).get("status") == "cancelled":
                    return
                self._update(
                    job_id,
                    status="training",
                    stage="training",
                    message="モデルを学習しています",
                )
                output_directory.mkdir(parents=True, exist_ok=True)
                self._execute(job_id, train_command, log, stage="training")
            if self._read(job_id).get("status") == "cancelled":
                return
            asset_path = self._final_asset(job["method"], output_directory)
            model = {
                "schema_version": 1,
                "id": job_id,
                "name": job["name"],
                "method": job["method"],
                "dataset_id": job["dataset_id"],
                "dataset_name": job["dataset_name"],
                "checkpoint": job["checkpoint"],
                "created_at": _now(),
                "asset_path": str(asset_path),
                "output_path": str(output_directory),
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
                completed_at=_now(),
                asset_path=str(asset_path),
            )
        except Exception as exc:
            try:
                job = self._read(job_id)
                if job.get("status") != "cancelled":
                    self._update(
                        job_id,
                        status="failed",
                        stage="failed",
                        message=str(exc),
                        completed_at=_now(),
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
                completed_at=_now(),
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
                updated_at=_now(),
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
                    completed_at=_now(),
                )
                self._write(job)
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
