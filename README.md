# Irodori Studio

Irodori Studioは、独立してクローンした[Irodori-TTS](https://github.com/Aratako/Irodori-TTS)をローカル制作環境として利用するSPAです。台本制作、複数テイク管理、ライブ配信、録音、ボイス学習、動画素材の書き出し、VOICEVOX互換APIを一つの画面と常駐ランタイムへまとめます。

StudioとIrodori-TTSは別リポジトリのまま利用します。Irodori-TTSの場所を一度指定すると、StudioがそのPython環境と推論ランタイムを使ってモデルを起動します。Gradioサーバーや別のIrodori APIサーバーを先に起動する必要はありません。

## 現在の機能

- 複数行の台本編集、複製、削除、ドラッグ並び替え
- ローカルプロジェクトの作成・保存・切り替え・削除
- 行ごとに最大4テイクを保持し、採用テイクを切り替え
- 話速、生成ステップ、Text/Speaker/Caption CFG、seed、詳細生成設定
- 公式45種の演技記号とVoice Design captionプリセット
- Speaker Inversion、複数参照音声、参照なし、LoRAをボイスとして保存
- 指定行からの連続生成・再生
- 配信用FIFOキュー、自動再生、停止、再生音量、OBS向け音声出力デバイス選択
- Irodori Starter 120／AICA Character Core 200／AICA Full 500の段階切り換え、波形・音量確認、試聴、採用、録り直し、進捗管理
- 名前付き録音データセットの作成・選択・削除と、学習用メタデータの自動保存
- 録音データセットからのSpeaker Inversion／LoRA学習、進捗・停止・履歴管理、名前付きモデル保存
- VOICEVOX互換APIと永続するSpeaker/Style ID
- 行別WAV、master WAV、SRT、VTT、CSV、JSON、FFmpeg concat listのZIP書き出し

## 必要なもの

- Windows 10/11
- PowerShell 5.1以降
- [uv](https://docs.astral.sh/uv/)
- Node.js 20以降
- Git
- 別途クローンしたIrodori-TTS
- 対応GPU、またはCPU実行環境

推奨配置例です。隣接配置は必須ではありません。

```text
C:\AI\
├─ Irodori-TTS\       # 推論・学習エンジン、モデル、学習成果物
└─ irodori-studio\    # このリポジトリ
```

## 最短セットアップ

初回だけIrodori-TTSの場所とPyTorch backendを指定します。NVIDIA GPUの例です。

```powershell
cd C:\AI\irodori-studio
.\setup-studio.ps1 -IrodoriPath C:\AI\Irodori-TTS -TorchBackend cu128
```

以後はこれだけで起動できます。

```powershell
.\start-studio.ps1
```

または`start-studio.cmd`をダブルクリックします。初回に設定していない場合は、Irodori-TTSフォルダーを選ぶダイアログが自動的に開きます。

起動スクリプトは次をまとめて行います。

1. 保存済みのIrodori-TTSパスを検証
2. 必要ならIrodori-TTSのuv環境を作成
3. 必要ならNode依存を導入してSPAをビルド
4. Studio APIを`127.0.0.1:8765`で起動
5. Irodoriモデルを同じPythonプロセスへバックグラウンドロード
6. VOICEVOX互換APIを`127.0.0.1:50021`で起動
7. ブラウザーでStudioを開く

設定は`.studio/config.json`へ保存され、Gitには含まれません。

## PyTorch backend

| 値 | 用途 |
| --- | --- |
| `cu128` | NVIDIA GPU、CUDA 12.8 |
| `cpu` | CPU |
| `xpu` | Intel GPU |
| `rocm` | AMD GPU。Irodori-TTS側の対応OS条件に従う |

環境を作り直す、または依存関係を同期し直す場合は`-ForceSync`を付けます。

```powershell
.\setup-studio.ps1 -IrodoriPath D:\AI\Irodori-TTS -TorchBackend cu128 -ForceSync
```

Irodori-TTSの保存場所だけを変更する場合は次のどちらかを使います。

```powershell
.\start-studio.ps1 -Configure
.\start-studio.ps1 -IrodoriPath D:\AI\Irodori-TTS
```

環境変数`IRODORI_TTS_PATH`でも指定できます。優先順位は、コマンドライン、環境変数、保存設定、隣接する`Irodori-TTS`フォルダーの順です。

## 起動オプション

```powershell
# ブラウザーを自動で開かない
.\start-studio.ps1 -NoOpen

# モデルの自動ロードを行わず、画面から選択する
.\start-studio.ps1 -NoAutoloadModel

# VOICEVOX互換APIを起動しない
.\start-studio.ps1 -NoVoicevoxApi

# ポートを変更
.\start-studio.ps1 -Port 8876 -VoicevoxPort 50031
```

既定モデルは外部Irodori-TTSリポジトリの`models/Irodori-TTS-v4.1-Small/model.safetensors`を優先します。ローカルモデルがない場合は`Aratako/Irodori-TTS-v4.1-Small`を使用します。Speaker Inversion、参照音声、LoRAの候補は、外部リポジトリの`outputs/`から検出します。

## Irodori-TTSとの関係

StudioはIrodori-TTSをコピー、fork、またはサブモジュール化しません。起動時に外部リポジトリをPython import pathへ追加し、Irodori-TTSのuv環境からStudioサーバーを実行します。

```text
Browser
   │
   ├─ Irodori Studio API :8765
   │      └─ Irodori inference runtime（モデル常駐）
   │
   └─ VOICEVOX互換API :50021
          └─ 同じ生成キューとモデルを共有
```

これにより、巨大なPyTorch/CUDA環境をStudio用に二重作成せず、Irodori-TTS側で選んだbackendをそのまま利用します。StudioはIrodori-TTSのソース、モデル、学習成果物を移動しません。初回セットアップ時には、同じ`.venv`へFastAPI、Uvicorn、python-multipartが不足している場合だけ追加します。

## 最初の操作

1. 起動時にブラウザーの音声アクセス確認が表示されたら、OBSなどへ出力先を切り替える場合は許可します。許可しない場合もシステム既定の出力先で利用できます。
2. 上部が`MODEL READY`になるまで待ちます。自動ロードを無効化した場合は右上からモデルを選択します。
3. 左下の「現在のボイス」からボイスライブラリを開きます。
4. Speaker Inversion、参照音声、参照なしのいずれかを設定します。変更は自動保存されます。
5. 台本行の再生、または「ここから連続再生」を開始します。
6. 更新アイコンで新しいテイクを作り、番号で採用テイクを選びます。

## 録音スタジオ

上部の「録音」から録音スタジオを開き、左上のコーパス選択で3段階の収録範囲を切り換えられます。第1段階のIrodori Starter 120 v2は、重複のない120文で日本語の主要なモーラ、外来音、数字、基本感情と20種類のフィラー／相づちを収録します。第2段階はフィラー・笑い・短い応答をさらに拡張するAICA Character Core 200、第3段階はAICA Full 500です。Core 200はFull 500と同じ文章IDと録音を共有するため、第3段階へ進んでも録り直す必要はありません。

初回表示時にブラウザー標準のマイク許可だけを求め、許可後は使用するマイクを選択できます。録音中は別ワークスペースやコーパスの切り換えを無効にし、停止後に波形、録音時間、音量、クリッピングを確認して、試聴・採用・録り直しを行えます。

録音画面では、話者や収録目的ごとに名前を付けた録音データセットを作成・選択・削除できます。録音は全段階で共通のルートデータセットとして扱い、48 kHz・モノラル・PCM 16-bit WAVへ変換して`workspace/recordings/`へ自動保存します。Core 200で採用した録音は、同じデータセットのFull 500でもそのまま採用済みとして扱われます。

各データセットには管理情報の`dataset.json`、採用済み音声だけを列挙する学習用`dataset.jsonl`、音声を保持する`wavs/`があり、録音や採用のたびにStudioが更新します。外部サービスへの送信や手動のZIP書き出しは必要ありません。学習タブは、この一覧と安定したデータセットIDを直接使用します。以前のブラウザー保存録音がある場合は、最初の読み込み時に名前付きデータセットへ安全に移してから元データを消去します。

AICAの文章には出典、固定した上流バージョン、CC0 1.0 Universalを記録します。AICAの文章と、新しく収録した音声の権利条件は別に扱います。

AICA corpusの出典とライセンスは[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。

## 学習スタジオ

上部の「学習」から、録音スタジオで作成したデータセットを直接選択します。モデル名を入力し、学習方法を選んで開始します。既定は、基本モデルを変更せず話者性だけを軽量に学ぶSpeaker Inversionです。LoRAも同じ画面から選択できますが、より多くの録音、GPUメモリ、学習時間が必要な上級者向けの選択肢です。

Studioは採用済み音声を学習ジョブ内へ複製し、冒頭と末尾だけを検出して180msの余白を残して無音をカットします。文中の間や演技上の沈黙は維持します。その後、Irodori-TTSの`prepare_manifest.py`で音量を-16 dBへ正規化してDACVAE latentへ変換し、外部リポジトリの公式v4-Small設定と`train.py`をバックグラウンドで実行します。開始時にはGPUメモリを確保するため、読み上げ用の常駐モデルを自動的にアンロードします。学習画面にはデータ準備、ステップ進捗、停止、完了・失敗履歴が表示され、元の録音WAVは変更しません。前処理の件数とカット時間はジョブ内の`preprocessing.json`に記録します。

学習済みモデルは名前と録音データセットの関係を`studio-model.json`へ記録し、学習履歴とは独立して保持します。Speaker InversionとLoRAの成果物はボイスライブラリの候補として検出されます。

## プロジェクト管理

上部のフォルダーアイコンから「プロジェクト管理」を開きます。ここで名前を付けた新規作成、保存済みプロジェクトを開く操作、不要なプロジェクトの削除ができます。別のプロジェクトを開く前には現在の作業が保存されるため、切り替えによって編集中の内容が失われることはありません。

通常の保存は上部の保存アイコンから行います。保存形式や内部ファイルを意識する必要はありません。台本行の選択、並び替え、複製、削除、追加は中央の読み上げ台本へ集約されています。複数の文章を一度に追加する場合だけ、左側の「文章をまとめて追加」を使用します。

## 再生音量と出力先

台本制作と配信コンソールには同じ再生音量と出力先が表示され、どちらで変更してももう一方とすべてのアプリ内再生へ即時反映されます。生成WAVや書き出しファイル自体の音量は変更しません。

ブラウザーの音声アクセスを許可すると、利用可能なスピーカーや仮想オーディオデバイスが出力先一覧へ追加されます。OBSへ送る場合はVB-CABLEなどの仮想出力を選択します。アクセスを許可しなかった場合、未対応ブラウザーの場合、または選択中のデバイスが外れた場合は、システム既定の出力先を使用します。

## ローカルデータ

Studio自身の実行データは`workspace/`へ保存します。

| パス | 内容 |
| --- | --- |
| `workspace/audio/` | 生成WAVと生成メタデータ |
| `workspace/projects/` | Studioで保存したローカルプロジェクト |
| `workspace/recordings/` | 名前付き録音データセット、採用済み学習マニフェスト、録音WAV |
| `workspace/training/` | 学習ジョブの設定、前後無音を整えた学習用WAV、前処理latent、ログ、履歴 |
| `workspace/models/speaker-embeddings/` | 名前付きSpeaker Inversionモデル |
| `workspace/models/lora/` | 名前付きLoRAモデル |
| `workspace/exports/` | 動画・配信用ZIP |
| `workspace/voices/profiles.json` | ボイスライブラリ本体、固定Style ID、API公開設定 |

`workspace/`、`.studio/`、モデル、個人音声はGit管理されません。ブラウザー側の作業中プロジェクトは`localStorage`にも自動保存されます。録音データセット、学習モデル、ボイスライブラリはプロジェクトとは独立してローカルサーバーへ自動保存され、別の制作プロジェクトから利用できます。プロジェクトを開き直すと安定したプロフィールIDでボイス設定を復元します。旧`workspace/voicevox/profiles.json`は初回起動時に新しい保存先へ安全に移行されます。

## VOICEVOX互換API

ボイスライブラリで「外部アプリから選べるようにする」を有効にして保存すると、VOICEVOX対応アプリから`127.0.0.1:50021`を利用できます。

```powershell
$query = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:50021/audio_query?text=こんにちは&speaker=1000'
Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:50021/synthesis?speaker=1000' -ContentType 'application/json' -Body ($query | ConvertTo-Json -Depth 20) -OutFile output.wav
```

対応範囲は[docs/VOICEVOX_API_COMPATIBILITY.md](docs/VOICEVOX_API_COMPATIBILITY.md)を参照してください。

## 開発

アーキテクチャと開発手順は[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)、設計上の判断は[AGENTS.md](AGENTS.md)、録音の現状と今後の学習統合は[docs/ROADMAP.md](docs/ROADMAP.md)にまとめています。

基本的な検証コマンドです。

```powershell
npm ci
npm test
npm run build
uv sync
uv run python -m unittest discover -s tests -p "test_*.py" -v
```

実際のIrodori importとローカル起動を含む検証は次のように行います。

```powershell
.\start-studio.ps1 -NoOpen -NoAutoloadModel -NoVoicevoxApi
```

## セキュリティ

既定では両APIとも`127.0.0.1`だけをlistenします。認証機能はないため、listen先をLANへ変更して公開することは推奨しません。Studioには音声、台本、モデルパス、生成物を外部サービスへ送信する機能はありません。
