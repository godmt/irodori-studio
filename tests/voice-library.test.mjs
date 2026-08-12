import assert from "node:assert/strict";
import test from "node:test";

import { createDefaultProject } from "../src/defaults.js";
import {
  mergeVoiceLibrary,
  voiceFingerprint,
  voiceProfileToVoice,
  voiceToProfilePayload,
} from "../src/voice-library.js";

const SPEAKER_PROFILE = {
  profile_id: "profile-main",
  speaker_uuid: "speaker-stable",
  style_id: 1000,
  name: "メインボイス",
  style_name: "ノーマル",
  enabled: true,
  source_type: "speaker",
  ref_embed: "C:/voices/main.speaker.safetensors",
  ref_wavs: [],
  lora_adapter: null,
  default_caption: "優しく",
  speed: 1,
  num_steps: 12,
  seed: null,
  cfg_scale_text: 3,
  cfg_scale_caption: 3,
  cfg_scale_speaker: 5,
  policy: "",
};

test("移行前プロジェクトを一意な同名プロフィールへ再接続する", () => {
  const project = createDefaultProject();
  assert.equal(project.voices[0].sourceType, "none");
  const merged = mergeVoiceLibrary(project, [SPEAKER_PROFILE]);
  assert.equal(merged.voices[0].apiProfileId, "profile-main");
  assert.equal(merged.voices[0].sourceType, "speaker");
  assert.equal(merged.voices[0].refEmbed, "C:/voices/main.speaker.safetensors");
});

test("プロフィールIDを名前より優先し、未使用プロフィールもライブラリへ追加する", () => {
  const project = createDefaultProject();
  project.voices[0].apiProfileId = "profile-main";
  project.voices[0].name = "プロジェクト内の旧名";
  const second = { ...SPEAKER_PROFILE, profile_id: "profile-second", name: "ナレーター", style_id: 1001 };
  const merged = mergeVoiceLibrary(project, [SPEAKER_PROFILE, second]);
  assert.equal(merged.voices[0].name, "メインボイス");
  assert.equal(merged.voices[1].name, "ナレーター");
});

test("ボイスとサーバープロフィールを欠落なく往復できる", () => {
  const voice = voiceProfileToVoice(SPEAKER_PROFILE, { id: "voice-main", color: "#fff" });
  const payload = voiceToProfilePayload(voice);
  assert.equal(payload.profile_id, "profile-main");
  assert.equal(payload.source_type, "speaker");
  assert.equal(payload.ref_embed, SPEAKER_PROFILE.ref_embed);
  assert.equal(voiceFingerprint(voice), voiceFingerprint({ ...voice, apiProfileId: "changed-id" }));
});
