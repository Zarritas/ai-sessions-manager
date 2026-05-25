"""Top-level Textual App. Owns the screen stack, global bindings, prefs and names store."""

from __future__ import annotations

from textual.app import App

from multi_claude.colors import SessionColorsStore
from multi_claude.config import Config, load_config, save_config
from multi_claude.names import NamesStore
from multi_claude.project_folders import ProjectFoldersStore
from multi_claude.project_names import ProjectNamesStore
from multi_claude.providers.base import Provider
from multi_claude.providers.claude import ClaudeProvider


class ClaudeBrowserApp(App[None]):
    """Root app. Pushes ProviderSelectScreen at startup; ProjectsScreen is pushed on selection."""

    CSS_PATH = "styles.tcss"
    TITLE = "multi-claude"

    def __init__(self) -> None:
        super().__init__()
        self.prefs: Config = load_config()
        self.names: NamesStore = NamesStore()
        self.project_names: ProjectNamesStore = ProjectNamesStore()
        self.session_colors: SessionColorsStore = SessionColorsStore()
        self.project_folders: ProjectFoldersStore = ProjectFoldersStore()
        # Default to Claude until ProviderSelectScreen sets the real choice.
        # Keeps screens that read ``app.provider`` from crashing if they're
        # constructed before selection (e.g. legacy tests that push
        # ProjectsScreen directly).
        self.provider: Provider = ClaudeProvider()

    def on_mount(self) -> None:
        from multi_claude.screens.providers import ProviderSelectScreen

        self.push_screen(ProviderSelectScreen())

    def update_prefs(self, prefs: Config) -> None:
        """Replace in-memory prefs and persist to disk."""
        self.prefs = prefs
        save_config(prefs)
