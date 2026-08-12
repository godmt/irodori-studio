from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.models import VoiceProfileRequest  # noqa: E402
from studio_backend.voice_profiles import VoiceProfileStore  # noqa: E402


class VoiceProfileStoreTests(unittest.TestCase):
    def test_ids_are_stable_across_updates_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.json"
            store = VoiceProfileStore(path)
            first = store.upsert(
                VoiceProfileRequest(name="Main", enabled=True, source_type="none")
            )
            updated = store.upsert(
                VoiceProfileRequest(
                    profile_id=first["profile_id"],
                    name="Main renamed",
                    style_name="配信",
                    enabled=True,
                    source_type="none",
                )
            )

            self.assertEqual(updated["style_id"], first["style_id"])
            self.assertEqual(updated["speaker_uuid"], first["speaker_uuid"])
            reloaded = VoiceProfileStore(path).get(first["profile_id"])
            self.assertEqual(reloaded["style_id"], first["style_id"])

            second = store.upsert(
                VoiceProfileRequest(name="Second", enabled=False, source_type="none")
            )
            self.assertEqual(second["style_id"], first["style_id"] + 1)
            self.assertEqual(len(store.list(enabled_only=True)), 1)

    def test_publishing_missing_speaker_asset_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VoiceProfileStore(Path(directory) / "profiles.json")
            with self.assertRaises(ValueError):
                store.upsert(
                    VoiceProfileRequest(
                        name="Missing",
                        enabled=True,
                        source_type="speaker",
                        ref_embed=str(Path(directory) / "missing.safetensors"),
                    )
                )


if __name__ == "__main__":
    unittest.main()
