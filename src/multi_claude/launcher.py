"""Launch `claude` in the right place depending on the surrounding environment.

Priority: tmux pane split → zellij new pane → suspend TUI and exec inline.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import App


class LauncherError(RuntimeError):
    """Raised when claude cannot be launched (e.g. binary not in PATH)."""


def detect_multiplexer() -> str | None:
    """Return 'tmux', 'zellij', or None based on env vars and available binaries."""
    if os.environ.get("TMUX") and shutil.which("tmux"):
        return "tmux"
    if os.environ.get("ZELLIJ") and shutil.which("zellij"):
        return "zellij"
    return None


def launch_claude(
    cwd: Path,
    session_id: str | None = None,
    *,
    display_name: str | None = None,
    app: "App | None" = None,
) -> None:
    """Launch `claude` with ``cwd``, optional ``--resume`` and optional ``-n``."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise LauncherError("`claude` no encontrado en PATH")

    argv = _build_claude_argv(session_id, display_name)
    mux = detect_multiplexer()
    cwd_str = str(cwd)

    if mux == "tmux":
        subprocess.run(
            ["tmux", "split-window", "-h", "-c", cwd_str, *argv],
            check=False,
        )
        return
    if mux == "zellij":
        subprocess.run(
            ["zellij", "action", "new-pane", "--cwd", cwd_str, "--", *argv],
            check=False,
        )
        return

    if app is not None:
        with app.suspend():
            subprocess.run(argv, cwd=cwd_str, check=False)
    else:
        subprocess.run(argv, cwd=cwd_str, check=False)


def _build_claude_argv(session_id: str | None, display_name: str | None = None) -> list[str]:
    argv = ["claude"]
    if session_id:
        argv += ["--resume", session_id]
    if display_name:
        argv += ["-n", display_name]
    return argv
