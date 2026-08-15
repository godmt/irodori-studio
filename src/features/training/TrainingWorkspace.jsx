import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowCounterClockwise,
  Brain,
  CaretRight,
  Check,
  CheckCircle,
  ClockCounterClockwise,
  Cpu,
  Database,
  FileAudio,
  FolderOpen,
  HardDrive,
  Info,
  Lightning,
  MagnifyingGlass,
  MagicWand,
  MicrophoneStage,
  PencilSimple,
  Play,
  Plus,
  SpinnerGap,
  Stop,
  Trash,
  WarningCircle,
  Waveform,
  XCircle,
} from "@phosphor-icons/react";

import { api, datasetRecordingUrl } from "../../api.js";
import {
  ConfirmDialog,
  IconButton,
  Modal,
  NameDialog,
} from "../../components/StudioUI.jsx";
import { getTrainingVramWarning } from "./training-requirements.js";
import "./training.css";

const ACTIVE_TRAINING_STATUSES = new Set(["queued", "preparing", "training", "cancelling"]);
const ACTIVE_IMPORT_STATUSES = new Set(["queued", "loading_model", "transcribing", "committing", "cancelling"]);
const RESUMABLE_IMPORT_STATUSES = new Set(["cancelled", "failed", "interrupted"]);
const RESUMABLE_TRAINING_STATUSES = new Set(["cancelled", "failed", "interrupted"]);
const DEFAULT_TRAINING_STEPS = {
  speaker_inversion: 500,
  lora: 1500,
};

function formatDuration(seconds) {
  const value = Math.round(Math.max(0, Number(seconds) || 0));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor(value / 60);
  const remainder = value % 60;
  if (hours > 0) return `${hours}時間${String(minutes % 60).padStart(2, "0")}分`;
  return `${minutes}分${String(remainder).padStart(2, "0")}秒`;
}

function formatTrainingEstimate(timing) {
  if (!timing) return { remaining: "計算中", total: "計算中" };
  return {
    remaining: formatDuration(timing.estimated_remaining_seconds),
    total: formatDuration(timing.estimated_total_seconds),
  };
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function fileName(path) {
  return String(path || "").split(/[\\/]/).filter(Boolean).pop() || "音声ファイル";
}

function trainingStatusLabel(status) {
  return {
    queued: "開始待ち",
    preparing: "データ調整中",
    training: "学習中",
    cancelling: "停止中",
    cancelled: "停止済み",
    completed: "完了",
    failed: "失敗",
    interrupted: "中断",
  }[status] || status;
}

function importStatusLabel(status) {
  return {
    queued: "開始待ち",
    loading_model: "文字起こしを準備中",
    transcribing: "分割・文字起こし中",
    committing: "学習用WAVを保存中",
    cancelling: "停止中",
    cancelled: "停止済み",
    completed: "前処理完了",
    failed: "前処理失敗",
    interrupted: "前処理中断",
  }[status] || status;
}

function methodLabel(method) {
  return method === "lora" ? "LoRA" : "Speaker Inversion";
}

function failureForJob(job) {
  return job?.failure || {
    title: "学習処理を完了できませんでした",
    summary: job?.message || "予期しない理由で学習処理が停止しました。",
    action: "学習設定を確認してから再開してください。",
    details: "",
  };
}

function reviewKind(recording) {
  if (recording?.accepted) return "accepted";
  if (recording?.reviewState === "excluded") return "excluded";
  return "needs_review";
}

function reviewLabel(recording) {
  return {
    accepted: "採用",
    excluded: "除外",
    needs_review: "確認待ち",
  }[reviewKind(recording)];
}

function MethodCard({ active, icon, title, badge, description, details, onClick }) {
  return (
    <button
      type="button"
      className={`training-method-card ${active ? "active" : ""}`}
      onClick={onClick}
    >
      <span className="training-method-icon">{icon}</span>
      <span className="training-method-copy">
        <span><strong>{title}</strong>{badge && <small>{badge}</small>}</span>
        <p>{description}</p>
        <em>{details}</em>
      </span>
      <span className="training-radio" aria-hidden="true" />
    </button>
  );
}

function DatasetReviewModal({
  dataset,
  notify,
  onClose,
  onRecordingUpdated,
  playbackVolume,
  outputDeviceId,
}) {
  const recordings = useMemo(
    () => Object.values(dataset?.recordings || {}).sort((left, right) => (
      Number(right?.accepted) - Number(left?.accepted)
      || String(left?.prompt_id).localeCompare(String(right?.prompt_id), "ja-JP")
    )),
    [dataset],
  );
  const counts = useMemo(() => recordings.reduce((result, recording) => {
    result[reviewKind(recording)] += 1;
    return result;
  }, { accepted: 0, needs_review: 0, excluded: 0 }), [recordings]);
  const [filter, setFilter] = useState(() => (counts.needs_review ? "needs_review" : "accepted"));
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const audioRef = useRef(null);
  const filtered = useMemo(() => recordings.filter((recording) => {
    if (filter !== "all" && reviewKind(recording) !== filter) return false;
    const normalized = query.trim().toLocaleLowerCase("ja-JP");
    if (!normalized) return true;
    return String(recording?.prompt?.text || "").toLocaleLowerCase("ja-JP").includes(normalized)
      || String(recording?.prompt?.sourceName || "").toLocaleLowerCase("ja-JP").includes(normalized);
  }), [filter, query, recordings]);
  const selected = recordings.find((recording) => recording.prompt_id === selectedId)
    || filtered[0]
    || recordings[0]
    || null;

  useEffect(() => {
    if (!selected) return;
    setSelectedId(selected.prompt_id);
    setText(String(selected.prompt?.text || ""));
  }, [selected?.prompt_id]);

  useEffect(() => () => {
    audioRef.current?.pause();
  }, []);

  const playSelected = async () => {
    if (!selected) return;
    audioRef.current?.pause();
    const audio = new Audio(datasetRecordingUrl(dataset.id, selected.prompt_id));
    audio.volume = Math.max(0, Math.min(1, Number(playbackVolume || 0) / 100));
    if (typeof audio.setSinkId === "function") {
      await audio.setSinkId(outputDeviceId || "").catch(() => {});
    }
    audioRef.current = audio;
    await audio.play().catch((error) => notify(error.message, "error"));
  };

  const updateReview = async (accepted) => {
    if (!selected || busy) return;
    if (accepted && !text.trim()) {
      notify("採用する音声には文字起こしが必要です", "error");
      return;
    }
    setBusy(true);
    try {
      const updated = await api.reviewDatasetRecording(dataset.id, selected.prompt_id, {
        text: text.trim(),
        accepted,
      });
      onRecordingUpdated(updated);
      setText(String(updated.prompt?.text || ""));
      notify(accepted ? "学習に使う音声として採用しました" : "学習対象から除外しました", "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const saveText = async () => {
    if (!selected || busy) return;
    setBusy(true);
    try {
      const updated = await api.reviewDatasetRecording(dataset.id, selected.prompt_id, {
        text: text.trim(),
      });
      onRecordingUpdated(updated);
      setText(String(updated.prompt?.text || ""));
      notify("文字起こしを修正しました", "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`${dataset.name}の内容を確認`}
      eyebrow="OPTIONAL REVIEW"
      onClose={onClose}
      wide
      scrollable
    >
      <div className="training-review-intro">
        <CheckCircle size={22} weight="fill" />
        <div>
          <strong>自動採用のまま学習できます</strong>
          <span>気になる音声だけ再生し、文字修正・採用・除外を行ってください。全件確認は不要です。</span>
        </div>
      </div>
      <div className="training-review-toolbar">
        <div className="training-review-filters" role="tablist" aria-label="音声の状態で絞り込み">
          {[
            ["all", "すべて", recordings.length],
            ["needs_review", "確認待ち", counts.needs_review],
            ["accepted", "採用", counts.accepted],
            ["excluded", "除外", counts.excluded],
          ].map(([value, label, count]) => (
            <button
              key={value}
              type="button"
              className={filter === value ? "active" : ""}
              onClick={() => setFilter(value)}
            >
              {label}<span>{count}</span>
            </button>
          ))}
        </div>
        <label className="training-review-search">
          <MagnifyingGlass size={18} />
          <input
            value={query}
            placeholder="文章を検索"
            aria-label="文字起こしを検索"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>
      <div className="training-review-layout">
        <div className="training-review-list">
          {filtered.map((recording) => (
            <button
              key={recording.prompt_id}
              type="button"
              className={selected?.prompt_id === recording.prompt_id ? "active" : ""}
              onClick={() => {
                setSelectedId(recording.prompt_id);
                setText(String(recording.prompt?.text || ""));
              }}
            >
              <span className={`training-review-state ${reviewKind(recording)}`}>
                {recording.accepted ? <Check size={15} weight="bold" /> : <WarningCircle size={15} />}
              </span>
              <span>
                <strong>{recording.prompt?.text || "文字起こしなし"}</strong>
                <small>{recording.prompt?.sourceName || "Studio録音"} · {Number(recording.duration || 0).toFixed(1)}秒</small>
              </span>
              <em>{reviewLabel(recording)}</em>
            </button>
          ))}
          {!filtered.length && <p className="training-review-empty">該当する音声はありません。</p>}
        </div>
        {selected && <section className="training-review-editor">
          <header>
            <div>
              <small>{selected.prompt?.sourceName || "Studio録音"}</small>
              <strong>{reviewLabel(selected)}</strong>
            </div>
            <button type="button" className="secondary-button" onClick={playSelected}>
              <Play size={18} weight="fill" />再生
            </button>
          </header>
          <label>
            <span>文字起こし <small>修正は任意</small></span>
            <textarea value={text} rows={6} onChange={(event) => setText(event.target.value)} />
          </label>
          <dl>
            <div><dt>長さ</dt><dd>{Number(selected.duration || 0).toFixed(2)}秒</dd></div>
            <div><dt>音量</dt><dd>{Number(selected.import?.rmsDbfs ?? -120).toFixed(1)} dBFS</dd></div>
            <div><dt>判定</dt><dd>{reviewLabel(selected)}</dd></div>
          </dl>
          <div className="training-review-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={busy || text.trim() === String(selected.prompt?.text || "").trim()}
              onClick={saveText}
            >
              文字を保存
            </button>
            <button type="button" className="danger-button" disabled={busy} onClick={() => updateReview(false)}>
              除外
            </button>
            <button type="button" className="primary-button" disabled={busy || !text.trim()} onClick={() => updateReview(true)}>
              採用
            </button>
          </div>
        </section>}
      </div>
    </Modal>
  );
}

export function TrainingWorkspace({
  bootstrap,
  notify,
  onModelUnloaded,
  onOpenRecorder,
  datasetId = "",
  onDatasetIdChange = () => {},
  playbackVolume = 80,
  outputDeviceId = "",
}) {
  const [datasets, setDatasets] = useState(() => bootstrap?.recording_datasets || []);
  const [datasetDetail, setDatasetDetail] = useState(null);
  const [importJobs, setImportJobs] = useState(() => bootstrap?.audio_import_jobs || []);
  const [jobs, setJobs] = useState(() => bootstrap?.training_jobs || []);
  const [trainedModels, setTrainedModels] = useState(() => bootstrap?.trained_models || []);
  const [name, setName] = useState("");
  const [method, setMethod] = useState("speaker_inversion");
  const [checkpoint, setCheckpoint] = useState(() => bootstrap?.default_checkpoint || "");
  const [device, setDevice] = useState(() => bootstrap?.default_device || "cuda");
  const [precision, setPrecision] = useState("bf16");
  const [maxSteps, setMaxSteps] = useState(DEFAULT_TRAINING_STEPS.speaker_inversion);
  const [sourcePaths, setSourcePaths] = useState([]);
  const [overwriteImport, setOverwriteImport] = useState(false);
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [showReview, setShowReview] = useState(false);
  const [showCreateDataset, setShowCreateDataset] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState("新しい学習データセット");
  const [renameDatasetTarget, setRenameDatasetTarget] = useState(null);
  const [renameDatasetName, setRenameDatasetName] = useState("");
  const [deleteDatasetTarget, setDeleteDatasetTarget] = useState(null);
  const [renameModelTarget, setRenameModelTarget] = useState(null);
  const [renameModelName, setRenameModelName] = useState("");
  const [deleteModelTarget, setDeleteModelTarget] = useState(null);
  const [deleteJobTarget, setDeleteJobTarget] = useState(null);
  const [restartJobTarget, setRestartJobTarget] = useState(null);
  const [failureJob, setFailureJob] = useState(null);
  const [showImportHistory, setShowImportHistory] = useState(false);
  const [deleteImportJobTarget, setDeleteImportJobTarget] = useState(null);
  const [trainingVramWarning, setTrainingVramWarning] = useState(null);

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === datasetId) || null,
    [datasetId, datasets],
  );
  const activeJob = useMemo(
    () => jobs.find((job) => ACTIVE_TRAINING_STATUSES.has(job.status)),
    [jobs],
  );
  const activeImportJob = useMemo(
    () => importJobs.find((job) => ACTIVE_IMPORT_STATUSES.has(job.status)),
    [importJobs],
  );
  const selectedDatasetImport = useMemo(
    () => importJobs.find((job) => job.dataset_id === datasetId) || null,
    [datasetId, importJobs],
  );
  const selectedDatasetImports = useMemo(
    () => importJobs.filter((job) => job.dataset_id === datasetId),
    [datasetId, importJobs],
  );
  const recordings = useMemo(
    () => Object.values(datasetDetail?.recordings || {}),
    [datasetDetail],
  );
  const reviewCount = useMemo(
    () => recordings.filter((recording) => reviewKind(recording) === "needs_review").length,
    [recordings],
  );
  const importedCount = useMemo(
    () => recordings.filter((recording) => recording.import || recording.prompt?.category === "imported_audio").length,
    [recordings],
  );
  const corpusCount = Math.max(0, recordings.length - importedCount);

  const loadDatasetDetail = useCallback(async (id, { quiet = false } = {}) => {
    if (!id) {
      setDatasetDetail(null);
      return;
    }
    try {
      setDatasetDetail(await api.recordingDataset(id));
    } catch (error) {
      if (!quiet) notify(error.message, "error");
    }
  }, [notify]);

  const showTrainingFailure = async (job) => {
    setFailureJob(job);
    try {
      setFailureJob(await api.trainingJob(job.id));
    } catch (error) {
      notify(error.message, "error");
    }
  };

  const refresh = useCallback(async ({ quiet = false } = {}) => {
    try {
      const [nextDatasets, nextImports, nextJobs, nextModels] = await Promise.all([
        api.recordingDatasets(),
        api.audioImportJobs(),
        api.trainingJobs(),
        api.trainedModels(),
      ]);
      setDatasets(nextDatasets);
      setImportJobs(nextImports);
      setJobs(nextJobs);
      setTrainedModels(nextModels);
      onDatasetIdChange((current) => (
        nextDatasets.some((dataset) => dataset.id === current) ? current : nextDatasets[0]?.id || ""
      ));
    } catch (error) {
      if (!quiet) notify(error.message, "error");
    }
  }, [notify, onDatasetIdChange]);

  useEffect(() => {
    refresh({ quiet: true });
  }, [refresh]);

  useEffect(() => {
    loadDatasetDetail(datasetId, { quiet: true });
  }, [datasetId, loadDatasetDetail, selectedDatasetImport?.status]);

  useEffect(() => {
    if (!checkpoint && bootstrap?.default_checkpoint) setCheckpoint(bootstrap.default_checkpoint);
  }, [bootstrap?.default_checkpoint, checkpoint]);

  useEffect(() => {
    if (!activeJob && !activeImportJob) return undefined;
    const timer = window.setInterval(() => refresh({ quiet: true }), 1500);
    return () => window.clearInterval(timer);
  }, [activeImportJob, activeJob, refresh]);

  useEffect(() => {
    setMaxSteps(DEFAULT_TRAINING_STEPS[method]);
  }, [method]);

  useEffect(() => {
    const available = bootstrap?.precisions?.[device] || ["fp32"];
    if (!available.includes(precision)) setPrecision(available[0]);
  }, [bootstrap?.precisions, device, precision]);

  const createDataset = async () => {
    const normalized = newDatasetName.trim();
    if (!normalized || busy) return;
    setBusy(true);
    try {
      const created = await api.createRecordingDataset(normalized);
      await refresh();
      onDatasetIdChange(created.id);
      setShowCreateDataset(false);
      setNewDatasetName(`新しい学習データセット ${datasets.length + 2}`);
      notify(`「${created.name}」を作成しました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const renameDataset = async () => {
    if (!renameDatasetTarget || !renameDatasetName.trim() || busy) return;
    setBusy(true);
    try {
      const renamed = await api.renameRecordingDataset(renameDatasetTarget.id, renameDatasetName.trim());
      await refresh();
      setRenameDatasetTarget(null);
      notify(`「${renamed.name}」へ変更しました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const deleteDataset = async () => {
    if (!deleteDatasetTarget || busy) return;
    setBusy(true);
    try {
      await api.deleteRecordingDataset(deleteDatasetTarget.id);
      setDeleteDatasetTarget(null);
      setDatasetDetail(null);
      await refresh();
      notify(`「${deleteDatasetTarget.name}」を削除しました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const chooseSourceFiles = async () => {
    try {
      const { paths } = await api.dialog("reference", true);
      if (!paths?.length) return;
      setSourcePaths(Array.from(new Set(paths)).slice(0, 64));
    } catch (error) {
      notify(error.message, "error");
    }
  };

  const startImport = async () => {
    if (!selectedDataset || !sourcePaths.length || busy) return;
    setBusy(true);
    try {
      const created = await api.createAudioImportJob({
        dataset_id: selectedDataset.id,
        sources: sourcePaths.map((path) => ({ path })),
        overwrite_existing: overwriteImport,
      });
      setImportJobs((current) => [created, ...current]);
      setSourcePaths([]);
      setOverwriteImport(false);
      onModelUnloaded?.();
      notify("音声の前処理を開始しました", "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const cancelImport = async (job) => {
    try {
      const updated = await api.cancelAudioImportJob(job.id);
      setImportJobs((current) => current.map((item) => item.id === updated.id ? updated : item));
      notify("音声前処理の停止を受け付けました");
    } catch (error) {
      notify(error.message, "error");
    }
  };

  const resumeImport = async (job) => {
    if (!job || busy) return;
    setBusy(true);
    try {
      const updated = await api.resumeAudioImportJob(job.id);
      setImportJobs((current) => current.map((item) => item.id === updated.id ? updated : item));
      onModelUnloaded?.();
      notify("保存済みの処理結果から音声前処理を再開しました", "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const deleteImportJob = async (job) => {
    if (!job || busy) return;
    setBusy(true);
    try {
      await api.deleteAudioImportJob(job.id);
      setImportJobs((current) => current.filter((item) => item.id !== job.id));
      setDeleteImportJobTarget(null);
      notify("音声前処理の履歴を削除しました", "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const createTrainingJob = async () => {
    setTrainingVramWarning(null);
    setBusy(true);
    try {
      const created = await api.createTrainingJob({
        name: name.trim(),
        dataset_id: selectedDataset.id,
        method,
        checkpoint,
        device,
        precision,
        max_steps: Number(maxSteps),
      });
      setJobs((current) => [created, ...current]);
      onModelUnloaded?.();
      notify(`${name.trim()}の学習を開始しました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const startTraining = () => {
    if (!name.trim()) {
      notify("モデル名を入力してください", "error");
      return;
    }
    if (!selectedDataset) {
      notify("学習データセットを選択してください", "error");
      return;
    }
    if (!selectedDataset.accepted) {
      notify("採用済みの音声がありません", "error");
      return;
    }

    const warning = getTrainingVramWarning({
      method,
      device,
      precision,
      totalVramGb: bootstrap?.model?.cuda?.total_gb,
      recommendedVramGb: bootstrap?.training_requirements?.recommended_vram_gb,
    });
    if (warning) {
      setTrainingVramWarning(warning);
      return;
    }

    void createTrainingJob();
  };

  const stopTraining = async (job) => {
    try {
      const updated = await api.cancelTrainingJob(job.id);
      setJobs((current) => current.map((item) => item.id === updated.id ? updated : item));
      notify("学習の停止を受け付けました");
    } catch (error) {
      notify(error.message, "error");
    }
  };

  const resumeTraining = async (job, overwriteExisting = false) => {
    if (!job || busy) return;
    setBusy(true);
    try {
      const updated = await api.resumeTrainingJob(job.id, overwriteExisting);
      setJobs((current) => current.map((item) => item.id === updated.id ? updated : item));
      setRestartJobTarget(null);
      onModelUnloaded?.();
      notify(overwriteExisting ? "学習を最初からやり直します" : "学習を再開しました", "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const deleteJob = async (job) => {
    if (busy) return;
    setBusy(true);
    try {
      await api.deleteTrainingJob(job.id);
      setJobs((current) => current.filter((item) => item.id !== job.id));
      setDeleteJobTarget(null);
      notify("学習履歴を削除しました", "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const renameModel = async () => {
    const nextName = renameModelName.trim();
    if (!renameModelTarget || !nextName || busy) return;
    setBusy(true);
    try {
      const renamed = await api.renameTrainedModel(renameModelTarget.id, nextName);
      setTrainedModels((current) => current.map((model) => model.id === renamed.id ? renamed : model));
      setRenameModelTarget(null);
      notify(`学習済みモデル名を「${renamed.name}」へ変更しました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const deleteModel = async (model) => {
    if (!model || busy) return;
    setBusy(true);
    try {
      await api.deleteTrainedModel(model.id);
      setTrainedModels((current) => current.filter((item) => item.id !== model.id));
      setDeleteModelTarget(null);
      notify(`「${model.name}」を削除しました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const updateDetailRecording = (recording) => {
    setDatasetDetail((current) => current ? {
      ...current,
      recordings: { ...current.recordings, [recording.prompt_id]: recording },
    } : current);
    refresh({ quiet: true });
  };

  const importProgress = Math.max(0, Math.min(100, Number(activeImportJob?.percent || 0)));
  const trainingBlocked = busy
    || Boolean(activeJob)
    || Boolean(activeImportJob)
    || !selectedDataset?.accepted
    || !name.trim();

  return (
    <>
      <main className="training-workspace">
        <section className="training-main">
          <header className="training-header">
            <div>
              <span className="eyebrow">VOICE TRAINING</span>
              <h1>学習スタジオ</h1>
              <p>録音や手持ち音声から学習データを整え、名前付きのボイスモデルを作ります。</p>
            </div>
            <span className="training-local-badge">
              <HardDrive size={19} />
              <span><small>LOCAL TRAINING</small><strong>すべてこのPCに保存</strong></span>
            </span>
          </header>

          <div className="training-scroll">
            <section className="training-setup-card training-data-card">
              <div className="training-section-title">
                <span>1</span>
                <div>
                  <h2>学習データを用意する</h2>
                  <p>収録した音声と手持ちの音声は、同じ学習データセットへまとめられます。</p>
                </div>
              </div>
              {datasets.length ? <>
                <div className="training-dataset-row">
                  <label className="training-dataset-select">
                    <Database size={23} />
                    <span>
                      <small>学習データセット</small>
                      <select value={datasetId} onChange={(event) => onDatasetIdChange(event.target.value)}>
                        {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}
                      </select>
                    </span>
                  </label>
                  <span className="training-dataset-actions">
                    <IconButton label="学習データセットを作成" onClick={() => setShowCreateDataset(true)}><Plus size={19} /></IconButton>
                    <IconButton
                      label="学習データセット名を変更"
                      disabled={!selectedDataset}
                      onClick={() => {
                        setRenameDatasetTarget(selectedDataset);
                        setRenameDatasetName(selectedDataset?.name || "");
                      }}
                    ><PencilSimple size={18} /></IconButton>
                    <IconButton label="学習データセットを削除" tone="danger" disabled={!selectedDataset} onClick={() => setDeleteDatasetTarget(selectedDataset)}><Trash size={18} /></IconButton>
                  </span>
                </div>
                {selectedDataset && <>
                  <div className="training-dataset-summary">
                    <div><strong>{selectedDataset.accepted}</strong><span>学習に使用</span></div>
                    <div><strong>{formatDuration(selectedDataset.accepted_seconds)}</strong><span>学習時間</span></div>
                    <div><strong>{selectedDataset.recorded}</strong><span>全音声</span></div>
                    <p>
                      {reviewCount > 0
                        ? `${reviewCount}件は必要な場合だけ確認できます。確認せず学習しても構いません。`
                        : "採用済み音声はそのまま学習に使えます。元音声は変更しません。"}
                    </p>
                  </div>
                  <div className="training-dataset-origin">
                    <span><MicrophoneStage size={16} />コーパス録音 {corpusCount}件</span>
                    <span><FileAudio size={16} />音声ファイル {importedCount}件</span>
                    <span className="training-dataset-tools">
                      {recordings.length > 0 && <button className="training-review-open" type="button" onClick={() => setShowReview(true)}>
                        内容を確認{reviewCount > 0 && <em>{reviewCount}</em>}
                      </button>}
                      <IconButton
                        label={`${selectedDataset.name}の音声前処理履歴を管理`}
                        onClick={() => setShowImportHistory(true)}
                      ><ClockCounterClockwise size={18} /></IconButton>
                    </span>
                  </div>
                </>}

                <div className="training-source-choices" aria-label="学習音声の追加方法">
                  <button type="button" onClick={onOpenRecorder}>
                    <span className="training-source-icon"><MicrophoneStage size={24} /></span>
                    <span><strong>コーパスを録音</strong><small>用意された文章を順番に収録</small></span>
                    <CaretRight size={18} />
                  </button>
                  <button type="button" onClick={chooseSourceFiles} disabled={Boolean(activeImportJob)}>
                    <span className="training-source-icon"><FileAudio size={24} /></span>
                    <span><strong>音声ファイルを使う</strong><small>複数のWAV・FLAC・MP3などを前処理</small></span>
                    <CaretRight size={18} />
                  </button>
                </div>

                {sourcePaths.length > 0 && !activeImportJob && <div className="training-import-ready">
                  <header>
                    <div><FileAudio size={21} /><span><strong>{sourcePaths.length}ファイルを選択</strong><small>分割・文字起こし・品質判定を自動で行います</small></span></div>
                    <IconButton label="選択を解除" onClick={() => setSourcePaths([])}><XCircle size={19} /></IconButton>
                  </header>
                  <ul>{sourcePaths.slice(0, 4).map((path) => <li key={path}>{fileName(path)}</li>)}</ul>
                  {sourcePaths.length > 4 && <p>ほか {sourcePaths.length - 4}ファイル</p>}
                  <label className="training-overwrite-option">
                    <input type="checkbox" checked={overwriteImport} onChange={(event) => setOverwriteImport(event.target.checked)} />
                    <span><strong>同じ素材を最初からやり直す</strong><small>通常は処理済み区間をスキップします</small></span>
                  </label>
                  <button className="primary-button" type="button" disabled={busy} onClick={startImport}>
                    <MagicWand size={19} />前処理を開始
                  </button>
                </div>}

                {activeImportJob && <div className="training-import-progress" role="status">
                  <header>
                    <span className="training-job-spinner"><SpinnerGap className="spin" size={21} /></span>
                    <div>
                      <small>{importStatusLabel(activeImportJob.status)}</small>
                      <strong>{datasets.find((dataset) => dataset.id === activeImportJob.dataset_id)?.name || "学習データセット"}</strong>
                    </div>
                    <IconButton label="音声の前処理を停止" tone="danger" disabled={activeImportJob.status === "cancelling"} onClick={() => cancelImport(activeImportJob)}><Stop size={18} weight="fill" /></IconButton>
                  </header>
                  <div className="training-progress"><span style={{ width: `${importProgress}%` }} /></div>
                  <div className="training-progress-meta"><span>{activeImportJob.candidate_count || 0}件を抽出</span><strong>{importProgress.toFixed(0)}%</strong></div>
                  <p>{activeImportJob.message}</p>
                </div>}

                {!activeImportJob && selectedDatasetImport?.status === "completed" && <div className="training-import-result">
                  <CheckCircle size={20} weight="fill" />
                  <div>
                    <strong>前処理が完了しています</strong>
                    <span>{selectedDatasetImport.committed?.imported || 0}件追加 · {selectedDatasetImport.committed?.skipped || 0}件スキップ</span>
                  </div>
                </div>}

                {!activeImportJob && RESUMABLE_IMPORT_STATUSES.has(selectedDatasetImport?.status) && <div className="training-import-result problem">
                  <WarningCircle size={21} weight="fill" />
                  <div>
                    <strong>{importStatusLabel(selectedDatasetImport.status)}</strong>
                    <span>{selectedDatasetImport.failure?.summary || selectedDatasetImport.message}</span>
                  </div>
                  <button
                    type="button"
                    disabled={Boolean(activeJob || busy)}
                    onClick={() => resumeImport(selectedDatasetImport)}
                  ><Play size={16} weight="fill" />続きから再開</button>
                </div>}

                <div className="training-preprocessing-note">
                  <MagicWand size={22} />
                  <div>
                    <strong>学習用音声の共通加工が完了しています</strong>
                    <span>48 kHz・モノラル化、前後無音調整、-16 LUFS正規化を音声追加時に適用</span>
                    <small>学習時は加工せず固定スナップショットを使用し、RAW原本と文中の間を維持します。</small>
                  </div>
                </div>
              </> : <div className="training-empty-dataset">
                <Database size={28} />
                <div><strong>学習データセットがありません</strong><span>新しく作成して、コーパス録音または音声ファイルを追加してください。</span></div>
                <button type="button" className="primary-button" onClick={() => setShowCreateDataset(true)}><Plus size={18} />作成</button>
              </div>}
            </section>

            <section className="training-setup-card">
              <div className="training-section-title">
                <span>2</span>
                <div><h2>モデルを名付ける</h2><p>完成後もボイスライブラリで識別できる名前にします。</p></div>
              </div>
              <label className="training-name-field">
                <span>モデル名</span>
                <input value={name} maxLength={80} placeholder="例：Usako ナレーション" onChange={(event) => setName(event.target.value)} />
              </label>
            </section>

            <section className="training-setup-card">
              <div className="training-section-title">
                <span>3</span>
                <div><h2>学習方法を選ぶ</h2><p>通常はSpeaker Inversionが適しています。</p></div>
              </div>
              <div className="training-methods">
                <MethodCard
                  active={method === "speaker_inversion"}
                  icon={<Waveform size={25} />}
                  title="Speaker Inversion"
                  badge="おすすめ"
                  description="話者らしさだけを小さな埋め込みとして学習します。"
                  details="軽量 · 短時間 · 基本モデルは変更しません"
                  onClick={() => setMethod("speaker_inversion")}
                />
                <MethodCard
                  active={method === "lora"}
                  icon={<Brain size={25} />}
                  title="LoRA"
                  description="声質と発話傾向をモデルへ追加学習します。"
                  details="上級者向け · より多くの音声と時間が必要です"
                  onClick={() => setMethod("lora")}
                />
              </div>
            </section>

            <section className="training-setup-card compact">
              <button className="training-advanced-toggle" type="button" onClick={() => setAdvanced((value) => !value)}>
                <Cpu size={20} />
                <span><strong>学習設定</strong><small>{device} · {precision} · {maxSteps.toLocaleString()} steps</small></span>
                <Plus size={18} className={advanced ? "open" : ""} />
              </button>
              {advanced && <div className="training-advanced-fields">
                <label>
                  <span>基本モデル</span>
                  <div className="training-path-input">
                    <input value={checkpoint} onChange={(event) => setCheckpoint(event.target.value)} />
                    <IconButton
                      label="基本モデルを選択"
                      onClick={() => api.dialog("checkpoint")
                        .then(({ paths: selected }) => selected[0] && setCheckpoint(selected[0]))
                        .catch((error) => notify(error.message, "error"))}
                    ><FolderOpen size={18} /></IconButton>
                  </div>
                </label>
                <label><span>デバイス</span><select value={device} onChange={(event) => setDevice(event.target.value)}>{(bootstrap?.devices || ["cuda", "cpu"]).map((item) => <option key={item}>{item}</option>)}</select></label>
                <label><span>精度</span><select value={precision} onChange={(event) => setPrecision(event.target.value)}>{(bootstrap?.precisions?.[device] || ["bf16", "fp32"]).map((item) => <option key={item}>{item}</option>)}</select></label>
                <label><span>学習ステップ</span><input type="number" min="1" max="1000000" value={maxSteps} onChange={(event) => setMaxSteps(Number(event.target.value))} /></label>
                <p className="training-step-guidance">
                  {method === "speaker_inversion" ? <><strong>既定は500 stepです。</strong> より高品質を求める場合は1000 step以上を目安にしてください。</> : <><strong>既定は1,500 stepです。</strong> 高品質・追い込みでは3,000 stepを目安にしてください。</>}
                </p>
              </div>}
            </section>

            <button className="training-start-button" type="button" onClick={startTraining} disabled={trainingBlocked}>
              {busy ? <SpinnerGap className="spin" size={22} /> : <Lightning size={22} weight="fill" />}
              <span><strong>{methodLabel(method)}を開始</strong><small>{activeImportJob ? "音声の前処理が完了すると開始できます" : "実行中は読み上げモデルをGPUから解放します"}</small></span>
            </button>
          </div>
        </section>

        <aside className="training-side-panel">
          <header><div><small>TRAINING RUNS</small><h2>学習とモデル</h2></div><span>{jobs.length}</span></header>
          {activeJob && <article className="training-active-card">
            <div className="training-job-heading">
              <span className="training-job-spinner"><SpinnerGap className="spin" size={22} /></span>
              <div><small>{trainingStatusLabel(activeJob.status)}</small><strong>{activeJob.name}</strong><span>{methodLabel(activeJob.method)} · {activeJob.dataset_name}</span></div>
            </div>
            <div className="training-progress"><span style={{ width: `${activeJob.progress || 0}%` }} /></div>
            <div className="training-progress-meta"><span>{activeJob.stage === "preparing" ? "音声を調整中" : `${Number(activeJob.step || 0).toLocaleString()} / ${Number(activeJob.max_steps || 0).toLocaleString()} steps`}</span><strong>{activeJob.progress || 0}%</strong></div>
            <div className="training-time-estimate" aria-label="学習時間の目安">
              <span>残り時間 <strong>{formatTrainingEstimate(activeJob.training_timing).remaining}</strong></span>
              <span>全体時間 <strong>{formatTrainingEstimate(activeJob.training_timing).total}</strong></span>
            </div>
            <p>{activeJob.message}</p>
            <button type="button" onClick={() => stopTraining(activeJob)} disabled={activeJob.status === "cancelling"}><Stop size={18} weight="fill" />学習を停止</button>
          </article>}

          <div className="training-history">
            {trainedModels.map((model) => <article key={`model-${model.id}`} className="training-history-item completed">
              <span className="training-history-icon"><CheckCircle size={21} weight="fill" /></span>
              <div><strong>{model.name}</strong><span>{methodLabel(model.method)} · 利用可能</span><small>{formatDate(model.created_at)} · {model.dataset_name}</small></div>
              <span className="training-resource-actions">
                <IconButton label={`${model.name}の名前を変更`} onClick={() => { setRenameModelTarget(model); setRenameModelName(model.name); }}><PencilSimple size={16} /></IconButton>
                <IconButton label={`${model.name}を削除`} tone="danger" onClick={() => setDeleteModelTarget(model)}><Trash size={16} /></IconButton>
              </span>
            </article>)}
            {jobs.filter((job) => job.id !== activeJob?.id && job.status !== "completed").map((job) => <article key={job.id} className={`training-history-item ${job.status}`}>
              <span className="training-history-icon">{job.status === "failed" ? <WarningCircle size={21} /> : <ClockCounterClockwise size={21} />}</span>
              <div>
                <strong>{job.name}</strong>
                <span>{methodLabel(job.method)} · {job.status === "failed" ? failureForJob(job).title : trainingStatusLabel(job.status)}</span>
                <small title={job.status === "failed" ? failureForJob(job).summary : undefined}>{job.status === "failed" ? failureForJob(job).summary : formatDate(job.updated_at)}</small>
              </div>
              <span className="training-resource-actions">
                {job.status === "failed" && <IconButton label={`${job.name}の失敗原因を確認`} onClick={() => showTrainingFailure(job)}><Info size={17} /></IconButton>}
                {RESUMABLE_TRAINING_STATUSES.has(job.status) && <>
                  <IconButton label={`${job.name}を再開`} onClick={() => resumeTraining(job)}><Play size={16} weight="fill" /></IconButton>
                  <IconButton label={`${job.name}を最初からやり直す`} onClick={() => setRestartJobTarget(job)}><ArrowCounterClockwise size={17} /></IconButton>
                </>}
                {!ACTIVE_TRAINING_STATUSES.has(job.status) && <IconButton label={`${job.name}の履歴を削除`} tone="danger" onClick={() => setDeleteJobTarget(job)}><Trash size={17} /></IconButton>}
              </span>
            </article>)}
            {!jobs.length && !trainedModels.length && <div className="training-empty-history"><Brain size={32} /><strong>まだ学習履歴はありません</strong><span>学習データを選び、最初のモデルを作成してください。</span></div>}
          </div>
          {trainedModels.length > 0 && <p className="training-model-count"><CheckCircle size={18} />利用可能な学習済みモデル {trainedModels.length}件</p>}
        </aside>
      </main>

      {showReview && datasetDetail && <DatasetReviewModal
        dataset={datasetDetail}
        notify={notify}
        onClose={() => setShowReview(false)}
        onRecordingUpdated={updateDetailRecording}
        playbackVolume={playbackVolume}
        outputDeviceId={outputDeviceId}
      />}

      {showImportHistory && selectedDataset && <Modal
        title={`${selectedDataset.name}の前処理履歴`}
        eyebrow="AUDIO PREPROCESSING"
        onClose={() => setShowImportHistory(false)}
        wide
        scrollable
      >
        <div className="training-import-history-intro">
          <ClockCounterClockwise size={22} />
          <div>
            <strong>失敗・中断した処理は続きから再開できます</strong>
            <span>保存済みの分割音声と文字起こしを再利用します。履歴を削除しても、データセットへ確定済みのWAVとRAW原本は残ります。</span>
          </div>
        </div>
        <div className="training-import-history-list">
          {selectedDatasetImports.map((job) => {
            const resumable = RESUMABLE_IMPORT_STATUSES.has(job.status);
            const active = ACTIVE_IMPORT_STATUSES.has(job.status);
            const sourceCount = job.sources?.length || job.report?.source_count || 0;
            return <article key={job.id} className={`training-import-history-item ${job.status}`}>
              <span className="training-import-history-icon">
                {job.status === "completed" && <CheckCircle size={22} weight="fill" />}
                {job.status === "failed" && <WarningCircle size={22} weight="fill" />}
                {job.status !== "completed" && job.status !== "failed" && <ClockCounterClockwise size={22} />}
              </span>
              <div className="training-import-history-copy">
                <span>
                  <strong>{importStatusLabel(job.status)}</strong>
                  {Number(job.attempt || 1) > 1 && <small>再開 {Number(job.attempt) - 1}回</small>}
                </span>
                <p>{job.failure?.summary || job.message}</p>
                {job.failure?.action && <span className="training-import-recovery">{job.failure.action}</span>}
                <small>
                  {formatDate(job.completed_at || job.updated_at)} · 素材 {sourceCount}件 · 抽出 {Number(job.candidate_count || 0).toLocaleString()}件 · 自動採用 {Number(job.accepted_count || 0).toLocaleString()}件
                </small>
                {job.report?.reused_candidate_count > 0 && <em>保存済み {Number(job.report.reused_candidate_count).toLocaleString()}件を再利用</em>}
                {active && <div className="training-progress"><span style={{ width: `${Number(job.percent || 0)}%` }} /></div>}
              </div>
              <span className="training-import-history-actions">
                {active && <IconButton label="音声の前処理を停止" tone="danger" disabled={job.status === "cancelling"} onClick={() => cancelImport(job)}><Stop size={17} weight="fill" /></IconButton>}
                {resumable && <IconButton
                  label="保存済みの処理結果から再開"
                  disabled={Boolean(activeImportJob || activeJob || busy)}
                  onClick={() => resumeImport(job)}
                ><Play size={16} weight="fill" /></IconButton>}
                {!active && <IconButton label="音声前処理の履歴を削除" tone="danger" onClick={() => setDeleteImportJobTarget(job)}><Trash size={17} /></IconButton>}
              </span>
            </article>;
          })}
          {!selectedDatasetImports.length && <div className="training-import-history-empty">
            <FileAudio size={30} />
            <strong>前処理履歴はまだありません</strong>
            <span>複数の音声ファイルを選ぶと、実行結果をここで管理できます。</span>
          </div>}
        </div>
      </Modal>}

      {showCreateDataset && <NameDialog
        title="学習データセットを作成"
        eyebrow="NEW DATASET"
        description="コーパス録音と手持ち音声を、同じ話者の学習データとしてまとめる名前を付けます。"
        label="データセット名"
        value={newDatasetName}
        onChange={setNewDatasetName}
        onSubmit={createDataset}
        onClose={() => setShowCreateDataset(false)}
        submitLabel="作成"
        busy={busy}
        disabled={!newDatasetName.trim() || datasets.some((dataset) => dataset.name.toLocaleLowerCase("ja-JP") === newDatasetName.trim().toLocaleLowerCase("ja-JP"))}
      />}

      {renameDatasetTarget && <NameDialog
        title="学習データセット名を変更"
        eyebrow="RENAME DATASET"
        description="録音タブと学習タブの両方で表示される名前を変更します。音声と学習履歴は維持されます。"
        label="データセット名"
        value={renameDatasetName}
        onChange={setRenameDatasetName}
        onSubmit={renameDataset}
        onClose={() => setRenameDatasetTarget(null)}
        submitLabel="名前を変更"
        busy={busy}
        disabled={!renameDatasetName.trim() || renameDatasetName.trim() === renameDatasetTarget.name || datasets.some((dataset) => dataset.id !== renameDatasetTarget.id && dataset.name.toLocaleLowerCase("ja-JP") === renameDatasetName.trim().toLocaleLowerCase("ja-JP"))}
      />}

      {deleteDatasetTarget && <ConfirmDialog
        title={`「${deleteDatasetTarget.name}」を削除しますか？`}
        eyebrow="DELETE DATASET"
        description="Studioが管理する収録音声と学習用WAVを削除します。rawフォルダに置いた原本は残します。"
        onConfirm={deleteDataset}
        onClose={() => setDeleteDatasetTarget(null)}
        busy={busy}
      />}

      {renameModelTarget && <NameDialog
        title="学習済みモデル名を変更"
        eyebrow="TRAINED MODEL"
        description="ボイスライブラリで選択するときの表示名を変更します。学習結果と元音声はそのまま維持されます。"
        label="モデル名"
        value={renameModelName}
        onChange={setRenameModelName}
        onSubmit={renameModel}
        onClose={() => setRenameModelTarget(null)}
        submitLabel="名前を変更"
        busy={busy}
        maxLength={80}
        disabled={!renameModelName.trim() || renameModelName.trim() === renameModelTarget.name || trainedModels.some((model) => model.id !== renameModelTarget.id && model.name.toLocaleLowerCase("ja-JP") === renameModelName.trim().toLocaleLowerCase("ja-JP"))}
      />}

      {deleteModelTarget && <ConfirmDialog
        title={`「${deleteModelTarget.name}」を削除しますか？`}
        eyebrow="DELETE MODEL"
        description="学習済みモデルのファイルを削除します。ボイスライブラリで使用中の場合は削除を停止します。"
        onConfirm={() => deleteModel(deleteModelTarget)}
        onClose={() => setDeleteModelTarget(null)}
        busy={busy}
      />}

      {trainingVramWarning && <ConfirmDialog
        title="VRAMが不足する可能性があります"
        eyebrow="TRAINING PREFLIGHT"
        description={`このGPUのVRAMは${trainingVramWarning.totalVramGb.toFixed(1)} GBです。現在の${methodLabel(trainingVramWarning.method)}設定は${trainingVramWarning.recommendedVramGb} GB以上を推奨しており、共有メモリへの退避で極端に遅くなるか、学習を開始できない可能性があります。${trainingVramWarning.method === "lora" ? "Speaker Inversionへの変更も検討してください。" : "他のGPU処理を終了するか、設定を見直してください。"}`}
        confirmLabel="それでも開始"
        danger={false}
        onConfirm={createTrainingJob}
        onClose={() => setTrainingVramWarning(null)}
        busy={busy}
      />}

      {restartJobTarget && <ConfirmDialog
        title={`「${restartJobTarget.name}」を最初からやり直しますか？`}
        eyebrow="RESTART TRAINING"
        description="前処理済みコピー、latent、未完成のモデル出力を作り直します。学習データセットとraw原本は変更しません。"
        confirmLabel="すべてやり直す"
        danger={false}
        onConfirm={() => resumeTraining(restartJobTarget, true)}
        onClose={() => setRestartJobTarget(null)}
        busy={busy}
      />}

      {failureJob && <Modal
        title={failureForJob(failureJob).title}
        eyebrow="TRAINING FAILED"
        onClose={() => setFailureJob(null)}
      >
        <div className="training-failure-dialog">
          <div className="training-failure-summary">
            <WarningCircle size={25} weight="fill" />
            <div>
              <strong>{failureForJob(failureJob).summary}</strong>
              <span>{failureForJob(failureJob).action}</span>
            </div>
          </div>
          <dl>
            <div><dt>学習方法</dt><dd>{methodLabel(failureJob.method)}</dd></div>
            <div><dt>データセット</dt><dd>{failureJob.dataset_name}</dd></div>
            <div><dt>停止日時</dt><dd>{formatDate(failureJob.updated_at)}</dd></div>
          </dl>
          {failureForJob(failureJob).details && <details>
            <summary><CaretRight size={17} />技術情報</summary>
            <pre>{failureForJob(failureJob).details}</pre>
          </details>}
        </div>
      </Modal>}

      {deleteJobTarget && <ConfirmDialog
        title={`「${deleteJobTarget.name}」の履歴を削除しますか？`}
        eyebrow="DELETE TRAINING RUN"
        description="学習ログと一時ファイルを削除します。完成済みの学習済みモデルは削除されません。"
        onConfirm={() => deleteJob(deleteJobTarget)}
        onClose={() => setDeleteJobTarget(null)}
        busy={busy}
      />}

      {deleteImportJobTarget && <ConfirmDialog
        title="この音声前処理履歴を削除しますか？"
        eyebrow="DELETE PREPROCESSING HISTORY"
        description="履歴と再開用の一時ファイルだけを削除します。学習データセットへ確定済みのWAVとRAW原本は削除しません。"
        onConfirm={() => deleteImportJob(deleteImportJobTarget)}
        onClose={() => setDeleteImportJobTarget(null)}
        busy={busy}
      />}
    </>
  );
}
