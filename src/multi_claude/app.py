"""Top-level Textual App. Owns the screen stack and global bindings."""

from __future__ import annotations

from textual.app import App


class ClaudeBrowserApp(App):
    """Root app. Pushes ProjectsScreen at startup; SessionsScreen is pushed on Enter."""

    CSS_PATH = "styles.tcss"
    TITLE = "multi-claude"

    def on_mount(self) -> None:
        from multi_claude.screens.projects import ProjectsScreen

        self.push_screen(ProjectsScreen())
