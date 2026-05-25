"""Tests for the provider abstraction and the Claude/Codex/Goose/opencode implementations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ai_sessions_manager import discovery as discovery_module
from ai_sessions_manager.providers import ALL_PROVIDERS, detect_available
from ai_sessions_manager.providers.base import Provider
from ai_sessions_manager.providers.claude import ClaudeProvider
from ai_sessions_manager.providers.codex import CodexProvider
from ai_sessions_manager.providers.goose import GooseProvider
from ai_sessions_manager.providers.opencode import OpenCodeProvider


# --------------------------------------------------------------------------- #
# Protocol conformance                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "provider_cls", [ClaudeProvider, CodexProvider, GooseProvider, OpenCodeProvider]
)
def test_provider_satisfies_protocol(provider_cls: type) -> None:
    """Every shipped provider implementation must satisfy the runtime Protocol."""
    instance = provider_cls()
    assert isinstance(instance, Provider)


def test_all_providers_registry_contains_every_shipped_provider() -> None:
    ids = {p.id for p in ALL_PROVIDERS}
    assert {"claude", "codex", "goose", "opencode"} <= ids


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


# --------------------------------------------------------------------------- #
# GooseProvider                                                                #
# --------------------------------------------------------------------------- #


def _build_goose_db(db_path: Path) -> sqlite3.Connection:
    """Create a SQLite db matching the Goose ``sessions``/``messages`` schema.

    We only define the columns the provider actually reads (plus ``archived_at``
    for the filter). Goose's real schema has many more columns but they're
    irrelevant here.
    """
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            working_dir TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            archived_at TIMESTAMP
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id),
            role TEXT NOT NULL,
            content_json TEXT NOT NULL,
            created_timestamp INTEGER NOT NULL
        );
        """
    )
    return conn


def test_goose_resume_argv_uses_id_subcommand() -> None:
    assert GooseProvider().resume_argv("20260225_120000") == [
        "goose",
        "session",
        "--resume",
        "--id",
        "20260225_120000",
    ]


def test_goose_new_argv_with_name() -> None:
    assert GooseProvider().new_argv("my-session") == ["goose", "session", "--name", "my-session"]


def test_goose_scan_returns_empty_when_db_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No sessions.db on disk → 0 projects, no exception."""
    monkeypatch.setattr(
        "ai_sessions_manager.providers.goose.GOOSE_SESSIONS_DB", tmp_path / "nope.db"
    )
    assert GooseProvider().scan_projects() == []


def test_goose_groups_sessions_by_working_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "sessions.db"
    conn = _build_goose_db(db)
    conn.execute(
        "INSERT INTO sessions (id, working_dir, updated_at) VALUES (?, ?, ?)",
        ("20260225_1", str(tmp_path / "proj-a"), "2026-02-25 12:00:00"),
    )
    conn.execute(
        "INSERT INTO sessions (id, working_dir, updated_at) VALUES (?, ?, ?)",
        ("20260225_2", str(tmp_path / "proj-a"), "2026-02-25 13:00:00"),
    )
    conn.execute(
        "INSERT INTO sessions (id, working_dir, updated_at) VALUES (?, ?, ?)",
        ("20260224_1", str(tmp_path / "proj-b"), "2026-02-24 10:00:00"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("ai_sessions_manager.providers.goose.GOOSE_SESSIONS_DB", db)

    projects = GooseProvider().scan_projects()
    by_name = {p.name: p for p in projects}
    assert len(projects) == 2
    assert by_name["proj-a"].session_count == 2
    assert by_name["proj-b"].session_count == 1
    # Newest first: proj-a's latest is 13:00 vs proj-b's 10:00.
    assert projects[0].name == "proj-a"


def test_goose_skips_archived_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sessions with ``archived_at IS NOT NULL`` must not appear."""
    db = tmp_path / "sessions.db"
    conn = _build_goose_db(db)
    conn.execute(
        "INSERT INTO sessions (id, working_dir, updated_at, archived_at) VALUES (?, ?, ?, ?)",
        ("archived", str(tmp_path / "p"), "2026-02-25 12:00:00", "2026-02-26 09:00:00"),
    )
    conn.execute(
        "INSERT INTO sessions (id, working_dir, updated_at) VALUES (?, ?, ?)",
        ("live", str(tmp_path / "p"), "2026-02-25 13:00:00"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("ai_sessions_manager.providers.goose.GOOSE_SESSIONS_DB", db)

    [project] = GooseProvider().scan_projects()
    assert project.session_count == 1


def test_goose_extracts_first_prompt_from_content_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "sessions.db"
    cwd = tmp_path / "proj"
    cwd.mkdir()
    conn = _build_goose_db(db)
    conn.execute(
        "INSERT INTO sessions (id, name, working_dir, updated_at) VALUES (?, ?, ?, ?)",
        ("20260225_1", "Login flow", str(cwd), "2026-02-25 12:00:00"),
    )
    # Goose serialises message content as a JSON object with a `content` list
    # of {"type": "text", "text": "..."} blocks.
    content = json.dumps(
        {"content": [{"type": "text", "text": "implement the login flow with OAuth"}]}
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content_json, created_timestamp) "
        "VALUES (?, 'user', ?, 1740484800)",
        ("20260225_1", content),
    )
    # Earlier-recorded assistant message that must NOT be picked as the prompt.
    conn.execute(
        "INSERT INTO messages (session_id, role, content_json, created_timestamp) "
        "VALUES (?, 'assistant', ?, 1740484700)",
        ("20260225_1", json.dumps({"content": [{"type": "text", "text": "an assistant reply"}]})),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("ai_sessions_manager.providers.goose.GOOSE_SESSIONS_DB", db)

    provider = GooseProvider()
    [project] = provider.scan_projects()
    [session] = provider.scan_sessions(project)
    assert session.first_prompt == "implement the login flow with OAuth"
    assert session.display_name == "Login flow"
    assert session.id == "20260225_1"
    assert session.message_count == 2  # both user + assistant counted


def test_goose_falls_back_when_content_unparseable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Bad JSON in content_json → fallback prompt, no crash."""
    db = tmp_path / "sessions.db"
    conn = _build_goose_db(db)
    conn.execute(
        "INSERT INTO sessions (id, working_dir, updated_at) VALUES (?, ?, ?)",
        ("s1", str(tmp_path / "p"), "2026-02-25 12:00:00"),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content_json, created_timestamp) "
        "VALUES (?, 'user', ?, 1740484800)",
        ("s1", "not json"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("ai_sessions_manager.providers.goose.GOOSE_SESSIONS_DB", db)

    provider = GooseProvider()
    [project] = provider.scan_projects()
    [session] = provider.scan_sessions(project)
    assert session.first_prompt == "(sin prompt inicial)"


# --------------------------------------------------------------------------- #
# OpenCodeProvider                                                             #
# --------------------------------------------------------------------------- #


def _build_opencode_db(db_path: Path) -> sqlite3.Connection:
    """Create a SQLite db matching the (real) opencode singular-table schema."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            parent_id TEXT,
            directory TEXT NOT NULL,
            title TEXT,
            time_created INTEGER,
            time_updated INTEGER,
            time_archived INTEGER
        );
        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            data TEXT NOT NULL,
            time_created INTEGER,
            time_updated INTEGER
        );
        CREATE TABLE part (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            data TEXT NOT NULL,
            time_created INTEGER,
            time_updated INTEGER
        );
        """
    )
    return conn


def test_opencode_resume_argv() -> None:
    assert OpenCodeProvider().resume_argv("ses_abc123") == ["opencode", "run", "-s", "ses_abc123"]


def test_opencode_new_argv() -> None:
    assert OpenCodeProvider().new_argv() == ["opencode"]


def test_opencode_scan_returns_empty_when_db_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "ai_sessions_manager.providers.opencode.OPENCODE_DB", tmp_path / "missing.db"
    )
    assert OpenCodeProvider().scan_projects() == []


def test_opencode_skips_forks_and_archived(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Forks (parent_id IS NOT NULL) and archived sessions must not surface as projects."""
    db = tmp_path / "opencode.db"
    cwd = str(tmp_path / "proj")
    (tmp_path / "proj").mkdir()
    conn = _build_opencode_db(db)
    conn.executemany(
        "INSERT INTO session (id, parent_id, directory, time_updated, time_archived) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("ses_root", None, cwd, 1_700_000_000_000, None),
            ("ses_fork", "ses_root", cwd, 1_700_000_001_000, None),
            ("ses_archived", None, cwd, 1_700_000_002_000, 1_700_000_999_000),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("ai_sessions_manager.providers.opencode.OPENCODE_DB", db)

    [project] = OpenCodeProvider().scan_projects()
    assert project.session_count == 1  # only ses_root


def test_opencode_canonicalises_mixed_slash_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """opencode stores cwds inconsistently; same dir with different separators collapses."""
    db = tmp_path / "opencode.db"
    proj = tmp_path / "proj"
    proj.mkdir()
    # Same logical directory written two ways — should still collapse to one project.
    posix_form = proj.as_posix()
    windows_form = str(proj)
    conn = _build_opencode_db(db)
    conn.executemany(
        "INSERT INTO session (id, parent_id, directory, time_updated) VALUES (?, NULL, ?, ?)",
        [
            ("ses_a", posix_form, 1_700_000_000_000),
            ("ses_b", windows_form, 1_700_000_500_000),
        ],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("ai_sessions_manager.providers.opencode.OPENCODE_DB", db)

    projects = OpenCodeProvider().scan_projects()
    assert len(projects) == 1
    assert projects[0].session_count == 2


def test_opencode_extracts_first_prompt_from_part_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The displayed prompt comes from a part.data {type:text,text:...} blob."""
    db = tmp_path / "opencode.db"
    cwd = tmp_path / "proj"
    cwd.mkdir()
    conn = _build_opencode_db(db)
    conn.execute(
        "INSERT INTO session (id, parent_id, directory, title, time_updated) "
        "VALUES (?, NULL, ?, ?, ?)",
        ("ses_1", str(cwd), "Login planning", 1_700_000_000_000),
    )
    conn.execute(
        "INSERT INTO message (id, session_id, data, time_created) VALUES (?, ?, ?, ?)",
        ("msg_1", "ses_1", json.dumps({"role": "user", "time": {"created": 1_700_000_000_000}}), 1_700_000_000_000),
    )
    # Two text parts on the same message — earliest wins.
    conn.execute(
        "INSERT INTO part (id, message_id, session_id, data, time_created) VALUES (?, ?, ?, ?, ?)",
        ("prt_1", "msg_1", "ses_1", json.dumps({"type": "text", "text": "design the login screen"}), 1),
    )
    conn.execute(
        "INSERT INTO part (id, message_id, session_id, data, time_created) VALUES (?, ?, ?, ?, ?)",
        ("prt_2", "msg_1", "ses_1", json.dumps({"type": "text", "text": "also do logout"}), 2),
    )
    # Tool-use part: must NOT be picked (filter selects only type='text').
    conn.execute(
        "INSERT INTO part (id, message_id, session_id, data, time_created) VALUES (?, ?, ?, ?, ?)",
        ("prt_3", "msg_1", "ses_1", json.dumps({"type": "tool_use", "id": "x"}), 0),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("ai_sessions_manager.providers.opencode.OPENCODE_DB", db)

    provider = OpenCodeProvider()
    [project] = provider.scan_projects()
    [session] = provider.scan_sessions(project)
    assert session.first_prompt == "design the login screen"
    assert session.display_name == "Login planning"
    assert session.id == "ses_1"


def test_opencode_timestamp_converted_from_milliseconds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``time_updated`` is epoch ms; the Provider must surface seconds-float."""
    db = tmp_path / "opencode.db"
    conn = _build_opencode_db(db)
    conn.execute(
        "INSERT INTO session (id, parent_id, directory, time_updated) VALUES (?, NULL, ?, ?)",
        ("ses_1", str(tmp_path / "p"), 1_700_000_123_456),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("ai_sessions_manager.providers.opencode.OPENCODE_DB", db)

    [project] = OpenCodeProvider().scan_projects()
    # 1_700_000_123_456 ms → 1_700_000_123.456 s
    assert project.last_activity == pytest.approx(1_700_000_123.456)
