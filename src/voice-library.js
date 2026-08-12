import { DEFAULT_VOICE_API, uid } from "./defaults.js";

export const VOICE_COLORS = ["#c9651b", "#35766d", "#7960a8", "#a94848", "#476b9b", "#7c7138"];

function normalizedName(value) {
  return String(value || "").trim().toLocaleLowerCase("ja-JP");
}

export function voiceProfileToVoice(profile, existing = {}, index = 0) {
  return {
    ...DEFAULT_VOICE_API,
    ...existing,
    id: existing.id || uid("voice"),
    name: profile.name || existing.name || `ボイス ${index + 1}`,
    color: existing.color || VOICE_COLORS[index % VOICE_COLORS.length],
    sourceType: profile.source_type || "none",
    refEmbed: profile.ref_embed || "",
    refWavs: Array.isArray(profile.ref_wavs) ? [...profile.ref_wavs] : [],
    loraAdapter: profile.lora_adapter || "",
    defaultCaption: profile.default_caption || "",
    apiProfileId: profile.profile_id || null,
    apiEnabled: Boolean(profile.enabled),
    apiSpeakerUuid: profile.speaker_uuid || null,
    apiStyleId: profile.style_id ?? null,
    apiStyleName: profile.style_name || "ノーマル",
    apiSpeed: Number(profile.speed ?? 1),
    apiNumSteps: Number(profile.num_steps ?? 12),
    apiSeed: profile.seed ?? null,
    apiCfgScaleText: Number(profile.cfg_scale_text ?? 3),
    apiCfgScaleCaption: Number(profile.cfg_scale_caption ?? 3),
    apiCfgScaleSpeaker: Number(profile.cfg_scale_speaker ?? 5),
    apiPolicy: profile.policy || "",
  };
}

export function voiceToProfilePayload(voice) {
  return {
    profile_id: voice.apiProfileId || null,
    name: String(voice.name || "").trim(),
    style_name: String(voice.apiStyleName || "ノーマル").trim(),
    enabled: Boolean(voice.apiEnabled),
    source_type: voice.sourceType || "none",
    ref_embed: voice.refEmbed || null,
    ref_wavs: (voice.refWavs || []).filter(Boolean),
    lora_adapter: voice.loraAdapter || null,
    default_caption: voice.defaultCaption || "",
    speed: Number(voice.apiSpeed ?? 1),
    num_steps: Number(voice.apiNumSteps ?? 12),
    seed: voice.apiSeed === "" || voice.apiSeed == null ? null : Number(voice.apiSeed),
    cfg_scale_text: Number(voice.apiCfgScaleText ?? 3),
    cfg_scale_caption: Number(voice.apiCfgScaleCaption ?? 3),
    cfg_scale_speaker: Number(voice.apiCfgScaleSpeaker ?? 5),
    policy: voice.apiPolicy || "",
  };
}

export function voiceFingerprint(voice) {
  const { profile_id: _profileId, ...content } = voiceToProfilePayload(voice);
  return JSON.stringify(content);
}

export function voicePersistenceError(voice) {
  if (!String(voice.name || "").trim()) return "ボイス名を入力してください";
  if (!voice.apiEnabled) return null;
  if (voice.sourceType === "speaker" && !String(voice.refEmbed || "").trim()) {
    return "API公開するSpeaker Inversionファイルを選択してください";
  }
  if (voice.sourceType === "reference" && !(voice.refWavs || []).some(Boolean)) {
    return "API公開する参照音声を1件以上選択してください";
  }
  return null;
}

export function mergeVoiceLibrary(project, profiles = []) {
  if (!project?.voices?.length || !profiles.length) return project;
  const profilesById = new Map(profiles.map((profile) => [profile.profile_id, profile]));
  const profilesByName = new Map();
  for (const profile of profiles) {
    const name = normalizedName(profile.name);
    if (!profilesByName.has(name)) profilesByName.set(name, []);
    profilesByName.get(name).push(profile);
  }

  const linked = new Set();
  const voices = project.voices.map((voice, index) => {
    let profile = voice.apiProfileId ? profilesById.get(voice.apiProfileId) : null;
    if (!profile) {
      const sameName = profilesByName.get(normalizedName(voice.name)) || [];
      if (sameName.length === 1) profile = sameName[0];
    }
    if (!profile) return voice;
    linked.add(profile.profile_id);
    return voiceProfileToVoice(profile, voice, index);
  });

  for (const profile of profiles) {
    if (linked.has(profile.profile_id)) continue;
    voices.push(voiceProfileToVoice(profile, {}, voices.length));
  }
  return { ...project, voices };
}
