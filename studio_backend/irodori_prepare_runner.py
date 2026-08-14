from __future__ import annotations

import argparse
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import soundfile as sf


def decode_studio_wav(
    value: dict[str, Any],
    *,
    audio_root: Path,
    target_sample_rate: int | None,
) -> dict[str, Any] | None:
    """Decode only Studio-owned prepared WAVs without TorchCodec.

    Hugging Face datasets normally delegates ``Audio`` decoding to TorchCodec.
    Studio already owns and validates these PCM WAV copies, so decoding them again
    through TorchCodec adds a system FFmpeg dependency without adding capability.
    Returning ``None`` tells the caller to use datasets' original decoder.
    """

    if not isinstance(value, dict) or value.get("bytes") is not None:
        return None
    raw_path = value.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None

    root = audio_root.resolve()
    try:
        path = Path(raw_path).resolve(strict=True)
    except OSError:
        return None
    if path.suffix.casefold() != ".wav" or root not in path.parents:
        return None

    info = sf.info(path)
    if (
        info.format != "WAV"
        or info.subtype != "PCM_16"
        or info.channels != 1
        or info.frames <= 0
    ):
        raise ValueError(f"Studio prepared WAV is invalid: {path.name}")
    if target_sample_rate is not None and info.samplerate != target_sample_rate:
        raise ValueError(
            f"Studio prepared WAV sample rate is {info.samplerate}, "
            f"expected {target_sample_rate}: {path.name}"
        )

    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    return {"array": audio, "sampling_rate": int(sample_rate)}


def install_studio_audio_decoder(audio_root: Path) -> Callable[..., Any] | None:
    """Patch datasets.Audio for Studio's validated dataset-snapshot boundary."""

    try:
        from datasets.features.audio import Audio
    except ImportError:
        # Small test doubles and future Irodori utilities may not import datasets.
        return None

    original = Audio.decode_example

    def decode_example(
        instance: Any,
        value: dict[str, Any],
        token_per_repo_id: dict[str, Any] | None = None,
    ) -> Any:
        decoded = decode_studio_wav(
            value,
            audio_root=audio_root,
            target_sample_rate=getattr(instance, "sampling_rate", None),
        )
        if decoded is not None:
            return decoded
        return original(instance, value, token_per_repo_id)

    Audio.decode_example = decode_example
    return original


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--script", required=True)
    parser.add_argument("--audio-root", required=True)
    runner_args, script_args = parser.parse_known_args()

    script = Path(runner_args.script).resolve(strict=True)
    sys.path.insert(0, str(script.parent))
    install_studio_audio_decoder(Path(runner_args.audio_root))
    sys.argv = [str(script), *script_args]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
