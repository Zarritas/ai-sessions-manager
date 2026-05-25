"""multi-claude — TUI to browse and resume Claude Code sessions across projects."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("multi-claude")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"
