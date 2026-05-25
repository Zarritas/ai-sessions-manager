"""Persistent alias store for projects and worktree groups.

Two namespaces share one JSON file:

- ``project:<encoded_path>`` → alias for a single project / worktree row
- ``repo:<repo_root>``       → alias for a whole worktree group (the shared repo)

``encoded_path`` is the ``~/.claude/projects/<encoded>`` directory and is stable
across cwd renames within Claude's bookkeeping. ``repo_root`` is the absolute path
returned by ``git rev-parse --git-common-dir`` — also stable.

File location follows the XDG Base Directory spec, just like :mod:`names`.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ai-sessions-manager" / "project-names.json"


def project_key(encoded_path: Path) -> str:
    return f"project:{encoded_path}"


def repo_key(repo_root: Path) -> str:
    return f"repo:{repo_root}"


class ProjectNamesStore:
    """File-backed dict for project / worktree-group aliases.

    Same atomic-write + lazy-load pattern as :class:`ai_sessions_manager.names.NamesStore`.
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

    # -- generic key API ---------------------------------------------------- #

    def get(self, key: str) -> str | None:
        return self._load().get(key)

    def set(self, key: str, name: str) -> None:
        data = self._load()
        data[key] = name
        self._write(data)

    def delete(self, key: str) -> None:
        data = self._load()
        if key in data:
            del data[key]
            self._write(data)

    def rename_key(self, old: str, new: str) -> None:
        """Move an alias from ``old`` to ``new`` (used when merging an orphan).

        No-op if ``old`` has no alias. Overwrites any alias already at ``new``
        only if ``old`` actually had one — never silently clobbers otherwise.
        """
        data = self._load()
        alias = data.pop(old, None)
        if alias is not None:
            data[new] = alias
            self._write(data)

    def all(self) -> dict[str, str]:
        return dict(self._load())

    # -- convenience helpers ------------------------------------------------- #

    def for_project(self, encoded_path: Path) -> str | None:
        return self.get(project_key(encoded_path))

    def set_for_project(self, encoded_path: Path, name: str) -> None:
        self.set(project_key(encoded_path), name)

    def delete_for_project(self, encoded_path: Path) -> None:
        self.delete(project_key(encoded_path))

    def for_repo(self, repo_root: Path) -> str | None:
        return self.get(repo_key(repo_root))

    def set_for_repo(self, repo_root: Path, name: str) -> None:
        self.set(repo_key(repo_root), name)

    def delete_for_repo(self, repo_root: Path) -> None:
        self.delete(repo_key(repo_root))

    # -- internals ---------------------------------------------------------- #

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=".project-names.", suffix=".tmp", dir=str(self.path.parent)
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
            os.replace(tmp_path, self.path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
