export const SILENT_PLAYBACK_PRIMER = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQQAAACAgICA";

export function shouldRetryWithSystemOutput(error, sinkId) {
  if (!sinkId) return false;
  return !["NotAllowedError", "AbortError"].includes(error?.name);
}

export function playbackFailureMessage(error) {
  if (error?.name === "NotAllowedError") {
    return "ブラウザーが自動再生を止めました。発話履歴の再生ボタンを押してください";
  }
  if (error?.name === "NotFoundError" || error?.name === "NotReadableError") {
    return "選択中の音声出力を使用できませんでした";
  }
  if (error?.name === "NotSupportedError") {
    return "生成した音声をこのブラウザーで再生できませんでした";
  }
  const detail = typeof error?.message === "string" ? error.message.trim() : "";
  return detail ? `音声を再生できませんでした: ${detail}` : "音声を再生できませんでした";
}
