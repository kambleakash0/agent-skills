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
| Add 2 lines to a function | any size | **~20x** (via `insert_in_body(at="top")` / `insert_in_body(at="bottom")`) | 5–10x | 3–5x |

Per-read input token savings versus reading the entire file:

| Read task | File size | AST reader tool | vs full file read |
| :--- | :--- | :--- | :--- |
| One function's source | 500 LoC | `read_symbol` | **~20x fewer tokens** |
| One function's source | 2,000 LoC | `read_symbol` | **~50-100x fewer tokens** |
| Class API (10 methods, no bodies) | 500 LoC | `read_symbol(depth="interface")` | **~10x fewer tokens** |
| Import block only | any size | `read_imports` | **~20-50x fewer tokens** |
| Structural overview (names + line numbers) | any size | `list_symbols` | **~15-30x fewer tokens** |
| One function's signature | any size | `read_symbol(depth="signature")` | **~50-200x fewer tokens** |

**For daily agent users, a realistic 40-60% reduction in total tokens per session is achievable, on average** (combining output savings from surgical edits with input savings from targeted reads).

The savings come from four compounding effects:

- **Output tokens:** Using `insert_in_body` (`at="top"` / `at="bottom"`, or anchored with `after=` / `before=`) for small additions instead of rewriting whole function bodies
- **Input tokens:** Using `read_symbol` (`depth="full"` / `"interface"`) / `read_imports` to read only what's needed instead of entire files (~10-20x fewer input tokens per read)
- **Discovery:** `list_symbols` / `read_symbol(depth="signature")` instead of reading whole files
- **Zero format failures:** AST edits never fail on whitespace drift, eliminating retry loops that plague other formats.

## Supported Languages & Capabilities

| Language | Extensions | Structural edits | Comments | Docstrings | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Python** | `.py` | ✅ | ✅ `#` | ✅ function/class | Decorators preserved. Module-level `dict`/`list` literals editable via `add_key` / `replace_value` / `delete_key` / `append_to_array` (nested dicts addressed by key path, e.g. `CONFIG."db"`). |
| **JavaScript** | `.js`, `.jsx`, `.mjs`, `.cjs` | ✅ | ✅ `//` + `/* ... */` | — | Exported declarations (`export function`, `export class`, `export default function c`) are listed and targeted by their own names, an anonymous `export default function () {}` / `export default class {}` as `default`; the `export` is part of the symbol, so `read_symbol` shows it and `replace_function` content should keep it. Generator functions (`function* g()`) and a `const`/`let`/`var` that declares one name bound to an arrow function or function expression (`const f = (x) => {...}`, exported or not) are listed and targeted as functions: `read_symbol`, `replace_function`, `delete_symbol`, the comment tools, `insert_sibling` and the parameter tools work on them, and the body tools on those with a `{ }` body (one whose body is an expression, `(x) => x * 2`, is refused: rewrite it with `replace_function`). Their signature is `const f = (x) =>`, and `replace_signature` replaces from the `const` when the new signature starts with it, else only `(x) =>`; a lone unparenthesized parameter gets parentheses from the parameter tools (`x => ...` becomes `(x, y) => ...`, or `() => ...` when it is removed). Module-level `const`/`let`/`var` object literals (exported or not) editable via `add_key` / `replace_value` / `delete_key`; nested objects addressed by dotted path (`CONFIG.server`). |
| **TypeScript** | `.ts`, `.tsx` | ✅ | ✅ `//` + `/* ... */` | — | Exports, generators and functions bound to names as for JavaScript. Abstract classes (`abstract class A`, exported or not) are classes for every tool, and their abstract methods are listed (an overloaded one once) and targeted (`A.m`) like the others, `replace_signature` included (the final `;` stays); enums, type aliases and interfaces are listed as `enum`, `type` and `interface` and can be read, replaced, deleted, commented and used as `insert_sibling` targets. Interfaces are treated as classes for `add_method` / `add_field`, which refuse an enum or type alias (rewrite those with `replace_function`); a type alias has no `depth="signature"`. A name that two kinds of declaration in one scope share, a type and a value as in zod's `export const User = z.object(...)` with `export type User = z.infer<typeof User>` (or an interface and a function), is refused as ambiguous by every tool that takes a target, the error naming both declarations and their lines: edit those with your normal edit tool. `.tsx` files are parsed with the TSX grammar, so JSX is valid there. Object literals editable as for JavaScript, including `{ ... } as const` and `satisfies T`. |
| **C** | `.c`, `.h` | ✅ | ✅ `//` + `/* ... */` (single + multi-line) | — | `.h` defaults to C — use `.hpp`/`.hxx`/`.hh` for C++ headers (adding C++-only syntax to a `.h` file that parses as C is refused by the save-time syntax check). |
| **C++** | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx`, `.hh` | ✅ | ✅ `//` + `/* ... */` (single + multi-line) | — | Supports `class`, `struct`, `union`, `enum`, `namespace`; `Class::method` qualified names resolve correctly. |
| **Ruby** | `.rb` | ✅ | ✅ `#` | — | Classes, modules, instance methods, `singleton_method` (class methods via `def self.foo`). `require`/`require_relative`/`load`/`autoload` recognized as imports. |
| **Go** | `.go` | ✅ | ✅ `//` + `/* ... */` | — | `struct`, `interface`, functions, methods. Methods are addressed by receiver: `Cache.Get` resolves to the top-level `func (c *Cache) Get(...)`. Grouped `import (...)` blocks supported. |
| **Java** | `.java` | ✅ | ✅ `//` + `/* ... */` + Javadoc `/** ... */` | — | `class`, `interface`, `enum`, `record`; methods, constructors, fields. Annotations (`@Override`, `@Deprecated`) travel with their method on edits (wrapped in the `modifiers` node); `replace_signature` keeps them unless the new signature includes its own, and also works on interface and abstract methods, which have no body. Enum methods (nested in `enum_body_declarations`) discovered via BFS in `list_symbols`. |
| **JSON** | `.json` | ✅ (keys, values, arrays) | — (no comment syntax) | — | Numbers with a `+` in the exponent (`6.02E+23`), which the grammar cannot parse on its own, are read as whole values, so `replace_value`, `delete_key` and `add_key` beside them work as for any other number. |
| **YAML** | `.yml`, `.yaml` | ✅ (keys, values, sequences) | ✅ `#` | — | Block and flow sequences supported. Keys inside flow mappings are addressable by path (`a: {x: 1}` is `a.x`, nested ones too), so `read_symbol`, `replace_value` and `delete_key` work on them and they stay inline. `add_key` also adds to flow mappings (`{a: 1}`, `{}`) and to a key with no value (`parent:`). A key with no value can be read (as an empty string), commented, and given a value with `replace_value` (`a: 3`; content of several lines, or a block sequence or mapping, goes below the key one level deeper); an explicit key with no value (`? a`) gets its value on a `: 3` line below it, in the column of the `?`. In a multi-document file a path is looked up in each document in turn (`add_key` with `parent_target=""` adds to the first document with content). Quoted keys are matched by the name they spell, so `'it''s'` is target `it's` and `"caf\u00e9"` is `café`. |
| **TOML** | `.toml` | ✅ (keys, values, arrays, tables) | ✅ `#` | — | `[table]` headers (dotted and quoted ones too, `[tool.uv]`, `[a."b.c"]`) addressable by their names for comment tools and `add_key`. Keys inside inline tables (`t = { a = 1 }` is `t.a`, nested ones too) and dotted keys (`x.y = 1` is `x.y`) are addressable by path. `add_key` also adds to inline tables (`t = { a = 1 }`, `t = {}`). |

**Cross-cutting features:**

- **Decorated functions and classes** (Python and JS/TS `@decorator`, Java annotations): decorators are part of the symbol. They are preserved on body edits; `read_symbol`, `replace_function` and `delete_symbol` include them; a leading comment belongs above the first of them (`edit_leading_comment` puts it there and finds an existing one there), and `insert_sibling(position="before")` goes above them and that comment, so the comment stays on the symbol it documents. This holds for TypeScript methods too, whose decorators the grammar places beside the method in the class body, and for decorated Python classes. `replace_signature` keeps them as written unless the new signature includes its own, which then replace them.
- **Layout-aware `add_method` / `add_field`**: the new member is indented like the class's existing members (falling back to the file's indent unit, then the language default: 4 spaces for Python and Java, a tab for Go, 2 spaces otherwise), keeping the content's relative indentation; in a class indented with tabs that indentation is written in tabs too (one per indentation step of the content), so a snippet written with spaces fits a tab-indented file. A method follows the last member after one blank line, or none when the class's methods have no blank lines between them (TS interface members stay one per line) or the last member is a C++ access label (`public:`); a field goes before the first member (after a Python class docstring), with a blank line after it when that member is a method, and a comment after the `{` on its line (`class K { // NOLINT`) stays there. In a Java enum both go after the constants, and a `;` is added after them when they have none. No blank line is added before the closing brace, and a braced body on one line (`class K {}`, `class K { a() {} }`, Go `struct{ A int }`) is opened up over several lines, its existing members on a line of their own. A Python or Ruby class written on one line (`class K: pass`) is refused.
- **Layout-aware `add_key`**: in JSON objects, Python dicts, JS/TS object literals, YAML flow mappings and TOML inline tables the new entry follows the container's layout (one key per line at the existing indentation, inline objects stay inline, a trailing comma is kept, and a comment on the last entry's line stays there); an empty JS/TS or YAML `{}` becomes `{ key: value }` (TOML: `{ key = value }`). A YAML key with no value gets a nested block mapping one indentation level deeper. YAML and TOML keys are quoted only when they need it: `my key` and `a.b` stay plain in YAML, while `a:b`, `yes`, `123` or a leading `-`/`#`/`&` get quotes (in the quote style most of the file uses); in TOML anything but a bare key (letters, digits, `_`, `-`) is quoted, and dots separate the parts of a dotted key, so `b.c` adds `c` under `b` and a name with a dot in it must be passed quoted (`'"example.com"'`). A key the container already has is refused with a pointer to `replace_value`, for every format, naming a target that works (quoted where the key has a dot, inside flow mappings and inline tables too).
- **Layout-aware `append_to_array`**: JSON arrays, TOML arrays and YAML flow sequences keep their layout: an inline array stays inline (`[1, 2]` becomes `[1, 2, 3]`, `[]` becomes `[3]`), an array with one element per line gets a new line at the elements' indentation, a trailing comma is kept (the new element gets one too), and a comment on the last element's line stays there. A YAML block sequence gets a new `- value` item.
- **Config paths from the top level**: a dotted config target is followed from the top of the file, one key per segment: `a.b` is key `b` under the top-level key `a`, never an `a.b` nested deeper (such as `x.a.b`), and in TOML a plain `version` is a top-level key, not one inside a `[table]` (use `project.version`). One path syntax covers JSON, YAML and TOML and every config tool (`read_symbol`, `replace_value`, `add_key`'s `parent_target`, `delete_key`, `append_to_array`, `remove_from_array` and `edit_leading_comment`): a segment in double quotes is one key taken literally, dots included, its escapes resolved as in a JSON string (`"editor.fontSize"`, `a."b.c".d`), and in TOML single quotes work too (`a.'b.c'`), as in a TOML dotted key, whose syntax TOML paths share. Keys compare by the names they spell, so `"a.b"` finds `a.b: 1`, `'a.b': 1` and `"a.b": 1` in YAML, and `[x.'y.z']` and `[ x . "y.z" ]` are both TOML table `x."y.z"`. Keys inside YAML flow mappings and TOML inline tables are part of the path. Elements of arrays are not addressable by path (`a.0` is a key named `0`).
- **Byte-correct slicing**: multi-byte characters (emoji, `═`, `→`) handled safely in source text.
- **Idempotent imports**: `add_import` skips exact duplicates automatically. For Go specifically, when a parenthesized `import ( ... )` block already exists, new specs are inserted inside the block rather than as a bare top-level line (which would be a syntax error for spec-only input like `"path/filepath"`).
- **Doc-comment-aware deletion**: `delete_symbol` by default removes the contiguous leading comment block above the symbol (Godoc, Javadoc, `#`/`//` comment runs) so docs don't become orphaned. Opt out with `include_leading_comments=False`. Only real comments count, for this and every other tool that finds a leading comment: a line that starts with `#` or `//` inside a multi-line string, template literal or YAML block scalar is text. A `#!` line and the encoding or magic comments after it (`# -*- coding: utf-8 -*-`, `# frozen_string_literal: true`) at the top of a Python or Ruby file are never taken for a symbol's comment, by this or any other tool.
- **Layout-aware deletion**: the blank lines that separated a deleted symbol go with it, so the rest keeps the file's spacing: deleting the first symbol of a file or class body leaves no blank lines at the top or after the `{`, deleting the last one leaves none before the closing brace (and the next top-level symbol keeps its own separation, such as Python's two blank lines), and between the two symbols that remain only the wider of the two gaps stays. Only empty lines and lines of spaces and tabs are blank: a form feed line (a Python page break) next to the symbol stays.
- **Syntax-checked saves**: before anything is written, the edited file is re-parsed with its tree-sitter grammar. An edit that would introduce a syntax error into a file that parsed cleanly is refused with the error's line and column (e.g. `Edit refused: the result would have a syntax error at line 11, column 2 (missing '}')`), and the file is left unchanged. Files that already had syntax errors are not guarded, so you can keep working on them. For `.py` files Python's own parser (that of the interpreter running the server) decides: it catches the indentation errors tree-sitter lets through and accepts newer syntax the grammar does not know (PEP 696 type parameter defaults). For `.json` files the `json` module overrules the grammar wherever it would reject valid JSON, and comments in JSONC files stay allowed; exponents written with a `+` (`1e+2`), which tree-sitter-json cannot parse, are masked before parsing, so files that use them are checked like any other. Other languages have no second parser, so valid code using syntax the grammar does not support (very new language features, macro-heavy C/C++) can be refused: if you are sure the code is valid, make that edit with your normal edit tool.
- **Line endings preserved**: CRLF files stay CRLF and LF files stay LF, whichever tool makes the edit, and blank lines at the end of a file are kept as they were (deleting the last symbol does not leave extra ones behind). Write content, snippets and anchors with `\n` line breaks: inserted text is converted to the file's style, and a `\n` in a snippet or anchor matches a CRLF line break. Content is split into lines on `\n` (or CRLF) only, so a form feed, vertical tab, U+0085, U+2028 or U+2029 inside a string literal or comment stays where it was written. Only spaces and tabs count as indentation, so when content is re-indented a form feed at the start of a line (a Python page break, `\fdef g():`) or a U+2028 starting a line inside a string stays, and a form feed before the target's own `def` is not copied onto the new lines. A file with mixed endings is written back in the style most of its lines use.

### Language-specific design decisions

A few tools have language-specific semantics where multiple reasonable interpretations exist. The chosen behavior is documented here for transparency:

**`add_field` (Ruby and Go) — option (a): literal text passthrough**

- **Ruby:** `add_field("LRUCache", "  attr_accessor :capacity")` inserts the literal string at the top of the class body. The tool does **not** auto-wrap bare names in `attr_accessor` — you provide the exact text you want (whether that's `attr_accessor`, `attr_reader`, `@instance_var = nil` in `initialize`, or `CLASS_CONST = 42`).
- **Go:** `add_field("Cache", "\tversion int")` inserts the literal string inside the `struct { ... }` body. The tool does **not** infer types from bare names — you provide the full Go field declaration.
- **Rationale:** consistent with how `add_field` works for other languages (Python, JS/TS, C++) where the caller provides the full source text. The alternative option (b) — auto-wrapping (e.g. `attr_accessor :foo` from the name `foo`) — would be more magical but harder to use for edge cases (typed fields, readonly fields, field with default value, etc.).

**`add_method` (Go) — option (a): top-level sibling insertion**

- `add_method("Cache", "func (c *Cache) Has(key string) bool { ... }")` locates the `type Cache struct { ... }` declaration and inserts the new method **immediately after it, at the top level** (not inside the struct's braces).
- **Rationale:** Go methods are lexically top-level, not nested inside their receiver type — this matches how Go code is actually written. The alternative option (b) — refusing because "Go methods aren't inside structs" — would be pedantically correct but force callers to use `insert_sibling("Cache", content, position="after")` instead, which loses the semantic signal that this is a method addition.

## Tools Exposed

All tools require `file_path` to be an **absolute path** to an existing file.

### Code editing — structural (Python, JS, TS, C, C++, Ruby, Go, Java)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `replace_function` | `file_path`, `target`, `content` | Replace a full function definition (signature + body + decorators, and a JS/TS `export`, as `read_symbol` returns it). |
| `replace_function_body` | `file_path`, `target`, `content` | Replace only the body of a function, preserving signature and decorators. |
| `replace_signature` | `file_path`, `target`, `new_signature` | Replace only the signature, preserving the body. Existing decorators (Python, JS/TS) and Java annotations are kept unless `new_signature` includes its own, which replace them. Indentation on the signature's first line is ignored, so `"def get(self):"` and `"    def get(self):"` both work for a method; the lines after it may be indented relative to it (`"@staticmethod\ndef get(key):"`) or written as `read_symbol(depth="signature")` returns them. For a JS/TS `const f = (a) => {...}`, `"const f = (a, b) =>"` replaces from the `const` on and `"(a, b) =>"` only the function's own part. A method declared without a body (a TS abstract method, a Java interface or abstract method) is all signature but its final `;`, which stays whether or not `new_signature` ends with one. |
| `replace_in_body` | `file_path`, `target`, `old_snippet`, `new_snippet` | Replace a byte-identical snippet inside a function body. Scoped to target's body; raises on multiple matches. |
| `delete_in_body` | `file_path`, `target`, `snippet` | Delete a byte-identical snippet inside a function body. Scoped to target's body; raises on multiple matches. |
| `insert_in_body` | `file_path`, `target`, `new_snippet`, `at` \| `after` \| `before` | Insert a snippet inside a function body. Pass exactly ONE of: `at="top"` (prepend), `at="bottom"` (append), `after=<snippet>` (anchored), `before=<snippet>` (anchored). `at` inserts at the body's own indentation level even when the body ends in a nested block; a Python docstring stays first; a body written on one line with its signature or braces is refused (rewrite it with `replace_function_body`). |
| `add_top_level` | `file_path`, `content`, `position="bottom"` | Insert top-level content. `position="bottom"` appends at end of file (default); `position="top"` inserts after preamble (package/imports/includes/leading comments, plus Python module docstring) and before the first real declaration. |
| `add_method` | `file_path`, `class_target`, `content` | Add a method at the end of a class body, indented like the class's members and separated as its methods are (see Layout-aware `add_method` / `add_field` above). |
| `add_field` | `file_path`, `class_target`, `content` | Add a field/attribute/member at the top of a class body (after a Python class docstring), indented like the class's members. |
| `insert_sibling` | `file_path`, `target`, `content`, `position` | Insert content as a sibling of a named symbol. `position="before"` or `"after"`; `"before"` goes above the symbol's leading comment block, decorators and a JS/TS `export`. |
| `delete_symbol` | `file_path`, `target`, `include_leading_comments=True` | Delete a function or class definition block (including decorators and a JS/TS `export`) and the blank lines that separated it (see Layout-aware deletion above). By default also consumes the contiguous leading comment block above the symbol and its decorators (Godoc, Javadoc `/** ... */`, `#` or `//` comments); pass `include_leading_comments=False` to keep it. |

### Parameters & signatures

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `add_parameter` | `file_path`, `target`, `parameter`, `position="end"` | Add a parameter to a function signature (`position`: `"start"` or `"end"`; any other value is refused). |
| `remove_parameter` | `file_path`, `target`, `parameter_name` | Remove a parameter by name. |

### Imports & includes

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `add_import` | `file_path`, `import_text` | Add an `import`/`from`/`#include` line. Skips duplicates. For Go, if a parenthesized `import ( ... )` block already exists, the spec is inserted inside that block (accepts either `import "foo"` or just `"foo"` / `alias "foo"` as input). |
| `remove_import` | `file_path`, `import_text` | Remove a matching import line. |
| `add_import_name` | `file_path`, `module`, `name` | Add one name to an existing named-import statement: `from <module> import a, b` (Python) or `import { a, b } from "<module>"` (JS/TS). Idempotent. |
| `remove_import_name` | `file_path`, `module`, `name` | Remove one name from a multi-name named-import statement (Python and JS/TS). If the last named import is removed and no default/namespace binding remains, the whole line is removed. |

### Comments & docstrings

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `edit_leading_comment` | `file_path`, `target`, `op`, `comment=""` | Edit the contiguous leading-comment block above a named symbol, which is above its decorators/annotations and a JS/TS `export`. `op="add"` inserts (refused if the symbol already has a leading comment; the error quotes it, so a following `op="replace"` can repeat lines worth keeping, such as `// eslint-disable-next-line` or `//go:noinline` directives); `op="replace"` replaces (or inserts if none); `op="remove"` deletes. Works for `#` / `//` / `/* ... */` / Javadoc `/** ... */`; a `/* ... */` that follows code on its line (`int x = 1; /* n */`) is not taken as a leading comment. In YAML and TOML the target is a key path (a YAML key with no value too) or a TOML `[table]` by its header's names (`tool.uv`); a key that does not start its line (inside a flow mapping or inline table) is refused, since the comment line above would belong to another key. |
| `replace_docstring` | `file_path`, `target`, `new_docstring` | Replace or insert a Python function/class docstring. Python-only. |

### Dict/list editing (JSON, YAML, TOML, Python module-level dict/list literals, AND JS/TS object literals)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `replace_value` | `file_path`, `target`, `content` | Replace the value of an existing key. Targets as for `delete_key`: JSON/YAML/TOML dotted path from the top level (`"editor.fontSize"` for a key with dots; keys inside YAML flow mappings and TOML inline tables too, which stay inline); Python `DictName.keyExpr`; JS/TS `VarName.key` (a shorthand `{ key }` becomes `key: <content>`). A YAML key with no value (`a:`) gets one (`a: 3`, or a nested block below the key for content of several lines or a block sequence or mapping; a first line that is only `|`, `>-`, an `&anchor` or a `!tag` stays after the colon). |
| `add_key` | `file_path`, `parent_target`, `key`, `value` | Add a key-value pair to a dict/object/mapping/table. For config, `parent_target` is a dotted path from the top level (use `""` for root; a TOML `[table]` by its header's names, `a."b.c"` for `[a.'b.c']`); YAML flow mappings (nested ones too) and keys with no value and TOML inline tables work too. For JSON and YAML `key` is one name, dots included. For Python it is the dict variable name; for JS/TS the name of a module-level `const`/`let`/`var` (or `export const`) object literal, `as const` / `satisfies` included. Both may continue into nested literals (`CONFIG."db"`, `CONFIG.server`). JSON keys are quoted for you, YAML and TOML keys only when they need it (in TOML, dots make a dotted key), JS/TS keys only when they are not valid identifiers, Python keys are key expressions (`'"timeout"'`). The entry follows the container's layout (one per line, inline, trailing comma), and a key that already exists is refused (use `replace_value`). |
| `delete_key` | `file_path`, `target` | Delete a key-value pair. Targets: JSON/YAML/TOML dotted path from the top level (`"editor.fontSize"` for a key with dots; keys inside YAML flow mappings and TOML inline tables too, cut like JSON entries with their comma); Python `DictName.keyExpr`; JS/TS `VarName.keyName` on `const`/`let`/`var` or `export const` object literals (handles regular pairs, `{ key }` shorthand, methods, and quoted `"complex-key"`). Python and JS/TS paths may continue into nested literals (`CONFIG.server.port`). For JSON, Python and JS/TS, the adjacent comma is also removed (an entry on its own line goes with that whole line, including its same-line comment), and deleting the only entry leaves `{}`. |
| `append_to_array` | `file_path`, `target`, `value` | Append a literal value to a list/array/sequence. For Python, `target` is the list variable name; for config, a dotted path from the top level. The array keeps its layout: inline stays inline (`[1, 2, 3]`), one element per line gets a new line at the elements' indentation, and a trailing comma is kept. |
| `remove_from_array` | `file_path`, `target`, `value_match` | Remove the first matching element from a list/array/sequence. |

### Navigation & reading (read-only)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_symbols` | `file_path` | Formatted outline of all top-level functions, classes, and methods with line numbers (a symbol's line is that of its first decorator or `export`). JS/TS exported declarations are listed under their own names, an anonymous default export as `default`; generators and functions bound to a `const`/`let`/`var` as `function`, TS abstract classes as `class` (with their abstract methods), and TS enums, type aliases and interfaces as `enum`, `type` and `interface`. Every listed name is a valid target, except a TS name that a type and a value share, which is refused as ambiguous (see TypeScript above). |
| `find_references` | `file_path`, `target` | Syntactic search for all occurrences of an identifier (no scope awareness). |
| `read_symbol` | `file_path`, `target`, `depth="full"` | Return source text of a single named symbol. `depth` controls how much: `"full"` returns the entire source (typically **10-20x fewer tokens** than the whole file); `"interface"` returns a class stub (header + fields + method sigs with `...`, each member at its indentation relative to the class header) or a function's signature; `"signature"` returns signature-only (a method with no body, such as a TS abstract or Java interface method, is its whole declaration). For a config key path, `"full"` returns the key's value (an empty string for a YAML key with no value). |
| `read_imports` | `file_path` | Return all import/include statements in the file. |

**Target format:** Use the exact function name (e.g., `get`) or dotted `Class.method` path (e.g., `LRUCache.get`). JS/TS exported declarations are targeted by their own names (`export function add` is `add`); an anonymous `export default function/class` is `default` (and its methods `default.run`), and `const f = () => {...}` is `f`. Decorated functions are fully supported — decorators are preserved when replacing bodies or signatures, and included when deleting or replacing the full function.

**Tip:** Call `list_symbols` first to discover exact target names before editing. This avoids guessing and makes subsequent edits much more reliable.

## Which tool should I use?

A decision guide grouped by intent. Start at the top and pick the narrowest match.

### Discovering what's in a file (do this first)

- **Don't know what symbols exist?** → `list_symbols`
- **Need one specific function's full source?** → `read_symbol` (`depth="full"`, the default — 10-20x cheaper than reading the whole file)
- **Need a class's public API (methods + fields, no bodies)?** → `read_symbol(target, depth="interface")`
- **Need just a function's signature?** → `read_symbol(target, depth="signature")`
- **Need to see a file's imports/dependencies?** → `read_imports`
- **Where is a symbol used?** → `find_references`

Dotted targets descend into closures: Go `stdioCmd.RunE` (func_literal in struct field), TS `app.handler` (arrow function in object literal).

### Adding new content

| Intent | Tool |
| :--- | :--- |
| New top-level function, class, constant, or type alias | `add_top_level` (use `position="top"` to prepend after preamble) |
| New method in an existing class | `add_method` |
| New field/attribute/member in a class | `add_field` |
| New content before or after a top-level symbol | `insert_sibling(position="before" \| "after")` (`"before"` goes above the symbol's leading comment) |
| New lines at the top of an existing function body | `insert_in_body(at="top")` |
| New lines at the bottom of an existing function body | `insert_in_body(at="bottom")` |
| **New lines at a specific spot inside a function body (anchored to existing text)** | `insert_in_body(after=…)` or `insert_in_body(before=…)` |
| New parameter on an existing function | `add_parameter` |
| New import or `#include` | `add_import` |
| New name in an existing `from X import …` or `import { a, b } from "mod"` | `add_import_name` |
| New comment above a symbol | `edit_leading_comment(op="add")` |
| New Python docstring on a function/class | `replace_docstring` |
| New key in a dict/object/mapping/table (any lang) | `add_key` |
| New item in a list/array/sequence (any lang) | `append_to_array` |

### Modifying existing content

| Intent | Tool |
| :--- | :--- |
| Rewrite the full function (signature + body) | `replace_function` |
| Rewrite only the body, keep the signature | `replace_function_body` |
| **Change one statement/block inside a large body** | `replace_in_body` (scoped snippet match) |
| Change only the signature, keep the body | `replace_signature` |
| Change only the leading comment above a symbol | `edit_leading_comment(op="replace")` |
| Change only the Python docstring | `replace_docstring` |
| Change the value of an existing key (config, Python dict, JS/TS object) | `replace_value` |

### Removing content

| Intent | Tool |
| :--- | :--- |
| Remove a function, method, or class | `delete_symbol` (consumes leading doc comment by default) |
| **Remove one statement/line inside a function body** | `delete_in_body` |
| Remove a parameter from a function | `remove_parameter` |
| Remove an import or `#include` | `remove_import` |
| Remove one name from a multi-name named-import (Python or JS/TS) | `remove_import_name` |
| Remove a leading comment above a symbol | `edit_leading_comment(op="remove")` |
| Remove a key from a dict / config / JS-TS object literal | `delete_key` |
| Remove an item from a list/array | `remove_from_array` |

### Anti-patterns to avoid

- **Don't use `replace_function` or `replace_function_body` to change a few lines** — use `replace_in_body` (scoped snippet match) or `insert_in_body(at="top" \| "bottom")` for appending/prepending. Rewriting the whole function is wasteful and error-prone.
- **Don't use `replace_signature` to add or remove one parameter** — use `add_parameter`/`remove_parameter`.
- **Don't use `replace_value` to add a new key** — use `add_key`. `replace_value` only updates existing keys, and `add_key` refuses a key that already exists.
- **Don't use `add_import` to add a name to an existing `from X import …` or named import** — use `add_import_name`.
- **Don't guess at target names.** Call `list_symbols` first. Names are case-sensitive and must match exactly.

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

The server depends on `mcp`, `tree-sitter`, and a tree-sitter grammar package for each supported language. `uv` handles all of these automatically on first run.

## Installation

> **Note:** Replace `/absolute/path/to/ast-editor` below with the absolute path to the `ast-editor` folder on your machine (the folder that contains its `pyproject.toml`).

### Method 1: CLI Configuration (Claude Code, Codex, Gemini)

If your agent supports adding servers via CLI, run the following:

`--scope user` installs the server globally so it's available in every project on your machine. Drop it if you only want the server active in the current project.

```bash
# Claude Code / Codex
[claude|codex] mcp add ast-editor --scope user -- uv --directory /absolute/path/to/ast-editor run ast-editor-mcp

# Gemini CLI
gemini mcp add --transport stdio --scope user ast-editor -- uv --directory /absolute/path/to/ast-editor run ast-editor-mcp
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
    "ast-editor": {
      "command": "/absolute/path/to/uv",
      "args": [
        "--directory",
        "/absolute/path/to/ast-editor",
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
| **Antigravity** | `~/.gemini/config/mcp_config.json` — see [Antigravity IDE](#antigravity-ide) (uses `uvx --from`) |
| **Gemini CLI** | `~/.gemini/settings.json` (Global) or `.gemini/settings.json` (Project) |

### Antigravity IDE

The Antigravity IDE uses its own MCP config file and a `uvx`-based command — **not** the `uv --directory … run` form shown above. Add the server to `~/.gemini/config/mcp_config.json`:

> **Important:** Use the **absolute path** to `uvx` for `"command"`, not a bare `"uvx"` — Antigravity doesn't inherit your shell `PATH`. Find it with `which uvx` (e.g. `/opt/homebrew/bin/uvx`).

> **Note:** `uvx` ignores both this server's `uv.lock` and the `[tool.uv]` settings in its `pyproject.toml`. It re-resolves dependencies on each launch instead of using the locked versions, and the 7-day cooldown is passed explicitly as `--exclude-newer "7 days"` in `args`, so you get the newest compatible releases that are at least 7 days old. This requires uv 0.9.17 or newer: older versions reject the value (`invalid value '7 days' for '--exclude-newer <EXCLUDE_NEWER>'`) and the server fails to start.

```json
{
  "mcpServers": {
    "ast-editor": {
      "command": "/absolute/path/to/uvx",
      "args": [
        "--exclude-newer",
        "7 days",
        "--from",
        "/absolute/path/to/ast-editor",
        "ast-editor-mcp"
      ]
    }
  }
}
```

### Using Standard Python (Fallback)

If you prefer not to use `uv`, run the following from the `ast-editor` folder (the one that contains its `pyproject.toml`), then point to the `.venv` executable it creates. `python3` must be Python 3.10 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install .
```

This path doesn't use uv, so the `[tool.uv]` 7-day dependency cooldown doesn't apply. With pip 26.1 or newer, add `--uploaded-prior-to P7D` to the `pip install` command to apply the same cooldown.

```json
{
  "mcpServers": {
    "ast-editor": {
      "command": "/absolute/path/to/ast-editor/.venv/bin/python",
      "args": ["-m", "ast_editor.server"]
    }
  }
}
```

## Agent Configuration (Important)

Coding agents are heavily biased toward their default tools. You **must** explicitly instruct them to use `ast-editor` when editing code and config files. The agent prompt lives in [`AST-EDITOR.md`](./AST-EDITOR.md) — a standalone file you wire into your agent's system instructions. The server also sends a condensed version of this guidance (at most 1,500 characters: start with `list_symbols`, pick the narrowest tool, what to do when an edit is refused for a syntax error, and the escape hatches) as MCP server `instructions`, which some clients, Claude Code among them, pass to the model automatically alongside any prompt file. Wiring in the full prompt file is still recommended. After updating the server, copy the new `AST-EDITOR.md` over the one you installed (for example `~/.claude/AST-EDITOR.md`), since an installed copy does not update itself.

### Claude Code / Claude Desktop (via `@`-include)

Claude Code supports `@filename` includes in `CLAUDE.md`. Copy the prompt file into your global config directory and add one include line:

```bash
cp /absolute/path/to/ast-editor/AST-EDITOR.md ~/.claude/
echo '@AST-EDITOR.md' >> ~/.claude/CLAUDE.md
```

Or for a single project, place it next to the project's `CLAUDE.md` and add `@AST-EDITOR.md` there.

### Other agents (Cursor, Codex CLI, Windsurf, Antigravity, Aider, Gemini CLI, etc.)

Copy the **contents** of [`AST-EDITOR.md`](./AST-EDITOR.md) into your agent's instruction file (`AGENTS.md`, `.cursor/rules/*.mdc`, `.windsurfrules`, `.github/copilot-instructions.md`, system prompt, etc.). Most non-Claude agents don't support `@`-include — paste the prompt body directly.

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
