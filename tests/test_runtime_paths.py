from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.runtime_paths import resolve_irodori_root  # noqa: E402


def make_irodori_root(path: Path) -> Path:
    package = path / "irodori_tts"
    package.mkdir(parents=True)
    (path / "pyproject.toml").write_text("[project]\nname='irodori-tts'\n", encoding="utf-8")
    (package / "inference_runtime.py").write_text("", encoding="utf-8")
    return path


class RuntimePathTests(unittest.TestCase):
    def test_cli_path_has_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            studio = root / "studio"
            studio.mkdir()
            cli = make_irodori_root(root / "cli")
            environment = make_irodori_root(root / "environment")
            resolved = resolve_irodori_root(
                studio, str(cli), {"IRODORI_TTS_PATH": str(environment)}
            )
            self.assertEqual(resolved, cli.resolve())

    def test_saved_configuration_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            studio = root / "studio"
            config_dir = studio / ".studio"
            config_dir.mkdir(parents=True)
            irodori = make_irodori_root(root / "engine")
            (config_dir / "config.json").write_text(
                json.dumps({"irodoriTtsPath": str(irodori)}), encoding="utf-8"
            )
            self.assertEqual(resolve_irodori_root(studio, environ={}), irodori.resolve())

    def test_missing_repository_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            studio = Path(directory) / "studio"
            studio.mkdir()
            with self.assertRaisesRegex(RuntimeError, "-IrodoriPath"):
                resolve_irodori_root(studio, environ={})


if __name__ == "__main__":
    unittest.main()
