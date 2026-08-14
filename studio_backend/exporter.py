from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from studio_backend.audio_utils import read_mono_audio, resample_linear
from studio_backend.models import ProductionExportRequest
from studio_backend.path_utils import safe_stem


@dataclass(frozen=True)
class TimelineEntry:
    index: int
    line_id: str
    text: str
    caption: str
    voice_name: str
    seed: int | None
    audio_name: str
    start: float
    end: float
    duration: float


def _timecode(seconds: float, *, srt: bool) -> str:
    total_ms = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    separator = "," if srt else "."
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}{separator}{millis:03d}"


def _build_srt(entries: list[TimelineEntry]) -> str:
    chunks = []
    for item in entries:
        chunks.append(
            f"{item.index}\n{_timecode(item.start, srt=True)} --> "
            f"{_timecode(item.end, srt=True)}\n{item.text}\n"
        )
    return "\n".join(chunks)


def _build_vtt(entries: list[TimelineEntry]) -> str:
    chunks = ["WEBVTT\n"]
    for item in entries:
        chunks.append(
            f"{_timecode(item.start, srt=False)} --> {_timecode(item.end, srt=False)}\n"
            f"{item.text}\n"
        )
    return "\n".join(chunks)


def _build_csv(entries: list[TimelineEntry]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(asdict(entries[0]).keys()))
    writer.writeheader()
    writer.writerows(asdict(item) for item in entries)
    return stream.getvalue()


def create_production_zip(
    request: ProductionExportRequest,
    *,
    audio_dir: Path,
    export_dir: Path,
) -> Path:
    audio_dir = audio_dir.resolve()
    export_dir.mkdir(parents=True, exist_ok=True)
    loaded: list[tuple[object, Path, np.ndarray, int]] = []
    for segment in request.segments:
        candidate = (audio_dir / Path(segment.audio_file).name).resolve()
        if candidate.parent != audio_dir or not candidate.is_file():
            raise FileNotFoundError(f"Generated audio not found: {segment.audio_file}")
        audio, sample_rate = read_mono_audio(candidate)
        loaded.append((segment, candidate, audio, sample_rate))

    target_rate = loaded[0][3]
    gap_samples = round(target_rate * request.gap_ms / 1000)
    gap = np.zeros(gap_samples, dtype=np.float32)
    cursor = 0.0
    entries: list[TimelineEntry] = []
    mastered: list[np.ndarray] = []
    line_files: list[tuple[Path, str]] = []

    for index, (segment, source_path, audio, sample_rate) in enumerate(loaded, start=1):
        audio = resample_linear(audio, sample_rate, target_rate)
        duration = len(audio) / target_rate
        audio_name = f"{index:03d}_{safe_stem(segment.id, f'line-{index}')}.wav"
        entries.append(
            TimelineEntry(
                index=index,
                line_id=segment.id,
                text=segment.text,
                caption=segment.caption,
                voice_name=segment.voice_name,
                seed=segment.seed,
                audio_name=f"lines/{audio_name}",
                start=cursor,
                end=cursor + duration,
                duration=duration,
            )
        )
        mastered.append(audio)
        line_files.append((source_path, audio_name))
        cursor += duration
        if index < len(loaded):
            mastered.append(gap)
            cursor += request.gap_ms / 1000

    stem = safe_stem(request.project_name)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = export_dir / f"{stem}-{timestamp}.zip"
    master_audio = np.concatenate(mastered) if mastered else np.zeros(1, dtype=np.float32)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_path, audio_name in line_files:
            archive.write(source_path, f"lines/{audio_name}")

        if request.include_master:
            master_buffer = io.BytesIO()
            sf.write(master_buffer, master_audio, target_rate, format="WAV", subtype="PCM_16")
            archive.writestr("master.wav", master_buffer.getvalue())
        if request.include_srt:
            archive.writestr("subtitles.srt", _build_srt(entries).encode("utf-8-sig"))
        if request.include_vtt:
            archive.writestr("subtitles.vtt", _build_vtt(entries).encode("utf-8"))
        if request.include_csv:
            archive.writestr("timeline.csv", _build_csv(entries).encode("utf-8-sig"))

        concat_lines = ["ffconcat version 1.0"]
        for entry in entries:
            concat_lines.append(f"file '{entry.audio_name}'")
            concat_lines.append(f"duration {entry.duration:.6f}")
        archive.writestr("ffconcat.txt", ("\n".join(concat_lines) + "\n").encode("utf-8"))
        archive.writestr(
            "timeline.json",
            json.dumps([asdict(item) for item in entries], ensure_ascii=False, indent=2),
        )
        archive.writestr(
            "project.json",
            json.dumps(request.project, ensure_ascii=False, indent=2),
        )
        archive.writestr(
            "README.txt",
            (
                "Irodori Studio production export\n\n"
                f"Sample rate: {target_rate} Hz\n"
                f"Lines: {len(entries)}\n"
                f"Inter-line gap: {request.gap_ms} ms\n"
                "master.wav: joined program audio\n"
                "lines/: individual generated WAV files\n"
                "subtitles.srt / subtitles.vtt: subtitle tracks\n"
                "timeline.csv / timeline.json: edit timing metadata\n"
                "ffconcat.txt: FFmpeg concat demuxer input\n"
            ).encode(),
        )
    return zip_path
