# AST Code Editor MCP Server

A robust, language-agnostic Model Context Protocol (MCP) server that provides AI coding agents with the ability to edit files surgically via Abstract Syntax Trees (AST) instead of relying on token-heavy, brittle search-and-replace or diff operations.

## Why AST Edits?

Every major AI coding tool makes a different bet on how models should express code edits: [Claude Code](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool) uses search/replace, [Codex CLI](https://developers.openai.com/api/docs/guides/tools-apply-patch) uses patch diffs, [Cursor](https://cursor.com/blog/instant-apply) rewrites the entire file, and [Aider](https://aider.chat/docs/more/edit-formats.html) picks per model. None of them use AST-targeted edits.

[Geometric AGI tested all of them](https://geometricagi.github.io/2026/04/02/ast-edits.html). **AST won.**

### The Benchmark

They built 29 editing tasks ranging from one-line fixes in 100-line files to multi-site rewrites in 4,200-line modules, tested across 7 edit formats and 4 models (Claude Haiku 4.5, OpenAI o4-mini, GPT-5.4, Claude Opus 4.6).

### Key Findings

- **AST edit is the only format that hits 100% correctness on 3 out of 4 models.** Only "whole file rewrite" comes close.
- **Whole file rewrite uses 18x more output tokens and takes 12x longer** than AST edit on a 4,200-line file.
- **AST edit has zero format failures across all 4 models.** The JSON always parses, the function names always resolve. The only failures (4, all on Haiku) were logic errors where the model got the code change itself wrong, not the format.
- **Unified diff is the riskiest choice** — it scores 93.1% on Opus but crashes to 20.7% on o4-mini due to context line mismatches and hunk header errors.
- **Search/replace fails** when the model reproduces old code with slightly wrong whitespace, or when the search string matches multiple locations in large files.
- **Picking the right format can matter more than picking the right model.** o4-mini goes from 100% (AST) down to 20.7% (unified diff).

### Why Other Formats Fail

All non-AST formats share the same fundamental flaw: **the model has to copy text perfectly from a file it saw once.** On a 4,200-line file, one whitespace mismatch in a context line tanks the whole edit. AST edit sidesteps this entirely — the model just names the function (e.g., `LRUCache.get`) and provides the new code. The parser figures out where it lives in the file.

### Credits

This MCP server was inspired by research from [Jack Foxabbott](https://www.linkedin.com/in/foxabbott/) and the team at [Geometric AGI](https://geometricagi.github.io/), who benchmarked AST-targeted edits against every major code editing format and demonstrated its superiority across models and file sizes. Their full findings, benchmark suite, and code are available here:

- [AST Edits: The Code Editing Format Nobody Uses](https://geometricagi.github.io/2026/04/02/ast-edits.html) (Blog)
- [Jack Foxabbott's original post](https://www.linkedin.com/posts/foxabbott_i-didnt-know-until-recently-that-all-the-share-7445506956783480832-dcXr/) (LinkedIn)
- [GeometricAGI/blog](https://github.com/GeometricAGI/blog) (Benchmark code & data)

## Supported Languages

- Python (`.py`)
- JavaScript (`.js`, `.jsx`, `.cjs`, `.mjs`)
- TypeScript (`.ts`, `.tsx`)
- JSON (`.json`)
- YAML (`.yml`, `.yaml`)
- TOML (`.toml`)

## Tools Exposed

All tools require `file_path` to be an **absolute path** to an existing file.

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `replace_function` | `file_path`, `target`, `content` | Replace an entire function definition — including signature, decorators, and body — with new content. |
| `replace_function_body` | `file_path`, `target`, `content` | Replace only the body of a function, preserving its signature and decorators. |
| `add_method` | `file_path`, `class_target`, `content` | Add a new method to the end of a class block. |
| `delete_node` | `file_path`, `target` | Delete an entire function or class definition block (including decorators). |
| `replace_value` | `file_path`, `target`, `content` | For config files only (JSON, YAML, TOML). `target` is the dotted key path (e.g., `dependencies.mcp`). |

**Target format:** Use the exact function name (e.g., `get`) or dotted `Class.method` path (e.g., `LRUCache.get`). Decorated Python functions are fully supported — decorators are included when replacing or deleting the full function.

## Logging & Debugging

The server logs all tool invocations and errors to **stderr** (safe for stdio transport — does not interfere with JSON-RPC). Logs include timestamps and severity levels.

To inspect logs when running under Claude Desktop, check `~/Library/Logs/Claude/mcp*.log` (macOS) or `%APPDATA%\Claude\logs\mcp*.log` (Windows).

For interactive testing, use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector).

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

## Installation

> **Note:** Replace `/absolute/path/to` below with the actual path to this repository on your machine.

### Method 1: CLI Configuration (Claude Code, Codex, Gemini)

If your agent supports adding servers via CLI, run the following:

**Claude Code / Codex CLI / Gemini CLI:**

```bash
# Claude Code / Codex
[claude|codex] mcp add ast-editor -- uv --directory /absolute/path/to/mcp-servers/ast-editor run ast-editor-mcp

# Gemini CLI
gemini mcp add --transport stdio ast-editor -- uv --directory /absolute/path/to/mcp-servers/ast-editor run ast-editor-mcp
```

### Method 2: JSON Configuration

For tools that use a `mcp_config.json` or `settings.json` file, add the following block to the appropriate file path:

```json
{
  "mcpServers": {
    "ast-editor": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-servers/ast-editor",
        "run",
        "ast-editor-mcp"
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
cd mcp-servers/ast-editor && python3 -m venv .venv && source .venv/bin/activate && pip install .
```

```json
{
  "mcpServers": {
    "ast-editor": {
      "command": "/absolute/path/to/mcp-servers/ast-editor/.venv/bin/python",
      "args": ["-m", "ast_editor.server"]
    }
  }
}
```

## Agent Configuration (Important)

Coding agents are heavily biased toward their default tools. You **must** explicitly instruct them to use AST tools.

### Claude (Code & Desktop)

Add to `CLAUDE.md`, `~/.claude/CLAUDE.md`, or **Custom Instructions**:

> *When editing `.py`, `.js`, or `.ts` files, do NOT use the `edit` tool. Instead, use the AST editing MCP tools (`replace_function_body`, `replace_function`, `add_method`) from the `ast-editor` server. When modifying `.json`, `.yaml`, or `.toml` files, use `replace_value` instead of `edit`.*

### Specific Tool Overrides

| Agent | Target Instructions / File | Instruction |
| :--- | :--- | :--- |
| **Cursor** | `.cursorrules` / Settings | ...do NOT use `edit_file`. Use AST tools (`replace_function_body`, etc.) instead. |
| **Codex CLI** | `copilot-instructions.md` | ...do NOT use `apply-patch`. Use AST tools instead. |
| **Windsurf** | `.windsurfrules` / `AGENTS.md` | ...do NOT use Cascade's built-in write mode. Use AST tools instead. |
| **Antigravity** | `_agents/rules/` | ...do NOT use `write_to_file`, `replace_file_content`, or `multi_replace_file_content`. Use AST tools instead. |

### Generic / Aider / Gemini CLI

Add to rules or system prompt:

> *When editing `.py`, `.js`, or `.ts` files, do NOT use your default editing tools (diff, whole, etc.). Instead, use the AST editing MCP tools (`replace_function_body`, `replace_function`, `add_method`, `delete_node`) to make surgical, syntax-aware edits. For configuration files (`.json`, `.yaml`, `.toml`), use `replace_value` with dotted key paths.*
