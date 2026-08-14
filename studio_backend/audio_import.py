from __future__ import annotations

import gc
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

import numpy as np
import soundfile as sf

from studio_backend.time_utils import utc_now

ASR_SAMPLE_RATE = 16_000
DATASET_SAMPLE_RATE = 48_000
DEFAULT_WINDOW_SECONDS = 300.0
DEFAULT_WINDOW_OVERLAP_SECONDS = 15.0


@dataclass(frozen=True)
class SpeechRange:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def normalize_transcript(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    japanese = r"\u3040-\u30ff\u3400-\u9fff\u3000-\u303f"
    return re.sub(rf"(?<=[{japanese}]) (?=[{japanese}])", "", text)


def meaningful_character_count(text: str) -> int:
    return sum(1 for char in text if char.isalnum() or "\u3040" <= char <= "\u9fff")


def merge_speech_ranges(
    ranges: Sequence[SpeechRange],
    *,
    merge_gap_seconds: float,
    max_clip_seconds: float,
) -> list[SpeechRange]:
    """Merge nearby VAD ranges without creating clips longer than the training limit."""

    merged: list[SpeechRange] = []
    for item in ranges:
        if item.end <= item.start:
            continue
        if not merged:
            merged.append(item)
            continue
        previous = merged[-1]
        gap = item.start - previous.end
        combined_duration = item.end - previous.start
        if gap <= merge_gap_seconds and combined_duration <= max_clip_seconds:
            merged[-1] = SpeechRange(previous.start, max(previous.end, item.end))
        else:
            merged.append(item)
    return merged


def audio_metrics(audio: np.ndarray, sample_rate: int) -> dict[str, float]:
    mono = np.asarray(audio, dtype=np.float32).reshape(-1)
    if mono.size == 0:
        return {
            "peak": 0.0,
            "rms_dbfs": -120.0,
            "clipping_ratio": 1.0,
            "silence_ratio": 1.0,
            "estimated_snr_db": 0.0,
        }
    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64)) + 1e-12))
    rms_dbfs = float(20.0 * math.log10(max(rms, 1e-6)))
    clipping_ratio = float(np.mean(np.abs(mono) >= 0.999))

    frame_size = max(1, int(round(sample_rate * 0.02)))
    frame_count = mono.size // frame_size
    if frame_count > 0:
        framed = mono[: frame_count * frame_size].reshape(frame_count, frame_size)
        frame_rms = np.sqrt(np.mean(np.square(framed, dtype=np.float64), axis=1) + 1e-12)
        silence_threshold = max(10.0 ** (-50.0 / 20.0), rms * 0.08)
        silence_ratio = float(np.mean(frame_rms < silence_threshold))
    else:
        silence_ratio = 0.0

    edge_frames = max(1, min(int(sample_rate * 0.10), mono.size // 4))
    noise_samples = np.concatenate([mono[:edge_frames], mono[-edge_frames:]])
    noise_rms = float(np.sqrt(np.mean(np.square(noise_samples, dtype=np.float64)) + 1e-12))
    if rms <= noise_rms:
        estimated_snr_db = 0.0
    else:
        speech_power = max(rms * rms - noise_rms * noise_rms, 1e-12)
        estimated_snr_db = float(
            min(60.0, 10.0 * math.log10(speech_power / max(noise_rms * noise_rms, 1e-12)))
        )
    return {
        "peak": peak,
        "rms_dbfs": rms_dbfs,
        "clipping_ratio": clipping_ratio,
        "silence_ratio": silence_ratio,
        "estimated_snr_db": estimated_snr_db,
    }


def quality_reasons(
    *,
    duration: float,
    text: str,
    word_probability: float,
    avg_logprob: float,
    no_speech_probability: float,
    compression_ratio: float,
    metrics: dict[str, float],
    settings: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if duration < float(settings["min_clip_seconds"]):
        reasons.append("too_short")
    if duration > float(settings["max_clip_seconds"]):
        reasons.append("too_long")
    if meaningful_character_count(text) < int(settings["min_text_characters"]):
        reasons.append("text_too_short")
    if word_probability < float(settings["min_word_probability"]):
        reasons.append("low_word_probability")
    if avg_logprob < float(settings["min_avg_logprob"]):
        reasons.append("low_avg_logprob")
    if no_speech_probability > float(settings["max_no_speech_probability"]):
        reasons.append("high_no_speech_probability")
    if compression_ratio > float(settings["max_compression_ratio"]):
        reasons.append("high_compression_ratio")
    if metrics["rms_dbfs"] < float(settings["min_rms_dbfs"]):
        reasons.append("too_quiet")
    if metrics["clipping_ratio"] > float(settings["max_clipping_ratio"]):
        reasons.append("clipping")
    if metrics["silence_ratio"] > float(settings["max_silence_ratio"]):
        reasons.append("too_much_silence")
    min_estimated_snr_db = float(settings["min_estimated_snr_db"])
    if min_estimated_snr_db > 0.0 and metrics["estimated_snr_db"] < min_estimated_snr_db:
        reasons.append("low_estimated_snr")
    return sorted(set(reasons))


def default_import_settings() -> dict[str, Any]:
    return {
        "asr_model": "large-v3",
        "asr_device": "auto",
        "asr_compute_type": "auto",
        "language": "ja",
        "beam_size": 5,
        "window_seconds": DEFAULT_WINDOW_SECONDS,
        "window_overlap_seconds": DEFAULT_WINDOW_OVERLAP_SECONDS,
        "vad_threshold": 0.5,
        "vad_min_speech_ms": 250,
        "vad_min_silence_ms": 350,
        "vad_speech_pad_ms": 180,
        "merge_gap_seconds": 0.65,
        "min_clip_seconds": 1.5,
        "max_clip_seconds": 12.0,
        "min_text_characters": 2,
        "min_word_probability": 0.45,
        "min_avg_logprob": -1.0,
        "max_no_speech_probability": 0.60,
        "max_compression_ratio": 2.40,
        "min_rms_dbfs": -45.0,
        "max_clipping_ratio": 0.001,
        "max_silence_ratio": 0.65,
        # Edge-based SNR is useful for ranking, but VAD padding makes it too noisy for
        # automatic rejection. Keep the metric in every candidate and disable the hard gate.
        "min_estimated_snr_db": 0.0,
        "auto_accept": True,
    }


def probe_audio(path: Path) -> dict[str, Any]:
    """Read container metadata without decoding the complete input."""

    import av

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    with av.open(str(resolved), mode="r", metadata_errors="ignore") as container:
        streams = list(container.streams.audio)
        if not streams:
            raise ValueError(f"音声ストリームがありません: {resolved}")
        stream = streams[0]
        if stream.duration is not None and stream.time_base is not None:
            duration = float(stream.duration * stream.time_base)
        elif container.duration is not None:
            duration = float(container.duration) / 1_000_000.0
        else:
            raise ValueError(f"音声の長さを取得できません: {resolved}")
        codec = stream.codec_context
        return {
            "path": str(resolved),
            "name": resolved.name,
            "size_bytes": resolved.stat().st_size,
            "modified_ns": resolved.stat().st_mtime_ns,
            "duration_seconds": duration,
            "codec": str(codec.name or "unknown"),
            "sample_rate": int(codec.sample_rate or 0),
            "channels": int(codec.channels or 0),
        }


def decode_audio_window(
    path: Path,
    start_seconds: float,
    end_seconds: float,
    *,
    sample_rates: Sequence[int] = (ASR_SAMPLE_RATE, DATASET_SAMPLE_RATE),
) -> dict[int, np.ndarray]:
    """Decode only one time window into mono PCM16 arrays at the requested rates."""

    import av

    if end_seconds <= start_seconds:
        raise ValueError("音声の終了位置は開始位置より後である必要があります")
    rates = tuple(dict.fromkeys(int(rate) for rate in sample_rates))
    if any(rate <= 0 for rate in rates):
        raise ValueError("サンプルレートは正の整数である必要があります")
    expected = {
        rate: max(1, int(round((end_seconds - start_seconds) * rate))) for rate in rates
    }
    buffers = {rate: np.zeros(length, dtype=np.int16) for rate, length in expected.items()}
    copied = dict.fromkeys(rates, 0)
    fallback_time = dict.fromkeys(rates, start_seconds)

    resolved = path.expanduser().resolve()
    with av.open(str(resolved), mode="r", metadata_errors="ignore") as container:
        streams = list(container.streams.audio)
        if not streams:
            raise ValueError(f"音声ストリームがありません: {resolved}")
        stream = streams[0]
        seek_start = max(0.0, start_seconds - 2.0)
        if stream.time_base is not None:
            container.seek(
                int(seek_start / float(stream.time_base)),
                stream=stream,
                backward=True,
            )
        resamplers = {
            rate: av.AudioResampler(format="s16", layout="mono", rate=rate) for rate in rates
        }
        finished = dict.fromkeys(rates, False)
        for source_frame in container.decode(stream):
            for rate, resampler in resamplers.items():
                if finished[rate]:
                    continue
                for frame in resampler.resample(source_frame):
                    if frame.pts is not None and frame.time_base is not None:
                        frame_start = float(frame.pts * frame.time_base)
                    elif source_frame.time is not None:
                        frame_start = float(source_frame.time)
                    else:
                        frame_start = fallback_time[rate]
                    frame_end = frame_start + frame.samples / rate
                    fallback_time[rate] = frame_end
                    if frame_end <= start_seconds:
                        continue
                    if frame_start >= end_seconds:
                        finished[rate] = True
                        break
                    samples = frame.to_ndarray().reshape(-1)
                    source_left = max(0, int(round((start_seconds - frame_start) * rate)))
                    source_right = min(len(samples), int(round((end_seconds - frame_start) * rate)))
                    if source_right <= source_left:
                        continue
                    target_left = max(0, int(round((frame_start - start_seconds) * rate)))
                    if frame_start < start_seconds:
                        target_left = 0
                    target_right = min(expected[rate], target_left + source_right - source_left)
                    count = target_right - target_left
                    if count > 0:
                        buffers[rate][target_left:target_right] = samples[
                            source_left : source_left + count
                        ]
                        copied[rate] += count
            if all(finished.values()):
                break
    if not any(copied.values()):
        raise ValueError(f"指定範囲から音声をデコードできません: {resolved}")
    return buffers


def _resolve_asr_runtime(device: str, compute_type: str) -> tuple[str, str]:
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


class LongAudioImportProcessor:
    """Windowed long-audio segmentation, ASR, QC and lossless clip creation."""

    def __init__(
        self,
        *,
        model_factory: Callable[..., Any] | None = None,
        decoder: Callable[..., dict[int, np.ndarray]] = decode_audio_window,
        probe: Callable[[Path], dict[str, Any]] = probe_audio,
    ) -> None:
        self.model_factory = model_factory
        self.decoder = decoder
        self.probe = probe

    def _create_model(self, settings: dict[str, Any]) -> tuple[Any, str, str]:
        if self.model_factory is None:
            from faster_whisper import WhisperModel

            factory = WhisperModel
        else:
            factory = self.model_factory
        device, compute_type = _resolve_asr_runtime(
            str(settings["asr_device"]), str(settings["asr_compute_type"])
        )
        model = factory(
            str(settings["asr_model"]),
            device=device,
            compute_type=compute_type,
            cpu_threads=max(1, min(8, int(settings.get("asr_cpu_threads") or 8))),
        )
        return model, device, compute_type

    @staticmethod
    def _detect_speech(audio: np.ndarray, settings: dict[str, Any]) -> list[SpeechRange]:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        options = VadOptions(
            threshold=float(settings["vad_threshold"]),
            min_speech_duration_ms=int(settings["vad_min_speech_ms"]),
            max_speech_duration_s=float(settings["max_clip_seconds"]),
            min_silence_duration_ms=int(settings["vad_min_silence_ms"]),
            speech_pad_ms=int(settings["vad_speech_pad_ms"]),
        )
        ranges = [
            SpeechRange(item["start"] / ASR_SAMPLE_RATE, item["end"] / ASR_SAMPLE_RATE)
            for item in get_speech_timestamps(audio, options)
        ]
        return merge_speech_ranges(
            ranges,
            merge_gap_seconds=float(settings["merge_gap_seconds"]),
            max_clip_seconds=float(settings["max_clip_seconds"]),
        )

    @staticmethod
    def _transcribe_clip(
        model: Any, audio: np.ndarray, settings: dict[str, Any]
    ) -> dict[str, Any]:
        segments_iter, _ = model.transcribe(
            audio,
            language=str(settings["language"]),
            beam_size=int(settings["beam_size"]),
            vad_filter=False,
            word_timestamps=True,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        segments = list(segments_iter)
        words = [word for segment in segments for word in (getattr(segment, "words", None) or [])]
        text = normalize_transcript("".join(str(segment.text) for segment in segments))
        word_probability = (
            float(sum(float(getattr(word, "probability", 0.0)) for word in words) / len(words))
            if words
            else 0.0
        )
        return {
            "text": text,
            "word_probability": word_probability,
            "avg_logprob": (
                float(
                    sum(float(getattr(segment, "avg_logprob", -10.0)) for segment in segments)
                    / len(segments)
                )
                if segments
                else -10.0
            ),
            "no_speech_probability": max(
                (float(getattr(segment, "no_speech_prob", 1.0)) for segment in segments),
                default=1.0,
            ),
            "compression_ratio": max(
                (float(getattr(segment, "compression_ratio", 0.0)) for segment in segments),
                default=0.0,
            ),
        }

    def process(
        self,
        config: dict[str, Any],
        output_directory: Path,
        *,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started = monotonic()
        output_directory = output_directory.resolve()
        clips_directory = output_directory / "clips"
        clips_directory.mkdir(parents=True, exist_ok=True)
        candidates_path = output_directory / "candidates.jsonl"
        settings = {**default_import_settings(), **dict(config.get("settings") or {})}
        sources = list(config.get("sources") or [])
        if not sources:
            raise ValueError("取り込む音声ファイルを1件以上指定してください")

        source_reports: list[dict[str, Any]] = []
        total_selected_seconds = 0.0
        for source in sources:
            source_path = Path(str(source["path"])).expanduser().resolve()
            metadata = self.probe(source_path)
            selection_start = max(0.0, float(source.get("start_seconds") or 0.0))
            requested_end = source.get("end_seconds")
            selection_end = min(
                float(metadata["duration_seconds"]),
                float(requested_end) if requested_end is not None else float(metadata["duration_seconds"]),
            )
            if selection_end <= selection_start:
                raise ValueError(f"処理範囲が空です: {source_path}")
            report = {
                **metadata,
                "selection_start_seconds": selection_start,
                "selection_end_seconds": selection_end,
                "selection_duration_seconds": selection_end - selection_start,
            }
            source_reports.append(report)
            total_selected_seconds += selection_end - selection_start

        if progress:
            progress({"stage": "loading_model", "percent": 0.0})
        model, resolved_device, resolved_compute_type = self._create_model(settings)
        settings["resolved_device"] = resolved_device
        settings["resolved_compute_type"] = resolved_compute_type

        candidates: list[dict[str, Any]] = []
        candidate_ids: set[str] = set()
        processed_seconds = 0.0
        rejection_reasons: Counter[str] = Counter()
        with candidates_path.open("w", encoding="utf-8", newline="\n") as candidate_file:
            for source_index, source in enumerate(source_reports, start=1):
                source_path = Path(source["path"])
                selection_start = float(source["selection_start_seconds"])
                selection_end = float(source["selection_end_seconds"])
                window_seconds = float(settings["window_seconds"])
                overlap_seconds = float(settings["window_overlap_seconds"])
                core_start = selection_start
                source_candidate_start = len(candidates)
                while core_start < selection_end:
                    core_end = min(selection_end, core_start + window_seconds)
                    decode_start = max(selection_start, core_start - overlap_seconds)
                    decode_end = min(selection_end, core_end + overlap_seconds)
                    decoded = self.decoder(
                        source_path,
                        decode_start,
                        decode_end,
                        sample_rates=(ASR_SAMPLE_RATE, DATASET_SAMPLE_RATE),
                    )
                    asr_audio = decoded[ASR_SAMPLE_RATE].astype(np.float32) / 32768.0
                    speech_ranges = self._detect_speech(asr_audio, settings)
                    for speech in speech_ranges:
                        absolute_start = decode_start + speech.start
                        absolute_end = decode_start + speech.end
                        midpoint = (absolute_start + absolute_end) / 2.0
                        if midpoint < core_start or midpoint >= core_end:
                            continue
                        asr_left = max(0, int(math.floor(speech.start * ASR_SAMPLE_RATE)))
                        asr_right = min(
                            len(asr_audio), int(math.ceil(speech.end * ASR_SAMPLE_RATE))
                        )
                        transcription = self._transcribe_clip(
                            model, asr_audio[asr_left:asr_right], settings
                        )
                        output_audio = decoded[DATASET_SAMPLE_RATE]
                        output_left = max(
                            0,
                            int(math.floor((absolute_start - decode_start) * DATASET_SAMPLE_RATE)),
                        )
                        output_right = min(
                            len(output_audio),
                            int(math.ceil((absolute_end - decode_start) * DATASET_SAMPLE_RATE)),
                        )
                        clip_audio_i16 = output_audio[output_left:output_right]
                        clip_audio = clip_audio_i16.astype(np.float32) / 32768.0
                        duration = len(clip_audio_i16) / DATASET_SAMPLE_RATE
                        metrics = audio_metrics(clip_audio, DATASET_SAMPLE_RATE)
                        reasons = quality_reasons(
                            duration=duration,
                            text=str(transcription["text"]),
                            word_probability=float(transcription["word_probability"]),
                            avg_logprob=float(transcription["avg_logprob"]),
                            no_speech_probability=float(
                                transcription["no_speech_probability"]
                            ),
                            compression_ratio=float(transcription["compression_ratio"]),
                            metrics=metrics,
                            settings=settings,
                        )
                        source_identity = "|".join(
                            (
                                str(source_path).casefold(),
                                str(source.get("size_bytes") or 0),
                                str(source.get("modified_ns") or 0),
                            )
                        )
                        source_fingerprint = hashlib.sha256(
                            source_identity.encode("utf-8")
                        ).hexdigest()[:12]
                        start_ms = max(0, round(absolute_start * 1000.0))
                        end_ms = max(start_ms + 1, round(absolute_end * 1000.0))
                        candidate_id = (
                            f"import_{source_fingerprint}_{start_ms:010d}_{end_ms:010d}"
                        )
                        if candidate_id in candidate_ids:
                            continue
                        candidate_ids.add(candidate_id)
                        clip_name = f"{candidate_id}.flac"
                        sf.write(
                            clips_directory / clip_name,
                            clip_audio_i16,
                            DATASET_SAMPLE_RATE,
                            format="FLAC",
                            subtype="PCM_16",
                        )
                        accepted = bool(settings["auto_accept"]) and not reasons
                        for reason in reasons:
                            rejection_reasons[reason] += 1
                        quality_score = float(
                            float(transcription["word_probability"]) * 0.55
                            + max(0.0, 1.0 - abs(duration - 6.0) / 6.0) * 0.15
                            + min(max(metrics["estimated_snr_db"], 0.0), 40.0) / 40.0 * 0.20
                            + (1.0 - metrics["silence_ratio"]) * 0.10
                        )
                        candidate = {
                            "id": candidate_id,
                            "audio_file": clip_name,
                            "text": transcription["text"],
                            "accepted": accepted,
                            "review_state": "auto_accepted" if accepted else "needs_review",
                            "rejection_reasons": reasons,
                            "duration": duration,
                            "sample_rate": DATASET_SAMPLE_RATE,
                            "source_index": source_index,
                            "source_file": str(source_path),
                            "source_name": source_path.name,
                            "source_start": absolute_start,
                            "source_end": absolute_end,
                            "quality_score": quality_score,
                            **transcription,
                            **metrics,
                        }
                        candidates.append(candidate)
                        candidate_file.write(
                            json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
                            + "\n"
                        )
                        candidate_file.flush()
                    processed_seconds += core_end - core_start
                    if progress:
                        progress(
                            {
                                "stage": "transcribing",
                                "source_index": source_index,
                                "source_count": len(source_reports),
                                "processed_seconds": processed_seconds,
                                "total_seconds": total_selected_seconds,
                                "percent": (
                                    processed_seconds / total_selected_seconds * 100.0
                                    if total_selected_seconds > 0
                                    else 100.0
                                ),
                                "candidate_count": len(candidates),
                                "accepted_count": sum(
                                    bool(candidate["accepted"]) for candidate in candidates
                                ),
                            }
                        )
                    core_start = core_end
                source["candidate_count"] = len(candidates) - source_candidate_start

        accepted = [candidate for candidate in candidates if candidate["accepted"]]
        report = {
            "schema_version": 1,
            "created_at": utc_now(),
            "job_id": config.get("job_id"),
            "dataset_id": config.get("dataset_id"),
            "settings": settings,
            "sources": source_reports,
            "source_count": len(source_reports),
            "source_duration_seconds": total_selected_seconds,
            "candidate_count": len(candidates),
            "accepted_count": len(accepted),
            "needs_review_count": len(candidates) - len(accepted),
            "accepted_duration_seconds": sum(float(item["duration"]) for item in accepted),
            "rejection_reasons": dict(sorted(rejection_reasons.items())),
            "output_bytes": sum(
                (clips_directory / str(candidate["audio_file"])).stat().st_size
                for candidate in candidates
            ),
            "processing_seconds": monotonic() - started,
            "candidates_jsonl": str(candidates_path),
        }
        (output_directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        del model
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        if progress:
            progress({"stage": "completed", "percent": 100.0, **report})
        return report
