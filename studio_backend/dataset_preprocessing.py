from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.signal import resample_poly

from studio_backend.time_utils import utc_now

DATASET_AUDIO_PIPELINE_VERSION = 1
DATASET_SAMPLE_RATE = 48_000
DATASET_LOUDNESS_LUFS = -16.0
EDGE_SILENCE_THRESHOLD_DBFS = -45.0
EDGE_SILENCE_PADDING_MS = 180
EDGE_SILENCE_WINDOW_MS = 10
MAX_OUTPUT_PEAK = 0.999


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_dataset_wav(path: Path) -> bool:
    try:
        info = sf.info(path)
        return (
            path.is_file()
            and info.format == "WAV"
            and info.subtype == "PCM_16"
            and info.channels == 1
            and info.samplerate == DATASET_SAMPLE_RATE
            and info.frames > 0
        )
    except (OSError, RuntimeError, ValueError):
        return False


def preprocessing_is_current(recording: dict[str, Any]) -> bool:
    preprocessing = recording.get("preprocessing")
    return isinstance(preprocessing, dict) and int(
        preprocessing.get("pipeline_version") or 0
    ) == DATASET_AUDIO_PIPELINE_VERSION


def _resample(audio: np.ndarray, source_rate: int) -> np.ndarray:
    if source_rate == DATASET_SAMPLE_RATE:
        return audio.astype(np.float32, copy=False)
    divisor = math.gcd(source_rate, DATASET_SAMPLE_RATE)
    return resample_poly(
        audio,
        DATASET_SAMPLE_RATE // divisor,
        source_rate // divisor,
    ).astype(np.float32)


def _trim_edges(audio: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    frame_count = int(audio.shape[0])
    window_frames = max(1, round(DATASET_SAMPLE_RATE * EDGE_SILENCE_WINDOW_MS / 1000))
    threshold = 10.0 ** (EDGE_SILENCE_THRESHOLD_DBFS / 20.0)
    active_windows = [
        index
        for index, start in enumerate(range(0, frame_count, window_frames))
        if float(np.sqrt(np.mean(np.square(audio[start : start + window_frames])))) >= threshold
    ]
    if not active_windows:
        return audio, {
            "status": "no_activity",
            "threshold_dbfs": EDGE_SILENCE_THRESHOLD_DBFS,
            "window_ms": EDGE_SILENCE_WINDOW_MS,
            "padding_ms": EDGE_SILENCE_PADDING_MS,
            "trimmed_start_seconds": 0.0,
            "trimmed_end_seconds": 0.0,
            "trimmed_seconds": 0.0,
            "internal_silence": "preserved",
        }

    padding_frames = round(DATASET_SAMPLE_RATE * EDGE_SILENCE_PADDING_MS / 1000)
    first_active = active_windows[0] * window_frames
    last_active = min(frame_count, (active_windows[-1] + 1) * window_frames)
    left = max(0, first_active - padding_frames)
    right = min(frame_count, last_active + padding_frames)
    status = "trimmed" if left > 0 or right < frame_count else "unchanged"
    return audio[left:right], {
        "status": status,
        "threshold_dbfs": EDGE_SILENCE_THRESHOLD_DBFS,
        "window_ms": EDGE_SILENCE_WINDOW_MS,
        "padding_ms": EDGE_SILENCE_PADDING_MS,
        "trimmed_start_seconds": round(left / DATASET_SAMPLE_RATE, 6),
        "trimmed_end_seconds": round((frame_count - right) / DATASET_SAMPLE_RATE, 6),
        "trimmed_seconds": round((left + frame_count - right) / DATASET_SAMPLE_RATE, 6),
        "internal_silence": "preserved",
    }


def _measure_loudness(audio: np.ndarray) -> tuple[float, str]:
    duration = audio.shape[0] / DATASET_SAMPLE_RATE
    if duration >= 0.4:
        value = float(pyln.Meter(DATASET_SAMPLE_RATE).integrated_loudness(audio))
        return value, "itu_bs_1770"
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    return (20.0 * math.log10(rms) if rms > 0 else -math.inf), "rms_fallback"


def _normalize_loudness(audio: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    input_loudness, measurement = _measure_loudness(audio)
    if not math.isfinite(input_loudness):
        return audio, {
            "status": "no_activity",
            "measurement": measurement,
            "target_lufs": DATASET_LOUDNESS_LUFS,
            "input_lufs": None,
            "output_lufs": None,
            "gain_db": 0.0,
            "peak_limited": False,
        }

    gain_db = DATASET_LOUDNESS_LUFS - input_loudness
    normalized = audio * (10.0 ** (gain_db / 20.0))
    peak = float(np.max(np.abs(normalized))) if normalized.size else 0.0
    peak_limited = peak > MAX_OUTPUT_PEAK
    if peak_limited:
        normalized = normalized * (MAX_OUTPUT_PEAK / peak)
    output_loudness, _ = _measure_loudness(normalized)
    return normalized.astype(np.float32), {
        "status": "normalized",
        "measurement": measurement,
        "target_lufs": DATASET_LOUDNESS_LUFS,
        "input_lufs": round(input_loudness, 4),
        "output_lufs": round(output_loudness, 4),
        "gain_db": round(gain_db, 4),
        "peak_limited": peak_limited,
    }


def prepare_dataset_audio(source: Path, target: Path) -> dict[str, Any]:
    """Create the canonical, method-independent training-dataset WAV.

    The caller owns the immutable source. This function always writes a separate
    derived artifact and may safely replace an older derived WAV at ``target``.
    """

    source = source.resolve(strict=True)
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    source_hash = sha256_file(source)
    source_info = sf.info(source)
    decoded, source_rate = sf.read(source, dtype="float32", always_2d=True)
    if decoded.shape[0] <= 0:
        raise ValueError(f"音声が空です: {source.name}")
    mono = decoded.mean(axis=1, dtype=np.float32)
    canonical = _resample(mono, int(source_rate))
    original_seconds = canonical.shape[0] / DATASET_SAMPLE_RATE
    canonical, silence = _trim_edges(canonical)
    canonical, loudness = _normalize_loudness(canonical)

    temporary = target.with_name(f".{target.name}.dataset-v{DATASET_AUDIO_PIPELINE_VERSION}.tmp")
    try:
        sf.write(
            temporary,
            canonical,
            DATASET_SAMPLE_RATE,
            format="WAV",
            subtype="PCM_16",
        )
        if not valid_dataset_wav(temporary):
            raise ValueError(f"学習データセット用WAVの検証に失敗しました: {source.name}")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)

    output_info = sf.info(target)
    return {
        "schema_version": 1,
        "pipeline_version": DATASET_AUDIO_PIPELINE_VERSION,
        "processed_at": utc_now(),
        "source_sha256": source_hash,
        "output_sha256": sha256_file(target),
        "source_format": str(source_info.format).casefold(),
        "source_sample_rate": int(source_info.samplerate),
        "source_channels": int(source_info.channels),
        "output_format": "wav_pcm16_mono",
        "output_sample_rate": DATASET_SAMPLE_RATE,
        "original_seconds": round(original_seconds, 6),
        "processed_seconds": round(float(output_info.duration), 6),
        "silence": silence,
        "loudness": loudness,
    }
