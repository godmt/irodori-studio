# Irodori Studio development instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so a frontend-only demonstration can be handed to Sites. The actual synthesizer remains a local Python application and is not supplied by static hosting. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Product decisions for this prototype

- This is a desktop-first local production tool for Irodori-TTS, not a public hosted synthesizer.
- The selected visual source is the supplied warm ivory/orange script editor: compact left navigation, large editable line cards, and a persistent bottom inspector.
- Core workflows must be real, not mocked: load a local checkpoint, queue synthesis, play one line or continuously from a selected line, reorder/duplicate/delete lines, and export production files.
- Streaming support means a low-friction live input queue with stop/interrupt and automatic playback.
- Video-production support means persistent projects, batch generation, a joined master WAV, per-line WAV files, SRT/VTT subtitles, CSV timing data, and an FFmpeg concat list.
- Japanese body text must remain comfortably readable; avoid tiny labels and low-contrast gray text.
- Playback volume is a browser-local setting, available in the script toolbar above the reading list, and must affect all in-app playback without altering generated or exported audio files.
- Every script line exposes a refresh-icon action that adds and selects a new take using the current text, voice, and synthesis parameters without starting playback.
- VOICEVOX-compatible speaker/style definitions are saved by the local server, not only in browser storage. A Style ID and Speaker UUID stay stable across edits and restarts until that API registration is explicitly deleted.
- External speech clients use the separate local compatibility endpoint on `127.0.0.1:50021`; Studio and the compatibility API share the same resident model and FIFO synthesis queue.
- The voice library keeps its header visible and gives the modal body a dedicated vertical scroll area, so API details and save/delete actions remain reachable at ordinary desktop and mobile viewport heights.
- Use Phosphor Icons for interface icons. Do not substitute emoji or handcrafted SVG/CSS icons.
- The script and live text editors expose the official 45 Irodori performance emojis from an in-field Phosphor Smiley trigger. Insert at the remembered caret/selection, offer a compact common set before the full palette, and keep text emoji independent from Voice Design caption presets so both conditions can be used together.
- Script lines are reordered by drag only; do not restore redundant up/down buttons. The refresh icon creates and selects a new take with the current text, voice, and synthesis settings. Keep at most four takes per line, show the numbered take selector only when multiple takes exist, and make Play, Download, continuous playback, and export use the selected take.
- Irodori-TTS is an external, user-configured repository. Do not vendor it, copy model/training code into Studio, or commit an absolute local path. Resolve it through `--irodori-root`, `IRODORI_TTS_PATH`, ignored `.studio/config.json`, or the sibling-folder fallback.
- `start-studio.ps1` owns local orchestration: frontend setup/build, Irodori environment selection, Studio API, model autoload, browser opening, and the VOICEVOX compatibility endpoint.
- Recorder and Training are planned top-level workspaces. Keep new feature code separable so the current Script/Live implementation can move under `src/features/production` and `src/features/live` without changing persisted project semantics.
