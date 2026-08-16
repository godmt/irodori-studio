from __future__ import annotations

import shutil
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from studio_backend.model_catalog import (
    OFFICIAL_MODELS_BY_ID,
    inspect_checkpoint,
)

DownloadFunction = Callable[[str, list[str], Path], Path]


def _download_snapshot(repo_id: str, allow_patterns: list[str], local_dir: Path) -> Path:
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=repo_id,
            allow_patterns=allow_patterns,
            local_dir=local_dir,
        )
    )


class ModelInstallManager:
    """Installs known official checkpoints through a staging directory and atomic rename."""

    def __init__(
        self,
        *,
        irodori_root: Path,
        downloader: DownloadFunction = _download_snapshot,
    ) -> None:
        self.models_root = (irodori_root / "models").resolve()
        self.staging_root = self.models_root / ".studio-downloads"
        self.downloader = downloader
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(job) for job in self._jobs.values()]

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return dict(self._jobs[job_id])

    def start(self, model_id: str) -> dict[str, Any]:
        model = OFFICIAL_MODELS_BY_ID.get(model_id)
        if model is None or not model.installable or not model.subfolder:
            raise ValueError("Studioから導入できる公式モデルではありません")
        target = (self.models_root / model.relative_directory).resolve()
        if target.parent.parent != self.models_root and target.parent != self.models_root:
            raise ValueError("モデルの導入先が不正です")
        checkpoint = target / "model.safetensors"
        if checkpoint.is_file():
            raise ValueError("このモデルは既に導入されています")
        if target.exists():
            raise ValueError("導入先に同名のフォルダーがあります")
        with self._lock:
            for job in self._jobs.values():
                if job["model_id"] == model_id and job["status"] in {"queued", "downloading", "validating"}:
                    return dict(job)
            job_id = uuid.uuid4().hex
            job = {
                "id": job_id,
                "model_id": model_id,
                "name": model.name,
                "status": "queued",
                "message": "ダウンロードを準備しています",
                "error": None,
                "target": str(target),
            }
            self._jobs[job_id] = job
        threading.Thread(target=self._run, args=(job_id,), daemon=True).start()
        return dict(job)

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            self._jobs[job_id].update(changes)

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        model = OFFICIAL_MODELS_BY_ID[job["model_id"]]
        stage = self.staging_root / job_id
        download_dir = stage / "download"
        package_dir = stage / "package"
        target = Path(job["target"])
        installed_source: str | None = None
        failure: Exception | None = None
        try:
            stage.mkdir(parents=True, exist_ok=False)
            self._update(
                job_id,
                status="downloading",
                message="公式モデルをダウンロードしています",
            )
            snapshot = self.downloader(
                model.repo_id,
                [f"{model.subfolder}/model.safetensors", "tokenizer/*"],
                download_dir,
            )
            source_checkpoint = snapshot / model.subfolder / "model.safetensors"
            source_tokenizer = snapshot / "tokenizer"
            if not source_checkpoint.is_file():
                raise FileNotFoundError("ダウンロードしたモデルが見つかりません")
            if not (source_tokenizer / "tokenizer_config.json").is_file():
                raise FileNotFoundError("ダウンロードしたTokenizerが見つかりません")

            self._update(job_id, status="validating", message="モデルを検証しています")
            inspected = inspect_checkpoint(source_checkpoint)
            if inspected["metadata_error"]:
                raise ValueError(inspected["metadata_error"])
            actual_type = (inspected["quantization"] or {}).get("quantization_type")
            expected_type = (
                "int8_weight_only"
                if model.subfolder == "int8-weight-only"
                else "int4_weight_only"
            )
            if actual_type != expected_type:
                raise ValueError("ダウンロードしたモデルの量子化方式が一致しません")

            package_dir.mkdir(parents=True, exist_ok=False)
            source_checkpoint.replace(package_dir / "model.safetensors")
            shutil.copytree(source_tokenizer, package_dir / "tokenizer")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise FileExistsError("導入先に同名のフォルダーがあります")
            package_dir.replace(target)
            installed_source = str((target / "model.safetensors").resolve())
        except Exception as exc:
            failure = exc
        finally:
            if stage.is_dir():
                shutil.rmtree(stage, ignore_errors=True)
        if failure is not None:
            self._update(
                job_id,
                status="failed",
                message="モデルを導入できませんでした",
                error=str(failure),
            )
            return
        self._update(
            job_id,
            status="completed",
            message="モデルを導入しました",
            source=installed_source,
        )
