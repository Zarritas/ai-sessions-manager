"""Goose CLI provider (block/goose).

Goose persists every session to a single SQLite database. Sessions and their
messages live in two tables; we group sessions by ``working_dir`` to form
projects, and pull the first ``role='user'`` message via a correlated
subquery for the displayed first prompt.

Storage path (confirmed against ``crates/goose/src/session/session_manager.rs``
on the upstream repo, via the ``etcetera::choose_app_strategy`` crate which
applies XDG even on macOS):

- Linux/macOS: ``~/.local/share/goose/sessions/sessions.db``
- Windows: ``%APPDATA%\\Block\\goose\\data\\sessions\\sessions.db``

Column quirks worth knowing:

- ``sessions.working_dir`` — NOT ``working_directory``.
- ``messages.created_timestamp`` (INTEGER epoch-ish) is the reliable
  cronological order; ``messages.timestamp`` is a non-monotonic default.
- ``sessions.archived_at IS NULL`` filters out archived sessions — keep
  parity with what ``goose session list`` shows by default.

Resume command (from ``crates/goose-cli/src/cli.rs`` ``Identifier`` group):
``goose session --resume --id <YYYYMMDD_HHMMSS>``. Goose also accepts
``--name <NAME>`` as an alternative; we prefer ``--id`` because the
``sessions.id`` column is always populated and unambiguous, while ``name``
defaults to ``''`` for sessions the user never named.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from ai_sessions_manager.discovery import Project
from ai_sessions_manager.session import Session


def _default_sessions_db() -> Path:
    """Return the platform-native default location of ``sessions.db``."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Block" / "goose" / "data" / "sessions" / "sessions.db"
    return Path.home() / ".local" / "share" / "goose" / "sessions" / "sessions.db"


GOOSE_SESSIONS_DB = _default_sessions_db()
_PROMPT_MAX_CHARS = 120


class GooseProvider:
    """Provider implementation for the Goose CLI (``block/goose``)."""

    id = "goose"
    display_name = "Goose"
    binary = "goose"

    def is_installed(self) -> bool:
        import shutil

        return shutil.which(self.binary) is not None

    def sessions_root(self) -> Path:
        # The "root" for selection-screen purposes is the directory holding
        # sessions.db, even though the actual data lives in the .db file.
        return GOOSE_SESSIONS_DB.parent

    def scan_projects(self) -> list[Project]:
        """Group non-archived sessions by ``working_dir`` and build :class:`Project` rows."""
        rows = self._read_sessions()
        if not rows:
            return []

        # cwd → list of (sid, updated_at_epoch)
        by_cwd: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for row in rows:
            by_cwd[row["working_dir"]].append((row["id"], row["updated_at_epoch"]))

        projects: list[Project] = []
        for cwd_str, entries in by_cwd.items():
            cwd_path = Path(cwd_str)
            last_activity = max(ts for _, ts in entries)
            projects.append(
                Project(
                    name=cwd_path.name or cwd_str,
                    path=cwd_path,
                    encoded_path=cwd_path,  # Goose has no per-project dir; use cwd as identity.
                    session_count=len(entries),
                    last_activity=last_activity,
                    is_orphan=not cwd_path.is_dir(),
                    git_common_dir=None,
                )
            )
        projects.sort(key=lambda p: p.last_activity, reverse=True)
        return projects

    def scan_sessions(self, project: Project) -> list[Session]:
        """Return sessions whose ``working_dir`` matches ``project.path``."""
        target = str(project.path)
        rows = self._read_sessions(filter_working_dir=target)
        sessions: list[Session] = []
        for row in rows:
            sessions.append(
                Session(
                    id=row["id"],
                    path=GOOSE_SESSIONS_DB,  # No per-session file; surface the db.
                    first_prompt=row["first_prompt"] or "(sin prompt inicial)",
                    branch=None,  # Goose doesn't persist git branch per-session.
                    cwd=row["working_dir"],
                    message_count=row["message_count"],
                    size_bytes=0,
                    last_activity=row["updated_at_epoch"],
                    display_name=row["name"] or None,
                )
            )
        sessions.sort(key=lambda s: s.last_activity, reverse=True)
        return sessions

    def resume_argv(self, session_id: str, display_name: str | None = None) -> list[str]:
        # `--id` is more reliable than `--name` because session.id is always
        # populated; name defaults to '' for unnamed sessions.
        del display_name  # Goose doesn't accept a rename-on-resume parameter.
        return ["goose", "session", "--resume", "--id", session_id]

    def new_argv(self, display_name: str | None = None) -> list[str]:
        argv = ["goose", "session"]
        if display_name:
            argv += ["--name", display_name]
        return argv

    # ------------------------------------------------------------------- #
    # SQLite I/O                                                          #
    # ------------------------------------------------------------------- #

    def _read_sessions(
        self,
        *,
        filter_working_dir: str | None = None,
    ) -> list[dict]:
        """Run the listing query against ``sessions.db``.

        Opens read-only via the ``mode=ro`` URI so a concurrently-running
        ``goose`` process can't be locked out and we can't corrupt the db.
        Returns an empty list if the file doesn't exist yet (user never ran
        goose) or any sqlite error fires — the provider should degrade
        gracefully to "0 sessions" rather than crashing the TUI.
        """
        if not GOOSE_SESSIONS_DB.is_file():
            return []

        # `mode=ro` plus `nolock=1` would skip locking entirely but is risky
        # with a writer holding an exclusive lock. Plain `mode=ro` waits up
        # to the busy_timeout and then errors — safer.
        uri = f"file:{GOOSE_SESSIONS_DB.as_posix()}?mode=ro"
        params: tuple = ()
        where = "s.archived_at IS NULL"
        if filter_working_dir is not None:
            where += " AND s.working_dir = ?"
            params = (filter_working_dir,)

        query = f"""
            SELECT
                s.id              AS id,
                s.name            AS name,
                s.working_dir     AS working_dir,
                CAST(strftime('%s', s.updated_at) AS REAL) AS updated_at_epoch,
                (
                    SELECT COUNT(*) FROM messages m
                    WHERE m.session_id = s.id
                ) AS message_count,
                (
                    SELECT m.content_json FROM messages m
                    WHERE m.session_id = s.id AND m.role = 'user'
                    ORDER BY m.created_timestamp ASC
                    LIMIT 1
                ) AS first_user_content_json
            FROM sessions s
            WHERE {where}
            ORDER BY s.updated_at DESC
        """

        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=2.0)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
        except sqlite3.Error:
            return []

        return [
            {
                "id": r["id"],
                "name": r["name"] or "",
                "working_dir": r["working_dir"],
                "updated_at_epoch": float(r["updated_at_epoch"] or 0.0),
                "message_count": int(r["message_count"] or 0),
                "first_prompt": _extract_first_prompt(r["first_user_content_json"]),
            }
            for r in rows
        ]


def _extract_first_prompt(content_json: str | None) -> str | None:
    """Pull a plain-text prompt out of Goose's serialised ``Message`` blob.

    Goose stores the rust ``Message`` struct serde-JSON-encoded. The exact
    shape evolves with the schema migrations, but the consistent invariant is
    that user input lives in a ``content`` array of variants with a ``"text"``
    field. We try a handful of locations and bail if none yield text — the
    UI shows the fallback "(sin prompt inicial)" string.
    """
    if not content_json:
        return None
    try:
        payload = json.loads(content_json)
    except (json.JSONDecodeError, TypeError):
        return None

    # Case 1: ``{"content": [{"text": "...", ...}, ...]}``
    if isinstance(payload, dict):
        content = payload.get("content")
        text = _first_text_from_content(content)
        if text:
            return _truncate(text)

    # Case 2: bare list of content blocks.
    if isinstance(payload, list):
        text = _first_text_from_content(payload)
        if text:
            return _truncate(text)

    # Case 3: payload itself is a plain string.
    if isinstance(payload, str) and payload.strip():
        return _truncate(payload)

    return None


def _first_text_from_content(content: object) -> str | None:
    """Look for the first ``text`` field in a content-blocks-like structure."""
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict):
            # Common variants Goose uses: ``{"type": "text", "text": "..."}``,
            # ``{"Text": {"text": "..."}}`` (rust enum-tagged), or just
            # ``{"text": "..."}``. Try them in order.
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                return text
            inner = block.get("Text")
            if isinstance(inner, dict):
                text = inner.get("text")
                if isinstance(text, str) and text.strip():
                    return text
        if isinstance(block, str) and block.strip():
            return block
    return None


def _truncate(text: str, limit: int = _PROMPT_MAX_CHARS) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"
