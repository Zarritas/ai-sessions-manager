"""Session preview widget — renders the last N turns of a session jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from multi_claude.session import strip_command_wrappers

PREVIEW_LAST_LINES = 60
PREVIEW_TURN_LIMIT = 12
PREVIEW_TEXT_LIMIT = 800


class SessionPreview(Widget):
    """Read-only panel that renders the last few turns of a session."""

    DEFAULT_CSS = """
    SessionPreview {
        border: round $primary;
        padding: 0 1;
        background: $boost;
        height: 1fr;
        width: 1fr;
    }
    SessionPreview > VerticalScroll {
        height: 1fr;
    }
    SessionPreview .turn-user {
        color: $accent;
        text-style: bold;
    }
    SessionPreview .turn-assistant {
        color: $text;
    }
    SessionPreview .placeholder {
        color: $text-muted;
        text-style: italic;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="preview-scroll"):
            yield Static("Selecciona una sesión.", id="preview-body", classes="placeholder")

    def clear(self, placeholder: str = "Selecciona una sesión.") -> None:
        body = self.query_one("#preview-body", Static)
        body.remove_class("turn-user")
        body.remove_class("turn-assistant")
        body.add_class("placeholder")
        body.update(placeholder)

    def show_session(self, jsonl_path: Path | None) -> None:
        body = self.query_one("#preview-body", Static)
        if jsonl_path is None or not jsonl_path.exists():
            self.clear("No hay preview disponible.")
            return
        try:
            turns = _read_last_turns(jsonl_path)
        except OSError as exc:
            self.clear(f"Error leyendo {jsonl_path.name}: {exc}")
            return
        if not turns:
            self.clear("Sin turnos de texto en esta sesión.")
            return
        rendered = "\n\n".join(_format_turn(role, text) for role, text in turns)
        body.remove_class("placeholder")
        body.update(rendered)


def _read_last_turns(jsonl_path: Path) -> list[tuple[str, str]]:
    """Return ``[(role, text), ...]`` for the last few user/assistant turns."""
    with jsonl_path.open("rb") as f:
        lines = _tail_lines(f, PREVIEW_LAST_LINES)
    turns: list[tuple[str, str]] = []
    for raw in lines:
        try:
            event = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        role_and_text = _extract_role_and_text(event)
        if role_and_text is None:
            continue
        role, text = role_and_text
        text = strip_command_wrappers(text).strip()
        if not text:
            continue
        if len(text) > PREVIEW_TEXT_LIMIT:
            text = text[:PREVIEW_TEXT_LIMIT].rstrip() + "…"
        turns.append((role, text))
    return turns[-PREVIEW_TURN_LIMIT:]


def _tail_lines(file_obj: object, count: int) -> list[bytes]:
    """Cheap tail: read the whole file then slice the last ``count`` lines."""
    data = file_obj.read()  # type: ignore[attr-defined]
    if not isinstance(data, bytes) or not data:
        return []
    raw_lines = data.splitlines()
    return raw_lines[-count:]


def _extract_role_and_text(event: dict[str, object]) -> tuple[str, str] | None:
    etype = event.get("type")
    if etype not in ("user", "assistant"):
        return None
    message = event.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    role = "user" if etype == "user" else "assistant"
    if isinstance(content, str):
        return (role, content)
    if isinstance(content, list):
        chunks: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    chunks.append(t)
        if chunks:
            return (role, "\n".join(chunks))
    return None


def _format_turn(role: str, text: str) -> str:
    icon = "▶" if role == "user" else "◆"
    label = "Usuario" if role == "user" else "Claude"
    return f"{icon} {label}\n{text}"
