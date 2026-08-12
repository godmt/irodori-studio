export const AUDIO_OUTPUT_STORAGE_KEY = "irodori-studio-audio-output-v2";

export const DEFAULT_AUDIO_OUTPUT = {
  deviceId: "",
  label: "システム既定",
};

export function parseAudioOutputPreference(raw) {
  if (!raw) return { ...DEFAULT_AUDIO_OUTPUT, configured: false };
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.deviceId !== "string") {
      return { ...DEFAULT_AUDIO_OUTPUT, configured: false };
    }
    return {
      deviceId: parsed.deviceId,
      label: typeof parsed.label === "string" && parsed.label.trim()
        ? parsed.label.trim()
        : parsed.deviceId ? "選択した音声出力" : DEFAULT_AUDIO_OUTPUT.label,
      configured: true,
    };
  } catch {
    return { ...DEFAULT_AUDIO_OUTPUT, configured: false };
  }
}

export function normalizeAudioOutputs(devices = [], selectedDevice = null) {
  const outputs = [{ ...DEFAULT_AUDIO_OUTPUT }];
  const seen = new Set(["", "default"]);
  for (const device of [...devices, selectedDevice].filter(Boolean)) {
    if (device.kind !== "audiooutput" || !device.deviceId || seen.has(device.deviceId)) continue;
    seen.add(device.deviceId);
    outputs.push({
      deviceId: device.deviceId,
      label: device.label?.trim() || `音声出力 ${outputs.length}`,
    });
  }
  return outputs;
}
