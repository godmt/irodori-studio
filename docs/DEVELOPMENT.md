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
- `server.py` inserts that root into `sys.path` before importing `irodori_tts`.
- `StudioEngine` owns one resident `IrodoriInferenceRuntime` and one FIFO generation worker.
- Studio HTTP and VOICEVOX compatibility HTTP share the same `StudioEngine`.
- The frontend communicates only with the local Studio HTTP API.
- Recorder microphone capture happens in the browser, then accepted and review recordings are saved through the local Studio HTTP API under ignored `workspace/recordings/`.
- Training runs Irodori-TTS preprocessing and training in child processes. Studio owns job state, cancellation and output discovery but never copies the trainer source.
- Generated files, server-saved projects, named recording datasets, training state, learned models and the shared voice library live under ignored `workspace/`.

## Source map

```text
src/
  App.jsx                 Main application and current Script/Live workspaces
  audio-output.js         Browser output-device discovery and preference helpers
  defaults.js            Persistent project schema and migration defaults
  project-state.js       Pure line, take and ordering operations
  emoji-data.js          Official Irodori performance emoji metadata
  voice-library.js       Server profile/project voice reconciliation and payload mapping
  features/recorder/     Corpus UI, microphone capture, WAV conversion and named dataset management
  features/training/     Guided Speaker Inversion/LoRA setup, progress and model history
studio_backend/
  engine.py              Resident runtime and FIFO synthesis queue
  models.py              HTTP request schemas
  exporter.py            WAV/subtitle/timeline production ZIP
  project_store.py       Atomic local project persistence
  recording_datasets.py Named recording datasets and training-ready manifests
  training_jobs.py      External Irodori-TTS preprocessing/training process manager
  voice_profiles.py      Shared Voice Library and stable VOICEVOX speaker/style persistence
  voicevox_api.py        Compatibility endpoints
  runtime_paths.py       External Irodori-TTS discovery and validation
server.py                Local API, static SPA host and process orchestration
```

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

For changes to synthesis, voice selection, take handling or export, also run Studio against a real loaded model and verify the browser interaction. Avoid treating build success as runtime verification.

## Persistent schema compatibility

Browser projects are hydrated through `hydrateProject()` in `src/defaults.js`. Add migrations or safe defaults there whenever fields change. Existing single-audio lines are migrated into `takes[0]`; keep that compatibility when editing the take model.

`studio_backend/project_store.py` owns atomic local project creation, listing, loading, saving and deletion under `workspace/projects/`, including collection of every generated WAV referenced by selected and alternate takes. `studio_backend/generated_audio.py` safely removes released WAV basenames and matching JSON metadata. Line and capped-take deletion calls `/api/audio/release`; project save/delete performs the same reference-aware cleanup on the server. Never remove user-supplied reference audio, and retain generated files still referenced by another saved project. Project storage formats are implementation details and must not appear in the user-facing Studio project manager.

`studio_backend/recording_datasets.py` owns named datasets under human-readable `workspace/recordings/<dataset-name>/` directories. Each directory contains `dataset.json`, accepted-only `dataset.jsonl`, and `wavs/`. The folder name follows the user-visible name and changes on rename, while the opaque ID inside `dataset.json` remains stable and is resolved by scanning manifests. That stable ID and the local API list are the contract for the Training workspace. Migrate legacy ID-named folders on store initialization, add a numeric suffix only for filesystem collisions, and reject duplicate user-visible names. Recorder saves automatically; do not make ZIP export the primary handoff. Legacy IndexedDB recordings are cleared only after every WAV has been copied successfully.

`studio_backend/training_jobs.py` owns job state under `workspace/training/<job-id>/`, invokes the configured external checkout's `prepare_manifest.py` and `train.py`, and writes final assets beneath `workspace/models/speaker-embeddings/` or `workspace/models/lora/`. `studio_backend/audio_preprocessing.py` makes job-local WAV copies, trims only leading/trailing silence at -45 dBFS with 10 ms analysis windows and 180 ms boundary padding, preserves internal pauses, and records the result in `preprocessing.json`. DACVAE encoding then applies an explicit -16 dB loudness target. The default workflow is Speaker Inversion; LoRA remains an explicit advanced choice. Every completed output carries a `studio-model.json` registry record so the user-visible model name survives deletion of disposable job history. Never overwrite source recordings or place absolute machine paths in committed files.

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

Durable decisions are recorded in `AGENTS.md`. Notable constraints include readable Japanese text, a compact production-first interface, drag-only line ordering, conditional take controls, Phosphor icons, a scrollable voice-library body, and local-only runtime behavior.

## External engine compatibility

Studio follows the checked-out Irodori-TTS source rather than a vendored API snapshot. When upstream inference request fields change:

1. Update `studio_backend/models.py`.
2. Update the request mapping in `studio_backend/engine.py`.
3. Update frontend payload generation in `src/App.jsx`.
4. Add tests and record the required Irodori-TTS revision in release notes.

Do not silently modify the external Irodori-TTS checkout from application code. Environment synchronization belongs to the explicit setup script.

`start-studio.ps1` treats the existing Irodori-TTS `.venv` as the primary backend signal. Unless `-TorchBackend` is explicitly provided, detect the installed Torch build/runtime before consulting the saved Studio configuration or hardware fallback. This prevents setup from replacing an already working CPU, CUDA, ROCm or XPU environment merely because a different accelerator is visible on the host.
