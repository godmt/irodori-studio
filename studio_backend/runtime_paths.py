from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_RELATIVE_PATH = Path(".studio") / "config.json"


def is_irodori_root(path: Path) -> bool:
    root = path.expanduser().resolve()
    return (
        (root / "pyproject.toml").is_file()
        and (root / "irodori_tts" / "inference_runtime.py").is_file()
    )


def load_saved_irodori_root(studio_root: Path) -> Path | None:
    config_path = studio_root / CONFIG_RELATIVE_PATH
    if not config_path.is_file():
        return None
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw_path = payload.get("irodoriTtsPath")
    return Path(raw_path).expanduser() if isinstance(raw_path, str) and raw_path.strip() else None


def resolve_irodori_root(
    studio_root: Path,
    cli_path: str | None = None,
    environ: dict[str, str] | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    candidates: list[tuple[str, Path | None]] = [
        ("--irodori-root", Path(cli_path).expanduser() if cli_path else None),
        (
            "IRODORI_TTS_PATH",
            Path(environment["IRODORI_TTS_PATH"]).expanduser()
            if environment.get("IRODORI_TTS_PATH")
            else None,
        ),
        (str(CONFIG_RELATIVE_PATH), load_saved_irodori_root(studio_root)),
        ("sibling directory", studio_root.parent / "Irodori-TTS"),
    ]
    invalid: list[str] = []
    for source, candidate in candidates:
        if candidate is None:
            continue
        resolved = candidate.resolve()
        if is_irodori_root(resolved):
            return resolved
        invalid.append(f"{source}: {resolved}")

    details = "\n".join(f"  - {entry}" for entry in invalid)
    if details:
        details = f"\nChecked invalid candidates:\n{details}"
    raise RuntimeError(
        "Irodori-TTS repository was not found. Run start-studio.ps1 with "
        "-IrodoriPath <path>, or set IRODORI_TTS_PATH."
        f"{details}"
    )
