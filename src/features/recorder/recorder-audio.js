export const RECORDER_SAMPLE_RATE = 48_000;

export function flattenBuffers(chunks) {
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const output = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}

export function resampleAudio(input, inputRate, outputRate) {
  if (inputRate === outputRate) return input;
  const ratio = inputRate / outputRate;
  const output = new Float32Array(Math.round(input.length / ratio));
  for (let index = 0; index < output.length; index += 1) {
    const position = index * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, input.length - 1);
    const mix = position - left;
    output[index] = input[left] * (1 - mix) + input[right] * mix;
  }
  return output;
}

export function encodeWav(samples, sampleRate = RECORDER_SAMPLE_RATE) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeText = (offset, value) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export function analyseAudio(samples) {
  let peak = 0;
  let clipped = 0;
  let sumSquares = 0;
  for (const sample of samples) {
    const absolute = Math.abs(sample);
    peak = Math.max(peak, absolute);
    if (absolute >= 0.99) clipped += 1;
    sumSquares += sample * sample;
  }
  const size = Math.max(1, samples.length);
  return { peak, rms: Math.sqrt(sumSquares / size), clippedRatio: clipped / size };
}

export function createWaveformPreview(samples, points = 260) {
  if (!samples.length) return [];
  const block = Math.max(1, Math.floor(samples.length / points));
  const result = [];
  for (let offset = 0; offset < samples.length; offset += block) {
    let peak = 0;
    for (let index = offset; index < Math.min(offset + block, samples.length); index += 1) {
      peak = Math.max(peak, Math.abs(samples[index]));
    }
    result.push(peak);
  }
  return result.slice(0, points);
}

export function recordingQuality(recording) {
  if (!recording) return null;
  if (recording.clippedRatio > 0.002 || recording.peak >= 0.998) {
    return { tone: "warn", label: "音割れに注意" };
  }
  if (recording.rms < 0.018 || recording.peak < 0.08) {
    return { tone: "warn", label: "音量が小さめ" };
  }
  if (recording.duration < 0.8) return { tone: "warn", label: "録音が短め" };
  return { tone: "good", label: "音量は良好" };
}
