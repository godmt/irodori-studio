import assert from "node:assert/strict";
import test from "node:test";

import { strFromU8, unzipSync } from "fflate";

import corpus from "../src/features/recorder/corpus.json" with { type: "json" };
import { createRecordingArchive, selectAcceptedPrompts } from "../src/features/recorder/recorder-export.js";

test("the official starter corpus remains complete and stable", () => {
  assert.equal(corpus.length, 120);
  assert.equal(new Set(corpus.map((prompt) => prompt.id)).size, 120);
  assert.equal(corpus[0].id, "irodori_v2_0001");
  assert.equal(corpus.at(-1).id, "irodori_v2_0120");
});

test("recording export includes accepted takes only", async () => {
  const prompts = corpus.slice(0, 3);
  const recordings = {
    [prompts[0].id]: { accepted: true, blob: new Blob([new Uint8Array([1, 2, 3])]) },
    [prompts[1].id]: { accepted: false, blob: new Blob([new Uint8Array([4, 5, 6])]) },
  };

  assert.deepEqual(selectAcceptedPrompts(prompts, recordings).map((prompt) => prompt.id), [prompts[0].id]);

  const archive = unzipSync(await createRecordingArchive(prompts, recordings));
  assert.ok(archive[`wavs/${prompts[0].id}.wav`]);
  assert.equal(archive[`wavs/${prompts[1].id}.wav`], undefined);
  assert.ok(archive["dataset.jsonl"]);
  assert.ok(archive["recording_report.json"]);
  assert.ok(archive["README.txt"]);

  const manifest = strFromU8(archive["dataset.jsonl"]).trim().split("\n").map(JSON.parse);
  assert.equal(manifest.length, 1);
  assert.equal(manifest[0].id, prompts[0].id);
  assert.equal(manifest[0].audio, `wavs/${prompts[0].id}.wav`);
  assert.deepEqual(manifest[0].coverage_tags, prompts[0].coverageTags);

  const report = JSON.parse(strFromU8(archive["recording_report.json"]));
  assert.equal(report.sample_rate, 48_000);
  assert.equal(report.recorded, 1);
  assert.equal(report.total_prompts, 3);
});
