#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import base64
import binascii
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

STUDIO_ROOT = Path(__file__).resolve().parent
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.runtime_paths import resolve_irodori_root

_bootstrap_parser = argparse.ArgumentParser(add_help=False)
_bootstrap_parser.add_argument("--irodori-root")
_bootstrap_args, _ = _bootstrap_parser.parse_known_args()
try:
    IRODORI_ROOT = resolve_irodori_root(STUDIO_ROOT, _bootstrap_args.irodori_root)
except RuntimeError as exc:
    raise SystemExit(str(exc)) from exc
if str(IRODORI_ROOT) not in sys.path:
    sys.path.insert(0, str(IRODORI_ROOT))

import torch
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from irodori_tts.inference_runtime import (
    default_runtime_device,
    list_available_runtime_devices,
    list_available_runtime_precisions,
)

from studio_backend.audio_import_jobs import AudioImportJobManager
from studio_backend.engine import StudioEngine
from studio_backend.exporter import create_production_zip
from studio_backend.generated_audio import delete_generated_audio_files
from studio_backend.inference_settings import InferenceSettingsStore
from studio_backend.model_catalog import build_model_catalog, standard_checkpoint
from studio_backend.model_installs import ModelInstallManager
from studio_backend.models import (
    AudioImportJobCreateRequest,
    AudioReleaseRequest,
    DialogRequest,
    JobResumeRequest,
    ModelInstallRequest,
    ModelLoadRequest,
    ProductionExportRequest,
    ProfileSynthesisRequest,
    ProjectRenameRequest,
    ProjectSaveRequest,
    RecordingDatasetCreateRequest,
    RecordingDatasetRenameRequest,
    RecordingReviewRequest,
    SynthesisPayload,
    SynthesisPlanRequest,
    TrainedModelRenameRequest,
    TrainingJobCreateRequest,
    VoiceProfileRequest,
)
from studio_backend.profile_synthesis import build_profile_synthesis_payload
from studio_backend.project_store import ProjectStore, project_audio_files
from studio_backend.recording_datasets import RecordingDatasetStore
from studio_backend.text_segmentation import split_synthesis_text
from studio_backend.training_jobs import TrainingJobManager
from studio_backend.voice_profiles import VoiceProfileStore, migrate_voice_profile_store
from studio_backend.voicevox_api import create_voicevox_app

WORKSPACE = STUDIO_ROOT / "workspace"
AUDIO_DIR = WORKSPACE / "audio"
EXPORT_DIR = WORKSPACE / "exports"
PROJECT_DIR = WORKSPACE / "projects"
RECORDING_DIR = WORKSPACE / "recordings"
MODEL_DIR = WORKSPACE / "models"
TRAINING_DIR = WORKSPACE / "training"
VOICEVOX_DIR = WORKSPACE / "voicevox"
VOICE_DIR = WORKSPACE / "voices"
for directory in (
    AUDIO_DIR,
    EXPORT_DIR,
    PROJECT_DIR,
    RECORDING_DIR,
    MODEL_DIR,
    TRAINING_DIR,
    VOICEVOX_DIR,
    VOICE_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

migrate_voice_profile_store(VOICEVOX_DIR / "profiles.json", VOICE_DIR / "profiles.json")

engine = StudioEngine(audio_dir=AUDIO_DIR)
project_store = ProjectStore(PROJECT_DIR)
recording_dataset_store = RecordingDatasetStore(RECORDING_DIR)
audio_import_job_manager = AudioImportJobManager(
    workspace=WORKSPACE,
    recording_store=recording_dataset_store,
)
voice_profile_store = VoiceProfileStore(VOICE_DIR / "profiles.json")
inference_settings_store = InferenceSettingsStore(
    STUDIO_ROOT / ".studio" / "inference.json"
)
model_install_manager = ModelInstallManager(irodori_root=IRODORI_ROOT)
voicevox_runtime: dict[str, Any] = {
    "enabled": True,
    "host": "127.0.0.1",
    "port": 50021,
}
gpu_job_launch_lock = threading.RLock()
model_notice_lock = threading.RLock()
model_runtime_notice: str | None = None
app = FastAPI(title="Irodori Studio Local API", version="0.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://terminal.local:4173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def release_generated_audio(
    audio_files: set[str] | list[str], *, exclude_project: str | None = None
) -> dict[str, int]:
    """Delete unreferenced Studio-generated WAV files and their metadata sidecars."""
    retained = project_store.referenced_audio_files(exclude_name=exclude_project)
    return delete_generated_audio_files(AUDIO_DIR, audio_files, retained=retained)


def _default_checkpoint() -> str:
    """Return the full-precision base used by training and first-run inference."""
    return standard_checkpoint(IRODORI_ROOT)


def _cuda_capability() -> tuple[int, int] | None:
    if not torch.cuda.is_available():
        return None
    try:
        return tuple(torch.cuda.get_device_capability())
    except (AssertionError, RuntimeError):
        return None


def _model_catalog() -> list[dict[str, Any]]:
    return build_model_catalog(IRODORI_ROOT, cuda_capability=_cuda_capability())


def _default_inference_settings() -> dict[str, Any]:
    device = default_runtime_device()
    precisions = list_available_runtime_precisions(device)
    precision = "bf16" if "bf16" in precisions else "fp32"
    return ModelLoadRequest(
        checkpoint=_default_checkpoint(),
        model_device=device,
        model_precision=precision,
        codec_device=device,
        codec_precision=precision,
    ).model_dump()


def _preferred_inference_settings() -> dict[str, Any]:
    saved = inference_settings_store.load()
    if saved is not None:
        try:
            return ModelLoadRequest.model_validate(saved).model_dump()
        except ValueError:
            pass
    return _default_inference_settings()


def _set_model_notice(message: str | None) -> None:
    global model_runtime_notice
    with model_notice_lock:
        model_runtime_notice = message


def _model_status() -> dict[str, Any]:
    status = engine.status()
    with model_notice_lock:
        status["notice"] = model_runtime_notice
    return status


def _asset_scan() -> dict[str, list[str]]:
    models_root = IRODORI_ROOT / "models"
    outputs_root = IRODORI_ROOT / "outputs"
    checkpoints: list[str] = []
    speakers: list[str] = []
    references: list[str] = []
    loras: list[str] = []
    if models_root.exists():
        checkpoints = [
            str(path.resolve())
            for path in models_root.glob("**/model.safetensors")
            if ".studio-downloads" not in path.parts
        ]
        checkpoints.extend(
            str(path.resolve())
            for path in models_root.glob("**/checkpoint_*.pt")
            if ".studio-downloads" not in path.parts
        )
    if outputs_root.exists():
        for path in outputs_root.glob("**/*.safetensors"):
            lowered = path.name.lower()
            if "speaker" in lowered:
                speakers.append(str(path.resolve()))
            elif path.name == "model.safetensors" or path.name.startswith("checkpoint_"):
                checkpoints.append(str(path.resolve()))
        for extension in ("*.wav", "*.flac", "*.mp3", "*.m4a", "*.ogg"):
            references.extend(str(path.resolve()) for path in outputs_root.glob(f"**/{extension}"))
        loras = [str(path.parent.resolve()) for path in outputs_root.glob("**/adapter_config.json")]
    studio_speakers = MODEL_DIR / "speaker-embeddings"
    studio_loras = MODEL_DIR / "lora"
    if studio_speakers.exists():
        speakers.extend(str(path.resolve()) for path in studio_speakers.glob("**/*.speaker.safetensors"))
    if studio_loras.exists():
        loras.extend(str(path.parent.resolve()) for path in studio_loras.glob("**/adapter_config.json"))
    return {
        "checkpoints": sorted(set(checkpoints)),
        "speaker_embeddings": sorted(set(speakers)),
        "reference_audio": sorted(set(references))[:500],
        "lora_adapters": sorted(set(loras)),
    }


training_job_manager = TrainingJobManager(
    workspace=WORKSPACE,
    irodori_root=IRODORI_ROOT,
    recording_store=recording_dataset_store,
    default_checkpoint=_default_checkpoint(),
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "irodori-studio",
        "irodori_root": str(IRODORI_ROOT),
        "model": _model_status(),
    }


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    devices = list_available_runtime_devices()
    default_device = default_runtime_device()
    return {
        "default_checkpoint": _default_checkpoint(),
        "devices": devices,
        "precisions": {device: list_available_runtime_precisions(device) for device in devices},
        "default_device": default_device,
        "inference_settings": _preferred_inference_settings(),
        "model_catalog": _model_catalog(),
        "model_installs": model_install_manager.list(),
        "assets": _asset_scan(),
        "model": _model_status(),
        "voice_profiles": voice_profile_store.list(),
        "recording_datasets": recording_dataset_store.list(),
        "audio_import_jobs": audio_import_job_manager.list(),
        "training_jobs": training_job_manager.list(),
        "trained_models": training_job_manager.models(),
        "training_paths": training_job_manager.paths(),
        "training_requirements": training_job_manager.requirements(),
        "voicevox_api": dict(voicevox_runtime),
        "irodori_root": str(IRODORI_ROOT),
    }


@app.post("/api/assets/refresh")
def refresh_assets() -> dict[str, list[str]]:
    return _asset_scan()


@app.get("/api/models")
def list_models() -> list[dict[str, Any]]:
    return _model_catalog()


@app.post("/api/models/install", status_code=202)
def install_model(request: ModelInstallRequest) -> dict[str, Any]:
    entry = next((item for item in _model_catalog() if item["id"] == request.model_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="モデルが見つかりません")
    if not entry["supported"]:
        raise HTTPException(
            status_code=409,
            detail=entry["compatibility_message"] or "この環境では利用できません",
        )
    try:
        return model_install_manager.start(request.model_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/model-installs/{job_id}")
def model_install_status(job_id: str) -> dict[str, Any]:
    try:
        return model_install_manager.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="モデル導入処理が見つかりません") from exc


@app.get("/api/voice-profiles")
def list_voice_profiles() -> list[dict[str, Any]]:
    return voice_profile_store.list()


@app.post("/api/voice-profiles")
def save_voice_profile(request: VoiceProfileRequest) -> dict[str, Any]:
    try:
        return voice_profile_store.upsert(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice profile not found") from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/voice-profiles/{profile_id}")
def delete_voice_profile(profile_id: str) -> dict[str, bool]:
    try:
        voice_profile_store.delete(profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Voice profile not found") from exc
    return {"deleted": True}


@app.post("/api/model/load")
def load_model(request: ModelLoadRequest) -> dict[str, Any]:
    try:
        status = engine.load_model(request)
        inference_settings_store.save(request.model_dump())
        _set_model_notice(None)
        return {**status, "notice": None}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/model/unload")
def unload_model() -> dict[str, Any]:
    try:
        return engine.unload_model()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/model/status")
def model_status() -> dict[str, Any]:
    return _model_status()


@app.post("/api/synthesis", status_code=202)
def synthesize(payload: SynthesisPayload) -> dict[str, Any]:
    if not engine.status().get("loaded"):
        raise HTTPException(status_code=409, detail="モデルを先にロードしてください")
    return engine.create_job(payload)


@app.post("/api/synthesis/plan")
def plan_synthesis(request: SynthesisPlanRequest) -> dict[str, Any]:
    segments = split_synthesis_text(request.text)
    return {"segments": segments, "segment_count": len(segments)}


@app.post("/api/voice-profiles/{profile_id}/synthesis", status_code=202)
def synthesize_voice_profile(
    profile_id: str, request: ProfileSynthesisRequest
) -> dict[str, Any]:
    if not engine.status().get("loaded"):
        raise HTTPException(status_code=409, detail="モデルを先にロードしてください")
    try:
        profile = voice_profile_store.get(profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="ボイスが見つかりません") from exc
    return engine.create_job(
        build_profile_synthesis_payload(
            profile,
            request.text,
            line_id=request.line_id,
            caption=request.caption,
            num_steps=request.num_steps,
            seed=request.seed,
        )
    )


@app.get("/api/jobs")
def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    return engine.list_jobs(max(1, min(limit, 200)))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    try:
        return engine.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    try:
        return engine.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.post("/api/jobs/cancel-all")
def cancel_all_jobs() -> list[dict[str, Any]]:
    return engine.cancel_all()


@app.get("/api/audio/{audio_file}")
def get_audio(audio_file: str) -> FileResponse:
    path = (AUDIO_DIR / Path(audio_file).name).resolve()
    if path.parent != AUDIO_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@app.post("/api/audio/release")
def release_audio(request: AudioReleaseRequest) -> dict[str, int]:
    return release_generated_audio(
        request.audio_files, exclude_project=request.project_name
    )


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    return project_store.list()


@app.post("/api/projects/create")
def create_project(request: ProjectSaveRequest) -> dict[str, Any]:
    try:
        return project_store.create(request.name, request.project)
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail="同じ名前のプロジェクトがすでにあります"
        ) from exc


@app.get("/api/projects/{project_name}")
def load_project(project_name: str) -> dict[str, Any]:
    try:
        return project_store.load(project_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="プロジェクトを開けませんでした") from exc


@app.post("/api/projects/save")
def save_project(request: ProjectSaveRequest) -> dict[str, Any]:
    try:
        previous = project_store.load(request.name)
    except KeyError:
        previous = None
    result = project_store.save(request.name, request.project)
    if previous is not None:
        released = release_generated_audio(
            project_audio_files(previous) - project_audio_files(request.project)
        )
        result.update(released)
    return result


@app.post("/api/projects/{project_name}/rename")
def rename_project(project_name: str, request: ProjectRenameRequest) -> dict[str, Any]:
    try:
        return project_store.rename(project_name, request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません") from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail="同じ名前のプロジェクトがすでにあります"
        ) from exc


@app.delete("/api/projects/{project_name}")
def delete_project(project_name: str) -> dict[str, Any]:
    try:
        deleted_project = project_store.delete(project_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません") from exc
    released = release_generated_audio(project_audio_files(deleted_project))
    return {"deleted": True, **released}


@app.get("/api/recording-datasets")
def list_recording_datasets() -> list[dict[str, Any]]:
    return recording_dataset_store.list()


@app.post("/api/recording-datasets")
def create_recording_dataset(
    request: RecordingDatasetCreateRequest,
) -> dict[str, Any]:
    try:
        return recording_dataset_store.create(request.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/recording-datasets/{dataset_id}")
def load_recording_dataset(dataset_id: str, corpus_only: bool = False) -> dict[str, Any]:
    try:
        return recording_dataset_store.load(dataset_id, corpus_only=corpus_only)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="録音データセットが見つかりません") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="録音データセットを開けませんでした") from exc


@app.post("/api/recording-datasets/{dataset_id}/rename")
def rename_recording_dataset(
    dataset_id: str, request: RecordingDatasetRenameRequest
) -> dict[str, Any]:
    try:
        return recording_dataset_store.rename(dataset_id, request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="録音データセットが見つかりません") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/recording-datasets/{dataset_id}/recordings/{prompt_id}")
async def save_dataset_recording(
    dataset_id: str,
    prompt_id: str,
    request: Request,
    recording_metadata: str = Header(alias="X-Irodori-Recording-Metadata"),
) -> dict[str, Any]:
    try:
        wav_bytes = await request.body()
        if len(wav_bytes) > 256 * 1024 * 1024:
            raise ValueError("録音ファイルが大きすぎます")
        metadata = json.loads(base64.b64decode(recording_metadata).decode("utf-8"))
        return recording_dataset_store.save_recording(
            dataset_id, prompt_id, wav_bytes, metadata
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="録音データセットが見つかりません") from exc
    except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/recording-datasets/{dataset_id}/audio/{prompt_id}")
def get_dataset_recording_audio(dataset_id: str, prompt_id: str) -> FileResponse:
    try:
        path = recording_dataset_store.audio_path(dataset_id, prompt_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="録音音声が見つかりません") from exc
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@app.post("/api/recording-datasets/{dataset_id}/recordings/{prompt_id}/review")
def review_dataset_recording(
    dataset_id: str,
    prompt_id: str,
    request: RecordingReviewRequest,
) -> dict[str, Any]:
    try:
        return recording_dataset_store.update_recording_review(
            dataset_id,
            prompt_id,
            text=request.text,
            accepted=request.accepted,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="録音音声が見つかりません") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/recording-datasets/{dataset_id}")
def delete_recording_dataset(dataset_id: str) -> dict[str, bool]:
    try:
        if audio_import_job_manager.active_for_dataset(dataset_id):
            raise ValueError("前処理中の録音データセットは削除できません")
        recording_dataset_store.delete(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="録音データセットが見つかりません") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"deleted": True}


@app.get("/api/audio-import-jobs")
def list_audio_import_jobs() -> list[dict[str, Any]]:
    return audio_import_job_manager.list()


@app.post("/api/audio-import-jobs", status_code=202)
def create_audio_import_job(request: AudioImportJobCreateRequest) -> dict[str, Any]:
    try:
        with gpu_job_launch_lock:
            if any(
                job.get("status") in {"queued", "preparing", "training", "cancelling"}
                for job in training_job_manager.list()
            ):
                raise ValueError("学習の実行中は音声の前処理を開始できません")
            if engine.status().get("loaded"):
                engine.unload_model()
            return audio_import_job_manager.create(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="録音データセットが見つかりません") from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/audio-import-jobs/{job_id}")
def load_audio_import_job(job_id: str) -> dict[str, Any]:
    try:
        return audio_import_job_manager.load(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="音声前処理ジョブが見つかりません") from exc


@app.post("/api/audio-import-jobs/{job_id}/cancel")
def cancel_audio_import_job(job_id: str) -> dict[str, Any]:
    try:
        return audio_import_job_manager.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="音声前処理ジョブが見つかりません") from exc


@app.post("/api/audio-import-jobs/{job_id}/resume", status_code=202)
def resume_audio_import_job(job_id: str) -> dict[str, Any]:
    try:
        with gpu_job_launch_lock:
            if training_job_manager.has_active_job():
                raise ValueError("学習が完了または停止してから音声の前処理を再開してください")
            if engine.status().get("loaded"):
                engine.unload_model()
            return audio_import_job_manager.resume(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="音声前処理ジョブが見つかりません") from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/audio-import-jobs/{job_id}")
def delete_audio_import_job(job_id: str) -> dict[str, bool]:
    try:
        audio_import_job_manager.delete(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="音声前処理ジョブが見つかりません") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"deleted": True}


@app.get("/api/training-jobs")
def list_training_jobs() -> list[dict[str, Any]]:
    return training_job_manager.list()


@app.get("/api/trained-models")
def list_trained_models() -> list[dict[str, Any]]:
    return training_job_manager.models()


@app.post("/api/trained-models/{model_id}/rename")
def rename_trained_model(
    model_id: str, request: TrainedModelRenameRequest
) -> dict[str, Any]:
    try:
        return training_job_manager.rename_model(model_id, request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="学習済みモデルが見つかりません") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/trained-models/{model_id}")
def delete_trained_model(model_id: str) -> dict[str, bool]:
    try:
        model = training_job_manager.model(model_id)
        model_roots = [
            Path(str(raw)).expanduser().resolve()
            for raw in (model.get("output_path"), model.get("asset_path"))
            if raw
        ]
        for profile in voice_profile_store.list():
            referenced = [profile.get("ref_embed"), profile.get("lora_adapter")]
            if any(
                raw
                and any(
                    Path(str(raw)).expanduser().resolve() == root
                    or root in Path(str(raw)).expanduser().resolve().parents
                    or Path(str(raw)).expanduser().resolve()
                    in root.parents
                    for root in model_roots
                )
                for raw in referenced
            ):
                raise ValueError(
                    f"ボイス「{profile['name']}」で使用中です。先にボイス設定を変更してください"
                )
        training_job_manager.delete_model(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="学習済みモデルが見つかりません") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"deleted": True}


@app.post("/api/training-jobs", status_code=202)
def create_training_job(request: TrainingJobCreateRequest) -> dict[str, Any]:
    try:
        with gpu_job_launch_lock:
            if audio_import_job_manager.has_active_job():
                raise ValueError("音声の前処理が完了してから学習を開始してください")
            dataset = recording_dataset_store.load(request.dataset_id)
            if int(dataset.get("accepted") or 0) <= 0:
                raise ValueError("採用済みの録音がないため学習を開始できません")
            if engine.status().get("loaded"):
                engine.unload_model()
            return training_job_manager.create(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="録音データセットが見つかりません") from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/training-jobs/{job_id}")
def load_training_job(job_id: str) -> dict[str, Any]:
    try:
        return training_job_manager.load(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="学習ジョブが見つかりません") from exc


@app.post("/api/training-jobs/{job_id}/cancel")
def cancel_training_job(job_id: str) -> dict[str, Any]:
    try:
        return training_job_manager.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="学習ジョブが見つかりません") from exc


@app.post("/api/training-jobs/{job_id}/resume", status_code=202)
def resume_training_job(
    job_id: str, request: JobResumeRequest
) -> dict[str, Any]:
    try:
        with gpu_job_launch_lock:
            if audio_import_job_manager.has_active_job():
                raise ValueError("音声の前処理が完了してから学習を再開してください")
            if engine.status().get("loaded"):
                engine.unload_model()
            return training_job_manager.resume(
                job_id, overwrite_existing=request.overwrite_existing
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="学習ジョブが見つかりません") from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/training-jobs/{job_id}")
def delete_training_job(job_id: str) -> dict[str, bool]:
    try:
        training_job_manager.delete(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="学習ジョブが見つかりません") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"deleted": True}


@app.post("/api/export")
def export_project(request: ProductionExportRequest) -> FileResponse:
    try:
        zip_path = create_production_zip(
            request,
            audio_dir=AUDIO_DIR,
            export_dir=EXPORT_DIR,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.post("/api/dialog")
def open_dialog(request: DialogRequest) -> dict[str, list[str]]:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        paths: tuple[str, ...] | str
        if request.kind == "lora":
            paths = filedialog.askdirectory(title="LoRAアダプターを選択")
        else:
            filetypes = {
                "checkpoint": [("Irodori checkpoint", "*.safetensors *.pt")],
                "speaker": [("Speaker embedding", "*.safetensors")],
                "reference": [("Audio", "*.wav *.flac *.mp3 *.m4a *.ogg")],
            }[request.kind]
            if request.multiple:
                paths = filedialog.askopenfilenames(title="ファイルを選択", filetypes=filetypes)
            else:
                paths = filedialog.askopenfilename(title="ファイルを選択", filetypes=filetypes)
        root.destroy()
    except Exception as exc:
        raise HTTPException(status_code=501, detail=f"File dialog unavailable: {exc}") from exc
    if isinstance(paths, str):
        values = [paths] if paths else []
    else:
        values = list(paths)
    return {"paths": values}


CLIENT_DIR = STUDIO_ROOT / "dist" / "client"
if CLIENT_DIR.is_dir():
    app.mount("/", StaticFiles(directory=CLIENT_DIR, html=True), name="studio")


def _port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _autoload_default_model() -> None:
    saved = inference_settings_store.load()
    settings = _preferred_inference_settings()
    try:
        request = ModelLoadRequest.model_validate(settings)
        print(
            f"[studio] loading {request.checkpoint} on "
            f"{request.model_device}/{request.model_precision}"
        )
        engine.load_model(request)
        _set_model_notice(None)
        print("[studio] model ready")
    except Exception as exc:
        if saved is None or settings["checkpoint"] == _default_checkpoint():
            print(f"[studio] automatic model load failed: {exc}", file=sys.stderr)
            return
        try:
            fallback = ModelLoadRequest.model_validate(_default_inference_settings())
            print(
                f"[studio] preferred model unavailable ({exc}); "
                f"falling back to {fallback.checkpoint}",
                file=sys.stderr,
            )
            engine.load_model(fallback)
            _set_model_notice(
                "前回のモデルを読み込めなかったため、標準モデルで起動しました。"
                "モデル設定を確認してください。"
            )
            print("[studio] fallback model ready")
        except Exception as fallback_exc:
            print(
                f"[studio] automatic model load failed: {fallback_exc}", file=sys.stderr
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Irodori Studio API and SPA.")
    parser.add_argument("--irodori-root", default=str(IRODORI_ROOT))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--voicevox-api", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--voicevox-host", default="127.0.0.1")
    parser.add_argument("--voicevox-port", type=int, default=50021)
    parser.add_argument(
        "--autoload-model", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--access-log",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Show Uvicorn HTTP access logs (disabled by default).",
    )
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    voicevox_runtime.update(
        enabled=args.voicevox_api,
        host=args.voicevox_host,
        port=args.voicevox_port,
    )
    if not CLIENT_DIR.is_dir():
        print("[studio] dist/client is missing. Run `npm run build` in irodori-studio.")
    url = f"http://{args.host}:{args.port}/"
    if args.voicevox_api:
        if not _port_is_available(args.voicevox_host, args.voicevox_port):
            raise SystemExit(
                f"VOICEVOX compatibility port is already in use: "
                f"{args.voicevox_host}:{args.voicevox_port}"
            )
        compatibility_app = create_voicevox_app(
            engine=engine, profile_store=voice_profile_store, port=args.voicevox_port
        )
        compatibility_server = uvicorn.Server(
            uvicorn.Config(
                compatibility_app,
                host=args.voicevox_host,
                port=args.voicevox_port,
                log_level="info",
                access_log=args.access_log,
            )
        )
        threading.Thread(target=compatibility_server.run, daemon=True).start()
        print(
            f"[voicevox-api] http://{args.voicevox_host}:{args.voicevox_port}/ "
            f"({len(voice_profile_store.list(enabled_only=True))} published styles)"
        )
    if args.autoload_model:
        threading.Thread(target=_autoload_default_model, daemon=True).start()
    if not args.no_open and args.host in {"127.0.0.1", "localhost"}:
        threading.Timer(1.25, lambda: webbrowser.open(url)).start()
    print(f"[studio] {url}")
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=args.access_log,
    )


if __name__ == "__main__":
    main()
