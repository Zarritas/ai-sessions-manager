# ai-sessions-manager

TUI para navegar y reanudar sesiones de CLIs de IA. Cuatro providers de serie:

| Provider | Storage | Comando resume |
|---|---|---|
| **Claude Code** | `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl` | `claude --resume <id>` |
| **OpenAI Codex** | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | `codex resume <id>` |
| **Goose** (block/goose) | SQLite — `~/.local/share/goose/sessions/sessions.db` (Linux/macOS) o `%APPDATA%\Block\goose\data\sessions\sessions.db` (Windows) | `goose session --resume --id <id>` |
| **opencode** (sst/opencode) | SQLite — `~/.local/share/opencode/opencode.db` (XDG en todas las plataformas, incluido Windows) | `opencode run -s <id>` |

Arquitectura `Provider` extensible — añadir un CLI nuevo es un módulo bajo `providers/` que implementa cuatro métodos (`scan_projects`, `scan_sessions`, `resume_argv`, `new_argv`). Ver "Roadmap" más abajo para los CLIs investigados pero diferidos.

## Qué resuelve

Cuando acumulas decenas de proyectos y cientos de sesiones repartidas entre varias CLIs, encontrar "aquella conversación de hace tres semanas sobre el refactor X" se vuelve incómodo. Cada CLI tiene su propio `--resume` que solo muestra las sesiones del cwd actual, saltar entre proyectos implica `cd`s, y los IDs no son nada amigables.

`ai-sessions-manager`:

1. Te deja **elegir el provider** al arrancar (solo aparecen los CLIs que tienes instalados).
2. Lista todos los proyectos/sesiones de ese provider con metadatos legibles (primer prompt, branch git cuando lo guarda, última actividad).
3. Al pulsar Enter sobre una sesión, ejecuta el comando de resume del provider correspondiente en una pestaña/ventana nueva del terminal.

Comando corto: `aism`. Largo: `ai-sessions-manager`.

## Roadmap

CLIs investigados pero no soportados aún. Cada uno tiene un blocker concreto; PRs bienvenidos:

| CLI | Blocker | Veredicto |
|---|---|---|
| **Cursor CLI** (`cursor-agent`) | SQLite (`~/.cursor/chats/`) con schema indocumentado — reverse-engineering requerido. | Posible-con-hack |
| **Cline CLI** | SQLite (`~/.cline/data/sessions/`) con schema indocumentado. | Posible-con-hack |
| **Crush** (charmbracelet/crush) | SQLite global indocumentado + `--session` solo funciona en modo TUI interactivo, no en `crush run` headless. | Posible-con-hack |
| **Gemini CLI** | Sesiones bajo `~/.gemini/tmp/<project_hash>/chats/` con `project_hash` opaco — hay que computar el hash igual que Gemini para mapear cwd → sesiones. | Posible-con-hack |
| **Aider** | Sin sesiones discretas — todo a `.aider.chat.history.md` por cwd, sin IDs. No encaja en el modelo `Provider`. | No-soportable |

## Stack

- Python 3.10+
- [Textual](https://textual.textualize.io/) para la TUI
- Standard library para todo lo demás (sin dependencias pesadas de parsing)

## Comportamiento

### Pantalla 1 — Proyectos

`DataTable` con una fila por proyecto detectado en `~/.claude/projects/`.

| Columna           | Origen                                                                 |
|-------------------|------------------------------------------------------------------------|
| Proyecto          | basename del cwd real                                                  |
| Path              | cwd real extraído del primer evento del jsonl (no por decodificación)  |
| Sesiones          | nº de archivos `.jsonl` en el directorio del proyecto                  |
| Última actividad  | mtime más reciente entre los `.jsonl` del proyecto                     |

- Orden por defecto: última actividad descendente.
- Proyectos huérfanos (cwd ya no existe en disco): aparecen en estilo apagado, no se pueden abrir.

Atajos:
- `Enter` — entrar a la pantalla de sesiones del proyecto.
- `r` — re-escanear `~/.claude/projects/`.
- `q` — salir.

### Pantalla 2 — Sesiones del proyecto

`DataTable` con una fila por `.jsonl`.

| Columna           | Origen                                                                                |
|-------------------|---------------------------------------------------------------------------------------|
| Primer prompt     | primer `type=user` con `role=user`, limpiando wrappers `<command-message>` / args     |
| Branch            | `gitBranch` del primer evento con cwd                                                 |
| Msgs              | nº de líneas del jsonl                                                                |
| Tamaño            | size en KB del jsonl                                                                  |
| Última actividad  | mtime del jsonl                                                                       |

- Orden por defecto: última actividad descendente.

Atajos:
- `Enter` — reanudar esta sesión con el **modo de lanzamiento predeterminado**.
- `Shift+Enter` — reanudar esta sesión con el **modo alternativo**.
- `n` — nueva sesión en este proyecto (modo predeterminado).
- `s` — abrir el modal de **Ajustes** para cambiar predeterminado/alternativo.
- `Esc` / `←` — volver a la pantalla de proyectos.
- `r` — re-escanear las sesiones del proyecto.
- `q` — salir.

## Cómo se lanza Claude

`launcher.launch_claude(cwd, session_id=None, *, mode="auto")` despacha según el modo elegido:

| Modo       | Estrategia                                                                                              |
|------------|---------------------------------------------------------------------------------------------------------|
| `auto`     | multiplexer split → ventana nueva del emulador → suspender la TUI                                       |
| `window`   | ventana nueva del emulador → suspender la TUI                                                           |
| `suspend`  | suspender la TUI siempre (`app.suspend()` + `subprocess.run`)                                           |

**Cadena `auto` (en orden):**

1. `$TMUX` → `tmux split-window -h -c <cwd> claude [--resume <id>]`.
2. `$ZELLIJ` → `zellij action new-pane --cwd <cwd> -- claude [--resume <id>]`.
3. `$TERMINATOR_UUID` → `terminator --new-tab --working-directory=<cwd> -x claude [...]`.
4. **Ventana nueva del emulador detectado** (ver tabla más abajo).
5. `app.suspend()` + `subprocess.run(["claude", ...], cwd=cwd)`.

**Emuladores soportados en modo `window`** (detectados vía env vars + binario en PATH):

| Emulador          | Comando lanzado                                                       |
|-------------------|-----------------------------------------------------------------------|
| kitty             | `kitty --directory <cwd> claude ...`                                  |
| WezTerm           | `wezterm start --cwd <cwd> -- claude ...`                             |
| Ghostty           | `ghostty --working-directory=<cwd> -e claude ...`                     |
| Alacritty         | `alacritty --working-directory <cwd> -e claude ...`                   |
| Konsole           | `konsole --workdir <cwd> -e claude ...`                               |
| GNOME Terminal    | `gnome-terminal --working-directory=<cwd> -- claude ...`              |
| foot              | `foot --working-directory=<cwd> claude ...`                           |
| Terminator        | `terminator --working-directory=<cwd> -x claude ...` (ventana nueva)  |
| Windows Terminal  | `wt.exe new-tab -d <cwd> -- claude ...`                               |
| iTerm2 (macOS)    | `osascript` → `tell application "iTerm" ... write text "cd <cwd> && exec claude ..."` |
| Apple Terminal (macOS) | `osascript` → `tell application "Terminal" to do script "cd <cwd> && exec claude ..."` |
| x-terminal-emulator / xterm | `<term> -e sh -c "cd <cwd> && exec claude ..."`             |

Detección del emulador (en orden):

1. `$TERM_PROGRAM` (canónico, lo publican Ghostty, WezTerm…).
2. Env var específica del emulador (`$KITTY_PID`, `$GHOSTTY_RESOURCES_DIR`, `$ALACRITTY_LOG`, `$WT_SESSION`, etc.).
3. Fallback genérico: `x-terminal-emulator` o `xterm` si están en PATH (POSIX).

Si ninguno se detecta en modo `window`, la TUI se suspende como último recurso.

## Ajustes (`s`)

Modal en la TUI con dos selectores:

- **Enter (predeterminado)** — modo por defecto (recomendado: `auto`).
- **Shift+Enter (alternativo)** — modo del atajo alternativo (recomendado: `window`).

Solo se configura el **predeterminado**. El **alternativo** (Shift+Enter) se deriva automáticamente:

| Predeterminado | Alternativo (Shift+Enter) |
|----------------|---------------------------|
| `auto`         | `suspend`                 |
| `window`       | `suspend`                 |
| `suspend`      | `window`                  |

Persistido en:
- **Linux/macOS**: `~/.config/ai-sessions-manager/config.json` (o `$XDG_CONFIG_HOME/ai-sessions-manager/config.json` si está definido).
- **Windows**: `%APPDATA%\ai-sessions-manager\config.json` (típicamente `C:\Users\<user>\AppData\Roaming\ai-sessions-manager\config.json`).

```json
{
  "default_mode": "auto"
}
```

> Nota sobre `Shift+Enter`: la mayoría de los emuladores modernos lo transmiten distinto a `Enter`, pero algunos antiguos no — en ese caso `Shift+Enter` simplemente hará lo mismo que `Enter`. Si te ocurre, cambia el predeterminado en Ajustes para que ambas teclas hagan lo que quieres.

## Identidad de un proyecto

El nombre de la carpeta `~/.claude/projects/<encoded>/` es la ruta original con `/` reemplazado por `-`. Esta codificación es ambigua si el path original contenía guiones (`/foo-bar/baz` y `/foo/bar/baz` colisionan).

**Fuente de verdad**: el campo `cwd` del primer evento `type=user` del primer `.jsonl` del proyecto. Solo si no hay ningún jsonl parseable se cae a la heurística `-` → `/`.

`os.path.isdir(cwd)` decide si el proyecto está vivo o huérfano.

## Limitaciones conocidas (MVP)

- **Worktrees git**: cada worktree es un cwd distinto → un proyecto distinto en la TUI. No se agrupan bajo el repo raíz.
- **Proyecto movido de path**: si renombras una carpeta, las sesiones viejas y nuevas aparecen como dos proyectos. No se reconcilian.
- **Sin preview de mensajes**: la lista de sesiones muestra solo el primer prompt. Para leer la conversación tienes que reanudarla o abrir el jsonl a mano.
- **Sin búsqueda full-text**: no hay grep sobre el contenido de las sesiones. Filtras visualmente.

Todas son extensiones razonables para una v2.

## Instalación

### Requisitos previos

- **Linux** (Ubuntu/Debian/Fedora/Arch testados), **macOS** o **Windows 10/11**.
- **Python 3.10+** (la mayoría de distros modernas lo traen; en macOS `brew install python@3.13`; en Windows usa el instalador oficial o `winget install Python.Python.3.13`).
- **`claude`** (Claude Code CLI) en `PATH`. Sin él, `ai-sessions-manager` arranca pero no podrá reanudar sesiones — la propia TUI te lo dirá.
- *(Opcional, Linux/macOS)* **`tmux`** o **`zellij`** (o **`terminator`** sólo en Linux) para que Claude se abra en un split/pestaña sin perder la TUI.
- *(Opcional)* Un emulador soportado:
  - **Linux**: kitty, WezTerm, Ghostty, Alacritty, Konsole, GNOME Terminal, foot, Terminator, xterm.
  - **macOS**: **iTerm2** o **Terminal.app** (modo `window` invoca AppleScript vía `osascript`, que viene de serie en macOS). kitty, WezTerm, Ghostty y Alacritty también funcionan si los usas.
  - **Windows**: **Windows Terminal** (modo `window` abre `claude` en una pestaña nueva vía `wt.exe`).

  Sin nada de esto, la TUI se suspende y vuelve cuando cierras Claude.

### Paso 1 — Instalar un gestor de herramientas Python (si no tienes ninguno)

Cualquiera de los dos funciona; **uv** es el más rápido y el único que cubre las tres plataformas con el mismo binario.

**Linux / macOS:**

```bash
# uv (recomendado)
curl -LsSf https://astral.sh/uv/install.sh | sh

# o pipx
sudo apt install pipx && pipx ensurepath      # Debian/Ubuntu
brew install pipx && pipx ensurepath          # macOS
```

Cierra y abre la terminal para que `~/.local/bin` entre en `PATH`.

**Windows (PowerShell):**

```powershell
# uv (recomendado)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# o vía winget
winget install --id=astral-sh.uv -e
```

Cierra y abre PowerShell (o reinicia Windows Terminal) para que `%USERPROFILE%\.local\bin` entre en `PATH`.

### Paso 2 — Instalar ai-sessions-manager

Una sola línea, sin clonar nada — funciona idéntico en Linux, macOS y Windows:

```bash
uv tool install git+https://github.com/Zarritas/ai-sessions-manager.git
# o (Linux/macOS):
pipx install git+https://github.com/Zarritas/ai-sessions-manager.git
```

### Paso 3 — Lanzarlo

```bash
ai-sessions-manager
```

Deberías ver la lista de tus proyectos de Claude. Pulsa `Enter` para entrar en uno, `Enter` otra vez para reanudar una sesión.

> **macOS**: si es la primera vez que ai-sessions-manager lanza una sesión en una ventana nueva de iTerm2 / Terminal.app, macOS te pedirá permiso para que `osascript` controle esas apps (System Settings → Privacy & Security → Automation). Acepta una vez y queda persistido.
>
> **Windows**: en modo `auto` o `window`, las sesiones se abren en una pestaña nueva de Windows Terminal vía `wt.exe`. Si no estás en Windows Terminal (p.ej. `cmd.exe` o ConEmu), la TUI se suspende y `claude` corre inline.

### Actualizar a la última versión

```bash
uv tool upgrade ai-sessions-manager
# o
pipx upgrade ai-sessions-manager
```

### Desinstalar

```bash
uv tool uninstall ai-sessions-manager
# o
pipx uninstall ai-sessions-manager
```

### Instalación desde una copia local del repo

Si has clonado el repo y quieres instalar tu versión modificada:

```bash
git clone https://github.com/Zarritas/ai-sessions-manager.git
cd ai-sessions-manager
uv tool install .                       # snapshot del estado actual
# o, para que los cambios futuros del repo se reflejen sin reinstalar:
uv tool install --editable .
```

### Troubleshooting

- **`ai-sessions-manager: command not found`** tras instalar (Linux/macOS) → `~/.local/bin` no está en tu `PATH`.
  - `uv` y `pipx` añaden automáticamente esa ruta a la config de tu shell, pero hace falta reiniciar la terminal. Si persiste, ejecuta `uv tool dir --bin` o `pipx environment --value PIPX_BIN_DIR` y añade esa ruta a tu `PATH`.
- **`ai-sessions-manager` no se reconoce como comando** (Windows) → reinicia Windows Terminal/PowerShell tras instalar. Si persiste, comprueba que `%USERPROFILE%\.local\bin` (o el directorio que muestre `uv tool dir --bin`) está en tu `PATH` de usuario.
- **`claude no encontrado en PATH`** al pulsar Enter sobre una sesión → instala Claude Code CLI siguiendo su guía oficial.
- **macOS pide permiso de Automation** la primera vez que lanzas una sesión → es el prompt nativo de `osascript` para controlar iTerm2 / Terminal.app. Acepta y no volverá a aparecer.
- **Proyectos en gris (huérfanos)** → la carpeta original del proyecto ya no existe (moviste o borraste el directorio). Las sesiones siguen ahí pero no se pueden reanudar; bórralas con `d`.

## Desarrollo

```bash
git clone https://github.com/Zarritas/ai-sessions-manager.git
cd ai-sessions-manager
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ai-sessions-manager        # arranca la TUI
pytest              # corre la suite (74 tests)
```

## Estructura del código

```
src/ai_sessions_manager/
  __main__.py        # entrypoint: arranca AiSessionsApp
  app.py             # AiSessionsApp(textual.App) — registra screens
  discovery.py       # scan_projects() → list[Project]
  session.py         # scan_sessions(project) → list[Session], parsers
  launcher.py        # launch_claude(cwd, session_id) con detección de multiplexer
  screens/
    projects.py      # ProjectsScreen — DataTable, bindings
    sessions.py      # SessionsScreen — DataTable, bindings
  styles.tcss        # estilos Textual
```
