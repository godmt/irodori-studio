from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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


class ProjectSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project: dict[str, Any]


class ProjectRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AudioReleaseRequest(BaseModel):
    audio_files: list[str] = Field(default_factory=list, max_length=256)
    project_name: str | None = Field(default=None, max_length=120)


class RecordingDatasetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RecordingDatasetRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TrainingJobCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    dataset_id: str = Field(min_length=1, max_length=96)
    method: Literal["speaker_inversion", "lora"] = "speaker_inversion"
    checkpoint: str | None = None
    device: str = "cuda"
    precision: Literal["fp32", "bf16"] = "bf16"
    max_steps: int = Field(default=3000, ge=1, le=1_000_000)

    @field_validator("checkpoint", mode="before")
    @classmethod
    def training_empty_checkpoint_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class TrainedModelRenameRequest(BaseModel):
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


class VoiceProfileRequest(BaseModel):
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
