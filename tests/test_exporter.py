from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.exporter import create_production_zip, safe_stem  # noqa: E402
from studio_backend.models import ProductionExportRequest  # noqa: E402


class ExporterTests(unittest.TestCase):
    def test_production_zip_contains_master_subtitles_and_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio_dir = root / "audio"
            export_dir = root / "exports"
            audio_dir.mkdir()
            sf.write(audio_dir / "one.wav", np.zeros(12_000), 24_000, subtype="PCM_16")
            sf.write(audio_dir / "two.wav", np.zeros(12_000), 48_000, subtype="PCM_16")

            request = ProductionExportRequest.model_validate(
                {
                    "project_name": "番組テスト",
                    "gap_ms": 250,
                    "segments": [
                        {
                            "id": "line-one",
                            "text": "最初の文章です。",
                            "audio_file": "one.wav",
                        },
                        {
                            "id": "line-two",
                            "text": "次の文章です。",
                            "audio_file": "two.wav",
                        },
                    ],
                    "project": {"title": "番組テスト"},
                }
            )
            result = create_production_zip(
                request,
                audio_dir=audio_dir,
                export_dir=export_dir,
            )

            with zipfile.ZipFile(result) as archive:
                names = set(archive.namelist())
                self.assertIn("master.wav", names)
                self.assertIn("lines/001_line-one.wav", names)
                self.assertIn("lines/002_line-two.wav", names)
                self.assertIn("subtitles.srt", names)
                self.assertIn("subtitles.vtt", names)
                self.assertIn("timeline.csv", names)
                self.assertIn("ffconcat.txt", names)
                srt = archive.read("subtitles.srt").decode("utf-8-sig")
                self.assertIn("00:00:00,000 --> 00:00:00,500", srt)
                self.assertIn("00:00:00,750 --> 00:00:01,000", srt)
                master, sample_rate = sf.read(io.BytesIO(archive.read("master.wav")))
                self.assertEqual(sample_rate, 24_000)
                self.assertAlmostEqual(len(master) / sample_rate, 1.0, places=3)

    def test_safe_stem_removes_path_punctuation(self) -> None:
        self.assertEqual(safe_stem(" ../番組:テスト/ "), "番組-テスト")


if __name__ == "__main__":
    unittest.main()
