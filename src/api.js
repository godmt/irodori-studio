async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body instanceof FormData || options.body instanceof Blob ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(message);
  }
  return response;
}

function encodeJsonHeader(payload) {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  let binary = "";
  for (let index = 0; index < bytes.length; index += 0x4000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x4000));
  }
  return btoa(binary);
}

export const api = {
  bootstrap: () => request("/api/bootstrap").then((response) => response.json()),
  refreshAssets: () => request("/api/assets/refresh", { method: "POST" }).then((response) => response.json()),
  voiceProfiles: () => request("/api/voice-profiles").then((response) => response.json()),
  saveVoiceProfile: (payload) => request("/api/voice-profiles", { method: "POST", body: JSON.stringify(payload) }).then((response) => response.json()),
  deleteVoiceProfile: (id) => request(`/api/voice-profiles/${encodeURIComponent(id)}`, { method: "DELETE" }).then((response) => response.json()),
  modelStatus: () => request("/api/model/status").then((response) => response.json()),
  loadModel: (payload) => request("/api/model/load", { method: "POST", body: JSON.stringify(payload) }).then((response) => response.json()),
  unloadModel: () => request("/api/model/unload", { method: "POST" }).then((response) => response.json()),
  synthesize: (payload) => request("/api/synthesis", { method: "POST", body: JSON.stringify(payload) }).then((response) => response.json()),
  job: (id) => request(`/api/jobs/${id}`).then((response) => response.json()),
  jobs: () => request("/api/jobs").then((response) => response.json()),
  cancelJob: (id) => request(`/api/jobs/${id}/cancel`, { method: "POST" }).then((response) => response.json()),
  cancelAll: () => request("/api/jobs/cancel-all", { method: "POST" }).then((response) => response.json()),
  releaseAudio: (audioFiles, projectName = null) => request("/api/audio/release", {
    method: "POST",
    body: JSON.stringify({ audio_files: audioFiles, project_name: projectName }),
  }).then((response) => response.json()),
  createProject: (name, project) => request("/api/projects/create", { method: "POST", body: JSON.stringify({ name, project }) }).then((response) => response.json()),
  saveProject: (name, project) => request("/api/projects/save", { method: "POST", body: JSON.stringify({ name, project }) }).then((response) => response.json()),
  renameProject: (name, nextName) => request(`/api/projects/${encodeURIComponent(name)}/rename`, { method: "POST", body: JSON.stringify({ name: nextName }) }).then((response) => response.json()),
  projects: () => request("/api/projects").then((response) => response.json()),
  loadProject: (name) => request(`/api/projects/${encodeURIComponent(name)}`).then((response) => response.json()),
  deleteProject: (name) => request(`/api/projects/${encodeURIComponent(name)}`, { method: "DELETE" }).then((response) => response.json()),
  recordingDatasets: () => request("/api/recording-datasets").then((response) => response.json()),
  createRecordingDataset: (name) => request("/api/recording-datasets", { method: "POST", body: JSON.stringify({ name }) }).then((response) => response.json()),
  recordingDataset: (id) => request(`/api/recording-datasets/${encodeURIComponent(id)}`).then((response) => response.json()),
  renameRecordingDataset: (id, name) => request(`/api/recording-datasets/${encodeURIComponent(id)}/rename`, { method: "POST", body: JSON.stringify({ name }) }).then((response) => response.json()),
  saveDatasetRecording: (datasetId, promptId, blob, metadata) => request(`/api/recording-datasets/${encodeURIComponent(datasetId)}/recordings/${encodeURIComponent(promptId)}`, {
    method: "POST",
    body: blob,
    headers: {
      "Content-Type": "audio/wav",
      "X-Irodori-Recording-Metadata": encodeJsonHeader(metadata),
    },
  }).then((response) => response.json()),
  reviewDatasetRecording: (datasetId, promptId, payload) => request(`/api/recording-datasets/${encodeURIComponent(datasetId)}/recordings/${encodeURIComponent(promptId)}/review`, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((response) => response.json()),
  deleteRecordingDataset: (id) => request(`/api/recording-datasets/${encodeURIComponent(id)}`, { method: "DELETE" }).then((response) => response.json()),
  audioImportJobs: () => request("/api/audio-import-jobs").then((response) => response.json()),
  createAudioImportJob: (payload) => request("/api/audio-import-jobs", { method: "POST", body: JSON.stringify(payload) }).then((response) => response.json()),
  audioImportJob: (id) => request(`/api/audio-import-jobs/${encodeURIComponent(id)}`).then((response) => response.json()),
  cancelAudioImportJob: (id) => request(`/api/audio-import-jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }).then((response) => response.json()),
  resumeAudioImportJob: (id) => request(`/api/audio-import-jobs/${encodeURIComponent(id)}/resume`, { method: "POST" }).then((response) => response.json()),
  deleteAudioImportJob: (id) => request(`/api/audio-import-jobs/${encodeURIComponent(id)}`, { method: "DELETE" }).then((response) => response.json()),
  trainingJobs: () => request("/api/training-jobs").then((response) => response.json()),
  trainedModels: () => request("/api/trained-models").then((response) => response.json()),
  renameTrainedModel: (id, name) => request(`/api/trained-models/${encodeURIComponent(id)}/rename`, { method: "POST", body: JSON.stringify({ name }) }).then((response) => response.json()),
  deleteTrainedModel: (id) => request(`/api/trained-models/${encodeURIComponent(id)}`, { method: "DELETE" }).then((response) => response.json()),
  createTrainingJob: (payload) => request("/api/training-jobs", { method: "POST", body: JSON.stringify(payload) }).then((response) => response.json()),
  trainingJob: (id) => request(`/api/training-jobs/${encodeURIComponent(id)}`).then((response) => response.json()),
  cancelTrainingJob: (id) => request(`/api/training-jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }).then((response) => response.json()),
  resumeTrainingJob: (id, overwriteExisting = false) => request(`/api/training-jobs/${encodeURIComponent(id)}/resume`, {
    method: "POST",
    body: JSON.stringify({ overwrite_existing: overwriteExisting }),
  }).then((response) => response.json()),
  deleteTrainingJob: (id) => request(`/api/training-jobs/${encodeURIComponent(id)}`, { method: "DELETE" }).then((response) => response.json()),
  dialog: (kind, multiple = false) => request("/api/dialog", { method: "POST", body: JSON.stringify({ kind, multiple }) }).then((response) => response.json()),
  exportProject: async (payload) => {
    const response = await request("/api/export", { method: "POST", body: JSON.stringify(payload) });
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/i);
    return { blob: await response.blob(), filename: match?.[1] || "irodori-production.zip" };
  },
};

export const audioUrl = (audioFile) => `/api/audio/${encodeURIComponent(audioFile)}`;
export const datasetRecordingUrl = (datasetId, promptId) => `/api/recording-datasets/${encodeURIComponent(datasetId)}/audio/${encodeURIComponent(promptId)}`;
