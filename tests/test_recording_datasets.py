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
            dataset_directory = root / "話者A-Core"

            self.assertTrue(dataset_directory.is_dir())
            self.assertEqual(created["workspace_path"], "workspace/recordings/話者A-Core")

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
                for line in (dataset_directory / "dataset.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(rows[0]["id"], "aica_0003")
            self.assertEqual(rows[0]["audio"], "wavs/aica_0003.wav")
            self.assertEqual(rows[0]["source_license"], "CC0-1.0")

            store.delete(dataset_id)
            self.assertFalse(dataset_directory.exists())
            self.assertEqual(store.list(), [])

    def test_unaccepted_recording_is_not_added_to_training_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RecordingDatasetStore(root)
            dataset_id = store.create("確認中")["id"]
            dataset_directory = root / "確認中"
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

            self.assertEqual((dataset_directory / "dataset.jsonl").read_text(), "")
            self.assertEqual(store.list()[0]["recorded"], 1)
            self.assertEqual(store.list()[0]["accepted"], 0)

    def test_dataset_can_be_renamed_without_changing_its_stable_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = RecordingDatasetStore(root)
            created = store.create("仮の名前")
            dataset_id = created["id"]
            store.save_recording(
                dataset_id,
                "irodori_0001",
                empty_wav(),
                {"duration": 1, "accepted": True, "prompt": {"text": "テスト"}},
            )

            renamed = store.rename(dataset_id, "神山 メイン収録")

            self.assertEqual(renamed["id"], dataset_id)
            self.assertEqual(renamed["name"], "神山 メイン収録")
            self.assertEqual(
                renamed["workspace_path"], "workspace/recordings/神山-メイン収録"
            )
            self.assertFalse((root / "仮の名前").exists())
            self.assertTrue((root / "神山-メイン収録" / "wavs" / "irodori_0001.wav").is_file())
            self.assertEqual(store.load(dataset_id)["name"], "神山 メイン収録")

    def test_duplicate_dataset_names_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RecordingDatasetStore(Path(directory))
            first = store.create("話者A")
            second = store.create("話者B")

            with self.assertRaisesRegex(ValueError, "同じ名前"):
                store.create("話者A")
            with self.assertRaisesRegex(ValueError, "同じ名前"):
                store.rename(second["id"], "話者A")

            self.assertEqual(store.load(first["id"])["name"], "話者A")
            self.assertEqual(store.load(second["id"])["name"], "話者B")

    def test_legacy_id_directory_is_migrated_to_dataset_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = "a" * 32
            legacy = root / dataset_id
            legacy.mkdir()
            (legacy / "wavs").mkdir()
            (legacy / "dataset.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": dataset_id,
                        "name": "以前の収録",
                        "recordings": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            store = RecordingDatasetStore(root)

            self.assertFalse(legacy.exists())
            self.assertTrue((root / "以前の収録" / "dataset.json").is_file())
            self.assertEqual(store.load(dataset_id)["name"], "以前の収録")


if __name__ == "__main__":
    unittest.main()
