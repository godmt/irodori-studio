from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class NamedRequest(BaseModel):
    """Base schema for user-named resources with normalized surrounding whitespace."""

    @field_validator("name", mode="before", check_fields=False)
    @classmethod
    def strip_resource_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class ModelLoadRequest(BaseModel):
    checkpoint: str
    model_device: str = "cuda"
    model_precision: Literal["fp32", "bf16"] = "bf16"
    codec_device: str = "cuda"
    codec_precision: Literal["fp32", "bf16"] = "bf16"
    compile_model: bool = False
    compile_dynamic: bool = False


class SynthesisPayload(BaseModel):
    line_id: str | None = None
    text: str = Field(min_length=1, max_length=4000)
    caption: str | None = None
    ref_wavs: list[str] = Field(default_factory=list)
    ref_embed: str | None = None
    lora_adapter: str | None = None
    no_ref: bool = False
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    seconds: float | None = Field(default=None, gt=0.0, le=30.0)
    num_steps: int = Field(default=40, ge=1, le=120)
    seed: int | None = None
    cfg_guidance_mode: Literal["independent", "joint", "alternating"] = "independent"
    cfg_scale_text: float = Field(default=3.0, ge=0.0, le=12.0)
    cfg_scale_caption: float = Field(default=3.0, ge=0.0, le=12.0)
    cfg_scale_speaker: float = Field(default=5.0, ge=0.0, le=12.0)
    cfg_min_t: float = Field(default=0.5, ge=0.0, le=1.0)
    cfg_max_t: float = Field(default=1.0, ge=0.0, le=1.0)
    t_schedule_mode: Literal["linear", "sway"] = "linear"
    sway_coeff: float = Field(default=-1.0, ge=-2.0, le=2.0)
    truncation_factor: float | None = Field(default=None, gt=0.0)
    rescale_k: float | None = Field(default=None, gt=0.0)
    rescale_sigma: float | None = Field(default=None, gt=0.0)
    speaker_kv_scale: float | None = Field(default=None, gt=0.0)
    speaker_kv_min_t: float = Field(default=0.9, ge=0.0, le=1.0)
    speaker_kv_max_layers: int | None = Field(default=None, ge=0)
    context_kv_cache: bool = True
    trim_tail: bool = True

    @field_validator("caption", "ref_embed", "lora_adapter", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ProjectSaveRequest(NamedRequest):
    name: str = Field(min_length=1, max_length=120)
    project: dict[str, Any]


class ProjectRenameRequest(NamedRequest):
    name: str = Field(min_length=1, max_length=120)


class AudioReleaseRequest(BaseModel):
    audio_files: list[str] = Field(default_factory=list, max_length=256)
    project_name: str | None = Field(default=None, max_length=120)


class RecordingDatasetCreateRequest(NamedRequest):
    name: str = Field(min_length=1, max_length=120)


class RecordingDatasetRenameRequest(NamedRequest):
    name: str = Field(min_length=1, max_length=120)


class AudioImportSource(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    start_seconds: float = Field(default=0.0, ge=0.0)
    end_seconds: float | None = Field(default=None, gt=0.0)

    @field_validator("path", mode="before")
    @classmethod
    def strip_audio_import_path(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_audio_import_range(self) -> AudioImportSource:
        if self.end_seconds is not None and self.end_seconds <= self.start_seconds:
            raise ValueError("音声の終了位置は開始位置より後である必要があります")
        return self


class AudioImportJobCreateRequest(BaseModel):
    dataset_id: str = Field(min_length=1, max_length=96)
    sources: list[AudioImportSource] = Field(min_length=1, max_length=64)
    asr_model: str = Field(default="large-v3", min_length=1, max_length=500)
    asr_device: Literal["auto", "cuda", "cpu"] = "auto"
    asr_compute_type: str = Field(default="auto", min_length=1, max_length=40)
    asr_cpu_threads: int = Field(default=8, ge=1, le=64)
    language: str = Field(default="ja", min_length=2, max_length=16)
    beam_size: int = Field(default=5, ge=1, le=10)
    window_seconds: float = Field(default=300.0, ge=30.0, le=1800.0)
    window_overlap_seconds: float = Field(default=15.0, ge=12.0, le=60.0)
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    vad_min_speech_ms: int = Field(default=250, ge=0, le=5000)
    vad_min_silence_ms: int = Field(default=350, ge=50, le=5000)
    vad_speech_pad_ms: int = Field(default=180, ge=0, le=1000)
    merge_gap_seconds: float = Field(default=0.65, ge=0.0, le=3.0)
    min_clip_seconds: float = Field(default=1.5, ge=0.5, le=10.0)
    max_clip_seconds: float = Field(default=12.0, ge=2.0, le=30.0)
    min_text_characters: int = Field(default=2, ge=1, le=100)
    min_word_probability: float = Field(default=0.45, ge=0.0, le=1.0)
    min_avg_logprob: float = Field(default=-1.0, ge=-10.0, le=0.0)
    max_no_speech_probability: float = Field(default=0.60, ge=0.0, le=1.0)
    max_compression_ratio: float = Field(default=2.40, ge=1.0, le=10.0)
    min_rms_dbfs: float = Field(default=-45.0, ge=-120.0, le=0.0)
    max_clipping_ratio: float = Field(default=0.001, ge=0.0, le=1.0)
    max_silence_ratio: float = Field(default=0.65, ge=0.0, le=1.0)
    min_estimated_snr_db: float = Field(default=0.0, ge=0.0, le=60.0)
    auto_accept: bool = True
    overwrite_existing: bool = False

    @field_validator("dataset_id", "asr_model", "asr_compute_type", "language", mode="before")
    @classmethod
    def strip_audio_import_value(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_audio_import_settings(self) -> AudioImportJobCreateRequest:
        if self.min_clip_seconds > self.max_clip_seconds:
            raise ValueError("最短クリップ時間は最長クリップ時間以下にしてください")
        if self.window_overlap_seconds < self.max_clip_seconds:
            raise ValueError("窓の重複時間は最長クリップ時間以上にしてください")
        return self


class RecordingReviewRequest(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    accepted: bool | None = None

    @field_validator("text", mode="before")
    @classmethod
    def strip_review_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class TrainingJobCreateRequest(NamedRequest):
    name: str = Field(min_length=1, max_length=80)
    dataset_id: str = Field(min_length=1, max_length=96)
    method: Literal["speaker_inversion", "lora"] = "speaker_inversion"
    checkpoint: str | None = None
    device: str = "cuda"
    precision: Literal["fp32", "bf16"] = "bf16"
    max_steps: int = Field(default=500, ge=1, le=1_000_000)

    @model_validator(mode="before")
    @classmethod
    def apply_method_default_steps(cls, value: Any) -> Any:
        if isinstance(value, dict) and "max_steps" not in value:
            value = dict(value)
            value["max_steps"] = 1500 if value.get("method") == "lora" else 500
        return value

    @field_validator("checkpoint", mode="before")
    @classmethod
    def training_empty_checkpoint_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class JobResumeRequest(BaseModel):
    overwrite_existing: bool = False


class TrainedModelRenameRequest(NamedRequest):
    name: str = Field(min_length=1, max_length=80)


class ExportSegment(BaseModel):
    id: str
    text: str
    caption: str = ""
    voice_name: str = ""
    audio_file: str
    seed: int | None = None


class ProductionExportRequest(BaseModel):
    project_name: str = Field(default="irodori-project", min_length=1, max_length=120)
    segments: list[ExportSegment] = Field(min_length=1)
    project: dict[str, Any] = Field(default_factory=dict)
    gap_ms: int = Field(default=250, ge=0, le=5000)
    include_master: bool = True
    include_srt: bool = True
    include_vtt: bool = True
    include_csv: bool = True


class DialogRequest(BaseModel):
    kind: Literal["checkpoint", "speaker", "reference", "lora"]
    multiple: bool = False


class VoiceProfileRequest(NamedRequest):
    profile_id: str | None = None
    display_order: int | None = Field(default=None, ge=0)
    name: str = Field(min_length=1, max_length=80)
    style_name: str = Field(default="ノーマル", min_length=1, max_length=80)
    enabled: bool = False
    source_type: Literal["speaker", "reference", "none"] = "none"
    ref_embed: str | None = None
    ref_wavs: list[str] = Field(default_factory=list, max_length=32)
    lora_adapter: str | None = None
    default_caption: str = Field(default="", max_length=1000)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    num_steps: int = Field(default=12, ge=1, le=120)
    seed: int | None = None
    cfg_scale_text: float = Field(default=3.0, ge=0.0, le=12.0)
    cfg_scale_caption: float = Field(default=3.0, ge=0.0, le=12.0)
    cfg_scale_speaker: float = Field(default=5.0, ge=0.0, le=12.0)
    policy: str = Field(default="", max_length=4000)

    @field_validator("profile_id", "ref_embed", "lora_adapter", mode="before")
    @classmethod
    def profile_empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value
