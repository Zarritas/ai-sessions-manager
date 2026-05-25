"""Persistent display-name store for sessions.

Claude Code's ``-n <name>`` flag is documented as runtime-only (shown in prompt
box and resume picker) and does not persist to disk. ai-sessions-manager keeps its own
mapping ``{session_id: name}`` so renaming survives across restarts.

Default location follows the XDG Base Directory spec:
``$XDG_CONFIG_HOME/ai-sessions-manager/names.json`` (fallback ``~/.config/...``).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ai-sessions-manager" / "names.json"


class NamesStore:
    """File-backed dict of ``session_id -> display_name``.

    Tolerant to a missing or corrupt file (treated as empty). Writes are atomic
    via tmp-file + os.replace. Reads cache the data in memory; callers can call
    ``reload()`` to force a re-read.
    """

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

    def set(self, session_id: str, name: str) -> None:
        data = self._load()
        data[session_id] = name
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
        # Atomic write: tmp in same dir, then rename.
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=".names.", suffix=".tmp", dir=str(self.path.parent)
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
            os.replace(tmp_path, self.path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
