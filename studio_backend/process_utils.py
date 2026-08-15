from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any


def isolated_process_kwargs(*, hide_window: bool = False) -> dict[str, Any]:
    """Start a worker in a process group that can be cancelled as one unit."""

    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if hide_window:
            flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def terminate_process_tree(
    process: subprocess.Popen[Any], *, timeout_seconds: float = 10.0
) -> None:
    """Terminate a worker and every child so CUDA allocations are released."""

    if process.poll() is not None:
        return

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.terminate()
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            process.terminate()

    try:
        process.wait(timeout=timeout_seconds)
        return
    except subprocess.TimeoutExpired:
        pass

    if sys.platform == "win32":
        process.kill()
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            process.kill()
    process.wait(timeout=timeout_seconds)
