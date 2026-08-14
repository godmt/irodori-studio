export const QUALITY_PRESETS = {
  live: { label: "配信優先", short: "LIVE", numSteps: 12, description: "待ち時間を抑えた配信用" },
  balanced: { label: "バランス", short: "BAL", numSteps: 24, description: "確認と仮編集に最適" },
  quality: { label: "最高品質", short: "HQ", numSteps: 40, description: "最終音声の標準設定" },
  studio: { label: "仕上げ", short: "MAX", numSteps: 60, description: "時間をかけた最終書き出し" },
};

export const DEFAULT_PARAMS = {
  quality: "quality",
  speed: 1,
  numSteps: 40,
  cfgScaleText: 3,
  cfgScaleSpeaker: 5,
  cfgScaleCaption: 3,
  seed: null,
  cfgGuidanceMode: "independent",
  tScheduleMode: "linear",
  swayCoeff: -1,
  truncationFactor: null,
  speakerKvScale: null,
  speakerKvMinT: 0.9,
  contextKvCache: true,
};

export const DEFAULT_VOICE_API = {
  apiProfileId: null,
  apiOrder: null,
  apiEnabled: false,
  apiSpeakerUuid: null,
  apiStyleId: null,
  apiStyleName: "ノーマル",
  apiSpeed: 1,
  apiNumSteps: 12,
  apiSeed: null,
  apiCfgScaleText: 3,
  apiCfgScaleCaption: 3,
  apiCfgScaleSpeaker: 5,
  apiPolicy: "",
};

export function uid(prefix = "line") {
  if (globalThis.crypto?.randomUUID) return `${prefix}-${globalThis.crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createTake(overrides = {}) {
  const id = overrides.id || uid("take");
  return {
    id,
    audioFile: null,
    duration: null,
    generationSeconds: null,
    usedSeed: null,
    stale: false,
    createdAt: new Date().toISOString(),
    ...overrides,
    id,
  };
}

export function createLine(overrides = {}) {
  const suppliedTakes = Array.isArray(overrides.takes)
    ? overrides.takes.filter((take) => take?.audioFile).map((take) => createTake(take))
    : [];
  const takes = suppliedTakes.length
    ? suppliedTakes
    : overrides.audioFile
      ? [createTake({
        id: overrides.selectedTakeId || undefined,
        audioFile: overrides.audioFile,
        duration: overrides.duration ?? null,
        generationSeconds: overrides.generationSeconds ?? null,
        usedSeed: overrides.usedSeed ?? null,
        stale: Boolean(overrides.stale),
      })]
      : [];
  const selectedTakeId = takes.some((take) => take.id === overrides.selectedTakeId)
    ? overrides.selectedTakeId
    : takes.at(-1)?.id || null;
  const selectedTake = takes.find((take) => take.id === selectedTakeId) || null;
  return {
    id: uid("line"),
    text: "",
    caption: "",
    voiceId: "voice-main",
    params: { ...DEFAULT_PARAMS },
    status: "idle",
    audioFile: null,
    duration: null,
    generationSeconds: null,
    usedSeed: null,
    jobId: null,
    error: null,
    stale: false,
    ...overrides,
    params: { ...DEFAULT_PARAMS, ...(overrides.params || {}) },
    takes,
    selectedTakeId,
    audioFile: selectedTake?.audioFile || null,
    duration: selectedTake?.duration ?? null,
    generationSeconds: selectedTake?.generationSeconds ?? null,
    usedSeed: selectedTake?.usedSeed ?? null,
    stale: selectedTake ? Boolean(selectedTake.stale) : Boolean(overrides.stale),
  };
}

const SAMPLE_LINES = [
  ["今日は少しだけ、聞いてほしい話があるんです。", "落ち着いた自然な声で、相手に語りかける"],
  ["窓の外には、やわらかな朝の光が広がっていました。", "穏やかなナレーション。情景を丁寧に描く"],
  ["えっ、本当に？　それはすごくうれしい！", "驚きから喜びへ。明るく弾むように"],
  ["大丈夫。焦らなくても、ひとつずつ進めばいいよ。", "安心させる優しい声で、少しゆっくり"],
  ["次のコーナーは、皆さんから届いたメッセージをご紹介します。", "配信番組の進行。明瞭で軽快に"],
  ["それでは最後に、今日の出来事を振り返ってみましょう。", "締めのナレーション。余韻を残して"],
];

export function createDefaultProject() {
  return {
    version: 2,
    title: "新しい音声プロジェクト",
    updatedAt: new Date().toISOString(),
    voices: [
      {
        ...DEFAULT_VOICE_API,
        id: "voice-main",
        name: "メインボイス",
        color: "#c9651b",
        sourceType: "none",
        refEmbed: "",
        refWavs: [],
        loraAdapter: "",
        defaultCaption: "",
      },
    ],
    lines: SAMPLE_LINES.map(([text, caption], index) => createLine({
      text,
      caption,
      params: { ...DEFAULT_PARAMS, seed: 27 + index },
    })),
    exportSettings: {
      gapMs: 250,
      includeMaster: true,
      includeSrt: true,
      includeVtt: true,
      includeCsv: true,
    },
  };
}

export function hydrateProject(raw) {
  const fallback = createDefaultProject();
  if (!raw || !Array.isArray(raw.lines)) return fallback;
  const voices = Array.isArray(raw.voices) && raw.voices.length
    ? raw.voices.map((voice) => ({ ...DEFAULT_VOICE_API, ...voice }))
    : fallback.voices;
  return {
    ...fallback,
    ...raw,
    voices,
    lines: raw.lines.map((line) => createLine(line)),
    exportSettings: { ...fallback.exportSettings, ...(raw.exportSettings || {}) },
  };
}

export function formatDuration(value) {
  if (!Number.isFinite(Number(value))) return "—";
  const seconds = Number(value);
  if (seconds < 60) return `${seconds.toFixed(1)}秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}分${Math.round(seconds % 60)}秒`;
}
