import starterCorpus from "./corpus.json" with { type: "json" };
import aicaSource from "./aica-corpus.json" with { type: "json" };

export const AICA_SOURCE = Object.freeze({
  id: "aica-corpus",
  name: "AICA corpus",
  creator: "reinehonoka",
  url: "https://github.com/reinehonoka/aica-corpus",
  version: "v1.0.0",
  commit: "ce51cdfb3f0d8110cf1266ee3ca1fb7260a9ee88",
  license: "CC0-1.0",
});

const CORE_AICA_IDS = `
0003 0005 0006 0012 0013 0016 0017 0020 0021 0022 0025 0026 0028 0029 0030 0031 0032 0033 0034 0036
0041 0047 0048 0050 0052 0054 0055 0057 0058 0060 0061 0062 0063 0065 0066 0067 0069 0070 0071 0073
0075 0078 0081 0082 0083 0084 0085 0086 0087 0089 0091 0092 0093 0094 0095 0096 0097 0098 0104 0108
0112 0113 0115 0119 0120 0126 0132 0134 0136 0144 0148 0152 0153 0159 0162 0163 0169 0170 0176 0181
0183 0184 0195 0197 0201 0207 0211 0213 0214 0216 0218 0219 0221 0223 0224 0226 0227 0234 0242 0244
0246 0249 0254 0258 0263 0264 0265 0275 0283 0291 0292 0294 0304 0306 0311 0317 0323 0325 0326 0337
0342 0343 0344 0347 0348 0349 0352 0356 0358 0360 0362 0363 0369 0370 0371 0372 0373 0374 0375 0376
0378 0379 0381 0383 0385 0386 0387 0388 0389 0390 0393 0394 0395 0398 0400 0403 0404 0407 0408 0410
0416 0419 0421 0422 0423 0424 0425 0434 0435 0438 0440 0441 0444 0445 0447 0449 0452 0453 0456 0460
0464 0465 0467 0469 0470 0473 0474 0475 0480 0485 0486 0487 0490 0491 0493 0494 0496 0497 0498 0500
`.trim().split(/\s+/).map((id) => `aica_${id}`);

function aicaPerformance(id) {
  const number = Number(id);
  if (number <= 40) return { category: "daily_assistant", style: "neutral", emotion: "neutral", intensity: "medium", direction: "自然なAIアシスタントの会話として、句読点で短く間を取りながら明瞭に話す" };
  if (number <= 60) return { category: "casual_lifestyle", style: "neutral", emotion: "joy", intensity: "low", direction: "親しい相手との雑談として、作り込みすぎず自然な明るさで話す" };
  if (number <= 80) return { category: "it_system", style: "formal", emotion: "neutral", intensity: "medium", direction: "IT用語を崩さず、案内として聞き取りやすい速さで話す" };
  if (number <= 100) return { category: "loanword_coverage", style: "formal", emotion: "neutral", intensity: "medium", direction: "カタカナ語を一音ずつ意識しつつ、文章全体は自然につなげる" };
  if (number <= 130) return { category: "filler_uun", style: "hesitant", emotion: "neutral", intensity: "low", direction: "「うーん」を考えながら自然に発し、そのまま後続の言葉へつなげる" };
  if (number <= 160) return { category: "filler_etto", style: "hesitant", emotion: "neutral", intensity: "low", direction: "言葉を探す自然な間を置き、「えー／えっと」から会話を続ける" };
  if (number <= 190) return { category: "filler_aa", style: "hesitant", emotion: "neutral", intensity: "low", direction: "思い出したり言い直したりするように、「あー／あっと」を自然に挟む" };
  if (number <= 250) return { category: "uncertain_monologue", style: "hesitant", emotion: "neutral", intensity: "low", direction: "考えが揺れている独り言として、三点リーダーでは短く自然な間を取る" };
  if (number <= 280) return { category: "laugh_ahaha", style: "laugh", emotion: "joy", intensity: "medium", direction: "明るい「あはは」の笑いを実際に声に出し、続く台詞へ自然につなげる" };
  if (number <= 310) return { category: "laugh_ufufu", style: "laugh", emotion: "joy", intensity: "low", direction: "口元に笑みを含んだ控えめな「うふふ」として、息を止めずに話す" };
  if (number <= 340) return { category: "laugh_ehehe", style: "laugh", emotion: "joy", intensity: "medium", direction: "照れや嬉しさを含む「えへへ」を声に出し、台詞へ自然につなげる" };
  if (number <= 350) return { category: "laugh_rare", style: "laugh", emotion: "joy", intensity: "high", direction: "指定された特徴的な笑い方を演じ、誇張しすぎない範囲で個性を出す" };
  if (number <= 390) return { category: "short_response", style: "neutral", emotion: "neutral", intensity: "medium", direction: "短い返答として意図を明確にし、語尾まで省略せず話す" };
  if (number <= 410) return { category: "system_status", style: "formal", emotion: "neutral", intensity: "medium", direction: "システムの状態報告として、落ち着いて簡潔に伝える" };
  if (number <= 450) return { category: "question_observation", style: "calm", emotion: "neutral", intensity: "low", direction: "相手の様子を見ながら問いかけるように、間を生かして話す" };
  if (number <= 475) return { category: "emotion_relationship", style: "affection", emotion: "affection", intensity: "medium", direction: "親しさや戸惑いを言葉の流れに沿って表し、過度な演技にはしない" };
  return { category: "technical_command", style: "formal", emotion: "neutral", intensity: "medium", direction: "技術的な操作案内として、短い間と語句の区切りを明瞭にする" };
}

function estimateSeconds(text) {
  const spokenCharacters = Array.from(text.replace(/[、。！？!?…・「」『』（）()　\s]/g, "")).length;
  const pauses = (text.match(/…/g) || []).length * 0.3;
  return Math.round(Math.max(2, spokenCharacters / 4.9 + pauses) * 10) / 10;
}

const starterPrompts = starterCorpus.map((prompt) => Object.freeze({
  ...prompt,
  sourceId: prompt.id,
  sourceName: "Irodori Starter 120",
  sourceUrl: "",
  sourceVersion: "2",
  license: "Irodori Studio project corpus",
}));

const aicaPrompts = aicaSource.map((prompt) => Object.freeze({
  id: `aica_${prompt.id}`,
  sourceId: prompt.id,
  text: prompt.text,
  ...aicaPerformance(prompt.id),
  expectedSeconds: estimateSeconds(prompt.text),
  sourceName: AICA_SOURCE.name,
  sourceUrl: AICA_SOURCE.url,
  sourceVersion: `${AICA_SOURCE.version} (${AICA_SOURCE.commit})`,
  license: AICA_SOURCE.license,
}));

export const CORPUS_ROOT = Object.freeze([...starterPrompts, ...aicaPrompts]);
const promptsById = new Map(CORPUS_ROOT.map((prompt) => [prompt.id, prompt]));

const stageDefinitions = [
  {
    id: "starter",
    level: 1,
    title: "Irodori Starter 120",
    optionLabel: "第1段階 · 基礎 120文",
    description: "重複のない120文で、発音・数字・外来音・基本感情・フィラーを収録します。",
    promptIds: starterPrompts.map((prompt) => prompt.id),
  },
  {
    id: "aica-core",
    level: 2,
    title: "AICA Character Core 200",
    optionLabel: "第2段階 · キャラクター 200文",
    description: "フィラー、笑い、短い応答をバランスよく追加します。",
    promptIds: CORE_AICA_IDS,
    source: AICA_SOURCE,
  },
  {
    id: "aica-full",
    level: 3,
    title: "AICA Full 500",
    optionLabel: "第3段階 · AICA 全500文",
    description: "Core 200の録音を引き継ぎ、表現の変種をすべて収録します。",
    promptIds: aicaPrompts.map((prompt) => prompt.id),
    source: AICA_SOURCE,
  },
];

export const CORPUS_STAGES = Object.freeze(stageDefinitions.map((stage) => Object.freeze({ ...stage })));
const stagesById = new Map(CORPUS_STAGES.map((stage) => [stage.id, stage]));

export function getCorpusStage(stageId) {
  return stagesById.get(stageId) || CORPUS_STAGES[0];
}

export function getCorpusPrompts(stageId) {
  return getCorpusStage(stageId).promptIds.map((id) => promptsById.get(id)).filter(Boolean);
}
