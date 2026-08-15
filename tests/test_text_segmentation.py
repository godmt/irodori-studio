from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio_backend.text_segmentation import split_synthesis_text  # noqa: E402


class TextSegmentationTests(unittest.TestCase):
    def test_short_text_remains_one_segment(self) -> None:
        self.assertEqual(split_synthesis_text("短い文章です。"), ["短い文章です。"])

    def test_reported_live_sentence_splits_at_full_stop(self) -> None:
        text = (
            "ほ、このダージリンは素晴らしい香りがしますわね～。"
            "午後の優雅なひとときには、やはりこの最高級の茶葉でなければなりませんわ～。"
            "おほほほ～🤭"
        )

        chunks = split_synthesis_text(text)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0], "ほ、このダージリンは素晴らしい香りがしますわね～。")
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(chunk) <= 64 for chunk in chunks))

    def test_long_sentence_uses_secondary_punctuation_before_hard_cut(self) -> None:
        text = "あ" * 35 + "、" + "い" * 35 + "、" + "う" * 35

        chunks = split_synthesis_text(text)

        self.assertTrue(chunks[0].endswith("、"))
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(chunk) <= 64 for chunk in chunks))

    def test_unbroken_text_has_a_bounded_fallback(self) -> None:
        text = "長" * 150

        chunks = split_synthesis_text(text)

        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(1 <= len(chunk) <= 64 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
