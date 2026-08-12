# Development guide

## Repository responsibilities

Irodori Studio owns the product experience and local orchestration. Irodori-TTS remains the inference and training engine.

| Repository | Responsibility |
| --- | --- |
| `irodori-studio` | React SPA, local FastAPI host, synthesis queue, project data, recording, exports, VOICEVOX compatibility and the future Training workflow |
| `Irodori-TTS` | model architecture, inference runtime, codec, Speaker Inversion, LoRA and training implementation |

Do not copy `irodori_tts/`, checkpoints, training outputs, private recordings, or user-specific absolute paths into this repository.

## Runtime boundaries

- `start-studio.ps1` resolves and validates the external Irodori-TTS repository, verifies that its installed Torch backend matches the configured backend, and executes the server with that repository's `.venv` Python directly.
- `server.py` inserts that root into `sys.path` before importing `irodori_tts`.
- `StudioEngine` owns one resident `IrodoriInferenceRuntime` and one FIFO generation worker.
- Studio HTTP and VOICEVOX compatibility HTTP share the same `StudioEngine`.
- The frontend communicates only with the local Studio HTTP API.
- Recorder microphone capture happens in the browser, then accepted and review recordings are saved through the local Studio HTTP API under ignored `workspace/recordings/`.
- Generated files, server-saved projects, named recording datasets and the shared voice library live under ignored `workspace/`.

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
studio_backend/
  engine.py              Resident runtime and FIFO synthesis queue
  models.py              HTTP request schemas
  exporter.py            WAV/subtitle/timeline production ZIP
  project_store.py       Atomic local project persistence
  recording_datasets.py Named recording datasets and training-ready manifests
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

`studio_backend/project_store.py` owns atomic local project creation, listing, loading, saving and deletion under `workspace/projects/`. Project storage formats are implementation details and must not appear in the user-facing Studio project manager.

`studio_backend/recording_datasets.py` owns named datasets under `workspace/recordings/<dataset-id>/`. Each directory contains `dataset.json`, accepted-only `dataset.jsonl`, and `wavs/`. The stable dataset ID and local API list are the contract for the Training workspace. Recorder saves automatically; do not make ZIP export the primary handoff. Legacy IndexedDB recordings are cleared only after every WAV has been copied successfully.

Server-saved voice profiles under `workspace/voices/profiles.json` are the source of truth for the shared Voice Library and require stable `profile_id`, `speaker_uuid` and `style_id`. Projects retain a compatible snapshot plus the profile ID. Reconcile by ID on load; only use a unique exact-name match to migrate legacy projects. Do not regenerate stable IDs during ordinary edits. The legacy `workspace/voicevox/profiles.json` is copied once when the shared store does not yet exist.

Playback volume and output routing are browser-local preferences. Both Script and Live render the same state and apply it to the single shared audio element. Device discovery requests browser audio permission once at startup, stops the temporary input stream immediately, and falls back to the system default without blocking Studio when permission or `setSinkId()` is unavailable.

## Product decisions

Durable decisions are recorded in `AGENTS.md`. Notable constraints include readable Japanese text, a compact production-first interface, drag-only line ordering, conditional take controls, Phosphor icons, a scrollable voice-library body, and local-only runtime behavior.

## External engine compatibility

Studio follows the checked-out Irodori-TTS source rather than a vendored API snapshot. When upstream inference request fields change:

1. Update `studio_backend/models.py`.
2. Update the request mapping in `studio_backend/engine.py`.
3. Update frontend payload generation in `src/App.jsx`.
4. Add tests and record the required Irodori-TTS revision in release notes.

Do not silently modify the external Irodori-TTS checkout from application code. Environment synchronization belongs to the explicit setup script.
