from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.recording_datasets import RecordingDatasetStore  # noqa: E402


def empty_wav() -> bytes:
    frames = b"\x00\x00" * 4_800
    return (
        b"RIFF"
        + (36 + len(frames)).to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (48_000).to_bytes(4, "little")
        + (96_000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(frames).to_bytes(4, "little")
        + frames
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
            self.assertEqual(saved["preprocessing"]["pipeline_version"], 1)
            self.assertTrue((dataset_directory / "raw" / "recordings" / "aica_0003.wav").is_file())
            self.assertTrue(store.audio_path(dataset_id, "aica_0003").is_file())
            self.assertEqual(store.list()[0]["accepted"], 1)
            self.assertTrue(store.list()[0]["processing_ready"])
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
            self.assertFalse((dataset_directory / "dataset.json").exists())
            self.assertFalse((dataset_directory / "wavs").exists())
            self.assertTrue((dataset_directory / "raw" / "recordings" / "aica_0003.wav").is_file())
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

    def test_raw_only_human_folder_is_adopted_when_dataset_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "Usako" / "raw"
            raw.mkdir(parents=True)
            source = raw / "cast.mp3"
            source.write_bytes(b"source")

            store = RecordingDatasetStore(root)
            created = store.create("Usako")

            self.assertEqual(created["workspace_path"], "workspace/recordings/Usako")
            self.assertTrue((root / "Usako" / "dataset.json").is_file())
            self.assertEqual(source.read_bytes(), b"source")

            store.delete(created["id"])

            self.assertFalse((root / "Usako" / "dataset.json").exists())
            self.assertEqual(source.read_bytes(), b"source")

    def test_selected_import_source_is_copied_to_dataset_raw_storage_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "配信音声.mp3"
            source.write_bytes(b"original-audio")
            store = RecordingDatasetStore(root / "recordings")
            dataset_id = store.create("話者")['id']

            first = store.preserve_raw_sources(
                dataset_id, [{"path": str(source), "start_seconds": 10.0}]
            )
            second = store.preserve_raw_sources(
                dataset_id, [{"path": str(source), "start_seconds": 10.0}]
            )

            preserved = Path(first[0]["path"])
            self.assertEqual(first[0]["path"], second[0]["path"])
            self.assertEqual(first[0]["original_path"], str(source.resolve()))
            self.assertEqual(preserved.read_bytes(), b"original-audio")
            self.assertEqual(source.read_bytes(), b"original-audio")
            self.assertIn("raw", preserved.parts)

    def test_imported_flac_becomes_wav_then_can_be_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clips = root / "clips"
            clips.mkdir()
            store = RecordingDatasetStore(root / "recordings")
            dataset_id = store.create("Usako")["id"]
            clip = clips / "import_job_001_000001.flac"
            sf.write(clip, np.zeros(48_000, dtype=np.int16), 48_000, format="FLAC")
            candidate = {
                "id": "import_job_001_000001",
                "audio_file": clip.name,
                "text": "最初の文字起こし",
                "accepted": True,
                "review_state": "auto_accepted",
                "duration": 1.0,
                "sample_rate": 48_000,
                "source_name": "cast.mp3",
            }

            committed = store.commit_import(
                dataset_id, [candidate], clips, import_job_id="job"
            )

            self.assertEqual(
                committed,
                {"imported": 1, "overwritten": 0, "skipped": 0, "accepted": 1},
            )
            self.assertEqual(store.audio_path(dataset_id, candidate["id"]).suffix, ".wav")
            self.assertFalse(clip.exists())
            self.assertEqual(store.list()[0]["accepted"], 1)

            corrected = store.update_recording_review(
                dataset_id,
                candidate["id"],
                text="文字だけを修正",
                accepted=None,
            )
            self.assertTrue(corrected["accepted"])
            self.assertEqual(corrected["reviewState"], "auto_accepted")

            excluded = store.update_recording_review(
                dataset_id,
                candidate["id"],
                text="修正後の文字起こし",
                accepted=False,
            )
            self.assertEqual(excluded["prompt"]["text"], "修正後の文字起こし")
            self.assertEqual(store.list()[0]["accepted"], 0)

            accepted = store.update_recording_review(
                dataset_id, candidate["id"], text=None, accepted=True
            )
            self.assertTrue(accepted["accepted"])
            manifest = (store.dataset_directory(dataset_id) / "dataset.jsonl").read_text(
                encoding="utf-8"
            )
            self.assertIn("修正後の文字起こし", manifest)

    def test_import_defaults_to_skip_and_explicitly_overwrites_existing_wav(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clips = root / "clips"
            clips.mkdir()
            store = RecordingDatasetStore(root / "recordings")
            dataset_id = store.create("再実行")['id']
            candidate = {
                "id": "import_stable_0001",
                "audio_file": "import_stable_0001.flac",
                "text": "同じ区間です。",
                "accepted": True,
                "duration": 1.0,
                "sample_rate": 48_000,
            }
            source = clips / candidate["audio_file"]
            sf.write(source, np.zeros(48_000, dtype=np.float32), 48_000, format="FLAC")
            store.commit_import(dataset_id, [candidate], clips, import_job_id="first")
            target = store.audio_path(dataset_id, candidate["id"])
            first_bytes = target.read_bytes()

            sf.write(source, np.full(48_000, 0.25, dtype=np.float32), 48_000, format="FLAC")
            skipped = store.commit_import(dataset_id, [candidate], clips, import_job_id="second")
            self.assertEqual(skipped["skipped"], 1)
            self.assertEqual(target.read_bytes(), first_bytes)
            self.assertFalse(source.exists())

            sf.write(source, np.full(48_000, 0.25, dtype=np.float32), 48_000, format="FLAC")
            overwritten = store.commit_import(
                dataset_id,
                [candidate],
                clips,
                import_job_id="third",
                overwrite_existing=True,
            )
            self.assertEqual(overwritten["overwritten"], 1)
            self.assertNotEqual(target.read_bytes(), first_bytes)
            self.assertFalse(source.exists())

    def test_legacy_dataset_flac_is_migrated_after_wav_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "話者"
            wavs = dataset / "wavs"
            raw = dataset / "raw"
            wavs.mkdir(parents=True)
            raw.mkdir()
            (raw / "original.mp3").write_bytes(b"original")
            legacy_flac = wavs / "import_old.flac"
            sf.write(legacy_flac, np.zeros(48_000, dtype=np.float32), 48_000, format="FLAC")
            (dataset / "dataset.json").write_text(
                json.dumps(
                    {
                        "id": "dataset0001",
                        "name": "話者",
                        "recordings": {
                            "import_old": {
                                "prompt_id": "import_old",
                                "audio": "wavs/import_old.flac",
                                "accepted": True,
                                "prompt": {"text": "移行します。"},
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            store = RecordingDatasetStore(root)

            self.assertEqual(store.audio_path("dataset0001", "import_old").suffix, ".wav")
            self.assertFalse(legacy_flac.exists())
            self.assertEqual((raw / "original.mp3").read_bytes(), b"original")

    def test_legacy_dataset_wav_is_backed_up_before_canonical_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "旧データ"
            wavs = dataset / "wavs"
            wavs.mkdir(parents=True)
            legacy_wav = wavs / "sample.wav"
            samples = np.concatenate(
                (np.zeros(14_400), np.full(24_000, 0.03), np.zeros(14_400))
            ).astype(np.float32)
            sf.write(legacy_wav, samples, 48_000, subtype="PCM_16")
            legacy_bytes = legacy_wav.read_bytes()
            (dataset / "dataset.json").write_text(
                json.dumps(
                    {
                        "id": "dataset0002",
                        "name": "旧データ",
                        "recordings": {
                            "sample": {
                                "prompt_id": "sample",
                                "audio": "wavs/sample.wav",
                                "accepted": True,
                                "prompt": {"text": "移行対象です。"},
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            store = RecordingDatasetStore(root)

            loaded = store.load("dataset0002")
            backup = dataset / "raw" / "legacy-clips" / "sample.wav"
            self.assertEqual(backup.read_bytes(), legacy_bytes)
            self.assertEqual(
                loaded["recordings"]["sample"]["preprocessing"]["pipeline_version"],
                1,
            )
            self.assertTrue(loaded["processing_ready"])
            self.assertLess(
                loaded["recordings"]["sample"]["duration"],
                len(samples) / 48_000,
            )


if __name__ == "__main__":
    unittest.main()
