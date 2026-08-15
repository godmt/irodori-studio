import assert from "node:assert/strict";
import test from "node:test";

import {
  playbackFailureMessage,
  shouldRetryWithSystemOutput,
} from "../src/playback.js";

test("自動再生拒否は履歴から再試行できる案内にする", () => {
  assert.equal(
    playbackFailureMessage({ name: "NotAllowedError" }),
    "ブラウザーが自動再生を止めました。発話履歴の再生ボタンを押してください",
  );
});

test("選択中の出力先だけが失敗した場合はシステム既定で再試行する", () => {
  assert.equal(shouldRetryWithSystemOutput({ name: "NotReadableError" }, "virtual-cable"), true);
  assert.equal(shouldRetryWithSystemOutput({ name: "NotAllowedError" }, "virtual-cable"), false);
  assert.equal(shouldRetryWithSystemOutput({ name: "NotReadableError" }, ""), false);
});

test("不明な再生失敗ではブラウザーの詳細を残す", () => {
  assert.equal(
    playbackFailureMessage({ name: "UnknownError", message: "device vanished" }),
    "音声を再生できませんでした: device vanished",
  );
});
