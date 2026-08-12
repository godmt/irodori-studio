import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeAudioOutputs,
  parseAudioOutputPreference,
} from "../src/audio-output.js";

test("音声出力一覧はシステム既定を先頭に置き、入力機器と重複を除外する", () => {
  const outputs = normalizeAudioOutputs([
    { kind: "audioinput", deviceId: "mic", label: "Microphone" },
    { kind: "audiooutput", deviceId: "default", label: "Default Speakers" },
    { kind: "audiooutput", deviceId: "cable", label: "CABLE Input" },
    { kind: "audiooutput", deviceId: "cable", label: "CABLE Input" },
    { kind: "audiooutput", deviceId: "monitor", label: "" },
  ]);

  assert.deepEqual(outputs, [
    { deviceId: "", label: "システム既定" },
    { deviceId: "cable", label: "CABLE Input" },
    { deviceId: "monitor", label: "音声出力 2" },
  ]);
});

test("許可直後の出力デバイスを列挙結果へ補完する", () => {
  const outputs = normalizeAudioOutputs([], {
    kind: "audiooutput",
    deviceId: "obs-cable",
    label: "OBS Virtual Cable",
  });
  assert.equal(outputs.at(-1).deviceId, "obs-cable");
});

test("保存済み出力先を安全に復元する", () => {
  assert.deepEqual(parseAudioOutputPreference(null), {
    deviceId: "",
    label: "システム既定",
    configured: false,
  });
  assert.deepEqual(parseAudioOutputPreference('{"deviceId":"cable","label":" CABLE Input "}'), {
    deviceId: "cable",
    label: "CABLE Input",
    configured: true,
  });
  assert.equal(parseAudioOutputPreference("broken").configured, false);
});
