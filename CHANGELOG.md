# Changelog

## Unreleased

- Added sentence-aware long-text synthesis shared by Script, Live, and the VOICEVOX-compatible runtime: bounded segments are generated sequentially and returned as one WAV, while Live now surfaces playback failures, preserves retry from history, and falls back to the system output when a selected device becomes unavailable.
- Reduced Recorder tab reopen latency for large learning datasets by caching unchanged recording manifests and summaries, and by excluding long-audio import records from the corpus-recording payload without removing them from Training.
- Added an allow-listed Windows runtime package with a prebuilt frontend, no Node.js runtime requirement, SHA-256 output, and automatic attachment to newly published GitHub Releases while keeping development documentation and tests in source archives only.

## 0.3.0 — 2026-08-15

- Added method- and precision-aware CUDA preflight checks for Speaker Inversion and LoRA that warn when physical VRAM is below the recommendation, while allowing an explicit override and leaving the resident model untouched when cancelled.
- Disabled routine Uvicorn access logs by default so frequent successful polling requests do not bury Training, warning, and error output; added the opt-in `-AccessLog` launch switch for HTTP debugging.
- Fixed Training and long-audio cancellation to terminate the complete worker process tree and wait for exit, ensuring CUDA/VRAM resources are released instead of leaving a child trainer running.
- Changed the default Speaker Inversion run to 500 steps and added in-field guidance recommending 1000 steps or more when pursuing higher quality.
- Changed the default LoRA run to 1,500 steps and added 3,000-step guidance for high-quality tuning.
- Added live Training duration estimates showing approximate remaining and full-run time from observed step speed.
- Added per-dataset long-audio preprocessing history management, resumable failed/interrupted/cancelled jobs that reuse validated candidate checkpoints, and safe history deletion that retains committed WAVs and RAW sources.

## 0.2.0 — 2026-08-14

- Added the long-audio preprocessing core for multiple WAV/FLAC/MP3/M4A-compatible single-speaker sources: bounded overlapping decode windows, Silero VAD, faster-whisper Japanese transcription, automatic QC/adoption, optional transcript review state, job-local lossless FLAC intermediates, stable rerun IDs, atomic 48 kHz PCM16 WAV dataset commits, and persistent cancellable jobs without creating a giant master WAV.
- Added resumable Training jobs. Existing validated dataset snapshots and completed latent manifests are skipped by default, LoRA resumes full trainer checkpoints, Speaker Inversion warm-starts from the latest periodic embedding, and explicit all-overwrite restart removes only generated job/model artifacts.
- Established the product-wide learning-data contract: immutable RAW sources, versioned method-independent canonical samples, and model-specific job artifacts. Recording and import now apply edge-only trimming and -16 LUFS normalization once at dataset commit, while Training verifies and snapshots those WAVs without double normalization.

- Aligned tests and documentation with the current codebase, removed the retired Recorder ZIP-export path and obsolete line-order helpers, and consolidated shared audio, path, timestamp, resource-name, and playback-control behavior.
- Shortened the Japanese Live workspace label from `配信コンソール` to `配信`.
- Unified Script and Voice Library reordering with animated insertion gaps, opaque full-card drag overlays, smooth drop motion, pointer/touch support, and accessible keyboard sorting.
- Standardized the Voice Library as the rightmost header action in every workspace and added persistent drag-and-drop voice ordering shared by all voice selectors.
- Moved production export out of the shared header into a Script-only floating action, so Live no longer exposes an unrelated export workflow.
- Unified resource management and naming UX across Script, Live, Recorder, and Training; added global Voice Library access, project rename, trained-model rename/delete, shared name and confirmation dialogs, and the canonical `DESIGN.md` policy.

- Added Recorder dataset renaming and human-readable name-based workspace folders while preserving stable internal dataset IDs; legacy ID-named folders migrate automatically.
- Changed Studio setup to infer the PyTorch backend from the selected Irodori-TTS `.venv`, with explicit `-TorchBackend` retained only as an override and saved configuration/hardware used as fallbacks.
- Fixed Script voice assignment so the selected current voice is applied to new and imported lines, existing lines can change voice from their voice-name control, and the resulting audio is marked for regeneration.
- Added lifecycle cleanup for generated Script audio and metadata when lines, discarded takes, cancelled generations, or projects are deleted, while retaining files shared by another saved project.
- Added conservative dataset audio preparation with edge-only silence trimming, 180 ms padding, preserved internal pauses, -16 LUFS normalization, and per-recording provenance hashes.
- Added the Training workspace with Speaker Inversion as the recommended default, optional LoRA fine-tuning, direct Recorder dataset selection, named models, background progress/cancellation, durable job history, and Studio-owned model directories.
- Rebuilt Irodori Starter 120 as corpus v2 with 120 unique prompts, explicit Japanese mora and foreign-mora coverage, and 20 distinct fillers or backchannels; versioned prompt IDs prevent stale v1 recordings from being attached to revised text.
- Added the top-level Recording Studio with switchable Irodori Starter 120, AICA Character Core 200, and AICA Full 500 stages over one shared recording root, browser microphone selection, 48 kHz mono WAV capture, waveform and quality review, and redo/adopt navigation.
- Replaced browser-only recorder storage and the manual export workflow with named Studio datasets under `workspace/recordings`, including create/select/delete management, automatic training manifests, stable IDs shared with Training, and safe legacy IndexedDB migration.
- Added pinned AICA corpus provenance, CC0 1.0 licensing notices, performance directions, and credit metadata in Studio recording datasets.
- Added user-facing local project creation, opening, saving and deletion with atomic server persistence.
- Reworked the shared Voice Library so Speaker Inversion, reference audio, LoRA and VOICEVOX publication settings auto-save independently of projects and restore by stable profile ID.
- Added synchronized playback volume and output-device selection to Script and Live for OBS and virtual-audio routing.
- Simplified the Script workspace to one authoritative editable line list and removed duplicate sidebar navigation and line insertion controls.
- Removed JSON project file controls from the GUI and removed the unused Sites/Cloudflare static-hosting artifacts.

## 0.1.0 — 2026-08-12

- Extracted Irodori Studio into its own repository.
- Added external Irodori-TTS repository discovery and validation.
- Added one-command Windows setup and launch orchestration.
- Preserved Script, Live, Voice Library, take management, production export and VOICEVOX compatibility features.
- Added standalone architecture, development, migration and roadmap documentation.
