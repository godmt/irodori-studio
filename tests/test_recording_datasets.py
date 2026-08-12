from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.recording_datasets import RecordingDatasetStore  # noqa: E402


def empty_wav() -> bytes:
    return (
        b"RIFF"
        + (36).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (48_000).to_bytes(4, "little")
        + (96_000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + (0).to_bytes(4, "little")
    )


class RecordingDatasetStoreTests(unittest.TestCase):
    def test_dataset_is_training_ready_and_deletable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RecordingDatasetStore(root)
            created = store.create("話者A Core")
            dataset_id = created["id"]

            saved = store.save_recording(
                dataset_id,
                "aica_0003",
                empty_wav(),
                {
                    "duration": 2.5,
                    "sampleRate": 48_000,
                    "preview": [0.1, 0.2],
                    "accepted": True,
                    "acceptedAt": "2026-08-12T00:00:00Z",
                    "prompt": {
                        "sourceId": "0003",
                        "text": "予定の時間です。",
                        "direction": "自然に話す",
                        "category": "daily_assistant",
                        "sourceName": "AICA corpus",
                        "sourceUrl": "https://github.com/reinehonoka/aica-corpus",
                        "sourceVersion": "v1.0.0",
                        "license": "CC0-1.0",
                    },
                },
            )

            self.assertTrue(saved["accepted"])
            self.assertTrue(store.audio_path(dataset_id, "aica_0003").is_file())
            self.assertEqual(store.list()[0]["accepted"], 1)
            self.assertEqual(store.load(dataset_id)["name"], "話者A Core")

            rows = [
                json.loads(line)
                for line in (root / dataset_id / "dataset.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(rows[0]["id"], "aica_0003")
            self.assertEqual(rows[0]["audio"], "wavs/aica_0003.wav")
            self.assertEqual(rows[0]["source_license"], "CC0-1.0")

            store.delete(dataset_id)
            self.assertFalse((root / dataset_id).exists())
            self.assertEqual(store.list(), [])

    def test_unaccepted_recording_is_not_added_to_training_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RecordingDatasetStore(root)
            dataset_id = store.create("確認中")["id"]
            store.save_recording(
                dataset_id,
                "irodori_0001",
                empty_wav(),
                {
                    "duration": 1,
                    "accepted": False,
                    "prompt": {"text": "テスト"},
                },
            )

            self.assertEqual((root / dataset_id / "dataset.jsonl").read_text(), "")
            self.assertEqual(store.list()[0]["recorded"], 1)
            self.assertEqual(store.list()[0]["accepted"], 0)


if __name__ == "__main__":
    unittest.main()
