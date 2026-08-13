from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.models import VoiceProfileRequest  # noqa: E402
from studio_backend.voice_profiles import (  # noqa: E402
    VoiceProfileStore,
    migrate_voice_profile_store,
)


class VoiceProfileStoreTests(unittest.TestCase):
    def test_legacy_voicevox_store_is_migrated_without_overwriting_current_library(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "voicevox" / "profiles.json"
            current = root / "voices" / "profiles.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"schema_version": 1, "profiles": [{"name": "Legacy"}]}', encoding="utf-8")

            self.assertTrue(migrate_voice_profile_store(legacy, current))
            self.assertIn("Legacy", current.read_text(encoding="utf-8"))
            self.assertFalse(current.with_suffix(".migration.tmp").exists())
            current.write_text("current", encoding="utf-8")
            self.assertFalse(migrate_voice_profile_store(legacy, current))
            self.assertEqual(current.read_text(encoding="utf-8"), "current")

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

            store.upsert(
                VoiceProfileRequest(
                    profile_id=second["profile_id"],
                    display_order=0,
                    name="Second",
                    enabled=False,
                    source_type="none",
                )
            )
            store.upsert(
                VoiceProfileRequest(
                    profile_id=first["profile_id"],
                    display_order=1,
                    name="Main renamed",
                    style_name="配信",
                    enabled=True,
                    source_type="none",
                )
            )
            self.assertEqual(
                [profile["profile_id"] for profile in VoiceProfileStore(path).list()],
                [second["profile_id"], first["profile_id"]],
            )

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
