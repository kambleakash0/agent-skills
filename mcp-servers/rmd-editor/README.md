# RMD Editor MCP Server

A Model Context Protocol (MCP) server for editing R Markdown (`.rmd`) documents with **chunk- and prose-level primitives** and **R kernel execution**. Provides 24 native tools for working with R Markdown the way data scientists actually use it: code chunks as first-class citizens, YAML frontmatter as structured data, and a real R kernel for running chunks and capturing results.

## Why a chunk-native server?

R Markdown files are `.rmd` text documents with YAML frontmatter, interleaved markdown prose, and executable ` ```{r} ` code chunks — not a flat source file and not a JSON notebook. A chunk-specific server can model this correctly:

- **Chunks are the unit of analysis.** Add, delete, reorder, split, merge — all operations that a line-based editor would corrupt.
- **Chunk options are structured.** Labels (`setup`, `analysis`), `echo=FALSE`, `fig.width=7`, `message=FALSE` — these live in the chunk header and need first-class read/write tools.
- **YAML frontmatter is structured too.** `title`, `author`, `output`, `date` belong in the YAML header, not scattered in prose. Dedicated tools keep edits clean.
- **Kernel execution is part of the workflow.** Running a chunk and inspecting output is how analysts iterate. Outputs are returned **inline** to the caller and are **never** written to the `.rmd` file — R Markdown regenerates outputs on render (`rmarkdown::render()`), so persisting them would drift from the canonical format.

This server complements `notebook-editor` (for `.ipynb` Jupyter notebooks): different file format, same mental model. If you already use `notebook-editor`, the API here is deliberately parallel.

## Tools Exposed

All tools require `file_path` to be an **absolute path**. Every tool except `create_rmd` additionally requires the `.rmd` file to already exist.

### Document creation

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `create_rmd` | `file_path`, `title` (default `""`), `author` (default `""`), `output_format` (default `"html_document"`), `overwrite` (default `False`) | Create a new empty `.rmd` with a minimal YAML frontmatter. Refuses to overwrite unless `overwrite=True`. |

### Cell structure & navigation

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_cells` | `file_path` | Outline of all cells with index, type (code/markdown), language/label/option-count for chunks, line count, and a one-line preview. |
| `get_cell` | `file_path`, `index` | Return the source text of a specific cell. |
| `add_cell` | `file_path`, `index`, `source` (default `""`), `cell_type` (`"code"` or `"markdown"`, default `"code"`) | Insert a new cell at the given index. Pass `index=-1` to append. |
| `delete_cell` | `file_path`, `index` | Remove a cell by index. |
| `move_cell` | `file_path`, `from_index`, `to_index` | Reorder: move a cell from one position to another. |
| `split_cell` | `file_path`, `index`, `line_offset` | Split one cell into two at a line boundary. |
| `merge_cells` | `file_path`, `start_index`, `end_index` | Merge consecutive cells of the same type into one. Code chunks must share a language. |

### Cell content editing

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `replace_cell_source` | `file_path`, `index`, `new_source` | Replace a cell's entire body. For code chunks, language/label/options are preserved. |
| `prepend_to_cell` | `file_path`, `index`, `source` | Add lines to the top of a cell. |
| `append_to_cell` | `file_path`, `index`, `source` | Add lines to the bottom of a cell. |

### Chunk options (labels and `key=value` pairs on code chunks)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `get_chunk_options` | `file_path`, `index` | Return the chunk's language, label, and all options formatted as text. Raises on markdown cells. |
| `set_chunk_option` | `file_path`, `index`, `key`, `value` | Set or overwrite one option. Use `key="label"` to set the chunk label (e.g. `setup`). |
| `remove_chunk_option` | `file_path`, `index`, `key` | Remove one option. Use `key="label"` to clear the chunk label. |

### YAML frontmatter

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `get_frontmatter` | `file_path` | Return the YAML frontmatter as a formatted YAML string. |
| `set_frontmatter_key` | `file_path`, `key`, `value` | Set or overwrite one top-level YAML key. Value is parsed as YAML where possible (so `"true"` → bool, `"42"` → int). |
| `remove_frontmatter_key` | `file_path`, `key` | Remove one top-level YAML key. |

### Discovery (read-only)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `find_in_rmd` | `file_path`, `pattern` | Case-sensitive substring search across all cell sources. Returns `cell[i] line N: <text>` per hit. |

### Kernel execution

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `execute_cell` | `file_path`, `index`, `timeout` (default `60.0`) | Execute one code chunk via a Jupyter kernel. Captured outputs are returned **inline** — never written to the `.rmd` file. |
| `execute_all_cells` | `file_path`, `timeout` (default `60.0`), `stop_on_error` (default `True`) | Execute all code chunks in order. Returns a cell-by-cell transcript. |
| `get_kernel_state` | `file_path` | Report whether this document's kernel is `not started`, `alive`, or `dead`. |
| `restart_kernel` | `file_path` | Restart the kernel. All in-memory state is lost. |
| `interrupt_kernel` | `file_path` | Send a signal to stop a long-running chunk. |
| `shutdown_kernel` | `file_path` | Shut down the kernel and release resources. |

### Kernel lifecycle notes

- The kernel is **started lazily** on the first `execute_cell` / `execute_all_cells` call.
- **One kernel per `.rmd` file path**, cached in memory for the server's lifetime.
- **Runs in the document's folder.** As in Jupyter, the kernel's working directory is the folder that contains the `.rmd` file, so relative paths in chunks (for example `read.csv("data/input.csv")`) resolve against that folder, not the server's install directory. `restart_kernel` keeps the same folder.
- **Kernel chosen by the first chunk run.** The language of the first executed chunk picks the kernelspec: `r` launches IRkernel (`ir`), `python` launches `python3`, `julia` launches `julia-1`, and other languages pass through lowercased as the kernelspec name. Later chunks run in that same kernel whatever their language, so in a mixed-language document call `shutdown_kernel` before running chunks in another language (this discards the kernel's state). The matching Jupyter kernel must be installed on the host.
- **Install IRkernel** (R): in R, run `install.packages("IRkernel"); IRkernel::installspec()`.
- **Outputs are never persisted.** R Markdown regenerates outputs on render (`rmarkdown::render()`), so the server returns outputs inline to the caller only.
- Kernels survive across tool calls: state accumulates across `execute_cell` invocations. Use `restart_kernel` to reset or `shutdown_kernel` to free resources.

### Format notes

- `.rmd` has no cell-boundary markers between adjacent prose blocks (unlike `.ipynb`). Two adjacent `markdown` cells in the model **auto-merge** on save + re-parse. This is expected; prefer inserting prose between code chunks or appending to an existing markdown cell.
- Polyglot chunks (`{python}`, `{bash}`, `{sql}`) parse and round-trip correctly. For execution, the matching Jupyter kernel must be installed.
- Regular markdown code fences (` ```python ` without braces) stay as prose — only ` ```{lang} ` form is treated as a chunk.

## Which tool should I use?

### Discovering what's in a document (do this first)

- **Don't know what's in the document?** → `list_cells`
- **Need to see a chunk's language/label/options?** → `get_chunk_options`
- **Need to see the YAML header?** → `get_frontmatter`
- **Searching for a name or string?** → `find_in_rmd`
- **Need to read a specific cell?** → `get_cell`

### Creating documents

- **Need a new empty `.rmd`?** → `create_rmd` (do NOT hand-write `.rmd` with a generic `Write` tool — `create_rmd` guarantees a valid YAML frontmatter)

### Editing

| Intent | Tool |
| :--- | :--- |
| Add a new cell at a specific position | `add_cell` |
| Remove a cell | `delete_cell` |
| Reorder cells | `move_cell` |
| Break a large cell into two | `split_cell` |
| Combine consecutive same-type cells | `merge_cells` |
| Rewrite a cell's whole body | `replace_cell_source` |
| Add lines to the top of a cell | `prepend_to_cell` |
| Add lines to the bottom of a cell | `append_to_cell` |
| Set a chunk label or option | `set_chunk_option` |
| Remove a chunk label or option | `remove_chunk_option` |
| Set a frontmatter key | `set_frontmatter_key` |
| Remove a frontmatter key | `remove_frontmatter_key` |

### Running chunks

| Intent | Tool |
| :--- | :--- |
| Run one specific chunk | `execute_cell` |
| Re-run the whole document | `execute_all_cells` |
| Stop a stuck chunk | `interrupt_kernel` |
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

For kernel execution, install the matching Jupyter kernel:

- **R:** in R, run `install.packages("IRkernel"); IRkernel::installspec()`. Docs: <https://irkernel.github.io/>
- **Python:** `pip install ipykernel`, then `python -m ipykernel install --user` with the same Python. The second step registers the kernel in your user Jupyter folder, which the server always searches. Without it, the kernelspec stays under that Python's own prefix (for example a Homebrew, pyenv or conda Python), where the server may not find it.
- **Julia:** in Julia, `using Pkg; Pkg.add("IJulia")`.

The server itself depends on `mcp`, `pyyaml`, and `jupyter-client`. `uv` handles all of these automatically on first run.

## Installation

> **Note:** Replace `/absolute/path/to/rmd-editor` below with the absolute path to the `rmd-editor` folder on your machine (the folder that contains its `pyproject.toml`).

### Method 1: CLI Configuration (Claude Code, Codex, Gemini)

If your agent supports adding servers via CLI, run the following:

`--scope user` installs the server globally so it's available in every project on your machine. Drop it if you only want the server active in the current project.

```bash
# Claude Code / Codex
[claude|codex] mcp add rmd-editor --scope user -- uv --directory /absolute/path/to/rmd-editor run rmd-editor-mcp

# Gemini CLI
gemini mcp add --transport stdio --scope user rmd-editor -- uv --directory /absolute/path/to/rmd-editor run rmd-editor-mcp
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
    "rmd-editor": {
      "command": "/absolute/path/to/uv",
      "args": [
        "--directory",
        "/absolute/path/to/rmd-editor",
        "run",
        "rmd-editor-mcp"
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
    "rmd-editor": {
      "command": "/absolute/path/to/uvx",
      "args": [
        "--exclude-newer",
        "7 days",
        "--from",
        "/absolute/path/to/rmd-editor",
        "rmd-editor-mcp"
      ]
    }
  }
}
```

### Using Standard Python (Fallback)

If you prefer not to use `uv`, run the following from the `rmd-editor` folder (the one that contains its `pyproject.toml`), then point to the `.venv` executable it creates. `python3` must be Python 3.10 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install .
```

This path doesn't use uv, so the `[tool.uv]` 7-day dependency cooldown doesn't apply. With pip 26.1 or newer, add `--uploaded-prior-to P7D` to the `pip install` command to apply the same cooldown.

```json
{
  "mcpServers": {
    "rmd-editor": {
      "command": "/absolute/path/to/rmd-editor/.venv/bin/python",
      "args": ["-m", "rmd_editor.server"]
    }
  }
}
```

## Agent Configuration (Important)

Coding agents are heavily biased toward their default tools. You **must** explicitly instruct them to use `rmd-editor` when working with R Markdown documents. The agent prompt lives in [`RMD-EDITOR.md`](./RMD-EDITOR.md) — a standalone file you wire into your agent's system instructions. The server also sends a condensed version of this guidance as MCP server `instructions`, which some clients pass to the model automatically. Wiring in the full prompt file is still recommended.

### Claude Code / Claude Desktop (via `@`-include)

Claude Code supports `@filename` includes in `CLAUDE.md`. Copy the prompt file into your global config directory and add one include line:

```bash
cp /absolute/path/to/rmd-editor/RMD-EDITOR.md ~/.claude/
echo '@RMD-EDITOR.md' >> ~/.claude/CLAUDE.md
```

Or for a single project, place it next to the project's `CLAUDE.md` and add `@RMD-EDITOR.md` there.

### Other agents (Cursor, Codex CLI, Windsurf, Antigravity, Aider, Gemini CLI, etc.)

Copy the **contents** of [`RMD-EDITOR.md`](./RMD-EDITOR.md) into your agent's instruction file (`AGENTS.md`, `.cursor/rules/*.mdc`, `.windsurfrules`, `.github/copilot-instructions.md`, system prompt, etc.). Most non-Claude agents don't support `@`-include — paste the prompt body directly.

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

- **`No such kernel named <name>`** — the Jupyter kernel for the chunk's language isn't installed (`ir` for R chunks, `python3` for Python chunks). To see the kernels the server can find, run `uv --directory /absolute/path/to/rmd-editor run jupyter kernelspec list`. Install the missing one per the Prerequisites section, then run the chunk again; `get_kernel_state` stays `not started` after this error, so the server doesn't need a restart.
- **"Kernel failed to start"** — the kernelspec exists but the kernel couldn't be launched (for example, its command points to an R installation that has moved), or it started but died or didn't become ready within 30 seconds. The message includes the underlying error. Check that the kernel's own runtime works (for example, that R starts and loads IRkernel), then retry. `restart_kernel` reports the same kinds of problems as **"Kernel failed to restart"**.
- **"File is not a .rmd document"** — every tool validates the extension. Rename your file to `.rmd` or use [`jupytext`](https://jupytext.readthedocs.io/) to convert `.Rmd` ↔ `.ipynb`.
- **Outputs aren't appearing in the file** — by design. Outputs are returned inline to the caller. To persist, render with `rmarkdown::render("file.rmd")`.
- **Adjacent markdown cells merged after a save** — by design. `.rmd` has no cell-boundary markers for prose; the model collapses consecutive markdown cells on re-parse.

## Tool count

**24 tools** total:

- 1 document creation (`create_rmd`)
- 7 cell structure & navigation (`list_cells`, `get_cell`, `add_cell`, `delete_cell`, `move_cell`, `split_cell`, `merge_cells`)
- 3 cell content editing (`replace_cell_source`, `prepend_to_cell`, `append_to_cell`)
- 3 chunk options (`get_chunk_options`, `set_chunk_option`, `remove_chunk_option`)
- 3 YAML frontmatter (`get_frontmatter`, `set_frontmatter_key`, `remove_frontmatter_key`)
- 1 discovery (`find_in_rmd`)
- 2 execution (`execute_cell`, `execute_all_cells`)
- 4 kernel lifecycle (`get_kernel_state`, `restart_kernel`, `interrupt_kernel`, `shutdown_kernel`)
