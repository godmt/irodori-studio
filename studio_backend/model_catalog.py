from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

QUANTIZATION_METADATA_KEY = "irodori_quantization_json"
MAX_SAFETENSORS_HEADER_BYTES = 64 * 1024 * 1024

_QUANTIZATION_LABELS = {
    "int8_weight_only": "INT8 Weight-only",
    "int8_dynamic_activation_int8_weight": "INT8 Dynamic",
    "int4_weight_only": "INT4 Weight-only",
    "float8_weight_only": "FP8 Weight-only",
    "float8_dynamic_activation_float8_weight": "FP8 Dynamic",
}


@dataclass(frozen=True)
class OfficialModel:
    id: str
    name: str
    description: str
    repo_id: str
    subfolder: str | None
    relative_directory: Path
    tier: str
    recommended: bool = False
    experimental: bool = False
    installable: bool = False

    @property
    def hf_source(self) -> str:
        return f"{self.repo_id}/{self.subfolder}" if self.subfolder else self.repo_id

    @property
    def relative_checkpoint(self) -> Path:
        return self.relative_directory / "model.safetensors"


OFFICIAL_MODELS = (
    OfficialModel(
        id="irodori-v4.1-small-standard",
        name="Irodori v4.1 Small",
        description="品質を優先する標準モデル",
        repo_id="Aratako/Irodori-TTS-v4.1-Small",
        subfolder=None,
        relative_directory=Path("Irodori-TTS-v4.1-Small"),
        tier="standard",
        recommended=True,
    ),
    OfficialModel(
        id="irodori-v4.1-small-int8-weight-only",
        name="Irodori v4.1 Small INT8",
        description="品質と省VRAMのバランスを取る推奨量子化モデル",
        repo_id="Aratako/Irodori-TTS-v4.1-Small-Quantized",
        subfolder="int8-weight-only",
        relative_directory=Path("Irodori-TTS-v4.1-Small-Quantized") / "int8-weight-only",
        tier="memory-saving",
        recommended=True,
        installable=True,
    ),
    OfficialModel(
        id="irodori-v4.1-small-int4-weight-only",
        name="Irodori v4.1 Small INT4",
        description="VRAMをさらに抑える実験的な量子化モデル",
        repo_id="Aratako/Irodori-TTS-v4.1-Small-Quantized",
        subfolder="int4-weight-only",
        relative_directory=Path("Irodori-TTS-v4.1-Small-Quantized") / "int4-weight-only",
        tier="minimum-memory",
        experimental=True,
        installable=True,
    ),
)
OFFICIAL_MODELS_BY_ID = {model.id: model for model in OFFICIAL_MODELS}


def standard_checkpoint(irodori_root: Path) -> str:
    model = OFFICIAL_MODELS_BY_ID["irodori-v4.1-small-standard"]
    local = irodori_root / "models" / model.relative_checkpoint
    if local.is_file():
        inspected = inspect_checkpoint(local)
        if inspected["metadata_error"] is None and inspected["quantization"] is None:
            return str(local.resolve())
    return model.hf_source


def read_safetensors_metadata(path: Path) -> dict[str, str]:
    """Read only the bounded JSON header; model tensors never enter memory."""
    file_size = path.stat().st_size
    with path.open("rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise ValueError("Safetensorsヘッダーがありません")
        header_length = int.from_bytes(raw_length, "little", signed=False)
        if header_length <= 0 or header_length > MAX_SAFETENSORS_HEADER_BYTES:
            raise ValueError("Safetensorsヘッダーサイズが不正です")
        if 8 + header_length > file_size:
            raise ValueError("Safetensorsファイルが途中で切れています")
        header = json.loads(handle.read(header_length).decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("SafetensorsヘッダーがJSONオブジェクトではありません")
    metadata = header.get("__metadata__", {})
    if not isinstance(metadata, dict):
        raise ValueError("Safetensorsメタデータが不正です")
    return {str(key): str(value) for key, value in metadata.items()}


def parse_quantization_metadata(metadata: dict[str, str]) -> dict[str, Any] | None:
    raw = metadata.get(QUANTIZATION_METADATA_KEY)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("量子化メタデータが不正です") from exc
    if not isinstance(payload, dict):
        raise ValueError("量子化メタデータがJSONオブジェクトではありません")
    quantization_type = str(payload.get("quantization_type", "")).strip()
    if not quantization_type:
        raise ValueError("量子化方式が記録されていません")
    return {
        **payload,
        "quantization_type": quantization_type,
        "label": _QUANTIZATION_LABELS.get(quantization_type, quantization_type),
    }


def inspect_checkpoint(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    result: dict[str, Any] = {
        "path": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "quantization": None,
        "metadata_error": None,
    }
    if resolved.suffix.lower() != ".safetensors":
        return result
    try:
        result["quantization"] = parse_quantization_metadata(
            read_safetensors_metadata(resolved)
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        result["metadata_error"] = str(exc)
    return result


def _local_model_id(path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
    return f"local-{digest}"


def _display_name(path: Path) -> str:
    if path.name == "model.safetensors":
        return path.parent.name
    return path.stem


def _compatibility(
    quantization: dict[str, Any] | None,
    *,
    torchao_available: bool,
    cuda_capability: tuple[int, int] | None,
) -> tuple[bool, str | None]:
    if quantization is None:
        return True, None
    if not torchao_available:
        return False, "量子化モデルの読込に必要なTorchAOがありません"
    if quantization.get("quantization_type") == "int4_weight_only":
        if cuda_capability is None or cuda_capability < (8, 0):
            return False, "INT4にはCompute Capability 8.0以上のCUDA GPUが必要です"
    return True, None


def _entry_from_path(
    path: Path,
    *,
    official: OfficialModel | None,
    torchao_available: bool,
    cuda_capability: tuple[int, int] | None,
) -> dict[str, Any]:
    inspected = inspect_checkpoint(path)
    supported, compatibility_message = _compatibility(
        inspected["quantization"],
        torchao_available=torchao_available,
        cuda_capability=cuda_capability,
    )
    if inspected["metadata_error"]:
        supported = False
        compatibility_message = inspected["metadata_error"]
    if official and official.subfolder:
        expected_type = (
            "int8_weight_only"
            if official.subfolder == "int8-weight-only"
            else "int4_weight_only"
        )
        if (inspected["quantization"] or {}).get("quantization_type") != expected_type:
            supported = False
            compatibility_message = "公式モデルの配置と量子化メタデータが一致しません"
    elif official and inspected["quantization"] is not None:
        supported = False
        compatibility_message = "標準モデルの配置に量子化チェックポイントがあります"
    return {
        "id": official.id if official else _local_model_id(path),
        "name": official.name if official else _display_name(path),
        "description": official.description if official else "Irodori-TTSで検出したローカルモデル",
        "source": str(path.resolve()),
        "path": str(path.resolve()),
        "installed": True,
        "installable": False,
        "official": official is not None,
        "tier": official.tier if official else "custom",
        "recommended": bool(official and official.recommended),
        "experimental": bool(official and official.experimental),
        "size_bytes": inspected["size_bytes"],
        "quantization": inspected["quantization"],
        "supported": supported,
        "compatibility_message": compatibility_message,
    }


def build_model_catalog(
    irodori_root: Path,
    *,
    cuda_capability: tuple[int, int] | None = None,
    torchao_available: bool | None = None,
) -> list[dict[str, Any]]:
    models_root = irodori_root / "models"
    outputs_root = irodori_root / "outputs"
    has_torchao = (
        importlib.util.find_spec("torchao") is not None
        if torchao_available is None
        else torchao_available
    )
    official_paths = {
        (models_root / model.relative_checkpoint).resolve(): model for model in OFFICIAL_MODELS
    }
    discovered: set[Path] = set()
    for root in (models_root, outputs_root):
        if not root.is_dir():
            continue
        discovered.update(
            path.resolve()
            for path in root.glob("**/model.safetensors")
            if ".studio-downloads" not in path.parts
        )
        discovered.update(
            path.resolve()
            for path in root.glob("**/checkpoint_*.pt")
            if ".studio-downloads" not in path.parts
        )

    entries: list[dict[str, Any]] = []
    for model in OFFICIAL_MODELS:
        path = (models_root / model.relative_checkpoint).resolve()
        if path.is_file():
            entries.append(
                _entry_from_path(
                    path,
                    official=model,
                    torchao_available=has_torchao,
                    cuda_capability=cuda_capability,
                )
            )
            continue
        entries.append(
            {
                "id": model.id,
                "name": model.name,
                "description": model.description,
                "source": model.hf_source,
                "path": None,
                "installed": False,
                "installable": model.installable,
                "official": True,
                "tier": model.tier,
                "recommended": model.recommended,
                "experimental": model.experimental,
                "size_bytes": None,
                "quantization": (
                    {
                        "quantization_type": (
                            "int8_weight_only"
                            if model.subfolder == "int8-weight-only"
                            else "int4_weight_only"
                        ),
                        "label": (
                            "INT8 Weight-only"
                            if model.subfolder == "int8-weight-only"
                            else "INT4 Weight-only"
                        ),
                        "profile": "core",
                    }
                    if model.subfolder
                    else None
                ),
                "supported": (
                    has_torchao
                    and (
                        model.subfolder != "int4-weight-only"
                        or (cuda_capability is not None and cuda_capability >= (8, 0))
                    )
                )
                if model.subfolder
                else True,
                "compatibility_message": (
                    "量子化モデルの読込に必要なTorchAOがありません"
                    if model.subfolder and not has_torchao
                    else (
                        "INT4にはCompute Capability 8.0以上のCUDA GPUが必要です"
                        if model.subfolder == "int4-weight-only"
                        and (cuda_capability is None or cuda_capability < (8, 0))
                        else None
                    )
                ),
            }
        )

    for path in sorted(discovered):
        if path in official_paths:
            continue
        entries.append(
            _entry_from_path(
                path,
                official=None,
                torchao_available=has_torchao,
                cuda_capability=cuda_capability,
            )
        )
    return entries
