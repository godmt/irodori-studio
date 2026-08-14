from __future__ import annotations

import argparse
import json
from pathlib import Path

from studio_backend.audio_import import LongAudioImportProcessor

PROGRESS_PREFIX = "STUDIO_AUDIO_IMPORT_PROGRESS "


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Irodori Studio long-audio import worker")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))

    def report_progress(payload: dict[str, object]) -> None:
        print(
            PROGRESS_PREFIX
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )

    LongAudioImportProcessor().process(
        config,
        args.output_dir,
        progress=report_progress,
    )


if __name__ == "__main__":
    main()
