from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from studio_backend.inference_settings import InferenceSettingsStore


class InferenceSettingsStoreTests(unittest.TestCase):
    def test_round_trip_preserves_last_successful_runtime_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".studio" / "inference.json"
            store = InferenceSettingsStore(path)
            settings = {
                "checkpoint": "Aratako/example/int8-weight-only",
                "model_device": "cuda",
                "model_precision": "bf16",
                "codec_device": "cpu",
                "codec_precision": "fp32",
            }
            store.save(settings)
            self.assertEqual(store.load(), settings)
            self.assertEqual(json.loads(path.read_text())["schema_version"], 1)

    def test_invalid_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "inference.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertIsNone(InferenceSettingsStore(path).load())


if __name__ == "__main__":
    unittest.main()
