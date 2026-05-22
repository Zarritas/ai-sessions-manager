"""Tests for multi_claude.discovery."""

from __future__ import annotations

from pathlib import Path

from multi_claude.discovery import (
    decode_path_fallback,
    resolve_real_cwd,
    scan_projects,
)

from tests.conftest import write_session


def test_decode_path_fallback_handles_naive_dash_to_slash() -> None:
    assert decode_path_fallback("-home-jesus-WS-project") == Path("/home/jesus/WS/project")


def test_resolve_real_cwd_reads_first_jsonl_cwd(tmp_path: Path) -> None:
    project_dir = tmp_path / "-home-foo-bar"
    write_session(project_dir, cwd="/home/foo/bar")
    assert resolve_real_cwd(project_dir) == Path("/home/foo/bar")


def test_resolve_real_cwd_skips_jsonl_without_cwd(tmp_path: Path) -> None:
    project_dir = tmp_path / "p"
    write_session(project_dir, session_id="a", cwd=None, mtime=2000.0)
    write_session(project_dir, session_id="b", cwd="/real/path", mtime=1000.0)
    # 'a' is newer so checked first but has no cwd → falls back to 'b'
    assert resolve_real_cwd(project_dir) == Path("/real/path")


def test_resolve_real_cwd_returns_none_when_no_jsonl(tmp_path: Path) -> None:
    project_dir = tmp_path / "empty"
    project_dir.mkdir()
    assert resolve_real_cwd(project_dir) is None


def test_scan_projects_sorted_by_last_activity_desc(
    projects_root: Path, tmp_path: Path
) -> None:
    # project A: real path that exists
    real_a = tmp_path / "alpha"
    real_a.mkdir()
    write_session(projects_root / "-alpha", cwd=str(real_a), mtime=1000.0)
    # project B: more recent activity
    real_b = tmp_path / "beta"
    real_b.mkdir()
    write_session(projects_root / "-beta", cwd=str(real_b), mtime=3000.0)

    projects = scan_projects(projects_root)
    assert [p.name for p in projects] == ["beta", "alpha"]
    assert all(not p.is_orphan for p in projects)


def test_scan_projects_flags_orphan_when_real_path_missing(
    projects_root: Path,
) -> None:
    write_session(projects_root / "-gone", cwd="/this/path/does/not/exist/anywhere")
    projects = scan_projects(projects_root)
    assert len(projects) == 1
    assert projects[0].is_orphan is True


def test_scan_projects_ignores_dirs_with_no_jsonl(
    projects_root: Path, tmp_path: Path
) -> None:
    (projects_root / "-empty").mkdir()
    real = tmp_path / "real"
    real.mkdir()
    write_session(projects_root / "-real", cwd=str(real))
    projects = scan_projects(projects_root)
    assert [p.name for p in projects] == ["real"]


def test_scan_projects_missing_root_returns_empty(tmp_path: Path) -> None:
    assert scan_projects(tmp_path / "nope") == []


def test_scan_projects_falls_back_to_decoded_path_when_no_cwd(
    projects_root: Path,
) -> None:
    # jsonl with no cwd field anywhere → must use decode_path_fallback
    project_dir = projects_root / "-tmp-fake-encoded"
    write_session(project_dir, cwd=None)
    projects = scan_projects(projects_root)
    assert len(projects) == 1
    # decoded path is /tmp/fake/encoded — doesn't exist → orphan
    assert projects[0].path == Path("/tmp/fake/encoded")
    assert projects[0].is_orphan is True
