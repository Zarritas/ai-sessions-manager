"""Color assignment for sessions and projects.

Two layers, manual > rules:

- :class:`SessionColorsStore` — persistent ``{session_id: color}`` map written
  by the user via the ``c`` binding.
- :class:`ColorRule` — pattern-based defaults loaded from ``config.json``.

Both layers produce a Textual / Rich style string (``"green"``, ``"bold cyan"``,
``"#ffaa00"``...) — whatever the renderer accepts. Nothing here imports Textual
so the resolution logic stays unit-testable.

Conditions supported in rules (one ``when`` string per rule):

- ``branch=main``           — exact branch match (case-insensitive)
- ``branch~=feature/*``     — glob over the branch field
- ``prompt~=^/``            — regex over the displayed prompt / display name
- ``active=true``           — session is reported as live in ~/.claude/sessions
- ``age<1h`` / ``age<2d``   — last activity is more recent than the threshold

The first rule whose condition matches wins.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from multi_claude.session import Session


# --------------------------------------------------------------------------- #
# Palette                                                                      #
# --------------------------------------------------------------------------- #


PALETTE: tuple[tuple[str, str], ...] = (
    ("Rojo", "bold red"),
    ("Verde", "bold green"),
    ("Amarillo", "bold yellow"),
    ("Azul", "bold blue"),
    ("Magenta", "bold magenta"),
    ("Cian", "bold cyan"),
    ("Naranja", "bold #ff8800"),
    ("Violeta", "bold #c678dd"),
    ("Gris", "dim white"),
)


def palette_label_for(style: str) -> str | None:
    """Reverse-lookup: human label for a stored style string, or ``None``."""
    for label, value in PALETTE:
        if value == style:
            return label
    return None


# --------------------------------------------------------------------------- #
# Manual override store                                                        #
# --------------------------------------------------------------------------- #


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "multi-claude" / "session-colors.json"


class SessionColorsStore:
    """File-backed ``{session_id: style}`` map. Same atomic-write pattern as NamesStore."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()
        self._data: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._data is not None:
            return self._data
        try:
            with self.path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            raw = {}
        self._data = (
            {str(k): str(v) for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
            if isinstance(raw, dict)
            else {}
        )
        return self._data

    def reload(self) -> None:
        self._data = None
        self._load()

    def get(self, session_id: str) -> str | None:
        return self._load().get(session_id)

    def set(self, session_id: str, style: str) -> None:
        data = self._load()
        data[session_id] = style
        self._write(data)

    def delete(self, session_id: str) -> None:
        data = self._load()
        if session_id in data:
            del data[session_id]
            self._write(data)

    def all(self) -> dict[str, str]:
        return dict(self._load())

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=".session-colors.", suffix=".tmp", dir=str(self.path.parent)
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
            os.replace(tmp_path, self.path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise


# --------------------------------------------------------------------------- #
# Rule model + parser                                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ColorRule:
    when: str
    color: str

    def to_dict(self) -> dict[str, str]:
        return {"when": self.when, "color": self.color}

    @classmethod
    def from_dict(cls, raw: object) -> ColorRule | None:
        if not isinstance(raw, dict):
            return None
        when = raw.get("when")
        color = raw.get("color")
        if not isinstance(when, str) or not isinstance(color, str):
            return None
        if not when or not color:
            return None
        return cls(when=when, color=color)


_AGE_RE = re.compile(r"^(\d+)\s*([smhdw])$")
_AGE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}


def _parse_age_seconds(value: str) -> float | None:
    match = _AGE_RE.match(value.strip().lower())
    if not match:
        return None
    quantity, unit = match.groups()
    return float(int(quantity) * _AGE_UNITS[unit])


def _match_condition(when: str, session: Session, *, is_active: bool, now: float) -> bool:
    """Evaluate one ``when`` expression against ``session``.

    Unknown / malformed expressions evaluate to False so a typo in config can't
    accidentally colour everything.
    """
    expr = when.strip()
    if not expr:
        return False

    # active=true / active=false
    if expr.startswith("active="):
        wanted = expr.split("=", 1)[1].strip().lower() == "true"
        return is_active == wanted

    # age<1h
    if expr.startswith("age<"):
        seconds = _parse_age_seconds(expr[4:])
        if seconds is None:
            return False
        return (now - session.last_activity) < seconds

    # field~=glob_or_regex
    if "~=" in expr:
        field, pattern = expr.split("~=", 1)
        haystack = _field_value(field.strip(), session)
        if haystack is None:
            return False
        return _matches_glob_or_regex(pattern.strip(), haystack)

    # field=value (exact, case-insensitive)
    if "=" in expr:
        field, value = expr.split("=", 1)
        haystack = _field_value(field.strip(), session)
        if haystack is None:
            return False
        return haystack.casefold() == value.strip().casefold()

    return False


def _field_value(name: str, session: Session) -> str | None:
    if name == "branch":
        return session.branch or ""
    if name == "prompt":
        return session.display_name or session.first_prompt or ""
    if name == "id":
        return session.id
    if name == "cwd":
        return session.cwd or ""
    return None


def _matches_glob_or_regex(pattern: str, haystack: str) -> bool:
    """``~=`` accepts either a shell glob or, if it looks like a regex (starts with
    ``^`` or contains regex metacharacters not in glob), a Python regex."""
    if pattern.startswith("^") or any(c in pattern for c in "()|\\"):
        try:
            return re.search(pattern, haystack) is not None
        except re.error:
            return False
    return fnmatch.fnmatchcase(haystack.casefold(), pattern.casefold())


# --------------------------------------------------------------------------- #
# Resolution                                                                   #
# --------------------------------------------------------------------------- #


def resolve_style(
    session: Session,
    *,
    manual: SessionColorsStore | None = None,
    rules: list[ColorRule] | None = None,
    is_active: bool = False,
    now: float | None = None,
) -> str | None:
    """Manual override wins; otherwise first matching rule wins; else ``None``."""
    if manual is not None:
        override = manual.get(session.id)
        if override:
            return override
    if not rules:
        return None
    now_ts = time.time() if now is None else now
    for rule in rules:
        if _match_condition(rule.when, session, is_active=is_active, now=now_ts):
            return rule.color
    return None
