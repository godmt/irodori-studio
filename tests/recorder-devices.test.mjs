import assert from "node:assert/strict";
import test from "node:test";

import { enumerateAudioInputs } from "../src/features/recorder/recorder-devices.js";

test("audio input enumeration filters non-microphone devices", async () => {
  const devices = await enumerateAudioInputs({
    enumerateDevices: async () => [
      { kind: "audioinput", deviceId: "mic", label: "Studio Mic" },
      { kind: "audiooutput", deviceId: "speaker", label: "Speaker" },
      { kind: "videoinput", deviceId: "camera", label: "Camera" },
    ],
  });

  assert.deepEqual(devices.map((device) => device.deviceId), ["mic"]);
});

test("audio input enumeration retries until browser exposes labels", async () => {
  let calls = 0;
  const waits = [];
  const devices = await enumerateAudioInputs({
    enumerateDevices: async () => {
      calls += 1;
      return [{ kind: "audioinput", deviceId: "mic", label: calls < 3 ? "" : "Studio Mic" }];
    },
  }, {
    waitForLabels: true,
    retryDelays: [0, 20, 40],
    wait: async (delay) => waits.push(delay),
  });

  assert.equal(calls, 3);
  assert.deepEqual(waits, [20, 40]);
  assert.equal(devices[0].label, "Studio Mic");
});
