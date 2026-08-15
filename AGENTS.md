# Irodori Studio repository instructions

## Working agreement

- The application code is the behavioral source of truth. Keep tests and documentation aligned with implemented behavior; do not preserve obsolete contracts only because a test or document still mentions them.
- Read the relevant canonical document below before changing that area. Do not copy detailed feature specifications back into this file.
- Build the SPA in `src/`. Run the local server and open the available browser preview yourself when runtime or UI verification is relevant.
- Before substantial visual changes, read `DESIGN.md` and inspect the current product. If the visual source is unclear, use the available Product Design context or audit workflow. When a selected mock exists, treat it as the source of truth for layout, hierarchy, density, spacing, color and typography.
- Verify in proportion to the change. The standard commands and area-specific checks are documented in `docs/DEVELOPMENT.md`.

## Non-negotiable project boundaries

- Irodori Studio is a desktop-first, local-only SPA served by FastAPI from `dist/client`. It is not a Sites, Pages, Worker or other static-hosting project. Do not add `.openai/hosting.json` or cloud-hosting artifacts.
- Irodori-TTS is an external, user-configured inference and training engine. Do not vendor it, silently edit it, commit private checkpoints or recordings, or commit machine-specific absolute paths.
- Implement real local workflows, not UI-only mocks. Preserve user work across reloads, navigation, renames, migrations, cancellations and resumptions.
- Stable IDs and server-owned persistence are contracts. Rename and migrate resources without severing references; use atomic writes and reference-aware cleanup for destructive operations.
- Learning data follows three layers: immutable source data, versioned method-independent canonical samples, and model-specific training artifacts. Never overwrite RAW or repeat common audio transforms during model training.
- Long-running preprocessing and training jobs must be cancellable and resumable. Stopping must terminate the complete worker tree and release CPU, RAM and accelerator resources.
- Reuse shared product patterns and components. New tab-specific variants require a documented reason in the appropriate canonical document.

## Canonical documents

| Concern | Canonical source |
| --- | --- |
| Product principles, workspace roles, UX, visual language, accessibility and interaction details | [`DESIGN.md`](DESIGN.md) |
| Architecture, runtime boundaries, persistence, processing pipelines, external-engine integration and verification | [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) |
| Implemented user-facing features, setup and everyday operation | [`README.md`](README.md) |
| Current implementation status and future candidates | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| VOICEVOX-compatible API surface | [`docs/VOICEVOX_API_COMPATIBILITY.md`](docs/VOICEVOX_API_COMPATIBILITY.md) |
| Third-party corpora, assets and license notices | [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) |

Record durable UI and product decisions in `DESIGN.md`, technical and persistence contracts in `docs/DEVELOPMENT.md`, and unimplemented candidates in `docs/ROADMAP.md`. Change `AGENTS.md` only when a repository-wide invariant or this documentation routing changes.
