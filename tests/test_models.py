from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.models import (  # noqa: E402
    AudioImportJobCreateRequest,
    ProjectRenameRequest,
    RecordingDatasetCreateRequest,
    TrainingJobCreateRequest,
    VoiceProfileRequest,
)


class RequestModelTests(unittest.TestCase):
    def test_user_resource_names_are_trimmed_consistently(self) -> None:
        self.assertEqual(ProjectRenameRequest(name="  番組  ").name, "番組")
        self.assertEqual(RecordingDatasetCreateRequest(name="  話者A  ").name, "話者A")
        training = TrainingJobCreateRequest(name="  話者モデル  ", dataset_id="dataset")
        self.assertEqual(training.name, "話者モデル")
        self.assertEqual(training.max_steps, 500)
        self.assertEqual(VoiceProfileRequest(name="  メインボイス  ").name, "メインボイス")

    def test_training_steps_default_to_the_selected_method(self) -> None:
        speaker = TrainingJobCreateRequest(name="話者", dataset_id="dataset")
        lora = TrainingJobCreateRequest(name="話者LoRA", dataset_id="dataset", method="lora")
        custom = TrainingJobCreateRequest(
            name="話者LoRA 高品質",
            dataset_id="dataset",
            method="lora",
            max_steps=3000,
        )

        self.assertEqual(speaker.max_steps, 500)
        self.assertEqual(lora.max_steps, 1500)
        self.assertEqual(custom.max_steps, 3000)

    def test_whitespace_only_resource_names_are_rejected(self) -> None:
        for schema in (ProjectRenameRequest, RecordingDatasetCreateRequest):
            with self.subTest(schema=schema.__name__), self.assertRaises(ValidationError):
                schema(name="   ")

    def test_audio_import_accepts_multiple_sources_and_validates_ranges(self) -> None:
        request = AudioImportJobCreateRequest(
            dataset_id=" dataset ",
            sources=[
                {"path": " one.mp3 "},
                {"path": "two.wav", "start_seconds": 30, "end_seconds": 60},
            ],
        )

        self.assertEqual(request.dataset_id, "dataset")
        self.assertEqual([source.path for source in request.sources], ["one.mp3", "two.wav"])
        with self.assertRaises(ValidationError):
            AudioImportJobCreateRequest(
                dataset_id="dataset",
                sources=[{"path": "bad.wav", "start_seconds": 60, "end_seconds": 30}],
            )


if __name__ == "__main__":
    unittest.main()
