import test from "node:test";
import assert from "node:assert/strict";

import { createLine } from "../src/defaults.js";
import {
  audioFilesForLine,
  appendLineTake,
  duplicateLine,
  removedAudioFiles,
  selectLineTake,
  splitImportedText,
  updateLine,
} from "../src/project-state.js";

test("editing generated text marks the line stale", () => {
  const line = createLine({ text: "元の文章", audioFile: "one.wav", stale: false });
  const [updated] = updateLine([line], line.id, { text: "新しい文章" });
  assert.equal(updated.stale, true);
  assert.equal(updated.audioFile, "one.wav");
  assert.equal(updated.takes[0].stale, true);
});

test("duplicate creates an unrendered line directly after the source", () => {
  const first = createLine({ text: "一", audioFile: "one.wav" });
  const second = createLine({ text: "二" });
  const result = duplicateLine([first, second], first.id);
  assert.equal(result.length, 3);
  assert.equal(result[1].text, "一");
  assert.equal(result[1].audioFile, null);
  assert.deepEqual(result[1].takes, []);
  assert.notEqual(result[1].id, first.id);
});

test("new generations become selected takes without losing the previous take", () => {
  const line = createLine({ text: "候補", audioFile: "first.wav", duration: 1.2 });
  const previousTakeId = line.selectedTakeId;
  const [withSecond] = appendLineTake([line], line.id, {
    audioFile: "second.wav",
    duration: 1.4,
    generationSeconds: 0.8,
    usedSeed: 42,
  });
  assert.equal(withSecond.takes.length, 2);
  assert.equal(withSecond.audioFile, "second.wav");
  assert.notEqual(withSecond.selectedTakeId, previousTakeId);

  const [selectedPrevious] = selectLineTake([withSecond], line.id, previousTakeId);
  assert.equal(selectedPrevious.audioFile, "first.wav");
  assert.equal(selectedPrevious.duration, 1.2);
});

test("a fifth take keeps the previous selection and discards the oldest alternative", () => {
  const line = createLine({ text: "最大4候補" });
  let lines = [line];
  for (let index = 1; index <= 4; index += 1) {
    lines = appendLineTake(lines, line.id, { audioFile: `${index}.wav` });
  }
  const beforeFifth = lines[0];
  const previousSelection = beforeFifth.selectedTakeId;
  lines = appendLineTake(lines, line.id, { audioFile: "5.wav" });
  assert.equal(lines[0].takes.length, 4);
  assert.ok(lines[0].takes.some((take) => take.id === previousSelection));
  assert.equal(lines[0].audioFile, "5.wav");
  assert.equal(lines[0].takes.some((take) => take.audioFile === "1.wav"), false);
});

test("multiline import preserves input order and applies the selected voice", () => {
  const imported = splitImportedText("甲\n\n乙\n", { voiceId: "voice-selected" });
  assert.deepEqual(imported.map((line) => line.text), ["甲", "乙"]);
  assert.deepEqual(imported.map((line) => line.voiceId), ["voice-selected", "voice-selected"]);
});

test("line audio helpers include every take and report discarded files", () => {
  const previous = createLine({
    audioFile: "one.wav",
    takes: [
      { id: "take-one", audioFile: "one.wav" },
      { id: "take-two", audioFile: "two.wav" },
    ],
    selectedTakeId: "take-one",
  });
  const next = createLine({
    ...previous,
    takes: [{ id: "take-two", audioFile: "two.wav" }],
    selectedTakeId: "take-two",
  });
  assert.deepEqual(audioFilesForLine(previous).sort(), ["one.wav", "two.wav"]);
  assert.deepEqual(removedAudioFiles(previous, next), ["one.wav"]);
});
