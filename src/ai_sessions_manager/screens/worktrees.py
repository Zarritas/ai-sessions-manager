"""WorktreesScreen — drill into a group of worktrees that share a git repo."""

from __future__ import annotations

from typing import cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header
from textual.widgets.data_table import RowKey

from ai_sessions_manager.app_protocol import AppProtocol
from ai_sessions_manager.discovery import Project, WorktreeGroup
from ai_sessions_manager.formatting import format_relative_time
from ai_sessions_manager.modals import RenameModal


class WorktreesScreen(Screen[None]):
    """Lists individual worktrees of a repo. Enter drills into the project's sessions."""

    BINDINGS = [
        Binding("e", "rename", "Rename"),
        Binding("escape", "back", "Back"),
        Binding("left", "back", "Back", show=False),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, group: WorktreeGroup) -> None:
        super().__init__()
        self.group = group
        self._members: tuple[Project, ...] = group.members

    @property
    def _root_app(self) -> AppProtocol:
        return cast(AppProtocol, self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="worktrees", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        group_alias = self._root_app.project_names.for_repo(self.group.repo_root)
        repo_label = group_alias or self.group.repo_root.name or str(self.group.repo_root)
        self.sub_title = f"{repo_label} — {self.group.repo_root}"
        table = self.query_one("#worktrees", DataTable)
        table.add_columns("Worktree", "Path", "Sesiones", "Última")
        self._repaint()
        table.focus()

    def _repaint(self) -> None:
        table = self.query_one("#worktrees", DataTable)
        table.clear()
        store = self._root_app.project_names
        for idx, project in enumerate(self._members):
            display = store.for_project(project.encoded_path) or project.name
            table.add_row(
                display,
                str(project.path),
                str(project.session_count),
                format_relative_time(project.last_activity),
                key=str(idx),
            )

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        project = self._project_for_row(event.row_key)
        if project is None:
            return
        from ai_sessions_manager.screens.sessions import SessionsScreen

        self.app.push_screen(SessionsScreen(project))

    def _project_for_row(self, row_key: RowKey) -> Project | None:
        if row_key.value is None:
            return None
        idx = int(row_key.value)
        if idx >= len(self._members):
            return None
        return self._members[idx]

    def _selected_worktree(self) -> Project | None:
        table = self.query_one("#worktrees", DataTable)
        if table.cursor_row is None or table.cursor_row < 0:
            return None
        if table.cursor_row >= len(self._members):
            return None
        return self._members[table.cursor_row]

    def action_rename(self) -> None:
        worktree = self._selected_worktree()
        if worktree is None:
            return
        store = self._root_app.project_names
        current = store.for_project(worktree.encoded_path)
        self.app.push_screen(
            RenameModal(
                subtitle=f"{worktree.name} — {worktree.path}",
                current_name=current,
                title="Renombrar worktree",
                placeholder="alias del worktree",
            ),
            lambda result: self._apply_rename(worktree, result),
        )

    def _apply_rename(self, worktree: Project, result: str | None) -> None:
        if result is None:
            return  # cancelled
        store = self._root_app.project_names
        if result == "":
            store.delete_for_project(worktree.encoded_path)
            self.notify("Alias borrado")
        else:
            store.set_for_project(worktree.encoded_path, result)
            self.notify(f"Worktree renombrado: {result}")
        self._repaint()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        return not (action == "rename" and self._selected_worktree() is None)

    def action_back(self) -> None:
        self.app.pop_screen()
