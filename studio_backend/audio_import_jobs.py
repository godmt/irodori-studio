from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from studio_backend.audio_import_worker import PROGRESS_PREFIX
from studio_backend.time_utils import utc_now

ACTIVE_IMPORT_STATUSES = {"queued", "loading_model", "transcribing", "committing", "cancelling"}


class AudioImportJobManager:
    """Run long-audio preprocessing out of process and commit completed clips atomically."""

    def __init__(self, *, workspace: Path, recording_store: Any) -> None:
        self.workspace = workspace.resolve()
        self.recording_store = recording_store
        self.directory = self.workspace / "imports"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._recover_interrupted_jobs()

    def _job_directory(self, job_id: str) -> Path:
        if not job_id or any(char not in "0123456789abcdef" for char in job_id):
            raise KeyError(job_id)
        path = (self.directory / job_id).resolve()
        if path.parent != self.directory:
            raise KeyError(job_id)
        return path

    def _job_path(self, job_id: str) -> Path:
        return self._job_directory(job_id) / "job.json"

    def _read(self, job_id: str) -> dict[str, Any]:
        path = self._job_path(job_id)
        if not path.is_file():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, job: dict[str, Any]) -> None:
        directory = self._job_directory(str(job["id"]))
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "job.tmp"
        temporary.write_text(
            json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(directory / "job.json")

    def _update(self, job_id: str, **patch: Any) -> dict[str, Any]:
        with self._lock:
            job = self._read(job_id)
            job.update(patch)
            job["updated_at"] = utc_now()
            self._write(job)
            return job

    def _recover_interrupted_jobs(self) -> None:
        for path in self.directory.glob("*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job.get("status") in ACTIVE_IMPORT_STATUSES:
                    job["status"] = "interrupted"
                    job["stage"] = "interrupted"
                    job["message"] = "Studioの前回終了時に音声の前処理が中断されました"
                    job["updated_at"] = utc_now()
                    self._write(job)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue

    def list(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        with self._lock:
            paths = sorted(
                self.directory.glob("*/job.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            for path in paths:
                try:
                    jobs.append(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue
        return jobs

    def load(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._read(job_id)

    def has_active_job(self) -> bool:
        return any(job.get("status") in ACTIVE_IMPORT_STATUSES for job in self.list())

    def active_for_dataset(self, dataset_id: str) -> bool:
        return any(
            job.get("dataset_id") == dataset_id and job.get("status") in ACTIVE_IMPORT_STATUSES
            for job in self.list()
        )

    def create(self, payload: Any) -> dict[str, Any]:
        with self._lock:
            self.recording_store.load(payload.dataset_id)
            if self.has_active_job():
                raise ValueError(
                    "別の音声前処理が実行中です。完了または中止してから開始してください"
                )
            for source in payload.sources:
                path = Path(source.path).expanduser().resolve()
                if not path.is_file():
                    raise FileNotFoundError(path)
            job_id = uuid4().hex
            job_directory = self._job_directory(job_id)
            job_directory.mkdir(parents=True, exist_ok=False)
            payload_data = payload.model_dump(mode="json")
            payload_data["sources"] = self.recording_store.preserve_raw_sources(
                payload.dataset_id, payload_data["sources"]
            )
            settings = {
                key: value
                for key, value in payload_data.items()
                if key not in {"dataset_id", "sources"}
            }
            config = {
                "job_id": job_id,
                "dataset_id": payload.dataset_id,
                "sources": payload_data["sources"],
                "settings": settings,
            }
            (job_directory / "config.json").write_text(
                json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            now = utc_now()
            job = {
                "schema_version": 1,
                "id": job_id,
                "dataset_id": payload.dataset_id,
                "status": "queued",
                "stage": "queued",
                "message": "前処理を開始します",
                "percent": 0.0,
                "candidate_count": 0,
                "accepted_count": 0,
                "created_at": now,
                "updated_at": now,
                "sources": payload_data["sources"],
                "settings": settings,
            }
            self._write(job)
        thread = threading.Thread(
            target=self._run,
            args=(job_id,),
            daemon=True,
            name=f"audio-import-{job_id[:8]}",
        )
        thread.start()
        return job

    def _run(self, job_id: str) -> None:
        job_directory = self._job_directory(job_id)
        log_path = job_directory / "import.log"
        output_directory = job_directory / "output"
        output_directory.mkdir(exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "studio_backend.audio_import_worker",
            "--config",
            str(job_directory / "config.json"),
            "--output-dir",
            str(output_directory),
        ]
        try:
            self._update(
                job_id,
                status="loading_model",
                stage="loading_model",
                message="文字起こしモデルを読み込んでいます",
            )
            process = subprocess.Popen(
                command,
                cwd=Path(__file__).resolve().parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            with self._lock:
                self._processes[job_id] = process
            with log_path.open("a", encoding="utf-8", newline="\n") as log:
                assert process.stdout is not None
                for raw_line in process.stdout:
                    line = raw_line.rstrip("\r\n")
                    log.write(line + "\n")
                    log.flush()
                    if not line.startswith(PROGRESS_PREFIX):
                        continue
                    try:
                        progress = json.loads(line[len(PROGRESS_PREFIX) :])
                    except json.JSONDecodeError:
                        continue
                    stage = str(progress.get("stage") or "transcribing")
                    status = {
                        "loading_model": "loading_model",
                        "transcribing": "transcribing",
                        "completed": "committing",
                    }.get(stage, "transcribing")
                    message = {
                        "loading_model": "文字起こしモデルを読み込んでいます",
                        "transcribing": "音声を分割し、文字起こししています",
                        "completed": "前処理結果をまとめています",
                    }.get(stage, "音声を前処理しています")
                    patch = {
                        "status": status,
                        "stage": stage,
                        "message": message,
                        "percent": round(float(progress.get("percent") or 0.0), 2),
                        "candidate_count": int(progress.get("candidate_count") or 0),
                        "accepted_count": int(progress.get("accepted_count") or 0),
                    }
                    if "processed_seconds" in progress:
                        patch["processed_seconds"] = float(progress["processed_seconds"])
                    if "total_seconds" in progress:
                        patch["total_seconds"] = float(progress["total_seconds"])
                    self._update(job_id, **patch)
            exit_code = process.wait()
            with self._lock:
                self._processes.pop(job_id, None)
            current = self._read(job_id)
            if current.get("status") == "cancelling":
                self._update(
                    job_id,
                    status="cancelled",
                    stage="cancelled",
                    message="前処理を中止しました",
                )
                return
            if exit_code != 0:
                raise RuntimeError(f"音声前処理ワーカーが終了コード{exit_code}で停止しました")

            report = json.loads((output_directory / "report.json").read_text(encoding="utf-8"))
            candidates = [
                json.loads(line)
                for line in (output_directory / "candidates.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
            self._update(
                job_id,
                status="committing",
                stage="committing",
                message="処理済み音声を録音データセットへ保存しています",
                percent=100.0,
            )
            committed = self.recording_store.commit_import(
                str(current["dataset_id"]),
                candidates,
                output_directory / "clips",
                import_job_id=job_id,
                overwrite_existing=bool(
                    (current.get("settings") or {}).get("overwrite_existing", False)
                ),
            )
            self._update(
                job_id,
                status="completed",
                stage="completed",
                message="前処理が完了しました",
                percent=100.0,
                report=report,
                committed=committed,
                candidate_count=int(report["candidate_count"]),
                accepted_count=int(report["accepted_count"]),
            )
        except Exception as exc:
            with self._lock:
                self._processes.pop(job_id, None)
            try:
                current = self._read(job_id)
                if current.get("status") == "cancelling":
                    self._update(
                        job_id,
                        status="cancelled",
                        stage="cancelled",
                        message="前処理を中止しました",
                    )
                else:
                    self._update(
                        job_id,
                        status="failed",
                        stage="failed",
                        message=str(exc),
                    )
            except Exception:
                pass

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._read(job_id)
            if job.get("status") not in ACTIVE_IMPORT_STATUSES:
                return job
            job = self._update(
                job_id,
                status="cancelling",
                stage="cancelling",
                message="前処理を中止しています",
            )
            process = self._processes.get(job_id)
            if process is not None and process.poll() is None:
                process.terminate()
            return job

    def delete(self, job_id: str) -> None:
        with self._lock:
            job = self._read(job_id)
            if job.get("status") in ACTIVE_IMPORT_STATUSES:
                raise ValueError("実行中の音声前処理は削除できません")
            directory = self._job_directory(job_id)
            if directory.parent != self.directory:
                raise ValueError("音声前処理ジョブの保存先が不正です")
            shutil.rmtree(directory)
