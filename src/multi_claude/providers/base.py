"""Provider protocol — abstraction over different AI CLI session formats.

Each supported CLI (Claude Code, Codex CLI, ...) implements :class:`Provider`.
The TUI scans every available provider, lets the user pick one, and from then
on the screens stay provider-agnostic: they call ``provider.scan_projects()``
/ ``provider.scan_sessions(project)`` and pass the resulting ``argv`` from
``provider.resume_argv(...)`` to the generic launcher dispatcher.

Adding a new provider means writing one module under ``providers/`` that
returns the four pieces this protocol asks for. The dispatcher
(multiplexer / emulator / suspend) stays untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from multi_claude.discovery import Project
from multi_claude.session import Session


@runtime_checkable
class Provider(Protocol):
    """Contract for a CLI whose sessions multi-claude can browse and resume.

    Implementations are typically lightweight value-objects: instance state is
    limited to paths and cached scan results. Each method is called from the
    Textual main loop or a worker, so blocking I/O is fine but unbounded scans
    must respect cancellation.
    """

    id: str
    """Stable identifier (``"claude"``, ``"codex"``, ...). Used in config files
    and as a registry key. Never localised."""

    display_name: str
    """Human-readable label shown in the provider-selection screen."""

    binary: str
    """Name of the CLI executable to look up in ``$PATH``. Used by
    :meth:`is_installed` and to surface ``not found`` errors with the right
    command name."""

    def is_installed(self) -> bool:
        """Return ``True`` if the CLI binary is on ``$PATH``.

        Used by the provider-selection screen to grey out (or hide) entries
        for CLIs the user hasn't installed.
        """
        ...

    def sessions_root(self) -> Path:
        """Filesystem root where this provider stores its session files.

        May not exist if the user has never used the CLI; the selection
        screen treats a missing root as "0 sessions" rather than an error.
        """
        ...

    def scan_projects(self) -> list[Project]:
        """Return every project this provider knows about, newest first.

        A "project" is whatever grouping the CLI uses for sessions — for
        Claude Code it's the ``~/.claude/projects/<encoded-cwd>/`` directory;
        for Codex it's the set of rollout files sharing the same ``cwd`` in
        their ``session_meta`` header.
        """
        ...

    def scan_sessions(self, project: Project) -> list[Session]:
        """Return every session belonging to ``project``, newest first."""
        ...

    def resume_argv(self, session_id: str, display_name: str | None = None) -> list[str]:
        """Build the CLI argv to resume ``session_id``.

        ``display_name`` is optional and only honoured by providers that
        support naming sessions on resume (Claude Code does via ``-n``).
        Providers that don't support it ignore the parameter.
        """
        ...

    def new_argv(self, display_name: str | None = None) -> list[str]:
        """Build the CLI argv to start a fresh session in the current cwd."""
        ...
