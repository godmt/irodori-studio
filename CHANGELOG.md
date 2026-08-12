# Changelog

## Unreleased

- Rebuilt Irodori Starter 120 as corpus v2 with 120 unique prompts, explicit Japanese mora and foreign-mora coverage, and 20 distinct fillers or backchannels; versioned prompt IDs prevent stale v1 recordings from being attached to revised text.
- Added the top-level Recording Studio with switchable Irodori Starter 120, AICA Character Core 200, and AICA Full 500 stages over one shared recording root, browser microphone selection, 48 kHz mono WAV capture, waveform and quality review, and redo/adopt navigation.
- Replaced browser-only recorder storage and the manual export workflow with named Studio datasets under `workspace/recordings`, including create/select/delete management, automatic training manifests, stable IDs for the upcoming Training workspace, and safe legacy IndexedDB migration.
- Added pinned AICA corpus provenance, CC0 1.0 licensing notices, performance directions, and credit metadata in AICA recording exports.
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
