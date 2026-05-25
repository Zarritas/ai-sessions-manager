"""Claude Code provider — wraps the original ``discovery`` and ``session`` modules.

This is a thin adapter: scanning logic stays in the existing modules
(``multi_claude.discovery``, ``multi_claude.session``) because those still
serve the legacy single-provider entry points. The provider only delegates and
adds the Claude-specific argv builder.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from multi_claude.discovery import CLAUDE_PROJECTS_DIR, Project, scan_projects
from multi_claude.session import Session, scan_sessions


class ClaudeProvider:
    """:class:`multi_claude.providers.base.Provider` implementation for Claude Code."""

    id = "claude"
    display_name = "Claude Code"
    binary = "claude"

    def is_installed(self) -> bool:
        return shutil.which(self.binary) is not None

    def sessions_root(self) -> Path:
        return CLAUDE_PROJECTS_DIR

    def scan_projects(self) -> list[Project]:
        return scan_projects()

    def scan_sessions(self, project: Project) -> list[Session]:
        return scan_sessions(project.encoded_path)

    def resume_argv(self, session_id: str, display_name: str | None = None) -> list[str]:
        argv = ["claude", "--resume", session_id]
        if display_name:
            argv += ["-n", display_name]
        return argv

    def new_argv(self, display_name: str | None = None) -> list[str]:
        argv = ["claude"]
        if display_name:
            argv += ["-n", display_name]
        return argv
