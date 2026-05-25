"""Filesystem path completion for the add-project input.

Pure functions, no Textual import: keeps the modal small and lets us unit-test
the matching against ``tmp_path`` without spinning up an app.
"""

from __future__ import annotations

import os
from pathlib import Path

SUGGESTION_LIMIT = 12


def expand(prefix: str) -> Path:
    """``~`` and env-var expansion. Plain wrapper so callers don't import os."""
    return Path(os.path.expandvars(prefix)).expanduser()


def list_suggestions(prefix: str, *, limit: int = SUGGESTION_LIMIT) -> list[Path]:
    """Return up to ``limit`` directory candidates matching ``prefix``.

    Rules:
      - Empty prefix returns ``[]`` (don't dump ``/`` at startup).
      - Prefix ending in ``/`` lists every subdirectory of that path.
      - Otherwise lists the subdirectories of ``Path(prefix).parent`` whose name
        starts with ``Path(prefix).name`` (case-insensitive).
      - Only directories are surfaced — projects live in dirs.

    Errors (permission, missing parent, OSError) yield ``[]`` so the input stays
    interactive even when the user types into a non-readable area.
    """
    if not prefix:
        return []
    expanded = expand(prefix)
    if prefix.endswith("/") and expanded.is_dir():
        base = expanded
        name_filter = ""
    else:
        base = expanded.parent
        name_filter = expanded.name.lower()
    if not base.is_dir():
        return []

    try:
        candidates = [
            entry
            for entry in base.iterdir()
            if entry.is_dir() and entry.name.lower().startswith(name_filter)
        ]
    except (PermissionError, OSError):
        return []

    candidates.sort(key=lambda p: p.name.lower())
    return candidates[:limit]


def common_prefix_completion(prefix: str) -> str | None:
    """Return the longest common path prefix of every candidate, or ``None``.

    Used by Tab: if multiple matches share a longer prefix than the user typed,
    we extend the input to that prefix. If only one match exists, we extend all
    the way to it (and append ``/`` so the next Tab descends into it).
    """
    candidates = list_suggestions(prefix, limit=200)
    if not candidates:
        return None
    if len(candidates) == 1:
        return str(candidates[0]) + "/"
    # commonprefix is string-level (commonpath rounds down to the directory).
    # We want "feature-login" + "feature-logout" → "feature-log".
    common = os.path.commonprefix([str(c) for c in candidates])
    typed = str(expand(prefix))
    if len(common) > len(typed):
        return common
    return None
