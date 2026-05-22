"""Tests for multi_claude.deletion."""

from __future__ import annotations

import json
from pathlib import Path

from multi_claude.deletion import (
    delete_project,
    delete_session,
    list_active_sessions,
)
from multi_claude.names import NamesStore

from tests.conftest import write_session


def _make_session_artefacts(
    project_dir: Path,
    session_id: str,
    session_env_dir: Path,
    store: NamesStore,
    *,
    create_subdir: bool = True,
    create_env: bool = True,
    create_name: bool = True,
) -> dict[str, Path]:
    jsonl = write_session(project_dir, session_id=session_id, cwd=str(project_dir))
    paths = {"jsonl": jsonl}
    if create_subdir:
        subdir = project_dir / session_id
        (subdir / "subagents").mkdir(parents=True)
        (subdir / "subagents" / "x.json").write_text("{}", encoding="utf-8")
        paths["subdir"] = subdir
    if create_env:
        env_path = session_env_dir / session_id
        env_path.mkdir(parents=True)
        (env_path / "vars").write_text("FOO=bar", encoding="utf-8")
        paths["env"] = env_path
    if create_name:
        store.set(session_id, "mi nombre")
    return paths


def test_delete_session_removes_all_artefacts(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    session_env = tmp_path / "session-env"
    store = NamesStore(tmp_path / "names.json")
    paths = _make_session_artefacts(project_dir, "sid-1", session_env, store)

    delete_session("sid-1", project_dir, names_store=store, session_env_dir=session_env)

    assert not paths["jsonl"].exists()
    assert not paths["subdir"].exists()
    assert not paths["env"].exists()
    assert store.get("sid-1") is None


def test_delete_session_idempotent(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    session_env = tmp_path / "session-env"
    store = NamesStore(tmp_path / "names.json")
    # Nothing on disk → should not raise
    delete_session("ghost", project_dir, names_store=store, session_env_dir=session_env)


def test_delete_session_handles_missing_optional_artefacts(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    session_env = tmp_path / "session-env"
    store = NamesStore(tmp_path / "names.json")
    _make_session_artefacts(
        project_dir, "sid-2", session_env, store,
        create_subdir=False, create_env=False, create_name=False,
    )
    delete_session("sid-2", project_dir, names_store=store, session_env_dir=session_env)
    assert not (project_dir / "sid-2.jsonl").exists()


def test_delete_session_handles_env_as_file_not_dir(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    session_env = tmp_path / "session-env"
    session_env.mkdir()
    store = NamesStore(tmp_path / "names.json")
    write_session(project_dir, session_id="sid-3", cwd=str(project_dir))
    env_path = session_env / "sid-3"
    env_path.write_text("inline", encoding="utf-8")

    delete_session("sid-3", project_dir, names_store=store, session_env_dir=session_env)
    assert not env_path.exists()


def test_delete_project_cascades(tmp_path: Path) -> None:
    project_dir = tmp_path / "encoded"
    session_env = tmp_path / "session-env"
    store = NamesStore(tmp_path / "names.json")
    _make_session_artefacts(project_dir, "sid-a", session_env, store)
    _make_session_artefacts(project_dir, "sid-b", session_env, store)

    delete_project(project_dir, names_store=store, session_env_dir=session_env)

    assert not project_dir.exists()
    assert store.get("sid-a") is None
    assert store.get("sid-b") is None
    assert not (session_env / "sid-a").exists()
    assert not (session_env / "sid-b").exists()


def test_delete_project_missing_is_noop(tmp_path: Path) -> None:
    store = NamesStore(tmp_path / "names.json")
    delete_project(tmp_path / "nope", names_store=store, session_env_dir=tmp_path / "se")


def test_list_active_sessions_reads_session_ids(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "1.json").write_text(
        json.dumps({"pid": 1, "sessionId": "abc-123", "status": "busy"}),
        encoding="utf-8",
    )
    (sessions / "2.json").write_text(
        json.dumps({"pid": 2, "sessionId": "def-456", "status": "shell"}),
        encoding="utf-8",
    )
    assert list_active_sessions(sessions) == {"abc-123", "def-456"}


def test_list_active_sessions_ignores_garbage(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "broken.json").write_text("not json", encoding="utf-8")
    (sessions / "no-id.json").write_text(json.dumps({"pid": 3}), encoding="utf-8")
    (sessions / "ok.json").write_text(
        json.dumps({"sessionId": "x"}), encoding="utf-8"
    )
    assert list_active_sessions(sessions) == {"x"}


def test_list_active_sessions_missing_dir(tmp_path: Path) -> None:
    assert list_active_sessions(tmp_path / "nope") == set()
