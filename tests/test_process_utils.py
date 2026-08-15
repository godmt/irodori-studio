from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from studio_backend.process_utils import (  # noqa: E402
    isolated_process_kwargs,
    terminate_process_tree,
)


class ProcessUtilsTests(unittest.TestCase):
    def test_workers_start_in_an_isolated_process_group(self) -> None:
        kwargs = isolated_process_kwargs(hide_window=True)
        if sys.platform == "win32":
            self.assertIn("creationflags", kwargs)
            self.assertTrue(
                kwargs["creationflags"]
                & getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        else:
            self.assertEqual(kwargs, {"start_new_session": True})

    @patch("studio_backend.process_utils.subprocess.run")
    @patch("studio_backend.process_utils.sys.platform", "win32")
    def test_windows_cancellation_kills_the_complete_process_tree(
        self, run: Mock
    ) -> None:
        process = Mock(pid=4321)
        process.poll.return_value = None
        process.wait.return_value = 0

        terminate_process_tree(process, timeout_seconds=2)

        run.assert_called_once_with(
            ["taskkill", "/PID", "4321", "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        process.wait.assert_called_once_with(timeout=2)
        process.terminate.assert_not_called()
        process.kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
