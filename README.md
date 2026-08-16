# Irodori Studio

Irodori Studioは、独立してクローンした[Irodori-TTS](https://github.com/Aratako/Irodori-TTS)をローカル制作環境として利用するSPAです。台本制作、複数テイク管理、ライブ配信、録音、ボイス学習、動画素材の書き出し、VOICEVOX互換APIを一つの画面と常駐ランタイムへまとめます。

画面全体の意匠、操作語彙、リソース管理、文字サイズ、アイコン、アクセシビリティの基準は[DESIGN.md](DESIGN.md)にまとめています。新しいタブや操作UIはこの共通ポリシーへ揃えます。

StudioとIrodori-TTSは別リポジトリのまま利用します。Irodori-TTSの場所を一度指定すると、StudioがそのPython環境と推論ランタイムを使ってモデルを起動します。Gradioサーバーや別のIrodori APIサーバーを先に起動する必要はありません。

## 現在の機能

- 複数行の台本編集、複製、削除、ドラッグ並び替え
- ローカルプロジェクトの作成・保存・切り替え・名前変更・削除
- 行ごとに最大4テイクを保持し、採用テイクを切り替え
- 話速、生成ステップ、Text/Speaker/Caption CFG、seed、詳細生成設定
- 公式45種の演技記号とVoice Design captionプリセット
- Speaker Inversion、複数参照音声、参照なし、LoRAをボイスとして保存
- 指定行からの連続生成・再生
- 配信用FIFOキュー、自動再生、停止、再生音量、OBS向け音声出力デバイス選択
- 台本制作・配信・VOICEVOX互換APIに共通するボイス設定と長文の自動分割生成。配信は生成キューと再生キューを独立させ、先頭の分割音声から再生しながら続きを生成
- Irodori Starter 120／AICA Character Core 200／AICA Full 500の段階切り換え、波形・音量確認、試聴、採用、録り直し、進捗管理
- 名前付き学習データセットの作成・選択・名前変更・削除と、学習用メタデータの自動保存
- 学習タブから複数の長尺音声を選択し、一定量ずつ分割・文字起こし・自動採用して学習データセットへ追加する前処理
- 学習データセットからのSpeaker Inversion／LoRA学習、進捗・停止・再開・履歴管理、学習済みモデルの名前変更・削除
- VOICEVOX互換APIと永続するSpeaker/Style ID
- 行別WAV、master WAV、SRT、VTT、CSV、JSON、FFmpeg concat listのZIP書き出し

## 入手方法

通常利用では、[Releases](https://github.com/godmt/irodori-studio/releases)に添付される`irodori-studio-vX.Y.Z-windows.zip`を使用してください。ビルド済みSPAを同梱しているため、Node.jsは不要です。GitHubが自動生成する`Source code (zip)`と`Source code (tar.gz)`は、開発文書、テスト、フロントエンドソースを含む開発者向けのソースアーカイブです。

Windowsパッケージと同じ場所にある`.sha256`ファイルで、ダウンロードしたZIPのSHA-256を確認できます。

## 必要なもの

- Windows 10/11
- PowerShell 5.1以降
- [uv](https://docs.astral.sh/uv/)
- 別途クローンしたIrodori-TTS
- 対応GPU、またはCPU実行環境

ソースアーカイブから起動・開発する場合だけ、Node.js 20以降とGitも必要です。Windowsパッケージはビルド済みフロントエンドを使用するため、Node.jsを要求しません。

推奨配置例です。隣接配置は必須ではありません。

```text
C:\AI\
├─ Irodori-TTS\       # 推論・学習エンジン、モデル、学習成果物
└─ irodori-studio\    # このリポジトリ
```

## 最短セットアップ

初回だけIrodori-TTSの場所を指定します。既存の`.venv`にPyTorchがある場合は、そのバージョンとruntime情報からbackendを自動判別します。

```powershell
cd C:\AI\irodori-studio
.\setup-studio.ps1 -IrodoriPath C:\AI\Irodori-TTS
```

以後はこれだけで起動できます。

```powershell
.\start-studio.ps1
```

または`start-studio.cmd`をダブルクリックします。初回に設定していない場合は、Irodori-TTSフォルダーを選ぶダイアログが自動的に開きます。

起動スクリプトは次をまとめて行います。

1. 保存済みのIrodori-TTSパスを検証
2. 必要ならIrodori-TTSのuv環境を作成
3. Windowsパッケージでは同梱SPAを使用し、ソース版では依存定義の変更を検知して必要なNode・Python依存を同期し、SPAをビルド
4. Studio APIを`127.0.0.1:8765`で起動
5. Irodoriモデルを同じPythonプロセスへバックグラウンドロード
6. VOICEVOX互換APIを`127.0.0.1:50021`で起動
7. ブラウザーでStudioを開く

設定は`.studio/config.json`へ保存され、Gitには含まれません。

## 更新方法

### Gitで取得したソース版

Studioを停止してから、Studioのフォルダーで次を実行します。

```powershell
.\update-studio.ps1
.\start-studio.ps1
```

PowerShellを開かず、`update-studio.cmd`をダブルクリックしても更新できます。結果を確認できるよう、完了または失敗後もキーを押すまでウィンドウを閉じません。更新が完了したら`start-studio.cmd`で起動します。

`update-studio`は未コミットの変更がないことを確認してから`git pull --ff-only`を実行し、続けて更新後の準備だけを行います。`package-lock.json`とStudio用Python依存の定義を前回準備時の記録と比較し、変更がある場合だけ`npm ci`、Python依存の更新、SPAの再ビルドを自動実行します。したがって通常の更新では、手作業で`npm install`や`uv pip install`を実行する必要はありません。未コミットのファイルがある場合は、ユーザーの編集を上書きしないよう更新を中止します。

同じ処理を手動で行う場合は次の2コマンドです。

```powershell
git pull --ff-only
.\start-studio.ps1 -SetupOnly
```

依存環境が壊れた場合や、Irodori-TTS側も更新した場合は、一度だけ完全同期します。保存済みのIrodori-TTSパスとbackend設定が使われるため、通常は引数を再指定する必要はありません。

```powershell
.\update-studio.ps1 -ForceSync
.\start-studio.ps1
```

`-ForceSync`は、更新取得後にIrodori-TTSのuv環境、Studio用Python依存、ソース版のNode依存をすべて同期し直します。ユーザーの台本、録音、学習データ、モデルが入る`workspace/`と、保存済み設定が入る`.studio/`は削除しません。

### Windowsリリースパッケージ

リリースZIP版はGitリポジトリではないため、`git pull`せず、ソース版専用の`update-studio`も同梱しません。Studioを停止し、新しいReleaseの`irodori-studio-vX.Y.Z-windows.zip`を新しいフォルダーへ展開したうえで、以前のフォルダーから`workspace/`と`.studio/`を移します。Irodori-TTS本体、モデル、学習成果物は外部リポジトリにあるため移動不要です。移行後は`.\start-studio.ps1 -SetupOnly`を一度実行してから起動します。

## PyTorch backend

| 値 | 用途 |
| --- | --- |
| `cu128` | NVIDIA GPU、CUDA 12.8 |
| `cpu` | CPU |
| `xpu` | Intel GPU |
| `rocm` | AMD GPU。Irodori-TTS側の対応OS条件に従う |

通常は`-TorchBackend`を指定する必要はありません。判定順は、明示した`-TorchBackend`、Irodori-TTSの既存`.venv`、保存済みStudio設定、検出したハードウェアです。既存環境では`torch`の`+cu128`、`+cpu`、`+xpu`、`+rocm`などのbuild suffixを優先し、suffixがない場合はTorch runtimeのCUDA・HIP・XPU情報を確認します。初回で`.venv`がまだない場合は、NVIDIA GPUを検出すれば`cu128`、それ以外は`cpu`を選びます。

既存環境と異なるbackendへ意図的に切り替える場合だけ明示します。

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

# HTTPリクエスト調査用のアクセスログを表示
.\start-studio.ps1 -AccessLog
```

画面が定期取得する正常なHTTPリクエストは、重要な学習・エラーログを埋もれさせないよう既定では表示しません。警告、エラー、Studioの処理ログは引き続き表示されます。HTTP通信自体を調査するときだけ`-AccessLog`を指定してください。

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

これにより、巨大なPyTorch/CUDA環境をStudio用に二重作成せず、Irodori-TTS側で選んだbackendをそのまま利用します。StudioはIrodori-TTSのソース、モデル、学習成果物を移動しません。初回セットアップ時には、同じ`.venv`へFastAPI、Uvicorn、NumPy、Pydantic、SoundFile、faster-whisperが不足している場合だけ追加します。

## 最初の操作

1. 起動時にブラウザーの音声アクセス確認が表示されたら、OBSなどへ出力先を切り替える場合は許可します。許可しない場合もシステム既定の出力先で利用できます。
2. 上部が`MODEL READY`になるまで待ちます。自動ロードを無効化した場合は右上からモデルを選択します。
3. ヘッダー右端のボイスライブラリアイコンを開きます。
4. Speaker Inversion、参照音声、参照なしのいずれかを設定します。変更は共有ライブラリへ自動保存されます。
5. 台本制作の左側で、新しく追加する行に使う既定のボイスを選びます。必要なら各行のボイス名から、その行だけ別のボイスへ変更できます。
6. 台本行の再生または「ここから連続再生」を開始します。更新アイコンで新しいテイクを作り、番号で採用テイクを選びます。

## 録音スタジオ

上部の「録音」から録音スタジオを開き、左上のコーパス選択で3段階の収録範囲を切り換えられます。第1段階のIrodori Starter 120 v2は、重複のない120文で日本語の主要なモーラ、外来音、数字、基本感情と20種類のフィラー／相づちを収録します。第2段階はフィラー・笑い・短い応答をさらに拡張するAICA Character Core 200、第3段階はAICA Full 500です。Core 200はFull 500と同じ文章IDと録音を共有するため、第3段階へ進んでも録り直す必要はありません。

初回表示時にブラウザー標準のマイク許可だけを求め、許可後は使用するマイクを選択できます。録音中は別ワークスペースやコーパスの切り換えを無効にし、停止後に波形、録音時間、音量、クリッピングを確認して、試聴・採用・録り直しを行えます。

録音画面では、話者や収録目的ごとに名前を付けた学習データセットを作成・選択・名前変更・削除できます。録音は全段階で共通のルートデータセットとして扱い、48 kHz・モノラル・PCM 16-bit WAVへ変換して`workspace/recordings/<データセット名>/`へ自動保存します。画面で名前を変更するとフォルダ名も変わりますが、学習連携に使う内部IDは維持されます。以前のID名フォルダは起動時にデータセット名へ安全に移行します。Core 200で採用した録音は、同じデータセットのFull 500でもそのまま採用済みとして扱われます。

各データセットには管理情報の`dataset.json`、採用済み音声だけを列挙する学習用`dataset.jsonl`、音声を保持する`wavs/`があり、録音や採用のたびにStudioが更新します。外部サービスへの送信や手動のZIP書き出しは必要ありません。学習タブは、この一覧と安定したデータセットIDを直接使用します。以前のブラウザー保存録音がある場合は、最初の読み込み時に名前付きデータセットへ安全に移してから元データを消去します。

### 長尺音声の前処理コア

ローカルAPIは、同じ話者の複数のWAV、FLAC、MP3、M4Aなどを1件の前処理ジョブとして受け取れます。音声全体を巨大なWAVへ変換したりメモリへ読み込んだりせず、5分単位の重複窓でデコードし、Silero VADで発話を分け、既定の`faster-whisper large-v3`で日本語を文字起こしします。ASRモデルは初回利用時に取得され、利用可能ならCUDA／float16を、なければCPU／int8を選びます。

短すぎる区間、空の文字起こし、明確に信頼度が不足する区間だけを確認対象とし、それ以外は自動採用します。学習タブの「学習データを用意する」から複数ファイルを選択し、進捗と停止を管理できます。処理後の文字修正・採用・除外は「内容を確認」から任意で行え、全件確認は学習の前提ではありません。選択した元ファイルはデータセットの`raw/imports/`へそのまま複製して以後の再加工元とし、ジョブ内では一時的にlossless FLACを使用します。データセットへ確定するときに48 kHz・モノラル・PCM 16-bit WAVへ変換し、前後だけを180 msの余白で調整して-16 LUFSへ正規化します。文中の間は維持し、管理情報の保存成功後に一時FLACを削除します。原本と出力のハッシュ、時刻範囲、ASR確信度、音量・クリッピング等の監査情報は保持します。同じ元ファイルの同じ区間には安定したIDが付くため、再実行は同じ加工版の有効なWAVを既定でスキップし、明示した場合だけ全上書きします。ジョブ状態とログは`workspace/imports/<job-id>/`へ保存し、全処理が完了してからデータセットへまとめて確定します。失敗・中断・停止したジョブは、同じデータセットの前処理履歴から再開できます。再開時は保存済みの分割音声と文字起こしを再利用し、未完了区間だけを続行します。履歴と再開用一時ファイルは個別に削除できますが、確定済みWAVと`raw/`原本は残ります。

AICAの文章には出典、固定した上流バージョン、CC0 1.0 Universalを記録します。AICAの文章と、新しく収録した音声の権利条件は別に扱います。

AICA corpusの出典とライセンスは[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)を参照してください。

## 学習スタジオ

上部の「学習」は、学習データを用意してモデルを作るワークスペースです。コーパスを収録する場合は録音へ移動し、手持ちのWAV・FLAC・MP3等を使う場合は複数ファイルを選んで前処理します。どちらも同じ学習データセットへ合流し、任意確認の後はモデル名と学習方法を選んで開始できます。既定は、基本モデルを変更せず話者性だけを軽量に学ぶSpeaker Inversionです。Speaker Inversionは500 stepを既定とし、より高品質を求める場合は1000 step以上を設定欄で案内します。LoRAは1,500 stepを既定とし、高品質・追い込みでは3,000 stepを目安にします。LoRAの学習率スケジュールは、上流30,000-step設定の比率に合わせて指定step内へ自動短縮します。LoRAは同じ画面から選択できますが、より多くの録音、GPUメモリ、学習時間が必要な上級者向けの選択肢です。

CUDAで学習を開始するときはGPUの総VRAMを確認します。現行構成ではSpeaker InversionにBF16/FP16で12 GB、FP32で16 GB、LoRAにBF16/FP16で24 GB、FP32で32 GBを推奨します。下回る場合は共有メモリへの退避による極端な低速化や開始失敗の可能性を確認ダイアログで知らせます。キャンセルした場合は学習ジョブを作成せず、読み上げ用モデルも解放しません。環境差があるため一律には禁止せず、確認後の明示的な続行も選べます。

録音と外部音声の追加時点で、StudioはRAW原本を維持したまま、方式に依存しない共通加工済みWAVをデータセットへ作ります。学習開始時は採用済みWAVのハッシュを検証して`dataset-snapshot/`へ固定し、無音調整や音量正規化を繰り返しません。Irodori-TTSの`prepare_manifest.py`には正規化なしで渡してDACVAE latentへ変換し、外部リポジトリの公式v4-Small設定と`train.py`をバックグラウンドで実行します。開始時にはGPUメモリを確保するため、読み上げ用の常駐モデルを自動的にアンロードします。学習画面にはデータ準備、ステップ進捗、観測済みステップ速度から求めた残り時間／全体時間の目安、停止、完了・失敗履歴が表示されます。開始直後は「計算中」とし、GPU負荷などで速度が変われば予測も更新します。共通加工の版・原本と出力のハッシュ・調整値は各録音の管理情報へ、学習時の固定内容は`dataset-snapshot.json`へ記録します。

停止・異常終了した学習は同じジョブから再開できます。停止時はSpeaker InversionとLoRAのどちらもトレーナーの子プロセスまで終了を待ち、学習に使ったGPU／VRAMを解放します。既定の再開では、検証済みのデータセットスナップショットと完成済みlatentをスキップし、LoRAは最新チェックポイントの学習状態を継続、Speaker Inversionは最新の途中埋め込みからウォームスタートします。以前のチェックポイントは上書きせず、新しい試行フォルダへ保存します。明示的な「全上書き」再実行だけがジョブ生成物と未完成のモデル出力を削除して最初から処理し、`raw/`と学習データセットは常に保持します。

学習済みモデルは名前と学習データセットの関係を`studio-model.json`へ記録し、学習履歴とは独立して保持します。Speaker InversionとLoRAの成果物はボイスライブラリの候補として検出されます。

## プロジェクト管理

上部のフォルダーアイコンから「プロジェクト管理」を開きます。ここで名前を付けた新規作成、保存済みプロジェクトを開く操作、名前変更、不要なプロジェクトの削除ができます。別のプロジェクトを開く前には現在の作業が保存されるため、切り替えによって編集中の内容が失われることはありません。行やプロジェクトを削除すると、ほかの保存済みプロジェクトから参照されていない生成音声と付随メタデータも`workspace/audio/`から回収されます。ボイス設定に指定した外部の参照WAVは削除しません。

通常の保存は上部の保存アイコンから行います。保存形式や内部ファイルを意識する必要はありません。台本行の選択、並び替え、複製、削除、追加は中央の読み上げ台本へ集約されています。複数の文章を一度に追加する場合だけ、左側の「文章をまとめて追加」を使用します。

## 再生音量と出力先

台本制作と配信には同じ再生音量と出力先が表示され、どちらで変更してももう一方とすべてのアプリ内再生へ即時反映されます。生成WAVや書き出しファイル自体の音量は変更しません。

ブラウザーの音声アクセスを許可すると、利用可能なスピーカーや仮想オーディオデバイスが出力先一覧へ追加されます。OBSへ送る場合はVB-CABLEなどの仮想出力を選択します。アクセスを許可しなかった場合、未対応ブラウザーの場合、または選択中のデバイスが外れた場合は、システム既定の出力先を使用します。

長い文章は、句読点に沿った適度な長さへ内部で分けて順番に生成します。台本や配信文章をユーザーが手作業で分割する必要はありません。台本制作は一つのWAVへ連結します。配信は生成側をproducer、再生側をconsumerとして独立させ、先頭の分割音声が完成した時点で再生を始めた後も、再生完了を待たず残りの生成を続けます。配信タブとVOICEVOX互換APIは、共有ボイスライブラリから話者素材・速度・CFG設定を解決する同じサーバー処理を使用します。配信でブラウザーが自動再生を止めた場合は発話履歴の再生ボタンから全分割音声を順番に再試行でき、選択中の出力先が利用できなくなった場合は通知してシステム既定で再試行します。

## ローカルデータ

Studio自身の実行データは`workspace/`へ保存します。

| パス | 内容 |
| --- | --- |
| `workspace/audio/` | 生成WAVと生成メタデータ |
| `workspace/projects/` | Studioで保存したローカルプロジェクト |
| `workspace/recordings/` | 名前付き学習データセット、原本`raw/`、採用済み学習マニフェスト、統一された学習用WAV |
| `workspace/imports/` | 長尺音声前処理ジョブの設定、ログ、候補一覧、一時FLAC、監査レポート |
| `workspace/training/` | 学習ジョブの設定、検証済みデータセットスナップショット、モデル固有latent、ログ、履歴 |
| `workspace/models/speaker-embeddings/` | 名前付きSpeaker Inversionモデル |
| `workspace/models/lora/` | 名前付きLoRAモデル |
| `workspace/exports/` | 動画・配信用ZIP |
| `workspace/voices/profiles.json` | ボイスライブラリ本体、固定Style ID、API公開設定 |

`workspace/`、`.studio/`、モデル、個人音声はGit管理されません。ブラウザー側の作業中プロジェクトは`localStorage`にも自動保存されます。学習データセット、学習モデル、ボイスライブラリはプロジェクトとは独立してローカルサーバーへ自動保存され、別の制作プロジェクトから利用できます。プロジェクトを開き直すと安定したプロフィールIDでボイス設定を復元します。旧`workspace/voicevox/profiles.json`は初回起動時に新しい保存先へ安全に移行されます。

## VOICEVOX互換API

ボイスライブラリで「外部アプリから選べるようにする」を有効にして保存すると、VOICEVOX対応アプリから`127.0.0.1:50021`を利用できます。

```powershell
$query = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:50021/audio_query?text=こんにちは&speaker=1000'
Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:50021/synthesis?speaker=1000' -ContentType 'application/json' -Body ($query | ConvertTo-Json -Depth 20) -OutFile output.wav
```

対応範囲は[docs/VOICEVOX_API_COMPATIBILITY.md](docs/VOICEVOX_API_COMPATIBILITY.md)を参照してください。

## 開発

アーキテクチャと開発手順は[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)、プロダクトとUI/UXの判断は[DESIGN.md](DESIGN.md)、現在の実装状況と今後の候補は[docs/ROADMAP.md](docs/ROADMAP.md)にまとめています。`AGENTS.md`は、リポジトリ全体の不変条件とこれら正本文書への案内に限定しています。

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

ソースチェックアウトでは、一般ユーザー向けWindowsパッケージを次のコマンドで`artifacts/`へ生成できます。ZIPには許可リストで選んだ実行ファイル、ビルド済みSPA、利用者向け文書とライセンスだけを含め、開発文書、テスト、`src/`、`.github/`は含めません。

```powershell
.\build-release.ps1
```

GitHubでReleaseを公開すると、同じ処理がWindows runnerで実行され、ZIPとSHA-256がRelease Assetsへ自動添付されます。

## セキュリティ

既定では両APIとも`127.0.0.1`だけをlistenします。認証機能はないため、listen先をLANへ変更して公開することは推奨しません。Studioには音声、台本、モデルパス、生成物を外部サービスへ送信する機能はありません。
