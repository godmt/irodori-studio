# Product roadmap

Irodori Studio is intended to become a local end-to-end environment with three primary workspaces.

## Production — implemented

- Script editing and line ordering
- Multiple takes and adopted-take selection
- Voice library and synthesis controls
- Continuous playback and production export
- Live queue and VOICEVOX-compatible external integration

## Recorder — planned

Integrate the existing offline corpus-recorder concept as a first-class tab rather than an iframe or separate hosted site.

Expected scope:

- Sequential reading prompts and acting direction
- Automatic microphone permission and device refresh
- Record, stop, review, redo and progress navigation
- Local browser storage with no server transfer
- Partial or complete ZIP export compatible with Irodori dataset preparation
- Importing the resulting corpus into the Training workspace

The public static recorder can remain a separately deployable build, but shared prompt schemas and validation should move into reusable modules.

## Training — planned

Provide guided local workflows around the external Irodori-TTS checkout.

Expected scope:

- Import recorder ZIP or one/multiple long single-speaker recordings
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
