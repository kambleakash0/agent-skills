# Notebook Editor MCP Server

A Model Context Protocol (MCP) server for editing Jupyter notebooks (`.ipynb`) with **cell-level primitives** and **kernel execution**. Provides 23 native tools for working with notebooks the way data scientists actually use them: cells as first-class citizens, outputs and execution state as managed data, and a real Jupyter kernel (whichever one the notebook's kernelspec names: Python, R, Julia, ...) for running code and capturing results.

## Why a cell-native server?

Jupyter notebooks are structured JSON containers with cells, outputs, execution state, and metadata — not flat source files. A notebook-specific server can model this correctly:

- **Cells are the unit of work.** Add, delete, move, split, and merge operations have no analog in a line-based editor.
- **Outputs and execution state matter.** Clearing stale outputs, resetting execution counts, and reading captured results are everyday operations that need first-class tools.
- **Kernel execution is part of the workflow.** Running a cell and capturing its output is how notebooks are used. An editor that can't execute cells misses half the point.
- **Notebook-native discovery.** Listing cells with types and previews, finding symbols across cells, and text-searching all cell sources at once are more useful than treating an `.ipynb` file as a blob of JSON.

This server provides all of these as dedicated tools with clear semantics, built on [`nbformat`](https://nbformat.readthedocs.io/) (for schema-safe notebook I/O) and [`jupyter_client`](https://jupyter-client.readthedocs.io/) (for kernel execution).

## Tools Exposed

All tools require `file_path` to be an **absolute path**. Every tool except `create_notebook` additionally requires the `.ipynb` file to already exist.

### Notebook creation

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `create_notebook` | `file_path`, `kernel_name` (default `"python3"`), `kernel_display_name` (default `""` = same as `kernel_name`), `language` (default `"python"`), `overwrite` (default `False`) | Create a new empty `.ipynb` with a valid nbformat schema and kernelspec. Refuses to overwrite unless `overwrite=True`. |

### Cell structure & navigation

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_cells` | `file_path` | Formatted outline of all cells: index, type, line count, execution count, preview. |
| `get_cell` | `file_path`, `index` | Return the source text of a specific cell. |
| `add_cell` | `file_path`, `index`, `source` (default `""`), `cell_type` (default `"code"`) | Insert a new cell at the given index. `cell_type` is `"code"`, `"markdown"`, or `"raw"`. Pass `index=-1` to append. |
| `delete_cell` | `file_path`, `index` | Remove a cell by index. |
| `move_cell` | `file_path`, `from_index`, `to_index` | Reorder: move a cell from one position to another. |
| `split_cell` | `file_path`, `index`, `line_offset` | Split one cell into two at a line boundary. Outputs cleared on both halves. |
| `merge_cells` | `file_path`, `start_index`, `end_index` | Merge consecutive cells of the same type into one. Outputs cleared. |

### Cell content editing

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `replace_cell_source` | `file_path`, `index`, `new_source` | Replace a cell's entire source. Clears outputs on code cells. |
| `prepend_to_cell` | `file_path`, `index`, `source` | Add lines to the top of a cell. Clears outputs on code cells. |
| `append_to_cell` | `file_path`, `index`, `source` | Add lines to the bottom of a cell. Clears outputs on code cells. |

### Outputs & metadata

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `clear_outputs` | `file_path`, `index` (default `-1` = all code cells) | Clear outputs and execution_count on one code cell or all code cells. |
| `clear_execution_counts` | `file_path` | Reset execution numbering across all code cells. Outputs preserved. |
| `get_outputs` | `file_path`, `index` | Formatted text view of a code cell's outputs (streams, results, errors, display data). |
| `set_cell_metadata` | `file_path`, `index`, `key`, `value` | Set a metadata key on a cell. Value parsed as JSON (supports bools, numbers, arrays, objects). |

### Discovery (read-only)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_notebook_symbols` | `file_path` | Walk all code cells, list Python symbols (functions, classes, methods, imports, top-level assignments) with cell index and line number. |
| `find_in_notebook` | `file_path`, `pattern` | Case-sensitive substring search across all cell sources. |

### Kernel execution

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `execute_cell` | `file_path`, `index`, `timeout` (default `60.0` seconds) | Execute a code cell using the notebook's Jupyter kernel (from `metadata.kernelspec.name`). Captures outputs and writes them back to the file. A cell still running at `timeout` is interrupted and an error is returned. |
| `execute_all_cells` | `file_path`, `timeout` (default `60.0` seconds per cell), `stop_on_error` (default `True`) | Execute all code cells in order. Returns a summary of executed/errored/stopped counts. A cell still running at `timeout` is interrupted and the run stops with an error. |
| `get_kernel_state` | `file_path` | Report whether the notebook's kernel is `not started`, `alive`, or `dead`. |
| `restart_kernel` | `file_path` | Restart the kernel. All in-memory state is lost. |
| `interrupt_kernel` | `file_path` | Interrupt the running cell (SIGINT or the kernel's interrupt message; a KeyboardInterrupt in Python). Stops a long-running or stuck cell. Returns an error saying the kernel is not running if its process has died. |
| `shutdown_kernel` | `file_path` | Shut down the kernel and release resources. |

### Kernel lifecycle notes

- The kernel is **started lazily** on the first `execute_cell` / `execute_all_cells` call.
- **One kernel per notebook file path**, cached in memory for the server's lifetime. Different notebooks get different kernels (isolated namespaces).
- **The kernel runs in the notebook's folder**, as in Jupyter, so relative paths in cells (for example `pd.read_csv("data.csv")`) resolve against the folder that contains the `.ipynb`, not the directory the server was launched from. `restart_kernel` keeps the same working directory.
- **Kernel-agnostic.** The kernel language is read from `metadata.kernelspec.name` in the notebook itself — works with any Jupyter kernel installed on the host: `python3`, `ir` (R via [IRkernel](https://irkernel.github.io/)), `julia-1.x` ([IJulia](https://github.com/JuliaLang/IJulia.jl)), etc. Falls back to `python3` if the notebook has no kernelspec. Set the kernel at creation time with `create_notebook(file_path, kernel_name="ir", language="R", ...)`.
- **The built-in `python3` kernel runs in the server's own environment.** `python3` is the `ipykernel` that ships with the server, in the server's `.venv`. A `python3` notebook can import only what is installed there, so `import pandas` or importing your project's code fails even if your own environment has it. To run notebooks in a project environment:
  1. Install `ipykernel` in that environment (for example `pip install ipykernel` or `uv add ipykernel`).
  2. Register it under its own name, using that environment's Python: `python -m ipykernel install --user --name <name>`.
  3. Create notebooks with `create_notebook(file_path, kernel_name="<name>")`. For an existing notebook, set its `metadata.kernelspec.name` to `<name>` (in JupyterLab, **Kernel → Change Kernel**, then save), then call `shutdown_kernel` so the next run starts the new kernel.

  Registering the environment as `python3` doesn't replace the built-in kernel. The server runs in a virtual environment, so Jupyter looks for kernels in that environment before your user-level ones, and the server's own `python3` is found first.
- **Symbol discovery is Python-only.** `list_notebook_symbols` uses Python's `ast` module and returns a clear "not supported for <language>" message for non-Python notebooks. Use `find_in_notebook` for text search in any language.
- Kernels survive across tool calls, so state accumulates: `execute_cell(0)` then `execute_cell(1)` in a later call sees the variables from cell 0.
- **A timeout interrupts the cell.** When a cell is still running after `timeout` seconds, the server interrupts it (as `interrupt_kernel` does) and waits up to 5 seconds for the kernel to stop. The error then says the cell was interrupted; the kernel keeps its variables and is ready for the next call. If the cell ignores the interrupt, the error says the kernel is still busy: call `restart_kernel`. `timeout` must be positive. If the kernel hadn't started the cell yet when the timeout passed, the cell is interrupted as soon as it starts.
- **Calls on one notebook take turns.** Concurrent `execute_cell` / `execute_all_cells` calls on the same notebook never run two cells at once, and each gets its own outputs; another call's cell can run between two cells of an `execute_all_cells` run. `interrupt_kernel` acts at once. `restart_kernel` and `shutdown_kernel` don't wait for a running cell: they kill the kernel, and that execute call fails with "Kernel died during execution". Calls waiting behind it run afterwards on the restarted kernel, or fail with "Kernel was shut down" after `shutdown_kernel`.
- **Outputs go into the file as it is now.** Execution writes outputs into the notebook as it is when the cell finishes, so edits saved while the cell ran (another tool call, or another cell's execution) are kept.
- Use `shutdown_kernel` to free resources when done with a notebook.

## Which tool should I use?

### Discovering what's in a notebook (do this first)

- **Don't know what's in the notebook?** → `list_cells`
- **Need to see Python symbols defined across cells?** → `list_notebook_symbols`
- **Searching for a name or string?** → `find_in_notebook`
- **Need to read a specific cell?** → `get_cell`

### Creating notebooks

- **Need to create a new empty notebook?** → `create_notebook` (do NOT hand-write `.ipynb` JSON with a generic `Write` tool — `create_notebook` guarantees valid nbformat structure and kernelspec)

### Editing cells

| Intent | Tool |
| :--- | :--- |
| Add a new cell at a specific position | `add_cell` |
| Remove a cell | `delete_cell` |
| Reorder cells | `move_cell` |
| Break a large cell into two | `split_cell` |
| Combine multiple cells into one | `merge_cells` |
| Rewrite a cell's whole source | `replace_cell_source` |
| Add lines to the top of a cell | `prepend_to_cell` |
| Add lines to the bottom of a cell | `append_to_cell` |

### Managing outputs and metadata

| Intent | Tool |
| :--- | :--- |
| Read a cell's output | `get_outputs` |
| Clear stale outputs before committing | `clear_outputs` |
| Remove `In [3]:` numbering noise | `clear_execution_counts` |
| Tag a cell with Jupyter metadata | `set_cell_metadata` |

### Running cells

| Intent | Tool |
| :--- | :--- |
| Run one specific cell | `execute_cell` |
| Re-run the whole notebook | `execute_all_cells` |
| Stop a stuck cell | `interrupt_kernel` |
| Reset kernel state | `restart_kernel` |
| Check if the kernel is alive | `get_kernel_state` |
| Release kernel resources | `shutdown_kernel` |

## Prerequisites

This MCP server uses [`uv`](https://docs.astral.sh/uv/) to manage its Python environment and dependencies automatically. Install `uv` if you don't have it already:

**macOS / Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Homebrew (macOS):**

```bash
brew install uv
```

**pip (any platform):**

```bash
pip install uv
```

Verify the installation:

```bash
uv --version
```

> For more options (Docker, Cargo, WinGet, etc.), see the [official uv installation docs](https://docs.astral.sh/uv/getting-started/installation/).

**uv 0.9.17 or newer is required.** This server's `pyproject.toml` sets a 7-day dependency cooldown (`[tool.uv] exclude-newer = "7 days"`). Older uv versions can't parse that relative duration. They print a warning and ignore the setting. A plain `uv sync` or `uv run`, including the `uv --directory … run` launch commands below, then discards the committed `uv.lock`, re-resolves to the newest compatible versions (even ones published in the last 7 days), and rewrites the file. Upgrade with `uv self update`, `brew upgrade uv`, or `pip install -U uv`, depending on how you installed it. Upgrading doesn't undo an earlier rewrite: restore the original `uv.lock` with `git checkout HEAD -- uv.lock` in this folder, or copy it again from the archive you downloaded.

The server depends on `mcp`, `nbformat`, `jupyter-client`, and `ipykernel`. `uv` handles all of these automatically on first run.

## Installation

> **Note:** Replace `/absolute/path/to/notebook-editor` below with the absolute path to the `notebook-editor` folder on your machine (the folder that contains its `pyproject.toml`).

### Method 1: CLI Configuration (Claude Code, Codex, Gemini)

If your agent supports adding servers via CLI, run the following:

`--scope user` installs the server globally so it's available in every project on your machine. Drop it if you only want the server active in the current project.

```bash
# Claude Code / Codex
[claude|codex] mcp add notebook-editor --scope user -- uv --directory /absolute/path/to/notebook-editor run notebook-editor-mcp

# Gemini CLI
gemini mcp add --transport stdio --scope user notebook-editor -- uv --directory /absolute/path/to/notebook-editor run notebook-editor-mcp
```

### Method 2: JSON Configuration

For tools that use a `mcp_config.json` or `settings.json` file, add the following block.

> **Important:** Use the **absolute path** to `uv` for `"command"`, not just `"uv"`. GUI-based MCP clients (Claude Desktop, Cursor) don't always inherit your shell `PATH`, so a bare `"uv"` will fail with a "command not found" error. Get your absolute path with:
>
> ```bash
> which uv
> # e.g. /Users/you/.local/bin/uv  or  /opt/homebrew/bin/uv
> ```

```json
{
  "mcpServers": {
    "notebook-editor": {
      "command": "/absolute/path/to/uv",
      "args": [
        "--directory",
        "/absolute/path/to/notebook-editor",
        "run",
        "notebook-editor-mcp"
      ]
    }
  }
}
```

| Agent | Configuration File Path |
| :--- | :--- |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS); `%APPDATA%\Claude\claude_desktop_config.json` (Windows) |
| **Cursor** | `.cursor/mcp.json` (Project) or `~/.cursor/mcp.json` (Global) |
| **Windsurf** | Agent Panel → "..." → MCP Servers → View raw config |
| **Antigravity** | `~/.gemini/config/mcp_config.json` — see [Antigravity IDE](#antigravity-ide) (uses `uvx --from`) |
| **Gemini CLI** | `~/.gemini/settings.json` (Global) or `.gemini/settings.json` (Project) |

### Antigravity IDE

The Antigravity IDE uses its own MCP config file and a `uvx`-based command — **not** the `uv --directory … run` form shown above. Add the server to `~/.gemini/config/mcp_config.json`:

> **Important:** Use the **absolute path** to `uvx` for `"command"`, not a bare `"uvx"` — Antigravity doesn't inherit your shell `PATH`. Find it with `which uvx` (e.g. `/opt/homebrew/bin/uvx`).

> **Note:** `uvx` ignores both this server's `uv.lock` and the `[tool.uv]` settings in its `pyproject.toml`. It re-resolves dependencies on each launch instead of using the locked versions, and the 7-day cooldown is passed explicitly as `--exclude-newer "7 days"` in `args`, so you get the newest compatible releases that are at least 7 days old. This requires uv 0.9.17 or newer: older versions reject the value (`invalid value '7 days' for '--exclude-newer <EXCLUDE_NEWER>'`) and the server fails to start.

```json
{
  "mcpServers": {
    "notebook-editor": {
      "command": "/absolute/path/to/uvx",
      "args": [
        "--exclude-newer",
        "7 days",
        "--from",
        "/absolute/path/to/notebook-editor",
        "notebook-editor-mcp"
      ]
    }
  }
}
```

### Using Standard Python (Fallback)

If you prefer not to use `uv`, run the following from the `notebook-editor` folder (the one that contains its `pyproject.toml`), then point to the `.venv` executable it creates. `python3` must be Python 3.10 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install .
```

This path doesn't use uv, so the `[tool.uv]` 7-day dependency cooldown doesn't apply. With pip 26.1 or newer, add `--uploaded-prior-to P7D` to the `pip install` command to apply the same cooldown.

```json
{
  "mcpServers": {
    "notebook-editor": {
      "command": "/absolute/path/to/notebook-editor/.venv/bin/python",
      "args": ["-m", "notebook_editor.server"]
    }
  }
}
```

## Agent Configuration (Important)

Coding agents are heavily biased toward their default tools. You **must** explicitly instruct them to use `notebook-editor` when working with notebooks. The agent prompt lives in [`NOTEBOOK-EDITOR.md`](./NOTEBOOK-EDITOR.md) — a standalone file you wire into your agent's system instructions. The server also sends a condensed version of this guidance as MCP server `instructions`, which some clients pass to the model automatically. Wiring in the full prompt file is still recommended.

### Claude Code / Claude Desktop (via `@`-include)

Claude Code supports `@filename` includes in `CLAUDE.md`. Copy the prompt file into your global config directory and add one include line:

```bash
cp /absolute/path/to/notebook-editor/NOTEBOOK-EDITOR.md ~/.claude/
echo '@NOTEBOOK-EDITOR.md' >> ~/.claude/CLAUDE.md
```

Or for a single project, place it next to the project's `CLAUDE.md` and add `@NOTEBOOK-EDITOR.md` there.

### Other agents (Cursor, Codex CLI, Windsurf, Antigravity, Aider, Gemini CLI, etc.)

Copy the **contents** of [`NOTEBOOK-EDITOR.md`](./NOTEBOOK-EDITOR.md) into your agent's instruction file (`AGENTS.md`, `.cursor/rules/*.mdc`, `.windsurfrules`, `.github/copilot-instructions.md`, system prompt, etc.). Most non-Claude agents don't support `@`-include — paste the prompt body directly.

| Agent | Instruction file |
| :--- | :--- |
| **Any agent that reads `AGENTS.md`** (Codex CLI, Windsurf, Zed, Cursor secondary) | `AGENTS.md` at repo root |
| **Cursor** | `.cursor/rules/*.mdc` (current) — legacy: `.cursorrules` |
| **GitHub Copilot** | `.github/copilot-instructions.md` |
| **Windsurf** | `.windsurfrules` or `AGENTS.md` |
| **Antigravity** | `_agents/rules/` |
| **Aider / Gemini CLI / generic** | Rules file or system prompt |

## Logging & Debugging

The server logs all tool invocations and errors to **stderr** (safe for stdio transport — does not interfere with JSON-RPC). Logs include timestamps and severity levels.

To inspect logs when running under Claude Desktop, check:

- **macOS:** `~/Library/Logs/Claude/mcp*.log`
- **Windows:** `%APPDATA%\Claude\logs\mcp*.log`

For interactive testing, use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector), which provides a UI for exercising each tool with custom parameters and inspecting responses.

### Common issues

- **`No such kernel named <name>`** — the kernel named in the notebook's `metadata.kernelspec.name` isn't installed on this machine. `ipykernel` ships with the server, so `python3` notebooks normally work out of the box; for other languages, install the matching Jupyter kernel (for example IRkernel for R).
- **`ModuleNotFoundError` (for example `No module named 'pandas'`) in a `python3` notebook** — the built-in `python3` kernel runs in the server's own environment, not yours. Register your environment as its own kernel and use it, as described in [Kernel lifecycle notes](#kernel-lifecycle-notes). Naming it `python3` doesn't work, because the server's own `python3` is found first.
- **"Kernel failed to start"** — the kernelspec exists but the kernel couldn't be launched (for example, its `argv` points at a missing executable), or the process died or didn't become ready within 30 seconds. Check that the kernel's own runtime works (for example, that R starts and loads IRkernel), then retry.
- **Retrying after either startup error** — nothing is left running: `get_kernel_state` reports `not started`, and the next `execute_cell` / `execute_all_cells` call tries to start the kernel again. The same holds after a failed `restart_kernel` (**"Kernel failed to restart"**). The server log gets a short warning for each failed start (no traceback).
- **"File is not a .ipynb notebook"** — every tool validates the extension. Rename your file to `.ipynb` or use a conversion tool like [`jupytext`](https://jupytext.readthedocs.io/) to convert `.py` ↔ `.ipynb`.
- **Kernel state carries across calls** — this is intentional. If you need a clean namespace, call `restart_kernel` or `shutdown_kernel`.
- **"Execution timed out after Ns; the cell was interrupted"** — the cell ran longer than `timeout` and was stopped; the kernel keeps its state. For long-running code, pass a larger `timeout` (in seconds).
- **"... the kernel was interrupted but is still busy"** — the cell ignored the interrupt (for example, native code that doesn't check for signals). Call `restart_kernel`; in-memory state is lost.
- **"Kernel is not running (its process has exited)"** from `interrupt_kernel` — the kernel crashed or was killed (`get_kernel_state` reports `dead`). The next `execute_cell` starts a fresh kernel.

## Tool count

**23 tools** total:

- 1 notebook creation (`create_notebook`)
- 7 cell structure & navigation (`list_cells`, `get_cell`, `add_cell`, `delete_cell`, `move_cell`, `split_cell`, `merge_cells`)
- 3 cell content editing (`replace_cell_source`, `prepend_to_cell`, `append_to_cell`)
- 4 outputs & metadata (`clear_outputs`, `clear_execution_counts`, `get_outputs`, `set_cell_metadata`)
- 2 discovery, read-only (`list_notebook_symbols`, `find_in_notebook`)
- 6 kernel execution (`execute_cell`, `execute_all_cells`, `get_kernel_state`, `restart_kernel`, `interrupt_kernel`, `shutdown_kernel`)
