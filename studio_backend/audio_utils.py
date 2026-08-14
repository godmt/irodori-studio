from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def read_mono_audio(path: Path) -> tuple[np.ndarray, int]:
    """Read an audio file as float32 mono samples and its sample rate."""
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    return audio.mean(axis=1), int(sample_rate)


def resample_linear(
    audio: np.ndarray, source_rate: int, target_rate: int
) -> np.ndarray:
    """Resample one-dimensional audio with deterministic linear interpolation."""
    if source_rate == target_rate or audio.size == 0:
        return audio
    target_length = max(1, round(audio.shape[0] * target_rate / source_rate))
    source_x = np.linspace(0.0, 1.0, num=audio.shape[0], endpoint=False)
    target_x = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
    return np.interp(target_x, source_x, audio).astype(np.float32)


def write_pcm16_wav(
    source: Path,
    target: Path,
    *,
    sample_rate: int = 48_000,
) -> dict[str, int | float]:
    """Atomically convert a short audio artifact to mono PCM16 WAV.

    Long source recordings are never passed here. Import workers keep their compact
    FLAC clips in the job directory until this conversion and the dataset manifest
    commit have both succeeded.
    """

    source = source.resolve()
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    audio, source_rate = read_mono_audio(source)
    audio = resample_linear(audio, source_rate, sample_rate)
    temporary = target.with_name(f"{target.name}.tmp")
    try:
        sf.write(temporary, audio, sample_rate, format="WAV", subtype="PCM_16")
        info = sf.info(temporary)
        if (
            info.format != "WAV"
            or info.channels != 1
            or info.samplerate != sample_rate
            or info.frames <= 0
        ):
            raise ValueError(f"学習用WAVの検証に失敗しました: {source.name}")
        temporary.replace(target)
        return {
            "sample_rate": int(info.samplerate),
            "frames": int(info.frames),
            "duration": float(info.duration),
        }
    finally:
        temporary.unlink(missing_ok=True)
