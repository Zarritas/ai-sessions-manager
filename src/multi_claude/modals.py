"""Modal screens: rename session, add project, confirm delete.

Each modal completes via ``self.dismiss(<result>)``. Callers use
``await self.app.push_screen(Modal(...), callback)`` and react in ``callback``.
"""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RadioButton, RadioSet, Static

from multi_claude.config import VALID_MODES, Config, LaunchMode, alternate_for
from multi_claude.discovery import Project


def _stop_event(event: object) -> None:
    """Best-effort stop+prevent_default on a Textual key event."""
    stop = getattr(event, "stop", None)
    if callable(stop):
        stop()
    prevent_default = getattr(event, "prevent_default", None)
    if callable(prevent_default):
        prevent_default()


class RenameModal(ModalScreen[str | None]):
    """Ask for a new display name. Empty string + Enter ⇒ delete the name.

    Dismisses with:
      - ``None`` → cancel (no change)
      - ``""``   → delete the existing name
      - ``"x"``  → set name to "x"

    Generic over the entity being renamed: caller passes a title (e.g. "Renombrar
    sesión" / "Renombrar proyecto") and a short subtitle (id, path) for context.
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

    def __init__(
        self,
        subtitle: str,
        current_name: str | None,
        *,
        title: str = "Renombrar",
        placeholder: str = "nuevo nombre",
    ) -> None:
        super().__init__()
        self.subtitle = subtitle
        self.current_name = current_name or ""
        self._title_text = title
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title_text, classes="title")
            yield Static(self.subtitle)
            yield Input(value=self.current_name, placeholder=self._placeholder, id="name-input")
            yield Label("Enter guarda · vacío borra el nombre · Esc cancela", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    @on(Input.Submitted, "#name-input")
    def _submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


class AddProjectModal(ModalScreen[Path | None]):
    """Ask for a project path with shell-like autocomplete.

    - Typing updates a list of matching subdirectories below the input.
    - ``Tab``  → extend the input to the longest common prefix of candidates.
    - ``↓``    → move focus into the suggestion list; ``Enter`` picks one.
    - ``Enter`` on the input → submit and resolve the path.
    - Returns a resolved :class:`Path` on submit, ``None`` on cancel.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("down", "focus_suggestions", "Elegir sugerencia", priority=True),
    ]

    DEFAULT_CSS = """
    AddProjectModal {
        align: center middle;
    }
    AddProjectModal > Vertical {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 90;
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
    AddProjectModal OptionList#suggestions {
        max-height: 12;
        border: round $accent;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import OptionList

        with Vertical():
            yield Label("Añadir proyecto — lanzar Claude en un cwd nuevo", classes="title")
            yield Input(placeholder="/ruta/al/proyecto", id="path-input")
            suggestions = OptionList(id="suggestions")
            suggestions.display = False
            yield suggestions
            yield Label("", id="error", classes="error")
            yield Label("Enter lanza · Tab completa · ↓ elige · Esc cancela", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#path-input", Input).focus()

    # -- typing + suggestions ------------------------------------------------ #

    @on(Input.Changed, "#path-input")
    def _on_input_changed(self, event: Input.Changed) -> None:
        self._refresh_suggestions(event.value)

    def _refresh_suggestions(self, prefix: str) -> None:
        from textual.widgets import OptionList

        from multi_claude.path_complete import list_suggestions

        suggestions = list_suggestions(prefix)
        opt_list = self.query_one("#suggestions", OptionList)
        opt_list.clear_options()
        if not suggestions:
            opt_list.display = False
            return
        opt_list.display = True
        for path in suggestions:
            opt_list.add_option(str(path))

    # -- keys ---------------------------------------------------------------- #

    def on_key(self, event: object) -> None:
        key = getattr(event, "key", None)
        if key == "tab":
            self._tab_complete()
            _stop_event(event)
            return
        # Escape hatches when focus is inside the suggestion list.
        if self._suggestions_have_focus():
            if key == "escape":
                self._focus_input()
                _stop_event(event)
                return
            if key == "up" and self._suggestions_at_top():
                self._focus_input()
                _stop_event(event)

    def _suggestions_have_focus(self) -> bool:
        from textual.widgets import OptionList

        try:
            opt_list = self.query_one("#suggestions", OptionList)
        except Exception:
            return False
        return bool(opt_list.has_focus)

    def _suggestions_at_top(self) -> bool:
        from textual.widgets import OptionList

        try:
            opt_list = self.query_one("#suggestions", OptionList)
        except Exception:
            return False
        # highlighted is None when nothing is selected; treat that as "at top".
        return opt_list.highlighted in (None, 0)

    def _focus_input(self) -> None:
        input_w = self.query_one("#path-input", Input)
        input_w.focus()
        input_w.cursor_position = len(input_w.value)

    def action_focus_suggestions(self) -> None:
        """Move focus into the suggestion list (priority binding so Input doesn't eat ↓)."""
        from textual.widgets import OptionList

        input_w = self.query_one("#path-input", Input)
        opt_list = self.query_one("#suggestions", OptionList)
        if not input_w.has_focus:
            return
        if not opt_list.display or opt_list.option_count == 0:
            return
        opt_list.focus()
        opt_list.highlighted = 0

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Disable the ↓ priority binding once focus is inside the suggestion list.

        Without this, ``Binding("down", ..., priority=True)`` would keep swallowing
        every ↓ and the OptionList could never advance the highlight.
        """
        if action == "focus_suggestions":
            try:
                input_w = self.query_one("#path-input", Input)
            except Exception:
                return False
            if not input_w.has_focus:
                return False
            from textual.widgets import OptionList

            try:
                opt_list = self.query_one("#suggestions", OptionList)
            except Exception:
                return False
            if not opt_list.display or opt_list.option_count == 0:
                return False
        return True

    def _tab_complete(self) -> None:
        from multi_claude.path_complete import common_prefix_completion

        input_w = self.query_one("#path-input", Input)
        completion = common_prefix_completion(input_w.value)
        if completion is None or completion == input_w.value:
            return
        input_w.value = completion
        input_w.cursor_position = len(completion)
        self._refresh_suggestions(completion)

    # -- option picked ------------------------------------------------------- #

    def _handle_suggestion_selected(self, prompt: str) -> None:
        if not prompt:
            return
        if not prompt.endswith("/"):
            prompt = prompt + "/"
        input_w = self.query_one("#path-input", Input)
        input_w.value = prompt
        input_w.cursor_position = len(prompt)
        input_w.focus()
        self._refresh_suggestions(prompt)

    def on_option_list_option_selected(self, event: object) -> None:
        # Filter by widget id (Textual delivers the OptionSelected message to the screen).
        control = getattr(event, "control", None) or getattr(event, "option_list", None)
        if control is not None and getattr(control, "id", None) != "suggestions":
            return
        option = getattr(event, "option", None)
        prompt = str(getattr(option, "prompt", "")) if option is not None else ""
        self._handle_suggestion_selected(prompt)

    # -- submit / cancel ----------------------------------------------------- #

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


_MODE_LABELS: dict[LaunchMode, str] = {
    "auto": "Auto — multiplexer > ventana nueva > suspend",
    "window": "Ventana nueva del emulador (suspend si no se detecta)",
    "suspend": "Suspender la TUI",
}


class SettingsModal(ModalScreen[Config | None]):
    """Edit the default launch mode. Shift+Enter mode is derived (see alternate_for)."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    SettingsModal {
        align: center middle;
    }
    SettingsModal > Vertical {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 80;
        height: auto;
    }
    SettingsModal Label.title {
        text-style: bold;
    }
    SettingsModal Label.section {
        margin-top: 1;
        text-style: bold;
        color: $accent;
    }
    SettingsModal Label.alt-preview {
        margin-top: 1;
        color: $text-muted;
    }
    SettingsModal Label.hint {
        color: $text-muted;
        margin-top: 1;
    }
    SettingsModal Horizontal {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    SettingsModal Button {
        margin: 0 1;
    }
    """

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._initial = config

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal

        with Vertical():
            yield Label("Ajustes — modo de lanzamiento", classes="title")

            yield Label("Enter (predeterminado)", classes="section")
            with RadioSet(id="default-mode"):
                for mode in VALID_MODES:
                    yield RadioButton(
                        _MODE_LABELS[mode],
                        value=(mode == self._initial.default_mode),
                        id=f"default-{mode}",
                    )

            yield Label(
                self._alt_preview_text(self._initial.default_mode),
                id="alt-preview",
                classes="alt-preview",
            )

            yield Label("Enter guarda · Esc cancela", classes="hint")
            with Horizontal():
                yield Button("Cancelar", id="cancel", variant="default")
                yield Button("Guardar", id="save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#default-mode", RadioSet).focus()

    @on(RadioSet.Changed, "#default-mode")
    def _on_default_changed(self, event: RadioSet.Changed) -> None:
        mode = self._mode_from_radio_id(event.pressed.id, self._initial.default_mode)
        self.query_one("#alt-preview", Label).update(self._alt_preview_text(mode))

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save")
    def _save(self) -> None:
        self.dismiss(self._collect())

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _collect(self) -> Config:
        radio_set = self.query_one("#default-mode", RadioSet)
        pressed = radio_set.pressed_button
        mode = self._mode_from_radio_id(
            pressed.id if pressed is not None else None,
            self._initial.default_mode,
        )
        return Config(default_mode=mode)

    @staticmethod
    def _mode_from_radio_id(radio_id: str | None, fallback: LaunchMode) -> LaunchMode:
        if radio_id and radio_id.startswith("default-"):
            candidate = radio_id.split("-", 1)[1]
            if candidate in VALID_MODES:
                return candidate
        return fallback

    @staticmethod
    def _alt_preview_text(default: LaunchMode) -> str:
        return f"Shift+Enter → {_MODE_LABELS[alternate_for(default)]}"


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


class MergeProjectModal(ModalScreen[Project | None]):
    """Pick a destination project to merge an orphan into.

    Lists candidate projects automatically detected (same repo root or same name).
    Dismisses with the chosen :class:`Project`, or ``None`` on cancel.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    MergeProjectModal {
        align: center middle;
    }
    MergeProjectModal > Vertical {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 90;
        height: auto;
    }
    MergeProjectModal Label.title {
        text-style: bold;
    }
    MergeProjectModal Label.section {
        margin-top: 1;
        text-style: bold;
        color: $accent;
    }
    MergeProjectModal Label.hint {
        color: $text-muted;
        margin-top: 1;
    }
    MergeProjectModal Label.error {
        color: $error;
        margin-top: 1;
    }
    """

    def __init__(self, orphan: Project, candidates: list[Project]) -> None:
        super().__init__()
        self.orphan = orphan
        self.candidates = candidates

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Reconciliar proyecto huérfano", classes="title")
            yield Static(f"Huérfano: {self.orphan.path}  ·  {self.orphan.session_count} sesión(es)")

            if self.candidates:
                yield Label("Candidatos detectados", classes="section")
                with RadioSet(id="merge-target"):
                    for idx, candidate in enumerate(self.candidates):
                        label = f"{candidate.name} — {candidate.path}"
                        yield RadioButton(label, value=(idx == 0), id=f"target-{idx}")
                yield Label("Enter confirma · Esc cancela", classes="hint")
            else:
                yield Label(
                    "No hay candidatos automáticos. Crea primero el proyecto destino con `a` "
                    "y vuelve a intentarlo.",
                    classes="hint",
                )

            yield Label("", id="merge-error", classes="error")

    def on_mount(self) -> None:
        if self.candidates:
            self.query_one("#merge-target", RadioSet).focus()

    def on_key(self, event: object) -> None:
        # Confirm with Enter when focused on the RadioSet.
        if not self.candidates:
            return
        key_name = getattr(event, "key", None)
        if key_name == "enter":
            self._submit_radio()

    def _submit_radio(self) -> None:
        if not self.candidates:
            self.dismiss(None)
            return
        radio_set = self.query_one("#merge-target", RadioSet)
        pressed = radio_set.pressed_button
        if pressed is None or pressed.id is None or not pressed.id.startswith("target-"):
            self._set_error("Selecciona un candidato.")
            return
        idx = int(pressed.id.split("-", 1)[1])
        self.dismiss(self.candidates[idx])

    def _set_error(self, msg: str) -> None:
        self.query_one("#merge-error", Label).update(msg)

    def action_cancel(self) -> None:
        self.dismiss(None)
