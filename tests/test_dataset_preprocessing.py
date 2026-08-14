from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.dataset_preprocessing import (  # noqa: E402
    DATASET_AUDIO_PIPELINE_VERSION,
    DATASET_SAMPLE_RATE,
    prepare_dataset_audio,
    sha256_file,
    valid_dataset_wav,
)


class DatasetPreprocessingTests(unittest.TestCase):
    def test_pipeline_preserves_source_and_internal_pause(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            target = root / "dataset.wav"
            samples = np.concatenate(
                (
                    np.zeros(14_400),
                    np.full(9_600, 0.08),
                    np.zeros(9_600),
                    np.full(9_600, -0.08),
                    np.zeros(14_400),
                )
            ).astype(np.float32)
            sf.write(source, samples, DATASET_SAMPLE_RATE, subtype="PCM_16")
            original_hash = sha256_file(source)

            result = prepare_dataset_audio(source, target)

            self.assertEqual(sha256_file(source), original_hash)
            self.assertTrue(valid_dataset_wav(target))
            self.assertEqual(result["pipeline_version"], DATASET_AUDIO_PIPELINE_VERSION)
            self.assertEqual(result["silence"]["status"], "trimmed")
            self.assertEqual(result["silence"]["internal_silence"], "preserved")
            self.assertAlmostEqual(result["silence"]["trimmed_start_seconds"], 0.12, places=2)
            self.assertAlmostEqual(result["silence"]["trimmed_end_seconds"], 0.12, places=2)
            self.assertEqual(result["output_sha256"], sha256_file(target))

    def test_pipeline_converts_flac_stereo_to_canonical_wav_and_normalizes_loudness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.flac"
            target = root / "dataset.wav"
            rate = 44_100
            timeline = np.arange(rate, dtype=np.float32) / rate
            tone = 0.02 * np.sin(2.0 * math.pi * 220.0 * timeline)
            stereo = np.column_stack((tone, tone * 0.8))
            sf.write(source, stereo, rate, format="FLAC", subtype="PCM_16")

            result = prepare_dataset_audio(source, target)

            info = sf.info(target)
            self.assertEqual(info.samplerate, DATASET_SAMPLE_RATE)
            self.assertEqual(info.channels, 1)
            self.assertEqual(info.subtype, "PCM_16")
            self.assertEqual(result["source_format"], "flac")
            self.assertEqual(result["loudness"]["status"], "normalized")
            self.assertAlmostEqual(result["loudness"]["output_lufs"], -16.0, delta=0.15)

    def test_silence_remains_valid_without_inventing_gain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "silence.wav"
            target = root / "dataset.wav"
            sf.write(source, np.zeros(4_800, dtype=np.float32), DATASET_SAMPLE_RATE)

            result = prepare_dataset_audio(source, target)

            self.assertTrue(valid_dataset_wav(target))
            self.assertEqual(result["silence"]["status"], "no_activity")
            self.assertEqual(result["loudness"]["status"], "no_activity")
            self.assertEqual(result["loudness"]["gain_db"], 0.0)


if __name__ == "__main__":
    unittest.main()
