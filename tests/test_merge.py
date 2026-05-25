"""Tests for the orphan-merge flow (deletion.merge_projects)."""

from __future__ import annotations

from pathlib import Path

from ai_sessions_manager.deletion import merge_projects
from tests.conftest import write_session


def test_merge_projects_moves_jsonls_and_subdirs(tmp_path: Path) -> None:
    orphan = tmp_path / "orphan"
    dest = tmp_path / "dest"

    write_session(orphan, session_id="sid-1", cwd="/old/path", first_prompt="prompt 1")
    write_session(orphan, session_id="sid-2", cwd="/old/path", first_prompt="prompt 2")
    # subdir alongside one jsonl
    (orphan / "sid-1").mkdir()
    (orphan / "sid-1" / "data.txt").write_text("hello", encoding="utf-8")

    moved = merge_projects(orphan, dest)

    assert moved == 2
    assert not orphan.exists()
    assert (dest / "sid-1.jsonl").exists()
    assert (dest / "sid-2.jsonl").exists()
    assert (dest / "sid-1").is_dir()
    assert (dest / "sid-1" / "data.txt").read_text(encoding="utf-8") == "hello"


def test_merge_projects_skips_existing_targets(tmp_path: Path) -> None:
    """Files already at the destination are kept (no silent overwrite)."""
    orphan = tmp_path / "orphan"
    dest = tmp_path / "dest"
    write_session(orphan, session_id="sid-collision", first_prompt="orphan version")
    write_session(dest, session_id="sid-collision", first_prompt="dest version")

    moved = merge_projects(orphan, dest)

    assert moved == 0
    # Destination keeps its version
    contents = (dest / "sid-collision.jsonl").read_text(encoding="utf-8")
    assert "dest version" in contents


def test_merge_projects_noop_when_orphan_missing(tmp_path: Path) -> None:
    assert merge_projects(tmp_path / "missing", tmp_path / "dest") == 0
