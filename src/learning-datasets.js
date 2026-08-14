export const LEARNING_DATASET_STORAGE_KEY = "irodori-studio-recorder-dataset-v1";

export function resolveLearningDatasetId(datasets, selectedId = "") {
  if (selectedId && datasets.some((dataset) => dataset.id === selectedId)) return selectedId;
  return datasets[0]?.id || "";
}
