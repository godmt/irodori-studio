import { api, datasetRecordingUrl } from "../../api.js";

const DB_NAME = "irodori-corpus-studio";
const STORE_NAME = "recordings";

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function runRequest(mode, operation) {
  return openDatabase().then((database) => new Promise((resolve, reject) => {
    const request = operation(database.transaction(STORE_NAME, mode).objectStore(STORE_NAME));
    request.onsuccess = () => {
      database.close();
      resolve(request.result);
    };
    request.onerror = () => {
      database.close();
      reject(request.error);
    };
  }));
}

export function readLegacyRecordings() {
  return runRequest("readonly", (store) => store.getAll());
}

export function clearLegacyRecordings() {
  return runRequest("readwrite", (store) => store.clear());
}

export function listRecordingDatasets() {
  return api.recordingDatasets();
}

export function createRecordingDataset(name) {
  return api.createRecordingDataset(name);
}

export function renameRecordingDataset(datasetId, name) {
  return api.renameRecordingDataset(datasetId, name);
}

export async function loadRecordingDataset(datasetId) {
  const dataset = await api.recordingDataset(datasetId, { corpusOnly: true });
  const recordings = Object.fromEntries(Object.entries(dataset.recordings || {}).map(([promptId, recording]) => [
    promptId,
    {
      ...recording,
      id: promptId,
      audioUrl: datasetRecordingUrl(datasetId, promptId),
    },
  ]));
  return { ...dataset, recordings };
}

export async function writeDatasetRecording(datasetId, recording, prompt) {
  const blob = recording.blob || (recording.audioUrl
    ? await fetch(recording.audioUrl).then((response) => {
      if (!response.ok) throw new Error("保存済み録音を読み込めませんでした。");
      return response.blob();
    })
    : null);
  if (!blob) throw new Error("保存する録音音声がありません。");
  const metadata = {
    duration: recording.duration,
    sampleRate: recording.sampleRate,
    preview: (recording.preview || []).map((value) => Math.round(value * 10000) / 10000),
    peak: recording.peak,
    rms: recording.rms,
    clippedRatio: recording.clippedRatio,
    accepted: recording.accepted,
    updatedAt: recording.updatedAt,
    acceptedAt: recording.acceptedAt || null,
    prompt: {
      id: prompt.id,
      sourceId: prompt.sourceId || prompt.id,
      text: prompt.text,
      direction: prompt.direction,
      category: prompt.category,
      style: prompt.style,
      emotion: prompt.emotion,
      intensity: prompt.intensity,
      expectedSeconds: prompt.expectedSeconds,
      sourceName: prompt.sourceName || "Irodori Starter 120",
      sourceUrl: prompt.sourceUrl || "",
      sourceVersion: prompt.sourceVersion || "1",
      license: prompt.license || "Irodori Studio project corpus",
    },
  };
  const saved = await api.saveDatasetRecording(datasetId, prompt.id, blob, metadata);
  return {
    ...saved,
    id: prompt.id,
    blob,
    audioUrl: datasetRecordingUrl(datasetId, prompt.id),
  };
}

export function deleteRecordingDataset(datasetId) {
  return api.deleteRecordingDataset(datasetId);
}
