"""Parse session jsonl files cheaply.

We only read the first ~50 lines of each session for the listing — enough to
extract cwd, gitBranch, version, and the first user prompt. Line count and size
come from stat and a streaming wc-equivalent (no full parse).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from multi_claude.names import NamesStore


HEADER_SCAN_LINES = 80
PROMPT_MAX_CHARS = 120


@dataclass(frozen=True)
class Session:
    id: str
    path: Path
    first_prompt: str
    branch: str | None
    cwd: str | None
    message_count: int
    size_bytes: int
    last_activity: float
    display_name: str | None


def scan_sessions(
    project_dir: Path,
    *,
    names_store: NamesStore | None = None,
) -> list[Session]:
    """Return all sessions under ``project_dir`` sorted by last_activity desc."""
    store = names_store or NamesStore()
    sessions: list[Session] = []
    for jsonl in project_dir.glob("*.jsonl"):
        try:
            session = _build_session(jsonl, store)
        except OSError:
            continue
        sessions.append(session)
    sessions.sort(key=lambda s: s.last_activity, reverse=True)
    return sessions


def _build_session(jsonl_path: Path, names_store: NamesStore) -> Session:
    stat = jsonl_path.stat()
    header = parse_session_header(jsonl_path)
    sid = jsonl_path.stem
    return Session(
        id=sid,
        path=jsonl_path,
        first_prompt=header.get("first_prompt") or "(sin prompt inicial)",
        branch=header.get("branch"),
        cwd=header.get("cwd"),
        message_count=count_lines(jsonl_path),
        size_bytes=stat.st_size,
        last_activity=stat.st_mtime,
        display_name=names_store.get(sid),
    )


def parse_session_header(jsonl_path: Path, max_lines: int = HEADER_SCAN_LINES) -> dict:
    """Read up to ``max_lines`` lines and extract first user prompt, cwd, branch, name."""
    result: dict[str, str | None] = {
        "first_prompt": None,
        "cwd": None,
        "branch": None,
        "display_name": None,
    }
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as f:
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if result["cwd"] is None and isinstance(event.get("cwd"), str):
                    result["cwd"] = event["cwd"]
                if result["branch"] is None and isinstance(event.get("gitBranch"), str):
                    result["branch"] = event["gitBranch"]
                if result["display_name"] is None and isinstance(event.get("name"), str):
                    result["display_name"] = event["name"]
                if result["first_prompt"] is None:
                    prompt = _extract_user_prompt(event)
                    if prompt:
                        result["first_prompt"] = _truncate(strip_command_wrappers(prompt))
                if all(v is not None for v in result.values()):
                    break
    except OSError:
        pass
    return result


def _extract_user_prompt(event: dict) -> str | None:
    """If this event is a user message with string content, return the content."""
    if event.get("type") != "user":
        return None
    message = event.get("message")
    if not isinstance(message, dict):
        return None
    if message.get("role") != "user":
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Some user messages come as a list of blocks; pick the first text block.
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    return text
    return None


_CMD_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
_CMD_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>.*?</[^>]+>", re.DOTALL)


def strip_command_wrappers(text: str) -> str:
    """Convert slash-command wrappers into a human-friendly summary.

    Standard form::

        <command-message>refine-task</command-message>
        <command-name>/refine-task</command-name>
        <command-args>https://...</command-args>

    becomes ``/refine-task https://...``. Plain prompts pass through with all
    inline ``<tag>...</tag>`` blocks stripped.
    """
    name_match = _CMD_NAME_RE.search(text)
    if name_match:
        name = name_match.group(1).strip()
        args_match = _CMD_ARGS_RE.search(text)
        args = args_match.group(1).strip() if args_match else ""
        return f"{name} {args}".strip()
    cleaned = _TAG_RE.sub("", text)
    return cleaned.strip()


def _truncate(text: str, limit: int = PROMPT_MAX_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def count_lines(path: Path) -> int:
    """Streaming line count, no full file in memory."""
    count = 0
    with path.open("rb") as f:
        while chunk := f.read(64 * 1024):
            count += chunk.count(b"\n")
    return count
