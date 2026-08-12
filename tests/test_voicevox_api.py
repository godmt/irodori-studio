from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.models import VoiceProfileRequest  # noqa: E402
from studio_backend.voice_profiles import VoiceProfileStore  # noqa: E402
from studio_backend.voicevox_api import create_voicevox_app  # noqa: E402


class FakeEngine:
    def __init__(self, audio_dir: Path) -> None:
        self.audio_dir = audio_dir
        self.audio_dir.mkdir(parents=True)
        self.last_payload = None

    def status(self) -> dict:
        return {
            "loaded": True,
            "loading": False,
            "queue_depth": 0,
            "running_jobs": 0,
            "cuda": None,
        }

    def create_job(self, payload):
        self.last_payload = payload
        sample_rate = 48_000
        seconds = 0.2
        time = np.arange(round(sample_rate * seconds), dtype=np.float32) / sample_rate
        audio = (0.15 * np.sin(2 * np.pi * 440 * time)).astype(np.float32)
        sf.write(self.audio_dir / "generated.wav", audio, sample_rate)
        return {"id": "fake-job"}

    def wait_for_job(self, job_id: str, timeout: float = 300.0) -> dict:
        self.wait_args = (job_id, timeout)
        return {"id": job_id, "status": "completed", "audio_file": "generated.wav"}


class VoicevoxApiTests(unittest.TestCase):
    def test_discovery_query_and_wav_synthesis_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = VoiceProfileStore(root / "profiles.json")
            profile = store.upsert(
                VoiceProfileRequest(
                    name="配信用ボイス",
                    style_name="標準",
                    enabled=True,
                    source_type="none",
                    speed=1.15,
                    num_steps=16,
                    seed=42,
                )
            )
            engine = FakeEngine(root / "audio")
            client = TestClient(create_voicevox_app(engine=engine, profile_store=store))

            speakers = client.get("/speakers")
            self.assertEqual(speakers.status_code, 200)
            self.assertEqual(speakers.json()[0]["styles"][0]["id"], profile["style_id"])

            query_response = client.post(
                "/audio_query",
                params={"text": "こんにちは😆", "speaker": profile["style_id"]},
            )
            self.assertEqual(query_response.status_code, 200)
            self.assertEqual(
                query_response.headers["content-type"], "application/json; charset=utf-8"
            )
            query = query_response.json()
            self.assertEqual(query["kana"], "こんにちは😆")
            self.assertEqual(query["speedScale"], 1.15)
            query["outputSamplingRate"] = 24_000
            query["outputStereo"] = True
            query["prePhonemeLength"] = 0.05
            query["postPhonemeLength"] = 0.05

            response = client.post(
                "/synthesis", params={"speaker": profile["style_id"]}, json=query
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "audio/wav")
            self.assertEqual(response.headers["x-irodori-adapter-version"], "1.0.0")
            self.assertEqual(engine.last_payload.speed, 1.15)
            self.assertEqual(engine.last_payload.num_steps, 16)
            self.assertEqual(engine.last_payload.seed, 42)
            self.assertEqual(engine.last_payload.text, "こんにちは😆")

            output = root / "response.wav"
            output.write_bytes(response.content)
            info = sf.info(output)
            self.assertEqual(info.samplerate, 24_000)
            self.assertEqual(info.channels, 2)
            self.assertEqual(info.subtype, "PCM_16")
            self.assertAlmostEqual(info.duration, 0.3, places=2)

    def test_unpublished_and_unknown_styles_are_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = VoiceProfileStore(root / "profiles.json")
            profile = store.upsert(
                VoiceProfileRequest(name="Private", enabled=False, source_type="none")
            )
            client = TestClient(
                create_voicevox_app(engine=FakeEngine(root / "audio"), profile_store=store)
            )

            self.assertEqual(client.get("/speakers").json(), [])
            response = client.post(
                "/audio_query", params={"text": "test", "speaker": profile["style_id"]}
            )
            self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
