"""Shared fixtures: builders for synthetic Claude project trees on tmpfs."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    """A fresh ~/.claude/projects-like directory rooted under tmp_path."""
    root = tmp_path / "projects"
    root.mkdir()
    return root


def write_session(
    project_dir: Path,
    *,
    session_id: str | None = None,
    cwd: str | None = None,
    branch: str | None = "main",
    first_prompt: str = "hola",
    extra_events: int = 5,
    mtime: float | None = None,
) -> Path:
    """Build a minimal jsonl that looks like a real Claude session."""
    project_dir.mkdir(parents=True, exist_ok=True)
    sid = session_id or str(uuid.uuid4())
    jsonl = project_dir / f"{sid}.jsonl"
    events: list[dict] = []
    if first_prompt:
        events.append(
            {
                "type": "user",
                "message": {"role": "user", "content": first_prompt},
                "cwd": cwd,
                "gitBranch": branch,
                "sessionId": sid,
                "timestamp": "2026-05-01T00:00:00.000Z",
            }
        )
    events.append(
        {
            "type": "permission-mode",
            "permissionMode": "auto",
            "sessionId": sid,
        }
    )
    for i in range(extra_events):
        events.append({"type": "assistant", "seq": i, "sessionId": sid})
    with jsonl.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    if mtime is not None:
        os.utime(jsonl, (mtime, mtime))
    return jsonl
