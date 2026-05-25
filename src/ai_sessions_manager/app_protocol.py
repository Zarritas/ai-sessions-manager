"""Typed contract for the root app, used by screens and modals.

Lets screens type ``self.app`` precisely instead of leaking ``# type: ignore``s.
Anything the screens read off the app (prefs, names store) belongs here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ai_sessions_manager.colors import SessionColorsStore
    from ai_sessions_manager.config import Config
    from ai_sessions_manager.names import NamesStore
    from ai_sessions_manager.project_folders import ProjectFoldersStore
    from ai_sessions_manager.project_names import ProjectNamesStore
    from ai_sessions_manager.providers.base import Provider


class AppProtocol(Protocol):
    prefs: Config
    names: NamesStore
    project_names: ProjectNamesStore
    session_colors: SessionColorsStore
    project_folders: ProjectFoldersStore
    provider: Provider

    def update_prefs(self, prefs: Config) -> None: ...
