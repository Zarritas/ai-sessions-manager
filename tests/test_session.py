"""Tests for ai_sessions_manager.session."""

from __future__ import annotations

from pathlib import Path

from ai_sessions_manager.names import NamesStore
from ai_sessions_manager.session import (
    count_lines,
    parse_session_header,
    scan_sessions,
    strip_command_wrappers,
)
from tests.conftest import write_session


def test_strip_command_wrappers_extracts_slash_command_and_args() -> None:
    text = (
        "<command-message>refine-task</command-message>\n"
        "<command-name>/refine-task</command-name>\n"
        "<command-args>https://example.com/issue/1</command-args>"
    )
    assert strip_command_wrappers(text) == "/refine-task https://example.com/issue/1"


def test_strip_command_wrappers_with_no_args() -> None:
    text = (
        "<command-message>status</command-message>\n"
        "<command-name>/status</command-name>\n"
        "<command-args></command-args>"
    )
    assert strip_command_wrappers(text) == "/status"


def test_strip_command_wrappers_plain_text_passes_through() -> None:
    assert strip_command_wrappers("just a regular prompt") == "just a regular prompt"


def test_strip_command_wrappers_strips_system_reminder() -> None:
    text = "real prompt <system-reminder>noise</system-reminder>"
    assert strip_command_wrappers(text) == "real prompt"


def test_parse_session_header_extracts_cwd_branch_first_prompt(tmp_path: Path) -> None:
    jsonl = write_session(
        tmp_path,
        cwd="/home/user/project",
        branch="feature/x",
        first_prompt="<command-name>/foo</command-name><command-args>bar</command-args>",
    )
    header = parse_session_header(jsonl)
    assert header["cwd"] == "/home/user/project"
    assert header["branch"] == "feature/x"
    assert header["first_prompt"] == "/foo bar"


def test_parse_session_header_handles_malformed_lines(tmp_path: Path) -> None:
    jsonl = tmp_path / "broken.jsonl"
    jsonl.write_text(
        'this is not json\n{"type":"user","message":{"role":"user","content":"hi"},"cwd":"/x"}\n',
        encoding="utf-8",
    )
    header = parse_session_header(jsonl)
    assert header["cwd"] == "/x"
    assert header["first_prompt"] == "hi"


def test_count_lines_matches_actual(tmp_path: Path) -> None:
    f = tmp_path / "x.jsonl"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    assert count_lines(f) == 3


def test_count_lines_no_trailing_newline(tmp_path: Path) -> None:
    f = tmp_path / "x.jsonl"
    f.write_text("a\nb", encoding="utf-8")
    assert count_lines(f) == 1


def test_scan_sessions_sorted_by_mtime_desc(tmp_path: Path) -> None:
    write_session(tmp_path, session_id="old", mtime=1000.0)
    write_session(tmp_path, session_id="new", mtime=2000.0)
    write_session(tmp_path, session_id="mid", mtime=1500.0)
    sessions = scan_sessions(tmp_path)
    assert [s.id for s in sessions] == ["new", "mid", "old"]


def test_scan_sessions_empty_dir(tmp_path: Path) -> None:
    assert scan_sessions(tmp_path) == []


def test_scan_sessions_populates_display_name_from_store(tmp_path: Path) -> None:
    write_session(tmp_path, session_id="sid-named")
    write_session(tmp_path, session_id="sid-anon")
    store = NamesStore(tmp_path / "names.json")
    store.set("sid-named", "Mi feature")

    sessions = {s.id: s for s in scan_sessions(tmp_path, names_store=store)}
    assert sessions["sid-named"].display_name == "Mi feature"
    assert sessions["sid-anon"].display_name is None
