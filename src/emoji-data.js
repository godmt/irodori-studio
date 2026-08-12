export const EMOJI_PALETTE = [
  { emoji: "👂", label: "囁き", description: "耳元の音", featured: true },
  { emoji: "😮‍💨", label: "吐息", description: "溜息、寝息", featured: true },
  { emoji: "⏸️", label: "間", description: "沈黙" },
  { emoji: "🤭", label: "笑い", description: "くすくす、含み笑い", featured: true },
  { emoji: "🥵", label: "喘ぎ", description: "うめき声、唸り声" },
  { emoji: "📢", label: "エコー", description: "リバーブ" },
  { emoji: "😏", label: "からかう", description: "甘えるように" },
  { emoji: "🥺", label: "震え声", description: "自信なさげに" },
  { emoji: "🌬️", label: "息切れ", description: "荒い息遣い、呼吸音" },
  { emoji: "😮", label: "息をのむ", description: "Gasp" },
  { emoji: "👅", label: "舐める音", description: "咀嚼音、水音" },
  { emoji: "💋", label: "リップノイズ", description: "Lip smack" },
  { emoji: "🫶", label: "優しく", description: "Tenderly", featured: true },
  { emoji: "😭", label: "泣き声", description: "嗚咽、悲しみ", featured: true },
  { emoji: "😱", label: "悲鳴", description: "叫び、絶叫" },
  { emoji: "😪", label: "眠そう", description: "気だるげに" },
  { emoji: "😴", label: "寝言", description: "いびき" },
  { emoji: "⏩", label: "早口", description: "一気に、急いで", featured: true },
  { emoji: "📞", label: "電話越し", description: "スピーカー越し" },
  { emoji: "🐢", label: "ゆっくり", description: "Slowly", featured: true },
  { emoji: "🥤", label: "飲み込む", description: "唾を飲む音" },
  { emoji: "🤧", label: "咳・鼻", description: "咳き込み、鼻すすり" },
  { emoji: "😒", label: "舌打ち", description: "Tutting" },
  { emoji: "😰", label: "慌てる", description: "動揺、緊張、どもり" },
  { emoji: "😆", label: "喜び", description: "嬉しそうに", featured: true },
  { emoji: "💥", label: "勢いよく", description: "力強い勢い" },
  { emoji: "😠", label: "怒り", description: "不満げ、拗ねる", featured: true },
  { emoji: "😲", label: "驚き", description: "感嘆", featured: true },
  { emoji: "🥱", label: "あくび", description: "Yawn" },
  { emoji: "😖", label: "苦しげ", description: "Agonizingly" },
  { emoji: "😟", label: "心配", description: "不安そうに" },
  { emoji: "🫣", label: "照れ", description: "恥ずかしそうに" },
  { emoji: "🙄", label: "呆れ", description: "Exasperatedly" },
  { emoji: "😊", label: "楽しげ", description: "嬉しそうに" },
  { emoji: "😎", label: "得意げ", description: "自信ありげに" },
  { emoji: "👌", label: "相槌", description: "頷く音" },
  { emoji: "🙏", label: "懇願", description: "お願いするように" },
  { emoji: "🥴", label: "酔う", description: "Drunkenly" },
  { emoji: "🎵", label: "鼻歌", description: "Humming" },
  { emoji: "🤐", label: "口を塞ぐ", description: "Muffled" },
  { emoji: "😌", label: "安堵", description: "満足げに" },
  { emoji: "🤔", label: "疑問", description: "Questioning" },
  { emoji: "💪", label: "力強く", description: "力を込めて" },
  { emoji: "👃", label: "嗅ぐ音", description: "匂いを嗅ぐ音" },
  { emoji: "📖", label: "朗読", description: "ナレーション" },
];

export const FEATURED_EMOJI = EMOJI_PALETTE.filter((item) => item.featured);

export const CAPTION_PRESETS = [
  { id: "neutral", label: "自然", caption: "感情を強調せず、自然な会話の速さと距離で話す" },
  { id: "joy", label: "喜び", caption: "喜びがあふれる、明るく弾む声で楽しそうに話す" },
  { id: "sadness", label: "悲しみ", caption: "深い悲しみを抑えながら、低く弱い声で静かに話す" },
  { id: "anger", label: "怒り", caption: "強い怒りと不満を込め、鋭くはっきりした口調で話す" },
  { id: "surprise", label: "驚き", caption: "予想外の出来事に驚き、感嘆を込めて大きく反応する" },
  { id: "whisper", label: "囁き", caption: "すぐ近くの相手だけに届く、息を抑えた静かな囁き声で話す" },
  { id: "tender", label: "優しく", caption: "相手を安心させるように、包み込むような優しい声で話す" },
  { id: "fast", label: "早口", caption: "明瞭さを保ちながら、内容を急いで伝えるようにテンポよく話す" },
  { id: "relaxed", label: "穏やか", caption: "肩の力を抜き、落ち着いた柔らかな声でゆったり話す" },
];

export function insertAtSelection(text, insertion, selectionStart, selectionEnd) {
  const source = String(text ?? "");
  const start = Number.isInteger(selectionStart) ? Math.max(0, Math.min(selectionStart, source.length)) : source.length;
  const end = Number.isInteger(selectionEnd) ? Math.max(start, Math.min(selectionEnd, source.length)) : start;
  return {
    text: `${source.slice(0, start)}${insertion}${source.slice(end)}`,
    caret: start + insertion.length,
  };
}
