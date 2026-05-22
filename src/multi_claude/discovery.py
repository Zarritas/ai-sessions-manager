"""Discover Claude projects on disk.

Scans `~/.claude/projects/`, resolves each encoded-path back to a real cwd
(reading the first jsonl event as source of truth), and flags orphans whose
real directory no longer exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CWD_SCAN_LINES = 80


@dataclass(frozen=True)
class Project:
    name: str
    path: Path
    encoded_path: Path
    session_count: int
    last_activity: float
    is_orphan: bool


def scan_projects(projects_dir: Path | None = None) -> list[Project]:
    """Return all projects sorted by last_activity desc."""
    if projects_dir is None:
        projects_dir = CLAUDE_PROJECTS_DIR
    if not projects_dir.is_dir():
        return []
    projects: list[Project] = []
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue
        jsonl_files = list(entry.glob("*.jsonl"))
        if not jsonl_files:
            continue
        real_cwd = resolve_real_cwd(entry) or decode_path_fallback(entry.name)
        last_activity = max(f.stat().st_mtime for f in jsonl_files)
        is_orphan = not real_cwd.is_dir()
        name = real_cwd.name or str(real_cwd)
        projects.append(
            Project(
                name=name,
                path=real_cwd,
                encoded_path=entry,
                session_count=len(jsonl_files),
                last_activity=last_activity,
                is_orphan=is_orphan,
            )
        )
    projects.sort(key=lambda p: p.last_activity, reverse=True)
    return projects


def decode_path_fallback(encoded: str) -> Path:
    """Naive heuristic: every `-` becomes `/`. Used when no jsonl yields a cwd."""
    return Path("/" + encoded.lstrip("-").replace("-", "/"))


def resolve_real_cwd(project_dir: Path) -> Path | None:
    """Read the first jsonl event with a `cwd` field. Return None if no jsonl yields one.

    Iterates files newest first so a corrupted ancient session does not block resolution.
    """
    jsonl_files = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for jsonl in jsonl_files:
        try:
            with jsonl.open("r", encoding="utf-8", errors="replace") as f:
                for _ in range(CWD_SCAN_LINES):
                    line = f.readline()
                    if not line:
                        break
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cwd = event.get("cwd")
                    if isinstance(cwd, str) and cwd:
                        return Path(cwd)
        except OSError:
            continue
    return None
