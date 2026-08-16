from __future__ import annotations

import sys
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.profile_synthesis import build_profile_synthesis_payload  # noqa: E402


class ProfileSynthesisTests(unittest.TestCase):
    def test_profile_defaults_are_resolved_for_every_client(self) -> None:
        payload = build_profile_synthesis_payload(
            {
                "source_type": "speaker",
                "ref_embed": "voice.safetensors",
                "lora_adapter": "adapter",
                "default_caption": "[happy]",
                "speed": 1.15,
                "num_steps": 16,
                "seed": 42,
                "cfg_scale_text": 2.5,
                "cfg_scale_caption": 3.5,
                "cfg_scale_speaker": 4.5,
            },
            "こんにちは",
            line_id="shared-request",
        )

        self.assertEqual(payload.line_id, "shared-request")
        self.assertEqual(payload.caption, "[happy]")
        self.assertEqual(payload.ref_embed, "voice.safetensors")
        self.assertEqual(payload.ref_wavs, [])
        self.assertFalse(payload.no_ref)
        self.assertEqual(payload.lora_adapter, "adapter")
        self.assertEqual(payload.speed, 1.15)
        self.assertEqual(payload.num_steps, 16)
        self.assertEqual(payload.seed, 42)
        self.assertEqual(payload.cfg_scale_text, 2.5)
        self.assertEqual(payload.cfg_scale_caption, 3.5)
        self.assertEqual(payload.cfg_scale_speaker, 4.5)

    def test_live_overrides_only_per_utterance_controls(self) -> None:
        payload = build_profile_synthesis_payload(
            {
                "source_type": "reference",
                "ref_wavs": ["reference.wav"],
                "default_caption": "[calm]",
                "speed": 1.2,
                "num_steps": 12,
                "seed": 7,
            },
            "配信テスト",
            caption="[excited]",
            num_steps=24,
            seed=8,
        )

        self.assertEqual(payload.caption, "[excited]")
        self.assertEqual(payload.ref_wavs, ["reference.wav"])
        self.assertIsNone(payload.ref_embed)
        self.assertEqual(payload.speed, 1.2)
        self.assertEqual(payload.num_steps, 24)
        self.assertEqual(payload.seed, 8)


if __name__ == "__main__":
    unittest.main()
