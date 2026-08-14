from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from studio_backend.audio_utils import read_mono_audio, resample_linear
from studio_backend.models import SynthesisPayload
from studio_backend.voice_profiles import VoiceProfileStore

ADAPTER_VERSION = "1.0.0"
ENGINE_UUID = "82ba99d7-74a2-5e8b-a3c5-2d62d3998759"
TRANSPARENT_PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAHnOcQAAAAABJRU5ErkJggg=="
    )
).decode("ascii")


class AudioQuery(BaseModel):
    model_config = ConfigDict(extra="allow")

    accent_phrases: list[dict[str, Any]] = Field(default_factory=list)
    speedScale: float = Field(default=1.0, gt=0.0, le=4.0)
    pitchScale: float = 0.0
    intonationScale: float = 1.0
    volumeScale: float = Field(default=1.0, ge=0.0, le=4.0)
    prePhonemeLength: float = Field(default=0.1, ge=0.0, le=10.0)
    postPhonemeLength: float = Field(default=0.1, ge=0.0, le=10.0)
    pauseLength: float | None = None
    pauseLengthScale: float = 1.0
    outputSamplingRate: int = Field(default=48_000, ge=8_000, le=192_000)
    outputStereo: bool = False
    kana: str | None = None
    irodori: dict[str, Any] | None = None


def _audio_query(text: str) -> AudioQuery:
    return AudioQuery(
        accent_phrases=[
            {
                "moras": [
                    {
                        "text": text,
                        "consonant": None,
                        "consonant_length": None,
                        "vowel": "a",
                        "vowel_length": 0.0,
                        "pitch": 0.0,
                    }
                ],
                "accent": 1,
                "pause_mora": None,
                "is_interrogative": text.rstrip().endswith(("?", "？")),
            }
        ],
        kana=text,
        irodori={"schemaVersion": 1, "requestId": uuid.uuid4().hex, "text": text},
    )


def _render_wav(path: Path, query: AudioQuery) -> bytes:
    mono, sample_rate = read_mono_audio(path)
    mono = np.clip(mono * max(0.0, min(float(query.volumeScale), 4.0)), -1.0, 1.0)
    target_rate = int(query.outputSamplingRate or 48_000)
    if target_rate < 8_000 or target_rate > 192_000:
        raise ValueError("outputSamplingRate must be between 8000 and 192000")
    mono = resample_linear(mono, sample_rate, target_rate)
    pre = np.zeros(round(max(0.0, min(query.prePhonemeLength, 10.0)) * target_rate))
    post = np.zeros(round(max(0.0, min(query.postPhonemeLength, 10.0)) * target_rate))
    mono = np.concatenate([pre, mono, post]).astype(np.float32)
    output = np.column_stack([mono, mono]) if query.outputStereo else mono
    buffer = io.BytesIO()
    sf.write(buffer, output, target_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def _profile_payload(profile: dict[str, Any], query: AudioQuery, text: str) -> SynthesisPayload:
    # The profile speed is exposed as AudioQuery.speedScale.  Use the value sent
    # back by the client directly so a round trip does not apply it twice.
    speed = max(0.5, min(float(query.speedScale), 2.0))
    source_type = profile.get("source_type", "none")
    return SynthesisPayload.model_validate(
        {
            "line_id": f"voicevox-{uuid.uuid4().hex}",
            "text": text,
            "caption": profile.get("default_caption") or None,
            "ref_wavs": profile.get("ref_wavs", []) if source_type == "reference" else [],
            "ref_embed": profile.get("ref_embed") if source_type == "speaker" else None,
            "no_ref": source_type == "none",
            "lora_adapter": profile.get("lora_adapter") or None,
            "speed": speed,
            "num_steps": profile.get("num_steps", 12),
            "seed": profile.get("seed"),
            "cfg_scale_text": profile.get("cfg_scale_text", 3.0),
            "cfg_scale_caption": profile.get("cfg_scale_caption", 3.0),
            "cfg_scale_speaker": profile.get("cfg_scale_speaker", 5.0),
            "trim_tail": True,
        }
    )


def _speaker_groups(store: VoiceProfileStore) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for profile in store.list(enabled_only=True):
        speaker_uuid = profile["speaker_uuid"]
        group = groups.setdefault(
            speaker_uuid,
            {
                "name": profile["name"],
                "speaker_uuid": speaker_uuid,
                "styles": [],
                "version": "1.0.0",
                "supported_features": {"permitted_synthesis_morphing": "NOTHING"},
            },
        )
        group["styles"].append(
            {"name": profile.get("style_name", "ノーマル"), "id": profile["style_id"], "type": "talk"}
        )
    return list(groups.values())


def create_voicevox_app(
    *, engine: Any, profile_store: VoiceProfileStore, port: int = 50021, max_queue: int = 16
) -> FastAPI:
    app = FastAPI(
        title="Irodori-TTS VOICEVOX Compatibility Engine",
        description="VOICEVOX HTTP API compatible adapter for local Irodori-TTS inference.",
        version=ADAPTER_VERSION,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|app://.*|chrome-extension://.*)$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def declare_json_utf8(request: Request, call_next: Any) -> Response:
        # Windows PowerShell 5.1 otherwise decodes Japanese JSON using the
        # system code page.  VOICEVOX clients accept the explicit charset.
        response = await call_next(request)
        if response.headers.get("content-type") == "application/json":
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response

    def resolve_style(style_id: int) -> dict[str, Any]:
        try:
            return profile_store.get_by_style_id(style_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown speaker style: {style_id}") from exc

    @app.get("/")
    def root() -> str:
        return "Irodori-TTS VOICEVOX Compatibility Engine"

    @app.get("/version")
    def version() -> str:
        return ADAPTER_VERSION

    @app.get("/core_versions")
    def core_versions() -> list[str]:
        return [ADAPTER_VERSION]

    @app.get("/supported_devices")
    def supported_devices() -> dict[str, bool]:
        status = engine.status()
        return {"cpu": True, "cuda": status.get("cuda") is not None, "dml": False}

    @app.get("/engine_manifest")
    def engine_manifest() -> dict[str, Any]:
        def feature(value: bool, name: str) -> dict[str, Any]:
            return {"type": "bool", "value": value, "name": name}

        return {
            "manifest_version": "0.13.1",
            "name": "Irodori-TTS Compatibility Engine",
            "brand_name": "Irodori-TTS",
            "uuid": ENGINE_UUID,
            "url": "https://github.com/Aratako/Irodori-TTS",
            "icon": TRANSPARENT_PNG,
            "default_sampling_rate": 48_000,
            "frame_rate": 50.0,
            "terms_of_service": "Irodori-TTSおよび使用する音声モデルの利用条件に従ってください。",
            "update_infos": [],
            "dependency_licenses": [],
            "supported_features": {
                "adjust_mora_pitch": feature(False, "モーラごとの音高の調整"),
                "adjust_phoneme_length": feature(False, "音素ごとの長さの調整"),
                "adjust_speed_scale": feature(True, "全体の話速の調整"),
                "adjust_pitch_scale": feature(False, "全体の音高の調整"),
                "adjust_intonation_scale": feature(False, "全体の抑揚の調整"),
                "adjust_volume_scale": feature(True, "全体の音量の調整"),
                "adjust_pause_length": feature(False, "句読点などの無音時間の調整"),
                "interrogative_upspeak": feature(False, "疑問文の自動調整"),
                "synthesis_morphing": feature(False, "モーフィング"),
                "sing": feature(False, "歌唱音声合成"),
                "manage_library": feature(False, "音声ライブラリ管理"),
                "return_resource_url": feature(False, "リソースURL返却"),
                "apply_katakana_english": feature(False, "英単語のカタカナ読み"),
            },
        }

    @app.get("/speakers")
    def speakers(core_version: str | None = None) -> list[dict[str, Any]]:
        del core_version
        return _speaker_groups(profile_store)

    @app.get("/speaker_info")
    def speaker_info(
        speaker_uuid: str,
        resource_format: str = Query(default="base64", pattern="^(base64|url)$"),
        core_version: str | None = None,
    ) -> dict[str, Any]:
        del resource_format, core_version
        profiles = [
            profile
            for profile in profile_store.list(enabled_only=True)
            if profile["speaker_uuid"] == speaker_uuid
        ]
        if not profiles:
            raise HTTPException(status_code=404, detail="Speaker not found")
        return {
            "policy": profiles[0].get("policy") or "ローカル音声プロファイルの利用条件に従ってください。",
            "portrait": TRANSPARENT_PNG,
            "style_infos": [
                {
                    "id": profile["style_id"],
                    "icon": TRANSPARENT_PNG,
                    "portrait": TRANSPARENT_PNG,
                    "voice_samples": [],
                }
                for profile in profiles
            ],
        }

    @app.get("/singers")
    def singers(core_version: str | None = None) -> list[Any]:
        del core_version
        return []

    @app.get("/presets")
    def presets() -> list[dict[str, Any]]:
        return [
            {
                "id": profile["style_id"],
                "name": f'{profile["name"]} / {profile.get("style_name", "ノーマル")}',
                "speaker_uuid": profile["speaker_uuid"],
                "style_id": profile["style_id"],
                "speedScale": profile.get("speed", 1.0),
                "pitchScale": 0.0,
                "intonationScale": 1.0,
                "volumeScale": 1.0,
                "prePhonemeLength": 0.1,
                "postPhonemeLength": 0.1,
                "pauseLength": None,
                "pauseLengthScale": 1.0,
            }
            for profile in profile_store.list(enabled_only=True)
        ]

    @app.post("/audio_query")
    def audio_query(text: str, speaker: int, enable_katakana_english: bool = True, core_version: str | None = None) -> dict[str, Any]:
        del enable_katakana_english, core_version
        profile = resolve_style(speaker)
        cleaned = text.strip()
        if not cleaned:
            raise HTTPException(status_code=422, detail="text must not be empty")
        if len(cleaned) > 1000:
            raise HTTPException(status_code=413, detail="text is too long")
        query = _audio_query(cleaned)
        query.speedScale = profile.get("speed", 1.0)
        return query.model_dump()

    @app.post("/audio_query_from_preset")
    def audio_query_from_preset(text: str, preset_id: int, enable_katakana_english: bool = True) -> dict[str, Any]:
        del enable_katakana_english
        profile = resolve_style(preset_id)
        cleaned = text.strip()
        if not cleaned:
            raise HTTPException(status_code=422, detail="text must not be empty")
        if len(cleaned) > 1000:
            raise HTTPException(status_code=413, detail="text is too long")
        query = _audio_query(cleaned)
        query.speedScale = profile.get("speed", 1.0)
        return query.model_dump()

    @app.post("/initialize_speaker")
    def initialize_speaker(speaker: int, skip_reinit: bool = False) -> None:
        del skip_reinit
        resolve_style(speaker)
        return None

    @app.get("/is_initialized_speaker")
    def is_initialized_speaker(speaker: int) -> bool:
        resolve_style(speaker)
        return True

    @app.post("/synthesis")
    def synthesis(query: AudioQuery, speaker: int, enable_interrogative_upspeak: bool = True) -> Response:
        del enable_interrogative_upspeak
        profile = resolve_style(speaker)
        text = str((query.irodori or {}).get("text") or query.kana or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="AudioQuery does not contain readable text")
        if len(text) > 1000:
            raise HTTPException(status_code=413, detail="text is too long")
        status = engine.status()
        if status.get("loading"):
            raise HTTPException(status_code=503, detail="Irodori-TTS model is loading")
        if not status.get("loaded"):
            raise HTTPException(status_code=503, detail="Irodori-TTS model is not loaded")
        active = int(status.get("queue_depth", 0)) + int(status.get("running_jobs", 0))
        if active >= max_queue:
            raise HTTPException(status_code=429, detail="Synthesis queue is full")

        job = engine.create_job(_profile_payload(profile, query, text))
        try:
            result = engine.wait_for_job(job["id"], timeout=300.0)
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        if result["status"] == "failed":
            raise HTTPException(status_code=500, detail=result.get("error") or "Synthesis failed")
        if result["status"] == "cancelled":
            raise HTTPException(status_code=409, detail="Synthesis was cancelled")
        audio_path = (engine.audio_dir / Path(result["audio_file"]).name).resolve()
        if audio_path.parent != engine.audio_dir.resolve() or not audio_path.is_file():
            raise HTTPException(status_code=500, detail="Generated audio is missing")
        try:
            content = _render_wav(audio_path, query)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        ignored = []
        if query.pitchScale != 0.0:
            ignored.append("pitchScale")
        if query.intonationScale != 1.0:
            ignored.append("intonationScale")
        if query.pauseLength is not None or query.pauseLengthScale != 1.0:
            ignored.append("pauseLength")
        headers = {
            "Content-Disposition": 'inline; filename="irodori.wav"',
            "Cache-Control": "no-store",
            "X-Irodori-Adapter-Version": ADAPTER_VERSION,
        }
        if ignored:
            headers["X-Irodori-Ignored-Parameters"] = ",".join(ignored)
        return Response(content=content, media_type="audio/wav", headers=headers)

    return app
