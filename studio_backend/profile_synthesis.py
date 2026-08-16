from __future__ import annotations

import uuid
from typing import Any

from studio_backend.models import SynthesisPayload


def build_profile_synthesis_payload(
    profile: dict[str, Any],
    text: str,
    *,
    line_id: str | None = None,
    caption: str | None = None,
    speed: float | None = None,
    num_steps: int | None = None,
    seed: int | None = None,
) -> SynthesisPayload:
    """Resolve one shared Voice Library profile into an engine request."""

    source_type = profile.get("source_type", "none")
    effective_caption = (
        (caption or "").strip()
        or str(profile.get("default_caption") or "").strip()
        or None
    )
    effective_speed = profile.get("speed", 1.0) if speed is None else speed
    effective_steps = profile.get("num_steps", 12) if num_steps is None else num_steps
    effective_seed = profile.get("seed") if seed is None else seed
    return SynthesisPayload.model_validate(
        {
            "line_id": line_id or f"profile-{uuid.uuid4().hex}",
            "text": text,
            "caption": effective_caption,
            "ref_wavs": profile.get("ref_wavs", []) if source_type == "reference" else [],
            "ref_embed": profile.get("ref_embed") if source_type == "speaker" else None,
            "no_ref": source_type == "none",
            "lora_adapter": profile.get("lora_adapter") or None,
            "speed": max(0.5, min(float(effective_speed), 2.0)),
            "num_steps": effective_steps,
            "seed": effective_seed,
            "cfg_scale_text": profile.get("cfg_scale_text", 3.0),
            "cfg_scale_caption": profile.get("cfg_scale_caption", 3.0),
            "cfg_scale_speaker": profile.get("cfg_scale_speaker", 5.0),
            "trim_tail": True,
        }
    )
