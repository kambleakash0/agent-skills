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
| **Python** | `.py` | ✅ | ✅ `#` | ✅ function/class | Decorators preserved. Nested classes (decorated ones too) are listed with their members (`class A.B`, `method A.B.m`). Module-level `dict`/`list` literals editable via `add_key` / `replace_value` / `delete_key` / `append_to_array` (nested dicts addressed by key path, e.g. `CONFIG."db"`); comments in a list are not elements, so `append_to_array` puts the comma before them. Module-level variables (`X = 1`, `Y: int = 2`) are listed as `variable` and class attributes as `field` (`A.x`), at their first assignment; `replace_value` replaces their value. `@overload` stubs directly before their function are one symbol with it, listed once at the first stub. A name defined again (a redefinition, a `@property` setter) is listed again, and the name targets the first. |
| **JavaScript** | `.js`, `.jsx`, `.mjs`, `.cjs` | ✅ | ✅ `//` + `/* ... */` | — | Exported declarations (`export function`, `export class`, `export default function c`) are listed and targeted by their own names, an anonymous `export default function () {}` / `export default class {}` as `default`; the `export` is part of the symbol, so `read_symbol` shows it and `replace_function` content should keep it. Generator functions (`function* g()`) and each name of a `const`/`let`/`var` bound to an arrow function or function expression (`const f = (x) => {...}`, exported or not) are listed and targeted as functions: `read_symbol`, `replace_function`, `delete_symbol`, the comment tools, `insert_sibling` and the parameter tools work on them, and the body tools on those with a `{ }` body (one whose body is an expression, `(x) => x * 2`, is refused: rewrite it with `replace_function`). Their signature is `const f = (x) =>`, and `replace_signature` replaces from the `const` when the new signature starts with it, else only `(x) =>`; a lone unparenthesized parameter gets parentheses from the parameter tools (`x => ...` becomes `(x, y) => ...`, or `() => ...` when it is removed). Module-level `const`/`let`/`var` object literals (exported or not) editable via `add_key` / `replace_value` / `delete_key`; nested objects addressed by dotted path (`CONFIG.server`). Other data is listed too: each name of a `const` as `constant` and of a `let`/`var` as `variable`, and class fields as `field` (`A.x`, `A.#y`, static, decorated and `declare` ones), which the whole-symbol tools and `replace_value` (its value alone) take; a method or function wins over a class field or `var` of its name (`static run = false;` beside `run() {}`), and a setter beside its getter is not listed (the name targets the getter). Computed and quoted names are targets as listed (`E.[Symbol.iterator]`, `E.'a.b'`). A comment after a symbol on its last line (`function f() {} // f`) is no part of it, as in the other languages. CommonJS `require` statements count as imports for `add_import`. |
| **TypeScript** | `.ts`, `.tsx` | ✅ | ✅ `//` + `/* ... */` | — | Exports, generators and functions bound to names as for JavaScript. Abstract classes (`abstract class A`, exported or not) are classes for every tool, and their abstract methods are listed (an overloaded one once) and targeted (`A.m`) like the others, `replace_signature` included (the final `;` stays); enums, type aliases and interfaces are listed as `enum`, `type` and `interface` and can be read, replaced, deleted, commented and used as `insert_sibling` targets. Interfaces are treated as classes for `add_method` / `add_field`, which refuse an enum or type alias (rewrite those with `replace_function`); a type alias has no `depth="signature"`. A type alias or interface that shares its name with a value in one scope, as in zod's `export const User = z.object(...)` with `export type User = z.infer<typeof User>` (or an interface and a function), is targeted with its keyword, `type User` or `interface Props` (listed as `type type User`; with a dotted path the keyword goes first, `type N.User`), and the plain name targets the value. Overload signatures directly before their implementation (through `export` and `declare`, comments and the implementation's decorators between them; a run of signatures alone too) are one symbol with it, listed once at the first signature: `read_symbol`, `replace_function` and `delete_symbol` take them all, `insert_sibling(position="before")` and `edit_leading_comment` go above the first, and the signature depths, `replace_signature`, the parameter tools and the body tools work on the implementation. Namespaces (`namespace N {}`, `module N {}`) are listed as `namespace` with their classes and functions (`N.C`, `N.f`); one opened again, or merged with the class, function or enum of its name, is one container: the name targets the class, function or enum, its members and the namespace's are found and listed under it, and none of this is ambiguous. `declare` declarations are listed like plain ones (`read_symbol` shows the `declare`), and an abstract method reads with its `;`. A namespace's interface ends with its `}`, without a comment after it. `.tsx` files are parsed with the TSX grammar, so JSX is valid there. Object literals editable as for JavaScript, including `{ ... } as const` and `satisfies T`. |
| **C** | `.c`, `.h` | ✅ | ✅ `//` + `/* ... */` (single + multi-line) | — | `.h` defaults to C — use `.hpp`/`.hxx`/`.hh` for C++ headers (adding C++-only syntax to a `.h` file that parses as C is refused by the save-time syntax check). A struct, union or enum ends with the `;` after its `}`: `read_symbol` shows it, `replace_function` content should end with `};`, and `delete_symbol` and `insert_sibling(position="after")` take it, also when it is on a line of its own. Listed as `struct`, `union`, `enum`, `function`, `macro` (`#define`, function-like ones over several lines too), `type` (typedefs; an anonymous `typedef struct {...} P;` lists its fields as `P.x` and takes `add_field`), `field`, `variable` and `constant` (`const` but not a pointer), including what `#if`/`#ifdef` blocks (include guards too) and `extern "C"` hold; a struct defined in a declaration or typedef is shown whole by `read_symbol` (`struct S {...} s;`, `typedef struct N {...} N;`). A definition wins over its forward declaration (`struct S;`), prototype or `extern` declaration in either order, and is what list and target; a prototype alone is a bodiless `function` (`replace_signature` and the parameter tools work on it). A definition outside `#if`/`#ifdef` blocks wins over one inside (`#if 0`), and of alternative definitions in `#ifdef`/`#else` branches the first is listed and targeted. A struct, union or enum that shares its name with a function, variable or typedef is targeted with its keyword (`struct stat`, listed as `struct struct stat`), and the plain name targets the other symbol (`typedef struct N {...} N;` stays one symbol, and a typedef of a struct declared apart, `typedef struct Node Node;`, is `Node`); `add_method` and `add_field` look only at containers, so `stat` is the struct there. Without overloading, `f(int)` only checks the parameter types. `replace_value` replaces the value of a global or field (`int g = 1;`, `int a[] = {1}`) or a macro's text (`#define N 3`), and gives one to a declaration without one; for a name that a macro shares with a function, the name is the macro and the function is `name(types)`. A type that is only used (`struct S *p;`) and variables inside function bodies are not targets. |
| **C++** | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx`, `.hh` | ✅ | ✅ `//` + `/* ... */` (single + multi-line) | — | Supports `class`, `struct`, `union`, `enum`, `namespace`; `Class::method` qualified names resolve correctly. Classes end with their `;` as in C. A template's `template <...>` header is part of its symbol, as decorators are: `read_symbol` shows it, `replace_function` content should include it, `delete_symbol` removes it, a leading comment and `insert_sibling(position="before")` go above it, and `replace_signature` keeps it unless the new signature starts with `template`. Template functions, classes and member templates are listed at the line of their header, an explicit specialization (`template <> int id<int>(int)`) under the name it specializes, and a definition outside its class (`int A::f()`, `template <typename T> T Box<T>::get()`) as a function under its qualified name (`A::f`, `Box::get`, `A::A`; the last name alone, or a shorter tail, still finds it when nothing else in the scope has that name). Overloads take their parameter types, written as declared without names, defaults or attributes, spacing free (`A.m(int)`, `A.m(const std::string &, int)`, `A::A(int)`, `A.operator()(int)`), and method qualifiers where only those differ (`A.get(int) const`); spellings of one type match (`unsigned` and `unsigned int`, `char const *` and `const char *`, `int[]` and `int *`, a `const` on the parameter itself, `struct S *` and `S *`), so a prototype and a definition that spell it differently are one function. The bare name of an overloaded function, and a name several qualified names end with, are refused with the targets to use. A class or namespace declared with its scope (`struct A::B {...}`, `namespace a::b {}`) is `A::B`, and `class X` targets a class that shares its name with another symbol. Everything listed for C, plus `class`, `namespace` (members as `ns.f`; a namespace opened again in its scope is listed once with the members of all its blocks, and a target finds a definition in any of them), nested classes (`class A.B`), `using` aliases as `type`, static members, methods declared in their class, and structured bindings (`auto [x, y] = p;`). Destructors and operators are named as written without spaces, `~A`, `operator==`, `operator()`, `operator bool`, and targeted as `A.~A` or `A.operator==` (any spacing matches); `find_references` finds them. |
| **Ruby** | `.rb` | ✅ | ✅ `#` | — | Classes, modules, instance methods, `singleton_method` (class methods via `def self.foo`). `require`/`require_relative`/`load`/`autoload` recognized as imports. A statement that opens a heredoc (`X = <<~EOS`) ends with the heredoc's body, for `read_symbol` and the whole-symbol edits. An endless method (`def f = x`) has no body for the body tools. Classes and modules nested in modules are listed with their members, `private def m` and `class << self` methods too (`read_symbol` shows the `private`). Embedded documents (`=begin` ... `=end` at column 0) stay at column 0 when content is re-indented, and an edit that would leave a `=begin` indented is refused; one directly above a method is its leading comment. A Sorbet signature directly above a method (`sig { ... }`, `sig do ... end`) is part of it, as a decorator is, and the signature depths start at its `def`. Constants are listed as `constant` and locals as `variable`. A class reopened in one scope is listed for each block, and the name targets the first; a dotted target finds a member in any of them. Interfaces show every method as its signature plus ` ...`, empty and endless ones too. |
| **Go** | `.go` | ✅ | ✅ `//` + `/* ... */` | — | `struct`, `interface`, functions, methods. Methods are addressed by receiver: `Cache.Get` resolves to the top-level `func (c *Cache) Get(...)`. Grouped `import (...)` blocks supported. Type aliases (`type T = int`) are listed as `type`, and every name of a `var`/`const` as `variable`/`constant`. `read_symbol` shows the `type`, `var` or `const` of a declaration of one spec (a spec in a `type (...)` group alone) and a closure's key (`RunE: func() error {...}`). `remove_parameter` removes one name of `a, b int`, keeping the others' comments. A `var x = func(...) {...}` is a function for the parameter, body and signature tools (listed as `variable`; one of several values, `var p, q = func() {}, func() {}`, has its own signature). `replace_value` on a constant without a value that the constants below it repeat is refused, as a value would change theirs. |
| **Java** | `.java` | ✅ | ✅ `//` + `/* ... */` + Javadoc `/** ... */` | — | `class`, `interface`, `enum`, `record`; methods, constructors, fields. Annotations (`@Override`, `@Deprecated`) travel with their method on edits (wrapped in the `modifiers` node); `replace_signature` keeps them unless the new signature includes its own, and also works on interface and abstract methods, which have no body. Enum methods (nested in `enum_body_declarations`) discovered via BFS in `list_symbols`. Fields and interface constants are listed as `field A.x` and targetable; a field that shares its name with a method is the name's target, and the method is `A.x()`. Overloaded methods and constructors take their parameter types (`A.m(int)`, `A.m(String...)`, `A.join(List<String>, String)`, `A.A()`), without modifiers and annotations; the bare name is refused with the targets to use. Nested classes, enums, interfaces and records are listed with their members, and a nested class whose name a field takes is left out, its members still listed (`A.B.m`). |
| **JSON** | `.json` | ✅ (keys, values, arrays) | — (no comment syntax) | — | Numbers with a `+` in the exponent (`6.02E+23`), which the grammar cannot parse on its own, are read as whole values, so `replace_value`, `delete_key` and `add_key` beside them work as for any other number. |
| **YAML** | `.yml`, `.yaml` | ✅ (keys, values, sequences) | ✅ `#` | — | Block and flow sequences supported. Keys inside flow mappings are addressable by path (`a: {x: 1}` is `a.x`, nested ones too), so `read_symbol`, `replace_value` and `delete_key` work on them and they stay inline. `add_key` also adds to flow mappings (`{a: 1}`, `{}`) and to a key with no value (`parent:`). A key with no value can be read (as an empty string), commented, and given a value with `replace_value` (`a: 3`; content of several lines, or a block sequence or mapping, goes below the key one level deeper); an explicit key with no value (`? a`) gets its value on a `: 3` line below it, in the column of the `?`. In a multi-document file a path is looked up in each document in turn (`add_key` with `parent_target=""` adds to the first document with content). Quoted keys are matched by the name they spell, so `'it''s'` is target `it's` and `"caf\u00e9"` is `café`. Removing the only item of a block sequence leaves `key: []`. |
| **TOML** | `.toml` | ✅ (keys, values, arrays, tables) | ✅ `#` | — | `[table]` headers (dotted and quoted ones too, `[tool.uv]`, `[a."b.c"]`) addressable by their names for comment tools and `add_key`. Keys inside inline tables (`t = { a = 1 }` is `t.a`, nested ones too) and dotted keys (`x.y = 1` is `x.y`) are addressable by path. `add_key` also adds to inline tables (`t = { a = 1 }`, `t = {}`). |

**Cross-cutting features:**

- **Decorated functions and classes** (Python and JS/TS `@decorator`, Java annotations): decorators are part of the symbol. They are preserved on body edits; `read_symbol`, `replace_function` and `delete_symbol` include them; a leading comment belongs above the first of them (`edit_leading_comment` puts it there and finds an existing one there), and `insert_sibling(position="before")` goes above them and that comment, so the comment stays on the symbol it documents. This holds for TypeScript methods too, whose decorators the grammar places beside the method in the class body, for decorated Python classes, for a C++ template's `template <...>` header and for a Ruby Sorbet `sig`. `replace_signature` keeps them as written unless the new signature includes its own, which then replace them.
- **Layout-aware `add_method` / `add_field`**: the new member is indented like the class's existing members (falling back to the file's indent unit, then the language default: 4 spaces for Python and Java, a tab for Go, 2 spaces otherwise), keeping the content's relative indentation; in a class indented with tabs that indentation is written in tabs too (one per indentation step of the content), so a snippet written with spaces fits a tab-indented file. The lines that start inside a multi-line string literal of the content (a triple-quoted string, template literal, heredoc, raw string, C string continued with `\`) or a Ruby embedded document (`=begin` ... `=end`, at column 0) keep their text, here and in every tool that re-indents content (`replace_function`, `replace_function_body`, `insert_in_body(at=...)`, `insert_sibling`, `edit_leading_comment`); a Python docstring, a Ruby `<<~` heredoc and a Java text block, whose indentation the language strips, move with the code instead, every line by the same amount. A method follows the last member after one blank line, or none when the class's methods have no blank lines between them (TS interface members stay one per line) or the last member is a C++ access label (`public:`); a field goes before the first member (after a Python class docstring, and below the access label a C++ class body opens with, so it gets that section's access), with a blank line after it when that member is a method (a C++ member template counts), and a comment after the `{` on its line (`class K { // NOLINT`) stays there. In a Java enum both go after the constants, and a `;` is added after them when they have none. No blank line is added before the closing brace, and a braced body on one line (`class K {}`, `class K { a() {} }`, Go `struct{ A int }`) is opened up over several lines, its existing members on a line of their own. A Python or Ruby class written on one line (`class K: pass`) is refused. Both tools look only at containers, so a name a struct or interface shares with a function (`struct stat` and `int stat(...)`) is the struct, and a function target is refused (use `insert_in_body`).
- **Layout-aware `add_key`**: in JSON objects, Python dicts, JS/TS object literals, YAML flow mappings and TOML inline tables the new entry follows the container's layout (one key per line at the existing indentation, inline objects stay inline, a trailing comma is kept, and a comment on the last entry's line stays there); an empty JS/TS or YAML `{}` becomes `{ key: value }` (TOML: `{ key = value }`). A YAML key with no value gets a nested block mapping one indentation level deeper. YAML and TOML keys are quoted only when they need it: `my key` and `a.b` stay plain in YAML, while `a:b`, `yes`, `123` or a leading `-`/`#`/`&` get quotes (in the quote style most of the file uses); in TOML anything but a bare key (letters, digits, `_`, `-`) is quoted, and dots separate the parts of a dotted key, so `b.c` adds `c` under `b` and a name with a dot in it must be passed quoted (`'"example.com"'`). A key the container already has is refused with a pointer to `replace_value`, for every format, naming a target that works (quoted where the key has a dot, inside flow mappings and inline tables too).
- **Layout-aware `append_to_array`**: JSON arrays, TOML arrays, YAML flow sequences and Python lists keep their layout: an inline array stays inline (`[1, 2]` becomes `[1, 2, 3]`, `[]` becomes `[3]`), an array with one element per line gets a new line at the elements' indentation (also one aligned under its `[` whose `]` closes the last line), a trailing comma is kept (the new element gets one too), and comments are not elements: one on the last element's line stays there, after the comma (`2,  # two`), and a value that ends with a comment gets its comma before it (`3,  # new`). A YAML block sequence gets a new `- value` item.
- **Config paths from the top level**: a dotted config target is followed from the top of the file, one key per segment: `a.b` is key `b` under the top-level key `a`, never an `a.b` nested deeper (such as `x.a.b`), and in TOML a plain `version` is a top-level key, not one inside a `[table]` (use `project.version`). One path syntax covers JSON, YAML and TOML and every config tool (`read_symbol`, `replace_value`, `add_key`'s `parent_target`, `delete_key`, `append_to_array`, `remove_from_array` and `edit_leading_comment`): a segment in double quotes is one key taken literally, dots included, its escapes resolved as in a JSON string (`"editor.fontSize"`, `a."b.c".d`), and in TOML single quotes work too (`a.'b.c'`), as in a TOML dotted key, whose syntax TOML paths share. Keys compare by the names they spell, so `"a.b"` finds `a.b: 1`, `'a.b': 1` and `"a.b": 1` in YAML, and `[x.'y.z']` and `[ x . "y.z" ]` are both TOML table `x."y.z"`. Keys inside YAML flow mappings and TOML inline tables are part of the path. Elements of arrays are not addressable by path (`a.0` is a key named `0`).
- **Byte-correct slicing**: multi-byte characters (emoji, `═`, `→`) handled safely in source text.
- **Idempotent imports**: `add_import` skips exact duplicates automatically. A new import goes on the line after the last one (a C/C++ `#include` right after the last include, a conditional of includes counting as one; a CommonJS `require` counts as an import). A first import goes after the file's preamble (a package clause, `#!` and encoding or magic comments, the module docstring, `'use strict'` and other directives, TS `///` lines, `#pragma once`, an include guard's `#define`, and a header comment set off by a blank line), with a blank line above it and one below it (two before a Python def or class). For Go specifically, when a parenthesized `import ( ... )` block already exists, new specs are inserted inside the block rather than as a bare top-level line (which would be a syntax error for spec-only input like `"path/filepath"`).
- **Doc-comment-aware deletion**: `delete_symbol` by default removes the contiguous leading comment block above the symbol (Godoc, Javadoc, `#`/`//` comment runs) so docs don't become orphaned. Opt out with `include_leading_comments=False`. The block ends at a blank line and at a comment line indented deeper than the symbol, which belongs to the code above it (`    # end of f` under f's last line, a commented-out YAML list item), for this and every tool that finds a leading comment: `insert_sibling(position="before")` goes below such a comment, and `edit_leading_comment` neither removes nor replaces it. Such comment lines right below a symbol's last line belong to it: `delete_symbol` removes them with it and `insert_sibling(position="after")` goes below them (`read_symbol` and `replace_function` leave them out). A Ruby `=begin` ... `=end` document directly above a symbol is its leading comment. Only real comments count, for this and every other tool that finds a leading comment: a line that starts with `#` or `//` inside a multi-line string, template literal or YAML block scalar is text. A `#!` line and the encoding or magic comments after it (`# -*- coding: utf-8 -*-`, `# frozen_string_literal: true`) at the top of a Python or Ruby file are never taken for a symbol's comment, by this or any other tool.
- **Layout-aware deletion**: the blank lines that separated a deleted symbol go with it, so the rest keeps the file's spacing: deleting the first symbol of a file or class body leaves no blank lines at the top or after the `{`, deleting the last one leaves none before the closing brace (and the next top-level symbol keeps its own separation, such as Python's two blank lines), and between the two symbols that remain only the wider of the two gaps stays. Only empty lines and lines of spaces and tabs are blank: a form feed line (a Python page break) next to the symbol stays. A symbol that shares a line with other code (`class A { a() {} b() {} }`, `x = 1; y = 2`) is cut out of that line instead, with the `;` or `,` that ends it (the last entry of a one-line literal takes the one before it: `{ a: 1, b: 2 }` minus `b` is `{ a: 1 }`) and a comment after it at the end of the line; the spaces that were before it stay between the code on both sides. `replace_function` likewise replaces only such a symbol's own text, and refuses content that ends with a `#` or `//` comment when code follows the symbol on its line.
- **Syntax-checked saves**: before anything is written, the edited file is re-parsed with its tree-sitter grammar. An edit that would introduce a syntax error into a file that parsed cleanly is refused with the error's line and column (e.g. `Edit refused: the result would have a syntax error at line 11, column 2 (missing '}')`), and the file is left unchanged. Files that already had syntax errors are not guarded, so you can keep working on them. For `.py` files Python's own parser (that of the interpreter running the server) decides: it catches the indentation errors tree-sitter lets through and accepts newer syntax the grammar does not know (PEP 696 type parameter defaults). For `.json` files the `json` module overrules the grammar wherever it would reject valid JSON, and comments in JSONC files stay allowed; exponents written with a `+` (`1e+2`), which tree-sitter-json cannot parse, are masked before parsing, so files that use them are checked like any other. Other languages have no second parser, so valid code using syntax the grammar does not support (very new language features, macro-heavy C/C++) can be refused: if you are sure the code is valid, make that edit with your normal edit tool.
- **Line endings and byte order marks preserved**: CRLF files stay CRLF and LF files stay LF, whichever tool makes the edit, and blank lines at the end of a file are kept as they were (deleting the last symbol does not leave extra ones behind); a file whose last line has no line break keeps it that way. A UTF-8 byte order mark stays at the start of the file, whatever the edit adds or removes at the top; it never shows up in tool output, and content that starts the file with one leaves a single mark. Files that are not UTF-8 (UTF-16, UTF-32, Latin-1), also UTF-16 or UTF-32 without a byte order mark and files with NUL bytes, are refused with a message saying so, and left unchanged. Write content, snippets and anchors with `\n` line breaks: inserted text is converted to the file's style, and a `\n` in a snippet or anchor matches a CRLF line break. Content is split into lines on `\n` (or CRLF) only, so a form feed, vertical tab, U+0085, U+2028 or U+2029 inside a string literal or comment stays where it was written. Only spaces and tabs count as indentation, so when content is re-indented a form feed at the start of a line (a Python page break, `\fdef g():`) or a U+2028 starting a line inside a string stays, and a form feed before the target's own `def` is not copied onto the new lines. A file with mixed endings is written back in the style most of its lines use.

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
| `replace_function` | `file_path`, `target`, `content` | Replace a full function definition (signature + body + decorators, and a JS/TS `export` or C++ `template <...>` header): exactly what `read_symbol` returns, so its text can be edited and given back as is, and given back unchanged leaves the file byte for byte as it was. Content written relative (first line at column 0, the rest indented from it) or at its file indentation is re-indented as before. A comment after the symbol on its last line stays unless the content ends with one, and so does a `;` after it unless the content ends with it (a JS/TS class field's goes when the content is a method). A name declared together with others (`int a = 1, b = 2;`, `struct S {...} s;`) has that declaration replaced, and content that would drop the others is refused. A symbol that shares a line with other code has only its own text replaced (see Layout-aware deletion above). Refused in JSON, YAML and TOML files (use `replace_value`). |
| `replace_function_body` | `file_path`, `target`, `content` | Replace only the body of a function, preserving signature and decorators. A body written on one line with its signature or braces (`function f() { return 1; }`, `def f(): return 1`) is rebuilt over lines of its own, one level deeper than the function, as is content for an empty body (`{` and `}` on lines of their own); a Ruby endless method (`def f = x`) is refused. |
| `replace_signature` | `file_path`, `target`, `new_signature` | Replace only the signature, preserving the body. Existing decorators (Python, JS/TS), Java annotations and a C++ `template <...>` header are kept unless `new_signature` includes its own, which replace them. Indentation on the signature's first line is ignored, so `"def get(self):"` and `"    def get(self):"` both work for a method; the lines after it may be indented relative to it (`"@staticmethod\ndef get(key):"`) or written as `read_symbol(depth="signature")` returns them. For a JS/TS `const f = (a) => {...}`, `"const f = (a, b) =>"` replaces from the `const` on and `"(a, b) =>"` only the function's own part; likewise a closure's key (`handler: (a) =>`), a TS `declare`, a C/C++ `typedef` or `extern "C"`, a Go `type` or `var`, a Ruby `private` and a Sorbet `sig` are replaced by a new signature that starts with its own, and kept otherwise. A method declared without a body (a TS abstract method, a Java interface or abstract method, a C++ `A() = default;`, a Go function without one) is all signature but its final `;`, which stays whether or not `new_signature` ends with one. A Go struct or interface type and an empty Ruby class, module or method take the header `read_symbol(depth="signature")` gives them (`type A struct`); a variable or constant has no signature and is refused. |
| `replace_in_body` | `file_path`, `target`, `old_snippet`, `new_snippet` | Replace a byte-identical snippet inside a function body. Scoped to target's body; raises on multiple matches. |
| `delete_in_body` | `file_path`, `target`, `snippet` | Delete a byte-identical snippet inside a function body. Scoped to target's body; raises on multiple matches. |
| `insert_in_body` | `file_path`, `target`, `new_snippet`, `at` \| `after` \| `before` | Insert a snippet inside a function body. Pass exactly ONE of: `at="top"` (prepend), `at="bottom"` (append), `after=<snippet>` (anchored), `before=<snippet>` (anchored). `at` inserts at the body's own indentation level even when the body ends in a nested block; a Python docstring stays first; a body written on one line with its signature or braces is refused (rewrite it with `replace_function_body`). |
| `add_top_level` | `file_path`, `content`, `position="bottom"` | Insert top-level content. `position="bottom"` appends at end of file (default), in a header inside its include guard, before the `#endif`; `position="top"` inserts after the preamble (as for a first import: package, `#!` and magic comments, directives, imports and includes, a header comment, the Python module docstring, a header's include guard) and before the first real declaration, without splitting a comment from the code it documents. The content is separated from its neighbours by one blank line, two in a Python module when either is a def or class (PEP 8). |
| `add_method` | `file_path`, `class_target`, `content` | Add a method at the end of a class body, indented like the class's members and separated as its methods are (see Layout-aware `add_method` / `add_field` above). |
| `add_field` | `file_path`, `class_target`, `content` | Add a field/attribute/member at the top of a class body (after a Python class docstring or a Java enum's constants, below the access label a C++ class body opens with), indented like the class's members. |
| `insert_sibling` | `file_path`, `target`, `content`, `position` | Insert content as a sibling of a named symbol. `position="before"` or `"after"`; `"before"` goes above the symbol's leading comment block, decorators, a JS/TS `export` and a C++ `template <...>` header. The new code is separated from the target and from the symbol on its other side (with that symbol's comment, decorators and `export`) by one blank line, or two at the top level of a Python module when either is a def or class (PEP 8); the end of a body or file, a C++ access label and a comment above the new code get no added blank lines. `"after"` goes below comment lines right under the target that are indented deeper than it (they end its code). Content is indented in tabs next to a tab-indented target, as for `add_method`. `"before"` is refused when other code comes before the target on its first line, `"after"` when other code follows it on its last line, and empty content is refused, as is the tool in JSON, YAML and TOML files. |
| `delete_symbol` | `file_path`, `target`, `include_leading_comments=True` | Delete a function or class definition block (including decorators, a JS/TS `export` and a C++ `template <...>` header) and the blank lines that separated it (see Layout-aware deletion above). By default also consumes the contiguous leading comment block above the symbol and its decorators (Godoc, Javadoc `/** ... */`, `#` or `//` comments); pass `include_leading_comments=False` to keep it. A Ruby `=begin` document and a Sorbet `sig` above a method go too, and so do comment lines right below the symbol indented deeper than it. A name declared together with others (`int a, *b;`, `struct S {...} s;`, Go `var a, b = 1, 2`, JS `const a = 1, b = 2;`) is refused, naming them, rather than deleted with them. Refused in JSON, YAML and TOML files (use `delete_key`). |

### Parameters & signatures

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `add_parameter` | `file_path`, `target`, `parameter`, `position="end"` | Add a parameter to a function signature (`position`: `"start"` or `"end"`; any other value is refused). A list written one parameter per line (aligned under the first one too) gets the new one on a line of its own at the parameters' indentation, with a trailing comma when the last parameter has one; comments are not parameters and stay on their lines. A list with two parameters on a line gets it inline (`a, b, c`). An empty list over two lines (`def f(\n):`) gets the parameter on a line of its own, one level deeper (with a trailing comma in Go, and in Python, JS and TS as the file's other lists have it). A name the function already has is refused (`Parameter 'a' already exists in 'f'`), names in destructuring patterns and Go groups included. |
| `remove_parameter` | `file_path`, `target`, `parameter_name` | Remove a parameter by name. One on a line of its own goes with that line and the comment at its end; comments on other lines stay (one after the parameter before it too), and removing the only parameter leaves `()`. A Go name of several that share a type goes alone (`func f(a, b int)` minus `a` is `func f(b int)`), the other names keeping their comments; a type-only Go parameter, the receiver and named results are not parameters; a comment after the comma before a last Go name stays. A name bound by a JS/TS or Ruby destructuring parameter goes alone (`{a: x, b}` minus `x` is `{b}`; in an array or Ruby pattern a hole or `_` keeps the positions, `[a, b]` minus `a` is `[, b]`), and the parameter goes when it was its only name. |

### Imports & includes

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `add_import` | `file_path`, `import_text` | Add an `import`/`from`/`#include` line. Skips duplicates. Goes after the last import (a C/C++ `#include` right after the last include, a CommonJS `require` counting as an import); a first import goes after the preamble with a blank line around it (see Idempotent imports above). For Go, if a parenthesized `import ( ... )` block already exists, the spec is inserted inside that block (accepts either `import "foo"` or just `"foo"` / `alias "foo"` as input). |
| `remove_import` | `file_path`, `import_text` | Remove a matching import line. |
| `add_import_name` | `file_path`, `module`, `name` | Add one name to an existing named-import statement: `from <module> import a, b` (Python) or `import { a, b } from "<module>"` (JS/TS). Idempotent. |
| `remove_import_name` | `file_path`, `module`, `name` | Remove one name from a multi-name named-import statement (Python and JS/TS). If the last named import is removed and no default/namespace binding remains, the whole line is removed. |

### Comments & docstrings

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `edit_leading_comment` | `file_path`, `target`, `op`, `comment=""` | Edit the contiguous leading-comment block above a named symbol, which is above its decorators/annotations, a JS/TS `export` and a C++ `template <...>` header; a symbol that other code comes before on its line has none of its own and is refused. `op="add"` inserts (refused if the symbol already has a leading comment; the error quotes it, so a following `op="replace"` can repeat lines worth keeping, such as `// eslint-disable-next-line` or `//go:noinline` directives); `op="replace"` replaces (or inserts if none); `op="remove"` deletes. Works for `#` / `//` / `/* ... */` / Javadoc `/** ... */` and a Ruby `=begin` document; a Ruby Sorbet `sig` is part of its method, so the comment goes above it; a `/* ... */` that follows code on its line (`int x = 1; /* n */`) is not taken as a leading comment. In YAML and TOML the target is a key path (a YAML key with no value too) or a TOML `[table]` by its header's names (`tool.uv`); a key that does not start its line (inside a flow mapping or inline table) is refused, since the comment line above would belong to another key. |
| `replace_docstring` | `file_path`, `target`, `new_docstring` | Replace or insert a Python function/class docstring. Python-only. Inserting one into a body on its signature's line (`def f(): return 1`) is refused: rewrite the body with `replace_function_body`. |

### Dict/list editing (JSON, YAML, TOML, Python module-level dict/list literals, AND JS/TS object literals)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `replace_value` | `file_path`, `target`, `content` | Replace the value of an existing key. Targets as for `delete_key`: JSON/YAML/TOML dotted path from the top level (`"editor.fontSize"` for a key with dots; keys inside YAML flow mappings and TOML inline tables too, which stay inline); Python `DictName.keyExpr`; JS/TS `VarName.key` (a shorthand `{ key }` becomes `key: <content>`). A YAML key with no value (`a:`) gets one (`a: 3`, or a nested block below the key for content of several lines or a block sequence or mapping; a first line that is only `|`, `>-`, an `&anchor` or a `!tag` stays after the colon). In source files it also replaces the value of a variable, constant or field (Python `X = 1`, JS/TS `const X = 1;` and class fields `A.x`, Go `var`/`const`, C/C++ globals, fields and macros, Java fields, Ruby constants): only the value, and a declaration without one gets one (`let x;` becomes `let x = 2;`); a function or class, a name that shares one value with others (`a = b = 1`) and one that cannot have a value (`extern`, `declare`, an abstract field) are refused. |
| `add_key` | `file_path`, `parent_target`, `key`, `value` | Add a key-value pair to a dict/object/mapping/table. For config, `parent_target` is a dotted path from the top level (use `""` for root; a TOML `[table]` by its header's names, `a."b.c"` for `[a.'b.c']`); YAML flow mappings (nested ones too) and keys with no value and TOML inline tables work too. For JSON and YAML `key` is one name, dots included. For Python it is the dict variable name; for JS/TS the name of a module-level `const`/`let`/`var` (or `export const`) object literal, `as const` / `satisfies` included. Both may continue into nested literals (`CONFIG."db"`, `CONFIG.server`). JSON keys are quoted for you, YAML and TOML keys only when they need it (in TOML, dots make a dotted key), JS/TS keys only when they are not valid identifiers, Python keys are key expressions (`'"timeout"'`). The entry follows the container's layout (one per line, inline, trailing comma), and a key that already exists is refused (use `replace_value`). |
| `delete_key` | `file_path`, `target` | Delete a key-value pair. Targets: JSON/YAML/TOML dotted path from the top level (`"editor.fontSize"` for a key with dots; keys inside YAML flow mappings and TOML inline tables too, cut like JSON entries with their comma); Python `DictName.keyExpr`; JS/TS `VarName.keyName` on `const`/`let`/`var` or `export const` object literals (handles regular pairs, `{ key }` shorthand, methods, and quoted `"complex-key"`). Python and JS/TS paths may continue into nested literals (`CONFIG.server.port`). For JSON, Python and JS/TS, the adjacent comma is also removed (an entry on its own line goes with that whole line, including its same-line comment), and deleting the only entry leaves `{}`. |
| `append_to_array` | `file_path`, `target`, `value` | Append a literal value to a list/array/sequence. For Python, `target` is the list variable name; for config, a dotted path from the top level. The array keeps its layout: inline stays inline (`[1, 2, 3]`), one element per line gets a new line at the elements' indentation, and a trailing comma is kept; comments are not elements, and the new element's comma goes before a comment (see Layout-aware `append_to_array` above). |
| `remove_from_array` | `file_path`, `target`, `value_match` | Remove the first matching element from a list/array/sequence. Comments are not elements: one on its own line goes with that line and the comment at its end, comments on other lines stay (one above it, or after the element before it, too), the trailing-comma style is kept, and removing the only element leaves `[]` (a YAML block sequence becomes `key: []`). |

### Navigation & reading (read-only)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_symbols` | `file_path` | Formatted outline of all top-level functions, classes, methods and data with line numbers (a symbol's line is that of its first decorator, `export`, Ruby Sorbet `sig` or first overload signature). JS/TS exported declarations are listed under their own names, an anonymous default export as `default`; generators and functions bound to a `const`/`let`/`var` as `function`, other `const` names as `constant`, `let`/`var` names as `variable` and class fields as `field`, TS abstract classes as `class` (with their abstract methods), and TS enums, type aliases, interfaces and namespaces as `enum`, `type`, `interface` and `namespace`. Nested classes are listed under their containers with their members (`class A.B`, `method A.B.m`), as are Python module variables and class attributes, Ruby constants and locals, C/C++ fields, macros, typedefs, globals, destructors and operators, Java fields and Go type aliases and variables (see the language table). Of a name a scope declares more than once, the target is listed, once. In C, C++, Java, JS and TS every entry is listed under the target that finds it at the listed line: overloads with their parameter types (`method A.m(int) (line 2)`), a method beside a field of its name as `A.x()`, a C++ definition outside its class by its qualified name (`function A::f`), and a tag or type that shares its name with another symbol after its keyword, so the line reads `struct struct stat (line 1)` or `type type User (line 2)`; an entry no target reaches is left out. In Python and Ruby a name defined again is listed again, and the name targets the first. |
| `find_references` | `file_path`, `target` | Syntactic search for all occurrences of an identifier (no scope awareness), listed in file order, by line and column. |
| `read_symbol` | `file_path`, `target`, `depth="full"` | Return source text of a single named symbol. `depth` controls how much: `"full"` returns the entire source (typically **10-20x fewer tokens** than the whole file), from its first byte, so the later lines keep their file indentation: exactly what `replace_function` and `delete_symbol` take (with a Go `type`/`var`/`const`, a closure's key, a TS `declare`, the C typedef or declaration around a struct, a Ruby `private`, a TS abstract method's `;`), ready to be edited and given back to `replace_function` as is; `"interface"` returns a class stub (header + fields + method sigs with `...`, each member at its indentation relative to the class header and ending as written, with its `;` or `,`; a C/C++ class closes with `};`) or a function's signature; `"signature"` returns signature-only (a method with no body, such as a TS abstract or Java interface method or a C++ `A() = default;`, is its whole declaration, and a Go struct its header, `type A struct`). Both start where the full text starts, except that a function's or class's signature leaves out its decorators and a JS/TS `export` (`handler: () =>`, `RunE: func() error`, `declare function f(a: number): void`, `extern "C" int f(int a)`, `private def m(x)`, `typedef struct N`), and a closure's interface is its signature. A TS overload group and a Python `@overload` group give the implementation's signature, a Ruby endless method its part before the `=`. Both refuse a variable, constant, field, type alias, macro or C/C++ forward declaration, saying what it is (`'X' is a constant, which has no signature ...; read it with depth='full'`). For a config key path, `"full"` returns the key's value (an empty string for a YAML key with no value). |
| `read_imports` | `file_path` | Return all import/include statements in the file. |

**Target format:** Use the exact function name (e.g., `get`) or dotted `Class.method` path (e.g., `LRUCache.get`). In C, C++ and Java an overload takes its parameter types (`A.m(int, String)`, `A.m()`, C `f(void)` being `f()`), a C++ definition outside its class its qualified name (`A::f`), and a name that a field shares with methods targets the field (the method is `A.x()`). A C/C++ tag or TS type alias or interface that shares its name with another symbol takes its keyword (`struct stat`, `union u`, `class C`, `type User`, `interface Props`), in front of a dotted path (`type N.User`). JS/TS exported declarations are targeted by their own names (`export function add` is `add`); an anonymous `export default function/class` is `default` (and its methods `default.run`), and `const f = () => {...}` is `f`. Decorated functions are fully supported — decorators are preserved when replacing bodies or signatures, and included when deleting or replacing the full function.

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

Coding agents are heavily biased toward their default tools. You **must** explicitly instruct them to use `ast-editor` when editing code and config files. The agent prompt lives in [`AST-EDITOR.md`](./AST-EDITOR.md) — a standalone file you wire into your agent's system instructions. The server also sends a condensed version of this guidance (at most 1,500 characters: start with `list_symbols`, how to target overloads and a struct or type that shares its name, pick the narrowest tool, what to do when an edit is refused for a syntax error, and the escape hatches) as MCP server `instructions`, which some clients, Claude Code among them, pass to the model automatically alongside any prompt file. Wiring in the full prompt file is still recommended. After updating the server, copy the new `AST-EDITOR.md` over the one you installed (for example `~/.claude/AST-EDITOR.md`), since an installed copy does not update itself.

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
