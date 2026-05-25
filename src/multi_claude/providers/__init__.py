"""Registry of every CLI provider multi-claude knows about.

To plug in a new provider:

1. Drop a module under ``providers/`` whose class implements
   :class:`~multi_claude.providers.base.Provider`.
2. Append an instance to :data:`ALL_PROVIDERS` below.

:func:`detect_available` filters to the providers whose CLI is actually
installed on the user's system; the provider-selection screen displays only
those. Providers with no sessions on disk are still shown but with a 0-count
hint so the user understands the empty state.
"""

from __future__ import annotations

from multi_claude.providers.base import Provider
from multi_claude.providers.claude import ClaudeProvider
from multi_claude.providers.codex import CodexProvider

ALL_PROVIDERS: tuple[Provider, ...] = (
    ClaudeProvider(),
    CodexProvider(),
)


def detect_available() -> list[Provider]:
    """Return providers whose CLI binary is on ``$PATH``.

    Used by the provider-selection screen. A provider that's installed but
    has zero sessions still shows up — only the binary check gates inclusion.
    """
    return [p for p in ALL_PROVIDERS if p.is_installed()]


__all__ = ["Provider", "ClaudeProvider", "CodexProvider", "ALL_PROVIDERS", "detect_available"]
