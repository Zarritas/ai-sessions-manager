"""Entrypoint. `python -m ai_sessions_manager` and the `ai-sessions-manager` console script both land here."""

from __future__ import annotations


def main() -> None:
    from ai_sessions_manager.app import AiSessionsApp

    AiSessionsApp().run()


if __name__ == "__main__":
    main()
