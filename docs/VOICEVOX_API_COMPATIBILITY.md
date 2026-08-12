# Irodori-TTS VOICEVOX API互換アダプター設計

## 1. ステータス

- 状態: 初期版実装済み（Level 1・2、およびLevel 3の一部）
- 対象: Irodori Studioのローカル実行環境
- 互換ターゲット: VOICEVOX ENGINE 0.25.2のHTTP API
- アダプターバージョン: `1.0.0`から開始
- 既定の公開先: `http://127.0.0.1:50021`

VOICEVOX ENGINEの中核APIである`/audio_query`と`/synthesis`へ対応し、話者探索に使われる周辺APIも実装する。Irodori-TTSをVOICEVOXとして偽装するのではなく、エンジン名を明示したVOICEVOX API互換エンジンとして提供する。

参照仕様:

- [VOICEVOX ENGINE API](https://voicevox.github.io/voicevox_engine/api/)
- [VOICEVOX ENGINE](https://github.com/VOICEVOX/voicevox_engine)
- [AivisSpeech EngineのVOICEVOX API互換性](https://github.com/Aivis-Project/AivisSpeech-Engine#voicevox-api-%E3%81%A8%E3%81%AE%E4%BA%92%E6%8F%9B%E6%80%A7%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6)

## 2. 判断

この方式を本命とする価値がある。

- わんコメ専用プラグインを必要としない。
- わんコメ自身が生成WAVの再生、出力デバイス、音量、速度、読み上げ待機上限を管理できる。
- VOICEVOX APIの接続先を変更できる他のアプリからも利用できる。
- Irodori Studioのブラウザを開いたままにする必要がない。
- OBSには、クライアントのアプリ音声または仮想オーディオデバイス経由で入力できる。
- Studioと互換APIが同じモデル常駐ランタイムとFIFO生成キューを共有できる。

ただし、VOICEVOX API全体が固定されたわけではない。中核の2段階合成は安定している一方、`pauseLength`、カタカナ英語、リソースURL、音声ライブラリ管理などは後から追加されている。互換バージョンを明示し、契約テストを持つ。

## 3. ゴールと非ゴール

### ゴール

1. VOICEVOX API対応クライアントが、接続先をIrodoriへ変更するだけで話者一覧の取得と音声合成を行える。
2. Irodori Studioと互換APIでモデルを二重ロードしない。
3. Speaker Inversion、参照音声、LoRA、Voice Design captionを「話者スタイル」として永続化する。
4. 標準的な速度、音量、前後無音、サンプルレート、モノラル／ステレオ指定を反映する。
5. API差異を機能マニフェストと文書で正直に公開する。
6. ループバック限定を既定とし、ローカルAPIとして安全に動かす。

### 非ゴール

- VOICEVOXの名称、キャラクター、アイコン、音声資産を含めない。
- Irodoriに存在しないモーラ単位の音高・音素長編集を再現しない。
- 初期版では歌唱、モーフィング、音声ライブラリの導入機能を実装しない。
- 初期版ではVOICEVOXユーザー辞書のアクセント規則を再現しない。
- APIサーバー自身は再生しない。WAVを受け取ったクライアントが再生する。

## 4. 全体構成

```text
VOICEVOX対応アプリ
  │  HTTP :50021
  ▼
VOICEVOX Compatibility App
  ├─ APIスキーマ変換
  ├─ 話者スタイル解決
  ├─ 同期応答への変換
  └─ WAV後処理
          │
          ▼
共有 StudioEngine
  ├─ モデル常駐ランタイム
  ├─ FIFO生成キュー
  └─ Irodori-TTS推論
          ▲
          │
Irodori Studio API / SPA :8765
```

`127.0.0.1:8765`は既存Studio APIとSPAのまま維持する。`127.0.0.1:50021`に互換専用ASGIアプリを追加し、同一プロセス内の`StudioEngine`を共有する。

互換APIはアプリファクトリーとして実装し、Studioサーバーと同じプロセスから起動する。

```text
create_voicevox_app(engine, profile_store)
run_studio_host(studio_port=8765, voicevox_port=50021)
```

VOICEVOX本体などが50021番を使用中なら起動時に明確なエラーを出す。互換ポートはCLIで変更可能にする。

## 5. 互換レベル

### Level 1: 必須合成経路

| API | 動作 |
| --- | --- |
| `POST /audio_query` | 標準`AudioQuery`とIrodori拡張情報を返す |
| `POST /synthesis` | FIFOキューで生成し、完了まで待って`audio/wav`を返す |

### Level 2: クライアント探索

| API | 動作 |
| --- | --- |
| `GET /version` | Irodori互換アダプターのSemVerを返す |
| `GET /speakers` | 公開済みIrodoriボイスとスタイルを返す |
| `GET /speaker_info` | ポリシー、アイコン、サンプル情報を返す |
| `GET /engine_manifest` | エンジン名と対応機能を返す |
| `GET /supported_devices` | 現在のIrodoriランタイムで利用可能なデバイスを返す |
| `GET /core_versions` | 互換用のバージョン配列を返す |
| `GET /` | エンジン名と稼働状態を文字列で返す |
| `GET /openapi.json`、`GET /docs` | 実装している仕様を公開する |

### Level 3: よく使われる追加経路

| API | 初期方針 |
| --- | --- |
| `POST /audio_query_from_preset` | Irodoriプリセットからクエリを作る |
| `GET /presets` | 公開済みプリセット一覧を返す |
| `POST /initialize_speaker` | 互換用no-op。プロファイル検証を行う |
| `GET /is_initialized_speaker` | 利用可能なら`true`を返す |
| `GET /singers` | 空配列を返す |

`/multi_synthesis`と`/cancellable_synthesis`は次版で追加する。わんコメを含む通常の読み上げ経路は`/audio_query`と`/synthesis`を使用する。

### 初期非対応

- `/accent_phrases`、`/mora_data`、`/mora_length`、`/mora_pitch`
- `/morphable_targets`、`/synthesis_morphing`
- 歌唱関連API
- 音声ライブラリ管理API
- ユーザー辞書のアクセント編集API

クライアントが存在確認だけを行う読み取りAPIは、正しい型の空データを返す。実処理を要求するAPIは`501 Not Implemented`と機械可読なエラーコードを返し、成功したように見せない。

## 6. AudioQueryの扱い

VOICEVOXの`AudioQuery`には、`/synthesis`で読み上げる元の通常テキストを保持する標準フィールドがない。VOICEVOXは`accent_phrases`とAquesTalk風の`kana`から合成するが、Irodoriは通常の日本語文章を直接入力する。

初期版ではAivisSpeech Engineと同じ実績のある考え方を採用する。

- `kana`に通常の読み上げテキストを格納する。
- `accent_phrases`はスキーマ互換の表示用データとし、推論には使用しない。
- `irodori`という追加フィールドにも元テキストとリクエストIDを格納する。
- `/synthesis`では`irodori.text`を優先し、存在しなければ`kana`を読む。
- 未知フィールドを削除するクライアントでも`kana`により合成できる。

例:

```json
{
  "accent_phrases": [],
  "speedScale": 1.0,
  "pitchScale": 0.0,
  "intonationScale": 1.0,
  "volumeScale": 1.0,
  "prePhonemeLength": 0.1,
  "postPhonemeLength": 0.1,
  "pauseLength": null,
  "pauseLengthScale": 1.0,
  "outputSamplingRate": 48000,
  "outputStereo": false,
  "kana": "今日はいい天気ですね。",
  "irodori": {
    "schemaVersion": 1,
    "requestId": "...",
    "text": "今日はいい天気ですね。"
  }
}
```

アクセント句を編集するクライアントでは、その編集結果は初期版のIrodori音声へ反映されない。この差異は`engine_manifest`とAPIドキュメントへ表示する。

## 7. 標準パラメータの変換

| AudioQuery | Irodoriでの処理 | 対応 |
| --- | --- | --- |
| `speedScale` | `SynthesisPayload.speed`へ変換し0.5～2.0へ制限 | 対応 |
| `volumeScale` | 生成後に線形ゲインを適用しクリッピングを防止 | 対応 |
| `prePhonemeLength` | WAV先頭へ無音追加 | 対応 |
| `postPhonemeLength` | WAV末尾へ無音追加 | 対応 |
| `outputSamplingRate` | 生成後に線形補間でリサンプル | 対応 |
| `outputStereo` | モノラルを2チャンネルへ複製 | 対応 |
| `pitchScale` | 初期版では無視 | 非対応 |
| `intonationScale` | 初期版では無視 | 非対応 |
| `pauseLength` | 初期版では無視 | 非対応 |
| `pauseLengthScale` | 初期版では無視 | 非対応 |
| `accent_phrases`の編集 | 初期版では無視 | 非対応 |

未対応フィールドも入力スキーマ上は受理し、一般的なクライアントを壊さない。非既定値が指定された場合はサーバーログへ一度だけ警告し、レスポンスに`X-Irodori-Ignored-Parameters`を付ける。

返却WAVは既定で48 kHz、PCM 16-bit、モノラルとする。`outputSamplingRate`と`outputStereo`が指定された場合は従う。

## 8. 話者とスタイル

VOICEVOXの`style_id`を、Irodoriの「公開ボイスプロファイル」へ対応させる。

```json
{
  "schema_version": 1,
  "speakers": [
    {
      "speaker_uuid": "stable-uuid",
      "name": "配信用ボイス",
      "version": "1.0.0",
      "policy": "この音声プロファイルの利用条件",
      "styles": [
        {
          "id": 1000,
          "name": "ノーマル",
          "source_type": "speaker",
          "ref_embed": "C:/path/to/voice.safetensors",
          "default_caption": "落ち着いた自然な話し方",
          "lora_adapter": null,
          "num_steps": 12,
          "seed": null,
          "cfg_scale_text": 3.0,
          "cfg_scale_caption": 3.0,
          "cfg_scale_speaker": 5.0
        }
      ]
    }
  ]
}
```

- Speaker Inversion、参照音声、参照なしのすべてを登録可能にする。
- 配信用の既定はSpeaker Inversionと12 stepsとする。
- `speaker_uuid`と`style_id`は永続化し、設定変更や再起動で変えない。
- 削除した`style_id`は再利用しない。
- ローカルファイルの絶対パスは`/speakers`レスポンスへ含めない。
- 同一人物の「ノーマル」「喜び」「落ち着き」は同じspeakerの別styleにする。
- 別人物は別speakerにする。

ブラウザ`localStorage`だけでは外部APIから参照できないため、Studioのボイス画面に「VOICEVOX APIへ公開」を追加し、`workspace/voicevox/profiles.json`へ保存する。

## 9. 合成処理

`POST /synthesis?speaker={style_id}`の処理順序:

1. `AudioQuery`と`style_id`を検証する。
2. 公開ボイスプロファイルを解決する。
3. `irodori.text`、次に`kana`から読み上げ文を取得する。
4. 標準パラメータを`SynthesisPayload`へ変換する。
5. 既存`StudioEngine`のFIFOキューへ追加する。
6. ジョブ完了までHTTP要求を待機させる。
7. 音量、前後無音、サンプルレート、チャンネル数を後処理する。
8. PCM 16-bit WAVを`audio/wav`で返す。

互換APIは非同期ジョブIDをクライアントへ返さない。内部の既存ジョブ機構を同期APIへ変換する。

同時要求はFIFOで処理し、モデル推論は常に1件ずつ行う。待機上限は既定16件とし、超過時は`429 Too Many Requests`を返す。通常の`/synthesis`はクライアント切断後も生成を継続する。切断時の取消を行う`/cancellable_synthesis`は初期版では未対応。

## 10. モデルの起動

外部クライアントはStudioのモデルロード画面を操作できないため、互換APIモードでは次を追加する。

- 既定チェックポイントの自動ロード
- 公開スタイルの検証
- モデルロード中は`/synthesis`へ`503 Service Unavailable`
- `/speakers`と`/audio_query`はモデルロード中でも応答可能

起動例:

```powershell
uv run --no-sync python irodori-studio/server.py `
  --voicevox-api `
  --voicevox-port 50021 `
  --autoload-model
```

## 11. CORSとセキュリティ

- 既定ホストは`127.0.0.1`のみ。
- `localhost`、`127.0.0.1`、Originなし、`app://`、ブラウザ拡張Originを既定許可候補とする。
- `--voicevox-host`でlisten先は変更できるが、初期版は認証を持たないためLAN公開を推奨しない。
- 一般的なVOICEVOXクライアントは認証ヘッダーを設定できないため、初期版で独自トークンを必須にしない。
- 最大読み上げ文字数、最大要求サイズ、最大キュー数を制限する。
- 応答へローカルファイルパスを含めない。
- 生成音声は`Cache-Control: no-store`とする。

## 12. エンジン情報

`/engine_manifest`では次のようにIrodoriを明示する。

```json
{
  "manifest_version": "0.13.1",
  "name": "Irodori-TTS Compatibility Engine",
  "brand_name": "Irodori-TTS",
  "uuid": "irodori用の固定UUID",
  "version": "1.0.0",
  "port": 50021,
  "default_sampling_rate": 48000,
  "supported_features": {
    "adjust_speed_scale": { "type": "bool", "value": true },
    "adjust_pitch_scale": { "type": "bool", "value": false },
    "adjust_intonation_scale": { "type": "bool", "value": false },
    "adjust_volume_scale": { "type": "bool", "value": true },
    "adjust_pause_length": { "type": "bool", "value": false },
    "synthesis_morphing": { "type": "bool", "value": false },
    "sing": { "type": "bool", "value": false },
    "manage_library": { "type": "bool", "value": false }
  }
}
```

`/version`はVOICEVOXのバージョンを偽装せず、アダプター自身の`1.0.0`を返す。クライアントが特定バージョン文字列を誤って要求する場合のみ、個別の互換対応として検討する。

## 13. わんコメとOBS

結線:

```text
わんコメ
  ├─ ホスト: 127.0.0.1
  ├─ ポート: 50021
  ├─ 読み上げボイス: /speakersに出るIrodoriスタイル
  └─ 出力デバイス: CABLE Input

CABLE Output
  └─ OBS「音声入力キャプチャ」
```

この経路ではIrodori StudioやAPIサーバーは音声を再生しない。わんコメがWAVを受け取り、わんコメの出力デバイス設定から再生する。既存の読み上げ待機上限、読み上げ速度、枠ごとのボイス設定も利用できる。

## 14. テスト計画

### 契約テスト

- 0.25.2のOpenAPIスキーマへLevel 1・2のレスポンスが適合する。
- 必須フィールド、型、HTTPステータス、Content-Typeを検証する。
- 未知フィールドを保持するクライアントと削除するクライアントの両方を模擬する。

### 音声テスト

- 48 kHz PCM 16-bit monoが返る。
- `outputStereo=true`で2チャンネルになる。
- `outputSamplingRate`で指定レートになる。
- `speedScale`、`volumeScale`、前後無音が反映される。
- 同一Speaker Inversionスタイルで話者性が維持される。

### キューと障害

- 同時要求がFIFOになる。
- キュー上限超過で429になる。
- 未ロード、未知style、空文、長文で明確なエラーになる。
- Studio側の生成と互換API生成が同じキューを共有する。
- 実行中停止要求は完了後破棄になる。

### 実アプリ確認

1. わんコメで話者一覧再取得、接続テスト、コメント読み上げ。
2. VOICEVOX API URLを変更可能な別クライアントで話者取得と合成。
3. OBSのアプリ音声キャプチャと仮想ケーブルの両方。
4. 50021番の競合とカスタムポート。

## 15. 実装順序

1. 公開ボイスプロファイルのサーバー保存と安定style ID。
2. 共有`StudioEngine`を注入できるアプリファクトリー化。
3. 50021番の互換ASGIアプリとLevel 1・2 API。
4. 同期合成ラッパーとWAV後処理。
5. OpenAPI契約テストとcurl往復テスト。
6. Studioボイス画面の「VOICEVOX APIへ公開」。
7. モデル自動ロードとウォームアップ。
8. わんコメ実機試験。
9. Level 3 APIと他クライアント試験。

初期リリースの完了条件は、わんコメでIrodori話者が一覧表示され、接続テストと実コメントの読み上げが成功し、同じWAVが一般的な2段階API呼び出しからも取得できることとする。
