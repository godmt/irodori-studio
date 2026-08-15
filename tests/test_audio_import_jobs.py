from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.audio_import_jobs import AudioImportJobManager  # noqa: E402


class FakeRecordingStore:
    def load(self, dataset_id: str) -> dict[str, str]:
        return {"id": dataset_id, "name": "話者A"}


class DeferredThread:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def start(self) -> None:
        return None


class AudioImportJobManagerTests(unittest.TestCase):
    def test_failed_job_can_resume_using_existing_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            manager = AudioImportJobManager(
                workspace=workspace,
                recording_store=FakeRecordingStore(),
            )
            source = workspace / "recordings" / "話者A" / "raw" / "source.mp3"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            job_id = "a" * 32
            job_directory = manager.directory / job_id
            job_directory.mkdir()
            (job_directory / "config.json").write_text(
                json.dumps(
                    {
                        "job_id": job_id,
                        "dataset_id": "dataset-a",
                        "sources": [{"path": str(source)}],
                        "settings": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manager._write(
                {
                    "schema_version": 2,
                    "id": job_id,
                    "dataset_id": "dataset-a",
                    "dataset_name": "話者A",
                    "status": "failed",
                    "stage": "failed",
                    "message": "worker failed",
                    "attempt": 1,
                    "failure": {"summary": "worker failed"},
                }
            )

            with patch("studio_backend.audio_import_jobs.threading.Thread", DeferredThread):
                resumed = manager.resume(job_id)

            config = json.loads(
                (job_directory / "config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(resumed["status"], "queued")
            self.assertEqual(resumed["attempt"], 2)
            self.assertEqual(resumed["resume_mode"], "reuse_existing")
            self.assertIsNone(resumed["failure"])
            self.assertTrue(config["resume_existing"])

    def test_resume_rejects_missing_raw_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = AudioImportJobManager(
                workspace=Path(directory) / "workspace",
                recording_store=FakeRecordingStore(),
            )
            job_id = "b" * 32
            job_directory = manager.directory / job_id
            job_directory.mkdir()
            (job_directory / "config.json").write_text(
                json.dumps(
                    {
                        "job_id": job_id,
                        "dataset_id": "dataset-a",
                        "sources": [{"path": str(Path(directory) / "missing.wav")}],
                    }
                ),
                encoding="utf-8",
            )
            manager._write(
                {
                    "id": job_id,
                    "dataset_id": "dataset-a",
                    "status": "interrupted",
                    "attempt": 1,
                }
            )

            with self.assertRaisesRegex(FileNotFoundError, "RAW音声"):
                manager.resume(job_id)


if __name__ == "__main__":
    unittest.main()
