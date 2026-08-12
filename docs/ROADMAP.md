# Product roadmap

Irodori Studio is intended to become a local end-to-end environment with three primary workspaces.

## Production — implemented

- Script editing and line ordering
- Multiple takes and adopted-take selection
- Voice library and synthesis controls
- Continuous playback and production export
- Live queue and VOICEVOX-compatible external integration

## Recorder — implemented

The existing Irodori-TTS offline corpus recorder is integrated as a first-class Studio workspace rather than an iframe or separate application.

Current scope:

- Sequential reading prompts and acting direction
- Automatic microphone permission and device refresh
- Record, stop, review, redo and progress navigation
- Named local datasets under `workspace/recordings/`
- Automatic accepted-only training manifests without a manual export step
- Stable dataset IDs that the Training workspace can select directly

The Recorder UI, audio conversion and device discovery live under `src/features/recorder`; server-owned dataset persistence lives in `studio_backend/recording_datasets.py`. The official 120-prompt starter corpus is versioned with Studio so recording remains available without running the external Irodori-TTS frontend.

## Training — planned

Provide guided local workflows around the external Irodori-TTS checkout.

Expected scope:

- Select a Studio recording dataset or add one/multiple long single-speaker recordings
- Automated resampling, denoise checks, silence segmentation and transcription
- Dataset validation and a small exception queue rather than full manual labeling
- Speaker Inversion setup, progress, checkpoints and comparison playback
- LoRA dataset preparation and training as an advanced path
- Model/embedding/adapter registration directly into the Voice Library

Training jobs should run as explicit background processes with logs, cancellation boundaries and recoverable job metadata. The UI must not conceal destructive preprocessing or overwrite source recordings.

## Architecture direction

As these workspaces are introduced, split the current frontend by feature without changing the user-facing top-level shell:

```text
src/features/
├─ production/
├─ live/
├─ recorder/
└─ training/
```

Backend orchestration should likewise separate inference and training job managers while sharing configuration, asset discovery and the Voice Library. Do not move Irodori-TTS source code into Studio; invoke the configured external repository through stable adapters.
