import assert from "node:assert/strict";
import test from "node:test";

import {
  CAPTION_PRESETS,
  EMOJI_PALETTE,
  FEATURED_EMOJI,
  insertAtSelection,
} from "../src/emoji-data.js";

test("Irodori公式の演技記号45種を重複なく提供する", () => {
  assert.equal(EMOJI_PALETTE.length, 45);
  assert.equal(new Set(EMOJI_PALETTE.map((item) => item.emoji)).size, 45);
  assert.ok(EMOJI_PALETTE.some((item) => item.emoji === "👂" && item.label === "囁き"));
  assert.ok(EMOJI_PALETTE.some((item) => item.emoji === "📖" && item.label === "朗読"));
});

test("よく使う演技は公式パレットの部分集合である", () => {
  assert.equal(FEATURED_EMOJI.length, 10);
  assert.ok(FEATURED_EMOJI.every((item) => EMOJI_PALETTE.includes(item)));
});

test("選択範囲を演技記号で置換し、その直後へカーソルを戻す", () => {
  const result = insertAtSelection("今日は嬉しいです", "😆", 3, 6);
  assert.deepEqual(result, { text: "今日は😆です", caret: 5 });
});

test("captionプリセットは空でない一意な指示を持つ", () => {
  assert.equal(CAPTION_PRESETS.length, 9);
  assert.equal(new Set(CAPTION_PRESETS.map((preset) => preset.caption)).size, 9);
  assert.ok(CAPTION_PRESETS.every((preset) => preset.caption.trim().length > 0));
});
