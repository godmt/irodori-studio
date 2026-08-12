from __future__ import annotations

import math
import shutil
import sys
import wave
from array import array
from pathlib import Path
from typing import Any

EDGE_SILENCE_THRESHOLD_DBFS = -45.0
EDGE_SILENCE_PADDING_MS = 180
EDGE_SILENCE_WINDOW_MS = 10
TRAINING_LOUDNESS_DB = -16.0


def _copy_result(
    source: Path,
    target: Path,
    *,
    status: str,
    sample_rate: int = 0,
    frame_count: int = 0,
) -> dict[str, Any]:
    shutil.copyfile(source, target)
    duration = frame_count / sample_rate if sample_rate > 0 else 0.0
    return {
        "status": status,
        "sample_rate": sample_rate,
        "original_seconds": round(duration, 6),
        "processed_seconds": round(duration, 6),
        "trimmed_start_seconds": 0.0,
        "trimmed_end_seconds": 0.0,
        "trimmed_seconds": 0.0,
    }


def trim_wav_edge_silence(
    source: Path,
    target: Path,
    *,
    threshold_dbfs: float = EDGE_SILENCE_THRESHOLD_DBFS,
    padding_ms: int = EDGE_SILENCE_PADDING_MS,
    window_ms: int = EDGE_SILENCE_WINDOW_MS,
) -> dict[str, Any]:
    """Trim only leading/trailing silence from a Studio PCM16 mono WAV.

    Internal pauses are preserved. A fixed amount of context remains before the first
    active window and after the last one so quiet consonants and natural breath are not
    cut at the boundary. Unsupported WAV formats are copied unchanged.
    """

    source = source.resolve()
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(source), "rb") as reader:
        params = reader.getparams()
        sample_rate = reader.getframerate()
        channels = reader.getnchannels()
        sample_width = reader.getsampwidth()
        frame_count = reader.getnframes()
        compression = reader.getcomptype()
        frames = reader.readframes(frame_count)

    if channels != 1 or sample_width != 2 or compression != "NONE" or frame_count <= 0:
        return _copy_result(
            source,
            target,
            status="unsupported" if frame_count > 0 else "empty",
            sample_rate=sample_rate,
            frame_count=frame_count,
        )

    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()

    window_frames = max(1, round(sample_rate * window_ms / 1000))
    threshold = 32767.0 * (10.0 ** (threshold_dbfs / 20.0))
    active_windows: list[int] = []
    for window_index, start in enumerate(range(0, frame_count, window_frames)):
        end = min(frame_count, start + window_frames)
        window = samples[start:end]
        if not window:
            continue
        rms = math.sqrt(sum(float(sample) ** 2 for sample in window) / len(window))
        if rms >= threshold:
            active_windows.append(window_index)

    if not active_windows:
        return _copy_result(
            source,
            target,
            status="no_activity",
            sample_rate=sample_rate,
            frame_count=frame_count,
        )

    padding_frames = max(0, round(sample_rate * padding_ms / 1000))
    first_active = active_windows[0] * window_frames
    last_active = min(frame_count, (active_windows[-1] + 1) * window_frames)
    trim_start = max(0, first_active - padding_frames)
    trim_end = min(frame_count, last_active + padding_frames)

    if trim_start == 0 and trim_end == frame_count:
        return _copy_result(
            source,
            target,
            status="unchanged",
            sample_rate=sample_rate,
            frame_count=frame_count,
        )

    processed = samples[trim_start:trim_end]
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    with wave.open(str(temporary), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(processed.tobytes())
    temporary.replace(target)

    original_seconds = frame_count / sample_rate
    processed_seconds = len(processed) / sample_rate
    trimmed_start_seconds = trim_start / sample_rate
    trimmed_end_seconds = (frame_count - trim_end) / sample_rate
    return {
        "status": "trimmed",
        "sample_rate": sample_rate,
        "original_seconds": round(original_seconds, 6),
        "processed_seconds": round(processed_seconds, 6),
        "trimmed_start_seconds": round(trimmed_start_seconds, 6),
        "trimmed_end_seconds": round(trimmed_end_seconds, 6),
        "trimmed_seconds": round(original_seconds - processed_seconds, 6),
    }
