"""Cross-platform clipboard write using whatever binary is available on PATH.

Tries (in order): ``wl-copy`` (Wayland), ``xclip``, ``xsel`` (X11). Returns the
name of the binary used, or raises :class:`ClipboardError` if none is found or
the spawn fails. Stays out of the way on macOS by also trying ``pbcopy``.
"""

from __future__ import annotations

import shutil
import subprocess


class ClipboardError(RuntimeError):
    """Raised when no clipboard backend is available or the copy command fails."""


_BACKENDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("wl-copy", ("wl-copy",)),
    ("xclip", ("xclip", "-selection", "clipboard")),
    ("xsel", ("xsel", "--clipboard", "--input")),
    ("pbcopy", ("pbcopy",)),
)


def copy_to_clipboard(text: str) -> str:
    """Write ``text`` to the system clipboard. Returns the backend used."""
    for binary, argv in _BACKENDS:
        if shutil.which(binary) is None:
            continue
        try:
            proc = subprocess.run(argv, input=text, text=True, capture_output=True, check=False)
        except OSError as exc:
            raise ClipboardError(f"{binary} falló: {exc}") from exc
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip() or "(sin stderr)"
            raise ClipboardError(f"{binary} salió con {proc.returncode}: {stderr}")
        return binary
    raise ClipboardError(
        "No se encontró ningún backend de portapapeles (wl-copy / xclip / xsel / pbcopy)."
    )
