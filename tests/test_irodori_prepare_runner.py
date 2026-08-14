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

from studio_backend.irodori_prepare_runner import decode_studio_wav  # noqa: E402


class IrodoriPrepareRunnerTests(unittest.TestCase):
    def test_studio_pcm_wav_decodes_without_torchcodec(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_root = root / "prepared-audio"
            audio_root.mkdir()
            path = audio_root / "sample.wav"
            sf.write(
                path,
                np.full(4_800, 0.1, dtype=np.float32),
                48_000,
                format="WAV",
                subtype="PCM_16",
            )

            decoded = decode_studio_wav(
                {"path": str(path), "bytes": None},
                audio_root=audio_root,
                target_sample_rate=48_000,
            )

            self.assertIsNotNone(decoded)
            assert decoded is not None
            self.assertEqual(decoded["sampling_rate"], 48_000)
            self.assertEqual(decoded["array"].shape, (4_800, 1))

    def test_audio_outside_job_boundary_uses_original_decoder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_root = root / "prepared-audio"
            audio_root.mkdir()
            outside = root / "outside.wav"
            sf.write(outside, np.zeros(100, dtype=np.float32), 48_000, subtype="PCM_16")

            decoded = decode_studio_wav(
                {"path": str(outside), "bytes": None},
                audio_root=audio_root,
                target_sample_rate=48_000,
            )

            self.assertIsNone(decoded)


if __name__ == "__main__":
    unittest.main()
