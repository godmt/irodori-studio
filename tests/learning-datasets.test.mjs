import assert from "node:assert/strict";
import test from "node:test";

import { resolveLearningDatasetId } from "../src/learning-datasets.js";

const datasets = [
  { id: "usako", name: "Usako" },
  { id: "kamiyama", name: "Kamiyama" },
];

test("録音と学習で共有する選択中のデータセットを復元する", () => {
  assert.equal(resolveLearningDatasetId(datasets, "usako"), "usako");
  assert.equal(resolveLearningDatasetId(datasets, "kamiyama"), "kamiyama");
});

test("削除済みの選択状態は利用可能なデータセットへ戻す", () => {
  assert.equal(resolveLearningDatasetId(datasets, "missing"), "usako");
  assert.equal(resolveLearningDatasetId([], "usako"), "");
});
