import { createLine, createTake } from "./defaults.js";

export const MAX_LINE_TAKES = 4;

export function audioFilesForLine(line) {
  return [...new Set([
    line?.audioFile,
    ...(line?.takes || []).map((take) => take?.audioFile),
  ].filter(Boolean))];
}

export function audioFilesForProject(project) {
  return [...new Set((project?.lines || []).flatMap(audioFilesForLine))];
}

export function removedAudioFiles(previousLine, nextLine) {
  const retained = new Set(audioFilesForLine(nextLine));
  return audioFilesForLine(previousLine).filter((audioFile) => !retained.has(audioFile));
}

function projectSelectedTake(line, take) {
  return {
    ...line,
    selectedTakeId: take?.id || null,
    audioFile: take?.audioFile || null,
    duration: take?.duration ?? null,
    generationSeconds: take?.generationSeconds ?? null,
    usedSeed: take?.usedSeed ?? null,
    stale: take ? Boolean(take.stale) : false,
  };
}

export function updateLine(lines, id, patch, invalidate = true) {
  return lines.map((line) => {
    if (line.id !== id) return line;
    const takes = invalidate
      ? (line.takes || []).map((take) => ({ ...take, stale: true }))
      : (patch.takes ?? line.takes ?? []);
    return {
      ...line,
      ...patch,
      takes,
      stale: invalidate && Boolean(line.audioFile) ? true : (patch.stale ?? line.stale),
      error: invalidate ? null : (patch.error ?? line.error),
    };
  });
}

export function appendLineTake(lines, id, takeFields, maxTakes = MAX_LINE_TAKES) {
  return lines.map((line) => {
    if (line.id !== id) return line;
    const previousSelectedId = line.selectedTakeId;
    const nextTake = createTake(takeFields);
    const takes = [...(line.takes || []), nextTake];
    while (takes.length > maxTakes) {
      let removalIndex = takes.findIndex((take) => (
        take.id !== previousSelectedId && take.id !== nextTake.id
      ));
      if (removalIndex < 0) removalIndex = takes.findIndex((take) => take.id !== nextTake.id);
      takes.splice(Math.max(0, removalIndex), 1);
    }
    return projectSelectedTake({
      ...line,
      takes,
      status: "ready",
      jobId: takeFields.jobId ?? line.jobId,
      error: null,
    }, nextTake);
  });
}

export function selectLineTake(lines, lineId, takeId) {
  return lines.map((line) => {
    if (line.id !== lineId) return line;
    const take = (line.takes || []).find((entry) => entry.id === takeId);
    return take ? projectSelectedTake({ ...line, status: "ready", error: null }, take) : line;
  });
}

export function duplicateLine(lines, id) {
  const index = lines.findIndex((line) => line.id === id);
  if (index < 0) return lines;
  const source = lines[index];
  const { id: _sourceId, ...sourceFields } = source;
  const copy = createLine({
    ...sourceFields,
    text: source.text,
    audioFile: null,
    takes: [],
    selectedTakeId: null,
    duration: null,
    generationSeconds: null,
    usedSeed: null,
    jobId: null,
    status: "idle",
    stale: false,
  });
  return [...lines.slice(0, index + 1), copy, ...lines.slice(index + 1)];
}

export function estimatedProjectSeconds(lines) {
  return lines.reduce((total, line) => total + (Number(line.duration) || 0), 0);
}

export function splitImportedText(raw, lineDefaults = {}) {
  return raw
    .split(/\r?\n+/)
    .map((text) => text.trim())
    .filter(Boolean)
    .map((text) => createLine({ ...lineDefaults, text }));
}
