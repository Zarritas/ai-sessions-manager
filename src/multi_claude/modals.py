"""Modal screens: rename session, add project, confirm delete.

Each modal completes via ``self.dismiss(<result>)``. Callers use
``await self.app.push_screen(Modal(...), callback)`` and react in ``callback``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class RenameModal(ModalScreen[str | None]):
    """Ask for a new display name. Empty string + Enter ⇒ delete the name.

    Dismisses with:
      - ``None`` → cancel (no change)
      - ``""``   → delete the existing name
      - ``"x"``  → set name to "x"
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    RenameModal {
        align: center middle;
    }
    RenameModal > Vertical {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 70;
        height: auto;
    }
    RenameModal Label.title {
        text-style: bold;
    }
    RenameModal Label.hint {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, session_id: str, current_name: str | None) -> None:
        super().__init__()
        self.session_id = session_id
        self.current_name = current_name or ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Renombrar sesión", classes="title")
            yield Static(f"id: {self.session_id}")
            yield Input(value=self.current_name, placeholder="nuevo nombre", id="name-input")
            yield Label("Enter guarda · vacío borra el nombre · Esc cancela", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    @on(Input.Submitted, "#name-input")
    def _submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


class AddProjectModal(ModalScreen[Path | None]):
    """Ask for a project path. Returns a resolved Path on submit, None on cancel."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    AddProjectModal {
        align: center middle;
    }
    AddProjectModal > Vertical {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 80;
        height: auto;
    }
    AddProjectModal Label.title {
        text-style: bold;
    }
    AddProjectModal Label.error {
        color: $error;
        margin-top: 1;
    }
    AddProjectModal Label.hint {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Añadir proyecto — lanzar Claude en un cwd nuevo", classes="title")
            yield Input(placeholder="/ruta/al/proyecto", id="path-input")
            yield Label("", id="error", classes="error")
            yield Label("Enter lanza Claude · Esc cancela", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    @on(Input.Submitted, "#path-input")
    def _submit(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        if not raw:
            self._set_error("Indica una ruta")
            return
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve(strict=False)
        except OSError as exc:
            self._set_error(f"Ruta inválida: {exc}")
            return
        if not resolved.exists():
            self._set_error(f"No existe: {resolved}")
            return
        if not resolved.is_dir():
            self._set_error(f"No es un directorio: {resolved}")
            return
        self.dismiss(resolved)

    def _set_error(self, msg: str) -> None:
        self.query_one("#error", Label).update(msg)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmDeleteModal(ModalScreen[bool]):
    """Yes/no confirmation. Cancel-focused by default; ``y`` confirms.

    Dismisses with True (confirm) or False (cancel).
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
    ]

    DEFAULT_CSS = """
    ConfirmDeleteModal {
        align: center middle;
    }
    ConfirmDeleteModal > Vertical {
        background: $surface;
        border: thick $error;
        padding: 1 2;
        width: 80;
        height: auto;
    }
    ConfirmDeleteModal Label.title {
        text-style: bold;
        color: $error;
    }
    ConfirmDeleteModal Label.warning {
        color: $warning;
        text-style: bold;
        margin-top: 1;
    }
    ConfirmDeleteModal Label.hint {
        color: $text-muted;
        margin-top: 1;
    }
    ConfirmDeleteModal Horizontal {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    ConfirmDeleteModal Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        title: str,
        details: list[str],
        *,
        warning: str | None = None,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.details = details
        self.warning = warning

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal

        with Vertical():
            yield Label(self.title_text, classes="title")
            for line in self.details:
                yield Static(line)
            if self.warning:
                yield Label(f"⚠️  {self.warning}", classes="warning")
            yield Label("`y` confirma · Enter/Esc cancela", classes="hint")
            with Horizontal():
                yield Button("Cancelar", id="cancel", variant="default")
                yield Button("Borrar", id="confirm", variant="error")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm")
    def _confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)
