# Extraction from Irodori-TTS

## Status

Irodori Studio became an independent repository at version 0.1.0. This repository is now the source of truth for the Studio SPA, local server, production export, voice library and VOICEVOX compatibility layer.

The extraction preserved:

- Script and Live workspaces
- Project schema and single-audio-to-takes migration
- Voice profiles with stable VOICEVOX IDs
- Production exporter and API compatibility tests
- Product decisions in `AGENTS.md`
- Repository boundary documentation and an implementation-status roadmap

The local migration also copied the ignored `workspace/` data so previously generated WAV files, saved projects, exports and server-side voice profiles continue to work. Those files are intentionally not part of Git history.

## Deliberately not migrated into Git

- Irodori-TTS source code
- Model checkpoints and Hugging Face cache files
- Speaker Inversion embeddings and LoRA adapters
- Private source recordings and training datasets
- Generated audio, exports and saved local projects
- Machine-specific Irodori-TTS paths
- Build output, Node modules and virtual environments

These remain external or ignored. Studio discovers model and training assets from the configured Irodori-TTS repository at runtime.

## Development continuation

Continue Studio changes in this repository. Changes to model architecture, inference primitives, Speaker Inversion or LoRA training belong upstream in Irodori-TTS. When work crosses the boundary, implement a narrow adapter in Studio and document the minimum compatible Irodori-TTS revision.

Recorder and Training are now top-level workspaces implemented under `src/features/recorder` and `src/features/training`. Their server-owned persistence and orchestration live in `studio_backend/recording_datasets.py`, `studio_backend/dataset_preprocessing.py`, and `studio_backend/training_jobs.py`. Dataset preprocessing is method-independent and happens when audio enters the dataset; Training snapshots those canonical files and owns only model-specific preparation. Keep the external Irodori-TTS repository boundary intact; current implementation status and remaining candidates are recorded in `ROADMAP.md`.
