# Changelog

## Unreleased

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
