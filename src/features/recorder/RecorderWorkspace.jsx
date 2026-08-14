import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowCounterClockwise,
  Check,
  CheckCircle,
  Circle,
  Database,
  GearSix,
  Headphones,
  ListChecks,
  Microphone,
  Pause,
  PencilSimple,
  Play,
  Plus,
  ShieldCheck,
  SpinnerGap,
  Stop,
  Trash,
  WarningCircle,
  Waveform as WaveformIcon,
} from "@phosphor-icons/react";

import { ConfirmDialog, IconButton, Modal, NameDialog } from "../../components/StudioUI.jsx";
import { resolveLearningDatasetId } from "../../learning-datasets.js";
import { CORPUS_ROOT, CORPUS_STAGES, getCorpusPrompts, getCorpusStage } from "./corpus-catalog.js";
import {
  analyseAudio,
  createWaveformPreview,
  encodeWav,
  flattenBuffers,
  RECORDER_SAMPLE_RATE,
  recordingQuality,
  resampleAudio,
} from "./recorder-audio.js";
import { enumerateAudioInputs } from "./recorder-devices.js";
import {
  clearLegacyRecordings,
  createRecordingDataset,
  deleteRecordingDataset,
  listRecordingDatasets,
  loadRecordingDataset,
  readLegacyRecordings,
  renameRecordingDataset,
  writeDatasetRecording,
} from "./recorder-storage.js";
import "./recorder.css";

const LEGACY_CURRENT_INDEX_KEY = "irodori-studio-recorder-index-v1";
const CURRENT_PROMPTS_KEY = "irodori-studio-recorder-prompts-v2";
const CORPUS_STAGE_KEY = "irodori-studio-recorder-corpus-stage-v1";
const DEVICE_ID_KEY = "irodori-studio-recorder-device-v1";

function readPromptPositions() {
  try {
    return JSON.parse(localStorage.getItem(CURRENT_PROMPTS_KEY) || "{}");
  } catch {
    return {};
  }
}

function nextDatasetName(datasets) {
  const names = new Set(datasets.map((dataset) => dataset.name));
  if (!names.has("新しい学習データセット")) return "新しい学習データセット";
  let number = 2;
  while (names.has(`新しい学習データセット ${number}`)) number += 1;
  return `新しい学習データセット ${number}`;
}

function datasetSummary(recordings) {
  const values = Object.values(recordings);
  const accepted = values.filter((recording) => recording.accepted);
  return {
    recorded: values.length,
    accepted: accepted.length,
    accepted_seconds: accepted.reduce((total, recording) => total + Number(recording.duration || 0), 0),
  };
}

const emotionLabels = {
  neutral: "ニュートラル",
  joy: "喜び",
  sadness: "悲しみ",
  anger: "怒り",
  fear: "恐れ",
  surprise: "驚き",
  affection: "親愛",
  calm: "穏やか",
  tender: "やさしさ",
  whisper: "ささやき",
  relaxed: "リラックス",
  fast: "早口",
};

const intensityLabels = { low: "弱め", medium: "標準", high: "強め" };

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function Waveform({ samples, active }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round(rect.width * ratio);
      canvas.height = Math.round(rect.height * ratio);
      const context = canvas.getContext("2d");
      context.scale(ratio, ratio);
      context.clearRect(0, 0, rect.width, rect.height);
      context.strokeStyle = active ? "#ad3d31" : "#c9651b";
      context.lineWidth = 2;
      context.lineCap = "round";
      context.beginPath();
      const middle = rect.height / 2;
      const values = samples?.length ? samples : new Array(80).fill(0);
      values.forEach((value, index) => {
        const x = (index / Math.max(1, values.length - 1)) * rect.width;
        const height = Math.max(1, value * (rect.height * 0.78));
        context.moveTo(x, middle - height / 2);
        context.lineTo(x, middle + height / 2);
      });
      context.stroke();
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [active, samples]);

  return <canvas ref={canvasRef} className="recorder-waveform" aria-label="録音波形" />;
}

export function RecorderWorkspace({
  notify,
  onRecordingStateChange = () => {},
  playbackVolume = 80,
  outputDeviceId = "",
  datasetId = "",
  onDatasetIdChange = () => {},
}) {
  const [corpusStageId, setCorpusStageId] = useState(() => getCorpusStage(localStorage.getItem(CORPUS_STAGE_KEY)).id);
  const activeStage = getCorpusStage(corpusStageId);
  const corpus = useMemo(() => getCorpusPrompts(corpusStageId), [corpusStageId]);
  const [currentPromptId, setCurrentPromptId] = useState(() => {
    const savedId = readPromptPositions()[corpusStageId];
    if (savedId && corpus.some((prompt) => prompt.id === savedId)) return savedId;
    if (corpusStageId === "starter") {
      const legacyIndex = Number(localStorage.getItem(LEGACY_CURRENT_INDEX_KEY)) || 0;
      return corpus[Math.max(0, Math.min(corpus.length - 1, legacyIndex))].id;
    }
    return corpus[0].id;
  });
  const [datasets, setDatasets] = useState([]);
  const [recordings, setRecordings] = useState({});
  const [isLoaded, setIsLoaded] = useState(false);
  const [datasetBusy, setDatasetBusy] = useState(false);
  const [showCreateDataset, setShowCreateDataset] = useState(false);
  const [showRenameDataset, setShowRenameDataset] = useState(false);
  const [showDeleteDataset, setShowDeleteDataset] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState("新しい学習データセット");
  const [renameDatasetName, setRenameDatasetName] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [liveWave, setLiveWave] = useState([]);
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState(() => localStorage.getItem(DEVICE_ID_KEY) || "");
  const [microphonePermission, setMicrophonePermission] = useState("prompt");
  const [filter, setFilter] = useState("all");
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState("");
  const engineRef = useRef(null);
  const timerRef = useRef(null);
  const audioRef = useRef(null);
  const initialDatasetIdRef = useRef(datasetId);
  const deviceAccessRequestedRef = useRef(false);
  const deviceIdRef = useRef(deviceId);
  const currentIndex = Math.max(0, corpus.findIndex((item) => item.id === currentPromptId));
  const prompt = corpus[currentIndex];
  const currentRecording = recordings[prompt.id];
  const activeDatasetId = datasetId;
  const activeDataset = datasets.find((dataset) => dataset.id === activeDatasetId) || null;

  const refreshDevices = useCallback(async ({ waitForLabels = false } = {}) => (
    enumerateAudioInputs(navigator.mediaDevices, {
      waitForLabels,
      onDevices: (available) => {
        setDevices((previous) => {
          const knownLabels = new Map(previous
            .filter((device) => device.deviceId && device.label?.trim())
            .map((device) => [device.deviceId, device.label]));
          const normalized = available.map((device) => ({
            deviceId: device.deviceId,
            groupId: device.groupId,
            kind: device.kind,
            label: device.label?.trim() || knownLabels.get(device.deviceId) || "",
          }));
          if (deviceIdRef.current && !normalized.some((device) => device.deviceId === deviceIdRef.current)) {
            setDeviceId("");
          }
          return normalized;
        });
      },
    })
  ), []);

  useEffect(() => {
    let cancelled = false;
    const initializeDatasets = async () => {
      try {
        let available = await listRecordingDatasets();
        let selectedId = initialDatasetIdRef.current;
        let migrationDatasetId = "";
        let migrationCommitted = false;
        try {
          const legacy = await readLegacyRecordings();
          if (legacy.length) {
            const migrated = await createRecordingDataset(`以前の録音 ${new Date().toLocaleDateString("ja-JP")}`);
            migrationDatasetId = migrated.id;
            const promptsById = new Map(CORPUS_ROOT.map((item) => [item.id, item]));
            for (const recording of legacy) {
              const legacyPrompt = promptsById.get(recording.id);
              if (!legacyPrompt || !recording.blob) throw new Error("以前の録音に対応する文章または音声がありません。");
              await writeDatasetRecording(migrated.id, recording, legacyPrompt);
            }
            available = await listRecordingDatasets();
            await clearLegacyRecordings();
            migrationCommitted = true;
            selectedId = migrated.id;
            notify("以前のブラウザー録音をStudioのデータセットへ移しました。", "success");
          }
        } catch {
          if (migrationDatasetId && !migrationCommitted) {
            await deleteRecordingDataset(migrationDatasetId).catch(() => {});
            available = await listRecordingDatasets().catch(() => available);
          }
          setError("以前のブラウザー録音はそのまま残っています。Studioへの移行を完了できませんでした。");
        }
        selectedId = resolveLearningDatasetId(available, selectedId);
        const selected = selectedId ? await loadRecordingDataset(selectedId) : null;
        if (cancelled) return;
        setDatasets(available);
        onDatasetIdChange(selectedId);
        setRecordings(selected?.recordings || {});
        setNewDatasetName(nextDatasetName(available));
      } catch {
        if (!cancelled) setError("Studioに保存した学習データセットを読み込めませんでした。");
      } finally {
        if (!cancelled) setIsLoaded(true);
      }
    };
    initializeDatasets();
    refreshDevices().catch(() => {});
    return () => { cancelled = true; };
  }, [notify, onDatasetIdChange, refreshDevices]);

  useEffect(() => {
    if (!navigator.mediaDevices?.addEventListener) return undefined;
    const handleChange = () => refreshDevices().catch(() => {});
    navigator.mediaDevices.addEventListener("devicechange", handleChange);
    return () => navigator.mediaDevices.removeEventListener("devicechange", handleChange);
  }, [refreshDevices]);

  useEffect(() => {
    localStorage.setItem(CORPUS_STAGE_KEY, corpusStageId);
    const positions = readPromptPositions();
    positions[corpusStageId] = currentPromptId;
    localStorage.setItem(CURRENT_PROMPTS_KEY, JSON.stringify(positions));
  }, [corpusStageId, currentPromptId]);

  useEffect(() => {
    deviceIdRef.current = deviceId;
    if (deviceId) localStorage.setItem(DEVICE_ID_KEY, deviceId);
    else localStorage.removeItem(DEVICE_ID_KEY);
  }, [deviceId]);

  useEffect(() => {
    onRecordingStateChange(isRecording);
  }, [isRecording, onRecordingStateChange]);

  const objectAudioUrl = useMemo(() => (
    currentRecording?.blob ? URL.createObjectURL(currentRecording.blob) : ""
  ), [currentRecording]);
  const audioUrl = objectAudioUrl || currentRecording?.audioUrl || "";

  useEffect(() => () => {
    if (objectAudioUrl) URL.revokeObjectURL(objectAudioUrl);
  }, [objectAudioUrl]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = playbackVolume / 100;
    if (typeof audio.setSinkId === "function") audio.setSinkId(outputDeviceId || "").catch(() => {});
  }, [audioUrl, outputDeviceId, playbackVolume]);

  useEffect(() => {
    const warn = (event) => {
      if (isRecording) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [isRecording]);

  useEffect(() => () => {
    window.clearInterval(timerRef.current);
    const engine = engineRef.current;
    if (!engine) return;
    engine.processor.onaudioprocess = null;
    engine.stream.getTracks().forEach((track) => track.stop());
    engine.context.close().catch(() => {});
    engineRef.current = null;
    onRecordingStateChange(false);
  }, [onRecordingStateChange]);

  const acceptedCount = useMemo(
    () => corpus.filter((prompt) => recordings[prompt.id]?.accepted === true).length,
    [corpus, recordings],
  );
  const reviewCount = corpus.filter((item) => recordings[item.id] && !recordings[item.id].accepted).length;
  const progressPercent = (acceptedCount / corpus.length) * 100;
  const hasDeviceLabels = devices.some((device) => device.label?.trim());

  const requestMicrophoneAccess = useCallback(async () => {
    setError("");
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError("録音にはlocalhostまたは安全な接続での表示が必要です。");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      setMicrophonePermission("granted");
      const inputs = await refreshDevices({ waitForLabels: true });
      if (!inputs.some((device) => device.label?.trim())) {
        setError("マイク名を取得できませんでした。ブラウザーのマイク設定を確認してください。");
      }
    } catch (reason) {
      if (reason?.name === "NotAllowedError") {
        setMicrophonePermission("denied");
        setError("録音するにはブラウザーでマイクの使用を許可してください。");
      } else {
        setError("マイク情報を取得できませんでした。接続を確認してください。");
      }
    } finally {
      stream?.getTracks().forEach((track) => track.stop());
    }
  }, [refreshDevices]);

  useEffect(() => {
    if (!isLoaded || hasDeviceLabels || deviceAccessRequestedRef.current) return undefined;
    deviceAccessRequestedRef.current = true;
    let permissionStatus;
    const handlePermissionChange = async () => {
      if (!permissionStatus) return;
      setMicrophonePermission(permissionStatus.state);
      if (permissionStatus.state === "granted") {
        setError("");
        await refreshDevices({ waitForLabels: true });
      }
    };
    const requestOnEntry = async () => {
      try {
        if (navigator.permissions?.query) {
          permissionStatus = await navigator.permissions.query({ name: "microphone" });
          setMicrophonePermission(permissionStatus.state);
          permissionStatus.addEventListener?.("change", handlePermissionChange);
          if (permissionStatus.state === "denied") {
            setError("録音するにはブラウザー設定でマイクを許可してください。");
            return;
          }
        }
      } catch {
        // getUserMedia remains authoritative when Permissions API is unavailable.
      }
      await requestMicrophoneAccess();
    };
    requestOnEntry();
    return () => permissionStatus?.removeEventListener?.("change", handlePermissionChange);
  }, [hasDeviceLabels, isLoaded, refreshDevices, requestMicrophoneAccess]);

  const stopRecording = useCallback(async () => {
    const engine = engineRef.current;
    if (!engine) return;
    window.clearInterval(timerRef.current);
    engine.processor.onaudioprocess = null;
    engine.source.disconnect();
    engine.processor.disconnect();
    engine.silentGain.disconnect();
    engine.stream.getTracks().forEach((track) => track.stop());
    const sourceRate = engine.context.sampleRate;
    await engine.context.close();
    engineRef.current = null;
    setIsRecording(false);

    const captured = flattenBuffers(engine.chunks);
    if (!captured.length) {
      setError("音声を取得できませんでした。マイク設定を確認してください。");
      return;
    }
    const samples = resampleAudio(captured, sourceRate, RECORDER_SAMPLE_RATE);
    const recording = {
      id: prompt.id,
      blob: encodeWav(samples),
      duration: samples.length / RECORDER_SAMPLE_RATE,
      sampleRate: RECORDER_SAMPLE_RATE,
      preview: createWaveformPreview(samples),
      ...analyseAudio(samples),
      accepted: false,
      updatedAt: new Date().toISOString(),
    };
    setRecordings((current) => ({ ...current, [prompt.id]: recording }));
    try {
      const saved = await writeDatasetRecording(activeDatasetId, recording, prompt);
      setRecordings((current) => {
        const next = { ...current, [prompt.id]: saved };
        const summary = datasetSummary(next);
        setDatasets((items) => items.map((item) => item.id === activeDatasetId ? { ...item, ...summary, updated_at: Date.now() / 1000 } : item));
        return next;
      });
    } catch {
      setError("録音をStudioへ保存できませんでした。空き容量とStudioの状態を確認してください。");
      notify("録音は一時的に保持していますが、再読み込みすると失われる可能性があります。", "error");
    }
    setLiveWave(recording.preview);
    notify("録音しました。試聴して採用するか確認してください。", "success");
  }, [activeDatasetId, notify, prompt]);

  const startRecording = useCallback(async () => {
    setError("");
    if (!activeDatasetId) {
      setError("収録先の学習データセットを作成してください。");
      return;
    }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError("録音にはlocalhostまたは安全な接続での表示が必要です。");
      return;
    }
    let pendingStream;
    let pendingContext;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
          channelCount: 1,
          sampleRate: RECORDER_SAMPLE_RATE,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      pendingStream = stream;
      await navigator.storage?.persist?.();
      const context = new AudioContext({ sampleRate: RECORDER_SAMPLE_RATE, latencyHint: "interactive" });
      pendingContext = context;
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(2048, 1, 1);
      const silentGain = context.createGain();
      silentGain.gain.value = 0;
      const chunks = [];
      let lastPreviewAt = 0;
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        chunks.push(new Float32Array(input));
        const now = performance.now();
        if (now - lastPreviewAt > 90) {
          lastPreviewAt = now;
          setLiveWave(createWaveformPreview(input, 96));
        }
      };
      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(context.destination);
      engineRef.current = { context, stream, source, processor, silentGain, chunks };
      pendingStream = null;
      pendingContext = null;
      setElapsed(0);
      setLiveWave([]);
      setIsPlaying(false);
      setIsRecording(true);
      const startedAt = performance.now();
      timerRef.current = window.setInterval(() => setElapsed((performance.now() - startedAt) / 1000), 100);
      refreshDevices({ waitForLabels: true }).catch(() => {});
    } catch (reason) {
      pendingStream?.getTracks().forEach((track) => track.stop());
      pendingContext?.close().catch(() => {});
      if (reason?.name === "NotAllowedError") {
        setMicrophonePermission("denied");
        setError("マイクの使用が許可されていません。ブラウザーの権限を確認してください。");
      } else {
        setError("マイクを開始できませんでした。別のマイクを選んでお試しください。");
      }
    }
  }, [activeDatasetId, deviceId, refreshDevices]);

  useEffect(() => {
    const handleKey = (event) => {
      if (
        event.code !== "Space"
        || event.repeat
        || ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(event.target.tagName)
      ) return;
      event.preventDefault();
      if (isRecording) stopRecording();
      else startRecording();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isRecording, startRecording, stopRecording]);

  const goTo = useCallback((index) => {
    if (isRecording) return;
    audioRef.current?.pause();
    setIsPlaying(false);
    setLiveWave([]);
    const nextIndex = Math.max(0, Math.min(corpus.length - 1, index));
    setCurrentPromptId(corpus[nextIndex].id);
  }, [corpus, isRecording]);

  const changeCorpusStage = useCallback((event) => {
    if (isRecording) return;
    const nextStageId = getCorpusStage(event.target.value).id;
    const nextCorpus = getCorpusPrompts(nextStageId);
    const savedPromptId = readPromptPositions()[nextStageId];
    const nextPrompt = nextCorpus.find((item) => item.id === savedPromptId)
      || nextCorpus.find((item) => !recordings[item.id]?.accepted)
      || nextCorpus[0];
    audioRef.current?.pause();
    setIsPlaying(false);
    setLiveWave([]);
    setError("");
    setCorpusStageId(nextStageId);
    setCurrentPromptId(nextPrompt.id);
  }, [isRecording, recordings]);

  const acceptAndNext = useCallback(async () => {
    if (!currentRecording) return;
    const accepted = { ...currentRecording, accepted: true, acceptedAt: new Date().toISOString() };
    try {
      const saved = await writeDatasetRecording(activeDatasetId, accepted, prompt);
      setRecordings((current) => {
        const next = { ...current, [prompt.id]: saved };
        const summary = datasetSummary(next);
        setDatasets((items) => items.map((item) => item.id === activeDatasetId ? { ...item, ...summary, updated_at: Date.now() / 1000 } : item));
        return next;
      });
    } catch {
      setError("採用状態をStudioへ保存できませんでした。空き容量とStudioの状態を確認してください。");
      return;
    }
    const remaining = corpus.findIndex((item, index) => index > currentIndex && !recordings[item.id]?.accepted);
    const wrapped = corpus.findIndex((item) => item.id !== prompt.id && !recordings[item.id]?.accepted);
    if (remaining >= 0) goTo(remaining);
    else if (wrapped >= 0) goTo(wrapped);
    else notify(`${activeStage.title}の${corpus.length}件すべての録音が完了しました。`, "success");
  }, [activeDatasetId, activeStage.title, corpus, currentIndex, currentRecording, goTo, notify, prompt, recordings]);

  const togglePlayback = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
      return;
    }
    audio.currentTime = 0;
    try {
      await audio.play();
      setIsPlaying(true);
    } catch {
      setError("録音を再生できませんでした。");
    }
  }, [isPlaying]);

  const switchDataset = useCallback(async (event) => {
    const datasetId = event.target.value;
    if (!datasetId || datasetId === activeDatasetId || isRecording || datasetBusy) return;
    setDatasetBusy(true);
    setError("");
    try {
      const selected = await loadRecordingDataset(datasetId);
      audioRef.current?.pause();
      setIsPlaying(false);
      setLiveWave([]);
      onDatasetIdChange(datasetId);
      setRecordings(selected.recordings);
    } catch {
      setError("学習データセットを開けませんでした。");
    } finally {
      setDatasetBusy(false);
    }
  }, [activeDatasetId, datasetBusy, isRecording, onDatasetIdChange]);

  const createDataset = useCallback(async () => {
    if (!newDatasetName.trim() || datasetBusy) return;
    setDatasetBusy(true);
    setError("");
    try {
      const created = await createRecordingDataset(newDatasetName.trim());
      const available = await listRecordingDatasets();
      audioRef.current?.pause();
      setDatasets(available);
      onDatasetIdChange(created.id);
      setRecordings({});
      setCurrentPromptId(corpus[0].id);
      setLiveWave([]);
      setIsPlaying(false);
      setShowCreateDataset(false);
      setNewDatasetName(nextDatasetName(available));
      notify(`「${created.name}」を作成しました。`, "success");
    } catch (reason) {
      setError(reason.message || "学習データセットを作成できませんでした。");
    } finally {
      setDatasetBusy(false);
    }
  }, [corpus, datasetBusy, newDatasetName, notify, onDatasetIdChange]);

  const deleteActiveDataset = useCallback(async () => {
    if (!activeDatasetId || datasetBusy || isRecording) return;
    setDatasetBusy(true);
    setError("");
    const deletedName = activeDataset?.name || "学習データセット";
    try {
      await deleteRecordingDataset(activeDatasetId);
      const available = await listRecordingDatasets();
      const nextId = available[0]?.id || "";
      const next = nextId ? await loadRecordingDataset(nextId) : null;
      audioRef.current?.pause();
      setDatasets(available);
      onDatasetIdChange(nextId);
      setRecordings(next?.recordings || {});
      setCurrentPromptId(corpus[0].id);
      setLiveWave([]);
      setIsPlaying(false);
      setShowDeleteDataset(false);
      setNewDatasetName(nextDatasetName(available));
      notify(`「${deletedName}」を削除しました。`, "success");
    } catch (reason) {
      setError(reason.message || "学習データセットを削除できませんでした。");
    } finally {
      setDatasetBusy(false);
    }
  }, [activeDataset?.name, activeDatasetId, corpus, datasetBusy, isRecording, notify, onDatasetIdChange]);

  const renameActiveDataset = useCallback(async () => {
    const name = renameDatasetName.trim();
    if (!activeDatasetId || !name || datasetBusy || isRecording) return;
    setDatasetBusy(true);
    setError("");
    try {
      const renamed = await renameRecordingDataset(activeDatasetId, name);
      const available = await listRecordingDatasets();
      setDatasets(available);
      setShowRenameDataset(false);
      setNewDatasetName(nextDatasetName(available));
      notify(`学習データセット名を「${renamed.name}」へ変更しました。`, "success");
    } catch (reason) {
      setError(reason.message || "学習データセット名を変更できませんでした。");
    } finally {
      setDatasetBusy(false);
    }
  }, [activeDatasetId, datasetBusy, isRecording, notify, renameDatasetName]);

  const filteredPrompts = corpus
    .map((item, index) => ({ item, index, recording: recordings[item.id] }))
    .filter(({ recording }) => {
      if (filter === "done") return recording?.accepted;
      if (filter === "todo") return !recording?.accepted;
      return true;
    });
  const quality = recordingQuality(currentRecording);
  const waveform = isRecording ? liveWave : currentRecording?.preview || [];

  if (!isLoaded) {
    return <main className="recorder-loading"><SpinnerGap className="spin" size={27} /><span>録音環境を準備しています…</span></main>;
  }

  const progressPanel = (
    <aside className="recorder-progress-panel">
      <div className="recorder-progress-header">
        <div><small>STEP {activeStage.level} · RECORDING PROGRESS</small><h2>録音リスト</h2><p>{activeStage.title}</p></div>
        <span>{acceptedCount}/{corpus.length}</span>
      </div>
      <div className="recorder-progress-summary">
        <div><strong>{acceptedCount}</strong><span>採用済み</span></div>
        <div><strong>{reviewCount}</strong><span>確認待ち</span></div>
        <div><strong>{corpus.length - acceptedCount - reviewCount}</strong><span>未録音</span></div>
      </div>
      {activeStage.source && <a className="recorder-corpus-credit" href={activeStage.source.url} target="_blank" rel="noreferrer">
        {activeStage.source.name} · {activeStage.source.creator} · {activeStage.source.license}
      </a>}
      <div className="recorder-filter-tabs" role="tablist" aria-label="録音状態で絞り込み">
        {[["all", "すべて"], ["todo", "未完了"], ["done", "完了"]].map(([id, label]) => (
          <button key={id} className={filter === id ? "active" : ""} onClick={() => setFilter(id)}>{label}</button>
        ))}
      </div>
      <div className="recorder-prompt-list">
        {filteredPrompts.map(({ item, index, recording }) => (
          <button key={item.id} className={`recorder-prompt-item ${index === currentIndex ? "current" : ""}`} onClick={() => goTo(index)} disabled={isRecording}>
            <span className={`recorder-prompt-status ${recording?.accepted ? "done" : recording ? "review" : ""}`}>
              {recording?.accepted ? <Check size={15} /> : recording ? <Circle size={9} weight="fill" /> : String(index + 1).padStart(2, "0")}
            </span>
            <span className="recorder-prompt-copy"><strong>{item.text}</strong><small>{emotionLabels[item.emotion] || item.emotion} · {item.direction}</small></span>
            {recording && <ArrowCounterClockwise size={15} />}
          </button>
        ))}
      </div>
      <div className="recorder-autosave-status"><Database size={17} /><span><strong>{activeDataset?.name || "録音先がありません"}</strong><small>{activeDataset ? "採用済み音声は学習から選択できます" : "データセットを作成すると録音できます"}</small></span></div>
    </aside>
  );

  return (
    <main className="recorder-workspace">
      <section className="recorder-main">
        <header className="recorder-toolbar">
          <div><span className="eyebrow">VOICE CORPUS</span><h1>録音スタジオ</h1><p>読み上げ音声を収録し、Irodori-TTSの学習データを作ります。</p></div>
          <div className="recorder-toolbar-actions">
            <label className="recorder-device-select">
              <Microphone size={18} />
              <select value={deviceId} onChange={(event) => setDeviceId(event.target.value)} disabled={isRecording} aria-label="録音に使用するマイク">
                <option value="">{hasDeviceLabels ? "既定のマイク" : microphonePermission === "denied" ? "マイクの許可が必要" : "マイクを確認中…"}</option>
                {devices.filter((device) => device.label?.trim()).map((device) => <option key={device.deviceId} value={device.deviceId}>{device.label}</option>)}
              </select>
            </label>
            <span className="recorder-format"><WaveformIcon size={17} />48 kHz · Mono · PCM 16-bit</span>
            <IconButton label="録音設定" onClick={() => setShowSettings(true)}><GearSix size={19} /></IconButton>
          </div>
        </header>
        <div className="recorder-progress-rail" aria-label={`録音進捗 ${acceptedCount}/${corpus.length}`}><span style={{ width: `${progressPercent}%` }} /></div>

        <div className="recorder-scroll">
          <div className="recorder-studio-panel">
            <div className="recorder-dataset-bar">
              <label className="recorder-dataset-select">
                <Database size={21} />
                <span><small>収録先データセット</small><select value={activeDatasetId} onChange={switchDataset} disabled={isRecording || datasetBusy} aria-label="収録先の学習データセット">
                  {!datasets.length && <option value="">データセットを作成してください</option>}
                  {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name} · {dataset.accepted}件採用</option>)}
                </select></span>
              </label>
              <IconButton label="学習データセットを作成" onClick={() => { setError(""); setNewDatasetName(nextDatasetName(datasets)); setShowCreateDataset(true); }} disabled={isRecording || datasetBusy}><Plus size={19} /></IconButton>
              <IconButton label="学習データセット名を変更" onClick={() => { setError(""); setRenameDatasetName(activeDataset?.name || ""); setShowRenameDataset(true); }} disabled={!activeDatasetId || isRecording || datasetBusy}><PencilSimple size={19} /></IconButton>
              <IconButton label="学習データセットを削除" tone="danger" onClick={() => setShowDeleteDataset(true)} disabled={!activeDatasetId || isRecording || datasetBusy}><Trash size={19} /></IconButton>
            </div>
            <div className="recorder-studio-meta">
              <label className="recorder-corpus-switcher">
                <ListChecks size={19} />
                <span><small>収録コーパス</small><select value={corpusStageId} onChange={changeCorpusStage} disabled={isRecording} aria-label="収録するコーパス">
                  {CORPUS_STAGES.map((stage) => <option key={stage.id} value={stage.id}>{stage.optionLabel}</option>)}
                </select></span>
              </label>
              <div className="recorder-counter"><strong>{currentIndex + 1}</strong><span>/ {corpus.length}</span></div>
              <div className="recorder-nav-buttons">
                <button onClick={() => goTo(currentIndex - 1)} disabled={currentIndex === 0 || isRecording} aria-label="前の文章"><ArrowLeft size={19} /></button>
                <button onClick={() => goTo(currentIndex + 1)} disabled={currentIndex === corpus.length - 1 || isRecording} aria-label="次の文章"><ArrowRight size={19} /></button>
              </div>
            </div>

            {!activeDatasetId && <div className="recorder-dataset-required"><Database size={22} /><span><strong>収録先の学習データセットを作成してください。</strong> 音声はStudioへ自動保存され、学習からそのまま選択できます。</span><button className="primary-button" onClick={() => { setError(""); setNewDatasetName(nextDatasetName(datasets)); setShowCreateDataset(true); }}>作成</button></div>}
            {acceptedCount === corpus.length && <div className="recorder-complete"><CheckCircle size={21} /><span><strong>すべて録音できました。</strong> このデータセットは学習から選択できます。</span></div>}

            <article className={`recorder-reading-card emotion-${prompt.emotion}`}>
              <div className="recorder-reading-eyebrow"><span>READING {String(currentIndex + 1).padStart(3, "0")}</span><div><span>{emotionLabels[prompt.emotion] || prompt.emotion}</span><span>{intensityLabels[prompt.intensity] || prompt.intensity}</span></div></div>
              <p>{prompt.text}</p>
              <div className="recorder-direction"><span><Headphones size={19} /></span><div><small>演技・読み方</small><p>{prompt.direction}</p></div></div>
            </article>

            <section className={`recorder-capture-card ${isRecording ? "recording" : ""}`}>
              <div className="recorder-waveform-header">
                <span className={`recorder-state-dot ${isRecording ? "live" : currentRecording ? "ready" : ""}`} />
                <strong>{isRecording ? "録音中" : currentRecording ? (currentRecording.accepted ? "採用済み" : "確認してください") : "録音の準備ができました"}</strong>
                <time>{isRecording ? formatTime(elapsed) : currentRecording ? formatTime(currentRecording.duration) : `目安 ${prompt.expectedSeconds.toFixed(1)}秒`}</time>
              </div>
              <Waveform samples={waveform} active={isRecording} />
              <div className="recorder-waveform-scale"><span>0:00</span><span>{currentRecording ? formatTime(currentRecording.duration) : ""}</span></div>
              <div className="recorder-quality-row">
                <span>48,000 Hz</span><span>モノラル</span>
                {quality && <span className={`quality ${quality.tone}`}><Check size={14} />{quality.label}</span>}
              </div>
              {error && <div className="recorder-error" role="alert"><WarningCircle size={18} />{error}</div>}
              <div className="recorder-controls">
                {currentRecording && !isRecording && <button className="listen" onClick={togglePlayback}>{isPlaying ? <Pause size={20} /> : <Play size={20} weight="fill" />}{isPlaying ? "停止" : "聴く"}</button>}
                <button className={`record ${isRecording ? "stop" : ""}`} onClick={isRecording ? stopRecording : startRecording} disabled={!activeDatasetId || datasetBusy}>
                  <span>{isRecording ? <Stop size={20} weight="fill" /> : <Circle size={23} weight="fill" />}</span>
                  {isRecording ? "録音を停止" : currentRecording ? "録り直す" : "録音を開始"}
                </button>
                {currentRecording && !isRecording && <button className="accept" onClick={acceptAndNext}><Check size={20} />採用して次へ</button>}
              </div>
              <p className="recorder-shortcut">スペースキーでも録音を開始・停止できます</p>
              {audioUrl && <audio ref={audioRef} src={audioUrl} onEnded={() => setIsPlaying(false)} />}
            </section>
          </div>
        </div>
      </section>

      {progressPanel}

      {showSettings && <Modal title="録音設定" eyebrow="RECORDING" onClose={() => setShowSettings(false)}><section className="recorder-settings-content">
        <p className="resource-dialog-description">録音は48 kHz・モノラル・PCM 16-bit WAVへ変換し、選択中のデータセットへ自動保存します。</p>
        <label><span>使用するマイク</span><select value={deviceId} onChange={(event) => setDeviceId(event.target.value)} disabled={isRecording}><option value="">{hasDeviceLabels ? "既定のマイク" : "マイクの許可が必要"}</option>{devices.filter((device) => device.label?.trim()).map((device) => <option key={device.deviceId} value={device.deviceId}>{device.label}</option>)}</select></label>
        {microphonePermission === "denied" && <button className="secondary-button" onClick={requestMicrophoneAccess}><Microphone size={18} />マイクを許可</button>}
        <div className="recorder-privacy"><ShieldCheck size={20} /><span><strong>このPCだけで処理</strong>録音は外部へ送信せず、Studioの学習データセットへ保存します。</span></div>
      </section></Modal>}

      {showCreateDataset && <NameDialog
        title="学習データセットを作成"
        eyebrow="RECORDING DATASET"
        description="話者や収録セッションが分かる名前を付けてください。録音はこのデータセットへ自動保存されます。"
        label="データセット名"
        value={newDatasetName}
        onChange={setNewDatasetName}
        onSubmit={createDataset}
        onClose={() => setShowCreateDataset(false)}
        submitLabel="作成"
        busy={datasetBusy}
        error={error}
        disabled={!newDatasetName.trim() || datasets.some((dataset) => dataset.name.toLocaleLowerCase("ja-JP") === newDatasetName.trim().toLocaleLowerCase("ja-JP"))}
      />}

      {showRenameDataset && <NameDialog
        title="学習データセット名を変更"
        eyebrow="RECORDING DATASET"
        description="Studioの表示名とworkspace内の保存フォルダ名を一緒に変更します。録音や学習との紐付けは維持されます。"
        label="データセット名"
        value={renameDatasetName}
        onChange={setRenameDatasetName}
        onSubmit={renameActiveDataset}
        onClose={() => setShowRenameDataset(false)}
        submitLabel="名前を変更"
        busy={datasetBusy}
        error={error}
        disabled={!renameDatasetName.trim() || renameDatasetName.trim() === activeDataset?.name || datasets.some((dataset) => dataset.id !== activeDatasetId && dataset.name.toLocaleLowerCase("ja-JP") === renameDatasetName.trim().toLocaleLowerCase("ja-JP"))}
      />}

      {showDeleteDataset && <ConfirmDialog
        title={`「${activeDataset?.name}」を削除しますか？`}
        eyebrow="DELETE DATASET"
        description="このデータセットに保存された、採用済みを含むすべての録音を削除します。この操作は元に戻せません。"
        onConfirm={deleteActiveDataset}
        onClose={() => setShowDeleteDataset(false)}
        busy={datasetBusy}
      />}
    </main>
  );
}
