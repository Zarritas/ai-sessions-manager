"""ProviderSelectScreen — initial screen that picks which CLI to browse.

Shows one row per provider whose binary is on ``$PATH``. The session count
column gives a quick "do I have anything here" hint without forcing the user
to enter the screen to find out.

On Enter the chosen provider becomes ``app.provider`` and ProjectsScreen is
pushed. From that point on the rest of the app is provider-agnostic.
"""

from __future__ import annotations

from typing import cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from ai_sessions_manager.app_protocol import AppProtocol
from ai_sessions_manager.providers import detect_available
from ai_sessions_manager.providers.base import Provider


class ProviderSelectScreen(Screen[None]):
    """Initial provider chooser. One row per installed CLI."""

    BINDINGS = [
        Binding("enter", "select", "Select", priority=True),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._providers: list[Provider] = []

    @property
    def _root_app(self) -> AppProtocol:
        return cast(AppProtocol, self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="providers", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "Selecciona un proveedor"
        table = self.query_one("#providers", DataTable)
        table.add_columns("Proveedor", "Sesiones", "Ruta")
        self._populate()

    def _populate(self) -> None:
        self._providers = detect_available()
        table = self.query_one("#providers", DataTable)
        table.clear()
        if not self._providers:
            # No CLI on PATH at all — show a single informational row so the
            # screen isn't blank. The user can still press `q` to exit.
            table.add_row(
                "(ninguno detectado)",
                "—",
                "Instala `claude` o `codex` y vuelve a abrir ai-sessions-manager",
            )
            return
        for prov in self._providers:
            count = self._count_projects_safe(prov)
            table.add_row(prov.display_name, str(count), str(prov.sessions_root()))

    def _count_projects_safe(self, prov: Provider) -> int:
        # The selection screen does a synchronous scan per provider purely to
        # get the project count for the hint column. If a provider's scan
        # blows up we'd rather show 0 than crash the whole launcher; the user
        # can still pick it and the real failure will surface in ProjectsScreen.
        try:
            return len(prov.scan_projects())
        except Exception:
            return 0

    @on(DataTable.RowSelected)
    def _on_row_selected(self) -> None:
        self.action_select()

    def action_select(self) -> None:
        if not self._providers:
            return
        table = self.query_one("#providers", DataTable)
        row_idx = table.cursor_row
        if row_idx is None or row_idx < 0 or row_idx >= len(self._providers):
            return
        chosen = self._providers[row_idx]
        # Mutate the app's provider in place so every subsequent screen sees it.
        self._root_app.provider = chosen
        from ai_sessions_manager.screens.projects import ProjectsScreen

        self.app.push_screen(ProjectsScreen())

    def action_refresh(self) -> None:
        self._populate()

    def action_quit(self) -> None:
        self.app.exit()
