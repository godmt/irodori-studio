from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.project_store import ProjectStore, project_audio_files  # noqa: E402


class ProjectStoreTests(unittest.TestCase):
    def test_projects_can_be_created_listed_loaded_saved_and_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            created = store.create("番組A", {"title": "番組A", "lines": []})

            self.assertEqual(created["name"], "番組A")
            self.assertEqual(store.list()[0]["name"], "番組A")
            self.assertEqual(store.list()[0]["storage_name"], "番組A")
            self.assertEqual(store.load("番組A")["title"], "番組A")
            self.assertFalse((Path(directory) / "番組A.tmp").exists())

            store.save("番組A", {"title": "番組A", "lines": [{"text": "更新"}]})
            self.assertEqual(store.load("番組A")["lines"][0]["text"], "更新")

            deleted = store.delete("番組A")
            self.assertEqual(deleted["title"], "番組A")
            self.assertEqual(store.list(), [])
            with self.assertRaises(KeyError):
                store.load("番組A")

    def test_create_never_overwrites_an_existing_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            store.create("番組A", {"title": "番組A", "version": 1})
            with self.assertRaises(FileExistsError):
                store.create("番組A", {"title": "番組A", "version": 2})
            self.assertEqual(store.load("番組A")["version"], 1)

    def test_audio_references_include_takes_and_can_exclude_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory))
            first = {
                "title": "番組A",
                "lines": [
                    {
                        "audioFile": "selected.wav",
                        "takes": [
                            {"audioFile": "selected.wav"},
                            {"audioFile": "alternate.wav"},
                        ],
                    }
                ],
            }
            second = {
                "title": "番組B",
                "lines": [{"audioFile": "shared.wav"}],
            }
            store.create("番組A", first)
            store.create("番組B", second)

            self.assertEqual(
                project_audio_files(first), {"selected.wav", "alternate.wav"}
            )
            self.assertEqual(
                store.referenced_audio_files(),
                {"selected.wav", "alternate.wav", "shared.wav"},
            )
            self.assertEqual(
                store.referenced_audio_files(exclude_name="番組A"), {"shared.wav"}
            )


if __name__ == "__main__":
    unittest.main()
