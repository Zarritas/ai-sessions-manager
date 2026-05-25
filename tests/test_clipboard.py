"""Tests for the clipboard backend selection."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from multi_claude.clipboard import ClipboardError, copy_to_clipboard


def test_copy_uses_wl_copy_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(argv)

        class _R:
            returncode = 0
            stderr = ""

        return _R()

    with (
        patch(
            "multi_claude.clipboard.shutil.which",
            side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd == "wl-copy" else None,
        ),
        patch("multi_claude.clipboard.subprocess.run", side_effect=fake_run),
    ):
        assert copy_to_clipboard("hello") == "wl-copy"
    assert calls == [("wl-copy",)]


def test_copy_falls_back_to_xclip(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        class _R:
            returncode = 0
            stderr = ""

        return _R()

    with (
        patch(
            "multi_claude.clipboard.shutil.which",
            side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd == "xclip" else None,
        ),
        patch("multi_claude.clipboard.subprocess.run", side_effect=fake_run),
    ):
        assert copy_to_clipboard("hi") == "xclip"


def test_copy_raises_when_no_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    with patch("multi_claude.clipboard.shutil.which", return_value=None):
        with pytest.raises(ClipboardError, match="No se encontró"):
            copy_to_clipboard("x")


def test_copy_raises_when_backend_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        class _R:
            returncode = 2
            stderr = "no display"

        return _R()

    with (
        patch(
            "multi_claude.clipboard.shutil.which",
            side_effect=lambda cmd: "/usr/bin/wl-copy" if cmd == "wl-copy" else None,
        ),
        patch("multi_claude.clipboard.subprocess.run", side_effect=fake_run),
    ):
        with pytest.raises(ClipboardError, match="no display"):
            copy_to_clipboard("x")


def test_copy_handles_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    with (
        patch(
            "multi_claude.clipboard.shutil.which",
            side_effect=lambda cmd: "/usr/bin/wl-copy" if cmd == "wl-copy" else None,
        ),
        patch("multi_claude.clipboard.subprocess.run", side_effect=OSError("boom")),
    ):
        with pytest.raises(ClipboardError, match="boom"):
            copy_to_clipboard("x")


# Silence unused-import warning if subprocess gets removed by future refactors.
_ = subprocess.run
