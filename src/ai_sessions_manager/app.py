"""Top-level Textual App. Owns the screen stack, global bindings, prefs and names store."""

from __future__ import annotations

from textual.app import App

from ai_sessions_manager.colors import SessionColorsStore
from ai_sessions_manager.config import Config, load_config, save_config
from ai_sessions_manager.names import NamesStore
from ai_sessions_manager.project_folders import ProjectFoldersStore
from ai_sessions_manager.project_names import ProjectNamesStore
from ai_sessions_manager.providers.base import Provider
from ai_sessions_manager.providers.claude import ClaudeProvider


class AiSessionsApp(App[None]):
    """Root app. Pushes ProviderSelectScreen at startup; ProjectsScreen is pushed on selection."""

    CSS_PATH = "styles.tcss"
    TITLE = "ai-sessions-manager"

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
        from ai_sessions_manager.screens.providers import ProviderSelectScreen

        self.push_screen(ProviderSelectScreen())

    def update_prefs(self, prefs: Config) -> None:
        """Replace in-memory prefs and persist to disk."""
        self.prefs = prefs
        save_config(prefs)
