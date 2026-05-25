"""ai-sessions-manager — TUI to browse and resume Claude Code sessions across projects."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ai-sessions-manager")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"
