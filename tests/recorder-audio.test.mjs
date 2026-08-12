import assert from "node:assert/strict";
import test from "node:test";

import {
  analyseAudio,
  createWaveformPreview,
  encodeWav,
  flattenBuffers,
  recordingQuality,
  resampleAudio,
} from "../src/features/recorder/recorder-audio.js";

test("recorder audio is flattened and resampled for 48 kHz export", () => {
  const flattened = flattenBuffers([new Float32Array([0, 0.5]), new Float32Array([-0.5, 1])]);
  assert.deepEqual([...flattened], [0, 0.5, -0.5, 1]);

  const resampled = resampleAudio(new Float32Array([0, 0.5, 1, 0.5]), 24_000, 48_000);
  assert.equal(resampled.length, 8);
  assert.equal(resampled[0], 0);
  assert.equal(resampled.at(-1), 0.5);
});

test("recorder emits a mono PCM16 WAV header", async () => {
  const wav = encodeWav(new Float32Array([-1, 0, 1]), 48_000);
  const bytes = new Uint8Array(await wav.arrayBuffer());
  const view = new DataView(bytes.buffer);

  assert.equal(new TextDecoder().decode(bytes.slice(0, 4)), "RIFF");
  assert.equal(new TextDecoder().decode(bytes.slice(8, 12)), "WAVE");
  assert.equal(view.getUint16(20, true), 1);
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 48_000);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(bytes.length, 50);
});

test("recorder analysis and quality warnings remain deterministic", () => {
  const analysis = analyseAudio(new Float32Array([0, 0.25, -0.5, 1]));
  assert.equal(analysis.peak, 1);
  assert.equal(analysis.clippedRatio, 0.25);
  assert.ok(analysis.rms > 0.5);

  assert.equal(recordingQuality({ clippedRatio: 0.01, peak: 1, rms: 0.2, duration: 2 }).label, "音割れに注意");
  assert.equal(recordingQuality({ clippedRatio: 0, peak: 0.05, rms: 0.01, duration: 2 }).label, "音量が小さめ");
  assert.equal(recordingQuality({ clippedRatio: 0, peak: 0.5, rms: 0.1, duration: 0.5 }).label, "録音が短め");
  assert.equal(recordingQuality({ clippedRatio: 0, peak: 0.5, rms: 0.1, duration: 2 }).tone, "good");

  const preview = createWaveformPreview(new Float32Array([0, 0.2, -0.8, 0.4]), 2);
  assert.ok(Math.abs(preview[0] - 0.2) < 1e-6);
  assert.ok(Math.abs(preview[1] - 0.8) < 1e-6);
});
