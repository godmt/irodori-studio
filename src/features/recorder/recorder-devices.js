const DEFAULT_RETRY_DELAYS = [0, 50, 150, 300, 600, 1_200];
const sleep = (delay) => new Promise((resolve) => globalThis.setTimeout(resolve, delay));

export async function enumerateAudioInputs(
  mediaDevices,
  { waitForLabels = false, retryDelays = DEFAULT_RETRY_DELAYS, wait = sleep, onDevices } = {},
) {
  if (!mediaDevices?.enumerateDevices) return [];
  const delays = waitForLabels ? retryDelays : [0];
  let inputs = [];
  for (const delay of delays) {
    if (delay > 0) await wait(delay);
    inputs = (await mediaDevices.enumerateDevices()).filter((device) => device.kind === "audioinput");
    onDevices?.(inputs);
    if (!waitForLabels || inputs.some((device) => device.label?.trim())) break;
  }
  return inputs;
}
