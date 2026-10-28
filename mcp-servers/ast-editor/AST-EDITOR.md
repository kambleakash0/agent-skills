# AST Editor MCP Server

When editing `.py`, `.js`, `.ts`, `.c`, `.cpp`, `.rb`, `.go`, `.java`, `.json`, `.yaml`, or `.toml` files, do NOT use the `edit` tool. Use the `ast-editor` MCP server: its 28 tools edit code and config by symbol name.

The README (https://github.com/kambleakash0/agent-skills/tree/main/mcp-servers/ast-editor) has the full reference.

**Picking a tool - always start here:**

1. **Find the target.** Call `list_symbols` first: every name it lists is a target (`Class.method`, `A.B.m`, fields and variables too). Names are case-sensitive.
   - C, C++ and Java overloads take their parameter types (`A.m(int, String)`, `A.m()`); a C++ definition outside its class is `A::f`. A struct, union, enum or class, or a TS `type` or `interface`, that shares its name with another symbol takes its keyword (`struct stat`, `type User`). In C++ and Java a method sharing a field's name is `A.x()` (the plain name is the field); in JS/TS the method is `A.x`.
   - `read_symbol(target)` returns exactly what `replace_function` replaces (decorators, `export` and a C++ `template <...>` header included): edit it and pass it back as is. `depth="interface"` gives a class's API, `depth="signature"` a signature. `read_imports` lists imports; call `find_references` before a rename.
   - Dotted targets reach closures (`app.handler`, Go `cmd.RunE`). A JS/TS `const f = (x) => {...}` is function `f`; function tools also take a Go `var f = func() {...}`.
   - **Config files (JSON/YAML/TOML):** a target is the key path from the top level (`project.version`). Put a key with dots in double quotes: `"editor.fontSize"`, `a."b.c".d`. Array elements are not addressable. Edit keys with `replace_value`, `delete_key`, `add_key`.
2. **Adding content** - choose the narrowest tool:
   - Top-level code: `add_top_level` (`position="top"` goes after the imports and preamble).
   - In a class: `add_method` (after the last member) or `add_field` (before the first).
   - In a function body: `insert_in_body(at="top"|"bottom")`, or `insert_in_body(after=...)` / `insert_in_body(before=...)` next to an existing snippet.
   - Next to a symbol: `insert_sibling(position="before"|"after")`.
   - Imports: `add_import` (a whole line, into its group, at its sorted place) or `add_import_name` (one name into an existing `from X import ...` or `import { a } from "mod"`).
   - Parameters: `add_parameter` (`position="end"` or `"start"`).
   - Leading comment: `edit_leading_comment(op="add", comment=...)`.
   - Python docstring: `replace_docstring`, the string with its quotes (`'"""Summary."""'`); `target=""` is the module.
   - Dict or object entry (config, Python or JS/TS literal): `add_key` (`parent_target=""` is a config file's root). List item: `append_to_array`.
3. **Modifying content:**
   - A few lines in a body: `replace_in_body(target, old_snippet, new_snippet)`, the biggest token saver.
   - Whole function: `replace_function`. Body only: `replace_function_body`. Signature only: `replace_signature`.
   - Value of a key, variable, constant, field or macro: `replace_value`.
   - Leading comment: `edit_leading_comment(op="replace")`. Docstring: `replace_docstring`.
   - **Snippets and anchors** (`replace_in_body`, `delete_in_body`, `insert_in_body` after/before) match their exact text at token boundaries (`x = 1` is not found in `max = 10`), or else whole lines with their indentation shifted. They must match one place; if several match, add context.
4. **Removing content:**
   - Function, class or method: `delete_symbol` (its leading doc comment goes too unless `include_leading_comments=False`).
   - Lines in a body: `delete_in_body(target, snippet)`.
   - Others: `remove_parameter`, `remove_import` (whole line), `remove_import_name` (one name), `edit_leading_comment(op="remove")`, `delete_key`, `remove_from_array`.

**Anti-patterns to avoid:**

- Don't use `replace_function` or `replace_function_body` to change a few lines: use `replace_in_body` or `insert_in_body`.
- Don't use `replace_signature` to add or remove one parameter: use `add_parameter` / `remove_parameter`.
- Don't use `replace_value` to add a new key: use `add_key`.
- Don't use `add_import` to add a name to an existing import: use `add_import_name`.

**Safety nets:**

- Every edit is parse-checked. One that would add a syntax error is refused with its line and column, and the file is left unchanged: fix the content and retry. If the code is valid but the parser does not support it (very new syntax, macro-heavy C/C++), use your normal edit tool.
- Line endings, a UTF-8 byte order mark and a missing final newline are kept, and tab-indented code gets tabs.

**Escape hatches:**

- Deleting several symbols: call `delete_symbol` once per target. There is no `delete_group` tool.
- Editing a sub-expression inside a method chain: try `replace_in_body` with the literal snippet; for arbitrary expression edits use your normal `Edit` tool.
- Rewriting most of a file: use your normal `Write` tool.
