# AST Code Editor MCP Server

A robust, language-agnostic Model Context Protocol (MCP) server that provides AI coding agents with the ability to edit files surgically via Abstract Syntax Trees (AST) instead of relying on token-heavy, brittle search-and-replace or diff operations.

## Why AST Edits?

Every non-AST edit format — search/replace, unified diff, whole-file rewrite — requires the model to copy text *perfectly* from a file it saw once. One whitespace mismatch on a 4,000-line file and the edit fails. AST edits sidestep the problem entirely: the model names the target (e.g., `LRUCache.get`) and provides the new code; the parser figures out where it lives.

Geometric AGI benchmarked every major format across 4 models and 29 edit tasks. **AST edits were the only format to hit 100% correctness on 3 of 4 models, with 18x fewer output tokens than whole-file rewrite, and zero format failures.** Full methodology and results: [AST Edits: The Code Editing Format Nobody Uses](https://geometricagi.github.io/2026/04/02/ast-edits.html).

### Credits

This MCP server was inspired by research from [Jack Foxabbott](https://www.linkedin.com/in/foxabbott/) and the team at [Geometric AGI](https://geometricagi.github.io/). Their full findings, benchmark suite, and data are available here:

- [AST Edits: The Code Editing Format Nobody Uses](https://geometricagi.github.io/2026/04/02/ast-edits.html) (Blog)
- [Jack Foxabbott's original post](https://www.linkedin.com/posts/foxabbott_i-didnt-know-until-recently-that-all-the-share-7445506956783480832-dcXr/) (LinkedIn)
- [GeometricAGI/blog](https://github.com/GeometricAGI/blog) (Benchmark code & data)

## Estimated Token Savings

Per-edit output token savings versus other common edit formats:

| Edit size | File size | vs whole-file rewrite | vs unified diff | vs search/replace |
| :--- | :--- | :--- | :--- | :--- |
| 1-line tweak | 100 LoC | 3–5x | ~1.5x | ~1.5x |
| Function body rewrite | 500 LoC | 8–12x | 2–3x | 2–3x |
| Function body rewrite | 4,000 LoC | **15–20x** | 3–5x | 3–5x |
| Add 2 lines to a function | any size | **~20x** (via `prepend_to_body` / `append_to_body`) | 5–10x | 3–5x |

**For daily agent users, a realistic 40–60% reduction in total tokens per session is achievable, on average** (combining output savings from surgical edits with input savings from targeted reads).

The savings come from four compounding effects:

- **Output tokens:** Using `prepend_to_body` / `append_to_body` for small additions instead of rewriting whole function bodies
- **Input tokens:** Using `read_symbol` / `read_interface` / `read_imports` to read only what's needed instead of entire files (~10-20x fewer input tokens per read)
- **Discovery:** `list_symbols` / `get_signature` instead of reading whole files
- **Zero format failures:** AST edits never fail on whitespace drift, eliminating retry loops that plague other formats.

## Supported Languages & Capabilities

| Language | Extensions | Structural edits | Comments | Docstrings | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Python** | `.py` | ✅ | ✅ `#` | ✅ function/class | Decorators preserved. Module-level `dict`/`list` literals editable via `add_key` / `append_to_array`. |
| **JavaScript** | `.js`, `.jsx`, `.mjs`, `.cjs` | ✅ | ✅ `//` + `/* ... */` | — | |
| **TypeScript** | `.ts`, `.tsx` | ✅ | ✅ `//` + `/* ... */` | — | Interfaces are treated as classes for `add_method` / `add_field`. |
| **C** | `.c`, `.h` | ✅ | ✅ `//` + `/* ... */` (single + multi-line) | — | `.h` defaults to C — use `.hpp`/`.hxx`/`.hh` for C++ headers. |
| **C++** | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx`, `.hh` | ✅ | ✅ `//` + `/* ... */` (single + multi-line) | — | Supports `class`, `struct`, `union`, `enum`, `namespace`; `Class::method` qualified names resolve correctly. |
| **Ruby** | `.rb` | ✅ | ✅ `#` | — | Classes, modules, instance methods, `singleton_method` (class methods via `def self.foo`). `require`/`require_relative`/`load`/`autoload` recognized as imports. |
| **Go** | `.go` | ✅ | ✅ `//` + `/* ... */` | — | `struct`, `interface`, functions, methods. Methods are addressed by receiver: `Cache.Get` resolves to the top-level `func (c *Cache) Get(...)`. Grouped `import (...)` blocks supported. |
| **Java** | `.java` | ✅ | ✅ `//` + `/* ... */` + Javadoc `/** ... */` | — | `class`, `interface`, `enum`, `record`; methods, constructors, fields. Annotations (`@Override`, `@Deprecated`) travel with their method on edits (wrapped in the `modifiers` node). Enum methods (nested in `enum_body_declarations`) discovered via BFS in `list_symbols`. |
| **JSON** | `.json` | ✅ (keys, values, arrays) | — (no comment syntax) | — | |
| **YAML** | `.yml`, `.yaml` | ✅ (keys, values, sequences) | ✅ `#` | — | Block and flow sequences supported. |
| **TOML** | `.toml` | ✅ (keys, values, arrays, tables) | ✅ `#` | — | `[table]` headers addressable by name for comment tools. |

**Cross-cutting features:**

- **Decorated functions** (Python `@decorator`): decorators are preserved on body/signature edits and included on delete.
- **Byte-correct slicing**: multi-byte characters (emoji, `═`, `→`) handled safely in source text.
- **Idempotent imports**: `add_import` skips exact duplicates automatically.

### Language-specific design decisions

A few tools have language-specific semantics where multiple reasonable interpretations exist. The chosen behavior is documented here for transparency:

**`add_field` (Ruby and Go) — option (a): literal text passthrough**

- **Ruby:** `add_field("LRUCache", "  attr_accessor :capacity")` inserts the literal string at the top of the class body. The tool does **not** auto-wrap bare names in `attr_accessor` — you provide the exact text you want (whether that's `attr_accessor`, `attr_reader`, `@instance_var = nil` in `initialize`, or `CLASS_CONST = 42`).
- **Go:** `add_field("Cache", "\tversion int")` inserts the literal string inside the `struct { ... }` body. The tool does **not** infer types from bare names — you provide the full Go field declaration.
- **Rationale:** consistent with how `add_field` works for other languages (Python, JS/TS, C++) where the caller provides the full source text. The alternative option (b) — auto-wrapping (e.g. `attr_accessor :foo` from the name `foo`) — would be more magical but harder to use for edge cases (typed fields, readonly fields, field with default value, etc.).

**`add_method` (Go) — option (a): top-level sibling insertion**

- `add_method("Cache", "func (c *Cache) Has(key string) bool { ... }")` locates the `type Cache struct { ... }` declaration and inserts the new method **immediately after it, at the top level** (not inside the struct's braces).
- **Rationale:** Go methods are lexically top-level, not nested inside their receiver type — this matches how Go code is actually written. The alternative option (b) — refusing because "Go methods aren't inside structs" — would be pedantically correct but force callers to use `insert_after("Cache", content)` instead, which loses the semantic signal that this is a method addition.

## Tools Exposed

All tools require `file_path` to be an **absolute path** to an existing file.

### Code editing — structural (Python, JS, TS, C, C++, Ruby, Go, Java)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `replace_function` | `file_path`, `target`, `content` | Replace a full function definition (signature + body + decorators). |
| `replace_function_body` | `file_path`, `target`, `content` | Replace only the body of a function, preserving signature and decorators. |
| `replace_signature` | `file_path`, `target`, `new_signature` | Replace only the signature, preserving body and decorators. |
| `prepend_to_body` | `file_path`, `target`, `content` | Insert content at the top of a function body. |
| `append_to_body` | `file_path`, `target`, `content` | Insert content at the bottom of a function body. |
| `add_top_level` | `file_path`, `content` | Append any top-level content (function, class, constant, type alias) to the end of the file. |
| `add_method` | `file_path`, `class_target`, `content` | Add a method at the end of a class body. |
| `add_field` | `file_path`, `class_target`, `content` | Add a field/attribute/member at the top of a class body. |
| `insert_before` | `file_path`, `target`, `content` | Insert a sibling immediately before a named symbol. |
| `insert_after` | `file_path`, `target`, `content` | Insert a sibling immediately after a named symbol. |
| `delete_symbol` | `file_path`, `target` | Delete a function or class definition block (including decorators). |

### Parameters & signatures

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `add_parameter` | `file_path`, `target`, `parameter`, `position` | Add a parameter to a function signature (`position`: `"start"` or `"end"`). |
| `remove_parameter` | `file_path`, `target`, `parameter_name` | Remove a parameter by name. |

### Imports & includes

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `add_import` | `file_path`, `import_text` | Add an `import`/`from`/`#include` line. Skips duplicates. |
| `remove_import` | `file_path`, `import_text` | Remove a matching import line. |
| `add_import_name` | `file_path`, `module`, `name` | Add one name to an existing `from <module> import a, b`. Python-only. |
| `remove_import_name` | `file_path`, `module`, `name` | Remove one name from a multi-name Python from-import. |

### Comments & docstrings

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `add_comment_before` | `file_path`, `target`, `comment` | Insert a comment block immediately before a named symbol. Works for Python/Ruby/YAML/TOML (`#`), JS/TS/C/C++/Go/Java (`//` or `/* */`; Java Javadoc `/** */` supported). |
| `remove_leading_comment` | `file_path`, `target` | Remove the contiguous comment block above a symbol. Recognizes both line comments and C-style single-line or multi-line `/* ... */` blocks. |
| `replace_leading_comment` | `file_path`, `target`, `new_comment` | Replace the leading comment block above a symbol (or insert one if none exists). |
| `replace_docstring` | `file_path`, `target`, `new_docstring` | Replace or insert a Python function/class docstring. Python-only. |

### Dict/list editing (JSON, YAML, TOML, AND Python module-level dict/list literals)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `replace_value` | `file_path`, `target`, `content` | Replace the value of an existing config key. `target` is the dotted key path. |
| `add_key` | `file_path`, `parent_target`, `key`, `value` | Add a key-value pair to a dict/object/mapping/table. For Python, `parent_target` is the dict variable name; for config, a dotted path (use `""` for root). |
| `delete_key` | `file_path`, `target` | Delete a key-value pair. For Python, target is `DictName.keyExpr`. For JSON, also removes the adjacent comma. |
| `append_to_array` | `file_path`, `target`, `value` | Append a literal value to a list/array/sequence. For Python, `target` is the list variable name; for config, a dotted path. |
| `remove_from_array` | `file_path`, `target`, `value_match` | Remove the first matching element from a list/array/sequence. |

### Navigation & reading (read-only)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_symbols` | `file_path` | Formatted outline of all top-level functions, classes, and methods with line numbers. |
| `get_signature` | `file_path`, `target` | Return the signature of a function as plain text. |
| `find_references` | `file_path`, `target` | Syntactic search for all occurrences of an identifier (no scope awareness). |
| `read_symbol` | `file_path`, `target` | Return the full source text of a single named symbol (function, class, method, config key). Typically **10-20x fewer tokens** than reading the whole file. |
| `read_imports` | `file_path` | Return all import/include statements in the file. |
| `read_interface` | `file_path`, `target` | Return a stub view of a class: header, field declarations, and method signatures with bodies replaced by `...`. For Go, includes receiver method signatures. For a function target, returns just its signature. |

**Target format:** Use the exact function name (e.g., `get`) or dotted `Class.method` path (e.g., `LRUCache.get`). Decorated Python functions are fully supported — decorators are preserved when replacing bodies or signatures, and included when deleting or replacing the full function.

**Tip:** Call `list_symbols` first to discover exact target names before editing. This avoids guessing and makes subsequent edits much more reliable.

## Which tool should I use?

A decision guide grouped by intent. Start at the top and pick the narrowest match.

### Discovering what's in a file (do this first)

- **Don't know what symbols exist?** → `list_symbols`
- **Need just a function's signature?** → `get_signature`
- **Need one specific function's full source?** → `read_symbol` (10-20x cheaper than reading the whole file)
- **Need a class's public API (methods + fields, no bodies)?** → `read_interface`
- **Need to see a file's imports/dependencies?** → `read_imports`
- **Where is a symbol used?** → `find_references`

### Adding new content

| Intent | Tool |
| :--- | :--- |
| New top-level function, class, constant, or type alias | `add_top_level` |
| New method in an existing class | `add_method` |
| New field/attribute/member in a class | `add_field` |
| New content at a specific position relative to an existing symbol | `insert_before` / `insert_after` |
| New lines at the top of an existing function body | `prepend_to_body` |
| New lines at the bottom of an existing function body | `append_to_body` |
| New parameter on an existing function | `add_parameter` |
| New import or `#include` | `add_import` |
| New name in an existing `from X import …` | `add_import_name` |
| New comment above a symbol | `add_comment_before` |
| New Python docstring on a function/class | `replace_docstring` |
| New key in a dict/object/mapping/table (any lang) | `add_key` |
| New item in a list/array/sequence (any lang) | `append_to_array` |

### Modifying existing content

| Intent | Tool |
| :--- | :--- |
| Rewrite the full function (signature + body) | `replace_function` |
| Rewrite only the body, keep the signature | `replace_function_body` |
| Change only the signature, keep the body | `replace_signature` |
| Change only the leading comment above a symbol | `replace_leading_comment` |
| Change only the Python docstring | `replace_docstring` |
| Change the value of an existing config key | `replace_value` |

### Removing content

| Intent | Tool |
| :--- | :--- |
| Remove a function, method, or class | `delete_symbol` |
| Remove a parameter from a function | `remove_parameter` |
| Remove an import or `#include` | `remove_import` |
| Remove one name from a multi-name Python from-import | `remove_import_name` |
| Remove a leading comment above a symbol | `remove_leading_comment` |
| Remove a key from a dict/config | `delete_key` |
| Remove an item from a list/array | `remove_from_array` |

### Anti-patterns to avoid

- **Don't use `replace_function` to add a few lines** — use `prepend_to_body` or `append_to_body` instead. Rewriting the whole function is wasteful and error-prone.
- **Don't use `replace_function_body` to add a few lines** either — same reasoning. Use `prepend_to_body`/`append_to_body`.
- **Don't use `replace_signature` to add or remove one parameter** — use `add_parameter`/`remove_parameter`.
- **Don't use `replace_value` to add a new key** — use `add_key`. `replace_value` only updates existing keys.
- **Don't use `add_import` to add a name to an existing `from X import …`** — use `add_import_name`.
- **Don't guess at target names.** Call `list_symbols` first. Names are case-sensitive and must match exactly.

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

`--scope user` installs the server globally so it's available in every project on your machine. Drop it if you only want the server active in the current project.

```bash
# Claude Code / Codex
[claude|codex] mcp add ast-editor --scope user -- uv --directory /absolute/path/to/mcp-servers/ast-editor run ast-editor-mcp

# Gemini CLI
gemini mcp add --transport stdio --scope user ast-editor -- uv --directory /absolute/path/to/mcp-servers/ast-editor run ast-editor-mcp
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

Add the following block to `CLAUDE.md`, `~/.claude/CLAUDE.md`, or **Custom Instructions**:

> **When editing `.py`, `.js`, `.ts`, `.c`, `.cpp`, `.rb`, `.go`, `.java`, `.json`, `.yaml`, or `.toml` files, do NOT use the `edit` tool. Use the `ast-editor` MCP server instead. It exposes 32 surgical tools for structural code and config edits.**
>
> **Picking a tool — always start here:**
>
> 1. **Unsure of the file layout?** Call `list_symbols` first. Call `get_signature` if you only need a signature. Call `read_symbol` to read one function/class without reading the whole file. Call `read_interface` to see a class's API (methods + fields, no bodies). Call `read_imports` to see dependencies. Call `find_references` before renaming anything.
> 2. **Adding new content** — choose the narrowest tool:
>    - Top-level (function, class, constant, type alias): `add_top_level`
>    - In a class: `add_method`, `add_field`
>    - Inside a function body: `prepend_to_body`, `append_to_body`
>    - Relative to an existing symbol: `insert_before`, `insert_after`
>    - Imports: `add_import` (new line) or `add_import_name` (add to existing `from X import …`)
>    - Parameters: `add_parameter`
>    - Comments/docstrings: `add_comment_before`, `replace_docstring`
>    - Any dict (config OR Python literal): `add_key`
>    - Any list/array (config OR Python literal): `append_to_array`
> 3. **Modifying existing content:**
>    - Full function: `replace_function`
>    - Body only: `replace_function_body`
>    - Signature only: `replace_signature`
>    - Config value: `replace_value`
>    - Leading comment: `replace_leading_comment`
>    - Python docstring: `replace_docstring`
> 4. **Removing content:**
>    - Function/class/method: `delete_symbol`
>    - Parameter: `remove_parameter`
>    - Import: `remove_import` (whole line) or `remove_import_name` (one name)
>    - Leading comment: `remove_leading_comment`
>    - Dict key or list item: `delete_key`, `remove_from_array`
>
> **Anti-patterns to avoid:**
>
> - Don't use `replace_function` or `replace_function_body` to add a couple of lines — use `prepend_to_body` / `append_to_body`.
> - Don't use `replace_signature` to add one parameter — use `add_parameter` / `remove_parameter`.
> - Don't use `replace_value` to add a new key — use `add_key`.
> - Don't use `add_import` to add a name to an existing from-import — use `add_import_name`.
> - Don't guess target names — call `list_symbols` first. Names are case-sensitive.

### Specific Tool Overrides

| Agent | Target Instructions / File | Instruction |
| :--- | :--- | :--- |
| **Any agent that reads `AGENTS.md`** (recommended universal option) | `AGENTS.md` at repo root | Drop the Claude instruction block above into `AGENTS.md`. Read by Codex CLI, Windsurf, Zed, Cursor (as secondary), and a growing list of others. |
| **Cursor** | `.cursor/rules/*.mdc` (current) or `AGENTS.md` — legacy: `.cursorrules` | ...do NOT use `edit_file`. Use AST tools (`replace_function_body`, etc.) instead. |
| **Codex CLI** (OpenAI) | `AGENTS.md` at repo root | ...do NOT use `apply-patch`. Use AST tools instead. |
| **GitHub Copilot** (VS Code / JetBrains) | `.github/copilot-instructions.md` | ...do NOT use inline suggestions for structural edits. Use AST tools from the `ast-editor` MCP server. |
| **Windsurf** | `.windsurfrules` or `AGENTS.md` | ...do NOT use Cascade's built-in write mode. Use AST tools instead. |
| **Antigravity** | `_agents/rules/` | ...do NOT use `write_to_file`, `replace_file_content`, or `multi_replace_file_content`. Use AST tools instead. |

### Generic / Aider / Gemini CLI

Add to rules or system prompt:

> *When editing `.py`, `.js`, `.ts`, `.c`, `.cpp`, `.rb`, `.go`, or `.java` files, do NOT use your default editing tools (diff, whole, etc.). Instead, use the `ast-editor` MCP server, which exposes 32 surgical tools for adding/modifying/removing functions, classes, methods, fields, parameters, imports, comments, and docstrings. Start any edit session by calling `list_symbols` to discover exact target names. **For reading, use `read_symbol` to read one function/class (~10-20x fewer input tokens than reading the whole file), `read_interface` for a class's API (signatures only, no bodies), or `read_imports` for dependencies.** For small additions to a function body (logging, validation, cleanup), use `prepend_to_body` / `append_to_body` — these are the single biggest output-token-saving tools in the suite, giving ~20x fewer output tokens than rewriting the whole body. For `.json`, `.yaml`, or `.toml` files, use `replace_value`/`add_key`/`append_to_array`/`delete_key` instead of freeform edits.*
