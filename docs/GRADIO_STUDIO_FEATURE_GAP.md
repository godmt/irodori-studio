# Gradio UI と Irodori Studio の機能差分

比較対象は、このリポジトリの `gradio_app.py` と `irodori-studio/` です。Gradio UI は一回の生成実験、Studio は台本・配信・動画制作を継続して行う用途に重心があります。

## 両方にある機能

| 領域 | Gradio UI | Studio |
| --- | --- | --- |
| モデル | checkpoint、モデル/codec の device と precision、ロード/アンロード | 同等。ロード状態を常時表示 |
| 話者条件 | 複数参照音声、Speaker embedding、参照なし | 同等。さらにボイス定義として保存可能 |
| LoRA | adapter directory | ボイス定義ごとに保存可能 |
| 基本生成 | テキスト、ステップ数、seed、話速相当の duration scale | テキスト、品質プリセット/ステップ数、seed、話速 |
| CFG | Text/Speaker、Independent/Joint/Alternating | Text/Speaker/Caption、同じ3方式 |
| スケジュール | Linear/Sway、sway coefficient | 同等 |
| 一部の詳細設定 | Truncation、Speaker KV scale/min t、Context KV cache | payload は同等項目の一部に対応。通常UIは簡略化 |
| 演技記号 | 公式45種の絵文字パレット | 公式45種。本文内の顔アイコンからカーソル位置へ挿入 |

## Gradio UI にだけある機能（今後の判断対象）

| 機能 | 現状 | Studioへ入れる場合の判断材料 |
| --- | --- | --- |
| 1回で1～32候補を生成 | Studioは行ごとに最大4テイクを順次生成・保持 | Studioは一括バッチ候補ではなく、更新ボタンで1つずつ試し、採用テイクを切り替える制作向け方式。最大32候補の研究比較は未対応 |
| 秒数の手動指定 | Studioは自動尺 | 動画の厳密な尺合わせには有用。自然さを壊しやすいため詳細設定向き |
| CFG Scale Override | StudioはText/Caption/Speakerを個別指定 | 旧互換の一括上書き。個別指定より意図が曖昧なので優先度は低い |
| CFG Min t / Max t | Studio UIなし | 研究・追い込み調整向け。通常利用では露出させず上級設定が妥当 |
| Rescale k / sigma | Studio UIなし | 2値を組で扱う上級設定。プリセット化または上級設定向き |
| Speaker KV Max Layers | Studio UIなし | 話者寄せの研究調整向け。通常の制作UXでは低優先 |
| Context KV Cache の明示切替 | Studioは既定で有効 | デバッグ以外は通常オンでよく、UI露出の価値は小さい |
| 最大120 steps | Studioは80 steps | 極端な高品質比較用。実用上の時間対効果を確認してから上限変更 |
| 実行ログ・段階別Timing | Studioは状態、生成秒数、エラー表示 | 不具合調査と速度比較には有用。「診断パネル」として追加候補 |
| ブラウザへの直接ファイルupload | StudioはOSのローカルファイル選択 | Studioはローカル専用なので現方式が自然。変更優先度は低い |

## Studio にだけある機能

| 領域 | Studioの機能 |
| --- | --- |
| 台本編集 | 複数行、追加、削除、複製、ドラッグ並び替え、行単位再生/再生成 |
| テイク管理 | 行ごとに最大4テイク、更新アイコンで追加、番号で採用テイクを選択。再生・保存・連続再生・書き出しは選択テイクを使用 |
| 連続再生 | 任意の選択位置から生成しながら連続再生、停止 |
| 永続化 | プロジェクト作成・保存・切替・削除、ブラウザ自動保存 |
| ボイスライブラリ | Speaker Inversion/参照音声/参照なし/LoRA、既定captionを名前付き保存 |
| Voice Design | 行別caption、9種の演技プリセット、Caption CFG |
| 配信 | 低遅延FIFOキュー、自動再生、中断、発話履歴、台本制作と連動する再生音量・出力デバイス選択 |
| 外部連携 | VOICEVOX互換API、永続するSpeaker/Style ID、外部アプリ用ボイス公開 |
| 動画制作 | 行別WAV、結合WAV、SRT、VTT、CSV、JSON、FFmpeg concat list |
| 制作状態 | 未生成/生成中/生成済み/要再生成/失敗、キュー数、GPU状態 |

## 今回 Studio へ組み込んだ演技UI

- 台本各行と配信入力欄の右側に、SNSの入力欄に近い顔アイコンを配置。
- 押すと「よく使う10種」を表示し、そこから公式45種すべてへ展開可能。
- 選んだ演技記号はフォーカスを失う前のカーソル位置、または選択範囲へ挿入。
- 行全体の演技を指定する9種のcaptionプリセットを追加。自由入力で微調整可能。
- 本文の絵文字とcaptionは別々の条件として同時に送信。
- 配信コンソールとVOICEVOX互換APIから入る絵文字も除去せずIrodoriへ渡す。

## 次に判断すると効果が大きい候補

1. 診断パネル（実行ログ、モデル/codec/総処理時間）。
2. 動画尺合わせ用の手動秒数。通常は閉じた詳細設定に置く。
3. CFG時間範囲、Rescale、Speaker KV layersをまとめた「研究者向け設定」。

通常の制作画面へ常時出す情報は増やさず、次は診断情報を必要なときだけ開く構成にするのが、StudioのUXとGradioの探索能力を両立しやすい構成です。
