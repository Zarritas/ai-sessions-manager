"""Tests for discovery.group_worktrees."""

from __future__ import annotations

from pathlib import Path

from ai_sessions_manager.discovery import Project, WorktreeGroup, group_worktrees


def _p(name: str, *, common: Path | None) -> Project:
    return Project(
        name=name,
        path=Path("/tmp") / name,
        encoded_path=Path("/encoded") / name,
        session_count=1,
        last_activity=0.0,
        is_orphan=False,
        git_common_dir=common,
    )


def test_group_worktrees_collapses_shared_repo(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a/.git"
    repo_b = tmp_path / "repo-b/.git"
    projects = [
        _p("alpha", common=repo_a),
        _p("alpha-wt2", common=repo_a),
        _p("beta", common=repo_b),
    ]
    rows = group_worktrees(projects)
    assert len(rows) == 2
    group = next(r for r in rows if isinstance(r, WorktreeGroup))
    assert group.repo_root == repo_a
    assert {m.name for m in group.members} == {"alpha", "alpha-wt2"}


def test_group_worktrees_passes_through_singletons(tmp_path: Path) -> None:
    repo = tmp_path / "repo/.git"
    projects = [_p("only", common=repo)]
    rows = group_worktrees(projects)
    assert len(rows) == 1
    assert isinstance(rows[0], Project)


def test_group_worktrees_keeps_non_git_projects(tmp_path: Path) -> None:
    projects = [_p("loose", common=None), _p("also-loose", common=None)]
    rows = group_worktrees(projects)
    assert all(isinstance(r, Project) for r in rows)
    assert {r.name for r in rows if isinstance(r, Project)} == {"loose", "also-loose"}
