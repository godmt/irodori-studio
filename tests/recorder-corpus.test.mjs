import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { strFromU8, unzipSync } from "fflate";

import {
  AICA_SOURCE,
  CORPUS_ROOT,
  CORPUS_STAGES,
  getCorpusPrompts,
} from "../src/features/recorder/corpus-catalog.js";
import { createRecordingArchive } from "../src/features/recorder/recorder-export.js";

test("recorder stages are views over one shared prompt root", () => {
  assert.equal(CORPUS_ROOT.length, 620);
  assert.equal(new Set(CORPUS_ROOT.map((prompt) => prompt.id)).size, 620);
  assert.deepEqual(CORPUS_STAGES.map((stage) => stage.level), [1, 2, 3]);

  const starter = getCorpusPrompts("starter");
  const core = getCorpusPrompts("aica-core");
  const full = getCorpusPrompts("aica-full");
  const fullById = new Map(full.map((prompt) => [prompt.id, prompt]));

  assert.equal(starter.length, 120);
  assert.equal(core.length, 200);
  assert.equal(full.length, 500);
  assert.ok(core.every((prompt) => fullById.get(prompt.id) === prompt));
});

function normalizePromptText(text) {
  return text.normalize("NFKC").replace(/[\s、。！？!?…・「」『』（）()]/g, "");
}

function characterBigrams(text) {
  const normalized = normalizePromptText(text);
  return new Set(Array.from({ length: Math.max(0, normalized.length - 1) }, (_, index) => normalized.slice(index, index + 2)));
}

function diceSimilarity(left, right) {
  if (!left.size && !right.size) return 1;
  let overlap = 0;
  for (const value of left) if (right.has(value)) overlap += 1;
  return (2 * overlap) / (left.size + right.size);
}

test("Irodori Starter v2 contains 120 distinct, non-paraphrased prompts", () => {
  const starter = getCorpusPrompts("starter");
  assert.ok(starter.every((prompt, index) => prompt.id === `irodori_v2_${String(index + 1).padStart(4, "0")}`));

  const normalizedTexts = starter.map((prompt) => normalizePromptText(prompt.text));
  assert.equal(new Set(normalizedTexts).size, 120);

  const bigrams = starter.map((prompt) => characterBigrams(prompt.text));
  for (let left = 0; left < starter.length; left += 1) {
    for (let right = left + 1; right < starter.length; right += 1) {
      assert.ok(
        diceSimilarity(bigrams[left], bigrams[right]) < 0.82,
        `near-duplicate prompts: ${starter[left].id} and ${starter[right].id}`,
      );
    }
  }
});

test("Irodori Starter v2 explicitly covers Japanese mora classes and foreign mora", () => {
  const starter = getCorpusPrompts("starter");
  const coverage = new Set(starter.flatMap((prompt) => prompt.coverageTags || []));
  const requiredCoverage = [
    "母音", "カ行", "サ行", "タ行", "ナ行", "ハ行", "マ行", "ヤ行", "ラ行", "ワ行",
    "ガ行", "ザ行", "ダ行", "バ行", "パ行", "濁音", "半濁音",
    "キャ行", "キュ音", "キョ音", "ギャ音", "ギュ音", "ギョ音",
    "シャ行", "シュ音", "ショ音", "ジャ行", "ジュ音", "ジョ音",
    "チャ行", "チュ音", "チョ音", "ニャ音", "ニュ音", "ニョ音",
    "ヒャ音", "ヒュ音", "ヒョ音", "ビャ音", "ビュ音", "ビョ音",
    "ピャ音", "ピュ音", "ピョ音", "ミャ音", "ミュ音", "ミョ音",
    "リャ音", "リュ音", "リョ音", "促音", "撥音", "長音", "長母音", "連母音", "無声化",
    "ファ行", "ウィ音", "ウェ音", "シェ音", "ジェ音", "チェ音",
    "ティ音", "ディ音", "デュ音", "ヴ音", "ヴェ音", "ツァ音", "ツィ音", "クォ音", "トゥ音", "ドゥ音",
    "数字", "時刻", "金額", "小数", "助数詞", "日付", "敬語",
  ];
  assert.deepEqual(requiredCoverage.filter((tag) => !coverage.has(tag)), []);
});

test("Irodori Starter v2 has twenty distinct fillers and backchannels", () => {
  const fillerPrompts = getCorpusPrompts("starter").filter((prompt) => prompt.category === "filler");
  assert.equal(fillerPrompts.length, 20);
  const fillerTags = fillerPrompts.map((prompt) => prompt.coverageTags?.[0]);
  assert.equal(new Set(fillerTags).size, 20);
  assert.deepEqual(fillerTags, [
    "フィラー:えーと", "フィラー:あの", "フィラー:うーん", "フィラー:えっと", "フィラー:まあ",
    "フィラー:その", "フィラー:なんというか", "フィラー:ほら", "フィラー:そうですね", "フィラー:たしか",
    "フィラー:あー", "フィラー:ええと", "相づち:ええ", "相づち:はい", "相づち:なるほど",
    "相づち:そっか", "相づち:へえ", "相づち:そうそう", "フィラー:あ、そうだ", "フィラー:んー",
  ]);
});

test("AICA exports preserve upstream credit and stage metadata", async () => {
  const prompts = getCorpusPrompts("aica-core").slice(0, 2);
  const stage = CORPUS_STAGES.find((item) => item.id === "aica-core");
  const recordings = {
    [prompts[0].id]: { accepted: true, blob: new Blob([new Uint8Array([1, 2, 3])]) },
  };
  const archive = unzipSync(await createRecordingArchive(prompts, recordings, stage));
  const row = JSON.parse(strFromU8(archive["dataset.jsonl"]).trim());
  const report = JSON.parse(strFromU8(archive["recording_report.json"]));
  const credits = strFromU8(archive["CREDITS.txt"]);

  assert.equal(row.source_name, AICA_SOURCE.name);
  assert.equal(row.source_id.length, 4);
  assert.equal(row.source_license, "CC0-1.0");
  assert.equal(report.corpus_stage, "aica-core");
  assert.match(credits, /reinehonoka/);
  assert.match(credits, /CC0 1\.0 Universal/);

  const license = await readFile(new URL("../third_party/aica-corpus/LICENSE", import.meta.url), "utf8");
  assert.match(license, /^CC0 1\.0 Universal/);
});
