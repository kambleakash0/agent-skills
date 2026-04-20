# AST Editor MCP Server

When editing `.py`, `.js`, `.ts`, `.c`, `.cpp`, `.rb`, `.go`, `.java`, `.json`, `.yaml`, or `.toml` files, do NOT use the `edit` tool. Use the `ast-editor` MCP server instead. It exposes 28 surgical tools for structural code and config edits. Refer to the available tools below.

**Picking a tool — always start here:**

1. **Unsure of the file layout?** Call `list_symbols` first. Call `read_symbol(target)` to read one function/class's full source without reading the whole file. Call `read_symbol(target, depth="interface")` for a class's API (methods + fields, no bodies) or for a function's signature. Call `read_symbol(target, depth="signature")` for signature-only. Call `read_imports` to see dependencies. Call `find_references` before renaming anything. Dotted targets descend into closures: Go `stdioCmd.RunE` (func_literal in struct field), JS/TS `app.handler` (arrow function in object literal).
2. **Adding new content** — choose the narrowest tool:
   - Top-level (function, class, constant, type alias): `add_top_level` (use `position="top"` to prepend after preamble)
   - In a class: `add_method`, `add_field`
   - At top of a function body: `insert_in_body(at="top")`
   - At bottom of a function body: `insert_in_body(at="bottom")`
   - At a specific spot inside a function body (anchored to an existing snippet): `insert_in_body(after=...)` or `insert_in_body(before=...)`
   - Relative to an existing top-level symbol: `insert_sibling(position="before"|"after")`
   - Imports: `add_import` (new line) or `add_import_name` (add to existing `from X import ...` or `import { a, b } from "mod"`)
   - Parameters: `add_parameter`
   - Leading comment: `edit_leading_comment(op="add", comment=...)`
   - Python docstring: `replace_docstring`
   - Any dict/object (config OR Python/JS/TS literal): `add_key`
   - Any list/array (config OR Python literal): `append_to_array`
3. **Modifying existing content:**
   - Full function: `replace_function`
   - Body only: `replace_function_body`
   - One statement/block inside a large body: `replace_in_body(target, old_snippet, new_snippet)` — scoped match; the single biggest token-saver for long functions
   - Signature only: `replace_signature`
   - Config value: `replace_value`
   - Leading comment: `edit_leading_comment(op="replace", comment=...)`
   - Python docstring: `replace_docstring`
4. **Removing content:**
   - Function/class/method: `delete_symbol` (consumes the leading doc comment by default; pass `include_leading_comments=False` to keep it)
   - One statement/line inside a function body: `delete_in_body(target, snippet)` — scoped match; use for single-line removals (route mounts, middleware calls, object-literal keys in inline args)
   - Parameter: `remove_parameter`
   - Import: `remove_import` (whole line) or `remove_import_name` (one name from multi-name)
   - Leading comment: `edit_leading_comment(op="remove")`
   - Dict/object key or list item: `delete_key`, `remove_from_array`

**Anti-patterns to avoid:**

- Don't use `replace_function` or `replace_function_body` to change a few lines — use `replace_in_body` (scoped snippet match) or `insert_in_body(at="top"|"bottom")` for prepend/append.
- Don't use `replace_signature` to add one parameter — use `add_parameter` / `remove_parameter`.
- Don't use `replace_value` to add a new key — use `add_key`.
- Don't use `add_import` to add a name to an existing from-import or named import — use `add_import_name`.
- Don't guess target names — call `list_symbols` first. Names are case-sensitive.

**Escape hatches — when to step outside ast-editor:**

- **Deleting multiple related symbols as a group?** Call `delete_symbol` once per target. There's no `delete_group` tool; the extra tool calls are cheaper than the alternative of a custom grouped primitive.
- **Editing a sub-expression inside a method chain** (e.g. dropping `.references(...)` from `integer("x").notNull().references(...)`) or other arbitrary expression surgery? For common cases use `replace_in_body` with the literal snippet. For truly arbitrary sub-expression edits, fall back to the default `Edit` tool — ast-editor intentionally doesn't do AST pattern matching on expression trees.
- **Rewriting a whole file where the structure changes substantially?** Use the default `Write` tool. ast-editor is for targeted edits; duplicating `Write` as a tool here would add no value.
