"""Delete sessions and projects, cleaning every related artefact on disk.

Per-session disk artefacts found in a live Claude install:
- ``~/.claude/projects/<encoded>/<id>.jsonl``   — main log
- ``~/.claude/projects/<encoded>/<id>/``        — directory with subagents data
- ``~/.claude/session-env/<id>``                — env vars (file or dir)
- Entry in ``NamesStore``                       — display name

Deleting a project cascades the per-session cleanup over every jsonl inside and
then rmtree's the encoded directory itself.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from multi_claude.names import NamesStore


CLAUDE_HOME = Path.home() / ".claude"
SESSION_ENV_DIR = CLAUDE_HOME / "session-env"
ACTIVE_SESSIONS_DIR = CLAUDE_HOME / "sessions"


def delete_session(
    session_id: str,
    project_dir: Path,
    *,
    names_store: NamesStore | None = None,
    session_env_dir: Path = SESSION_ENV_DIR,
) -> None:
    """Remove every artefact tied to ``session_id``. Idempotent."""
    jsonl = project_dir / f"{session_id}.jsonl"
    jsonl.unlink(missing_ok=True)

    subdir = project_dir / session_id
    if subdir.is_dir():
        shutil.rmtree(subdir, ignore_errors=True)

    env_path = session_env_dir / session_id
    if env_path.is_dir():
        shutil.rmtree(env_path, ignore_errors=True)
    elif env_path.exists():
        env_path.unlink(missing_ok=True)

    (names_store or NamesStore()).delete(session_id)


def delete_project(
    project_dir: Path,
    *,
    names_store: NamesStore | None = None,
    session_env_dir: Path = SESSION_ENV_DIR,
) -> None:
    """Remove every session inside ``project_dir`` plus the directory itself."""
    store = names_store or NamesStore()
    if project_dir.is_dir():
        for jsonl in project_dir.glob("*.jsonl"):
            delete_session(
                jsonl.stem,
                project_dir,
                names_store=store,
                session_env_dir=session_env_dir,
            )
        shutil.rmtree(project_dir, ignore_errors=True)


def list_active_sessions(
    sessions_dir: Path = ACTIVE_SESSIONS_DIR,
) -> set[str]:
    """Return session ids currently registered as live in ``~/.claude/sessions/``."""
    active: set[str] = set()
    if not sessions_dir.is_dir():
        return active
    for entry in sessions_dir.glob("*.json"):
        try:
            with entry.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        sid = data.get("sessionId") if isinstance(data, dict) else None
        if isinstance(sid, str) and sid:
            active.add(sid)
    return active
