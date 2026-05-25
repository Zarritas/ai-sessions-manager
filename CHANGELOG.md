# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (BREAKING)

- **Renamed `multi-claude` → `ai-sessions-manager`**. Both `ai-sessions-manager` and the short alias `aism` are installed as console scripts. The Python package import changed from `multi_claude` to `ai_sessions_manager`; the root class is now `AiSessionsApp`. Existing config files under `~/.config/multi-claude/` need to be moved to `~/.config/ai-sessions-manager/` (or `%APPDATA%\ai-sessions-manager\` on Windows).

### Added

- **Multi-provider architecture**. A new `Provider` Protocol abstracts where each CLI stores its sessions and how to resume them. The TUI now starts on a provider-selection screen and runs the rest of the flow against whichever provider you pick.
  - **Claude Code** provider (`providers/claude.py`): wraps the original discovery/session logic. Behaviour identical to before.
  - **OpenAI Codex** provider (`providers/codex.py`): scans `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, parses each rollout's `session_meta` event for cwd/id/git.branch, groups rollouts by cwd to form projects. Skips Codex's injected `<…>`-wrapped boilerplate (permissions, AGENTS.md, environment_context) to surface the real first prompt. Resume command: `codex resume <id>`.
  - **Goose** provider (`providers/goose.py`): reads the SQLite `sessions.db` (Linux/macOS: `~/.local/share/goose/sessions/sessions.db`, Windows: `%APPDATA%\Block\goose\data\sessions\sessions.db`). Groups sessions by `working_dir` to form projects, filters out archived rows, extracts the first user prompt from `messages.content_json` (the serialised rust `Message` struct). Resume command: `goose session --resume --id <id>` — uses `--id` rather than `--name` because session ids are always populated while names default to empty. Validated against a real `sessions.db` written by goose 1.35.0.
  - **opencode** provider (`providers/opencode.py`): reads the SQLite `opencode.db` at `~/.local/share/opencode/opencode.db` — opencode follows XDG on every platform (including Windows, per upstream). Honours `$OPENCODE_DB` and `$XDG_DATA_HOME` overrides. Groups root sessions (`parent_id IS NULL`, non-archived) by canonicalised `directory` (opencode stores cwds inconsistently with mixed slashes and case, so `os.path.normcase(str(Path(...)))` collapses them). The displayed first prompt comes from the `part` table (not `message.data`, which only holds role/time/summary; the actual text blocks live in `part`). Converts `time_updated` from epoch ms to seconds for consistency with the other providers. Resume command: `opencode run -s <id>`. Validated against a real `opencode.db` with 107 sessions across 13 projects.
  - `providers/__init__.py` exposes `detect_available()` for the selection screen to filter to installed CLIs.

### Roadmap (investigated, deferred)

Four additional CLIs were investigated and have a clear path to integration but require either schema reverse-engineering against a live install or non-trivial reverse-engineering of opaque mappings. PRs welcome:

- **Cursor CLI** (`cursor-agent`): SQLite at `~/.cursor/chats/` with undocumented schema. Resume command confirmed: `cursor-agent resume <id>`.
- **Cline CLI**: SQLite at `~/.cline/data/sessions/` with undocumented schema. Resume: `cline --id <id>`.
- **Crush** (charmbracelet/crush): SQLite at the platform data dir with undocumented schema; additional blocker — `crush --session <id>` only works in interactive TUI mode, not `crush run`.
- **Gemini CLI**: sessions at `~/.gemini/tmp/<project_hash>/chats/`. The `project_hash` is opaque (computed by Gemini at runtime) — needs reverse-engineering of the hash function to map a cwd back to its session dir. Resume command confirmed: `gemini --resume <uuid>`.

**Aider** is explicitly out-of-scope: it stores chat history as `.aider.chat.history.md` per cwd with no discrete session boundaries or IDs — doesn't fit the `Provider` model.
- **macOS support** for spawning new windows in `window`/`auto` mode:
  - **iTerm2** (`TERM_PROGRAM=iTerm.app`) — drives iTerm2 via AppleScript: `tell application "iTerm" to create window with default profile` followed by `write text "cd <cwd> && exec claude [...]"` into the new session. Uses the two-step form because the one-shot `command` parameter is inconsistent across iTerm2 versions.
  - **Terminal.app** (`TERM_PROGRAM=Apple_Terminal`) — `tell application "Terminal" to do script "cd <cwd> && exec claude [...]"` followed by `activate` so the new window comes to the foreground.
  - Both go through `osascript` (always available on macOS). Display names and paths with embedded quotes or backslashes round-trip safely through the POSIX-single-quote + AppleScript-escape layers.
  - Cross-platform emulators (kitty, WezTerm, Ghostty, Alacritty) already worked on macOS without any change — only iTerm2 and Terminal.app needed native AppleScript dispatch.
- **Windows 10/11 support**. The TUI now runs natively on Windows: `Path.home() / ".claude" / "projects"` correctly resolves to `C:\Users\<user>\.claude\projects`, and project rows show real Windows paths (`C:\…`, `D:\…`) extracted from each session's `cwd` field.
  - **Windows Terminal** added to the emulator table — detected via `WT_SESSION` env var. In `window`/`auto` mode the launcher spawns `wt.exe new-tab -d <cwd> -- claude [...]`, opening a new tab in the current WT window (or a new window if none is open).
  - **ConEmu** detected via `ConEmuPID` and surfaced as "not yet supported" with a clear error message (instead of falling through silently).
  - Config file path now prefers `%APPDATA%\ai-sessions-manager\config.json` on Windows (typically `C:\Users\<user>\AppData\Roaming\ai-sessions-manager\config.json`). `XDG_CONFIG_HOME` is still honoured if set, and `~/.config` remains the fallback when `%APPDATA%` is unavailable.
  - On Windows, `detect_multiplexer()` returns `None` (no tmux/zellij/terminator in the native environment) and `auto` falls through directly to window or suspend mode.
- User-defined project folders (`f` in ProjectsScreen) with **nesting**: paths like `Trabajo/Cliente A/Backend`. ProjectsScreen shows one row per root folder summarising direct members and descendants; `Enter` drills into a FolderScreen that lists subfolders + directly-assigned projects mixed together. Inside a folder, `n` creates a subfolder, `e` renames (cascading to descendants and assignments), `d` deletes (cascade unassigns members), `f` removes a project from the folder. Assignments override worktree-grouping for the assigned members. Persists to `~/.config/ai-sessions-manager/project-folders.json`. Filter (`/`) matches folder names. Dangling assignments (folder deleted out-of-band) are auto-cleaned on load.
- Bulk session cleanup (`D`) in SessionsScreen: pick a preset age (1w / 1m / 3m / 6m / 1y) or a custom `YYYY-MM-DD` date, see a live count of how many sessions would be deleted, confirm. Active sessions are skipped automatically.
- Per-session colour override (`c`): pick from a palette; persists to `~/.config/ai-sessions-manager/session-colors.json`.
- In-TUI editor for the colour rules (`Shift+C` / `C`): list, add (`a`), edit (`e` or Enter), delete (`d`), reorder (`j`/`k`). Save with `s`, cancel with `Esc`. Available from both ProjectsScreen and SessionsScreen since rules are global.
- Configurable colour rules in `~/.config/ai-sessions-manager/config.json` under `color_rules`. Each rule is `{"when": "<condition>", "color": "<rich-style>"}` and the first match wins. Manual overrides still beat any rule. Supported conditions:
  - `branch=main` — exact match (case-insensitive)
  - `branch~=feature/*` — glob over branch (or any field)
  - `prompt~=^/` — regex over the displayed prompt
  - `active=true` — session is reported as live in `~/.claude/sessions`
  - `age<1h` / `age<2d` / `age<3w` — last activity newer than the threshold

### Added

- `AppProtocol` (typed contract for the root app) to remove `# type: ignore[attr-defined]` on `app.prefs` / `app.names`.
- Extensible emulator dispatch table in `launcher.py` (one entry per emulator instead of an `if/elif` chain). Adds detection for `TERM_PROGRAM` values published by iTerm2, Apple Terminal, VS Code, Tabby and Warp (notified clearly when no builder exists).
- Stderr capture for `tmux` / `zellij` / `terminator` invocations: failures now surface as a `notify(severity="error")` instead of being swallowed.
- SQLite-backed session index (`~/.local/share/ai-sessions-manager/index.sqlite3`) used as cache plus an FTS5 virtual table for full-text search.
- Background scans via Textual workers; the TUI no longer freezes while parsing large session trees.
- Configurable sort: keys `1`/`2`/`3`/`4` cycle column sort in projects/sessions; direction toggled with `shift+s`. Persisted in `config.json`.
- Per-row preview panel (`p` to toggle) rendering the last turns of the selected session.
- Global FTS search screen (`shift+/`) across all indexed sessions.
- Worktree grouping under the same git repo (`g` to collapse/expand).
- Project merge flow (`m`) to reconcile orphaned projects whose cwd was renamed.
- Yank session id to the clipboard (`y`).
- Fuzzy matching in `/` filter via `rapidfuzz`, plus `key:value` operators (`branch:`, `path:`, `id:`).
- Contextual footer: row-dependent bindings only appear when a row is selected.
- `ruff`, `mypy`, GitHub Actions CI (matrix py3.10/3.11/3.12), `hatch-vcs` versioning, `CHANGELOG.md`, `CONTRIBUTING.md`.

### Changed

- macOS support removed from package classifiers until proper iTerm2 / Terminal.app detection lands.
- Footer hides row-dependent bindings (Rename, Delete, Launch alt) when no session is selected, so the available actions match the cursor state.

### Not done (deferred)

- Differentiating click from Enter on the sessions list: Textual's `DataTable` fires `RowSelected` for both click and Enter, so splitting them cleanly needs a custom widget. Tracked for a follow-up; for now click still launches.

### Fixed

- Deleting a project now refuses (with a confirm-override warning) when one of its sessions is reported as live in `~/.claude/sessions/`.

## [0.1.0] - 2026-05-22

Initial MVP release.

- Two-screen TUI: projects + sessions, sorted by last activity.
- Launch modes: `auto` (multiplexer split → emulator window → suspend), `window` (emulator window → suspend), `suspend`.
- Multiplexer detection: tmux, zellij, terminator.
- Emulator detection: kitty, WezTerm, Ghostty, Alacritty, Konsole, GNOME Terminal, foot, Terminator, x-terminal-emulator, xterm.
- Session rename (`e`), delete (`d`), and persistent display-name store at `~/.config/ai-sessions-manager/names.json`.
- Project add via `a` (launches Claude in a new cwd).
- Settings modal (`s`) to choose default / alternate launch mode (Shift+Enter = opposite of default).

[Unreleased]: https://github.com/Zarritas/ai-sessions-manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Zarritas/ai-sessions-manager/releases/tag/v0.1.0
