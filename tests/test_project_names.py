"""Tests for ProjectNamesStore (worktree / project aliases)."""

from __future__ import annotations

from pathlib import Path

from multi_claude.project_names import ProjectNamesStore, project_key, repo_key


def test_set_and_get_project_alias(tmp_path: Path) -> None:
    store = ProjectNamesStore(tmp_path / "names.json")
    encoded = tmp_path / "encoded-a"
    store.set_for_project(encoded, "Cliente A")
    assert store.for_project(encoded) == "Cliente A"


def test_set_and_get_repo_alias(tmp_path: Path) -> None:
    store = ProjectNamesStore(tmp_path / "names.json")
    repo = tmp_path / "repo/.git"
    store.set_for_repo(repo, "Gextia ERP")
    assert store.for_repo(repo) == "Gextia ERP"


def test_project_and_repo_namespaces_dont_collide(tmp_path: Path) -> None:
    store = ProjectNamesStore(tmp_path / "names.json")
    shared = tmp_path / "shared"
    store.set_for_project(shared, "as-project")
    store.set_for_repo(shared, "as-repo")
    assert store.for_project(shared) == "as-project"
    assert store.for_repo(shared) == "as-repo"


def test_delete_removes_alias(tmp_path: Path) -> None:
    store = ProjectNamesStore(tmp_path / "names.json")
    encoded = tmp_path / "encoded-a"
    store.set_for_project(encoded, "x")
    store.delete_for_project(encoded)
    assert store.for_project(encoded) is None


def test_rename_key_transfers_alias(tmp_path: Path) -> None:
    store = ProjectNamesStore(tmp_path / "names.json")
    old = tmp_path / "old"
    new = tmp_path / "new"
    store.set_for_project(old, "Mi proyecto")
    store.rename_key(project_key(old), project_key(new))
    assert store.for_project(old) is None
    assert store.for_project(new) == "Mi proyecto"


def test_rename_key_noop_when_old_missing(tmp_path: Path) -> None:
    store = ProjectNamesStore(tmp_path / "names.json")
    new = tmp_path / "new"
    store.set_for_project(new, "kept")
    store.rename_key(project_key(tmp_path / "absent"), project_key(new))
    # Existing alias is untouched
    assert store.for_project(new) == "kept"


def test_load_handles_missing_file(tmp_path: Path) -> None:
    store = ProjectNamesStore(tmp_path / "absent.json")
    assert store.for_project(tmp_path / "anything") is None


def test_load_handles_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.json"
    path.write_text("not json", encoding="utf-8")
    store = ProjectNamesStore(path)
    assert store.all() == {}


def test_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "names.json"
    store_a = ProjectNamesStore(path)
    repo = tmp_path / "r"
    store_a.set_for_repo(repo, "alias")

    store_b = ProjectNamesStore(path)
    assert store_b.for_repo(repo) == "alias"


def test_key_helpers_are_consistent(tmp_path: Path) -> None:
    p = tmp_path / "x"
    assert project_key(p) == f"project:{p}"
    assert repo_key(p) == f"repo:{p}"
