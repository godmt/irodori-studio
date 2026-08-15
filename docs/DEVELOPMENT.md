# Development guide

## Repository responsibilities

Irodori Studio owns the product experience and local orchestration. Irodori-TTS remains the inference and training engine.

| Repository | Responsibility |
| --- | --- |
| `irodori-studio` | React SPA, local FastAPI host, synthesis queue, project data, recording, training orchestration, exports and VOICEVOX compatibility |
| `Irodori-TTS` | model architecture, inference runtime, codec, Speaker Inversion, LoRA and training implementation |

Do not copy `irodori_tts/`, checkpoints, training outputs, private recordings, or user-specific absolute paths into this repository.

## Runtime boundaries

- `start-studio.ps1` resolves and validates the external Irodori-TTS repository, verifies that its installed Torch backend matches the configured backend, and executes the server with that repository's `.venv` Python directly.
- Source checkouts persist dependency fingerprints under ignored `.studio/`. A changed `package-lock.json`, changed Studio Python requirement list, missing dependency directory, or explicit `-ForceSync` triggers the corresponding deterministic synchronization before the SPA build. Packaged releases have no frontend source and continue to use the bundled client without Node.js.
- `server.py` inserts that root into `sys.path` before importing `irodori_tts`.
- `StudioEngine` owns one resident `IrodoriInferenceRuntime` and one FIFO generation worker.
- Studio HTTP and VOICEVOX compatibility HTTP share the same `StudioEngine`.
- Unless an explicit duration is requested, `StudioEngine` splits long synthesis text at Japanese sentence or punctuation boundaries with a 64-character segment bound, generates segments sequentially through the resident runtime, inserts 160 ms joins and persists one combined WAV plus aggregate and per-segment metadata. Cancellation is checked between segments. Explicit-duration synthesis remains one segment because independently fixing each segment duration would change the request contract.
- The frontend communicates only with the local Studio HTTP API.
- Script and Live prime browser media playback from the initiating user gesture before asynchronous synthesis. A failed non-default output is retried once on the system output; autoplay denial remains a visible, retryable playback failure and does not discard the completed generation.
- Recorder microphone capture happens in the browser, then accepted and review recordings are saved through the local Studio HTTP API under ignored `workspace/recordings/`.
- Long-audio imports run in a dedicated child process over bounded overlapping windows. Studio owns persistent job/cancellation state, VAD/ASR/QC reports and the atomic commit into a named recording dataset; selected source media is copied into dataset-owned immutable `raw/` storage and is never expanded into a whole master WAV.
- Training runs only model-specific Irodori-TTS preparation and training in child processes. Studio owns job state, cancellation and output discovery but never copies the trainer source or reapplies dataset-level audio transforms.
- Generated files, server-saved projects, named recording datasets, training state, learned models and the shared voice library live under ignored `workspace/`.

## Source map

```text
src/
  App.jsx                 Main application and current Script/Live workspaces
  api.js                  Local Studio HTTP API client
  audio-output.js         Browser output-device discovery and preference helpers
  playback.js             Playback priming, output fallback decisions and user-facing error messages
  components/             Shared dialogs, controls and sortable-list interaction
  defaults.js            Persistent project schema and migration defaults
  project-state.js       Pure line, take and ordering operations
  emoji-data.js          Official Irodori performance emoji metadata
  voice-library.js       Server profile/project voice reconciliation and payload mapping
  features/recorder/     Corpus UI, microphone capture, WAV conversion and named dataset management
  features/training/     Guided Speaker Inversion/LoRA setup, progress and model history
studio_backend/
  audio_import.py        Windowed decode, VAD, ASR, QC and lossless clip creation
  audio_import_jobs.py   Persistent long-audio worker process and atomic dataset handoff
  audio_import_worker.py Isolated faster-whisper entry point
  audio_utils.py         Shared mono loading and deterministic linear resampling
  dataset_preprocessing.py Versioned method-independent dataset audio pipeline
  engine.py              Resident runtime and FIFO synthesis queue
  text_segmentation.py   Sentence-aware bounded synthesis segmentation
  models.py              HTTP request schemas
  exporter.py            WAV/subtitle/timeline production ZIP
  path_utils.py          Shared safe local filename generation
  project_store.py       Atomic local project persistence
  recording_datasets.py Named recording datasets and training-ready manifests
  time_utils.py          Shared persistent UTC timestamps
  training_jobs.py      External Irodori-TTS preprocessing/training process manager
  voice_profiles.py      Shared Voice Library and stable VOICEVOX speaker/style persistence
  voicevox_api.py        Compatibility endpoints
  runtime_paths.py       External Irodori-TTS discovery and validation
server.py                Local API, static SPA host and process orchestration
build-release.ps1        Allow-listed Windows runtime package and SHA-256 builder
update-studio.ps1        Source-checkout fast-forward update and dependency synchronization
.github/workflows/       Release-published package automation
```

`server.py` and `studio_backend/models.py` are the source of truth for the Studio HTTP
API. While Studio is running, `/docs` provides the generated interactive reference and
`/openapi.json` provides the machine-readable contract. Do not maintain a second,
hand-written endpoint schema. The API owns startup state and assets, model lifecycle,
synthesis jobs, generated audio, projects, the shared Voice Library, recording datasets,
long-audio import jobs, training jobs, learned models, production export and native file selection.

The VOICEVOX-compatible service is the separate FastAPI application in
`studio_backend/voicevox_api.py`. It shares the resident engine and Voice Library store,
but does not use the Studio `/api` prefix. Its supported surface is recorded in
`docs/VOICEVOX_API_COMPATIBILITY.md`.

## Local development

Install frontend and lightweight Python test dependencies:

```powershell
npm ci
uv sync
```

Start the backend without loading a model:

```powershell
.\start-studio.ps1 -NoOpen -NoAutoloadModel
```

In a second terminal, start Vite:

```powershell
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8765`. The production build is served by FastAPI from `dist/client`.

## Verification

```powershell
npm test
npm run build
uv run python -m unittest discover -s tests -p "test_*.py" -v
uv run ruff check server.py studio_backend tests
```

The application code is the behavioral source of truth. Tests must assert current user-visible contracts and persistence boundaries; delete tests only when the corresponding code path is removed. Shared backend helpers have focused tests in `test_audio_utils.py`, `test_path_utils.py` and `test_models.py`; move a test when implementation ownership moves instead of leaving it attached to an unrelated module. `README.md`, `DESIGN.md`, and documents under `docs/` describe implemented behavior unless a section is explicitly labeled as a future candidate.

For changes to synthesis, voice selection, take handling or export, also run Studio against a real loaded model and verify the browser interaction. Avoid treating build success as runtime verification.

## Release packaging

GitHub's automatically generated ZIP and TAR files remain source archives and intentionally contain tracked development documents, tests and frontend source. General users receive the separate `irodori-studio-v<version>-windows.zip` asset built by `build-release.ps1`.

The package builder is allow-list based. It includes the launch scripts, Python runtime, prebuilt `dist/client/`, user-facing README, changelog, project license and third-party notices. It excludes `AGENTS.md`, `DESIGN.md`, `docs/`, `src/`, `tests/`, `.github/`, local configuration and `workspace/`. Links from the packaged README to excluded reference documents are rewritten to the matching Git tag on GitHub. Do not change this to a broad repository copy followed by exclusions, because a new private or development-only path could then leak into an asset.

```powershell
.\build-release.ps1
```

The script validates that `package.json` matches the requested version, builds the frontend unless `-SkipBuild` is explicit, writes the ZIP under ignored `artifacts/`, and emits a sibling `.sha256` file. A packaged checkout contains no frontend source and therefore `start-studio.ps1` uses its bundled client without requiring Node.js; a source checkout retains dependency installation and source-freshness rebuilding.

`.github/workflows/release-package.yml` runs on a published GitHub Release, checks out that release tag, tests and builds the frontend on Windows, builds the package with the same script, preserves it as a workflow artifact, and attaches the ZIP plus checksum to the Release. Manual dispatch builds and preserves the artifact without modifying a Release.

## Persistent schema compatibility

Browser projects are hydrated through `hydrateProject()` in `src/defaults.js`. Add migrations or safe defaults there whenever fields change. Existing single-audio lines are migrated into `takes[0]`; keep that compatibility when editing the take model.

`studio_backend/project_store.py` owns atomic local project creation, listing, loading, saving and deletion under `workspace/projects/`, including collection of every generated WAV referenced by selected and alternate takes. `studio_backend/generated_audio.py` safely removes released WAV basenames and matching JSON metadata. Line and capped-take deletion calls `/api/audio/release`; project save/delete performs the same reference-aware cleanup on the server. Never remove user-supplied reference audio, and retain generated files still referenced by another saved project. Project storage formats are implementation details and must not appear in the user-facing Studio project manager.

`studio_backend/recording_datasets.py` owns named datasets under human-readable `workspace/recordings/<dataset-name>/` directories. Each directory contains `dataset.json`, accepted-only `dataset.jsonl`, immutable source material in `raw/`, and canonical PCM16 WAV clips in `wavs/`. Parsed manifests and list summaries are cached against manifest modification time and size, invalidated on Studio writes, and reloaded after external changes. Recorder requests the corpus-only dataset view so long-audio imports remain available to Training without sending thousands of unrelated records every time the recording workspace mounts. `studio_backend/dataset_preprocessing.py` is the method-independent boundary shared by microphone and imported utterances: mono 48 kHz PCM16, -45 dBFS edge detection with 10 ms windows and 180 ms padding, internal-pause preservation, -16 LUFS normalization with peak safety, and versioned source/output hashes. Never overwrite RAW. Import FLAC is job-local and temporary: create and validate its canonical WAV, atomically update both manifests, then delete the FLAC. Store initialization rebuilds legacy derived clips from a retained RAW copy and leaves the last usable bytes available if migration fails. The folder name follows the user-visible name and changes on rename, while the opaque ID inside `dataset.json` remains stable and is resolved by scanning manifests. That stable ID and the local API list are the contract for the Training workspace. Migrate legacy ID-named folders on store initialization, adopt a matching user-created `raw/`-only folder without moving its sources, add a numeric suffix only for filesystem collisions, and reject duplicate user-visible names. Deleting a dataset removes Studio-managed derived clips and manifests but leaves its `raw/` sources intact. Recorder saves automatically; do not make ZIP export the primary handoff. Legacy IndexedDB recordings are cleared only after every WAV has been copied successfully.

`studio_backend/audio_import.py` decodes each source as five-minute windows with overlap at least as long as the maximum utterance, so MP3 and multi-gigabyte WAV inputs have bounded memory use and no boundary duplicates. It detects speech with faster-whisper's packaged Silero VAD, transcribes each speech unit independently, writes compact 48 kHz mono FLAC intermediates, and records source offsets plus ASR/audio metrics. Candidate IDs derive from source identity and absolute time, so a rerun resolves to the same dataset WAV. `audio_import_worker.py` isolates GPU memory; `audio_import_jobs.py` owns status, logs, cancellation and the final all-or-rollback WAV commit into the selected dataset under `workspace/imports/<job-id>/`. Interrupted, failed and cancelled jobs set `resume_existing`; the processor validates checkpoint JSONL entries and their FLAC files, reuses valid candidates, and continues missing candidates without duplicating IDs. The Training UI lists these jobs per dataset and may remove a non-active job directory without touching committed dataset WAVs or dataset-owned RAW. Existing WAVs are skipped by default and replaced only when `overwrite_existing` is explicit. Structurally valid candidates are accepted automatically. Review updates may correct text or change acceptance later, but review is not a required stage before Training.

`studio_backend/training_jobs.py` owns job state under `workspace/training/<job-id>/`, invokes the configured external checkout's `prepare_manifest.py` and `train.py`, and writes final assets beneath `workspace/models/speaker-embeddings/` or `workspace/models/lora/`. It verifies every accepted canonical WAV against its recorded hash and creates an immutable job-local `dataset-snapshot/` plus `dataset-snapshot.json`; it does not trim or normalize again. Studio-owned prepared audio must enter this boundary as validated PCM WAV without requiring TorchCodec or a system FFmpeg installation. Irodori preparation runs through Studio's compatibility runner with normalization disabled and creates only model-specific DACVAE latents; every accepted row and latent must exist before training starts, and an empty or partial manifest is never success. During trainer execution it estimates seconds per step from the current process and persists approximate remaining and full-run durations in `training_timing`; no estimate is emitted until at least one new step is observed. Training and long-audio workers run in isolated process groups; cancellation terminates and waits for the complete process tree so child Python trainers cannot retain CUDA memory. This execution and cancellation path is shared by Speaker Inversion and LoRA. Resume validates and skips an unchanged snapshot and fingerprinted complete latent manifest. LoRA passes its latest adapter checkpoint to `train.py --resume`; Speaker Inversion follows the upstream supported behavior and passes the latest periodic embedding as `--speaker-inversion-init-embedding`. Normal resume writes into `resume-runs/<attempt>` so old checkpoints remain immutable. Explicit overwrite removes only validated job/model output roots before rebuilding. The default workflow is Speaker Inversion; LoRA remains an explicit advanced choice. Every completed output carries a `studio-model.json` registry record so the user-visible model name survives deletion of disposable job history. Never overwrite dataset or RAW audio, and never place absolute machine paths in committed files. Bootstrap exposes physical CUDA capacity and method-and-precision recommendations for both training modes, allowing the frontend to warn from stable hardware facts rather than the inference model's temporary allocation. Failed jobs expose a concise cause and recovery action in history, with the local technical log available on demand.

Server-saved voice profiles under `workspace/voices/profiles.json` are the source of truth for the shared Voice Library and require stable `profile_id`, `speaker_uuid` and `style_id`. Projects retain a compatible snapshot plus the profile ID. Reconcile by ID on load; only use a unique exact-name match to migrate legacy projects. Do not regenerate stable IDs during ordinary edits. The legacy `workspace/voicevox/profiles.json` is copied once when the shared store does not yet exist.

Playback volume and output routing are browser-local preferences. Both Script and Live render the same state and apply it to the single shared audio element. Device discovery requests browser audio permission once at startup, stops the temporary input stream immediately, and falls back to the system default without blocking Studio when permission or `setSinkId()` is unavailable.

## Product UX contracts

`DESIGN.md` is the canonical interaction contract for every workspace. Shared resource controls and dialogs live in `src/components/StudioUI.jsx`; do not recreate tab-specific naming or confirmation overlays.

Reorderable lists use `src/components/SortableList.jsx`. Script lines and Voice Library entries must share its insertion-gap animation, opaque drag overlay, handle-only activation, keyboard controls, and reduced-motion behavior instead of implementing tab-specific native drag events.

Named resource APIs currently include:

- `POST /api/projects/{project_name}/rename`
- `POST /api/recording-datasets/{dataset_id}/rename`
- `POST /api/trained-models/{model_id}/rename`
- `DELETE /api/trained-models/{model_id}`

Project and recording-dataset links retain ownership of their content through rename. A trained model keeps its stable model ID, and deletion is blocked while a Voice Library profile points at its asset.

## Product decisions

`DESIGN.md` owns durable product, visual and interaction decisions. This guide owns architecture, persistence, runtime and processing contracts. `docs/ROADMAP.md` owns unimplemented candidates, while `AGENTS.md` remains a concise map of repository-wide invariants and these canonical sources. Record a decision in one owning document and link to it instead of duplicating the full rule across files.

## External engine compatibility

Studio follows the checked-out Irodori-TTS source rather than a vendored API snapshot. When upstream inference request fields change:

1. Update `studio_backend/models.py`.
2. Update the request mapping in `studio_backend/engine.py`.
3. Update frontend payload generation in `src/App.jsx`.
4. Add tests and record the required Irodori-TTS revision in release notes.

Do not silently modify the external Irodori-TTS checkout from application code. Environment synchronization belongs to the explicit setup script.

`start-studio.ps1` treats the existing Irodori-TTS `.venv` as the primary backend signal. Unless `-TorchBackend` is explicitly provided, detect the installed Torch build/runtime before consulting the saved Studio configuration or hardware fallback. This prevents setup from replacing an already working CPU, CUDA, ROCm or XPU environment merely because a different accelerator is visible on the host.
