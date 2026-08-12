from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.generated_audio import delete_generated_audio_files  # noqa: E402


class GeneratedAudioTests(unittest.TestCase):
    def test_deletes_wav_and_metadata_but_keeps_referenced_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("remove.wav", "remove.json", "keep.wav", "keep.json"):
                (root / name).write_bytes(b"test")

            result = delete_generated_audio_files(
                root, ["remove.wav", "keep.wav"], retained={"keep.wav"}
            )

            self.assertEqual(result, {"audio_deleted": 1, "metadata_deleted": 1})
            self.assertFalse((root / "remove.wav").exists())
            self.assertFalse((root / "remove.json").exists())
            self.assertTrue((root / "keep.wav").exists())
            self.assertTrue((root / "keep.json").exists())

    def test_rejects_paths_and_non_wav_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside.wav"
            outside.write_bytes(b"test")
            note = root / "note.json"
            note.write_bytes(b"test")
            try:
                result = delete_generated_audio_files(
                    root, ["../outside.wav", "note.json"]
                )
                self.assertEqual(
                    result, {"audio_deleted": 0, "metadata_deleted": 0}
                )
                self.assertTrue(outside.exists())
                self.assertTrue(note.exists())
            finally:
                outside.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
