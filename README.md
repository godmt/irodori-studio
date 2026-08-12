# Irodori Studio

Irodori Studioは、独立してクローンした[Irodori-TTS](https://github.com/Aratako/Irodori-TTS)をローカル制作環境として利用するSPAです。台本制作、複数テイク管理、ライブ配信、動画素材の書き出し、VOICEVOX互換APIを一つの画面と常駐ランタイムへまとめます。

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
| `workspace/exports/` | 動画・配信用ZIP |
| `workspace/voices/profiles.json` | ボイスライブラリ本体、固定Style ID、API公開設定 |

`workspace/`、`.studio/`、モデル、個人音声はGit管理されません。ブラウザー側の作業中プロジェクトは`localStorage`にも自動保存されます。ボイスライブラリの変更はボイス単位でプロジェクトとは別にローカルサーバーへ自動保存され、別のプロジェクトでも同じボイスを利用できます。プロジェクトを開き直すと安定したプロフィールIDでボイス設定を復元します。旧`workspace/voicevox/profiles.json`は初回起動時に新しい保存先へ安全に移行されます。

## VOICEVOX互換API

ボイスライブラリで「外部アプリから選べるようにする」を有効にして保存すると、VOICEVOX対応アプリから`127.0.0.1:50021`を利用できます。

```powershell
$query = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:50021/audio_query?text=こんにちは&speaker=1000'
Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:50021/synthesis?speaker=1000' -ContentType 'application/json' -Body ($query | ConvertTo-Json -Depth 20) -OutFile output.wav
```

対応範囲は[docs/VOICEVOX_API_COMPATIBILITY.md](docs/VOICEVOX_API_COMPATIBILITY.md)を参照してください。

## 開発

アーキテクチャと開発手順は[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)、設計上の判断は[AGENTS.md](AGENTS.md)、今後の録音・学習統合は[docs/ROADMAP.md](docs/ROADMAP.md)にまとめています。

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
