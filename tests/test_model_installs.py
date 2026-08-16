from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from studio_backend.model_catalog import QUANTIZATION_METADATA_KEY
from studio_backend.model_installs import ModelInstallManager


def write_fake_quantized(path: Path, quantization_type: str) -> None:
    metadata = {
        QUANTIZATION_METADATA_KEY: json.dumps(
            {
                "format_version": 1,
                "backend": "torchao",
                "quantization_type": quantization_type,
                "profile": "core",
            }
        )
    }
    header = json.dumps({"__metadata__": metadata}, separators=(",", ":")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(len(header).to_bytes(8, "little") + header)


class ModelInstallManagerTests(unittest.TestCase):
    def test_install_validates_then_atomically_exposes_complete_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def downloader(_repo: str, _patterns: list[str], local_dir: Path) -> Path:
                write_fake_quantized(
                    local_dir / "int8-weight-only" / "model.safetensors",
                    "int8_weight_only",
                )
                tokenizer = local_dir / "tokenizer"
                tokenizer.mkdir(parents=True)
                (tokenizer / "tokenizer_config.json").write_text("{}")
                (tokenizer / "tokenizer.json").write_text("{}")
                return local_dir

            manager = ModelInstallManager(irodori_root=root, downloader=downloader)
            job = manager.start("irodori-v4.1-small-int8-weight-only")
            deadline = time.monotonic() + 3
            while job["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
                time.sleep(0.01)
                job = manager.get(job["id"])

            self.assertEqual(job["status"], "completed", job.get("error"))
            target = (
                root
                / "models"
                / "Irodori-TTS-v4.1-Small-Quantized"
                / "int8-weight-only"
            )
            self.assertTrue((target / "model.safetensors").is_file())
            self.assertTrue((target / "tokenizer" / "tokenizer_config.json").is_file())
            self.assertEqual(list((root / "models" / ".studio-downloads").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
