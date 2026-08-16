import assert from "node:assert/strict";
import test from "node:test";

import { runLiveSegmentPipeline } from "../src/features/live/live-synthesis.js";

test("配信の生成は先頭音声の再生完了を待たず全分割片を処理する", async () => {
  let releaseFirstPlayback;
  const firstPlayback = new Promise((resolve) => { releaseFirstPlayback = resolve; });
  let allProducedResolve;
  const allProduced = new Promise((resolve) => { allProducedResolve = resolve; });
  const produced = [];
  const consumed = [];

  const pipeline = runLiveSegmentPipeline({
    segmentCount: 4,
    produce: async (index) => {
      produced.push(index);
      if (produced.length === 4) allProducedResolve();
      return `audio-${index}`;
    },
    consume: async (audioFile, index) => {
      consumed.push(audioFile);
      if (index === 0) await firstPlayback;
    },
  });

  await allProduced;
  assert.deepEqual(produced, [0, 1, 2, 3]);
  assert.deepEqual(consumed, ["audio-0"]);

  releaseFirstPlayback();
  assert.deepEqual(await pipeline, ["audio-0", "audio-1", "audio-2", "audio-3"]);
  assert.deepEqual(consumed, ["audio-0", "audio-1", "audio-2", "audio-3"]);
});

test("生成失敗は待機中の再生側へ伝播する", async () => {
  await assert.rejects(
    runLiveSegmentPipeline({
      segmentCount: 3,
      produce: async (index) => {
        if (index === 1) throw new Error("segment failed");
        return `audio-${index}`;
      },
      consume: async () => {},
    }),
    /segment failed/,
  );
});
