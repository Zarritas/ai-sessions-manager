"""Tests for multi_claude.launcher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from multi_claude.launcher import (
    LauncherError,
    _build_claude_argv,
    detect_multiplexer,
    launch_claude,
)


def test_build_argv_without_session() -> None:
    assert _build_claude_argv(None) == ["claude"]


def test_build_argv_with_session() -> None:
    assert _build_claude_argv("abc-123") == ["claude", "--resume", "abc-123"]


def test_build_argv_with_display_name() -> None:
    assert _build_claude_argv(None, "Mi feature") == ["claude", "-n", "Mi feature"]


def test_build_argv_with_session_and_display_name() -> None:
    assert _build_claude_argv("abc", "X") == ["claude", "--resume", "abc", "-n", "X"]


def test_detect_multiplexer_prefers_tmux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-x/default,123,0")
    monkeypatch.setenv("ZELLIJ", "1")
    with patch("multi_claude.launcher.shutil.which", return_value="/usr/bin/tmux"):
        assert detect_multiplexer() == "tmux"


def test_detect_multiplexer_zellij_when_no_tmux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setenv("ZELLIJ", "1")
    with patch("multi_claude.launcher.shutil.which", return_value="/usr/bin/zellij"):
        assert detect_multiplexer() == "zellij"


def test_detect_multiplexer_none_when_neither(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("ZELLIJ", raising=False)
    assert detect_multiplexer() is None


def test_detect_multiplexer_none_when_env_set_but_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TMUX", "x")
    monkeypatch.delenv("ZELLIJ", raising=False)
    with patch("multi_claude.launcher.shutil.which", return_value=None):
        assert detect_multiplexer() is None


def test_launch_claude_raises_when_no_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("multi_claude.launcher.shutil.which", return_value=None):
        with pytest.raises(LauncherError):
            launch_claude(Path("/tmp"), "id")


def test_launch_claude_uses_tmux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMUX", "x")
    monkeypatch.delenv("ZELLIJ", raising=False)

    def fake_which(cmd: str) -> str | None:
        return f"/usr/bin/{cmd}"

    calls = []

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(argv)

    with patch("multi_claude.launcher.shutil.which", side_effect=fake_which), patch(
        "multi_claude.launcher.subprocess.run", side_effect=fake_run
    ):
        launch_claude(Path("/work/x"), "sid-1")

    assert calls == [["tmux", "split-window", "-h", "-c", "/work/x", "claude", "--resume", "sid-1"]]


def test_launch_claude_uses_zellij(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setenv("ZELLIJ", "x")

    def fake_which(cmd: str) -> str | None:
        return f"/usr/bin/{cmd}"

    calls = []

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(argv)

    with patch("multi_claude.launcher.shutil.which", side_effect=fake_which), patch(
        "multi_claude.launcher.subprocess.run", side_effect=fake_run
    ):
        launch_claude(Path("/work/y"), None)

    assert calls == [["zellij", "action", "new-pane", "--cwd", "/work/y", "--", "claude"]]


def test_launch_claude_fallback_runs_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("ZELLIJ", raising=False)

    def fake_which(cmd: str) -> str | None:
        return f"/usr/bin/{cmd}"

    calls = []

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((argv, kwargs.get("cwd")))

    with patch("multi_claude.launcher.shutil.which", side_effect=fake_which), patch(
        "multi_claude.launcher.subprocess.run", side_effect=fake_run
    ):
        launch_claude(Path("/work/z"), "sid-2", app=None)

    assert calls == [(["claude", "--resume", "sid-2"], "/work/z")]
