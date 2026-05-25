"""OpenAI Codex CLI provider.

Codex stores each interactive session as a JSONL rollout under::

    ~/.codex/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl

The first line is always a ``session_meta`` event whose payload carries the
session ``id`` (UUID), ``cwd``, ``timestamp``, ``cli_version`` and optionally
a ``git`` block with ``branch``. We group rollouts by ``cwd`` to form
"projects" — the same UX shape as Claude Code, but the grouping happens at
read time instead of being baked into the directory layout.

Subsequent lines are ``response_item`` events; the first user prompt sits in
the first ``role=user`` message whose content isn't injected boilerplate
(permissions instructions, AGENTS.md preamble, environment context). We skip
the boilerplate heuristically by looking for text that starts with ``<`` or
``# AGENTS.md`` — both signatures of Codex-injected wrappers, not real input.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

from multi_claude.discovery import Project
from multi_claude.session import Session

CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"

# Heuristic limit when scanning a rollout for its first real user prompt.
# Codex injects ~5-10 setup messages at the top; 80 lines is plenty.
_PROMPT_SCAN_LINES = 80
_PROMPT_MAX_CHARS = 120


class CodexProvider:
    """:class:`multi_claude.providers.base.Provider` implementation for Codex CLI."""

    id = "codex"
    display_name = "OpenAI Codex"
    binary = "codex"

    def is_installed(self) -> bool:
        return shutil.which(self.binary) is not None

    def sessions_root(self) -> Path:
        return CODEX_SESSIONS_DIR

    def scan_projects(self) -> list[Project]:
        """Group rollout files by their ``session_meta.cwd`` field.

        Returns one :class:`Project` per distinct cwd, ordered by the mtime of
        the most recent rollout in each group (newest first).
        """
        root = self.sessions_root()
        if not root.is_dir():
            return []

        # cwd-str → list of (rollout_path, mtime). Building both at once keeps
        # the I/O cost to "one stat + first line read" per rollout file.
        by_cwd: dict[str, list[tuple[Path, float]]] = defaultdict(list)
        for rollout in root.rglob("rollout-*.jsonl"):
            meta = _read_session_meta(rollout)
            cwd = meta.get("cwd") if meta else None
            if not isinstance(cwd, str) or not cwd:
                continue
            try:
                mtime = rollout.stat().st_mtime
            except OSError:
                continue
            by_cwd[cwd].append((rollout, mtime))

        projects: list[Project] = []
        for cwd_str, entries in by_cwd.items():
            cwd_path = Path(cwd_str)
            last_activity = max(m for _, m in entries)
            is_orphan = not cwd_path.is_dir()
            name = cwd_path.name or cwd_str
            projects.append(
                Project(
                    name=name,
                    path=cwd_path,
                    # Codex has no per-project directory; use the cwd itself as
                    # the stable identity. ProjectsScreen never opens this path
                    # directly, it only uses it as a dict key.
                    encoded_path=cwd_path,
                    session_count=len(entries),
                    last_activity=last_activity,
                    is_orphan=is_orphan,
                    git_common_dir=None,
                )
            )
        projects.sort(key=lambda p: p.last_activity, reverse=True)
        return projects

    def scan_sessions(self, project: Project) -> list[Session]:
        """Return every rollout whose ``session_meta.cwd`` matches ``project.path``.

        Walks the same tree as :meth:`scan_projects` but filters by cwd. For
        repos with many sessions this re-reads the first line of every rollout
        — acceptable for now; the SQLite index can cache this later.
        """
        root = self.sessions_root()
        if not root.is_dir():
            return []

        target = str(project.path)
        sessions: list[Session] = []
        for rollout in root.rglob("rollout-*.jsonl"):
            meta = _read_session_meta(rollout)
            if not meta or meta.get("cwd") != target:
                continue
            sessions.append(_build_session(rollout, meta))
        sessions.sort(key=lambda s: s.last_activity, reverse=True)
        return sessions

    def resume_argv(self, session_id: str, display_name: str | None = None) -> list[str]:
        # Codex uses `codex resume <id>` (subcommand) — not `--resume`.
        # `display_name` is ignored: Codex has no equivalent of Claude's `-n` flag.
        del display_name
        return ["codex", "resume", session_id]

    def new_argv(self, display_name: str | None = None) -> list[str]:
        del display_name
        return ["codex"]


def _read_session_meta(rollout: Path) -> dict | None:
    """Return the parsed payload of the first ``session_meta`` event, or None.

    Codex always emits ``session_meta`` as the first line, but we read up to
    four lines to be tolerant of future format changes (e.g. a leading
    metadata header above the session_meta).
    """
    try:
        with rollout.open("r", encoding="utf-8", errors="replace") as f:
            for _ in range(4):
                line = f.readline()
                if not line:
                    return None
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "session_meta":
                    payload = event.get("payload")
                    if isinstance(payload, dict):
                        return payload
    except OSError:
        return None
    return None


def _build_session(rollout: Path, meta: dict) -> Session:
    """Construct a :class:`Session` from a rollout's metadata and a header scan."""
    try:
        stat = rollout.stat()
    except OSError:
        # Stat failure — fall back to zeros so the row still renders.
        size_bytes = 0
        last_activity = 0.0
    else:
        size_bytes = stat.st_size
        last_activity = stat.st_mtime

    git = meta.get("git") if isinstance(meta.get("git"), dict) else None
    branch = git.get("branch") if git else None

    first_prompt = _scan_first_user_prompt(rollout) or "(sin prompt inicial)"

    return Session(
        id=str(meta.get("id") or rollout.stem),
        path=rollout,
        first_prompt=first_prompt,
        branch=branch if isinstance(branch, str) else None,
        cwd=meta.get("cwd") if isinstance(meta.get("cwd"), str) else None,
        # Codex doesn't expose a cheap message count and counting JSONL lines
        # for every row would be expensive at scan time. Surface "-" via 0;
        # the UI shows a dash for zero. The SQLite index can populate this later.
        message_count=0,
        size_bytes=size_bytes,
        last_activity=last_activity,
        display_name=None,
    )


def _scan_first_user_prompt(rollout: Path) -> str | None:
    """Walk the rollout until we find a user message that isn't injected boilerplate.

    Codex prepends 3-5 ``role=user`` messages to every session for permissions,
    AGENTS.md and environment context. They all start with ``<`` or
    ``# AGENTS.md``; the first user message that doesn't is the real prompt.
    """
    try:
        with rollout.open("r", encoding="utf-8", errors="replace") as f:
            for _ in range(_PROMPT_SCAN_LINES):
                line = f.readline()
                if not line:
                    return None
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = _extract_user_text(event)
                if text and not _looks_like_boilerplate(text):
                    return _truncate(text)
    except OSError:
        return None
    return None


def _extract_user_text(event: dict) -> str | None:
    """Pull the ``input_text`` of a ``role=user`` message event, if that's what it is."""
    if event.get("type") != "response_item":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "message" or payload.get("role") != "user":
        return None
    content = payload.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "input_text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                return text
    return None


def _looks_like_boilerplate(text: str) -> bool:
    """Detect Codex-injected wrapper messages we should skip past."""
    stripped = text.lstrip()
    return stripped.startswith("<") or stripped.startswith("# AGENTS.md")


def _truncate(text: str, limit: int = _PROMPT_MAX_CHARS) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"
