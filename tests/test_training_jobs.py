from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
import wave
from array import array
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.recording_datasets import RecordingDatasetStore  # noqa: E402
from studio_backend.training_jobs import TrainingJobManager  # noqa: E402


def empty_wav() -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(48_000)
        writer.writeframes(array("h", [0] * 4_800).tobytes())
    return output.getvalue()


class TrainingJobManagerTests(unittest.TestCase):
    def create_manager(self, root: Path) -> tuple[TrainingJobManager, RecordingDatasetStore]:
        irodori_root = root / "Irodori-TTS"
        (irodori_root / "configs").mkdir(parents=True)
        (irodori_root / "configs" / "train_v4_small_speaker_inversion.yaml").write_text(
            "train: {}\n", encoding="utf-8"
        )
        (irodori_root / "configs" / "train_v4_small_lora.yaml").write_text(
            "train: {}\n", encoding="utf-8"
        )
        (irodori_root / "prepare_manifest.py").write_text(
            """from pathlib import Path
import sys
args = sys.argv[1:]
target = Path(args[args.index('--output-manifest') + 1])
latent_dir = Path(args[args.index('--latent-dir') + 1])
latent_dir.mkdir(parents=True, exist_ok=True)
(latent_dir / 'test.pt').write_bytes(b'latent')
target.write_text('{\"text\":\"test\",\"latent_path\":\"latents/test.pt\"}\\n', encoding='utf-8')
print('prepared 1 sample', flush=True)
""",
            encoding="utf-8",
        )
        (irodori_root / "train.py").write_text(
            """from pathlib import Path
import sys
args = sys.argv[1:]
target = Path(args[args.index('--output-dir') + 1])
target.mkdir(parents=True, exist_ok=True)
(target / 'checkpoint_0000001.speaker.safetensors').write_bytes(b'partial')
(target / 'checkpoint_final.speaker.safetensors').write_bytes(b'test')
print('step=1 loss=0.5', flush=True)
""",
            encoding="utf-8",
        )
        recordings = RecordingDatasetStore(root / "workspace" / "recordings")
        manager = TrainingJobManager(
            workspace=root / "workspace",
            irodori_root=irodori_root,
            recording_store=recordings,
            default_checkpoint="Aratako/Irodori-TTS-v4.1-Small",
        )
        return manager, recordings

    def test_workspace_paths_and_source_manifest_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager, recordings = self.create_manager(root)
            dataset_id = recordings.create("話者A")["id"]
            recordings.save_recording(
                dataset_id,
                "irodori_0001",
                empty_wav(),
                {
                    "duration": 2.0,
                    "accepted": True,
                    "prompt": {"text": "テスト音声です。", "direction": "自然に"},
                },
            )
            job_directory = manager.training_directory / "job0001"
            job_directory.mkdir()

            snapshot = manager._snapshot_dataset_rows(dataset_id, job_directory)
            source = json.loads((job_directory / "source-dataset.jsonl").read_text(encoding="utf-8"))

            self.assertEqual(snapshot["files"], 1)
            self.assertEqual(snapshot["pipeline_version"], 1)
            self.assertFalse(snapshot["transformations_applied"])
            self.assertFalse(snapshot["source_dataset_modified"])
            self.assertEqual(source["text"], "テスト音声です。")
            self.assertTrue(Path(source["audio"]).is_absolute())
            self.assertEqual(Path(source["audio"]).parent.name, "dataset-snapshot")
            self.assertEqual(
                manager.paths()["speaker_embeddings"],
                "workspace/models/speaker-embeddings",
            )
            self.assertEqual(manager.paths()["lora_adapters"], "workspace/models/lora")

    def test_previous_active_job_is_marked_interrupted_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            job_directory = workspace / "training" / "job0001"
            job_directory.mkdir(parents=True)
            (job_directory / "job.json").write_text(
                json.dumps(
                    {
                        "id": "job0001",
                        "name": "中断テスト",
                        "status": "training",
                        "stage": "training",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            manager, _ = self.create_manager(root)

            recovered = manager.load("job0001")
            self.assertEqual(recovered["status"], "interrupted")
            self.assertEqual(recovered["stage"], "interrupted")

    def test_named_models_are_discovered_independently_of_job_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager, _ = self.create_manager(root)
            output = manager.speaker_directory / "voice-a"
            output.mkdir()
            payload = {
                "id": "model0001",
                "name": "話者A ナレーション",
                "method": "speaker_inversion",
                "created_at": "2026-08-12T00:00:00+00:00",
                "asset_path": str(output / "checkpoint_final.speaker.safetensors"),
            }
            (output / "studio-model.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

            models = manager.models()

            self.assertEqual(models[0]["name"], "話者A ナレーション")
            self.assertEqual(models[0]["method"], "speaker_inversion")

    def test_trained_model_can_be_renamed_and_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager, _ = self.create_manager(root)
            output = manager.speaker_directory / "voice-a"
            output.mkdir()
            payload = {
                "id": "model0001",
                "name": "仮モデル",
                "method": "speaker_inversion",
                "created_at": "2026-08-12T00:00:00+00:00",
                "asset_path": str(output / "checkpoint_final.speaker.safetensors"),
                "output_path": str(output),
            }
            (output / "studio-model.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

            renamed = manager.rename_model("model0001", "本番モデル")
            self.assertEqual(renamed["name"], "本番モデル")
            self.assertEqual(manager.model("model0001")["name"], "本番モデル")

            manager.delete_model("model0001")
            self.assertFalse(output.exists())
            with self.assertRaises(KeyError):
                manager.model("model0001")

    def test_speaker_inversion_job_completes_and_registers_named_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager, recordings = self.create_manager(root)
            dataset_id = recordings.create("話者A")["id"]
            recordings.save_recording(
                dataset_id,
                "irodori_0001",
                empty_wav(),
                {
                    "duration": 2.0,
                    "accepted": True,
                    "prompt": {"text": "テスト音声です。", "direction": "自然に"},
                },
            )
            request = SimpleNamespace(
                name="話者A ナレーション",
                dataset_id=dataset_id,
                method="speaker_inversion",
                checkpoint="base.safetensors",
                device="cpu",
                precision="fp32",
                max_steps=1,
            )

            created = manager.create(request)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                job = manager.load(created["id"])
                if job["status"] not in {"queued", "preparing", "training"}:
                    break
                time.sleep(0.05)

            self.assertEqual(job["status"], "completed")
            self.assertTrue(Path(job["asset_path"]).is_file())
            self.assertEqual(job["dataset_snapshot"]["pipeline_version"], 1)
            self.assertFalse(job["dataset_snapshot"]["transformations_applied"])
            prepare_command = manager._read(created["id"])["command"][0]
            self.assertEqual(prepare_command[prepare_command.index("--normalize-db") + 1], "none")
            self.assertEqual(manager.models()[0]["name"], "話者A ナレーション")

    def test_empty_irodori_manifest_stops_before_training_with_visible_cause(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager, recordings = self.create_manager(root)
            (manager.irodori_root / "prepare_manifest.py").write_text(
                """from pathlib import Path
import sys
args = sys.argv[1:]
target = Path(args[args.index('--output-manifest') + 1])
target.write_text('', encoding='utf-8')
print('done. seen=1 written=0 skipped_audio=1')
print('  dataset_iter_error: 1')
""",
                encoding="utf-8",
            )
            dataset_id = recordings.create("話者A")["id"]
            recordings.save_recording(
                dataset_id,
                "irodori_0001",
                empty_wav(),
                {
                    "duration": 0.1,
                    "accepted": True,
                    "prompt": {"text": "テスト音声です。"},
                },
            )
            request = SimpleNamespace(
                name="失敗原因テスト",
                dataset_id=dataset_id,
                method="speaker_inversion",
                checkpoint="base.safetensors",
                device="cpu",
                precision="fp32",
                max_steps=1,
            )

            created = manager.create(request)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                job = manager.load(created["id"])
                if job["status"] not in {"queued", "preparing", "training"}:
                    break
                time.sleep(0.05)

            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["failure"]["code"], "manifest_empty")
            self.assertIn("1件", job["failure"]["summary"])
            self.assertIn("dataset_iter_error", job["failure"]["details"])
            listed = next(item for item in manager.list() if item["id"] == job["id"])
            self.assertNotIn("details", listed["failure"])
            self.assertFalse(Path(job["output_path"]).exists())

    def test_interrupted_speaker_training_reuses_files_and_warm_starts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager, recordings = self.create_manager(root)
            dataset_id = recordings.create("話者A")["id"]
            recordings.save_recording(
                dataset_id,
                "irodori_0001",
                empty_wav(),
                {
                    "duration": 2.0,
                    "accepted": True,
                    "prompt": {"text": "再開する音声です。", "direction": "自然に"},
                },
            )
            request = SimpleNamespace(
                name="再開モデル",
                dataset_id=dataset_id,
                method="speaker_inversion",
                checkpoint="base.safetensors",
                device="cpu",
                precision="fp32",
                max_steps=1,
            )
            created = manager.create(request)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                job = manager.load(created["id"])
                if job["status"] not in {"queued", "preparing", "training"}:
                    break
                time.sleep(0.05)
            self.assertEqual(job["status"], "completed")
            output = Path(job["output_path"])
            (output / "checkpoint_final.speaker.safetensors").unlink()
            (output / "studio-model.json").unlink()
            interrupted = manager._read(created["id"])
            interrupted.update(status="interrupted", stage="interrupted", asset_path=None)
            manager._write(interrupted)

            resumed = manager.resume(created["id"])
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                resumed = manager.load(created["id"])
                if resumed["status"] not in {"queued", "preparing", "training"}:
                    break
                time.sleep(0.05)

            self.assertEqual(resumed["status"], "completed")
            self.assertTrue(resumed["manifest_reused"])
            command = manager._read(created["id"])["command"][1]
            self.assertIn("--speaker-inversion-init-embedding", command)
            self.assertIn("resume-runs", resumed["asset_path"])

    def test_resume_overwrite_removes_old_generated_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager, recordings = self.create_manager(root)
            dataset_id = recordings.create("話者A")["id"]
            recordings.save_recording(
                dataset_id,
                "irodori_0001",
                empty_wav(),
                {
                    "duration": 2.0,
                    "accepted": True,
                    "prompt": {"text": "最初から行います。"},
                },
            )
            request = SimpleNamespace(
                name="上書きモデル",
                dataset_id=dataset_id,
                method="speaker_inversion",
                checkpoint="base.safetensors",
                device="cpu",
                precision="fp32",
                max_steps=1,
            )
            created = manager.create(request)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                job = manager.load(created["id"])
                if job["status"] not in {"queued", "preparing", "training"}:
                    break
                time.sleep(0.05)
            failed = manager._read(created["id"])
            failed.update(status="failed", stage="failed", asset_path=None)
            manager._write(failed)
            sentinel = manager._job_directory(created["id"]) / "dataset-snapshot" / "stale.wav"
            sentinel.write_bytes(b"stale")

            manager.resume(created["id"], overwrite_existing=True)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                resumed = manager.load(created["id"])
                if resumed["status"] not in {"queued", "preparing", "training"}:
                    break
                time.sleep(0.05)

            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(resumed["resume_mode"], "overwrite")
            self.assertFalse(sentinel.exists())
            command = manager._read(created["id"])["command"][1]
            self.assertNotIn("--speaker-inversion-init-embedding", command)


if __name__ == "__main__":
    unittest.main()
