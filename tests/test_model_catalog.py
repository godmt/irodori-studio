from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from studio_backend.model_catalog import (
    QUANTIZATION_METADATA_KEY,
    build_model_catalog,
    inspect_checkpoint,
    standard_checkpoint,
)


def write_fake_safetensors(path: Path, quantization_type: str | None = None) -> None:
    metadata: dict[str, str] = {"config_json": "{}"}
    if quantization_type:
        metadata[QUANTIZATION_METADATA_KEY] = json.dumps(
            {
                "format_version": 1,
                "backend": "torchao",
                "quantization_type": quantization_type,
                "profile": "core",
            }
        )
    header = json.dumps({"__metadata__": metadata}, separators=(",", ":")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(len(header).to_bytes(8, "little") + header)


class ModelCatalogTests(unittest.TestCase):
    def test_standard_checkpoint_never_falls_back_to_quantized_local_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fake_safetensors(
                root
                / "models"
                / "Irodori-TTS-v4.1-Small-Quantized"
                / "int8-weight-only"
                / "model.safetensors",
                "int8_weight_only",
            )
            self.assertEqual(
                standard_checkpoint(root), "Aratako/Irodori-TTS-v4.1-Small"
            )

    def test_training_standard_rejects_quantized_checkpoint_in_standard_location(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fake_safetensors(
                root
                / "models"
                / "Irodori-TTS-v4.1-Small"
                / "model.safetensors",
                "int8_weight_only",
            )
            self.assertEqual(
                standard_checkpoint(root), "Aratako/Irodori-TTS-v4.1-Small"
            )

    def test_catalog_detects_quantization_from_metadata_not_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "models" / "renamed-by-user" / "model.safetensors"
            write_fake_safetensors(path, "int8_weight_only")
            catalog = build_model_catalog(
                root, torchao_available=True, cuda_capability=(8, 9)
            )
            entry = next(item for item in catalog if item.get("path") == str(path.resolve()))
            self.assertEqual(entry["quantization"]["label"], "INT8 Weight-only")
            self.assertTrue(entry["supported"])

    def test_official_int8_install_is_detected_with_stable_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = (
                root
                / "models"
                / "Irodori-TTS-v4.1-Small-Quantized"
                / "int8-weight-only"
                / "model.safetensors"
            )
            write_fake_safetensors(path, "int8_weight_only")
            catalog = build_model_catalog(
                root, torchao_available=True, cuda_capability=(8, 9)
            )
            entry = next(
                item
                for item in catalog
                if item["id"] == "irodori-v4.1-small-int8-weight-only"
            )
            self.assertTrue(entry["installed"])
            self.assertEqual(entry["source"], str(path.resolve()))

    def test_int4_is_rejected_on_unsupported_cuda_capability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = build_model_catalog(
                Path(temporary), torchao_available=True, cuda_capability=(7, 5)
            )
            entry = next(
                item
                for item in catalog
                if item["id"] == "irodori-v4.1-small-int4-weight-only"
            )
            self.assertFalse(entry["supported"])
            self.assertIn("8.0", entry["compatibility_message"])

    def test_incomplete_staged_download_is_never_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = (
                root
                / "models"
                / ".studio-downloads"
                / "interrupted"
                / "download"
                / "custom"
                / "model.safetensors"
            )
            write_fake_safetensors(staged, "int8_weight_only")
            catalog = build_model_catalog(
                root, torchao_available=True, cuda_capability=(8, 9)
            )
            self.assertNotIn(str(staged.resolve()), {item.get("path") for item in catalog})

    def test_inspection_reports_malformed_header_without_loading_tensors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "model.safetensors"
            path.write_bytes(b"broken")
            inspected = inspect_checkpoint(path)
            self.assertIsNotNone(inspected["metadata_error"])


if __name__ == "__main__":
    unittest.main()
