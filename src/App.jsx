import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowsClockwise,
  Broadcast,
  CaretDown,
  Check,
  Clock,
  Copy,
  Cpu,
  DotsSixVertical,
  DownloadSimple,
  Export,
  FileText,
  FloppyDisk,
  FolderOpen,
  FolderPlus,
  GearSix,
  GraduationCap,
  HardDrive,
  Lightning,
  ListNumbers,
  MagicWand,
  MicrophoneStage,
  Pause,
  PencilSimple,
  Play,
  PlugsConnected,
  Plus,
  Queue,
  SlidersHorizontal,
  Smiley,
  SpeakerHigh,
  SpinnerGap,
  Stop,
  Trash,
  UploadSimple,
  UserSound,
  VideoCamera,
  WarningCircle,
  Waveform,
  X,
} from "@phosphor-icons/react";

import { api, audioUrl } from "./api.js";
import {
  AUDIO_OUTPUT_STORAGE_KEY,
  normalizeAudioOutputs,
  parseAudioOutputPreference,
} from "./audio-output.js";
import {
  createDefaultProject,
  createLine,
  DEFAULT_PARAMS,
  DEFAULT_VOICE_API,
  formatDuration,
  hydrateProject,
  QUALITY_PRESETS,
  uid,
} from "./defaults.js";
import {
  CAPTION_PRESETS,
  EMOJI_PALETTE,
  FEATURED_EMOJI,
  insertAtSelection,
} from "./emoji-data.js";
import {
  audioFilesForLine,
  audioFilesForProject,
  duplicateLine,
  estimatedProjectSeconds,
  appendLineTake,
  removedAudioFiles,
  selectLineTake,
  splitImportedText,
  updateLine,
} from "./project-state.js";
import {
  playbackFailureMessage,
  shouldRetryWithSystemOutput,
  SILENT_PLAYBACK_PRIMER,
} from "./playback.js";
import {
  mergeVoiceLibrary,
  voiceFingerprint,
  voicePersistenceError,
  voiceToProfilePayload,
  VOICE_COLORS,
} from "./voice-library.js";
import { RecorderWorkspace } from "./features/recorder/RecorderWorkspace.jsx";
import { runLiveSegmentPipeline } from "./features/live/live-synthesis.js";
import { TrainingWorkspace } from "./features/training/TrainingWorkspace.jsx";
import {
  LEARNING_DATASET_STORAGE_KEY,
  resolveLearningDatasetId,
} from "./learning-datasets.js";
import {
  ConfirmDialog,
  IconButton,
  Modal,
  NameDialog,
  VoiceSelect,
} from "./components/StudioUI.jsx";
import { SortableList } from "./components/SortableList.jsx";

const STORAGE_KEY = "irodori-studio-project-v1";
const PLAYBACK_VOLUME_KEY = "irodori-studio-playback-volume-v2";

function formatModelSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  return bytes >= 1024 ** 3
    ? `${(bytes / (1024 ** 3)).toFixed(2)} GB`
    : `${Math.round(bytes / (1024 ** 2))} MB`;
}

function nextAvailableProjectName(projects, currentTitle = "") {
  const base = "新しい音声プロジェクト";
  const names = new Set([
    currentTitle,
    ...projects.map((item) => item.name),
  ].map((name) => String(name || "").trim()).filter(Boolean));
  if (!names.has(base)) return base;
  let index = 2;
  while (names.has(`${base} ${index}`)) index += 1;
  return `${base} ${index}`;
}

function loadPlaybackVolume() {
  const raw = localStorage.getItem(PLAYBACK_VOLUME_KEY);
  if (raw === null) return 80;
  try {
    const stored = Number(JSON.parse(raw)?.value);
    return Number.isFinite(stored) && stored >= 0 && stored <= 100 ? stored : 80;
  } catch {
    return 80;
  }
}

function loadLocalProject() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? hydrateProject(JSON.parse(raw)) : createDefaultProject();
  } catch {
    return createDefaultProject();
  }
}

function EmojiPicker({ picker, expanded, onExpandedChange, onSelect, onClose }) {
  if (!picker) return null;
  const items = expanded ? EMOJI_PALETTE : FEATURED_EMOJI;
  return (
    <div className="emoji-picker-layer" role="presentation" onMouseDown={onClose}>
      <section
        className="emoji-picker-popover"
        role="dialog"
        aria-label="演技記号を選択"
        style={picker.position}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div><Smiley size={21} /><span><strong>演技記号</strong><small>カーソル位置へ挿入</small></span></div>
          <IconButton label="閉じる" onClick={onClose}><X size={18} /></IconButton>
        </header>
        <div className="emoji-picker-grid">
          {items.map((item) => (
            <button
              type="button"
              key={item.emoji}
              className="emoji-choice"
              title={`${item.label}：${item.description}`}
              aria-label={`${item.label}：${item.description}`}
              onClick={() => onSelect(item.emoji)}
            >
              <span>{item.emoji}</span><small>{item.label}</small>
            </button>
          ))}
        </div>
        <footer>
          <span>{expanded ? `全${EMOJI_PALETTE.length}種類` : "よく使う演技"}</span>
          <button type="button" onClick={() => onExpandedChange(!expanded)}>
            {expanded ? "よく使うものだけ" : `すべて表示（${EMOJI_PALETTE.length}）`}
          </button>
        </footer>
      </section>
    </div>
  );
}

function CaptionPresetButtons({ value, onChange, disabled = false }) {
  return (
    <div className="caption-presets" aria-label="演技プリセット">
      <span>演技プリセット</span>
      <div>
        {CAPTION_PRESETS.map((preset) => (
          <button
            type="button"
            key={preset.id}
            className={value === preset.caption ? "active" : ""}
            title={preset.caption}
            aria-pressed={value === preset.caption}
            disabled={disabled}
            onClick={() => onChange(preset.caption)}
          >{preset.label}</button>
        ))}
        <button type="button" className={!value ? "active clear" : "clear"} disabled={disabled} onClick={() => onChange("")}>指定なし</button>
      </div>
    </div>
  );
}

function LabeledSlider({ label, value, min, max, step, suffix = "", onChange, disabled = false }) {
  return (
    <label className={`parameter-control ${disabled ? "disabled" : ""}`}>
      <span className="parameter-heading"><span>{label}</span><strong>{value}{suffix}</strong></span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function StatusBadge({ line }) {
  if (line.status === "queued") return <span className="status-badge queued"><Queue size={14} />待機中</span>;
  if (line.status === "running") return <span className="status-badge running"><SpinnerGap className="spin" size={14} />生成中</span>;
  if (line.status === "failed") return <span className="status-badge failed"><WarningCircle size={14} />失敗</span>;
  if (line.audioFile && line.stale) return <span className="status-badge stale"><ArrowsClockwise size={14} />要再生成</span>;
  if (line.audioFile) return <span className="status-badge ready"><Check size={14} />生成済み</span>;
  return <span className="status-badge idle">未生成</span>;
}

function PlaybackVolumeControl({ value, onChange }) {
  return (
    <label className="playback-volume">
      <SpeakerHigh size={19} aria-hidden="true" />
      <input
        type="range"
        min="0"
        max="100"
        step="1"
        value={value}
        aria-label="再生音量"
        aria-valuetext={`${value}%`}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <output>{value}%</output>
    </label>
  );
}

function AudioOutputControl({ devices, value, status, onChange }) {
  const busy = status === "requesting" || status === "switching";
  const locked = status === "locked-default" || status === "unsupported";
  return (
    <div className={`audio-output-control ${locked ? "locked" : ""}`}>
      <PlugsConnected size={19} aria-hidden="true" />
      <label>
        <select
          value={value}
          aria-label="再生音声の出力先"
          onChange={(event) => onChange(event.target.value)}
          disabled={busy || locked}
          title={locked ? "音声デバイスへのアクセスが許可されていないため、システム既定を使用します" : undefined}
        >
          {devices.map((device) => (
            <option key={device.deviceId || "system-default"} value={device.deviceId}>{device.label}</option>
          ))}
        </select>
      </label>
    </div>
  );
}

function PlaybackAudioControls({
  devices,
  outputDeviceId,
  outputStatus,
  onOutputChange,
  volume,
  onVolumeChange,
}) {
  return (
    <>
      <AudioOutputControl
        devices={devices}
        value={outputDeviceId}
        status={outputStatus}
        onChange={onOutputChange}
      />
      <PlaybackVolumeControl value={volume} onChange={onVolumeChange} />
    </>
  );
}

function App() {
  const [project, setProject] = useState(loadLocalProject);
  const [selectedLineId, setSelectedLineId] = useState(() => project.lines[0]?.id || null);
  const [view, setView] = useState("script");
  const [recorderRecording, setRecorderRecording] = useState(false);
  const [learningDatasetId, setLearningDatasetId] = useState(() => (
    localStorage.getItem(LEARNING_DATASET_STORAGE_KEY) || ""
  ));
  const [model, setModel] = useState({ loaded: false });
  const [bootstrap, setBootstrap] = useState(null);
  const [modelCatalog, setModelCatalog] = useState([]);
  const [installingModelId, setInstallingModelId] = useState("");
  const [modelSettings, setModelSettings] = useState({
    checkpoint: "",
    modelDevice: "cuda",
    modelPrecision: "bf16",
    codecDevice: "cuda",
    codecPrecision: "bf16",
  });
  const [connection, setConnection] = useState("connecting");
  const [modelLoading, setModelLoading] = useState(false);
  const [queueCount, setQueueCount] = useState(0);
  const [speakingLineId, setSpeakingLineId] = useState(null);
  const [sequenceActive, setSequenceActive] = useState(false);
  const [toast, setToast] = useState(null);
  const [activeModal, setActiveModal] = useState(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [selectedVoiceId, setSelectedVoiceId] = useState(project.voices[0]?.id || null);
  const [importText, setImportText] = useState("");
  const [savedProjects, setSavedProjects] = useState([]);
  const [newProjectName, setNewProjectName] = useState("");
  const [projectBusy, setProjectBusy] = useState(false);
  const [activeProjectName, setActiveProjectName] = useState(project.title);
  const [projectRenameTarget, setProjectRenameTarget] = useState(null);
  const [projectRenameName, setProjectRenameName] = useState("");
  const [projectDeleteTarget, setProjectDeleteTarget] = useState(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [liveInput, setLiveInput] = useState("");
  const [liveCaption, setLiveCaption] = useState("");
  const [liveItems, setLiveItems] = useState([]);
  const [liveVoiceId, setLiveVoiceId] = useState(project.voices[0]?.id || null);
  const [livePreset, setLivePreset] = useState("live");
  const [playbackVolume, setPlaybackVolume] = useState(loadPlaybackVolume);
  const [audioOutputPreference, setAudioOutputPreference] = useState(() => (
    parseAudioOutputPreference(localStorage.getItem(AUDIO_OUTPUT_STORAGE_KEY))
  ));
  const [audioOutputs, setAudioOutputs] = useState(() => normalizeAudioOutputs());
  const [audioOutputStatus, setAudioOutputStatus] = useState("checking");
  const [serverVoiceProfiles, setServerVoiceProfiles] = useState([]);
  const [voiceLibraryReady, setVoiceLibraryReady] = useState(false);
  const [voiceSaveState, setVoiceSaveState] = useState({ status: "loading", message: "ライブラリを読み込み中" });
  const [voiceNameAction, setVoiceNameAction] = useState(null);
  const [voiceNameValue, setVoiceNameValue] = useState("");
  const [voiceDeletePending, setVoiceDeletePending] = useState(false);
  const [voiceDeleteBusy, setVoiceDeleteBusy] = useState(false);
  const [emojiPicker, setEmojiPicker] = useState(null);
  const [emojiExpanded, setEmojiExpanded] = useState(false);

  const projectRef = useRef(project);
  const audioRef = useRef(null);
  const playbackResolveRef = useRef(null);
  const playbackCleanupRef = useRef(null);
  const playbackPrimedRef = useRef(false);
  const sequenceTokenRef = useRef(0);
  const generationPromisesRef = useRef(new Map());
  const liveQueueRef = useRef([]);
  const livePumpingRef = useRef(false);
  const liveGenerationTokenRef = useRef(0);
  const lineTextRefs = useRef(new Map());
  const liveTextRef = useRef(null);
  const textSelectionRef = useRef(new Map());
  const audioOutputInitializedRef = useRef(false);
  const voiceSaveTimerRef = useRef(null);
  const voiceSaveInFlightRef = useRef(false);
  const voiceSaveQueuedRef = useRef(false);
  const savedVoiceFingerprintsRef = useRef(new Map());

  const selectedLine = useMemo(
    () => project.lines.find((line) => line.id === selectedLineId) || project.lines[0] || null,
    [project.lines, selectedLineId],
  );
  const selectedVoice = useMemo(
    () => project.voices.find((voice) => voice.id === selectedVoiceId) || project.voices[0],
    [project.voices, selectedVoiceId],
  );
  const generatedCount = project.lines.filter((line) => line.audioFile && !line.stale).length;
  const staleOrMissing = project.lines.filter((line) => !line.audioFile || line.stale);
  const projectSeconds = estimatedProjectSeconds(project.lines);

  const notify = useCallback((message, tone = "normal") => {
    setToast({ message, tone, id: Date.now() });
  }, []);

  const updatePlaybackVolume = useCallback((value) => {
    setPlaybackVolume(value);
    localStorage.setItem(PLAYBACK_VOLUME_KEY, JSON.stringify({ value }));
  }, []);

  const rememberAudioOutput = useCallback((device) => {
    const preference = {
      deviceId: device?.deviceId || "",
      label: device?.label?.trim() || (device?.deviceId ? "選択した音声出力" : "システム既定"),
      configured: true,
    };
    setAudioOutputPreference(preference);
    localStorage.setItem(AUDIO_OUTPUT_STORAGE_KEY, JSON.stringify({
      deviceId: preference.deviceId,
      label: preference.label,
    }));
    return preference;
  }, []);

  const applyAudioOutput = useCallback(async (deviceId) => {
    const audio = audioRef.current;
    if (!audio || typeof audio.setSinkId !== "function") {
      if (deviceId) throw new Error("このブラウザーは音声出力先の切り替えに対応していません");
      return;
    }
    await audio.setSinkId(deviceId);
  }, []);

  const refreshAudioOutputs = useCallback(async (selectedDevice = null) => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setAudioOutputs(normalizeAudioOutputs([], selectedDevice));
      return [];
    }
    const devices = await navigator.mediaDevices.enumerateDevices();
    const normalized = normalizeAudioOutputs(devices, selectedDevice);
    setAudioOutputs(normalized);
    return normalized;
  }, []);

  const chooseAudioOutput = useCallback(async (deviceId) => {
    const device = audioOutputs.find((item) => item.deviceId === deviceId) || {
      deviceId: "",
      label: "システム既定",
    };
    setAudioOutputStatus("switching");
    try {
      await applyAudioOutput(device.deviceId);
      rememberAudioOutput(device);
      setAudioOutputStatus("ready");
      notify(`${device.label}へ再生音声を出力します`, "success");
    } catch (error) {
      await applyAudioOutput("");
      rememberAudioOutput({ deviceId: "", label: "システム既定" });
      setAudioOutputs(normalizeAudioOutputs());
      setAudioOutputStatus("locked-default");
      notify(error.message || "出力デバイスを切り替えられないため、システム既定へ戻しました", "error");
    }
  }, [applyAudioOutput, audioOutputs, notify, rememberAudioOutput]);

  useEffect(() => {
    projectRef.current = project;
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...project, updatedAt: new Date().toISOString() }));
  }, [project]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = playbackVolume / 100;
  }, [playbackVolume]);

  useEffect(() => {
    if (audioOutputInitializedRef.current) return undefined;
    audioOutputInitializedRef.current = true;
    let cancelled = false;
    const initialize = async () => {
      const supported = Boolean(
        navigator.mediaDevices?.enumerateDevices
        && navigator.mediaDevices?.getUserMedia
        && typeof audioRef.current?.setSinkId === "function"
      );
      if (!supported) {
        if (!cancelled) {
          await applyAudioOutput("");
          rememberAudioOutput({ deviceId: "", label: "システム既定" });
          setAudioOutputs(normalizeAudioOutputs());
          setAudioOutputStatus("unsupported");
        }
        return;
      }
      try {
        setAudioOutputStatus("requesting");
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        stream.getTracks().forEach((track) => track.stop());
        const devices = await refreshAudioOutputs(audioOutputPreference.deviceId ? {
          kind: "audiooutput",
          deviceId: audioOutputPreference.deviceId,
          label: audioOutputPreference.label,
        } : null);
        if (
          audioOutputPreference.deviceId
          && devices.some((device) => device.deviceId === audioOutputPreference.deviceId)
        ) {
          await applyAudioOutput(audioOutputPreference.deviceId);
        } else {
          await applyAudioOutput("");
          rememberAudioOutput({ deviceId: "", label: "システム既定" });
        }
        if (!cancelled) setAudioOutputStatus("ready");
      } catch {
        await applyAudioOutput("");
        rememberAudioOutput({ deviceId: "", label: "システム既定" });
        setAudioOutputs(normalizeAudioOutputs());
        if (!cancelled) setAudioOutputStatus("locked-default");
      }
    };
    initialize();
    return () => { cancelled = true; };
  }, [applyAudioOutput, audioOutputPreference, refreshAudioOutputs]);

  useEffect(() => {
    if (!navigator.mediaDevices?.addEventListener) return undefined;
    const handleDeviceChange = async () => {
      try {
        const devices = await refreshAudioOutputs();
        if (
          audioOutputPreference.deviceId
          && !devices.some((device) => device.deviceId === audioOutputPreference.deviceId)
        ) {
          await applyAudioOutput("");
          rememberAudioOutput({ deviceId: "", label: "システム既定" });
          notify("選択中の出力デバイスが外れたため、システム既定へ戻しました");
        }
      } catch {
        // Keep the current sink if device enumeration is temporarily unavailable.
      }
    };
    navigator.mediaDevices.addEventListener("devicechange", handleDeviceChange);
    return () => navigator.mediaDevices.removeEventListener("devicechange", handleDeviceChange);
  }, [applyAudioOutput, audioOutputPreference.deviceId, notify, refreshAudioOutputs, rememberAudioOutput]);

  useEffect(() => {
    const timer = toast ? window.setTimeout(() => setToast(null), 3600) : null;
    return () => timer && window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (learningDatasetId) localStorage.setItem(LEARNING_DATASET_STORAGE_KEY, learningDatasetId);
    else localStorage.removeItem(LEARNING_DATASET_STORAGE_KEY);
  }, [learningDatasetId]);

  useEffect(() => {
    let cancelled = false;
    api.bootstrap()
      .then((data) => {
        if (cancelled) return;
        setBootstrap(data);
        setModelCatalog(data.model_catalog || []);
        setLearningDatasetId((current) => resolveLearningDatasetId(data.recording_datasets || [], current));
        const profiles = data.voice_profiles || [];
        const mergedProject = mergeVoiceLibrary(projectRef.current, profiles);
        projectRef.current = mergedProject;
        setProject(mergedProject);
        setServerVoiceProfiles(profiles);
        savedVoiceFingerprintsRef.current = new Map(
          mergedProject.voices
            .filter((voice) => voice.apiProfileId)
            .map((voice) => [voice.id, voiceFingerprint(voice)]),
        );
        setVoiceLibraryReady(true);
        setVoiceSaveState({ status: "saved", message: "すべての変更を保存済み" });
        setModel(data.model || { loaded: false });
        const inferenceSettings = data.inference_settings || {};
        setModelSettings((current) => ({
          ...current,
          checkpoint: current.checkpoint || inferenceSettings.checkpoint || data.default_checkpoint,
          modelDevice: inferenceSettings.model_device || data.default_device || current.modelDevice,
          codecDevice: inferenceSettings.codec_device || data.default_device || current.codecDevice,
          modelPrecision: inferenceSettings.model_precision || (data.precisions?.[data.default_device]?.includes("bf16") ? "bf16" : "fp32"),
          codecPrecision: inferenceSettings.codec_precision || (data.precisions?.[data.default_device]?.includes("bf16") ? "bf16" : "fp32"),
        }));
        setConnection("online");
      })
      .catch(() => setConnection("offline"));
    return () => { cancelled = true; };
  }, []);

  const shownModelNoticeRef = useRef("");
  useEffect(() => {
    if (!model.notice || model.notice === shownModelNoticeRef.current) return;
    shownModelNoticeRef.current = model.notice;
    notify(model.notice, "error");
  }, [model.notice, notify]);

  useEffect(() => {
    if (connection !== "online") return undefined;
    const timer = window.setInterval(() => {
      api.modelStatus().then(setModel).catch(() => setConnection("offline"));
    }, 3000);
    return () => window.clearInterval(timer);
  }, [connection]);

  const mutateProject = useCallback((recipe) => {
    setProject((current) => {
      const next = typeof recipe === "function" ? recipe(current) : { ...current, ...recipe };
      return { ...next, updatedAt: new Date().toISOString() };
    });
  }, []);

  const updateSelectedVoice = useCallback((patch) => {
    if (!selectedVoiceId) return;
    mutateProject((current) => ({
      ...current,
      voices: current.voices.map((voice) => (
        voice.id === selectedVoiceId ? { ...voice, ...patch } : voice
      )),
    }));
  }, [mutateProject, selectedVoiceId]);

  const persistVoiceLibrary = useCallback(async ({ announce = false } = {}) => {
    if (!voiceLibraryReady || connection !== "online") return;
    if (voiceSaveInFlightRef.current) {
      voiceSaveQueuedRef.current = true;
      return;
    }
    voiceSaveInFlightRef.current = true;
    setVoiceSaveState({ status: "saving", message: "ボイス設定を保存中…" });
    const validationErrors = [];
    try {
      const snapshot = projectRef.current.voices;
      for (const voice of snapshot) {
        const validationError = voicePersistenceError(voice);
        if (validationError) {
          validationErrors.push(`${voice.name || "名称未設定"}: ${validationError}`);
          continue;
        }
        const fingerprint = voiceFingerprint(voice);
        if (
          voice.apiProfileId
          && savedVoiceFingerprintsRef.current.get(voice.id) === fingerprint
        ) continue;

        const profile = await api.saveVoiceProfile(voiceToProfilePayload(voice));
        savedVoiceFingerprintsRef.current.set(voice.id, fingerprint);
        setProject((current) => {
          const next = {
            ...current,
            voices: current.voices.map((item) => item.id === voice.id ? {
              ...item,
              apiProfileId: profile.profile_id,
              apiOrder: profile.display_order,
              apiSpeakerUuid: profile.speaker_uuid,
              apiStyleId: profile.style_id,
              apiEnabled: profile.enabled,
            } : item),
          };
          projectRef.current = next;
          return next;
        });
        setServerVoiceProfiles((current) => [
          ...current.filter((item) => item.profile_id !== profile.profile_id),
          profile,
        ].sort((a, b) => (a.display_order ?? a.style_id) - (b.display_order ?? b.style_id)));
      }

      if (validationErrors.length) {
        const message = validationErrors[0];
        setVoiceSaveState({ status: "error", message });
        if (announce) notify(message, "error");
      } else {
        setVoiceSaveState({ status: "saved", message: "すべての変更を保存済み" });
        if (announce) notify("ボイスライブラリを保存しました", "success");
      }
    } catch (error) {
      setVoiceSaveState({ status: "error", message: error.message });
      if (announce) notify(error.message, "error");
    } finally {
      voiceSaveInFlightRef.current = false;
      if (voiceSaveQueuedRef.current) {
        voiceSaveQueuedRef.current = false;
        window.setTimeout(() => persistVoiceLibrary(), 0);
      }
    }
  }, [connection, notify, voiceLibraryReady]);

  useEffect(() => {
    if (!voiceLibraryReady || connection !== "online") return undefined;
    window.clearTimeout(voiceSaveTimerRef.current);
    setVoiceSaveState({ status: "pending", message: "変更を保存します…" });
    voiceSaveTimerRef.current = window.setTimeout(() => persistVoiceLibrary(), 700);
    return () => window.clearTimeout(voiceSaveTimerRef.current);
  }, [connection, persistVoiceLibrary, project.voices, voiceLibraryReady]);

  const commitVoiceOrder = useCallback((voices) => {
    const ordered = voices.map((voice, index) => ({ ...voice, apiOrder: index }));
    const next = {
      ...projectRef.current,
      voices: ordered,
      updatedAt: new Date().toISOString(),
    };
    projectRef.current = next;
    setProject(next);
    window.clearTimeout(voiceSaveTimerRef.current);
    setVoiceSaveState({ status: "pending", message: "並び順を保存します…" });
    window.setTimeout(() => persistVoiceLibrary(), 0);
  }, [persistVoiceLibrary]);


  const deleteSelectedVoice = useCallback(async () => {
    if (!selectedVoice || projectRef.current.voices.length <= 1 || voiceDeleteBusy) return;
    setVoiceDeleteBusy(true);
    try {
      if (selectedVoice.apiProfileId) await api.deleteVoiceProfile(selectedVoice.apiProfileId);
      const replacementId = projectRef.current.voices.find((voice) => voice.id !== selectedVoice.id)?.id;
      savedVoiceFingerprintsRef.current.delete(selectedVoice.id);
      setServerVoiceProfiles((current) => current.filter((item) => item.profile_id !== selectedVoice.apiProfileId));
      mutateProject((current) => ({
        ...current,
        voices: current.voices.filter((voice) => voice.id !== selectedVoice.id),
        lines: current.lines.map((line) => line.voiceId === selectedVoice.id ? {
          ...line,
          voiceId: replacementId,
          stale: Boolean(line.audioFile),
        } : line),
      }));
      setSelectedVoiceId(replacementId);
      setVoiceDeletePending(false);
      notify("ボイスをライブラリから削除しました", "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setVoiceDeleteBusy(false);
    }
  }, [mutateProject, notify, selectedVoice, voiceDeleteBusy]);

  const submitVoiceName = useCallback(() => {
    const name = voiceNameValue.trim();
    if (!name || !voiceNameAction) return;
    if (voiceNameAction === "create") {
      const voice = {
        ...DEFAULT_VOICE_API,
        id: uid("voice"),
        name,
        color: VOICE_COLORS[projectRef.current.voices.length % VOICE_COLORS.length],
        sourceType: "none",
        apiOrder: projectRef.current.voices.length,
        refEmbed: "",
        refWavs: [],
        loraAdapter: "",
        defaultCaption: "",
      };
      mutateProject((current) => ({ ...current, voices: [...current.voices, voice] }));
      setSelectedVoiceId(voice.id);
      notify(`「${name}」をボイスライブラリへ追加しました`, "success");
    } else {
      updateSelectedVoice({ name });
      notify(`ボイス名を「${name}」へ変更しました`, "success");
    }
    setVoiceNameAction(null);
  }, [mutateProject, notify, updateSelectedVoice, voiceNameAction, voiceNameValue]);

  const mutateLine = useCallback((lineId, patch, invalidate = true) => {
    mutateProject((current) => ({
      ...current,
      lines: updateLine(current.lines, lineId, patch, invalidate),
    }));
  }, [mutateProject]);

  const releaseAudioFiles = useCallback(async (audioFiles, projectName = activeProjectName) => {
    const files = [...new Set(audioFiles.filter(Boolean))];
    if (!files.length || connection !== "online") return;
    try {
      await api.releaseAudio(files, projectName);
    } catch (error) {
      notify(`不要になった音声を削除できませんでした: ${error.message}`, "error");
    }
  }, [activeProjectName, connection, notify]);

  const rememberTextSelection = useCallback((key, element) => {
    textSelectionRef.current.set(key, {
      start: element.selectionStart,
      end: element.selectionEnd,
    });
  }, []);

  const openEmojiPicker = useCallback((event, target) => {
    event.stopPropagation();
    const triggerRect = event.currentTarget.getBoundingClientRect();
    const width = Math.min(410, window.innerWidth - 20);
    const left = Math.max(10, Math.min(triggerRect.right - width, window.innerWidth - width - 10));
    const showBelow = window.innerHeight - triggerRect.bottom >= 390;
    const position = showBelow
      ? { top: triggerRect.bottom + 8, left, width }
      : { bottom: window.innerHeight - triggerRect.top + 8, left, width };
    setEmojiExpanded(false);
    setEmojiPicker({ target, position });
  }, []);

  const insertEmoji = useCallback((emoji) => {
    const target = emojiPicker?.target;
    if (!target) return;
    const key = target.kind === "line" ? `line:${target.id}` : "live";
    const element = target.kind === "line" ? lineTextRefs.current.get(target.id) : liveTextRef.current;
    const selection = textSelectionRef.current.get(key) || {
      start: element?.selectionStart,
      end: element?.selectionEnd,
    };
    const source = target.kind === "line"
      ? projectRef.current.lines.find((line) => line.id === target.id)?.text || ""
      : liveTextRef.current?.value || liveInput;
    const inserted = insertAtSelection(source, emoji, selection.start, selection.end);
    if (target.kind === "line") mutateLine(target.id, { text: inserted.text });
    else setLiveInput(inserted.text);
    textSelectionRef.current.set(key, { start: inserted.caret, end: inserted.caret });
    setEmojiPicker(null);
    window.requestAnimationFrame(() => {
      const current = target.kind === "line" ? lineTextRefs.current.get(target.id) : liveTextRef.current;
      current?.focus();
      current?.setSelectionRange(inserted.caret, inserted.caret);
    });
  }, [emojiPicker, liveInput, mutateLine]);

  const buildPayload = useCallback((line, voice) => ({
    line_id: line.id,
    text: line.text,
    caption: line.caption.trim() || voice?.defaultCaption?.trim() || null,
    ref_wavs: voice?.sourceType === "reference" ? (voice.refWavs || []).filter(Boolean) : [],
    ref_embed: voice?.sourceType === "speaker" ? voice.refEmbed || null : null,
    no_ref: !voice || voice.sourceType === "none",
    lora_adapter: voice?.loraAdapter || null,
    speed: line.params.speed,
    num_steps: line.params.numSteps,
    seed: line.params.seed === "" ? null : line.params.seed,
    cfg_guidance_mode: line.params.cfgGuidanceMode,
    cfg_scale_text: line.params.cfgScaleText,
    cfg_scale_caption: line.params.cfgScaleCaption,
    cfg_scale_speaker: line.params.cfgScaleSpeaker,
    t_schedule_mode: line.params.tScheduleMode,
    sway_coeff: line.params.swayCoeff,
    truncation_factor: line.params.truncationFactor,
    speaker_kv_scale: line.params.speakerKvScale,
    speaker_kv_min_t: line.params.speakerKvMinT,
    context_kv_cache: line.params.contextKvCache,
    trim_tail: true,
  }), []);

  const waitForJob = useCallback(async (jobId, onProgress) => {
    while (true) {
      const job = await api.job(jobId);
      onProgress?.(job);
      if (job.status === "completed") return job;
      if (job.status === "failed") throw new Error(job.error || "音声生成に失敗しました");
      if (job.status === "cancelled") throw new Error("生成をキャンセルしました");
      await new Promise((resolve) => window.setTimeout(resolve, 650));
    }
  }, []);

  const submitSynthesis = useCallback(async (payload, onProgress) => {
    if (!model.loaded) throw new Error("モデルを先にロードしてください");
    setQueueCount((count) => count + 1);
    try {
      const queued = await api.synthesize(payload);
      onProgress?.(queued);
      return await waitForJob(queued.id, onProgress);
    } finally {
      setQueueCount((count) => Math.max(0, count - 1));
    }
  }, [model.loaded, waitForJob]);

  const submitProfileSynthesis = useCallback(async (profileId, payload, onProgress) => {
    if (!model.loaded) throw new Error("モデルを先にロードしてください");
    setQueueCount((count) => count + 1);
    try {
      const queued = await api.synthesizeVoiceProfile(profileId, payload);
      onProgress?.(queued);
      return await waitForJob(queued.id, onProgress);
    } finally {
      setQueueCount((count) => Math.max(0, count - 1));
    }
  }, [model.loaded, waitForJob]);

  const generateLine = useCallback(async (lineId) => {
    if (generationPromisesRef.current.has(lineId)) return generationPromisesRef.current.get(lineId);
    const promise = (async () => {
      const currentProject = projectRef.current;
      const line = currentProject.lines.find((item) => item.id === lineId);
      if (!line || !line.text.trim()) throw new Error("読み上げ文章を入力してください");
      const voice = currentProject.voices.find((item) => item.id === line.voiceId) || currentProject.voices[0];
      mutateLine(lineId, { status: "queued", error: null }, false);
      try {
        const result = await submitSynthesis(buildPayload(line, voice), (job) => {
          mutateLine(lineId, { status: job.status, jobId: job.id, error: job.error || null }, false);
        });
        const latestLine = projectRef.current.lines.find((item) => item.id === lineId);
        if (!latestLine) {
          await releaseAudioFiles([result.audio_file]);
          return result;
        }
        const projectedLine = appendLineTake([latestLine], lineId, {
          audioFile: result.audio_file,
          duration: result.duration,
          generationSeconds: result.generation_seconds,
          usedSeed: result.used_seed,
          jobId: result.id,
          stale: false,
        })[0];
        const projectedProject = {
          ...projectRef.current,
          lines: projectRef.current.lines.map((item) => (
            item.id === lineId ? projectedLine : item
          )),
        };
        const retainedAudio = new Set(audioFilesForProject(projectedProject));
        const discardedAudio = removedAudioFiles(latestLine, projectedLine)
          .filter((audioFile) => !retainedAudio.has(audioFile));
        mutateProject((current) => ({
          ...current,
          lines: appendLineTake(current.lines, lineId, {
            audioFile: result.audio_file,
            duration: result.duration,
            generationSeconds: result.generation_seconds,
            usedSeed: result.used_seed,
            jobId: result.id,
            stale: false,
          }),
        }));
        await releaseAudioFiles(discardedAudio);
        return result;
      } catch (error) {
        mutateLine(lineId, { status: "failed", error: error.message }, false);
        throw error;
      }
    })();
    generationPromisesRef.current.set(lineId, promise);
    try {
      return await promise;
    } finally {
      generationPromisesRef.current.delete(lineId);
    }
  }, [buildPayload, mutateLine, mutateProject, releaseAudioFiles, submitSynthesis]);

  const regenerateLine = useCallback(async (lineId) => {
    try {
      await generateLine(lineId);
      notify("現在の設定で新しいテイクを追加しました", "success");
    } catch (error) {
      notify(error.message, "error");
    }
  }, [generateLine, notify]);

  const stopPlayback = useCallback(() => {
    sequenceTokenRef.current += 1;
    setSequenceActive(false);
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    playbackCleanupRef.current?.();
    playbackCleanupRef.current = null;
    playbackResolveRef.current?.(false);
    playbackResolveRef.current = null;
    setSpeakingLineId(null);
  }, []);

  const primePlayback = useCallback(() => {
    if (playbackPrimedRef.current) return;
    const primer = new Audio(SILENT_PLAYBACK_PRIMER);
    const attempt = primer.play();
    if (!attempt) {
      playbackPrimedRef.current = true;
      return;
    }
    attempt.then(() => {
      playbackPrimedRef.current = true;
      primer.pause();
      primer.removeAttribute("src");
      primer.load();
    }).catch(() => {
      primer.removeAttribute("src");
      primer.load();
    });
  }, []);

  const changeLineVoice = useCallback((lineId, voiceId) => {
    if (speakingLineId === lineId) stopPlayback();
    setSelectedLineId(lineId);
    setSelectedVoiceId(voiceId);
    mutateLine(lineId, { voiceId });
  }, [mutateLine, speakingLineId, stopPlayback]);

  const chooseLineTake = useCallback((lineId, takeId) => {
    if (speakingLineId === lineId) stopPlayback();
    const line = projectRef.current.lines.find((entry) => entry.id === lineId);
    setSelectedLineId(lineId);
    if (line?.voiceId) setSelectedVoiceId(line.voiceId);
    mutateProject((current) => ({
      ...current,
      lines: selectLineTake(current.lines, lineId, takeId),
    }));
  }, [mutateProject, speakingLineId, stopPlayback]);

  const playAudio = useCallback((audioFile, lineId) => new Promise((resolve, reject) => {
    const audio = audioRef.current;
    if (!audio) return reject(new Error("Audio player unavailable"));
    playbackCleanupRef.current?.();
    playbackResolveRef.current?.(false);
    setSpeakingLineId(lineId);
    audio.src = audioUrl(audioFile);
    const cleanup = () => {
      audio.removeEventListener("ended", finish);
      audio.removeEventListener("error", fail);
    };
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      cleanup();
      setSpeakingLineId(null);
      playbackCleanupRef.current = null;
      playbackResolveRef.current = null;
      resolve(true);
    };
    const fail = (error) => {
      if (settled) return;
      settled = true;
      cleanup();
      setSpeakingLineId(null);
      playbackCleanupRef.current = null;
      playbackResolveRef.current = null;
      const cause = typeof error?.name === "string" || typeof error?.message === "string"
        ? error
        : audio.error;
      reject(new Error(playbackFailureMessage(cause)));
    };
    audio.addEventListener("ended", finish, { once: true });
    audio.addEventListener("error", fail, { once: true });
    playbackCleanupRef.current = cleanup;
    playbackResolveRef.current = resolve;
    audio.load();
    const beginPlayback = async () => {
      try {
        await audio.play();
        playbackPrimedRef.current = true;
      } catch (error) {
        if (shouldRetryWithSystemOutput(error, audio.sinkId)) {
          try {
            await applyAudioOutput("");
            rememberAudioOutput({ deviceId: "", label: "システム既定" });
            setAudioOutputs(normalizeAudioOutputs());
            setAudioOutputStatus("locked-default");
            notify("選択中の出力先で再生できないため、システム既定で再試行します", "error");
            await audio.play();
            playbackPrimedRef.current = true;
            return;
          } catch (fallbackError) {
            fail(fallbackError);
            return;
          }
        }
        fail(error);
      }
    };
    beginPlayback();
  }), [applyAudioOutput, notify, rememberAudioOutput]);

  const playLine = useCallback(async (lineId) => {
    try {
      primePlayback();
      setSelectedLineId(lineId);
      let line = projectRef.current.lines.find((item) => item.id === lineId);
      if (!line?.audioFile || line.stale) {
        const result = await generateLine(lineId);
        line = { ...line, audioFile: result.audio_file, stale: false };
      }
      await playAudio(line.audioFile, lineId);
    } catch (error) {
      notify(error.message, "error");
    }
  }, [generateLine, notify, playAudio, primePlayback]);

  const playFrom = useCallback(async (startLineId) => {
    stopPlayback();
    primePlayback();
    const token = sequenceTokenRef.current;
    setSequenceActive(true);
    const startIndex = Math.max(0, projectRef.current.lines.findIndex((line) => line.id === startLineId));
    try {
      for (let index = startIndex; index < projectRef.current.lines.length; index += 1) {
        if (sequenceTokenRef.current !== token) break;
        const id = projectRef.current.lines[index].id;
        setSelectedLineId(id);
        let line = projectRef.current.lines.find((item) => item.id === id);
        if (!line.audioFile || line.stale) {
          const result = await generateLine(id);
          line = { ...line, audioFile: result.audio_file, stale: false };
        }
        if (sequenceTokenRef.current !== token) break;
        const completed = await playAudio(line.audioFile, id);
        if (!completed) break;
      }
    } catch (error) {
      notify(error.message, "error");
    } finally {
      if (sequenceTokenRef.current === token) {
        setSequenceActive(false);
        setSpeakingLineId(null);
      }
    }
  }, [generateLine, notify, playAudio, primePlayback, stopPlayback]);

  const generateAllMissing = useCallback(async () => {
    const targets = projectRef.current.lines.filter((line) => !line.audioFile || line.stale);
    if (!targets.length) {
      notify("すべて生成済みです");
      return true;
    }
    for (let index = 0; index < targets.length; index += 1) {
      try {
        await generateLine(targets[index].id);
      } catch (error) {
        notify(`${index + 1}件目で停止しました: ${error.message}`, "error");
        return false;
      }
    }
    notify(`${targets.length}件の音声を生成しました`, "success");
    return true;
  }, [generateLine, notify]);

  const addLine = useCallback((afterId = null) => {
    const newLine = createLine({ voiceId: selectedVoiceId || projectRef.current.voices[0]?.id });
    mutateProject((current) => {
      const index = afterId ? current.lines.findIndex((line) => line.id === afterId) + 1 : current.lines.length;
      const lines = [...current.lines];
      lines.splice(Math.max(0, index), 0, newLine);
      return { ...current, lines };
    });
    setSelectedLineId(newLine.id);
  }, [mutateProject, selectedVoiceId]);

  const removeLine = useCallback((lineId) => {
    const currentProject = projectRef.current;
    const removedLine = currentProject.lines.find((line) => line.id === lineId);
    if (!removedLine || currentProject.lines.length === 1) return;
    if (removedLine.jobId && ["queued", "running"].includes(removedLine.status)) {
      api.cancelJob(removedLine.jobId).catch(() => {});
    }
    const remainingProject = {
      ...currentProject,
      lines: currentProject.lines.filter((line) => line.id !== lineId),
    };
    const retainedAudio = new Set(audioFilesForProject(remainingProject));
    const releasedAudio = audioFilesForLine(removedLine)
      .filter((audioFile) => !retainedAudio.has(audioFile));
    mutateProject((current) => {
      const index = current.lines.findIndex((line) => line.id === lineId);
      const lines = current.lines.filter((line) => line.id !== lineId);
      if (selectedLineId === lineId) setSelectedLineId(lines[Math.max(0, index - 1)]?.id || null);
      return { ...current, lines };
    });
    releaseAudioFiles(releasedAudio);
  }, [mutateProject, releaseAudioFiles, selectedLineId]);

  const handleLoadModel = useCallback(async () => {
    setModelLoading(true);
    try {
      const loaded = await api.loadModel({
        checkpoint: modelSettings.checkpoint,
        model_device: modelSettings.modelDevice,
        model_precision: modelSettings.modelPrecision,
        codec_device: modelSettings.codecDevice,
        codec_precision: modelSettings.codecPrecision,
        compile_model: false,
        compile_dynamic: false,
      });
      setModel(loaded);
      setConnection("online");
      notify(`${loaded.name || "モデル"}をロードしました`, "success");
      setActiveModal(null);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setModelLoading(false);
    }
  }, [modelSettings, notify]);

  const selectCatalogModel = useCallback((entry) => {
    if (!entry.installed && entry.installable) return;
    setModelSettings((current) => ({
      ...current,
      checkpoint: entry.source,
      modelPrecision: entry.quantization ? "bf16" : current.modelPrecision,
    }));
  }, []);

  const handleInstallModel = useCallback(async (entry) => {
    setInstallingModelId(entry.id);
    try {
      let job = await api.installModel(entry.id);
      while (!["completed", "failed"].includes(job.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 900));
        job = await api.modelInstall(job.id);
      }
      if (job.status === "failed") throw new Error(job.error || "モデルを導入できませんでした");
      const catalog = await api.models();
      setModelCatalog(catalog);
      const installed = catalog.find((item) => item.id === entry.id);
      if (installed) selectCatalogModel(installed);
      notify(`${entry.name}を導入しました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setInstallingModelId("");
    }
  }, [notify, selectCatalogModel]);

  const choosePath = useCallback(async (kind, multiple, onPaths) => {
    try {
      const result = await api.dialog(kind, multiple);
      if (result.paths.length) onPaths(result.paths);
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify]);

  const activateProject = useCallback((rawProject, storageName = null) => {
    const loaded = mergeVoiceLibrary(hydrateProject(rawProject), serverVoiceProfiles);
    stopPlayback();
    projectRef.current = loaded;
    setProject(loaded);
    setSelectedLineId(loaded.lines[0]?.id || null);
    setSelectedVoiceId(loaded.voices[0]?.id || null);
    setLiveVoiceId(loaded.voices[0]?.id || null);
    setActiveProjectName(storageName);
  }, [serverVoiceProfiles, stopPlayback]);

  const persistCurrentProject = useCallback(async () => {
    const current = projectRef.current;
    const title = String(current.title || "").trim();
    if (!title) throw new Error("プロジェクト名を入力してください");
    const storageName = activeProjectName || title;
    const normalized = { ...current, title, updatedAt: new Date().toISOString() };
    const result = await api.saveProject(storageName, normalized);
    projectRef.current = normalized;
    setProject(normalized);
    setActiveProjectName(result.name);
    return result;
  }, [activeProjectName]);

  const saveProject = useCallback(async () => {
    try {
      await persistCurrentProject();
      notify("プロジェクトを保存しました", "success");
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify, persistCurrentProject]);

  const refreshProjects = useCallback(async () => {
    const projects = await api.projects();
    setSavedProjects(projects);
    return projects;
  }, []);

  const openProjectsModal = useCallback(async () => {
    setActiveModal("projects");
    setProjectBusy(true);
    try {
      const projects = await refreshProjects();
      setNewProjectName(nextAvailableProjectName(projects, projectRef.current.title));
    } catch (error) {
      setSavedProjects([]);
      setNewProjectName(nextAvailableProjectName([], projectRef.current.title));
      notify(error.message, "error");
    } finally {
      setProjectBusy(false);
    }
  }, [notify, refreshProjects]);

  const createProject = useCallback(async () => {
    const name = newProjectName.trim();
    if (!name) {
      notify("新しいプロジェクトの名前を入力してください", "error");
      return;
    }
    setProjectBusy(true);
    try {
      await persistCurrentProject();
      const fresh = { ...createDefaultProject(), title: name, updatedAt: new Date().toISOString() };
      const result = await api.createProject(name, fresh);
      activateProject(fresh, result.name);
      setActiveModal(null);
      notify(`「${name}」を作成しました`, "success");
    } catch (error) {
      notify(error.message, "error");
      try {
        const projects = await refreshProjects();
        setNewProjectName(nextAvailableProjectName(projects, projectRef.current.title));
      } catch {
        // Keep the entered name when the project list is temporarily unavailable.
      }
    } finally {
      setProjectBusy(false);
    }
  }, [activateProject, newProjectName, notify, persistCurrentProject, refreshProjects]);

  const loadSavedProject = useCallback(async (saved) => {
    if (saved.storage_name === activeProjectName) {
      setActiveModal(null);
      return;
    }
    setProjectBusy(true);
    try {
      await persistCurrentProject();
      const loaded = await api.loadProject(saved.storage_name);
      activateProject(loaded, saved.storage_name);
      setActiveModal(null);
      notify(`「${saved.name}」を開きました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setProjectBusy(false);
    }
  }, [activateProject, activeProjectName, notify, persistCurrentProject]);

  const deleteSavedProject = useCallback(async (saved) => {
    setProjectBusy(true);
    try {
      const activeAudioFiles = saved.storage_name === activeProjectName
        ? audioFilesForProject(projectRef.current)
        : [];
      await api.deleteProject(saved.storage_name);
      await releaseAudioFiles(activeAudioFiles, null);
      const remaining = await refreshProjects();
      if (saved.storage_name === activeProjectName) {
        const fresh = createDefaultProject();
        activateProject(fresh, null);
      }
      setNewProjectName(nextAvailableProjectName(remaining, projectRef.current.title));
      setProjectDeleteTarget(null);
      notify(`「${saved.name}」を削除しました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setProjectBusy(false);
    }
  }, [activateProject, activeProjectName, notify, refreshProjects, releaseAudioFiles]);

  const openProjectRename = useCallback((saved = null) => {
    const target = saved || {
      name: projectRef.current.title,
      storage_name: activeProjectName,
    };
    setProjectRenameTarget(target);
    setProjectRenameName(target.name || "");
  }, [activeProjectName]);

  const renameProject = useCallback(async () => {
    const name = projectRenameName.trim();
    if (!projectRenameTarget || !name || projectBusy) return;
    setProjectBusy(true);
    try {
      const isCurrent = projectRenameTarget.storage_name === activeProjectName
        || (!projectRenameTarget.storage_name && !activeProjectName);
      if (isCurrent && activeProjectName) await persistCurrentProject();
      if (projectRenameTarget.storage_name) {
        const result = await api.renameProject(projectRenameTarget.storage_name, name);
        if (isCurrent) {
          const next = { ...projectRef.current, title: name };
          projectRef.current = next;
          setProject(next);
          setActiveProjectName(result.name);
        }
      } else {
        const next = { ...projectRef.current, title: name, updatedAt: new Date().toISOString() };
        const result = await api.saveProject(name, next);
        projectRef.current = next;
        setProject(next);
        setActiveProjectName(result.name);
      }
      await refreshProjects();
      setProjectRenameTarget(null);
      notify(`プロジェクト名を「${name}」へ変更しました`, "success");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setProjectBusy(false);
    }
  }, [activeProjectName, notify, persistCurrentProject, projectBusy, projectRenameName, projectRenameTarget, refreshProjects]);

  const exportProduction = useCallback(async () => {
    if (staleOrMissing.length) {
      notify("未生成または変更済みの行を先に生成してください", "error");
      return;
    }
    setExportBusy(true);
    try {
      const { blob, filename } = await api.exportProject({
        project_name: project.title,
        segments: project.lines.map((line) => {
          const voice = project.voices.find((item) => item.id === line.voiceId);
          return {
            id: line.id,
            text: line.text,
            caption: line.caption,
            voice_name: voice?.name || "",
            audio_file: line.audioFile,
            seed: line.usedSeed,
          };
        }),
        project,
        gap_ms: project.exportSettings.gapMs,
        include_master: project.exportSettings.includeMaster,
        include_srt: project.exportSettings.includeSrt,
        include_vtt: project.exportSettings.includeVtt,
        include_csv: project.exportSettings.includeCsv,
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify("制作パッケージを書き出しました", "success");
      setActiveModal(null);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setExportBusy(false);
    }
  }, [notify, project, staleOrMissing.length]);

  const enqueueLive = useCallback((text) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    primePlayback();
    const item = {
      id: uid("live"),
      text: trimmed,
      caption: liveCaption,
      voiceId: liveVoiceId,
      preset: livePreset,
      status: "queued",
      audioFile: null,
      audioFiles: [],
      duration: null,
      segmentsReady: 0,
      segmentsTotal: 1,
      error: null,
    };
    setLiveItems((current) => [item, ...current]);
    liveQueueRef.current.push(item);
    setLiveInput("");

    if (!livePumpingRef.current) {
      livePumpingRef.current = true;
      (async () => {
        while (liveQueueRef.current.length) {
          const next = liveQueueRef.current.shift();
          const voice = projectRef.current.voices.find((entry) => entry.id === next.voiceId) || projectRef.current.voices[0];
          const generationToken = liveGenerationTokenRef.current;
          const generatedAudioFiles = [];
          try {
            const plan = await api.synthesisPlan(next.text);
            const segments = plan.segments || [];
            if (!segments.length) throw new Error("読み上げ文章を入力してください");
            setLiveItems((current) => current.map((entry) => entry.id === next.id ? {
              ...entry,
              status: "running",
              segmentsTotal: segments.length,
            } : entry));

            const baseSeed = voice?.apiSeed === "" || voice?.apiSeed == null
              ? null
              : Number(voice.apiSeed);
            let totalDuration = 0;
            let playbackError = null;
            let autoplay = true;

            const startSegment = (index) => {
              const segmentSeed = baseSeed == null ? null : baseSeed + index;
              const onProgress = (job) => {
                if (liveGenerationTokenRef.current !== generationToken) return;
                setLiveItems((current) => current.map((entry) => entry.id === next.id ? {
                  ...entry,
                  status: "running",
                } : entry));
              };
              if (voice?.apiProfileId) {
                return submitProfileSynthesis(voice.apiProfileId, {
                  line_id: `${next.id}-${index + 1}`,
                  text: segments[index],
                  caption: next.caption,
                  num_steps: QUALITY_PRESETS[next.preset].numSteps,
                  seed: segmentSeed,
                }, onProgress);
              }
              const line = createLine({
                id: `${next.id}-${index + 1}`,
                text: segments[index],
                caption: next.caption,
                voiceId: next.voiceId,
                params: {
                  ...DEFAULT_PARAMS,
                  quality: next.preset,
                  numSteps: QUALITY_PRESETS[next.preset].numSteps,
                  seed: segmentSeed,
                },
              });
              return submitSynthesis(buildPayload(line, voice), onProgress);
            };

            await runLiveSegmentPipeline({
              segmentCount: segments.length,
              produce: async (index) => {
                if (liveGenerationTokenRef.current !== generationToken) throw new Error("生成をキャンセルしました");
                const result = await startSegment(index);
                generatedAudioFiles.push(result.audio_file);
                totalDuration += Number(result.duration || 0);
                setLiveItems((current) => current.map((entry) => entry.id === next.id ? {
                  ...entry,
                  status: "running",
                  audioFile: generatedAudioFiles[0],
                  audioFiles: [...generatedAudioFiles],
                  duration: totalDuration,
                  segmentsReady: index + 1,
                } : entry));
                return result;
              },
              consume: async (result) => {
                if (autoplay && liveGenerationTokenRef.current === generationToken) {
                  try {
                    const completed = await playAudio(result.audio_file, next.id);
                    if (!completed) autoplay = false;
                  } catch (playError) {
                    playbackError = playError.message;
                    autoplay = false;
                  }
                }
              },
            });

            if (liveGenerationTokenRef.current !== generationToken) throw new Error("生成をキャンセルしました");
            setLiveItems((current) => current.map((entry) => entry.id === next.id ? {
              ...entry,
              status: "ready",
              audioFile: generatedAudioFiles[0],
              audioFiles: [...generatedAudioFiles],
              duration: totalDuration,
              segmentsReady: segments.length,
              error: playbackError,
            } : entry));
            if (playbackError) notify(`${playbackError} 発話履歴から再生できます。`, "error");
          } catch (error) {
            await releaseAudioFiles(generatedAudioFiles);
            const cancelled = liveGenerationTokenRef.current !== generationToken;
            setLiveItems((current) => current.map((entry) => entry.id === next.id ? {
              ...entry,
              status: cancelled ? "cancelled" : "failed",
              audioFile: null,
              audioFiles: [],
              error: cancelled ? null : error.message,
            } : entry));
            if (!cancelled) notify(error.message, "error");
          }
        }
        livePumpingRef.current = false;
      })();
    }
  }, [buildPayload, liveCaption, livePreset, liveVoiceId, notify, playAudio, primePlayback, releaseAudioFiles, submitProfileSynthesis, submitSynthesis]);

  const replayLiveItem = useCallback(async (item) => {
    primePlayback();
    const audioFiles = item.audioFiles?.length ? item.audioFiles : [item.audioFile].filter(Boolean);
    try {
      for (const audioFile of audioFiles) {
        const completed = await playAudio(audioFile, item.id);
        if (!completed) break;
      }
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify, playAudio, primePlayback]);

  const stopLive = useCallback(async () => {
    liveGenerationTokenRef.current += 1;
    liveQueueRef.current = [];
    stopPlayback();
    try { await api.cancelAll(); } catch { /* Local playback still stops if cancellation fails. */ }
    setLiveItems((current) => current.map((item) => ["queued", "running"].includes(item.status) ? { ...item, status: "cancelled" } : item));
  }, [stopPlayback]);

  useEffect(() => {
    const onKeyDown = (event) => {
      const editing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
      if (event.key === "Escape" && emojiPicker) {
        event.preventDefault();
        setEmojiPicker(null);
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        saveProject();
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && selectedLine) {
        event.preventDefault();
        if (event.shiftKey) playFrom(selectedLine.id);
        else generateLine(selectedLine.id).catch((error) => notify(error.message, "error"));
      }
      if (!editing && event.key === "Escape") stopPlayback();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [emojiPicker, generateLine, notify, playFrom, saveProject, selectedLine, stopPlayback]);

  const updateSelectedParams = (patch) => {
    if (!selectedLine) return;
    mutateLine(selectedLine.id, { params: { ...selectedLine.params, ...patch } });
  };

  const setQuality = (quality) => {
    const preset = QUALITY_PRESETS[quality];
    updateSelectedParams({ quality, numSteps: preset.numSteps });
  };

  const speakingLine = project.lines.find((line) => line.id === speakingLineId) || liveItems.find((line) => line.id === speakingLineId);

  const renderScriptLine = (line, index, sortable = {}) => {
    const voice = project.voices.find((item) => item.id === line.voiceId) || project.voices[0];
    const selected = selectedLineId === line.id;
    const speaking = speakingLineId === line.id;
    const overlay = Boolean(sortable.overlay);
    return (
      <article
        {...(sortable.containerProps || {})}
        className={`script-line ${selected ? "selected" : ""} ${speaking ? "speaking" : ""} ${sortable.isDragging ? "sortable-source-hidden" : ""} ${sortable.isSorting ? "sorting" : ""} ${overlay ? "sortable-overlay-item" : ""}`}
        aria-hidden={overlay || undefined}
        onClick={overlay ? undefined : () => { setSelectedLineId(line.id); setSelectedVoiceId(voice.id); }}
      >
        <button
          {...(sortable.handleProps || {})}
          className="drag-handle"
          type="button"
          aria-label={`${index + 1}行目を並び替え`}
          title="ドラッグして並び替え"
          tabIndex={overlay ? -1 : undefined}
        ><DotsSixVertical size={20} /></button>
        <span className="line-number">{speaking ? <SpeakerHigh size={21} weight="fill" /> : index + 1}</span>
        <div className="line-content">
          <div className="text-editor-shell">
            <textarea
              ref={overlay ? undefined : (node) => {
                if (node) lineTextRefs.current.set(line.id, node);
                else lineTextRefs.current.delete(line.id);
              }}
              value={line.text}
              rows={Math.max(1, Math.min(3, Math.ceil((line.text.length || 1) / 42)))}
              placeholder="読み上げる文章を入力"
              readOnly={overlay}
              tabIndex={overlay ? -1 : undefined}
              onChange={(event) => mutateLine(line.id, { text: event.target.value })}
              onSelect={(event) => rememberTextSelection(`line:${line.id}`, event.currentTarget)}
              onKeyUp={(event) => rememberTextSelection(`line:${line.id}`, event.currentTarget)}
              onClick={(event) => {
                event.stopPropagation();
                rememberTextSelection(`line:${line.id}`, event.currentTarget);
              }}
            />
            <button
              type="button"
              className="emoji-trigger"
              title="演技記号を挿入"
              aria-label="演技記号を挿入"
              aria-haspopup="dialog"
              tabIndex={overlay ? -1 : undefined}
              onMouseDown={(event) => event.preventDefault()}
              onClick={(event) => openEmojiPicker(event, { kind: "line", id: line.id })}
            ><Smiley size={21} /></button>
          </div>
          <div className="line-meta">
            <label
              className="voice-chip voice-chip-select"
              title="この行のボイスを変更"
              onClick={(event) => event.stopPropagation()}
              onPointerDown={(event) => event.stopPropagation()}
            >
              <i style={{ backgroundColor: voice.color }} />
              <select
                value={voice.id}
                aria-label={`${index + 1}行目のボイス`}
                disabled={line.status === "running"}
                tabIndex={overlay ? -1 : undefined}
                onChange={(event) => changeLineVoice(line.id, event.target.value)}
              >
                {project.voices.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
              <CaretDown size={12} aria-hidden="true" />
            </label>
            <StatusBadge line={line} />
            {(line.takes || []).length > 1 && <div className="take-selector" role="group" aria-label={`${index + 1}行目のテイク`}>
              <span>テイク</span>
              {(line.takes || []).map((take, takeIndex) => (
                <button
                  type="button"
                  key={take.id}
                  className={`${take.id === line.selectedTakeId ? "active" : ""} ${take.stale ? "stale" : ""}`}
                  aria-label={`テイク${takeIndex + 1}${take.stale ? "、旧設定" : ""}`}
                  aria-pressed={take.id === line.selectedTakeId}
                  title={`テイク${takeIndex + 1} · ${formatDuration(take.duration)}${take.stale ? " · 変更前の設定" : ""}`}
                  disabled={line.status === "running"}
                  tabIndex={overlay ? -1 : undefined}
                  onClick={(event) => {
                    event.stopPropagation();
                    chooseLineTake(line.id, take.id);
                  }}
                >{takeIndex + 1}</button>
              ))}
            </div>}
            {line.duration && <span>{formatDuration(line.duration)}</span>}
            {line.generationSeconds && <span>生成 {line.generationSeconds.toFixed(2)}秒</span>}
            {line.error && <span className="line-error">{line.error}</span>}
          </div>
        </div>
        <div className="line-actions">
          <IconButton label="複製" tabIndex={overlay ? -1 : undefined} onClick={(event) => { event.stopPropagation(); mutateProject((current) => ({ ...current, lines: duplicateLine(current.lines, line.id) })); }}><Copy size={18} /></IconButton>
          <IconButton label="現在の設定で新しいテイクを作る" tabIndex={overlay ? -1 : undefined} onClick={(event) => { event.stopPropagation(); regenerateLine(line.id); }} disabled={!model.loaded || line.status === "running"}><ArrowsClockwise size={18} /></IconButton>
          <IconButton label={line.audioFile && !line.stale ? "再生" : "生成して再生"} tabIndex={overlay ? -1 : undefined} tone="play" onClick={(event) => { event.stopPropagation(); playLine(line.id); }} disabled={!model.loaded || line.status === "running"}>
            {line.status === "running" ? <SpinnerGap className="spin" size={19} /> : <Play size={19} weight="fill" />}
          </IconButton>
          <a className={`icon-button quiet ${line.audioFile ? "" : "disabled"}`} tabIndex={overlay ? -1 : undefined} title="WAVを保存" aria-label="WAVを保存" href={line.audioFile ? audioUrl(line.audioFile) : undefined} download><DownloadSimple size={19} /></a>
          <IconButton label="削除" tabIndex={overlay ? -1 : undefined} tone="danger" onClick={(event) => { event.stopPropagation(); removeLine(line.id); }} disabled={project.lines.length === 1}><Trash size={18} /></IconButton>
        </div>
      </article>
    );
  };

  const renderVoiceListItem = (voice, _index, sortable = {}) => {
    const overlay = Boolean(sortable.overlay);
    return (
      <div
        {...(sortable.containerProps || {})}
        className={`voice-list-item ${selectedVoiceId === voice.id ? "active" : ""} ${sortable.isDragging ? "sortable-source-hidden" : ""} ${sortable.isSorting ? "sorting" : ""} ${overlay ? "sortable-overlay-item" : ""}`}
        aria-hidden={overlay || undefined}
      >
        <button
          {...(sortable.handleProps || {})}
          type="button"
          className="voice-drag-handle"
          aria-label={`${voice.name}を並び替え`}
          title="ドラッグして並び替え"
          tabIndex={overlay ? -1 : undefined}
        ><DotsSixVertical size={19} /></button>
        <button
          type="button"
          className="voice-list-select"
          aria-pressed={selectedVoiceId === voice.id}
          tabIndex={overlay ? -1 : undefined}
          onClick={overlay ? undefined : () => setSelectedVoiceId(voice.id)}
        >
          <i style={{ backgroundColor: voice.color }} />
          <span>
            <strong>{voice.name}</strong>
            <small>{voice.apiEnabled ? `API · ID ${voice.apiStyleId}` : voice.sourceType === "speaker" ? "Speaker Inversion" : voice.sourceType === "reference" ? "参照音声" : "参照なし"}</small>
          </span>
        </button>
      </div>
    );
  };

  return (
    <div className="app-shell">
      <audio ref={audioRef} preload="auto" />
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-mark"><Waveform size={25} weight="bold" /></span>
          <div><strong>Irodori Studio</strong><small>LOCAL PRODUCTION CONSOLE</small></div>
        </div>
        <nav className="view-switcher" aria-label="制作モード">
          <button className={view === "script" ? "active" : ""} onClick={() => setView("script")} disabled={recorderRecording}><FileText size={18} />台本制作</button>
          <button className={view === "live" ? "active" : ""} onClick={() => setView("live")} disabled={recorderRecording}><Broadcast size={18} />配信</button>
          <button className={view === "recorder" ? "active" : ""} onClick={() => setView("recorder")}><MicrophoneStage size={18} />録音</button>
          <button className={view === "training" ? "active" : ""} onClick={() => setView("training")} disabled={recorderRecording}><GraduationCap size={18} />学習</button>
        </nav>
        <div className="top-actions">
          {view === "recorder" ? <span className="recorder-local-pill"><HardDrive size={18} /><span><small>RECORDING DATASETS</small><strong>{recorderRecording ? "録音中 · 画面を固定" : "Studioに自動保存"}</strong></span></span> : view === "training" ? <span className="recorder-local-pill"><GraduationCap size={18} /><span><small>TRAINING WORKSPACE</small><strong>モデルをStudioに保存</strong></span></span> : <>
            <button className={`model-pill ${model.loaded ? "loaded" : ""}`} onClick={() => setActiveModal("model")}>
              <span className="model-state" />
              <span><small>{connection === "offline" ? "API OFFLINE" : model.loaded ? `MODEL READY${model.quantization?.label ? ` · ${model.quantization.label}` : ""}` : "MODEL OFF"}</small><strong>{model.loaded ? model.name : "モデルをロード"}</strong></span>
              <CaretDown size={16} />
            </button>
            <span className="queue-indicator"><Queue size={18} /><strong>{queueCount}</strong></span>
          </>}
          {(view === "script" || view === "live") && <>
            <IconButton label="プロジェクト管理" onClick={openProjectsModal}><FolderOpen size={20} /></IconButton>
            <IconButton label="プロジェクトを保存" onClick={saveProject}><FloppyDisk size={20} /></IconButton>
          </>}
          <IconButton className="global-voice-button" label="ボイスライブラリ" onClick={() => setActiveModal("voices")}><UserSound size={21} /></IconButton>
        </div>
      </header>

      {view === "script" ? (
        <main className="workspace">
          <aside className="script-sidebar">
            <div className="project-heading">
              <label>PROJECT</label>
              <div className="project-title-row">
                <strong>{project.title}</strong>
                <IconButton label="プロジェクト名を変更" onClick={() => openProjectRename()}><PencilSimple size={17} /></IconButton>
              </div>
              <div className="project-metrics">
                <span><ListNumbers size={17} />{project.lines.length}行</span>
                <span><Clock size={17} />{formatDuration(projectSeconds)}</span>
                <span><Check size={17} />{generatedCount}/{project.lines.length}</span>
              </div>
            </div>
            <div className="sidebar-actions">
              <button onClick={() => setActiveModal("import")}><UploadSimple size={18} />文章をまとめて追加</button>
            </div>
            <div className="sidebar-voice">
              <span>既定のボイス</span>
              <VoiceSelect voices={project.voices} value={selectedVoiceId} onChange={setSelectedVoiceId} label="台本へ追加する既定のボイス" />
            </div>
          </aside>

          <section className="script-stage">
            <div className="stage-toolbar">
              <div>
                <span className="eyebrow">SCRIPT TIMELINE</span>
                <h1>読み上げ台本</h1>
              </div>
              <div className="transport-controls">
                <PlaybackAudioControls
                  devices={audioOutputs}
                  outputDeviceId={audioOutputPreference.deviceId}
                  outputStatus={audioOutputStatus}
                  onOutputChange={chooseAudioOutput}
                  volume={playbackVolume}
                  onVolumeChange={updatePlaybackVolume}
                />
                <button className="secondary-button" onClick={generateAllMissing} disabled={!model.loaded || queueCount > 0}><MagicWand size={19} />未生成を作る</button>
                {sequenceActive || speakingLineId ? (
                  <button className="stop-button" onClick={stopPlayback}><Stop size={19} weight="fill" />停止</button>
                ) : (
                  <button className="play-from-button" onClick={() => selectedLine && playFrom(selectedLine.id)} disabled={!selectedLine}><Play size={19} weight="fill" />ここから連続再生</button>
                )}
              </div>
            </div>

            <div className="line-list">
              <SortableList
                items={project.lines}
                label="読み上げ台本"
                onReorder={(lines) => mutateProject((current) => ({ ...current, lines }))}
                renderItem={renderScriptLine}
                renderOverlay={(line, index) => renderScriptLine(line, index, { overlay: true })}
              />
              <button className="add-line-card" onClick={() => addLine(selectedLineId)}><Plus size={19} />選択行の下に追加</button>
            </div>
            <IconButton
              className="script-export-fab"
              label="制作ファイルを書き出す"
              tone="primary"
              onClick={() => setActiveModal("export")}
            >
              <Export size={23} />
            </IconButton>
          </section>
        </main>
      ) : view === "live" ? (
        <main className="live-workspace">
          <section className="live-console">
            <div className="live-header">
              <div><span className="eyebrow">LOW-LATENCY QUEUE</span><h1>配信</h1><p>入力した文章を順番に生成し、完成したものから自動再生します。</p></div>
              <div className="live-header-actions">
                <div className="live-audio-controls">
                  <PlaybackAudioControls
                    devices={audioOutputs}
                    outputDeviceId={audioOutputPreference.deviceId}
                    outputStatus={audioOutputStatus}
                    onOutputChange={chooseAudioOutput}
                    volume={playbackVolume}
                    onVolumeChange={updatePlaybackVolume}
                  />
                </div>
                <button className="stop-button" onClick={stopLive}><Stop size={19} weight="fill" />発話を止める</button>
              </div>
            </div>
            <div className="live-composer">
              <div className="live-options">
                <div className="live-voice-option"><span>ボイス</span><VoiceSelect voices={project.voices} value={liveVoiceId} onChange={setLiveVoiceId} label="配信に使用するボイス" /></div>
                <div className="preset-tabs">{Object.entries(QUALITY_PRESETS).slice(0, 3).map(([key, preset]) => <button key={key} className={livePreset === key ? "active" : ""} onClick={() => setLivePreset(key)}>{preset.label}<small>{preset.numSteps} steps</small></button>)}</div>
              </div>
              <div className="live-text-editor">
                <textarea
                  ref={liveTextRef}
                  value={liveInput}
                  onChange={(event) => setLiveInput(event.target.value)}
                  onSelect={(event) => rememberTextSelection("live", event.currentTarget)}
                  onKeyUp={(event) => rememberTextSelection("live", event.currentTarget)}
                  onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); enqueueLive(liveInput); } }}
                  placeholder="今すぐ読ませる文章を入力。Enterでキューへ、Shift+Enterで改行。"
                  autoFocus
                />
                <button
                  type="button"
                  className="emoji-trigger"
                  title="演技記号を挿入"
                  aria-label="演技記号を挿入"
                  aria-haspopup="dialog"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={(event) => openEmojiPicker(event, { kind: "live" })}
                ><Smiley size={23} /></button>
              </div>
              <CaptionPresetButtons value={liveCaption} onChange={setLiveCaption} disabled={!model.use_caption_condition} />
              <div className="live-submit-row"><span><Lightning size={18} weight="fill" />Enterで即時発話キューへ追加</span><button onClick={() => enqueueLive(liveInput)} disabled={!liveInput.trim() || !model.loaded}><MicrophoneStage size={20} />読み上げる</button></div>
            </div>
            <div className="live-history">
              <header><strong>発話履歴</strong><span>{liveItems.length}件</span></header>
              {liveItems.length === 0 ? <div className="empty-live"><Broadcast size={32} /><strong>発話キューは空です</strong><span>上の入力欄から最初のメッセージを送ってください。</span></div> : liveItems.map((item) => (
                <article key={item.id} className={speakingLineId === item.id ? "speaking" : ""}>
                  <span className="live-state">{item.status === "running" ? <SpinnerGap className="spin" size={18} /> : item.status === "ready" ? <Check size={18} /> : item.status === "failed" ? <WarningCircle size={18} /> : <Queue size={18} />}</span>
                  <div><strong>{item.text}</strong><small>{QUALITY_PRESETS[item.preset]?.label} · {formatDuration(item.duration)}{item.segmentsTotal > 1 ? ` · ${item.segmentsReady}/${item.segmentsTotal}` : ""}</small>{item.error && <small className="line-error">{item.error}</small>}</div>
                  {item.audioFile && <IconButton label="もう一度再生" onClick={() => replayLiveItem(item)}><Play size={18} weight="fill" /></IconButton>}
                </article>
              ))}
            </div>
          </section>
          <aside className="live-side-panel">
            <div className="on-air-card"><span className="on-air-dot" /><small>LOCAL OUTPUT</small><strong>{speakingLine ? "NOW SPEAKING" : "STANDBY"}</strong><p>{speakingLine?.text || "発話待機中です"}</p></div>
            <div className="hotkey-card"><h3>配信用ショートカット</h3><dl><div><dt>Enter</dt><dd>キューへ追加</dd></div><div><dt>Shift + Enter</dt><dd>改行</dd></div><div><dt>Esc</dt><dd>再生停止</dd></div></dl></div>
            <div className="system-card"><h3>エンジン</h3><p><Cpu size={18} />{model.cuda?.name || model.model_device || "未接続"}</p><p><HardDrive size={18} />{model.cuda ? `${model.cuda.allocated_gb} GB 使用中` : "GPU情報なし"}</p><p><Queue size={18} />{queueCount}件を処理中</p></div>
          </aside>
        </main>
      ) : view === "recorder" ? (
        <RecorderWorkspace
          notify={notify}
          onRecordingStateChange={setRecorderRecording}
          playbackVolume={playbackVolume}
          outputDeviceId={audioOutputPreference.deviceId}
          datasetId={learningDatasetId}
          onDatasetIdChange={setLearningDatasetId}
        />
      ) : (
        <TrainingWorkspace
          bootstrap={bootstrap}
          notify={notify}
          onModelUnloaded={() => setModel({ loaded: false })}
          onOpenRecorder={() => setView("recorder")}
          datasetId={learningDatasetId}
          onDatasetIdChange={setLearningDatasetId}
          playbackVolume={playbackVolume}
          outputDeviceId={audioOutputPreference.deviceId}
        />
      )}

      {view === "script" && selectedLine && (
        <section className="inspector">
          <div className="inspector-title">
            <div><SlidersHorizontal size={19} /><span>選択中の行を調整</span><strong>{project.lines.findIndex((line) => line.id === selectedLine.id) + 1}行目</strong></div>
            <div className="quality-presets">{Object.entries(QUALITY_PRESETS).map(([key, preset]) => <button key={key} className={selectedLine.params.quality === key ? "active" : ""} title={preset.description} onClick={() => setQuality(key)}><span>{preset.short}</span>{preset.label}</button>)}</div>
          </div>
          <div className="parameter-grid">
            <LabeledSlider label="話速" value={selectedLine.params.speed.toFixed(2)} min={0.5} max={1.5} step={0.05} onChange={(value) => updateSelectedParams({ speed: value })} />
            <LabeledSlider label="ステップ数" value={selectedLine.params.numSteps} min={1} max={80} step={1} onChange={(value) => updateSelectedParams({ numSteps: value, quality: "custom" })} />
            <LabeledSlider label="テキスト忠実度 (CFG)" value={selectedLine.params.cfgScaleText.toFixed(1)} min={0} max={10} step={0.1} onChange={(value) => updateSelectedParams({ cfgScaleText: value })} />
            <LabeledSlider label="声の寄せ (CFG)" value={selectedLine.params.cfgScaleSpeaker.toFixed(1)} min={0} max={10} step={0.1} onChange={(value) => updateSelectedParams({ cfgScaleSpeaker: value })} disabled={!model.use_speaker_condition} />
            <LabeledSlider label="Voice Design (CFG)" value={selectedLine.params.cfgScaleCaption.toFixed(1)} min={0} max={10} step={0.1} onChange={(value) => updateSelectedParams({ cfgScaleCaption: value })} disabled={!model.use_caption_condition} />
            <label className="seed-control"><span>シード</span><div><input type="number" value={selectedLine.params.seed ?? ""} placeholder="ランダム" onChange={(event) => updateSelectedParams({ seed: event.target.value === "" ? null : Number(event.target.value) })} /><IconButton label="ランダムシード" onClick={() => updateSelectedParams({ seed: Math.floor(Math.random() * 2_147_483_647) })}><ArrowsClockwise size={17} /></IconButton></div></label>
          </div>
          <div className="caption-row">
            <div className="caption-control">
              <label><span>Voice Design caption <small>読み上げ文ではなく、声の感情・雰囲気・演技を指示</small></span><input value={selectedLine.caption} placeholder="例：落ち着いた優しい声で、ゆっくり話す" onChange={(event) => mutateLine(selectedLine.id, { caption: event.target.value })} disabled={!model.use_caption_condition} /></label>
              <CaptionPresetButtons value={selectedLine.caption} onChange={(caption) => mutateLine(selectedLine.id, { caption })} disabled={!model.use_caption_condition} />
            </div>
            <button className="advanced-toggle" onClick={() => setAdvancedOpen((open) => !open)}><GearSix size={18} />詳細設定<CaretDown size={16} className={advancedOpen ? "open" : ""} /></button>
          </div>
          {advancedOpen && <div className="advanced-panel"><label>CFG方式<select value={selectedLine.params.cfgGuidanceMode} onChange={(event) => updateSelectedParams({ cfgGuidanceMode: event.target.value })}><option value="independent">Independent</option><option value="joint">Joint</option><option value="alternating">Alternating</option></select></label><label>時間スケジュール<select value={selectedLine.params.tScheduleMode} onChange={(event) => updateSelectedParams({ tScheduleMode: event.target.value })}><option value="linear">Linear</option><option value="sway">Sway</option></select></label><label>Truncation<input type="number" step="0.05" value={selectedLine.params.truncationFactor ?? ""} placeholder="無効" onChange={(event) => updateSelectedParams({ truncationFactor: event.target.value === "" ? null : Number(event.target.value) })} /></label><label>Speaker KV Scale<input type="number" step="0.1" value={selectedLine.params.speakerKvScale ?? ""} placeholder="無効" onChange={(event) => updateSelectedParams({ speakerKvScale: event.target.value === "" ? null : Number(event.target.value) })} /></label></div>}
        </section>
      )}

      {speakingLine && <div className="now-speaking"><div><span><SpeakerHigh size={19} weight="fill" />NOW SPEAKING</span><strong>{speakingLine.text}</strong></div><IconButton label="停止" onClick={stopPlayback}><X size={20} /></IconButton></div>}
      {toast && <div className={`toast ${toast.tone}`} key={toast.id}>{toast.tone === "error" ? <WarningCircle size={20} /> : <Check size={20} />}{toast.message}</div>}
      <EmojiPicker picker={emojiPicker} expanded={emojiExpanded} onExpandedChange={setEmojiExpanded} onSelect={insertEmoji} onClose={() => setEmojiPicker(null)} />

      {activeModal === "model" && <Modal title="Irodori-TTSモデル" eyebrow="LOCAL RUNTIME" onClose={() => setActiveModal(null)} wide scrollable>
        <div className="model-layout">
          <section className="form-stack">
            <div className="model-catalog-heading"><div><strong>読み上げモデル</strong><span>導入済みモデルは自動検出され、最後に読み込んだ設定を次回も使用します。</span></div><IconButton label="モデル一覧を更新" onClick={async () => setModelCatalog(await api.models())}><ArrowsClockwise size={18} /></IconButton></div>
            <div className="model-catalog" role="radiogroup" aria-label="読み上げモデル">
              {modelCatalog.map((entry) => {
                const selected = modelSettings.checkpoint === entry.source;
                const installing = installingModelId === entry.id;
                return (
                  <div key={entry.id} className={`model-catalog-item ${selected ? "selected" : ""} ${!entry.supported ? "unsupported" : ""}`}>
                    <button
                      type="button"
                      className="model-catalog-select"
                      role="radio"
                      aria-checked={selected}
                      disabled={!entry.supported || (!entry.installed && entry.installable)}
                      onClick={() => selectCatalogModel(entry)}
                    >
                      <span className="model-catalog-radio">{selected && <Check size={15} weight="bold" />}</span>
                      <span className="model-catalog-copy">
                        <strong>{entry.name}</strong>
                        <small>{entry.description}</small>
                        <span className="model-catalog-meta">
                          {entry.quantization?.label && <em>{entry.quantization.label}</em>}
                          {entry.recommended && <em>推奨</em>}
                          {entry.experimental && <em>実験的</em>}
                          {entry.installed && <em>導入済み</em>}
                          {formatModelSize(entry.size_bytes) && <em>{formatModelSize(entry.size_bytes)}</em>}
                        </span>
                        {entry.compatibility_message && <span className="model-compatibility"><WarningCircle size={16} />{entry.compatibility_message}</span>}
                      </span>
                    </button>
                    {entry.installable && !entry.installed && <IconButton className="model-install-button" label={`${entry.name}を導入`} onClick={() => handleInstallModel(entry)} disabled={installing || !entry.supported}>{installing ? <SpinnerGap className="spin" size={20} /> : <DownloadSimple size={20} />}</IconButton>}
                  </div>
                );
              })}
            </div>
            <details className="custom-model-settings">
              <summary>一覧にないモデルを指定</summary>
              <label><span>チェックポイントまたはHugging Face ID</span><div className="path-input"><input list="checkpoint-assets" value={modelSettings.checkpoint} onChange={(event) => setModelSettings({ ...modelSettings, checkpoint: event.target.value })} /><IconButton label="チェックポイントを選択" onClick={() => choosePath("checkpoint", false, ([path]) => setModelSettings({ ...modelSettings, checkpoint: path }))}><FolderOpen size={18} /></IconButton></div><datalist id="checkpoint-assets">{bootstrap?.assets?.checkpoints?.map((path) => <option key={path} value={path} />)}</datalist></label>
            </details>
            <div className="form-grid"><label><span>モデルデバイス</span><select value={modelSettings.modelDevice} onChange={(event) => setModelSettings({ ...modelSettings, modelDevice: event.target.value })}>{(bootstrap?.devices || ["cuda", "cpu"]).map((device) => <option key={device}>{device}</option>)}</select></label><label><span>モデル精度</span><select value={modelSettings.modelPrecision} onChange={(event) => setModelSettings({ ...modelSettings, modelPrecision: event.target.value })}>{(bootstrap?.precisions?.[modelSettings.modelDevice] || ["fp32", "bf16"]).map((precision) => <option key={precision}>{precision}</option>)}</select></label><label><span>Codecデバイス</span><select value={modelSettings.codecDevice} onChange={(event) => setModelSettings({ ...modelSettings, codecDevice: event.target.value })}>{(bootstrap?.devices || ["cuda", "cpu"]).map((device) => <option key={device}>{device}</option>)}</select></label><label><span>Codec精度</span><select value={modelSettings.codecPrecision} onChange={(event) => setModelSettings({ ...modelSettings, codecPrecision: event.target.value })}>{(bootstrap?.precisions?.[modelSettings.codecDevice] || ["fp32", "bf16"]).map((precision) => <option key={precision}>{precision}</option>)}</select></label></div>
            <div className="modal-actions"><button className="secondary-button" onClick={async () => { await api.unloadModel(); setModel({ loaded: false }); }} disabled={!model.loaded || modelLoading}>アンロード</button><button className="primary-button" onClick={handleLoadModel} disabled={modelLoading || !modelSettings.checkpoint}>{modelLoading ? <SpinnerGap className="spin" size={20} /> : <Cpu size={20} />}{modelLoading ? "ロード中…" : "モデルをロード"}</button></div>
          </section>
          <aside className="runtime-summary"><span className={`runtime-icon ${model.loaded ? "loaded" : ""}`}><Cpu size={30} /></span><small>{model.loaded ? "READY" : "NOT LOADED"}</small><h3>{model.loaded ? model.name : "モデル未選択"}</h3>{model.loaded ? <dl><div><dt>Parameters</dt><dd>{model.parameter_count ? `${(model.parameter_count / 1e6).toFixed(0)}M` : "—"}</dd></div><div><dt>量子化</dt><dd>{model.quantization?.label || "標準"}</dd></div><div><dt>Voice Design</dt><dd>{model.use_caption_condition ? "対応" : "非対応"}</dd></div><div><dt>Speaker</dt><dd>{model.use_speaker_condition ? "対応" : "非対応"}</dd></div><div><dt>Duration</dt><dd>{model.use_duration_predictor ? "自動" : "固定"}</dd></div><div><dt>VRAM</dt><dd>{model.cuda ? `${model.cuda.allocated_gb} GB` : "—"}</dd></div></dl> : <p>使用するモデルを選び、メモリへロードしてください。</p>}</aside>
        </div>
      </Modal>}

      {activeModal === "voices" && <Modal title="ボイスライブラリ" eyebrow="VOICE PROFILES" onClose={() => setActiveModal(null)} wide scrollable>
        <div className="voice-layout">
          <aside className="voice-list">
            <div className="voice-list-toolbar">
              <span>ボイス</span>
              <IconButton label="ボイスを追加" onClick={() => {
                setVoiceNameValue(`ボイス ${project.voices.length + 1}`);
                setVoiceNameAction("create");
              }}><Plus size={18} /></IconButton>
            </div>
            <SortableList
              items={project.voices}
              label="ボイスライブラリ"
              onReorder={(voices) => {
                commitVoiceOrder(voices);
                notify("ボイスの並び順を更新しました", "success");
              }}
              renderItem={renderVoiceListItem}
              renderOverlay={(voice, index) => renderVoiceListItem(voice, index, { overlay: true })}
            />
          </aside>
          {selectedVoice && <section className="voice-editor">
            <div className={`voice-save-state ${voiceSaveState.status}`} title={voiceSaveState.message}>
              {voiceSaveState.status === "saving" || voiceSaveState.status === "pending"
                ? <SpinnerGap className="spin" size={17} />
                : voiceSaveState.status === "error"
                  ? <WarningCircle size={17} />
                  : <Check size={17} />}
              <span>{voiceSaveState.message}</span>
            </div>
            <div className="voice-name-row">
              <i style={{ backgroundColor: selectedVoice.color }} />
              <strong>{selectedVoice.name}</strong>
              <IconButton
                label="ボイス名を変更"
                onClick={() => {
                  setVoiceNameValue(selectedVoice.name);
                  setVoiceNameAction("rename");
                }}
              ><PencilSimple size={18} /></IconButton>
              {project.voices.length > 1 && <IconButton
                label="このボイスをライブラリから削除"
                tone="danger"
                onClick={() => setVoiceDeletePending(true)}
              ><Trash size={18} /></IconButton>}
            </div>
            <div className="source-tabs">
              <button className={selectedVoice.sourceType === "speaker" ? "active" : ""} onClick={() => updateSelectedVoice({ sourceType: "speaker" })}>Speaker Inversion</button>
              <button className={selectedVoice.sourceType === "reference" ? "active" : ""} onClick={() => updateSelectedVoice({ sourceType: "reference" })}>参照音声</button>
              <button className={selectedVoice.sourceType === "none" ? "active" : ""} onClick={() => updateSelectedVoice({ sourceType: "none" })}>参照なし</button>
            </div>
            {selectedVoice.sourceType === "speaker" && <label>
              <span>Speaker embedding (.safetensors)</span>
              <div className="path-input"><input list="speaker-assets" value={selectedVoice.refEmbed} onChange={(event) => updateSelectedVoice({ refEmbed: event.target.value })} /><button onClick={() => choosePath("speaker", false, ([path]) => updateSelectedVoice({ refEmbed: path }))}><FolderOpen size={18} />選択</button></div>
              <datalist id="speaker-assets">{bootstrap?.assets?.speaker_embeddings?.map((path) => <option key={path} value={path} />)}</datalist>
            </label>}
            {selectedVoice.sourceType === "reference" && <label>
              <span>参照音声（複数可・上から順に結合）</span>
              <textarea rows="5" value={(selectedVoice.refWavs || []).join("\n")} onChange={(event) => updateSelectedVoice({ refWavs: event.target.value.split(/\r?\n/).filter(Boolean) })} />
              <button className="inline-file-button" onClick={() => choosePath("reference", true, (paths) => updateSelectedVoice({ refWavs: paths }))}><FolderOpen size={18} />音声ファイルを選択</button>
            </label>}
            <label>
              <span>LoRAアダプター（任意）</span>
              <div className="path-input"><input value={selectedVoice.loraAdapter} onChange={(event) => updateSelectedVoice({ loraAdapter: event.target.value })} /><button onClick={() => choosePath("lora", false, ([path]) => updateSelectedVoice({ loraAdapter: path }))}><FolderOpen size={18} />選択</button></div>
            </label>
            <label><span>既定のVoice Design caption</span><input value={selectedVoice.defaultCaption} placeholder="各行に指示がない場合に使用" onChange={(event) => updateSelectedVoice({ defaultCaption: event.target.value })} /></label>

            <div className="api-profile-card">
              <header>
                <span className="api-profile-icon"><Broadcast size={23} /></span>
                <div><strong>VOICEVOX互換API</strong><small>ボイス本体は常にライブラリへ自動保存 · 127.0.0.1:{bootstrap?.voicevox_api?.port || 50021} · 公開中 {serverVoiceProfiles.filter((profile) => profile.enabled).length}スタイル</small></div>
                {selectedVoice.apiStyleId && <span className="style-id-badge">ID {selectedVoice.apiStyleId}</span>}
              </header>
              <label className="api-publish-toggle">
                <input type="checkbox" checked={Boolean(selectedVoice.apiEnabled)} onChange={(event) => updateSelectedVoice({ apiEnabled: event.target.checked })} />
                <span><strong>外部アプリから選べるようにする</strong><small>オンにすると自動保存後、127.0.0.1:{bootstrap?.voicevox_api?.port || 50021} の話者一覧へ反映されます</small></span>
              </label>
              {selectedVoice.sourceType === "none" && selectedVoice.apiEnabled && <p className="api-profile-warning"><WarningCircle size={17} />参照なしでは声質が発話ごとに変わりやすいため、配信にはSpeaker Inversionまたは参照音声を推奨します。</p>}
              <div className="api-profile-grid">
                <label><span>スタイル名</span><input value={selectedVoice.apiStyleName} onChange={(event) => updateSelectedVoice({ apiStyleName: event.target.value })} /></label>
                <label><span>API話速</span><input type="number" min="0.5" max="2" step="0.05" value={selectedVoice.apiSpeed} onChange={(event) => updateSelectedVoice({ apiSpeed: Number(event.target.value) })} /></label>
                <label><span>生成ステップ</span><input type="number" min="1" max="120" step="1" value={selectedVoice.apiNumSteps} onChange={(event) => updateSelectedVoice({ apiNumSteps: Number(event.target.value) })} /></label>
                <label><span>固定シード（空欄で自動）</span><input type="number" value={selectedVoice.apiSeed ?? ""} onChange={(event) => updateSelectedVoice({ apiSeed: event.target.value })} /></label>
              </div>
              <details>
                <summary>API生成の詳細設定</summary>
                <div className="api-profile-grid api-advanced-grid">
                  <label><span>Text CFG</span><input type="number" min="0" max="12" step="0.1" value={selectedVoice.apiCfgScaleText} onChange={(event) => updateSelectedVoice({ apiCfgScaleText: Number(event.target.value) })} /></label>
                  <label><span>Caption CFG</span><input type="number" min="0" max="12" step="0.1" value={selectedVoice.apiCfgScaleCaption} onChange={(event) => updateSelectedVoice({ apiCfgScaleCaption: Number(event.target.value) })} /></label>
                  <label><span>Speaker CFG</span><input type="number" min="0" max="12" step="0.1" value={selectedVoice.apiCfgScaleSpeaker} onChange={(event) => updateSelectedVoice({ apiCfgScaleSpeaker: Number(event.target.value) })} /></label>
                </div>
                <label><span>利用条件・メモ（話者情報APIに表示）</span><textarea rows="3" value={selectedVoice.apiPolicy} onChange={(event) => updateSelectedVoice({ apiPolicy: event.target.value })} /></label>
              </details>
              <div className="api-profile-actions">
                <span>変更はこのPCのボイスライブラリへ自動保存されます</span>
                <button className="secondary-button" onClick={() => persistVoiceLibrary({ announce: true })}><FloppyDisk size={18} />今すぐ保存</button>
              </div>
            </div>
          </section>}
        </div>
      </Modal>}

      {activeModal === "import" && <Modal title="文章を台本へ取り込む" eyebrow="TEXT IMPORT" onClose={() => setActiveModal(null)}><p className="modal-description">1行を1つの読み上げ単位として、現在のボイスで追加します。空行は無視されます。</p><textarea className="large-textarea" rows="12" value={importText} onChange={(event) => setImportText(event.target.value)} placeholder={'最初の文章を入力します。\n次の文章は改行して入力します。'} /><div className="modal-actions"><button className="secondary-button" onClick={() => setActiveModal(null)}>キャンセル</button><button className="primary-button" onClick={() => { const lines = splitImportedText(importText, { voiceId: selectedVoiceId || project.voices[0]?.id }); if (lines.length) { mutateProject((current) => ({ ...current, lines: [...current.lines, ...lines] })); setSelectedLineId(lines[0].id); setImportText(""); setActiveModal(null); notify(`${lines.length}行を追加しました`, "success"); } }} disabled={!importText.trim()}><Plus size={19} />台本へ追加</button></div></Modal>}

      {activeModal === "projects" && <Modal title="プロジェクト管理" eyebrow="PROJECTS" onClose={() => setActiveModal(null)} scrollable>
        <section className="project-create-panel">
          <div className="project-create-heading">
            <span><FolderPlus size={22} /></span>
            <div><strong>新しいプロジェクト</strong><small>名前を付けて、空の台本から制作を始めます。</small></div>
          </div>
          <div className="project-create-form">
            <input
              value={newProjectName}
              aria-label="新しいプロジェクト名"
              placeholder="プロジェクト名"
              onChange={(event) => setNewProjectName(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter" && !projectBusy) createProject(); }}
            />
            <IconButton className="resource-create-button" tone="primary" label="新しいプロジェクトを作成" onClick={createProject} disabled={projectBusy || !newProjectName.trim()}>
              {projectBusy ? <SpinnerGap className="spin" size={19} /> : <Plus size={19} />}
            </IconButton>
          </div>
        </section>
        <div className="project-list-heading"><strong>プロジェクト一覧</strong><span>{savedProjects.length}件</span></div>
        <div className="saved-projects">
          {savedProjects.length ? savedProjects.map((saved) => {
            const isCurrent = saved.storage_name === activeProjectName;
            return <article className={`saved-project-card ${isCurrent ? "current" : ""}`} key={saved.storage_name || saved.filename}>
              <span className="saved-project-icon"><FileText size={22} /></span>
              <span className="saved-project-info"><strong>{saved.name}</strong><small>{new Date(saved.updated_at * 1000).toLocaleString("ja-JP")} 更新</small></span>
              <span className="saved-project-actions">
                {isCurrent
                  ? <span className="current-project-badge"><Check size={15} />開いています</span>
                  : <IconButton label={`${saved.name}を開く`} onClick={() => loadSavedProject(saved)} disabled={projectBusy}><FolderOpen size={17} /></IconButton>}
                <IconButton label={`${saved.name}の名前を変更`} onClick={() => openProjectRename(saved)} disabled={projectBusy}><PencilSimple size={17} /></IconButton>
                <IconButton label={`${saved.name}を削除`} tone="danger" onClick={() => setProjectDeleteTarget(saved)} disabled={projectBusy}><Trash size={17} /></IconButton>
              </span>
            </article>;
          }) : <div className="empty-state"><FolderOpen size={30} /><span>まだプロジェクトがありません。<br />上の欄から新しく作成できます。</span></div>}
        </div>
      </Modal>}

      {projectRenameTarget && <NameDialog
        title="プロジェクト名を変更"
        eyebrow="PROJECT NAME"
        description="表示名とStudio内の保存名を一緒に変更します。台本と生成済み音声はそのまま維持されます。"
        label="プロジェクト名"
        value={projectRenameName}
        onChange={setProjectRenameName}
        onSubmit={renameProject}
        onClose={() => setProjectRenameTarget(null)}
        submitLabel="名前を変更"
        busy={projectBusy}
        disabled={!projectRenameName.trim() || projectRenameName.trim() === String(projectRenameTarget.name || "").trim()}
      />}

      {projectDeleteTarget && <ConfirmDialog
        title={`「${projectDeleteTarget.name}」を削除しますか？`}
        eyebrow="DELETE PROJECT"
        description="このプロジェクトと、ほかのプロジェクトから参照されていない生成済み音声を削除します。この操作は元に戻せません。"
        onConfirm={() => deleteSavedProject(projectDeleteTarget)}
        onClose={() => setProjectDeleteTarget(null)}
        busy={projectBusy}
      />}

      {voiceNameAction && <NameDialog
        title={voiceNameAction === "create" ? "ボイスを追加" : "ボイス名を変更"}
        eyebrow="VOICE NAME"
        description="台本制作と配信で共通して表示される名前です。ボイスの設定内容は維持されます。"
        label="ボイス名"
        value={voiceNameValue}
        onChange={setVoiceNameValue}
        onSubmit={submitVoiceName}
        onClose={() => setVoiceNameAction(null)}
        submitLabel={voiceNameAction === "create" ? "追加" : "名前を変更"}
        maxLength={80}
        disabled={!voiceNameValue.trim() || (voiceNameAction === "rename" && voiceNameValue.trim() === selectedVoice?.name) || project.voices.some((voice) => voice.id !== (voiceNameAction === "rename" ? selectedVoice?.id : null) && voice.name.toLocaleLowerCase("ja-JP") === voiceNameValue.trim().toLocaleLowerCase("ja-JP"))}
      />}

      {voiceDeletePending && selectedVoice && <ConfirmDialog
        title={`「${selectedVoice.name}」を削除しますか？`}
        eyebrow="DELETE VOICE"
        description="このボイスを使用している台本行は別のボイスへ切り替わり、再生成が必要になります。"
        onConfirm={deleteSelectedVoice}
        onClose={() => setVoiceDeletePending(false)}
        busy={voiceDeleteBusy}
      />}

      {activeModal === "export" && <Modal title="動画・配信用パッケージ" eyebrow="PRODUCTION EXPORT" onClose={() => setActiveModal(null)} wide><div className="export-layout"><section><div className="export-readiness"><span className={staleOrMissing.length ? "warning" : "ready"}>{staleOrMissing.length ? <WarningCircle size={25} /> : <Check size={25} />}</span><div><strong>{staleOrMissing.length ? `${staleOrMissing.length}行の生成が必要です` : "すべて書き出せます"}</strong><p>{generatedCount}/{project.lines.length}行 · 音声 {formatDuration(projectSeconds)}</p></div>{staleOrMissing.length > 0 && <button className="secondary-button" onClick={generateAllMissing} disabled={!model.loaded || queueCount > 0}><MagicWand size={18} />不足分を生成</button>}</div><label className="gap-setting"><span>行間の無音</span><input type="range" min="0" max="2000" step="50" value={project.exportSettings.gapMs} onChange={(event) => mutateProject((current) => ({ ...current, exportSettings: { ...current.exportSettings, gapMs: Number(event.target.value) } }))} /><strong>{project.exportSettings.gapMs} ms</strong></label><div className="export-checks">{[["includeMaster", "連結したmaster.wav", "動画編集・配信素材の完成音声", VideoCamera], ["includeSrt", "SRT字幕", "一般的な動画編集ソフト向け", FileText], ["includeVtt", "WebVTT字幕", "Web配信・プレイヤー向け", FileText], ["includeCsv", "CSVタイムライン", "開始・終了・声・シードを記録", ListNumbers]].map(([key, title, detail, Icon]) => <label key={key}><input type="checkbox" checked={project.exportSettings[key]} onChange={(event) => mutateProject((current) => ({ ...current, exportSettings: { ...current.exportSettings, [key]: event.target.checked } }))} /><Icon size={21} /><span><strong>{title}</strong><small>{detail}</small></span></label>)}</div></section><aside className="package-preview"><span className="package-icon"><Export size={31} /></span><h3>ZIPに含まれるもの</h3><ul><li>行ごとのPCM WAV</li><li>連結済みマスター音声</li><li>SRT / VTT字幕</li><li>タイムライン情報</li><li>FFmpeg concatリスト</li><li>再編集用のプロジェクトデータ</li></ul><button className="primary-button" onClick={exportProduction} disabled={exportBusy || staleOrMissing.length > 0}>{exportBusy ? <SpinnerGap className="spin" size={20} /> : <DownloadSimple size={20} />}{exportBusy ? "準備中…" : "制作パッケージを保存"}</button></aside></div></Modal>}
    </div>
  );
}

export { App };
