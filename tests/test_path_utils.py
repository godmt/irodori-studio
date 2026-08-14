from __future__ import annotations

import sys
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.path_utils import safe_stem  # noqa: E402


class PathUtilsTests(unittest.TestCase):
    def test_safe_stem_removes_path_punctuation(self) -> None:
        self.assertEqual(safe_stem(" ../番組:テスト/ "), "番組-テスト")

    def test_safe_stem_uses_fallback_for_punctuation_only_names(self) -> None:
        self.assertEqual(safe_stem(" ../ ", "resource"), "resource")


if __name__ == "__main__":
    unittest.main()
