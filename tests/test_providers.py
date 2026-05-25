"""Tests for the provider abstraction and the Claude/Codex implementations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sessions_manager import discovery as discovery_module
from ai_sessions_manager.providers import ALL_PROVIDERS, detect_available
from ai_sessions_manager.providers.base import Provider
from ai_sessions_manager.providers.claude import ClaudeProvider
from ai_sessions_manager.providers.codex import CodexProvider


# --------------------------------------------------------------------------- #
# Protocol conformance                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("provider_cls", [ClaudeProvider, CodexProvider])
def test_provider_satisfies_protocol(provider_cls: type) -> None:
    """Every shipped provider implementation must satisfy the runtime Protocol."""
    instance = provider_cls()
    assert isinstance(instance, Provider)


def test_all_providers_registry_contains_claude_and_codex() -> None:
    ids = {p.id for p in ALL_PROVIDERS}
    assert {"claude", "codex"} <= ids


# --------------------------------------------------------------------------- #
# ClaudeProvider argv                                                          #
# --------------------------------------------------------------------------- #


def test_claude_resume_argv_no_name() -> None:
    p = ClaudeProvider()
    assert p.resume_argv("abc-123") == ["claude", "--resume", "abc-123"]


def test_claude_resume_argv_with_name() -> None:
    p = ClaudeProvider()
    assert p.resume_argv("abc-123", "my feature") == [
        "claude",
        "--resume",
        "abc-123",
        "-n",
        "my feature",
    ]


def test_claude_new_argv_with_name() -> None:
    p = ClaudeProvider()
    assert p.new_argv("hello") == ["claude", "-n", "hello"]


# --------------------------------------------------------------------------- #
# CodexProvider argv                                                           #
# --------------------------------------------------------------------------- #


def test_codex_resume_argv() -> None:
    p = CodexProvider()
    assert p.resume_argv("019c81f3-aae1-79c2") == ["codex", "resume", "019c81f3-aae1-79c2"]


def test_codex_resume_argv_ignores_display_name() -> None:
    """Codex has no -n equivalent; display_name is silently dropped."""
    p = CodexProvider()
    assert p.resume_argv("sid", "should-be-ignored") == ["codex", "resume", "sid"]


def test_codex_new_argv() -> None:
    p = CodexProvider()
    assert p.new_argv() == ["codex"]


# --------------------------------------------------------------------------- #
# CodexProvider scan against a synthetic ~/.codex tree                         #
# --------------------------------------------------------------------------- #


def _write_codex_rollout(
    sessions_root: Path,
    *,
    date_subdir: str,
    session_id: str,
    cwd: str,
    branch: str | None = "main",
    first_user_text: str = "real first prompt",
    boilerplate_lines: int = 3,
) -> Path:
    """Build a JSONL that mimics the real Codex rollout shape.

    The synthetic session injects ``boilerplate_lines`` Codex-style preamble
    messages (each wrapped in ``<...>``) before the real user prompt, so we can
    assert the boilerplate-skipping heuristic.
    """
    day_dir = sessions_root / date_subdir
    day_dir.mkdir(parents=True, exist_ok=True)
    rollout = day_dir / f"rollout-2026-02-21T20-45-55-{session_id}.jsonl"

    events: list[dict] = []
    meta_payload: dict = {
        "id": session_id,
        "timestamp": "2026-02-21T20:45:55.809Z",
        "cwd": cwd,
        "originator": "codex_cli_rs",
        "cli_version": "0.104.0",
    }
    if branch is not None:
        meta_payload["git"] = {"branch": branch, "commit_hash": "abc123"}
    events.append({"timestamp": "2026-02-21T20:47:15.388Z", "type": "session_meta", "payload": meta_payload})

    # Injected boilerplate (matches what real Codex emits): wrapped in <…>.
    for i in range(boilerplate_lines):
        events.append(
            {
                "timestamp": "2026-02-21T20:47:15.388Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": f"<boilerplate-{i}>injected</boilerplate-{i}>"}],
                },
            }
        )

    # The real first user prompt (no <…> wrapper).
    events.append(
        {
            "timestamp": "2026-02-21T20:47:15.388Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": first_user_text}],
            },
        }
    )

    with rollout.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    return rollout


def test_codex_scan_groups_rollouts_by_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Two rollouts in the same cwd collapse into one project with session_count=2."""
    root = tmp_path / ".codex" / "sessions"
    _write_codex_rollout(root, date_subdir="2026/02/21", session_id="aaaa-aaaa", cwd=str(tmp_path / "proj-a"))
    _write_codex_rollout(root, date_subdir="2026/02/22", session_id="bbbb-bbbb", cwd=str(tmp_path / "proj-a"))
    _write_codex_rollout(root, date_subdir="2026/02/22", session_id="cccc-cccc", cwd=str(tmp_path / "proj-b"))

    monkeypatch.setattr("ai_sessions_manager.providers.codex.CODEX_SESSIONS_DIR", root)

    p = CodexProvider()
    projects = p.scan_projects()
    by_path = {str(proj.path): proj for proj in projects}
    assert len(projects) == 2
    assert by_path[str(tmp_path / "proj-a")].session_count == 2
    assert by_path[str(tmp_path / "proj-b")].session_count == 1


def test_codex_scan_marks_orphan_when_cwd_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / ".codex" / "sessions"
    _write_codex_rollout(root, date_subdir="2026/02/21", session_id="orph", cwd=str(tmp_path / "does-not-exist"))

    monkeypatch.setattr("ai_sessions_manager.providers.codex.CODEX_SESSIONS_DIR", root)

    [proj] = CodexProvider().scan_projects()
    assert proj.is_orphan is True


def test_codex_scan_returns_empty_when_root_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "ai_sessions_manager.providers.codex.CODEX_SESSIONS_DIR", tmp_path / "nope"
    )
    assert CodexProvider().scan_projects() == []


def test_codex_session_first_prompt_skips_boilerplate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The injected ``<boilerplate-…>`` messages must not become the displayed prompt."""
    root = tmp_path / ".codex" / "sessions"
    cwd = tmp_path / "proj"
    cwd.mkdir()
    _write_codex_rollout(
        root,
        date_subdir="2026/02/21",
        session_id="sid-1",
        cwd=str(cwd),
        first_user_text="implement the login flow",
        boilerplate_lines=4,
    )

    monkeypatch.setattr("ai_sessions_manager.providers.codex.CODEX_SESSIONS_DIR", root)

    provider = CodexProvider()
    [project] = provider.scan_projects()
    [session] = provider.scan_sessions(project)
    assert session.first_prompt == "implement the login flow"
    assert session.branch == "main"
    assert session.id == "sid-1"


def test_codex_session_falls_back_when_no_real_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If every user message is boilerplate, surface the default placeholder string."""
    root = tmp_path / ".codex" / "sessions"
    cwd = tmp_path / "p"
    cwd.mkdir()
    # All messages are boilerplate (start with `<`). first_prompt should fall back.
    _write_codex_rollout(
        root,
        date_subdir="2026/02/21",
        session_id="sid-x",
        cwd=str(cwd),
        first_user_text="<also-boilerplate>still wrapped</also-boilerplate>",
        boilerplate_lines=2,
    )

    monkeypatch.setattr("ai_sessions_manager.providers.codex.CODEX_SESSIONS_DIR", root)

    provider = CodexProvider()
    [project] = provider.scan_projects()
    [session] = provider.scan_sessions(project)
    assert session.first_prompt == "(sin prompt inicial)"


def test_codex_session_handles_missing_git_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A session_meta without a git block returns branch=None, not a crash."""
    root = tmp_path / ".codex" / "sessions"
    cwd = tmp_path / "no-git"
    cwd.mkdir()
    _write_codex_rollout(
        root,
        date_subdir="2026/02/21",
        session_id="sid-nogit",
        cwd=str(cwd),
        branch=None,
    )

    monkeypatch.setattr("ai_sessions_manager.providers.codex.CODEX_SESSIONS_DIR", root)

    provider = CodexProvider()
    [project] = provider.scan_projects()
    [session] = provider.scan_sessions(project)
    assert session.branch is None


# --------------------------------------------------------------------------- #
# detect_available                                                             #
# --------------------------------------------------------------------------- #


def test_detect_available_filters_to_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only providers whose binary resolves via shutil.which are returned."""
    # Both providers import the same `shutil` module, so we can only patch
    # `shutil.which` once and dispatch on the requested binary name.
    import shutil as real_shutil

    def fake_which(binary: str) -> str | None:
        # Pretend only `codex` is installed.
        return f"/fake/{binary}" if binary == "codex" else None

    monkeypatch.setattr(real_shutil, "which", fake_which)

    available = detect_available()
    ids = {p.id for p in available}
    assert ids == {"codex"}


# --------------------------------------------------------------------------- #
# ClaudeProvider delegates to the existing discovery module                    #
# --------------------------------------------------------------------------- #


def test_claude_scan_projects_delegates_to_discovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ClaudeProvider just forwards to the legacy ``scan_projects`` function."""
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    # Make an empty Claude tree so discovery.scan_projects returns [].
    monkeypatch.setattr(discovery_module, "CLAUDE_PROJECTS_DIR", projects_root)
    assert ClaudeProvider().scan_projects() == []
