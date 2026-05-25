"""SearchScreen — full-text search across every indexed session."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input
from textual.widgets.data_table import RowKey

from ai_sessions_manager.app_protocol import AppProtocol
from ai_sessions_manager.discovery import Project
from ai_sessions_manager.formatting import format_relative_time
from ai_sessions_manager.index import IndexedSession, default_index


class SearchScreen(Screen[None]):
    """Type a query, see matching sessions across all projects. Enter to drill in."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._results: list[IndexedSession] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="busca en todas las sesiones (FTS5)", id="fts-query")
        yield DataTable(id="fts-results", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "búsqueda global (FTS5)"
        table = self.query_one("#fts-results", DataTable)
        table.add_columns("Sesión", "Proyecto", "Branch", "Última")
        self.query_one("#fts-query", Input).focus()

    @on(Input.Changed, "#fts-query")
    def _on_query_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        if not query:
            self._results = []
            self._repaint()
            return
        self._search_worker(query)

    @work(thread=True, exclusive=True, group="fts-search")
    def _search_worker(self, query: str) -> None:
        results = default_index().fts_search(query, limit=200)
        self.app.call_from_thread(self._on_search_complete, results)

    def _on_search_complete(self, results: list[IndexedSession]) -> None:
        self._results = results
        self._repaint()

    def _repaint(self) -> None:
        table = self.query_one("#fts-results", DataTable)
        table.clear()
        for idx, session in enumerate(self._results):
            project_label = Path(session.project_dir).name or session.project_dir
            table.add_row(
                (session.first_prompt or session.session_id)[:80],
                project_label,
                session.branch or "—",
                format_relative_time(session.mtime),
                key=str(idx),
            )

    @on(Input.Submitted, "#fts-query")
    def _on_query_submitted(self, event: Input.Submitted) -> None:
        table = self.query_one("#fts-results", DataTable)
        if self._results:
            table.focus()

    @on(DataTable.RowSelected, "#fts-results")
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        result = self._result_for_row(event.row_key)
        if result is None:
            return
        project = self._project_for_session(result)
        if project is None:
            self.notify("No encuentro el proyecto correspondiente", severity="warning")
            return
        from ai_sessions_manager.screens.sessions import SessionsScreen

        self.app.pop_screen()  # back to ProjectsScreen
        self.app.push_screen(SessionsScreen(project))

    def _result_for_row(self, row_key: RowKey) -> IndexedSession | None:
        if row_key.value is None:
            return None
        idx = int(row_key.value)
        if idx >= len(self._results):
            return None
        return self._results[idx]

    def _project_for_session(self, session: IndexedSession) -> Project | None:
        target = Path(session.project_dir)
        provider = cast(AppProtocol, self.app).provider
        for project in provider.scan_projects():
            if project.encoded_path == target:
                return project
        return None

    def action_back(self) -> None:
        self.app.pop_screen()
