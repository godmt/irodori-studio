import { useEffect, useId } from "react";
import { CaretDown, X } from "@phosphor-icons/react";

export function IconButton({ label, children, tone = "quiet", className = "", ...props }) {
  return (
    <button
      className={`icon-button ${tone} ${className}`}
      type="button"
      title={label}
      aria-label={label}
      {...props}
    >
      {children}
    </button>
  );
}

export function Modal({ title, eyebrow, onClose, children, wide = false, scrollable = false }) {
  const modalId = useId();
  useEffect(() => {
    const closeOnEscape = (event) => {
      const dialogs = document.querySelectorAll("[data-studio-modal]");
      if (event.key === "Escape" && document.body.classList.contains("studio-sorting")) return;
      if (event.key === "Escape" && dialogs[dialogs.length - 1]?.getAttribute("data-studio-modal") === modalId) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className={`modal-card ${wide ? "wide" : ""} ${scrollable ? "scrollable" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        data-studio-modal={modalId}
        onMouseDown={(event) => event.stopPropagation()}
      >
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

export function NameDialog({
  title,
  eyebrow = "NAME",
  description,
  label,
  value,
  onChange,
  onSubmit,
  onClose,
  submitLabel,
  busy = false,
  disabled = false,
  maxLength = 120,
  error = "",
}) {
  const descriptionId = useId();
  return (
    <Modal title={title} eyebrow={eyebrow} onClose={() => !busy && onClose()}>
      <form
        className="resource-name-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy && !disabled) onSubmit();
        }}
      >
        {description && <p id={descriptionId} className="resource-dialog-description">{description}</p>}
        <label>
          <span>{label}</span>
          <input
            autoFocus
            value={value}
            maxLength={maxLength}
            aria-describedby={description ? descriptionId : undefined}
            onChange={(event) => onChange(event.target.value)}
          />
        </label>
        {error && <p className="resource-dialog-error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>キャンセル</button>
          <button className="primary-button" type="submit" disabled={busy || disabled}>{busy ? "処理中…" : submitLabel}</button>
        </div>
      </form>
    </Modal>
  );
}

export function ConfirmDialog({
  title,
  eyebrow = "CONFIRM",
  description,
  confirmLabel = "削除",
  onConfirm,
  onClose,
  busy = false,
  danger = true,
}) {
  return (
    <Modal title={title} eyebrow={eyebrow} onClose={() => !busy && onClose()}>
      <p className="resource-dialog-description">{description}</p>
      <div className="modal-actions">
        <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>キャンセル</button>
        <button className={danger ? "danger-button" : "primary-button"} type="button" onClick={onConfirm} disabled={busy}>{busy ? "処理中…" : confirmLabel}</button>
      </div>
    </Modal>
  );
}

export function VoiceSelect({ voices, value, onChange, label, disabled = false, className = "" }) {
  const selected = voices.find((voice) => voice.id === value) || voices[0];
  return (
    <label className={`voice-select ${className}`}>
      <i style={{ backgroundColor: selected?.color }} aria-hidden="true" />
      <select value={selected?.id || ""} onChange={(event) => onChange(event.target.value)} aria-label={label} disabled={disabled}>
        {voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}
      </select>
      <CaretDown size={14} aria-hidden="true" />
    </label>
  );
}
