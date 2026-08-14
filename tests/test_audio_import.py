from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.audio_import import (  # noqa: E402
    ASR_SAMPLE_RATE,
    DATASET_SAMPLE_RATE,
    LongAudioImportProcessor,
    SpeechRange,
    audio_metrics,
    decode_audio_window,
    default_import_settings,
    merge_speech_ranges,
    quality_reasons,
)


class FakeWhisperModel:
    def transcribe(self, audio: np.ndarray, **_: object) -> tuple[list[object], object]:
        words = [SimpleNamespace(word="テスト音声です", probability=0.95)]
        segment = SimpleNamespace(
            text=" テスト音声です。",
            words=words,
            avg_logprob=-0.1,
            no_speech_prob=0.01,
            compression_ratio=1.0,
        )
        return [segment], SimpleNamespace()


class PredictableProcessor(LongAudioImportProcessor):
    @staticmethod
    def _detect_speech(audio: np.ndarray, settings: dict[str, object]) -> list[SpeechRange]:
        del audio, settings
        return [SpeechRange(1.0, 4.0)]


class AudioImportTests(unittest.TestCase):
    def test_nearby_vad_ranges_merge_without_exceeding_clip_limit(self) -> None:
        merged = merge_speech_ranges(
            [SpeechRange(0.0, 2.0), SpeechRange(2.4, 4.0), SpeechRange(10.0, 23.0)],
            merge_gap_seconds=0.65,
            max_clip_seconds=12.0,
        )

        self.assertEqual(merged, [SpeechRange(0.0, 4.0), SpeechRange(10.0, 23.0)])

    def test_window_decoder_reads_only_requested_range_at_both_rates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "long.wav"
            sample_rate = 44_100
            time_axis = np.arange(sample_rate * 4, dtype=np.float32) / sample_rate
            sf.write(source, 0.2 * np.sin(2 * np.pi * 220 * time_axis), sample_rate)

            decoded = decode_audio_window(source, 1.0, 2.5)

            self.assertEqual(len(decoded[ASR_SAMPLE_RATE]), round(1.5 * ASR_SAMPLE_RATE))
            self.assertEqual(
                len(decoded[DATASET_SAMPLE_RATE]), round(1.5 * DATASET_SAMPLE_RATE)
            )
            self.assertGreater(np.max(np.abs(decoded[DATASET_SAMPLE_RATE])), 1000)

    def test_qc_reports_transcript_and_audio_problems_separately(self) -> None:
        settings = default_import_settings()
        metrics = audio_metrics(np.zeros(DATASET_SAMPLE_RATE, dtype=np.float32), 48_000)

        reasons = quality_reasons(
            duration=1.0,
            text="",
            word_probability=0.0,
            avg_logprob=-2.0,
            no_speech_probability=0.9,
            compression_ratio=3.0,
            metrics=metrics,
            settings=settings,
        )

        self.assertIn("too_short", reasons)
        self.assertIn("text_too_short", reasons)
        self.assertIn("too_quiet", reasons)
        self.assertIn("low_word_probability", reasons)

    def test_processor_writes_lossless_candidates_and_auditable_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp3"
            second_source = root / "second-source.m4a"
            source.write_bytes(b"test")
            second_source.write_bytes(b"test")

            def fake_probe(path: Path) -> dict[str, object]:
                return {
                    "path": str(path),
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "duration_seconds": 5.0,
                    "codec": "mp3",
                    "sample_rate": 44_100,
                    "channels": 2,
                }

            def fake_decoder(
                _: Path, start: float, end: float, *, sample_rates: tuple[int, ...]
            ) -> dict[int, np.ndarray]:
                result: dict[int, np.ndarray] = {}
                for rate in sample_rates:
                    audio = np.zeros(round((end - start) * rate), dtype=np.int16)
                    left = round(1.2 * rate)
                    right = round(3.8 * rate)
                    axis = np.arange(right - left, dtype=np.float32) / rate
                    audio[left:right] = np.asarray(
                        np.sin(2 * np.pi * 220 * axis) * 6000, dtype=np.int16
                    )
                    result[rate] = audio
                return result

            processor = PredictableProcessor(
                model_factory=lambda *args, **kwargs: FakeWhisperModel(),
                decoder=fake_decoder,
                probe=fake_probe,
            )
            output = root / "output"
            report = processor.process(
                {
                    "job_id": "12345678abcdef",
                    "dataset_id": "dataset",
                    "sources": [{"path": str(source)}, {"path": str(second_source)}],
                    "settings": {},
                },
                output,
            )

            candidates = [
                json.loads(line)
                for line in (output / "candidates.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(report["source_count"], 2)
            self.assertEqual(report["candidate_count"], 2)
            self.assertEqual(report["accepted_count"], 2)
            self.assertTrue(all(candidate["accepted"] for candidate in candidates))
            self.assertTrue(all(candidate["text"] == "テスト音声です。" for candidate in candidates))
            self.assertTrue(
                all(
                    (output / "clips" / candidate["audio_file"]).is_file()
                    for candidate in candidates
                )
            )
            second_output = root / "second-output"
            processor.process(
                {
                    "job_id": "different-job-id",
                    "dataset_id": "dataset",
                    "sources": [{"path": str(source)}, {"path": str(second_source)}],
                    "settings": {},
                },
                second_output,
            )
            second_candidates = [
                json.loads(line)
                for line in (second_output / "candidates.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                [candidate["id"] for candidate in candidates],
                [candidate["id"] for candidate in second_candidates],
            )


if __name__ == "__main__":
    unittest.main()
