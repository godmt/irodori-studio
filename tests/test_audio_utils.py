from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.audio_utils import read_mono_audio, resample_linear  # noqa: E402


class AudioUtilsTests(unittest.TestCase):
    def test_stereo_audio_is_read_as_float32_mono(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stereo.wav"
            stereo = np.array([[0.25, 0.75], [-0.5, 0.5]], dtype=np.float32)
            sf.write(path, stereo, 24_000, subtype="FLOAT")

            audio, sample_rate = read_mono_audio(path)

            self.assertEqual(sample_rate, 24_000)
            self.assertEqual(audio.dtype, np.float32)
            np.testing.assert_allclose(audio, np.array([0.5, 0.0], dtype=np.float32))

    def test_linear_resampling_has_the_expected_duration(self) -> None:
        audio = np.linspace(-1.0, 1.0, num=48, dtype=np.float32)

        resampled = resample_linear(audio, 48_000, 24_000)

        self.assertEqual(resampled.dtype, np.float32)
        self.assertEqual(len(resampled), 24)


if __name__ == "__main__":
    unittest.main()
