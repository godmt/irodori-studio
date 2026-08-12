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
  GearSix,
  HardDrive,
  Lightning,
  ListNumbers,
  MagicWand,
  MicrophoneStage,
  Pause,
  Play,
  Plus,
  Queue,
  SlidersHorizontal,
  Smiley,
  SpeakerHigh,
  SpinnerGap,
  Stop,
  Trash,
  UploadSimple,
  VideoCamera,
  WarningCircle,
  Waveform,
  X,
} from "@phosphor-icons/react";

import { api, audioUrl } from "./api.js";
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
  duplicateLine,
  estimatedProjectSeconds,
  appendLineTake,
  selectLineTake,
  splitImportedText,
  updateLine,
} from "./project-state.js";

const STORAGE_KEY = "irodori-studio-project-v1";
const PLAYBACK_VOLUME_KEY = "irodori-studio-playback-volume-v2";
const VOICE_COLORS = ["#c9651b", "#35766d", "#7960a8", "#a94848", "#476b9b", "#7c7138"];

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

function IconButton({ label, children, tone = "quiet", className = "", ...props }) {
  return (
    <button className={`icon-button ${tone} ${className}`} type="button" title={label} aria-label={label} {...props}>
      {children}
    </button>
  );
}

function Modal({ title, eyebrow, onClose, children, wide = false, scrollable = false }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className={`modal-card ${wide ? "wide" : ""} ${scrollable ? "scrollable" : ""}`} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header className="modal-header">
          <div>
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            <h2>{title}</h2>
          </div>
          <IconButton label="閉じる" onClick={onClose}><X size={21} /></IconButton>
        </header>
        <div className="modal-body">{children}</div>
      </section>
    </div>
  );
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

function App() {
  const [project, setProject] = useState(loadLocalProject);
  const [selectedLineId, setSelectedLineId] = useState(() => project.lines[0]?.id || null);
  const [view, setView] = useState("script");
  const [model, setModel] = useState({ loaded: false });
  const [bootstrap, setBootstrap] = useState(null);
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
  const [exportBusy, setExportBusy] = useState(false);
  const [draggedLineId, setDraggedLineId] = useState(null);
  const [liveInput, setLiveInput] = useState("");
  const [liveCaption, setLiveCaption] = useState("");
  const [liveItems, setLiveItems] = useState([]);
  const [liveVoiceId, setLiveVoiceId] = useState(project.voices[0]?.id || null);
  const [livePreset, setLivePreset] = useState("live");
  const [playbackVolume, setPlaybackVolume] = useState(loadPlaybackVolume);
  const [serverVoiceProfiles, setServerVoiceProfiles] = useState([]);
  const [emojiPicker, setEmojiPicker] = useState(null);
  const [emojiExpanded, setEmojiExpanded] = useState(false);

  const projectRef = useRef(project);
  const audioRef = useRef(null);
  const playbackResolveRef = useRef(null);
  const playbackCleanupRef = useRef(null);
  const sequenceTokenRef = useRef(0);
  const generationPromisesRef = useRef(new Map());
  const liveQueueRef = useRef([]);
  const livePumpingRef = useRef(false);
  const importFileRef = useRef(null);
  const lineTextRefs = useRef(new Map());
  const liveTextRef = useRef(null);
  const textSelectionRef = useRef(new Map());

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

  useEffect(() => {
    projectRef.current = project;
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...project, updatedAt: new Date().toISOString() }));
  }, [project]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = playbackVolume / 100;
  }, [playbackVolume]);

  useEffect(() => {
    const timer = toast ? window.setTimeout(() => setToast(null), 3600) : null;
    return () => timer && window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    let cancelled = false;
    api.bootstrap()
      .then((data) => {
        if (cancelled) return;
        setBootstrap(data);
        setServerVoiceProfiles(data.voice_profiles || []);
        setModel(data.model || { loaded: false });
        setModelSettings((current) => ({
          ...current,
          checkpoint: current.checkpoint || data.default_checkpoint,
          modelDevice: data.default_device || current.modelDevice,
          codecDevice: data.default_device || current.codecDevice,
          modelPrecision: data.precisions?.[data.default_device]?.includes("bf16") ? "bf16" : "fp32",
          codecPrecision: data.precisions?.[data.default_device]?.includes("bf16") ? "bf16" : "fp32",
        }));
        setConnection("online");
      })
      .catch(() => setConnection("offline"));
    return () => { cancelled = true; };
  }, []);

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

  const saveSelectedVoiceProfile = useCallback(async () => {
    if (!selectedVoice) return;
    try {
      const profile = await api.saveVoiceProfile({
        profile_id: selectedVoice.apiProfileId || null,
        name: selectedVoice.name.trim(),
        style_name: (selectedVoice.apiStyleName || "ノーマル").trim(),
        enabled: Boolean(selectedVoice.apiEnabled),
        source_type: selectedVoice.sourceType,
        ref_embed: selectedVoice.refEmbed || null,
        ref_wavs: (selectedVoice.refWavs || []).filter(Boolean),
        lora_adapter: selectedVoice.loraAdapter || null,
        default_caption: selectedVoice.defaultCaption || "",
        speed: Number(selectedVoice.apiSpeed ?? 1),
        num_steps: Number(selectedVoice.apiNumSteps ?? 12),
        seed: selectedVoice.apiSeed === "" || selectedVoice.apiSeed == null ? null : Number(selectedVoice.apiSeed),
        cfg_scale_text: Number(selectedVoice.apiCfgScaleText ?? 3),
        cfg_scale_caption: Number(selectedVoice.apiCfgScaleCaption ?? 3),
        cfg_scale_speaker: Number(selectedVoice.apiCfgScaleSpeaker ?? 5),
        policy: selectedVoice.apiPolicy || "",
      });
      updateSelectedVoice({
        apiProfileId: profile.profile_id,
        apiSpeakerUuid: profile.speaker_uuid,
        apiStyleId: profile.style_id,
        apiEnabled: profile.enabled,
      });
      setServerVoiceProfiles((current) => [
        ...current.filter((item) => item.profile_id !== profile.profile_id),
        profile,
      ].sort((a, b) => a.style_id - b.style_id));
      notify(profile.enabled ? `Style ID ${profile.style_id} でAPIへ公開しました` : "API設定を保存しました（非公開）", "success");
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify, selectedVoice, updateSelectedVoice]);

  const deleteSelectedVoiceProfile = useCallback(async () => {
    if (!selectedVoice?.apiProfileId) return;
    try {
      await api.deleteVoiceProfile(selectedVoice.apiProfileId);
      setServerVoiceProfiles((current) => current.filter((item) => item.profile_id !== selectedVoice.apiProfileId));
      updateSelectedVoice({
        apiProfileId: null,
        apiEnabled: false,
        apiSpeakerUuid: null,
        apiStyleId: null,
      });
      notify("API登録を削除しました", "success");
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify, selectedVoice, updateSelectedVoice]);

  const mutateLine = useCallback((lineId, patch, invalidate = true) => {
    mutateProject((current) => ({
      ...current,
      lines: updateLine(current.lines, lineId, patch, invalidate),
    }));
  }, [mutateProject]);

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
  }, [buildPayload, mutateLine, mutateProject, submitSynthesis]);

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
    const finish = () => {
      cleanup();
      setSpeakingLineId(null);
      playbackCleanupRef.current = null;
      playbackResolveRef.current = null;
      resolve(true);
    };
    const fail = () => {
      cleanup();
      setSpeakingLineId(null);
      playbackCleanupRef.current = null;
      playbackResolveRef.current = null;
      reject(new Error("音声を再生できませんでした"));
    };
    audio.addEventListener("ended", finish, { once: true });
    audio.addEventListener("error", fail, { once: true });
    playbackCleanupRef.current = cleanup;
    playbackResolveRef.current = resolve;
    audio.play().catch(fail);
  }), []);

  const playLine = useCallback(async (lineId) => {
    try {
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
  }, [generateLine, notify, playAudio]);

  const playFrom = useCallback(async (startLineId) => {
    stopPlayback();
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
  }, [generateLine, notify, playAudio, stopPlayback]);

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
    const newLine = createLine();
    mutateProject((current) => {
      const index = afterId ? current.lines.findIndex((line) => line.id === afterId) + 1 : current.lines.length;
      const lines = [...current.lines];
      lines.splice(Math.max(0, index), 0, newLine);
      return { ...current, lines };
    });
    setSelectedLineId(newLine.id);
  }, [mutateProject]);

  const removeLine = useCallback((lineId) => {
    mutateProject((current) => {
      if (current.lines.length === 1) return current;
      const index = current.lines.findIndex((line) => line.id === lineId);
      const lines = current.lines.filter((line) => line.id !== lineId);
      if (selectedLineId === lineId) setSelectedLineId(lines[Math.max(0, index - 1)]?.id || null);
      return { ...current, lines };
    });
  }, [mutateProject, selectedLineId]);

  const handleDrop = useCallback((targetId) => {
    if (!draggedLineId || draggedLineId === targetId) return;
    mutateProject((current) => {
      const from = current.lines.findIndex((line) => line.id === draggedLineId);
      const to = current.lines.findIndex((line) => line.id === targetId);
      const lines = [...current.lines];
      const [moved] = lines.splice(from, 1);
      lines.splice(to, 0, moved);
      return { ...current, lines };
    });
    setDraggedLineId(null);
  }, [draggedLineId, mutateProject]);

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

  const choosePath = useCallback(async (kind, multiple, onPaths) => {
    try {
      const result = await api.dialog(kind, multiple);
      if (result.paths.length) onPaths(result.paths);
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify]);

  const saveProject = useCallback(async () => {
    try {
      await api.saveProject(project.title, project);
      notify("プロジェクトをローカル保存しました", "success");
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify, project]);

  const downloadProjectJson = useCallback(() => {
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${project.title || "irodori-project"}.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [project]);

  const importProjectFile = useCallback(async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const loaded = hydrateProject(JSON.parse(await file.text()));
      setProject(loaded);
      setSelectedLineId(loaded.lines[0]?.id || null);
      setSelectedVoiceId(loaded.voices[0]?.id || null);
      notify("プロジェクトを読み込みました", "success");
    } catch {
      notify("プロジェクトJSONを読み込めませんでした", "error");
    } finally {
      event.target.value = "";
    }
  }, [notify]);

  const openProjectsModal = useCallback(async () => {
    setActiveModal("projects");
    try {
      setSavedProjects(await api.projects());
    } catch {
      setSavedProjects([]);
    }
  }, []);

  const loadSavedProject = useCallback(async (name) => {
    try {
      const loaded = hydrateProject(await api.loadProject(name));
      setProject(loaded);
      setSelectedLineId(loaded.lines[0]?.id || null);
      setSelectedVoiceId(loaded.voices[0]?.id || null);
      setActiveModal(null);
      notify("保存済みプロジェクトを開きました", "success");
    } catch (error) {
      notify(error.message, "error");
    }
  }, [notify]);

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
    const item = {
      id: uid("live"),
      text: trimmed,
      caption: liveCaption,
      voiceId: liveVoiceId,
      preset: livePreset,
      status: "queued",
      audioFile: null,
      duration: null,
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
          const line = createLine({
            id: next.id,
            text: next.text,
            caption: next.caption,
            voiceId: next.voiceId,
            params: {
              ...DEFAULT_PARAMS,
              quality: next.preset,
              numSteps: QUALITY_PRESETS[next.preset].numSteps,
              seed: null,
            },
          });
          try {
            const result = await submitSynthesis(buildPayload(line, voice), (job) => {
              setLiveItems((current) => current.map((entry) => entry.id === next.id ? { ...entry, status: job.status } : entry));
            });
            setLiveItems((current) => current.map((entry) => entry.id === next.id ? {
              ...entry,
              status: "ready",
              audioFile: result.audio_file,
              duration: result.duration,
            } : entry));
            await playAudio(result.audio_file, next.id);
          } catch (error) {
            setLiveItems((current) => current.map((entry) => entry.id === next.id ? { ...entry, status: "failed", error: error.message } : entry));
          }
        }
        livePumpingRef.current = false;
      })();
    }
  }, [buildPayload, liveCaption, livePreset, liveVoiceId, playAudio, submitSynthesis]);

  const stopLive = useCallback(async () => {
    liveQueueRef.current = [];
    stopPlayback();
    try { await api.cancelAll(); } catch { /* Local playback still stops if cancellation fails. */ }
    setLiveItems((current) => current.map((item) => item.status === "queued" ? { ...item, status: "cancelled" } : item));
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

  return (
    <div className="app-shell">
      <audio ref={audioRef} preload="auto" />
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-mark"><Waveform size={25} weight="bold" /></span>
          <div><strong>Irodori Studio</strong><small>LOCAL PRODUCTION CONSOLE</small></div>
        </div>
        <nav className="view-switcher" aria-label="制作モード">
          <button className={view === "script" ? "active" : ""} onClick={() => setView("script")}><FileText size={18} />台本制作</button>
          <button className={view === "live" ? "active" : ""} onClick={() => setView("live")}><Broadcast size={18} />配信コンソール</button>
        </nav>
        <div className="top-actions">
          <button className={`model-pill ${model.loaded ? "loaded" : ""}`} onClick={() => setActiveModal("model")}>
            <span className="model-state" />
            <span><small>{connection === "offline" ? "API OFFLINE" : model.loaded ? "MODEL READY" : "MODEL OFF"}</small><strong>{model.loaded ? model.name : "モデルをロード"}</strong></span>
            <CaretDown size={16} />
          </button>
          <span className="queue-indicator"><Queue size={18} /><strong>{queueCount}</strong></span>
          <IconButton label="プロジェクトを開く" onClick={openProjectsModal}><FolderOpen size={20} /></IconButton>
          <IconButton label="保存" onClick={saveProject}><FloppyDisk size={20} /></IconButton>
          <button className="primary-compact" onClick={() => setActiveModal("export")}><Export size={19} />書き出し</button>
        </div>
      </header>

      {view === "script" ? (
        <main className="workspace">
          <aside className="script-sidebar">
            <div className="project-heading">
              <label>PROJECT</label>
              <input value={project.title} onChange={(event) => mutateProject((current) => ({ ...current, title: event.target.value }))} aria-label="プロジェクト名" />
              <div className="project-metrics">
                <span><ListNumbers size={17} />{project.lines.length}行</span>
                <span><Clock size={17} />{formatDuration(projectSeconds)}</span>
                <span><Check size={17} />{generatedCount}/{project.lines.length}</span>
              </div>
            </div>
            <div className="sidebar-actions">
              <button onClick={() => addLine()}><Plus size={18} />行を追加</button>
              <button onClick={() => setActiveModal("import")}><UploadSimple size={18} />文章を取込</button>
            </div>
            <div className="line-navigator" aria-label="台本の行一覧">
              {project.lines.map((line, index) => {
                const voice = project.voices.find((item) => item.id === line.voiceId);
                return (
                  <button key={line.id} className={`nav-line ${selectedLineId === line.id ? "selected" : ""}`} onClick={() => setSelectedLineId(line.id)}>
                    <span className="nav-index">{index + 1}</span>
                    <span className="nav-copy"><strong>{line.text || "未入力の行"}</strong><small><i style={{ backgroundColor: voice?.color }} />{voice?.name || "ボイス未設定"}</small></span>
                    <span className={`nav-status ${line.status} ${line.audioFile && !line.stale ? "ready" : ""}`} />
                  </button>
                );
              })}
            </div>
            <div className="sidebar-voice">
              <span>現在のボイス</span>
              <button onClick={() => setActiveModal("voices")}><i style={{ backgroundColor: selectedVoice?.color }} /><strong>{selectedVoice?.name}</strong><SlidersHorizontal size={18} /></button>
            </div>
          </aside>

          <section className="script-stage">
            <div className="stage-toolbar">
              <div>
                <span className="eyebrow">SCRIPT TIMELINE</span>
                <h1>読み上げ台本</h1>
              </div>
              <div className="transport-controls">
                <label className="playback-volume">
                  <SpeakerHigh size={19} aria-hidden="true" />
                  <span>再生音量</span>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="1"
                    value={playbackVolume}
                    aria-label="再生音量"
                    aria-valuetext={`${playbackVolume}%`}
                    onChange={(event) => {
                      const value = Number(event.target.value);
                      setPlaybackVolume(value);
                      localStorage.setItem(PLAYBACK_VOLUME_KEY, JSON.stringify({ value }));
                    }}
                  />
                  <output>{playbackVolume}%</output>
                </label>
                <button className="secondary-button" onClick={generateAllMissing} disabled={!model.loaded || queueCount > 0}><MagicWand size={19} />未生成を作る</button>
                {sequenceActive || speakingLineId ? (
                  <button className="stop-button" onClick={stopPlayback}><Stop size={19} weight="fill" />停止</button>
                ) : (
                  <button className="play-from-button" onClick={() => selectedLine && playFrom(selectedLine.id)} disabled={!selectedLine}><Play size={19} weight="fill" />ここから連続再生</button>
                )}
              </div>
            </div>

            <div className="line-list">
              {project.lines.map((line, index) => {
                const voice = project.voices.find((item) => item.id === line.voiceId) || project.voices[0];
                const selected = selectedLineId === line.id;
                const speaking = speakingLineId === line.id;
                return (
                  <article
                    key={line.id}
                    className={`script-line ${selected ? "selected" : ""} ${speaking ? "speaking" : ""}`}
                    onClick={() => { setSelectedLineId(line.id); setSelectedVoiceId(line.voiceId); }}
                    draggable
                    onDragStart={() => setDraggedLineId(line.id)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={() => handleDrop(line.id)}
                  >
                    <button className="drag-handle" type="button" aria-label="ドラッグして並び替え"><DotsSixVertical size={20} /></button>
                    <span className="line-number">{speaking ? <SpeakerHigh size={21} weight="fill" /> : index + 1}</span>
                    <div className="line-content">
                      <div className="text-editor-shell">
                        <textarea
                          ref={(node) => {
                            if (node) lineTextRefs.current.set(line.id, node);
                            else lineTextRefs.current.delete(line.id);
                          }}
                          value={line.text}
                          rows={Math.max(1, Math.min(3, Math.ceil((line.text.length || 1) / 42)))}
                          placeholder="読み上げる文章を入力"
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
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={(event) => openEmojiPicker(event, { kind: "line", id: line.id })}
                        ><Smiley size={21} /></button>
                      </div>
                      <div className="line-meta">
                        <span className="voice-chip"><i style={{ backgroundColor: voice.color }} />{voice.name}</span>
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
                      <IconButton label="複製" onClick={(event) => { event.stopPropagation(); mutateProject((current) => ({ ...current, lines: duplicateLine(current.lines, line.id) })); }}><Copy size={18} /></IconButton>
                      <IconButton label="現在の設定で新しいテイクを作る" onClick={(event) => { event.stopPropagation(); regenerateLine(line.id); }} disabled={!model.loaded || line.status === "running"}><ArrowsClockwise size={18} /></IconButton>
                      <IconButton label={line.audioFile && !line.stale ? "再生" : "生成して再生"} tone="play" onClick={(event) => { event.stopPropagation(); playLine(line.id); }} disabled={!model.loaded || line.status === "running"}>
                        {line.status === "running" ? <SpinnerGap className="spin" size={19} /> : <Play size={19} weight="fill" />}
                      </IconButton>
                      <a className={`icon-button quiet ${line.audioFile ? "" : "disabled"}`} title="WAVを保存" aria-label="WAVを保存" href={line.audioFile ? audioUrl(line.audioFile) : undefined} download><DownloadSimple size={19} /></a>
                      <IconButton label="削除" tone="danger" onClick={(event) => { event.stopPropagation(); removeLine(line.id); }} disabled={project.lines.length === 1}><Trash size={18} /></IconButton>
                    </div>
                  </article>
                );
              })}
              <button className="add-line-card" onClick={() => addLine(selectedLineId)}><Plus size={19} />選択行の下に追加</button>
            </div>
          </section>
        </main>
      ) : (
        <main className="live-workspace">
          <section className="live-console">
            <div className="live-header">
              <div><span className="eyebrow">LOW-LATENCY QUEUE</span><h1>配信コンソール</h1><p>入力した文章を順番に生成し、完成したものから自動再生します。</p></div>
              <button className="stop-button" onClick={stopLive}><Stop size={19} weight="fill" />発話を止める</button>
            </div>
            <div className="live-composer">
              <div className="live-options">
                <label>ボイス<select value={liveVoiceId} onChange={(event) => setLiveVoiceId(event.target.value)}>{project.voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}</select></label>
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
                  <div><strong>{item.text}</strong><small>{QUALITY_PRESETS[item.preset]?.label} · {formatDuration(item.duration)}</small>{item.error && <small className="line-error">{item.error}</small>}</div>
                  {item.audioFile && <IconButton label="もう一度再生" onClick={() => playAudio(item.audioFile, item.id)}><Play size={18} weight="fill" /></IconButton>}
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

      {activeModal === "model" && <Modal title="Irodori-TTSモデル" eyebrow="LOCAL RUNTIME" onClose={() => setActiveModal(null)} wide>
        <div className="model-layout">
          <section className="form-stack">
            <label><span>チェックポイント</span><div className="path-input"><input list="checkpoint-assets" value={modelSettings.checkpoint} onChange={(event) => setModelSettings({ ...modelSettings, checkpoint: event.target.value })} /><button onClick={() => choosePath("checkpoint", false, ([path]) => setModelSettings({ ...modelSettings, checkpoint: path }))}><FolderOpen size={18} />選択</button></div><datalist id="checkpoint-assets">{bootstrap?.assets?.checkpoints?.map((path) => <option key={path} value={path} />)}</datalist></label>
            <div className="form-grid"><label><span>モデルデバイス</span><select value={modelSettings.modelDevice} onChange={(event) => setModelSettings({ ...modelSettings, modelDevice: event.target.value })}>{(bootstrap?.devices || ["cuda", "cpu"]).map((device) => <option key={device}>{device}</option>)}</select></label><label><span>モデル精度</span><select value={modelSettings.modelPrecision} onChange={(event) => setModelSettings({ ...modelSettings, modelPrecision: event.target.value })}>{(bootstrap?.precisions?.[modelSettings.modelDevice] || ["fp32", "bf16"]).map((precision) => <option key={precision}>{precision}</option>)}</select></label><label><span>Codecデバイス</span><select value={modelSettings.codecDevice} onChange={(event) => setModelSettings({ ...modelSettings, codecDevice: event.target.value })}>{(bootstrap?.devices || ["cuda", "cpu"]).map((device) => <option key={device}>{device}</option>)}</select></label><label><span>Codec精度</span><select value={modelSettings.codecPrecision} onChange={(event) => setModelSettings({ ...modelSettings, codecPrecision: event.target.value })}>{(bootstrap?.precisions?.[modelSettings.codecDevice] || ["fp32", "bf16"]).map((precision) => <option key={precision}>{precision}</option>)}</select></label></div>
            <div className="modal-actions"><button className="secondary-button" onClick={async () => { await api.unloadModel(); setModel({ loaded: false }); }} disabled={!model.loaded || modelLoading}>アンロード</button><button className="primary-button" onClick={handleLoadModel} disabled={modelLoading || !modelSettings.checkpoint}>{modelLoading ? <SpinnerGap className="spin" size={20} /> : <Cpu size={20} />}{modelLoading ? "ロード中…" : "モデルをロード"}</button></div>
          </section>
          <aside className="runtime-summary"><span className={`runtime-icon ${model.loaded ? "loaded" : ""}`}><Cpu size={30} /></span><small>{model.loaded ? "READY" : "NOT LOADED"}</small><h3>{model.loaded ? model.name : "ローカルモデル未選択"}</h3>{model.loaded ? <dl><div><dt>Parameters</dt><dd>{model.parameter_count ? `${(model.parameter_count / 1e6).toFixed(0)}M` : "—"}</dd></div><div><dt>Voice Design</dt><dd>{model.use_caption_condition ? "対応" : "非対応"}</dd></div><div><dt>Speaker</dt><dd>{model.use_speaker_condition ? "対応" : "非対応"}</dd></div><div><dt>Duration</dt><dd>{model.use_duration_predictor ? "自動" : "固定"}</dd></div><div><dt>VRAM</dt><dd>{model.cuda ? `${model.cuda.allocated_gb} GB` : "—"}</dd></div></dl> : <p>チェックポイントと実行デバイスを選び、モデルをメモリへロードしてください。</p>}</aside>
        </div>
      </Modal>}

      {activeModal === "voices" && <Modal title="ボイスライブラリ" eyebrow="VOICE PROFILES" onClose={() => setActiveModal(null)} wide scrollable>
        <div className="voice-layout">
          <aside className="voice-list">
            <button className="add-voice" onClick={() => {
              const voice = {
                ...DEFAULT_VOICE_API,
                id: uid("voice"),
                name: `ボイス ${project.voices.length + 1}`,
                color: VOICE_COLORS[project.voices.length % VOICE_COLORS.length],
                sourceType: "none",
                refEmbed: "",
                refWavs: [],
                loraAdapter: "",
                defaultCaption: "",
              };
              mutateProject((current) => ({ ...current, voices: [...current.voices, voice] }));
              setSelectedVoiceId(voice.id);
            }}><Plus size={18} />ボイスを追加</button>
            {project.voices.map((voice) => <button key={voice.id} className={selectedVoiceId === voice.id ? "active" : ""} onClick={() => setSelectedVoiceId(voice.id)}>
              <i style={{ backgroundColor: voice.color }} />
              <span>
                <strong>{voice.name}</strong>
                <small>{voice.apiEnabled ? `API · ID ${voice.apiStyleId}` : voice.sourceType === "speaker" ? "Speaker Inversion" : voice.sourceType === "reference" ? "参照音声" : "参照なし"}</small>
              </span>
            </button>)}
          </aside>
          {selectedVoice && <section className="voice-editor">
            <div className="voice-name-row">
              <i style={{ backgroundColor: selectedVoice.color }} />
              <input value={selectedVoice.name} onChange={(event) => updateSelectedVoice({ name: event.target.value })} />
              {project.voices.length > 1 && <IconButton
                label={selectedVoice.apiProfileId ? "API登録を削除してからボイスを削除してください" : "このボイスを削除"}
                tone="danger"
                disabled={Boolean(selectedVoice.apiProfileId)}
                onClick={() => {
                  const replacementId = project.voices.find((voice) => voice.id !== selectedVoice.id)?.id;
                  mutateProject((current) => ({
                    ...current,
                    voices: current.voices.filter((voice) => voice.id !== selectedVoice.id),
                    lines: current.lines.map((line) => line.voiceId === selectedVoice.id ? { ...line, voiceId: replacementId, stale: Boolean(line.audioFile) } : line),
                  }));
                  setSelectedVoiceId(replacementId);
                }}
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
                <div><strong>VOICEVOX互換API</strong><small>127.0.0.1:{bootstrap?.voicevox_api?.port || 50021} · 公開中 {serverVoiceProfiles.filter((profile) => profile.enabled).length}スタイル</small></div>
                {selectedVoice.apiStyleId && <span className="style-id-badge">ID {selectedVoice.apiStyleId}</span>}
              </header>
              <label className="api-publish-toggle">
                <input type="checkbox" checked={Boolean(selectedVoice.apiEnabled)} onChange={(event) => updateSelectedVoice({ apiEnabled: event.target.checked })} />
                <span><strong>外部アプリから選べるようにする</strong><small>保存すると 127.0.0.1:{bootstrap?.voicevox_api?.port || 50021} の話者一覧へ反映されます</small></span>
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
                {selectedVoice.apiProfileId && <button className="danger-text-button" onClick={deleteSelectedVoiceProfile}><Trash size={17} />API登録を削除</button>}
                <button className="primary-button" onClick={saveSelectedVoiceProfile}><FloppyDisk size={18} />{selectedVoice.apiEnabled ? "保存してAPIへ公開" : "API設定を保存"}</button>
              </div>
            </div>
          </section>}
        </div>
      </Modal>}

      {activeModal === "import" && <Modal title="文章を台本へ取り込む" eyebrow="TEXT IMPORT" onClose={() => setActiveModal(null)}><p className="modal-description">1行を1つの読み上げ単位として追加します。空行は無視されます。</p><textarea className="large-textarea" rows="12" value={importText} onChange={(event) => setImportText(event.target.value)} placeholder={'最初の文章を入力します。\n次の文章は改行して入力します。'} /><div className="modal-actions"><button className="secondary-button" onClick={() => setActiveModal(null)}>キャンセル</button><button className="primary-button" onClick={() => { const lines = splitImportedText(importText); if (lines.length) { mutateProject((current) => ({ ...current, lines: [...current.lines, ...lines] })); setSelectedLineId(lines[0].id); setImportText(""); setActiveModal(null); notify(`${lines.length}行を追加しました`, "success"); } }} disabled={!importText.trim()}><Plus size={19} />台本へ追加</button></div></Modal>}

      {activeModal === "projects" && <Modal title="プロジェクト" eyebrow="LOCAL PROJECTS" onClose={() => setActiveModal(null)}><div className="project-file-actions"><button onClick={() => importFileRef.current?.click()}><UploadSimple size={19} />JSONを読み込む</button><button onClick={downloadProjectJson}><DownloadSimple size={19} />現在のJSONを保存</button></div><input ref={importFileRef} className="hidden-input" type="file" accept="application/json,.json" onChange={importProjectFile} /> <div className="saved-projects">{savedProjects.length ? savedProjects.map((saved) => <button key={saved.filename} onClick={() => loadSavedProject(saved.name)}><FileText size={21} /><span><strong>{saved.name}</strong><small>{new Date(saved.updated_at * 1000).toLocaleString("ja-JP")}</small></span></button>) : <div className="empty-state"><FolderOpen size={30} /><span>API側に保存されたプロジェクトはまだありません。</span></div>}</div></Modal>}

      {activeModal === "export" && <Modal title="動画・配信用パッケージ" eyebrow="PRODUCTION EXPORT" onClose={() => setActiveModal(null)} wide><div className="export-layout"><section><div className="export-readiness"><span className={staleOrMissing.length ? "warning" : "ready"}>{staleOrMissing.length ? <WarningCircle size={25} /> : <Check size={25} />}</span><div><strong>{staleOrMissing.length ? `${staleOrMissing.length}行の生成が必要です` : "すべて書き出せます"}</strong><p>{generatedCount}/{project.lines.length}行 · 音声 {formatDuration(projectSeconds)}</p></div>{staleOrMissing.length > 0 && <button className="secondary-button" onClick={generateAllMissing} disabled={!model.loaded || queueCount > 0}><MagicWand size={18} />不足分を生成</button>}</div><label className="gap-setting"><span>行間の無音</span><input type="range" min="0" max="2000" step="50" value={project.exportSettings.gapMs} onChange={(event) => mutateProject((current) => ({ ...current, exportSettings: { ...current.exportSettings, gapMs: Number(event.target.value) } }))} /><strong>{project.exportSettings.gapMs} ms</strong></label><div className="export-checks">{[["includeMaster", "連結したmaster.wav", "動画編集・配信素材の完成音声", VideoCamera], ["includeSrt", "SRT字幕", "一般的な動画編集ソフト向け", FileText], ["includeVtt", "WebVTT字幕", "Web配信・プレイヤー向け", FileText], ["includeCsv", "CSVタイムライン", "開始・終了・声・シードを記録", ListNumbers]].map(([key, title, detail, Icon]) => <label key={key}><input type="checkbox" checked={project.exportSettings[key]} onChange={(event) => mutateProject((current) => ({ ...current, exportSettings: { ...current.exportSettings, [key]: event.target.checked } }))} /><Icon size={21} /><span><strong>{title}</strong><small>{detail}</small></span></label>)}</div></section><aside className="package-preview"><span className="package-icon"><Export size={31} /></span><h3>ZIPに含まれるもの</h3><ul><li>行ごとのPCM WAV</li><li>連結済みマスター音声</li><li>SRT / VTT字幕</li><li>CSV / JSONタイムライン</li><li>FFmpeg concatリスト</li><li>再編集可能なプロジェクトJSON</li></ul><button className="primary-button" onClick={exportProduction} disabled={exportBusy || staleOrMissing.length > 0}>{exportBusy ? <SpinnerGap className="spin" size={20} /> : <DownloadSimple size={20} />}{exportBusy ? "準備中…" : "制作パッケージを保存"}</button></aside></div></Modal>}
    </div>
  );
}

export { App };
