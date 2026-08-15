from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import torch
from irodori_tts.inference_runtime import (
    RuntimeKey,
    SamplingRequest,
    clear_cached_runtime,
    download_hf_checkpoint,
    get_cached_runtime,
    save_wav,
)

from studio_backend.models import ModelLoadRequest, SynthesisPayload
from studio_backend.time_utils import utc_now


@dataclass
class SynthesisJob:
    id: str
    payload: dict[str, Any]
    status: str = "queued"
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    progress: float = 0.0
    message: str = "生成待ち"
    error: str | None = None
    audio_file: str | None = None
    sample_rate: int | None = None
    duration: float | None = None
    generation_seconds: float | None = None
    used_seed: int | None = None
    stage_timings: list[tuple[str, float]] = field(default_factory=list)
    runtime_messages: list[str] = field(default_factory=list)
    cancel_requested: bool = False

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("payload", None)
        return data


class StudioEngine:
    def __init__(self, *, audio_dir: Path) -> None:
        self.audio_dir = audio_dir
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, SynthesisJob] = {}
        self._jobs_lock = threading.RLock()
        self._runtime_lock = threading.RLock()
        self._runtime = None
        self._runtime_key: RuntimeKey | None = None
        self._model_info: dict[str, Any] | None = None
        self._model_loading = False
        self._model_error: str | None = None
        self._queue: queue.Queue[str] = queue.Queue()
        self._job_condition = threading.Condition(self._jobs_lock)
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def load_model(self, request: ModelLoadRequest) -> dict[str, Any]:
        self._model_loading = True
        self._model_error = None
        try:
            checkpoint_raw = request.checkpoint.strip()
            if not checkpoint_raw:
                raise ValueError("checkpoint is required")
            local_path = Path(checkpoint_raw).expanduser()
            if local_path.suffix.lower() in {".pt", ".safetensors"}:
                if not local_path.is_file():
                    raise FileNotFoundError(f"Checkpoint not found: {local_path}")
                checkpoint = str(local_path.resolve())
            else:
                checkpoint = str(download_hf_checkpoint(checkpoint_raw))

            key = RuntimeKey(
                checkpoint=checkpoint,
                model_device=request.model_device,
                model_precision=request.model_precision,
                codec_device=request.codec_device,
                codec_precision=request.codec_precision,
                compile_model=request.compile_model,
                compile_dynamic=request.compile_dynamic,
            )
            started = time.perf_counter()
            with self._runtime_lock:
                runtime, reloaded = get_cached_runtime(key)
                self._runtime = runtime
                self._runtime_key = key
                self._model_info = {
                    "loaded": True,
                    "checkpoint": checkpoint,
                    "name": Path(checkpoint).parent.name or Path(checkpoint).stem,
                    "model_device": key.model_device,
                    "model_precision": key.model_precision,
                    "codec_device": key.codec_device,
                    "codec_precision": key.codec_precision,
                    "use_caption_condition": bool(runtime.model_cfg.use_caption_condition),
                    "use_speaker_condition": bool(runtime.model_cfg.use_speaker_condition_resolved),
                    "use_duration_predictor": bool(runtime.model_cfg.use_duration_predictor),
                    "max_text_len": runtime.default_text_max_len,
                    "max_caption_len": runtime.default_caption_max_len,
                    "max_ref_seconds": runtime.default_max_ref_seconds,
                    "parameter_count": sum(
                        parameter.numel() for parameter in runtime.model.parameters()
                    ),
                    "reloaded": bool(reloaded),
                    "load_seconds": time.perf_counter() - started,
                }
            self._model_loading = False
            return self.status()
        except Exception as exc:
            self._model_error = str(exc)
            self._model_loading = False
            raise

    def unload_model(self) -> dict[str, Any]:
        with self._runtime_lock:
            clear_cached_runtime()
            self._runtime = None
            self._runtime_key = None
            self._model_info = None
        return self.status()

    def status(self) -> dict[str, Any]:
        info = dict(self._model_info or {"loaded": False})
        info["loading"] = self._model_loading
        info["load_error"] = self._model_error
        info["queue_depth"] = self._queue.qsize()
        with self._jobs_lock:
            info["running_jobs"] = sum(job.status == "running" for job in self.jobs.values())
        if torch.cuda.is_available():
            properties = torch.cuda.get_device_properties(0)
            info["cuda"] = {
                "name": torch.cuda.get_device_name(0),
                "total_gb": round(properties.total_memory / 1024**3, 2),
                "allocated_gb": round(torch.cuda.memory_allocated(0) / 1024**3, 2),
                "reserved_gb": round(torch.cuda.memory_reserved(0) / 1024**3, 2),
            }
        else:
            info["cuda"] = None
        return info

    def create_job(self, payload: SynthesisPayload) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        job = SynthesisJob(id=job_id, payload=payload.model_dump())
        with self._jobs_lock:
            self.jobs[job_id] = job
        self._queue.put(job_id)
        return job.public_dict()

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job.public_dict()

    def wait_for_job(self, job_id: str, timeout: float = 300.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        with self._job_condition:
            while True:
                job = self.jobs.get(job_id)
                if job is None:
                    raise KeyError(job_id)
                if job.status in {"completed", "failed", "cancelled"}:
                    return job.public_dict()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Synthesis timed out: {job_id}")
                self._job_condition.wait(min(remaining, 1.0))

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._jobs_lock:
            ordered = sorted(self.jobs.values(), key=lambda item: item.created_at, reverse=True)
            return [job.public_dict() for job in ordered[:limit]]

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._jobs_lock:
            job = self.jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            job.cancel_requested = True
            if job.status == "queued":
                job.status = "cancelled"
                job.message = "キャンセル済み"
                job.finished_at = utc_now()
            elif job.status == "running":
                job.message = "停止要求済み（現在の推論完了後に破棄）"
            self._job_condition.notify_all()
            return job.public_dict()

    def cancel_all(self) -> list[dict[str, Any]]:
        with self._jobs_lock:
            ids = [job.id for job in self.jobs.values() if job.status in {"queued", "running"}]
        return [self.cancel_job(job_id) for job_id in ids]

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        with self._jobs_lock:
            job = self.jobs.get(job_id)
            if job is None or job.status == "cancelled":
                return
            job.status = "running"
            job.started_at = utc_now()
            job.progress = 0.1
            job.message = "音声を生成しています"
            payload = SynthesisPayload.model_validate(job.payload)
            self._job_condition.notify_all()

        started = time.perf_counter()
        try:
            with self._runtime_lock:
                runtime = self._runtime
                if runtime is None:
                    raise RuntimeError("モデルがロードされていません")
                ref_wavs = [
                    self._validated_file(path, "reference audio") for path in payload.ref_wavs
                ]
                ref_embed = (
                    self._validated_file(payload.ref_embed, "speaker embedding")
                    if payload.ref_embed
                    else None
                )
                lora_adapter = (
                    self._validated_directory(payload.lora_adapter, "LoRA adapter")
                    if payload.lora_adapter
                    else None
                )
                if ref_wavs and ref_embed:
                    raise ValueError("Reference audio and speaker embedding cannot be combined")
                no_ref = bool(payload.no_ref or (not ref_wavs and ref_embed is None))
                result = runtime.synthesize(
                    SamplingRequest(
                        text=payload.text,
                        caption=payload.caption,
                        ref_wavs=ref_wavs or None,
                        ref_embed=ref_embed,
                        no_ref=no_ref,
                        num_candidates=1,
                        decode_mode="sequential",
                        seconds=payload.seconds,
                        duration_scale=1.0 / payload.speed,
                        num_steps=payload.num_steps,
                        seed=payload.seed,
                        cfg_guidance_mode=payload.cfg_guidance_mode,
                        cfg_scale_text=payload.cfg_scale_text,
                        cfg_scale_caption=payload.cfg_scale_caption,
                        cfg_scale_speaker=payload.cfg_scale_speaker,
                        cfg_min_t=payload.cfg_min_t,
                        cfg_max_t=payload.cfg_max_t,
                        t_schedule_mode=payload.t_schedule_mode,
                        sway_coeff=payload.sway_coeff,
                        truncation_factor=payload.truncation_factor,
                        rescale_k=payload.rescale_k,
                        rescale_sigma=payload.rescale_sigma,
                        speaker_kv_scale=payload.speaker_kv_scale,
                        speaker_kv_min_t=payload.speaker_kv_min_t,
                        speaker_kv_max_layers=payload.speaker_kv_max_layers,
                        context_kv_cache=payload.context_kv_cache,
                        trim_tail=payload.trim_tail,
                        lora_adapter=lora_adapter,
                    )
                )

            line_stem = str(payload.line_id or "line").replace("/", "-").replace("\\", "-")
            audio_name = f"{line_stem[:48]}-{job_id[:10]}.wav"
            output_path = save_wav(
                self.audio_dir / audio_name,
                result.audio.float(),
                result.sample_rate,
            )
            duration = result.audio.shape[-1] / result.sample_rate
            metadata = {
                "job_id": job_id,
                "line_id": payload.line_id,
                "text": payload.text,
                "caption": payload.caption,
                "audio_file": output_path.name,
                "sample_rate": result.sample_rate,
                "duration": duration,
                "used_seed": result.used_seed,
                "stage_timings": result.stage_timings,
                "runtime_messages": result.messages,
                "created_at": utc_now(),
            }
            metadata_path = output_path.with_suffix(".json")
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            with self._jobs_lock:
                if job.cancel_requested:
                    output_path.unlink(missing_ok=True)
                    metadata_path.unlink(missing_ok=True)
                    job.status = "cancelled"
                    job.message = "生成完了後に破棄しました"
                else:
                    job.status = "completed"
                    job.progress = 1.0
                    job.message = "生成完了"
                    job.audio_file = output_path.name
                    job.sample_rate = result.sample_rate
                    job.duration = duration
                    job.used_seed = result.used_seed
                    job.stage_timings = result.stage_timings
                    job.runtime_messages = result.messages
                job.generation_seconds = time.perf_counter() - started
                job.finished_at = utc_now()
                self._job_condition.notify_all()
        except Exception as exc:
            with self._jobs_lock:
                job.status = "failed"
                job.error = str(exc)
                job.message = "生成に失敗しました"
                job.finished_at = utc_now()
                job.generation_seconds = time.perf_counter() - started
                self._job_condition.notify_all()

    @staticmethod
    def _validated_file(raw_path: str, label: str) -> str:
        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
        return str(path.resolve())

    @staticmethod
    def _validated_directory(raw_path: str, label: str) -> str:
        path = Path(raw_path).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"{label} not found: {path}")
        return str(path.resolve())
