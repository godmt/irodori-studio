from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
import wave
from array import array
from pathlib import Path
from types import SimpleNamespace

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.audio_preprocessing import trim_wav_edge_silence  # noqa: E402
from studio_backend.recording_datasets import RecordingDatasetStore  # noqa: E402
from studio_backend.training_jobs import TrainingJobManager  # noqa: E402


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


def write_pcm16_wav(path: Path, samples: list[int], sample_rate: int = 1000) -> None:
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(array("h", samples).tobytes())


class AudioPreprocessingTests(unittest.TestCase):
    def test_only_edge_silence_is_trimmed_with_padding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            target = root / "prepared.wav"
            source_samples = (
                [0] * 300
                + [6000] * 200
                + [0] * 200
                + [-6000] * 200
                + [0] * 300
            )
            write_pcm16_wav(source, source_samples)
            original_bytes = source.read_bytes()

            result = trim_wav_edge_silence(source, target, padding_ms=100)

            with wave.open(str(target), "rb") as reader:
                processed = array("h")
                processed.frombytes(reader.readframes(reader.getnframes()))
            self.assertEqual(result["status"], "trimmed")
            self.assertAlmostEqual(result["trimmed_start_seconds"], 0.2)
            self.assertAlmostEqual(result["trimmed_end_seconds"], 0.2)
            self.assertEqual(len(processed), 800)
            self.assertTrue(all(sample == 0 for sample in processed[300:500]))
            self.assertEqual(source.read_bytes(), original_bytes)

    def test_silent_recording_is_copied_without_destructive_trimming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            target = root / "prepared.wav"
            write_pcm16_wav(source, [0] * 1000)

            result = trim_wav_edge_silence(source, target)

            self.assertEqual(result["status"], "no_activity")
            self.assertEqual(target.read_bytes(), source.read_bytes())


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

            preprocessing = manager._dataset_rows(dataset_id, job_directory)
            source = json.loads((job_directory / "source-dataset.jsonl").read_text(encoding="utf-8"))

            self.assertEqual(preprocessing["files"], 1)
            self.assertEqual(preprocessing["loudness_target_db"], -16.0)
            self.assertFalse(preprocessing["source_recordings_modified"])
            self.assertEqual(source["text"], "テスト音声です。")
            self.assertTrue(Path(source["audio"]).is_absolute())
            self.assertEqual(Path(source["audio"]).parent.name, "prepared-audio")
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
            self.assertEqual(job["preprocessing"]["loudness_target_db"], -16.0)
            self.assertEqual(manager.models()[0]["name"], "話者A ナレーション")


if __name__ == "__main__":
    unittest.main()
