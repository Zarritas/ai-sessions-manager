"""opencode CLI provider (sst/opencode).

opencode persists every session to a single SQLite database. Unlike Goose,
opencode uses the literal XDG layout on **all** platforms (including macOS
and Windows — confirmed via the upstream ``xdg-basedir`` dependency and
issue #8235), so the path is the same shape everywhere:

    ~/.local/share/opencode/opencode.db

Overrides:

- ``$XDG_DATA_HOME`` — if set, replaces ``~/.local/share``.
- ``$OPENCODE_DB`` — absolute path to a specific db file (used by tests and
  non-prod channels which write to ``opencode-<channel>.db``).

Schema (verified against an actual ``opencode.db`` v1.1.35):

- ``session`` table (singular, Drizzle default): ``id`` (PK), ``directory``
  (= cwd), ``title``, ``time_created``, ``time_updated`` (epoch ms),
  ``time_archived``, ``parent_id`` (self-FK for forks), ``project_id``,
  ``slug``, ``version``, ``share_url``, ``permission`` (JSON), ``revert``,
  ``summary_additions``, ``summary_deletions``, ``summary_files``,
  ``summary_diffs``, ``time_compacting``.
- ``message`` table (singular): ``id`` (PK), ``session_id``, ``data`` (JSON
  blob with role + parts), ``time_created``, ``time_updated`` (epoch ms).
- Other tables we ignore: ``part`` (individual message blocks),
  ``project``, ``permission``, ``session_share``, ``todo``,
  ``control_account``.

We filter root sessions (``parent_id IS NULL``) by default so forks don't
show up as duplicate listings.

Resume (from ``packages/opencode/src/cli/cmd/run.ts``):

    opencode run --session <session-id>     # or -s <id>
    opencode run --continue                 # last root session
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from ai_sessions_manager.discovery import Project
from ai_sessions_manager.session import Session


def _default_db_path() -> Path:
    """Resolve the opencode SQLite path honouring overrides.

    Order:
      1. ``$OPENCODE_DB`` — explicit absolute path (highest priority).
      2. ``$XDG_DATA_HOME/opencode/opencode.db``.
      3. ``~/.local/share/opencode/opencode.db``.
    """
    explicit = os.environ.get("OPENCODE_DB")
    if explicit:
        return Path(explicit)
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "opencode" / "opencode.db"


OPENCODE_DB = _default_db_path()
_PROMPT_MAX_CHARS = 120


class OpenCodeProvider:
    """Provider implementation for opencode (``sst/opencode``)."""

    id = "opencode"
    display_name = "opencode"
    binary = "opencode"

    def is_installed(self) -> bool:
        import shutil

        return shutil.which(self.binary) is not None

    def sessions_root(self) -> Path:
        return OPENCODE_DB.parent

    def scan_projects(self) -> list[Project]:
        """Group non-archived root sessions by canonicalised ``directory``.

        opencode stores cwds inconsistently — the same directory may appear
        as ``D:\\Programing\\X`` and ``d:/Programing/X`` in different rows
        (case differs, slashes differ). We canonicalise before grouping so
        the same on-disk directory collapses into one project row.
        """
        rows = self._read_sessions()
        if not rows:
            return []

        # canonical_key → (display_directory, list_of_(id, ts))
        groups: dict[str, tuple[str, list[tuple[str, float]]]] = {}
        for row in rows:
            key = _canon(row["directory"])
            if key not in groups:
                groups[key] = (row["directory"], [])
            groups[key][1].append((row["id"], row["time_updated_epoch"]))

        projects: list[Project] = []
        for display_dir, entries in groups.values():
            cwd_path = Path(display_dir)
            last_activity = max(ts for _, ts in entries)
            projects.append(
                Project(
                    name=cwd_path.name or display_dir,
                    path=cwd_path,
                    encoded_path=cwd_path,
                    session_count=len(entries),
                    last_activity=last_activity,
                    is_orphan=not cwd_path.is_dir(),
                    git_common_dir=None,
                )
            )
        projects.sort(key=lambda p: p.last_activity, reverse=True)
        return projects

    def scan_sessions(self, project: Project) -> list[Session]:
        target_key = _canon(str(project.path))
        # Filter Python-side because the SQL ``=`` can't see through the
        # slash/case quirks. With ~hundreds of sessions per db the cost is
        # immaterial.
        rows = [r for r in self._read_sessions() if _canon(r["directory"]) == target_key]
        sessions: list[Session] = []
        for row in rows:
            sessions.append(
                Session(
                    id=row["id"],
                    path=OPENCODE_DB,
                    first_prompt=row["first_prompt"] or "(sin prompt inicial)",
                    branch=None,  # opencode doesn't persist git branch per session.
                    cwd=row["directory"],
                    message_count=row["message_count"],
                    size_bytes=0,
                    last_activity=row["time_updated_epoch"],
                    display_name=row["title"] or None,
                )
            )
        sessions.sort(key=lambda s: s.last_activity, reverse=True)
        return sessions

    def resume_argv(self, session_id: str, display_name: str | None = None) -> list[str]:
        # `run -s <id>` re-enters an existing session. Confirmed in
        # `packages/opencode/src/cli/cmd/run.ts`. `display_name` is ignored —
        # opencode has no rename-on-resume flag.
        del display_name
        return ["opencode", "run", "-s", session_id]

    def new_argv(self, display_name: str | None = None) -> list[str]:
        # `opencode` with no args drops into the TUI which creates a new
        # session bound to the current cwd. `display_name` (would-be title)
        # isn't a CLI flag — users rename from inside the TUI.
        del display_name
        return ["opencode"]

    # ------------------------------------------------------------------- #
    # SQLite I/O                                                          #
    # ------------------------------------------------------------------- #

    def _read_sessions(self) -> list[dict]:
        """Run the listing query against ``opencode.db``.

        Filters to root sessions (``parent_id IS NULL``) so forks don't
        appear as separate top-level rows. Returns empty list on any
        sqlite error or missing db so the TUI degrades gracefully.

        Directory filtering happens Python-side in :meth:`scan_sessions`
        because opencode's cwds aren't stored canonically — see the
        ``_canon`` helper at the bottom of this module.
        """
        if not OPENCODE_DB.is_file():
            return []

        uri = f"file:{OPENCODE_DB.as_posix()}?mode=ro"
        params: tuple = ()
        where = "s.time_archived IS NULL AND s.parent_id IS NULL"

        # The first user prompt isn't stored in ``message.data`` — that
        # only holds role/time/summary. The actual text lives in the
        # ``part`` table, one block per record. We pull the earliest text
        # part of the earliest user message.
        query = f"""
            SELECT
                s.id              AS id,
                s.title           AS title,
                s.directory       AS directory,
                s.time_updated    AS time_updated_epoch,
                (
                    SELECT COUNT(*) FROM message m
                    WHERE m.session_id = s.id
                ) AS message_count,
                (
                    SELECT p.data FROM part p
                    JOIN message m ON p.message_id = m.id
                    WHERE m.session_id = s.id
                      AND json_extract(m.data, '$.role') = 'user'
                      AND json_extract(p.data, '$.type') = 'text'
                    ORDER BY m.time_created ASC, p.time_created ASC
                    LIMIT 1
                ) AS first_user_part_data
            FROM session s
            WHERE {where}
            ORDER BY s.time_updated DESC
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
                "title": r["title"] or "",
                "directory": r["directory"],
                # opencode stores timestamps as epoch milliseconds. Convert
                # to seconds-float for parity with the rest of the codebase
                # which uses ``stat().st_mtime``.
                "time_updated_epoch": float(r["time_updated_epoch"] or 0.0) / 1000.0,
                "message_count": int(r["message_count"] or 0),
                "first_prompt": _extract_first_prompt(r["first_user_part_data"]),
            }
            for r in rows
        ]


def _extract_first_prompt(part_data_json: str | None) -> str | None:
    """Pull plain text out of a ``part.data`` JSON blob.

    The canonical shape from ``part`` rows is ``{"type": "text", "text": "..."}``;
    other ``type`` values (tool_use, tool_result, file, etc.) get filtered
    by the SQL query so we should only ever see text parts here.
    """
    if not part_data_json:
        return None
    try:
        payload = json.loads(part_data_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return _truncate(text)
    return None


def _canon(directory: str) -> str:
    """Canonicalise a path string for cross-row comparison.

    opencode stores the cwd inconsistently (mixed slashes, mixed casing on
    Windows). Round-tripping through :class:`Path` normalises separators
    to the platform native, and :func:`os.path.normcase` lower-cases on
    Windows (no-op on POSIX). The result is stable enough to use as a
    dict key for grouping and for equality filtering.
    """
    return os.path.normcase(str(Path(directory)))


def _truncate(text: str, limit: int = _PROMPT_MAX_CHARS) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"
