import { strToU8, zipSync } from "fflate";

import { RECORDER_SAMPLE_RATE } from "./recorder-audio.js";

export function selectAcceptedPrompts(prompts, recordings) {
  return prompts.filter((prompt) => recordings[prompt.id]?.accepted === true);
}

export async function createRecordingArchive(prompts, recordings, stage = {}) {
  const selected = selectAcceptedPrompts(prompts, recordings);
  const files = {};
  const manifest = selected.map((item) => ({
    id: item.id,
    audio: `wavs/${item.id}.wav`,
    text: item.text,
    caption: item.direction,
    category: item.category,
    style: item.style,
    emotion: item.emotion,
    intensity: item.intensity,
    expected_seconds: item.expectedSeconds,
    coverage_tags: item.coverageTags || [],
    source_id: item.sourceId || item.id,
    source_name: item.sourceName || "Irodori Studio",
    source_url: item.sourceUrl || null,
    source_version: item.sourceVersion || null,
    source_license: item.license || null,
  }));
  const entries = await Promise.all(selected.map(async (item) => [
    item,
    new Uint8Array(await recordings[item.id].blob.arrayBuffer()),
  ]));
  for (const [item, bytes] of entries) files[`wavs/${item.id}.wav`] = bytes;
  files["dataset.jsonl"] = strToU8(`${manifest.map((row) => JSON.stringify(row)).join("\n")}\n`);
  files["recording_report.json"] = strToU8(JSON.stringify({
    created_at: new Date().toISOString(),
    format: "PCM 16-bit mono WAV",
    sample_rate: RECORDER_SAMPLE_RATE,
    recorded: selected.length,
    total_prompts: prompts.length,
    corpus_stage: stage.id || null,
    corpus_title: stage.title || null,
    corpus_level: stage.level || null,
  }, null, 2));
  const usesAica = prompts.some((prompt) => prompt.sourceName === "AICA corpus");
  files["README.txt"] = strToU8(`Irodori-TTS recording dataset\n\nCorpus: ${stage.title || "Custom selection"}\nAudio: 48 kHz / mono / PCM 16-bit WAV\nManifest: dataset.jsonl\nIncluded: ${selected.length} accepted recording(s) of ${prompts.length} prompts.\nOnly accepted recordings are included. All files were captured and packaged locally in Irodori Studio.\n${usesAica ? "See CREDITS.txt for the AICA text corpus source and license.\n" : ""}`);
  if (usesAica) {
    files["CREDITS.txt"] = strToU8(`AICA corpus (AI Character Audio corpus)\n\nCreator: reinehonoka\nSource: https://github.com/reinehonoka/aica-corpus\nVersion: v1.0.0\nPinned commit: ce51cdfb3f0d8110cf1266ee3ca1fb7260a9ee88\nLicense: CC0 1.0 Universal\nLicense text: https://github.com/reinehonoka/aica-corpus/blob/ce51cdfb3f0d8110cf1266ee3ca1fb7260a9ee88/LICENSE\n\nIrodori Studio adds a Core 200 selection, recording categories, performance directions, estimated durations, and staged recording views. Upstream prompt IDs and source text are preserved in dataset.jsonl.\n\nCC0 applies to the upstream AICA text. Newly recorded audio is a separate recording and is not automatically offered under CC0. The performer or project owner is responsible for the rights and permissions applicable to recorded audio.\n`);
  }
  return zipSync(files, { level: 6 });
}
