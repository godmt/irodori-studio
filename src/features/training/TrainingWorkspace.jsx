import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Brain,
  CheckCircle,
  ClockCounterClockwise,
  Cpu,
  Database,
  FolderOpen,
  HardDrive,
  Lightning,
  MagicWand,
  PencilSimple,
  Plus,
  SpinnerGap,
  Stop,
  Trash,
  WarningCircle,
  Waveform,
} from "@phosphor-icons/react";

import { api } from "../../api.js";
import { ConfirmDialog, IconButton, NameDialog } from "../../components/StudioUI.jsx";
import "./training.css";

const ACTIVE_STATUSES = new Set(["queued", "preparing", "training", "cancelling"]);

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(value / 60);
  const remainder = Math.round(value % 60);
  return `${minutes}分${String(remainder).padStart(2, "0")}秒`;
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

function statusLabel(status) {
  return {
    queued: "開始待ち",
    preparing: "データ準備中",
    training: "学習中",
    cancelling: "停止中",
    cancelled: "停止済み",
    completed: "完了",
    failed: "失敗",
    interrupted: "中断",
  }[status] || status;
}

function methodLabel(method) {
  return method === "lora" ? "LoRA" : "Speaker Inversion";
}

function MethodCard({ active, icon, title, badge, description, details, onClick }) {
  return (
    <button type="button" className={`training-method-card ${active ? "active" : ""}`} onClick={onClick}>
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

export function TrainingWorkspace({ bootstrap, notify, onModelUnloaded }) {
  const [datasets, setDatasets] = useState(() => bootstrap?.recording_datasets || []);
  const [jobs, setJobs] = useState(() => bootstrap?.training_jobs || []);
  const [trainedModels, setTrainedModels] = useState(() => bootstrap?.trained_models || []);
  const [name, setName] = useState("");
  const [datasetId, setDatasetId] = useState(() => bootstrap?.recording_datasets?.[0]?.id || "");
  const [method, setMethod] = useState("speaker_inversion");
  const [checkpoint, setCheckpoint] = useState(() => bootstrap?.default_checkpoint || "");
  const [device, setDevice] = useState(() => bootstrap?.default_device || "cuda");
  const [precision, setPrecision] = useState("bf16");
  const [maxSteps, setMaxSteps] = useState(3000);
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [renameModelTarget, setRenameModelTarget] = useState(null);
  const [renameModelName, setRenameModelName] = useState("");
  const [deleteModelTarget, setDeleteModelTarget] = useState(null);
  const [deleteJobTarget, setDeleteJobTarget] = useState(null);

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === datasetId) || null,
    [datasetId, datasets],
  );
  const activeJob = useMemo(() => jobs.find((job) => ACTIVE_STATUSES.has(job.status)), [jobs]);
  const refresh = useCallback(async ({ quiet = false } = {}) => {
    try {
      const [nextDatasets, nextJobs, nextModels] = await Promise.all([api.recordingDatasets(), api.trainingJobs(), api.trainedModels()]);
      setDatasets(nextDatasets);
      setJobs(nextJobs);
      setTrainedModels(nextModels);
      setDatasetId((current) => (
        nextDatasets.some((dataset) => dataset.id === current) ? current : nextDatasets[0]?.id || ""
      ));
    } catch (error) {
      if (!quiet) notify(error.message, "error");
    }
  }, [notify]);

  useEffect(() => {
    refresh({ quiet: true });
  }, [refresh]);

  useEffect(() => {
    if (!checkpoint && bootstrap?.default_checkpoint) setCheckpoint(bootstrap.default_checkpoint);
  }, [bootstrap?.default_checkpoint, checkpoint]);

  useEffect(() => {
    if (!jobs.some((job) => ACTIVE_STATUSES.has(job.status))) return undefined;
    const timer = window.setInterval(() => refresh({ quiet: true }), 1500);
    return () => window.clearInterval(timer);
  }, [jobs, refresh]);

  useEffect(() => {
    if (method === "speaker_inversion") setMaxSteps(3000);
    else setMaxSteps(30000);
  }, [method]);

  useEffect(() => {
    const available = bootstrap?.precisions?.[device] || ["fp32"];
    if (!available.includes(precision)) setPrecision(available[0]);
  }, [bootstrap?.precisions, device, precision]);

  const startTraining = async () => {
    if (!name.trim()) {
      notify("モデル名を入力してください", "error");
      return;
    }
    if (!selectedDataset) {
      notify("録音データセットを選択してください", "error");
      return;
    }
    if (!selectedDataset.accepted) {
      notify("採用済みの録音がありません", "error");
      return;
    }
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

  const stopTraining = async (job) => {
    try {
      const updated = await api.cancelTrainingJob(job.id);
      setJobs((current) => current.map((item) => item.id === updated.id ? updated : item));
      notify("学習の停止を受け付けました");
    } catch (error) {
      notify(error.message, "error");
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

  const paths = bootstrap?.training_paths || {
    speaker_embeddings: "workspace/models/speaker-embeddings",
    lora_adapters: "workspace/models/lora",
  };

  return (
    <>
    <main className="training-workspace">
      <section className="training-main">
        <header className="training-header">
          <div><span className="eyebrow">VOICE TRAINING</span><h1>学習スタジオ</h1><p>録音データから名前付きのボイスモデルを作成します。</p></div>
          <span className="training-local-badge"><HardDrive size={19} /><span><small>LOCAL TRAINING</small><strong>すべてこのPCに保存</strong></span></span>
        </header>

        <div className="training-scroll">
          <section className="training-setup-card">
            <div className="training-section-title"><span>1</span><div><h2>モデルを名付ける</h2><p>完成後もボイスライブラリで識別できる名前にします。</p></div></div>
            <label className="training-name-field"><span>モデル名</span><input value={name} maxLength={80} placeholder="例：春日部つむぎ ナレーション" onChange={(event) => setName(event.target.value)} /></label>
          </section>

          <section className="training-setup-card">
            <div className="training-section-title"><span>2</span><div><h2>録音データを選ぶ</h2><p>元録音を保持したまま、採用済み音声の学習用コピーを整えます。</p></div></div>
            {datasets.length ? <>
              <label className="training-dataset-select"><Database size={23} /><span><small>録音データセット</small><select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></span></label>
              {selectedDataset && <div className="training-dataset-summary"><div><strong>{selectedDataset.accepted}</strong><span>採用済み</span></div><div><strong>{formatDuration(selectedDataset.accepted_seconds)}</strong><span>収録時間</span></div><div><strong>{selectedDataset.recorded}</strong><span>録音済み</span></div><p>{selectedDataset.accepted ? "採用済み音声だけを使います。元の録音は変更しません。" : "録音スタジオで音声を採用すると学習できます。"}</p></div>}
              <div className="training-preprocessing-note"><MagicWand size={22} /><div><strong>学習前に自動で整えます</strong><span>冒頭・末尾の無音を、発話前後に180msの余白を残してカット</span><span>音量を-16 dBへ正規化してからlatentへ変換</span><small>文中の間や演技上の沈黙、元の録音WAVは変更しません。</small></div></div>
            </> : <div className="training-empty-dataset"><Database size={28} /><div><strong>録音データセットがありません</strong><span>先に録音タブでデータセットを作成し、音声を採用してください。</span></div></div>}
          </section>

          <section className="training-setup-card">
            <div className="training-section-title"><span>3</span><div><h2>学習方法を選ぶ</h2><p>通常はSpeaker Inversionが適しています。</p></div></div>
            <div className="training-methods">
              <MethodCard active={method === "speaker_inversion"} icon={<Waveform size={25} />} title="Speaker Inversion" badge="おすすめ" description="話者らしさだけを小さな埋め込みとして学習します。" details="軽量 · 短時間 · 基本モデルは変更しません" onClick={() => setMethod("speaker_inversion")} />
              <MethodCard active={method === "lora"} icon={<Brain size={25} />} title="LoRA" description="声質と発話傾向をモデルへ追加学習します。" details="上級者向け · より多くの録音と時間が必要です" onClick={() => setMethod("lora")} />
            </div>
          </section>

          <section className="training-setup-card compact">
            <button className="training-advanced-toggle" type="button" onClick={() => setAdvanced((value) => !value)}><Cpu size={20} /><span><strong>学習設定</strong><small>{device} · {precision} · {maxSteps.toLocaleString()} steps</small></span><Plus size={18} className={advanced ? "open" : ""} /></button>
            {advanced && <div className="training-advanced-fields">
              <label><span>基本モデル</span><div className="training-path-input"><input value={checkpoint} onChange={(event) => setCheckpoint(event.target.value)} /><button type="button" onClick={() => api.dialog("checkpoint").then(({ paths: selected }) => selected[0] && setCheckpoint(selected[0])).catch((error) => notify(error.message, "error"))}><FolderOpen size={18} />選択</button></div></label>
              <label><span>デバイス</span><select value={device} onChange={(event) => setDevice(event.target.value)}>{(bootstrap?.devices || ["cuda", "cpu"]).map((item) => <option key={item}>{item}</option>)}</select></label>
              <label><span>精度</span><select value={precision} onChange={(event) => setPrecision(event.target.value)}>{(bootstrap?.precisions?.[device] || ["bf16", "fp32"]).map((item) => <option key={item}>{item}</option>)}</select></label>
              <label><span>学習ステップ</span><input type="number" min="1" max="1000000" value={maxSteps} onChange={(event) => setMaxSteps(Number(event.target.value))} /></label>
            </div>}
          </section>

          <button className="training-start-button" type="button" onClick={startTraining} disabled={busy || Boolean(activeJob) || !selectedDataset?.accepted || !name.trim()}>{busy ? <SpinnerGap className="spin" size={22} /> : <Lightning size={22} weight="fill" />}<span><strong>{methodLabel(method)}を開始</strong><small>実行中は読み上げモデルをGPUから解放します</small></span></button>
        </div>
      </section>

      <aside className="training-side-panel">
        <header><div><small>TRAINING RUNS</small><h2>学習とモデル</h2></div><span>{jobs.length}</span></header>
        {activeJob && <article className="training-active-card">
          <div className="training-job-heading"><span className="training-job-spinner"><SpinnerGap className="spin" size={22} /></span><div><small>{statusLabel(activeJob.status)}</small><strong>{activeJob.name}</strong><span>{methodLabel(activeJob.method)} · {activeJob.dataset_name}</span></div></div>
          <div className="training-progress"><span style={{ width: `${activeJob.progress || 0}%` }} /></div>
          <div className="training-progress-meta"><span>{activeJob.stage === "preparing" ? "音声を変換中" : `${Number(activeJob.step || 0).toLocaleString()} / ${Number(activeJob.max_steps || 0).toLocaleString()} steps`}</span><strong>{activeJob.progress || 0}%</strong></div>
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
            <span className="training-history-icon">{job.status === "completed" ? <CheckCircle size={21} weight="fill" /> : job.status === "failed" ? <WarningCircle size={21} /> : <ClockCounterClockwise size={21} />}</span>
            <div><strong>{job.name}</strong><span>{methodLabel(job.method)} · {statusLabel(job.status)}</span><small>{formatDate(job.updated_at)}{job.asset_path ? ` · 保存済み` : ""}</small></div>
            {!ACTIVE_STATUSES.has(job.status) && <IconButton label={`${job.name}の履歴を削除`} tone="danger" onClick={() => setDeleteJobTarget(job)}><Trash size={17} /></IconButton>}
          </article>)}
          {!jobs.length && !trainedModels.length && <div className="training-empty-history"><Brain size={32} /><strong>まだ学習履歴はありません</strong><span>設定を選び、最初のモデルを作成してください。</span></div>}
        </div>

        <section className="training-storage-card"><HardDrive size={21} /><div><strong>Studioのモデル保存先</strong><span>Speaker Inversion</span><code>{paths.speaker_embeddings}</code><span>LoRA</span><code>{paths.lora_adapters}</code></div></section>
        {trainedModels.length > 0 && <p className="training-model-count"><CheckCircle size={18} />利用可能な学習済みモデル {trainedModels.length}件</p>}
      </aside>
    </main>

    {renameModelTarget && <NameDialog
      title="学習済みモデル名を変更"
      eyebrow="TRAINED MODEL"
      description="ボイスライブラリで選択するときの表示名を変更します。学習結果と元の録音データはそのまま維持されます。"
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
      description="学習済みモデルのファイルを削除します。ボイスライブラリで使用中の場合は、誤って壊さないよう削除を停止します。"
      onConfirm={() => deleteModel(deleteModelTarget)}
      onClose={() => setDeleteModelTarget(null)}
      busy={busy}
    />}

    {deleteJobTarget && <ConfirmDialog
      title={`「${deleteJobTarget.name}」の履歴を削除しますか？`}
      eyebrow="DELETE TRAINING RUN"
      description="学習ログと一時ファイルを削除します。完成済みの学習済みモデルは削除されません。"
      onConfirm={() => deleteJob(deleteJobTarget)}
      onClose={() => setDeleteJobTarget(null)}
      busy={busy}
    />}
    </>
  );
}
