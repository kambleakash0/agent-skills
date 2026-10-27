# AST Editor MCP Server

When editing `.py`, `.js`, `.ts`, `.c`, `.cpp`, `.rb`, `.go`, `.java`, `.json`, `.yaml`, or `.toml` files, do NOT use the `edit` tool. Use the `ast-editor` MCP server instead. It exposes 28 surgical tools for structural code and config edits. Refer to the available tools below.

**Picking a tool — always start here:**

1. **Unsure of the file layout?** Call `list_symbols` first. Call `read_symbol(target)` to read one function/class's full source without reading the whole file. Call `read_symbol(target, depth="interface")` for a class's API (methods + fields, no bodies, indented as in the class and ending as written, `;` included) or for a function's signature. Call `read_symbol(target, depth="signature")` for signature-only. Both refuse a variable, constant, field or type alias, saying what it is: read those with the default depth. Call `read_imports` to see dependencies. Call `find_references` before renaming anything. Dotted targets descend into closures: Go `stdioCmd.RunE` (func_literal in struct field), JS/TS `app.handler` (arrow function in object literal). JS/TS exports are listed and targeted by their own names (an anonymous `export default function/class` is `default`); a symbol's decorators, its `export` and a C++ `template <...>` header are part of it, so `read_symbol` shows them, `replace_function` content should include them, and `delete_symbol` removes them; a C/C++ class, struct, union or enum ends with its `};`. JS/TS generators and a `const`/`let`/`var` bound to an arrow function or function expression (`const f = (x) => {...}` is `f`) are functions (the body tools need a `{ }` body; for `(x) => x * 2` use `replace_function`), TS abstract classes are classes (abstract methods included), and TS enums and type aliases are listed as `enum` and `type`. A TS name that a type and a value share in one scope (`const User = z.object(...)` with `type User = ...`) is refused as ambiguous: edit those declarations with your normal edit tool.
   - **Config files (JSON/YAML/TOML):** a target is the key path from the top level (`project.version`; `a.b` never matches a deeper `x.a.b`). Put a key that contains dots in double quotes: `"editor.fontSize"`, `a."b.c".d` (TOML also takes single quotes, as in a TOML dotted key). Keys inside YAML flow mappings and TOML inline tables are part of the path (`a: {x: 1}` is `a.x`, `t = { a = 1 }` is `t.a`) and stay inline when edited. Array elements are not addressable by path.
2. **Adding new content** — choose the narrowest tool:
   - Top-level (function, class, constant, type alias): `add_top_level` (use `position="top"` to prepend after preamble)
   - In a class: `add_method` (after the last member), `add_field` (before the first, after a Python docstring or a Java enum's constants); both indent like the class's existing members (in tabs for a tab-indented class) and keep your content's relative indentation and the text of its multi-line strings, as every tool that re-indents content does (a Python docstring, Ruby `<<~` heredoc or Java text block moves with the code)
   - At top of a function body: `insert_in_body(at="top")`
   - At bottom of a function body: `insert_in_body(at="bottom")`
   - At a specific spot inside a function body (anchored to an existing snippet): `insert_in_body(after=...)` or `insert_in_body(before=...)`
   - Relative to an existing top-level symbol: `insert_sibling(position="before"|"after")` (`"before"` goes above the symbol's leading comment, decorators, `export` and `template` header; the new code gets a blank line on each side, two next to a top-level Python def or class)
   - Imports: `add_import` (new line) or `add_import_name` (add to existing `from X import ...` or `import { a, b } from "mod"`)
   - Parameters: `add_parameter` (a list written one parameter per line gets the new one on a line of its own)
   - Leading comment: `edit_leading_comment(op="add", comment=...)` (goes above the symbol's decorators/annotations, `export` and `template` header; refused if the symbol already has one; the error quotes it, so use `op="replace"` with a block that repeats any lines to keep, such as lint or compiler directives)
   - Python docstring: `replace_docstring`
   - Any dict/object (config OR Python/JS/TS literal): `add_key` (refused if the key already exists; use `replace_value`). For config files, `parent_target` is the full key path from the top level (`""` for the root); YAML `{}`/flow mappings, a YAML key with no value and TOML inline tables work too, and YAML/TOML keys are quoted for you only when they need it (a JSON or YAML `key` is one name, dots included; in TOML, `a.b` is a dotted key: pass `'"a.b"'` for a name containing a dot). For Python/JS/TS, `parent_target` is the module-level variable name, dotted into nested literals (`CONFIG.server`, `CONFIG."db"`)
   - Any list/array (config OR Python literal): `append_to_array` (an inline array stays inline, one element per line gets a new line, a trailing comma is kept)
3. **Modifying existing content:**
   - Full function: `replace_function` (a symbol that shares a line with other code has only its own text replaced)
   - Body only: `replace_function_body` (a body on its signature's line is rebuilt over lines of its own)
   - One statement/block inside a large body: `replace_in_body(target, old_snippet, new_snippet)` — scoped match; the single biggest token-saver for long functions
   - Signature only: `replace_signature` (existing decorators/annotations such as `@Override` and a C++ `template <...>` header are kept unless you include your own; for `const f = (a) => {...}`, `"const f = (a, b) =>"` replaces from the `const`, `"(a, b) =>"` only the function's part)
   - Value of an existing key (config, Python dict or JS/TS object): `replace_value` (config targets are key paths as above; a YAML key with no value, `a:`, gets one: `a: 3`)
   - Leading comment: `edit_leading_comment(op="replace", comment=...)`
   - Python docstring: `replace_docstring`
4. **Removing content:**
   - Function/class/method: `delete_symbol` (consumes the leading doc comment by default; pass `include_leading_comments=False` to keep it; the blank lines that separated the symbol go too, so the file keeps its spacing; a symbol that shares a line with other code is cut out of that line)
   - One statement/line inside a function body: `delete_in_body(target, snippet)` — scoped match; use for single-line removals (route mounts, middleware calls, object-literal keys in inline args)
   - Parameter: `remove_parameter` (a parameter on a line of its own goes with that line and its comment; other comments stay)
   - Import: `remove_import` (whole line) or `remove_import_name` (one name from multi-name)
   - Leading comment: `edit_leading_comment(op="remove")`
   - Dict/object key or list item: `delete_key`, `remove_from_array` (likewise: an element on a line of its own goes with that line and its comment, other comments stay)

**Anti-patterns to avoid:**

- Don't use `replace_function` or `replace_function_body` to change a few lines — use `replace_in_body` (scoped snippet match) or `insert_in_body(at="top"|"bottom")` for prepend/append.
- Don't use `replace_signature` to add one parameter — use `add_parameter` / `remove_parameter`.
- Don't use `replace_value` to add a new key — use `add_key`.
- Don't use `add_import` to add a name to an existing from-import or named import — use `add_import_name`.
- Don't guess target names — call `list_symbols` first. Names are case-sensitive.

**Safety nets:**

- Every edit is parse-checked before it is saved. An edit that would introduce a syntax error into a file that parsed cleanly is refused (the message gives the error's line and column) and the file is left unchanged: fix the content and retry, or, if the code is valid but uses syntax the parser does not support (very new language features, macro-heavy C/C++), use your normal edit tool. Files that already had syntax errors are not guarded.
- Line endings are preserved (CRLF files stay CRLF). Always write content, snippets and anchors with `\n` line breaks; only `\n` (or CRLF) breaks a line, so form feeds or U+2028 inside string literals are kept as written, and only spaces and tabs count as indentation.

**Escape hatches — when to step outside ast-editor:**

- **Deleting multiple related symbols as a group?** Call `delete_symbol` once per target. There's no `delete_group` tool; the extra tool calls are cheaper than the alternative of a custom grouped primitive.
- **Editing a sub-expression inside a method chain** (e.g. dropping `.references(...)` from `integer("x").notNull().references(...)`) or other arbitrary expression surgery? For common cases use `replace_in_body` with the literal snippet. For truly arbitrary sub-expression edits, fall back to the default `Edit` tool — ast-editor intentionally doesn't do AST pattern matching on expression trees.
- **Rewriting a whole file where the structure changes substantially?** Use the default `Write` tool. ast-editor is for targeted edits; duplicating `Write` as a tool here would add no value.
