# Notebook Editor MCP Server

A Model Context Protocol (MCP) server for editing Jupyter notebooks (`.ipynb`) with **cell-level primitives** and **kernel execution**. Provides 23 native tools for working with notebooks the way data scientists actually use them: cells as first-class citizens, outputs and execution state as managed data, and a real Python kernel for running code and capturing results.

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
| `create_notebook` | `file_path`, `kernel_name` (default `"python3"`), `kernel_display_name`, `language` (default `"python"`), `overwrite` (default `False`) | Create a new empty `.ipynb` with a valid nbformat schema and kernelspec. Refuses to overwrite unless `overwrite=True`. |

### Cell structure & navigation

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_cells` | `file_path` | Formatted outline of all cells: index, type, line count, execution count, preview. |
| `get_cell` | `file_path`, `index` | Return the source text of a specific cell. |
| `add_cell` | `file_path`, `index`, `source`, `cell_type` | Insert a new cell at the given index. `cell_type` defaults to `"code"`; other options: `"markdown"`, `"raw"`. Pass `index=-1` to append. |
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
| `clear_outputs` | `file_path`, `index` (optional, `-1`=all) | Clear outputs and execution_count on one code cell or all code cells. |
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
| `execute_cell` | `file_path`, `index`, `timeout` | Execute a code cell using the notebook's Python kernel. Captures outputs and writes them back to the file. |
| `execute_all_cells` | `file_path`, `timeout`, `stop_on_error` | Execute all code cells in order. Returns a summary of executed/errored/stopped counts. |
| `get_kernel_state` | `file_path` | Report whether the notebook's kernel is `not started`, `alive`, or `dead`. |
| `restart_kernel` | `file_path` | Restart the kernel. All in-memory state is lost. |
| `interrupt_kernel` | `file_path` | Send a KeyboardInterrupt to the kernel. Stops a long-running or stuck cell. |
| `shutdown_kernel` | `file_path` | Shut down the kernel and release resources. |

### Kernel lifecycle notes

- The kernel is **started lazily** on the first `execute_cell` / `execute_all_cells` call.
- **One kernel per notebook file path**, cached in memory for the server's lifetime. Different notebooks get different kernels (isolated namespaces).
- **Python kernel only** (`python3`) — multi-kernel support (R, Julia, etc.) is not in v1.
- Kernels survive across tool calls, so state accumulates: `execute_cell(0)` then `execute_cell(1)` in a later call sees the variables from cell 0.
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

The server depends on `mcp`, `nbformat`, `jupyter_client`, and `ipykernel`. `uv` handles all of these automatically on first run.

## Installation

> **Note:** Replace `/absolute/path/to` below with the actual path to this repository on your machine.

### Method 1: CLI Configuration (Claude Code, Codex, Gemini)

If your agent supports adding servers via CLI:

`--scope user` installs the server globally so it's available in every project on your machine. Drop it if you only want the server active in the current project.

```bash
# Claude Code / Codex
[claude|codex] mcp add notebook-editor --scope user -- uv --directory /absolute/path/to/mcp-servers/notebook-editor run notebook-editor-mcp

# Gemini CLI
gemini mcp add --transport stdio --scope user notebook-editor -- uv --directory /absolute/path/to/mcp-servers/notebook-editor run notebook-editor-mcp
```

### Method 2: JSON Configuration

For tools that use a `mcp_config.json` or `settings.json` file, add the following block.

> **Important:** Use the **absolute path** to `uv` for `"command"`, not just `"uv"`. GUI-based MCP clients (Claude Desktop, Cursor, Antigravity) don't always inherit your shell `PATH`, so a bare `"uv"` will fail with a "command not found" error. Get your absolute path with:
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
        "/absolute/path/to/mcp-servers/notebook-editor",
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
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` (or via Agent Panel) |
| **Gemini CLI** | `~/.gemini/settings.json` (Global) or `.gemini/settings.json` (Project) |

### Using Standard Python (Fallback)

If you prefer not to use `uv`, install manually and point to the `.venv` executable:

```bash
cd mcp-servers/notebook-editor && python3 -m venv .venv && source .venv/bin/activate && pip install .
```

```json
{
  "mcpServers": {
    "notebook-editor": {
      "command": "/absolute/path/to/mcp-servers/notebook-editor/.venv/bin/python",
      "args": ["-m", "notebook_editor.server"]
    }
  }
}
```

## Agent Configuration (Important)

Coding agents are heavily biased toward their default tools. You **must** explicitly instruct them to use `notebook-editor` when working with notebooks. The agent prompt lives in [`NOTEBOOK-EDITOR.md`](./NOTEBOOK-EDITOR.md) — a standalone file you wire into your agent's system instructions.

### Claude Code / Claude Desktop (via `@`-include)

Claude Code supports `@filename` includes in `CLAUDE.md`. Copy the prompt file into your global config directory and add one include line:

```bash
cp /absolute/path/to/mcp-servers/notebook-editor/NOTEBOOK-EDITOR.md ~/.claude/
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

### Migrating from pre-`NOTEBOOK-EDITOR.md` instructions

**If your `CLAUDE.md` (or other rules file) contains an inline quoted "When working with `.ipynb` files... use notebook-editor" block from an older README version, delete that block and replace it with the `@NOTEBOOK-EDITOR.md` include (or paste the current file's contents).** The new file stays in sync with the current tool set (including `create_notebook`) — an outdated inline copy will drift as tools are added or renamed.

## Logging & Debugging

The server logs all tool invocations and errors to **stderr** (safe for stdio transport — does not interfere with JSON-RPC). Logs include timestamps and severity levels.

To inspect logs when running under Claude Desktop, check:

- **macOS:** `~/Library/Logs/Claude/mcp*.log`
- **Windows:** `%APPDATA%\Claude\logs\mcp*.log`

For interactive testing, use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector), which provides a UI for exercising each tool with custom parameters and inspecting responses.

### Common issues

- **"Cannot execute cell: Kernel failed to start"** — usually means `ipykernel` isn't installed in the server's environment. `uv sync` should handle this; if not, run `uv sync` in the `notebook-editor` directory.
- **"File is not a .ipynb notebook"** — every tool validates the extension. Rename your file to `.ipynb` or use a conversion tool like [`jupytext`](https://jupytext.readthedocs.io/) to convert `.py` ↔ `.ipynb`.
- **Kernel state carries across calls** — this is intentional. If you need a clean namespace, call `restart_kernel` or `shutdown_kernel`.
- **`execute_cell` timeouts on long-running code** — pass a larger `timeout` (in seconds) or interrupt with `interrupt_kernel`.

## Tool count

**23 tools** total:

- 1 notebook creation (`create_notebook`)
- 7 cell structure & navigation (`list_cells`, `get_cell`, `add_cell`, `delete_cell`, `move_cell`, `split_cell`, `merge_cells`)
- 3 cell content editing (`replace_cell_source`, `prepend_to_cell`, `append_to_cell`)
- 4 outputs & metadata (`clear_outputs`, `clear_execution_counts`, `get_outputs`, `set_cell_metadata`)
- 2 discovery, read-only (`list_notebook_symbols`, `find_in_notebook`)
- 6 kernel execution (`execute_cell`, `execute_all_cells`, `get_kernel_state`, `restart_kernel`, `interrupt_kernel`, `shutdown_kernel`)
