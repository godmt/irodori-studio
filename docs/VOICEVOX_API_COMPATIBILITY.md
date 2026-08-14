# VOICEVOX互換API

Irodori Studioは、VOICEVOX HTTP APIの一般的な読み上げ経路に対応するローカル互換APIを提供します。この文書は`studio_backend/voicevox_api.py`と`tests/test_voicevox_api.py`を正本として、現在実装されている範囲だけを記載します。

## 起動とランタイム

- 既定URL: `http://127.0.0.1:50021`
- アダプターバージョン: `1.0.0`
- Studio APIと同じプロセスで起動し、同じ`StudioEngine`、常駐モデル、FIFO合成キューを共有します。
- `start-studio.ps1 -VoicevoxPort <port>`でポートを変更できます。
- `start-studio.ps1 -NoVoicevoxApi`で互換APIを起動しない構成にできます。
- モデルのロード中・未ロード時、`/synthesis`は`503`を返します。

## ボイスの正本

公開ボイスは、Studio共通の`workspace/voices/profiles.json`に保存されるボイスライブラリです。ボイス画面の「外部アプリから選べるようにする」を有効にしたプロフィールだけを公開します。

- `profile_id`はStudio内の安定参照です。
- `speaker_uuid`と`style_id`はプロフィール削除まで維持します。
- Speaker Inversion、参照音声、参照なし、LoRA、既定caption、API話速、生成ステップ、seed、CFGを合成ペイロードへ反映します。
- ローカルのモデル・音声パスは話者探索レスポンスへ含めません。

旧`workspace/voicevox/profiles.json`は、共有ライブラリがまだ存在しない場合だけ初回起動時にコピーされます。以後の正本ではありません。

## 実装済みエンドポイント

| メソッドとパス | 現在の動作 |
| --- | --- |
| `GET /` | エンジン名を返す |
| `GET /version` | アダプターバージョンを返す |
| `GET /core_versions` | 対応バージョン配列を返す |
| `GET /supported_devices` | CPU、CUDA、DirectMLの利用状態を返す |
| `GET /engine_manifest` | Irodori-TTS名と対応機能を返す |
| `GET /speakers` | 公開済みプロフィールを話者・スタイルとして返す |
| `GET /speaker_info` | ポリシーと最小リソース情報を返す |
| `GET /singers` | 空配列を返す |
| `GET /presets` | 公開済みプロフィールのAPI設定をプリセットとして返す |
| `POST /audio_query` | 通常テキストから互換`AudioQuery`を作る |
| `POST /audio_query_from_preset` | 公開プリセットから互換`AudioQuery`を作る |
| `POST /initialize_speaker` | スタイルの存在を検証するno-op |
| `GET /is_initialized_speaker` | 公開スタイルなら`true`を返す |
| `POST /synthesis` | 共有FIFOキューで生成し、WAVを同期応答する |
| `GET /openapi.json`、`GET /docs` | FastAPIが現在のスキーマを公開する |

一覧にないVOICEVOX APIは実装していません。存在確認用の成功レスポンスを偽装せず、通常は`404`になります。

## テキストとAudioQuery

Irodori-TTSは通常の文章を直接入力するため、`/audio_query`は元テキストを次の2箇所へ保持します。

- `kana`
- `irodori.text`

`/synthesis`は`irodori.text`を優先し、なければ`kana`を読みます。`accent_phrases`はクライアントのスキーマ互換用に最小構造を返しますが、モーラ編集結果からIrodoriの読み上げ文を再構成しません。

- 空文は`422`
- 1000文字を超える文章は`413`
- 未公開または未知の`style_id`は`404`

## 反映するパラメータ

| `AudioQuery` | 処理 |
| --- | --- |
| `speedScale` | Irodori話速へ変換し、0.5～2.0に制限 |
| `volumeScale` | 生成後に0～4倍のゲインを適用し、クリップ範囲へ制限 |
| `prePhonemeLength` | 生成WAVの先頭へ0～10秒の無音を追加 |
| `postPhonemeLength` | 生成WAVの末尾へ0～10秒の無音を追加 |
| `outputSamplingRate` | 8,000～192,000 Hzへリサンプル |
| `outputStereo` | モノラルを左右同一の2チャンネルへ変換 |

返却形式はPCM 16-bit WAVです。`pitchScale`、`intonationScale`、`pauseLength`、`pauseLengthScale`は受理しますが音声へ反映しません。非既定値が指定された場合は`X-Irodori-Ignored-Parameters`レスポンスヘッダーで通知します。

## キュー、タイムアウト、レスポンス

- 既定の同時キュー上限は実行中を含め16件で、上限時は`429`です。
- 合成完了の待機上限は300秒で、超過時は`504`です。
- 生成失敗は`500`、取消は`409`です。
- WAVには`Cache-Control: no-store`と`X-Irodori-Adapter-Version`を付けます。

## セキュリティ

認証機能はありません。既定のlisten先は`127.0.0.1`で、LANやインターネットへの公開用途ではありません。CORSはlocalhost、127.0.0.1、`app://`、Chrome拡張Originを対象にします。

## 現在の自動テスト範囲

`tests/test_voicevox_api.py`は次を検証します。

- 公開スタイルの探索、非公開スタイルの除外、未知スタイルのエラー
- 日本語・演技記号を保持する`audio_query`往復
- ボイス設定から合成ペイロードへの変換
- サンプルレート、ステレオ、前後無音、PCM 16-bit WAV
- UTF-8 JSON Content-Typeとアダプターバージョンヘッダー

実クライアント固有の互換性、キュー飽和、タイムアウト、モデルロード状態は別途結合試験が必要です。
