import logging
import os
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from ast_editor.applier import Applier, ApplierError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("ast-editor")

# Condensed form of AST-EDITOR.md, sent to clients as MCP server instructions.
_INSTRUCTIONS = (
    "AST-targeted edits for .py .js .ts .c .cpp .rb .go .java .json .yaml "
    ".toml files: prefer these over text edits there. file_path must be "
    "absolute.\n\n"
    "Call list_symbols first for exact, case-sensitive targets "
    "(Class.method, overloads as A.m(int)), read_symbol to read one symbol "
    "(replace_function takes its text back as is), find_references before "
    "a rename. Config targets are key paths from the top level "
    "(project.version); quote a key with dots (\"editor.fontSize\").\n\n"
    "Use the narrowest tool: replace_in_body, insert_in_body or "
    "delete_in_body for a few lines, not replace_function or "
    "replace_function_body; add_parameter or remove_parameter for one "
    "parameter; add_key for a new key, replace_value for an existing one; "
    "add_import_name to extend an import.\n\n"
    "Every edit is parse-checked: one that would add a syntax error is "
    "refused and the file is left unchanged. For valid code the parser "
    "does not support, or sub-expression edits, use your normal edit tool; "
    "for whole-file rewrites, your write tool."
)


def _server_version() -> str:
    try:
        return _pkg_version("ast-editor-mcp")
    except PackageNotFoundError:
        return "0.0.0"


mcp = MCPServer(
    "AST-Code-Editor", instructions=_INSTRUCTIONS, version=_server_version()
)

# Tool annotation presets. Every tool works on one local file, so none is
# open-world; additive tools only insert code (the file is rewritten, keeping
# its line endings), destructive ones can also overwrite or delete existing
# text.
_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
_ADDITIVE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
_DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

# Parameter types shared by several tools; the descriptions become part of
# each tool's inputSchema.
FilePath = Annotated[
    str, Field(description="Absolute path to the source or config file.")
]
FunctionTarget = Annotated[
    str,
    Field(
        description="Function or method name as list_symbols lists it, "
        "dotted for nesting ('LRUCache.get'); overloads take parameter "
        "types ('A.m(int)')."
    ),
]
ClassTarget = Annotated[
    str,
    Field(
        description="Class name as list_symbols lists it (a struct, "
        "interface or Go struct type too), dotted for nesting ('A.B')."
    ),
]
BodySnippet = Annotated[
    str,
    Field(
        description="Text in the target's body, matching one place: its "
        "exact text at token boundaries, or else whole lines with the same "
        "indentation added to or removed from each."
    ),
]
LiteralValue = Annotated[
    str,
    Field(
        description="Value as source text in the file's syntax, strings "
        "quoted (e.g. '\"2.0.0\"' or '42')."
    ),
]
ArrayTarget = Annotated[
    str,
    Field(
        description="Key path from the top level to a JSON, YAML or TOML "
        "array ('project.dependencies'), or a Python module-level list's "
        "name."
    ),
]
ImportModule = Annotated[
    str,
    Field(
        description="Module of the import as written, without quotes "
        "(e.g. 'typing' or './utils')."
    ),
]
ImportName = Annotated[str, Field(description="One imported name, e.g. 'Optional'.")]


def _validate_file(file_path: str) -> str | None:
    """Return an error message if file_path is invalid, else None."""
    if not os.path.isabs(file_path):
        return f"file_path must be an absolute path, got: {file_path}"
    if not os.path.isfile(file_path):
        return f"File not found: {file_path}"
    return None


@mcp.tool(annotations=_DESTRUCTIVE)
def replace_function(
    file_path: FilePath,
    target: FunctionTarget,
    content: Annotated[
        str,
        Field(
            description="Complete new source of the symbol, decorators "
            "included, in read_symbol's shape or written from column 0."
        ),
    ],
) -> str:
    """
    Replace a whole symbol (decorators, signature and body) with new content.
    The replaced span is what read_symbol returns: decorators, a JS/TS
    `export`, a C++ `template <...>` header and code that only wraps the
    symbol are part of it, so keep them in content. read_symbol's text,
    edited or not, goes in as it is, and may become several members;
    content written from column 0 is re-indented to the symbol's level. A
    symbol that shares a line with other code has only its own text
    replaced. For one name of `int a, b;` the content must keep the others.
    Refused in JSON, YAML and TOML files (use replace_value).

    Use this when: rewriting a symbol top to bottom (name, parameters and body).
    Don't use this when: only the body changes (replace_function_body), only
    the signature (replace_signature), or a few lines (replace_in_body).

    Example:
        target="LRUCache.get"
        content='def get(self, key, default=None):\\n    return self.items.get(key, default)'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_function: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.replace_function(target, content)
        return "Updated"
    except ApplierError as e:
        logger.warning("replace_function: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("replace_function crashed")
        return f"Internal error in replace_function: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def replace_function_body(
    file_path: FilePath,
    target: FunctionTarget,
    content: Annotated[
        str,
        Field(
            description="New body statements without the signature or "
            "braces, re-indented as a block to the body's indentation."
        ),
    ],
) -> str:
    """
    Replace only the body of a function, keeping its signature and decorators.
    A body on its signature's line is rebuilt over lines of its own, and an
    empty body gets content one level deeper than the function. A Ruby
    method's rescue, else and ensure clauses stay and only the code before
    them is replaced, unless content has clauses of its own. Refused for a
    function without a block body: a Ruby endless method, or an arrow
    function whose body is an expression (use replace_function).

    Use this when: changing the implementation but not the interface.
    Don't use this when: the parameters or return type change too
    (replace_function), or only a few lines change (replace_in_body).

    Example:
        target="LRUCache.get"
        content='if key in self.items:\\n    return self.items[key]\\nreturn None'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_function_body: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.replace_function_body(target, content)
        return "Updated"
    except ApplierError as e:
        logger.warning("replace_function_body: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("replace_function_body crashed")
        return f"Internal error in replace_function_body: {type(e).__name__}: {e}"

@mcp.tool(annotations=_DESTRUCTIVE)
def replace_in_body(
    file_path: FilePath,
    target: FunctionTarget,
    old_snippet: BodySnippet,
    new_snippet: Annotated[
        str,
        Field(
            description="Replacement text; its lines move with the match's "
            "indentation, keeping their relative indentation, and text "
            "already at the file's indentation goes in as written. '' "
            "deletes the snippet."
        ),
    ],
) -> str:
    """
    Replace a snippet inside a function's body; the match is scoped to that
    body, so text elsewhere in the file never matches. A snippet found
    nowhere is refused; one found in several places is refused with their
    line numbers: add context.

    Use this when: changing one statement or block in a long body.
    Don't use this when: replacing the whole body (replace_function_body),
    or editing a sub-expression no unique snippet can locate (your normal
    edit tool).

    Example (a block written without its indentation):
        target="handle"
        old_snippet="if retry:\\n    wait()"
        new_snippet="if retry:\\n    backoff()\\n    wait()"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_in_body: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.replace_in_body(target, old_snippet, new_snippet)
        return "Updated"
    except ApplierError as e:
        logger.warning("replace_in_body: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("replace_in_body crashed")
        return f"Internal error in replace_in_body: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def delete_in_body(
    file_path: FilePath, target: FunctionTarget, snippet: BodySnippet
) -> str:
    """
    Delete a snippet inside a function's body, matched as replace_in_body
    matches one. A deletion that empties its lines removes them whole; a
    comment after the snippet on its last line stays. One that would leave
    a Python body without a statement is refused (replace the snippet with
    `pass`).

    Use this when: removing a statement, block or line in a body, or an
    entry of an object literal passed as an argument.
    Don't use this when: deleting a whole function or class (delete_symbol).

    Example:
        target="RegisterRoutes"
        snippet='r.Mount("/kb", kbHandler)'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("delete_in_body: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.delete_in_body(target, snippet)
        return "Deleted"
    except ApplierError as e:
        logger.warning("delete_in_body: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("delete_in_body crashed")
        return f"Internal error in delete_in_body: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def insert_in_body(
    file_path: FilePath,
    target: FunctionTarget,
    new_snippet: Annotated[
        str,
        Field(
            description="Text to insert. With at, re-indented as a block to "
            "the body's indentation; with after or before, indented like the "
            "anchor (as written when already at the file's indentation there)."
        ),
    ],
    after: Annotated[
        str,
        Field(
            description="Anchor in the body to insert after; '' (default) "
            "leaves this mode unused."
        ),
    ] = "",
    before: Annotated[
        str,
        Field(
            description="Anchor in the body to insert before; '' (default) "
            "leaves this mode unused."
        ),
    ] = "",
    at: Annotated[
        str,
        Field(
            description="'top' or 'bottom' of the body; '' (default) leaves "
            "this mode unused. Other values are refused."
        ),
    ] = "",
) -> str:
    """
    Insert new_snippet inside a function's body. Set exactly one of `at`,
    `after` or `before`. `at="top"` goes after a Python docstring,
    `at="bottom"` at body level after the last statement, and in an empty
    body one level deeper than the function; `at` is refused for a body on
    its signature's line (use replace_function_body).

    An anchor is matched as replace_in_body matches a snippet and must be
    unique. One that ends its line (after) or starts it (before) gets
    new_snippet on lines of its own; after a line that opens a block (`if
    x:`, `if (x) {`), new lines go inside the block. A mid-line anchor gets
    new_snippet byte for byte.

    Use this when: adding lines to a body.
    Don't use this when: replacing the whole body (replace_function_body),
    changing existing lines (replace_in_body), or adding a top-level symbol
    (add_top_level).

    Example (both written without indentation):
        target="handle"
        new_snippet='auth_check(request)'
        before='validate(request)'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "insert_in_body: target='%s' file='%s' mode=%s",
            target,
            file_path,
            "at=" + at if at else ("after" if after else ("before" if before else "none")),
        )
        applier = Applier(file_path)
        applier.insert_in_body(
            target,
            new_snippet,
            at=at if at else None,
            after=after if after else None,
            before=before if before else None,
        )
        return "Added"
    except ApplierError as e:
        logger.warning("insert_in_body: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("insert_in_body crashed")
        return f"Internal error in insert_in_body: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def add_method(
    file_path: FilePath,
    class_target: ClassTarget,
    content: Annotated[
        str,
        Field(
            description="Complete method source, re-indented like the "
            "class's members, keeping its own relative indentation."
        ),
    ],
) -> str:
    """
    Add a method at the end of a class body, after its last member, spaced
    like the class's methods. In Go it goes after the type declaration. In
    a C++ class whose last method is followed by an access label, it goes
    right after that method, so it gets the same access. A one-line Python
    or Ruby class is refused, and so is a function target (use
    insert_in_body).

    Use this when: adding a method to an existing class.
    Don't use this when: adding a field (add_field) or a top-level function
    (add_top_level).

    Example:
        class_target="LRUCache"
        content='def clear(self):\\n    self.items.clear()'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("add_method: class='%s' file='%s'", class_target, file_path)
        applier = Applier(file_path)
        applier.add_method(class_target, content)
        return "Added"
    except ApplierError as e:
        logger.warning("add_method: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("add_method crashed")
        return f"Internal error in add_method: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def delete_symbol(
    file_path: FilePath,
    target: Annotated[
        str,
        Field(
            description="Symbol name as list_symbols lists it, dotted for "
            "nesting (e.g. 'LRUCache.old_method', 'A.m(int)')."
        ),
    ],
    include_leading_comments: Annotated[
        bool,
        Field(
            description="True (default) also deletes the comment block above "
            "the symbol, or before it on its first line; false keeps it."
        ),
    ] = True,
) -> str:
    """
    Delete a whole function, method, class or other symbol, with its
    decorators, a JS/TS `export` and a C++ `template <...>` header. The
    blank lines that set it apart go too, so the file keeps its spacing. A
    symbol that shares a line with other code is cut out of the line. One
    name of a declaration of several (`int a, b;`, `struct S {...} s;`) is
    refused: give replace_function the declaration without it. Refused in
    JSON, YAML and TOML files (use delete_key).

    Use this when: removing a symbol along with its doc comment.
    Don't use this when: removing a config key (delete_key), an import
    (remove_import) or lines inside a body (delete_in_body).

    Example:
        target="LRUCache.old_method"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("delete_symbol: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.delete_symbol(target, include_leading_comments=include_leading_comments)
        return "Deleted"
    except ApplierError as e:
        logger.warning("delete_symbol: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("delete_symbol crashed")
        return f"Internal error in delete_symbol: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def replace_value(
    file_path: FilePath,
    target: Annotated[
        str,
        Field(
            description="Key path from the top level in a config file "
            "('project.version'; quote a key with dots, "
            "'\"editor.fontSize\"'; keys in YAML flow mappings and TOML "
            "inline tables count, 'a.x'), a path into a Python or JS/TS "
            "module-level dict or object ('CONFIG.\"timeout\"', "
            "'CONFIG.server.port'), or a variable, constant, field or macro "
            "name ('MAX', 'A.x')."
        ),
    ],
    content: LiteralValue,
) -> str:
    """
    Replace the value of an existing config key, dict or object entry, or
    of a variable, constant, field or macro in a source file (`X = 1`,
    `const X = 1;`, `int x = 1;`, `#define N 3`). Only the value changes; a
    declaration without one gets one (`let x;` becomes `let x = 2;`, YAML
    `a:` becomes `a: 2`). Refused: a function, class or type (use
    replace_function), a name sharing one value with others (`a = b = 1`)
    and a declaration that cannot have a value (`extern`, TS `declare`).
    Array elements are not addressable.

    Use this when: updating a value that exists.
    Don't use this when: the key is new (add_key), or you edit an array
    (append_to_array, remove_from_array).

    Example:
        target="project.version"
        content='"2.0.0"'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_value: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.replace_value(target, content)
        return "Updated"
    except ApplierError as e:
        logger.warning("replace_value: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("replace_value crashed")
        return f"Internal error in replace_value: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def add_import(
    file_path: FilePath,
    import_text: Annotated[
        str,
        Field(
            description="Complete import line in the file's language (e.g. "
            "'import os', '#include <stdlib.h>'); in Go a bare spec "
            "('\"fmt\"') works too."
        ),
    ],
) -> str:
    """
    Add an import line, skipping an exact duplicate. It goes into the group
    of imports it belongs with (same package, standard library or not,
    relative or not), at its sorted place when the group is sorted, else
    after the group's last import. A comment heading the group stays first
    (a next-line directive stays on its import), and so do Python `from
    __future__` imports. With no fitting group it goes after the last
    import, and a first import after the preamble.

    Use this when: importing something the file does not import yet.
    Don't use this when: adding a name to an existing import
    (add_import_name).

    Example:
        import_text="from typing import Optional"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("add_import: file='%s' import='%s'", file_path, import_text)
        applier = Applier(file_path)
        result = applier.add_import(import_text)
        return "Skipped (duplicate)" if "already exists" in result else "Added"
    except ApplierError as e:
        logger.warning("add_import: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("add_import crashed")
        return f"Internal error in add_import: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_import(
    file_path: FilePath,
    import_text: Annotated[
        str,
        Field(description="Exact import line to remove (e.g. 'import os')."),
    ],
) -> str:
    """
    Remove an import line, matched by its text with surrounding whitespace
    stripped.

    Use this when: removing an unused import.
    Don't use this when: removing one name from a multi-name import
    (remove_import_name).

    Example:
        import_text="import os"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("remove_import: file='%s' import='%s'", file_path, import_text)
        applier = Applier(file_path)
        applier.remove_import(import_text)
        return "Removed"
    except ApplierError as e:
        logger.warning("remove_import: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("remove_import crashed")
        return f"Internal error in remove_import: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def add_key(
    file_path: FilePath,
    parent_target: Annotated[
        str,
        Field(
            description="Parent container: its key path from the top level "
            "in a config file ('' for the root; quote a key with dots, "
            "'a.\"b.c\"'), or a Python or JS/TS module-level variable's "
            "name, dotted into nested literals ('CONFIG.server')."
        ),
    ],
    key: Annotated[
        str,
        Field(
            description="Key to add. JSON, YAML and JS/TS: one name, quoted "
            "for you when needed. TOML: a dotted key, so quote a name with a "
            "dot yourself ('\"example.com\"'). Python: a key expression, so "
            "quote string keys ('\"timeout\"')."
        ),
    ],
    value: LiteralValue,
) -> str:
    """
    Add a key-value pair to a JSON object, YAML mapping, TOML table, Python
    dict literal or JS/TS object literal. The entry follows the container's
    layout: one key per line stays so, an inline object stays inline, and a
    trailing comma is kept. A YAML key with no value gets a nested mapping.
    A key the container already has is refused, naming the target to give
    replace_value.

    Use this when: the key does not exist yet.
    Don't use this when: the key exists (replace_value), or you add a list
    item (append_to_array).

    Example (TS, const CONFIG = { server: {...} }):
        parent_target="CONFIG.server"
        key="port"
        value="8080"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "add_key: file='%s' parent='%s' key='%s'", file_path, parent_target, key
        )
        applier = Applier(file_path)
        applier.add_key(parent_target, key, value)
        return "Added"
    except ApplierError as e:
        logger.warning("add_key: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("add_key crashed")
        return f"Internal error in add_key: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def delete_key(
    file_path: FilePath,
    target: Annotated[
        str,
        Field(
            description="Key path from the top level in a config file "
            "('dependencies.tree-sitter'; quote a key with dots, "
            "'\"editor.fontSize\"'), or a path into a Python or JS/TS "
            "module-level dict or object ('CONFIG.\"timeout\"', "
            "'CONFIG.server.port')."
        ),
    ],
) -> str:
    """
    Delete a key-value pair from a config file, or from a Python or JS/TS
    module-level dict or object literal. The adjacent comma goes too where
    the syntax has one, and deleting the only entry leaves `{}`; YAML and
    TOML keys otherwise go with their lines.

    Use this when: removing a whole entry.
    Don't use this when: removing a list item (remove_from_array), or an
    entry of an object literal passed as an argument (delete_in_body).

    Example:
        target='CONFIG."timeout"'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("delete_key: file='%s' target='%s'", file_path, target)
        applier = Applier(file_path)
        applier.delete_key(target)
        return "Deleted"
    except ApplierError as e:
        logger.warning("delete_key: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("delete_key crashed")
        return f"Internal error in delete_key: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def append_to_array(
    file_path: FilePath, target: ArrayTarget, value: LiteralValue
) -> str:
    """
    Append a value to a JSON, YAML or TOML array or a Python module-level
    list. The value follows the array's layout: an inline array stays
    inline (`[1, 2]` becomes `[1, 2, 3]`), one element per line gets a new
    line, and a trailing comma is kept. Comments are not elements: the
    comma goes before them.

    Use this when: adding a list item.
    Don't use this when: adding a key-value pair (add_key).

    Example:
        target="project.dependencies"
        value='"new-package"'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("append_to_array: file='%s' target='%s'", file_path, target)
        applier = Applier(file_path)
        applier.append_to_array(target, value)
        return "Added"
    except ApplierError as e:
        logger.warning("append_to_array: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("append_to_array crashed")
        return f"Internal error in append_to_array: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_from_array(
    file_path: FilePath,
    target: ArrayTarget,
    value_match: Annotated[
        str,
        Field(
            description="Element to remove, compared with each element's "
            "source text, whitespace stripped (e.g. '\"old-package\"')."
        ),
    ],
) -> str:
    """
    Remove the first element matching value_match from a JSON, YAML or
    TOML array or a Python module-level list. An element on a line of its
    own goes with that line and its comment; other comments stay. The
    trailing-comma style is kept, and removing the only element leaves
    `[]`.

    Use this when: removing one list item.
    Don't use this when: removing a whole key (delete_key).

    Example:
        target="project.dependencies"
        value_match='"old-package"'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "remove_from_array: file='%s' target='%s' value='%s'",
            file_path,
            target,
            value_match,
        )
        applier = Applier(file_path)
        applier.remove_from_array(target, value_match)
        return "Removed"
    except ApplierError as e:
        logger.warning("remove_from_array: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("remove_from_array crashed")
        return f"Internal error in remove_from_array: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def add_field(
    file_path: FilePath,
    class_target: ClassTarget,
    content: Annotated[
        str,
        Field(
            description="Field or member declaration as source text (e.g. "
            "'version = \"1.0\"' or Go 'version int')."
        ),
    ],
) -> str:
    """
    Add a field or member at the top of a class body: before the first
    member, after a Python class docstring or a Java enum's constants
    (adding the `;` they need), and below the access label a C++ class
    opens with. It is indented like the class's members, with a blank line
    after it when a method follows. A function target is refused.

    Use this when: adding a class attribute, field or member variable.
    Don't use this when: adding a method (add_method).

    Example:
        class_target="LRUCache"
        content='version = "1.0"'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("add_field: class='%s' file='%s'", class_target, file_path)
        applier = Applier(file_path)
        applier.add_field(class_target, content)
        return "Added"
    except ApplierError as e:
        logger.warning("add_field: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("add_field crashed")
        return f"Internal error in add_field: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def replace_signature(
    file_path: FilePath,
    target: FunctionTarget,
    new_signature: Annotated[
        str,
        Field(
            description="Everything from the start of the definition up to "
            "its body, as read_symbol(depth='signature') returns it (e.g. "
            "'def get(self, key):', JS 'get(key, d)' without the '{'); "
            "indentation on its first line is ignored."
        ),
    ],
) -> str:
    """
    Replace the signature of a function, or the header of a class, keeping
    its body. Existing decorators, Java annotations and a C++ `template
    <...>` header stay unless new_signature has its own. Code that
    read_symbol's signature starts with (a JS/TS `const f =`, a closure's
    key, a TS `declare`, a Ruby `private`) is replaced when new_signature
    starts with it, else kept. A method without a body keeps its `;`.
    Refused for a symbol with no signature, such as a variable.

    Use this when: changing a function's parameters, return type or name.
    Don't use this when: the body changes too (replace_function), or one
    parameter is added or removed (add_parameter, remove_parameter).

    Example:
        target="LRUCache.get"
        new_signature="def get(self, key, default=None):"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_signature: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.replace_signature(target, new_signature)
        return "Updated"
    except ApplierError as e:
        logger.warning("replace_signature: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("replace_signature crashed")
        return f"Internal error in replace_signature: {type(e).__name__}: {e}"


@mcp.tool(annotations=_READ_ONLY)
def list_symbols(file_path: FilePath) -> str:
    """
    List the symbols of a source file, one per line as `<kind> <name> (line
    N)`, class members indented under their class (`method A.B.m`). Each
    name is the target the other tools take: overloads with their
    parameter types (`A.m(int)`), a C++ definition outside its class by
    its qualified name (`A::f`), and a struct or TS type that shares its
    name with another symbol after its keyword (`struct struct stat`
    targets `struct stat`). Kinds include function, method, class, struct,
    enum, interface, namespace, type, macro, field, variable and constant;
    a Go `var x = func(...) {...}`, listed as a variable, also takes the
    body, parameter and signature tools. A name with a prototype or
    forward declaration is listed once, at its definition. Read-only.

    Use this when: before editing a file, to get exact target names.
    Don't use this when: you already know the target (read_symbol reads
    one symbol).

    Example:
        file_path="/abs/path/to/module.py"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("list_symbols: file='%s'", file_path)
        applier = Applier(file_path)
        return applier.list_symbols()
    except ApplierError as e:
        logger.warning("list_symbols: %s", e)
        return f"Cannot list symbols: {e}"
    except Exception as e:
        logger.exception("list_symbols crashed")
        return f"Internal error in list_symbols: {type(e).__name__}: {e}"












@mcp.tool(annotations=_ADDITIVE)
def add_import_name(
    file_path: FilePath, module: ImportModule, name: ImportName
) -> str:
    """
    Add a name to an existing `from <module> import ...` (Python) or
    `import { ... } from "<module>"` (JS/TS) statement; a name already
    there is left as is. It goes at its sorted place when the names are
    sorted (plainly or as isort and ruff sort them), else at the end, in the
    list's layout: names one per line give it a line of its own, an inline
    list stays inline. Refused when the file has no such import.

    Use this when: the module is already imported with named imports.
    Don't use this when: there is no such import yet, or for a default or
    namespace import (add_import with the full line).

    Example (`from typing import Any, cast` becomes `Any, Dict, cast`):
        module="typing"
        name="Dict"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "add_import_name: module='%s' name='%s' file='%s'", module, name, file_path
        )
        applier = Applier(file_path)
        applier.add_import_name(module, name)
        return "Added"
    except ApplierError as e:
        logger.warning("add_import_name: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("add_import_name crashed")
        return f"Internal error in add_import_name: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_import_name(
    file_path: FilePath, module: ImportModule, name: ImportName
) -> str:
    """
    Remove one name from a `from <module> import ...` (Python) or `import
    { ... } from "<module>"` (JS/TS) statement. A name on a line of its own
    goes with that line and its comment. Removing the only name removes the
    statement, but is refused when a default import would be left with
    empty braces (`import D, { a } from "m"`): use remove_import, then
    add_import.

    Use this when: dropping one name from a multi-name import.
    Don't use this when: removing the whole import line (remove_import).

    Example:
        module="typing"
        name="List"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "remove_import_name: module='%s' name='%s' file='%s'",
            module,
            name,
            file_path,
        )
        applier = Applier(file_path)
        applier.remove_import_name(module, name)
        return "Removed"
    except ApplierError as e:
        logger.warning("remove_import_name: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("remove_import_name crashed")
        return f"Internal error in remove_import_name: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def add_parameter(
    file_path: FilePath,
    target: FunctionTarget,
    parameter: Annotated[
        str,
        Field(
            description="Source text of one parameter (e.g. 'default=None', "
            "'const int* buf'); the comma is added for you."
        ),
    ],
    position: Annotated[
        str,
        Field(
            description="'end' (default) after the last parameter, before "
            "any that must stay last; 'start' before the first. Other values "
            "are refused."
        ),
    ] = "end",
) -> str:
    """
    Add one parameter to a function's signature, keeping the body. "end"
    puts it after the last parameter but before those that must come after
    it (Python `**kwargs`, a JS/TS rest parameter, Go and Java variadics,
    C/C++ `...`, Ruby `**opts` and `&blk`); "start" before the first, but
    after a TS `this` or Java receiver parameter. A list written one
    parameter per line gets it on a line of its own, a C `(void)` takes it
    in place of `void`, and a bare JS/TS arrow parameter gets parentheses.
    A name the function already has is refused.

    Use this when: adding a parameter without retyping the signature.
    Don't use this when: rewriting the signature (replace_signature), or
    changing the body too (replace_function).

    Example (`def f(a, **kw)` becomes `def f(a, b, **kw)`):
        target="f"
        parameter="b"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "add_parameter: target='%s' param='%s' file='%s'",
            target,
            parameter,
            file_path,
        )
        applier = Applier(file_path)
        applier.add_parameter(target, parameter, position)
        return "Added"
    except ApplierError as e:
        logger.warning("add_parameter: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("add_parameter crashed")
        return f"Internal error in add_parameter: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_parameter(
    file_path: FilePath,
    target: FunctionTarget,
    parameter_name: Annotated[
        str,
        Field(
            description="Bare name of the parameter (e.g. 'default'), "
            "without its type or default value."
        ),
    ],
) -> str:
    """
    Remove a parameter by name from a function's signature, keeping the
    body. A parameter on a line of its own goes with that line and its
    comment. Removing the only one leaves `()`, or `(void)` in C. In Python
    a `*` or `/` left invalid goes too, and a `*args` with keyword-only
    parameters after it leaves a bare `*` (`def f(a, *args, b)` minus args
    is `def f(a, *, b)`). One Go name of `a, b int`, or one name that a
    destructuring parameter binds, goes alone. Refused: a name the function
    lacks, and in C the last named parameter before `...`.

    Use this when: dropping one parameter without retyping the signature.
    Don't use this when: rewriting the signature (replace_signature).

    Example:
        target="LRUCache.get"
        parameter_name="default"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "remove_parameter: target='%s' param='%s' file='%s'",
            target,
            parameter_name,
            file_path,
        )
        applier = Applier(file_path)
        applier.remove_parameter(target, parameter_name)
        return "Removed"
    except ApplierError as e:
        logger.warning("remove_parameter: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("remove_parameter crashed")
        return f"Internal error in remove_parameter: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def replace_docstring(
    file_path: FilePath,
    target: Annotated[
        str,
        Field(
            description="Python function, method or class name, dotted for "
            "nesting (e.g. 'LRUCache.get'), or '' for the module."
        ),
    ],
    new_docstring: Annotated[
        str,
        Field(
            description="One Python string literal with its quotes, usually "
            "triple-quoted."
        ),
    ],
) -> str:
    """
    Replace or add the docstring of a Python function, method or class, or
    of the module with target "". new_docstring must be one string literal
    with its quotes; anything else (bare text, an f-string, bytes, an empty
    value) is refused. A new docstring goes first in the body; the module's
    goes below a `#!` line and encoding or header comments. A new docstring
    for a body on its signature's line is refused (use
    replace_function_body); so is any non-Python file.

    Use this when: adding or updating a Python docstring.
    Don't use this when: editing a `#` comment above the symbol
    (edit_leading_comment).

    Example:
        target="LRUCache.get"
        new_docstring='\"\"\"Return the cached value, or None.\"\"\"'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_docstring: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        applier.replace_docstring(target, new_docstring)
        return "Updated"
    except ApplierError as e:
        logger.warning("replace_docstring: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("replace_docstring crashed")
        return f"Internal error in replace_docstring: {type(e).__name__}: {e}"


@mcp.tool(annotations=_READ_ONLY)
def find_references(
    file_path: FilePath,
    target: Annotated[
        str,
        Field(
            description="Identifier to find, a plain name, not a dotted "
            "path (e.g. 'LRUCache')."
        ),
    ],
) -> str:
    """
    List each occurrence of an identifier in a source file as `line N:
    <source line>`, in file order. Read-only and syntactic, with no scope
    analysis, so unrelated identifiers of the same name show up too. C++
    destructors and operators go by their list_symbols names (`~A`,
    `operator==`).

    Use this when: surveying a name's uses in a file before a rename.
    Don't use this when: you need references across files or by scope (use
    a language server).

    Example:
        target="LRUCache"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("find_references: target='%s' file='%s'", target, file_path)
        applier = Applier(file_path)
        return applier.find_references(target)
    except ApplierError as e:
        logger.warning("find_references: %s", e)
        return f"Cannot find references: {e}"
    except Exception as e:
        logger.exception("find_references crashed")
        return f"Internal error in find_references: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def add_top_level(
    file_path: FilePath,
    content: Annotated[
        str,
        Field(
            description="Top-level code, inserted as written; read_symbol's "
            "text of a nested symbol is moved to column 0 as a whole."
        ),
    ],
    position: Annotated[
        str,
        Field(
            description="'bottom' (default) at the end of the file; 'top' "
            "after the preamble (package clause, `#!` and magic comments, "
            "module docstring, directives such as 'use strict', imports and "
            "includes). Other values are refused."
        ),
    ] = "bottom",
) -> str:
    """
    Add top-level code (a function, class, constant or other statement) to
    a source file. "bottom" appends it at the end, inside a header's include
    guard; "top" puts it after the preamble, before the first declaration.
    It is set apart by a blank line, two around a Python def or class, but
    one-line code added at the bottom under stacked one-line code is
    stacked too. In Go, or a file indented with tabs, its indentation
    becomes tabs.

    Use this when: adding a top-level symbol or statement.
    Don't use this when: placing it next to a symbol (insert_sibling), in a
    class (add_method, add_field), in a body (insert_in_body) or in a
    config file (add_key).

    Example:
        content="MAX_CONNECTIONS = 10"
        position="top"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("add_top_level: file='%s' position='%s'", file_path, position)
        applier = Applier(file_path)
        applier.add_top_level(content, position=position)
        return "Added"
    except ApplierError as e:
        logger.warning("add_top_level: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("add_top_level crashed")
        return f"Internal error in add_top_level: {type(e).__name__}: {e}"


@mcp.tool(annotations=_READ_ONLY)
def read_symbol(
    file_path: FilePath,
    target: Annotated[
        str,
        Field(
            description="Symbol name as list_symbols lists it, dotted for "
            "nesting ('LRUCache.get', 'A.m(int)'), or a config key path from "
            "the top level ('project.version'; quote a key with dots, "
            "'\"editor.fontSize\"')."
        ),
    ],
    depth: Annotated[
        str,
        Field(
            description="'full' (default) the whole symbol; 'interface' a "
            "class skeleton or function signature; 'signature' the signature "
            "or class header. Config files take only 'full'. Other values "
            "are refused."
        ),
    ] = "full",
) -> str:
    """
    Return the source of one symbol (function, class, method, variable) or
    the value of a config key, without reading the whole file. Read-only.
    "full" is the text replace_function and delete_symbol take: decorators,
    a JS/TS `export`, a C++ `template <...>` header and code that only
    wraps the symbol (a Go `type`, a closure's key, a C `typedef`)
    included, a C/C++ class ending with its `;`. It starts at the symbol's
    first byte, the later lines at their file indentation. "interface"
    gives a class's header, fields and method signatures (bodies as
    ` ...`), indented as in the class, or a function's signature;
    "signature" the signature or class header alone, after decorators.
    Both refuse a variable, constant, field, type alias or macro, saying
    what it is. A name with a prototype or forward declaration reads as
    its definition.

    Use this when: reading one symbol; pick the narrowest depth.
    Don't use this when: you need the file's outline (list_symbols) or its
    imports (read_imports).

    Example:
        target="LRUCache", depth="interface"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "read_symbol: target='%s' depth='%s' file='%s'", target, depth, file_path
        )
        applier = Applier(file_path)
        return applier.read_symbol(target, depth)
    except ApplierError as e:
        logger.warning("read_symbol: %s", e)
        return f"Cannot read symbol: {e}"
    except Exception as e:
        logger.exception("read_symbol crashed")
        return f"Internal error in read_symbol: {type(e).__name__}: {e}"


@mcp.tool(annotations=_READ_ONLY)
def read_imports(file_path: FilePath) -> str:
    """
    Return the import statements of a source file (imports, includes, Ruby
    requires), without reading the rest. Read-only.

    Use this when: checking a file's dependencies, as before add_import.
    Don't use this when: changing imports (add_import, remove_import).

    Example:
        file_path="/abs/path/to/module.py"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("read_imports: file='%s'", file_path)
        applier = Applier(file_path)
        return applier.read_imports()
    except ApplierError as e:
        logger.warning("read_imports: %s", e)
        return f"Cannot read imports: {e}"
    except Exception as e:
        logger.exception("read_imports crashed")
        return f"Internal error in read_imports: {type(e).__name__}: {e}"




@mcp.tool(annotations=_DESTRUCTIVE)
def edit_leading_comment(
    file_path: FilePath,
    target: Annotated[
        str,
        Field(
            description="Symbol name as list_symbols lists it, dotted for "
            "nesting ('LRUCache.get'), or a YAML/TOML key path from the top "
            "level or TOML [table] name ('tool.uv')."
        ),
    ],
    op: Annotated[
        str,
        Field(
            description="'add' inserts a comment, refused when the symbol has "
            "one (the error quotes it: use 'replace' with a block that repeats "
            "lines to keep, such as lint directives); 'replace' replaces the "
            "block, or adds one; 'remove' deletes it. Other values are refused."
        ),
    ],
    comment: Annotated[
        str,
        Field(
            description="Comment text with its markers ('# note', '// note', "
            "'/** ... */'); required for 'add' and 'replace', ignored for "
            "'remove'."
        ),
    ] = "",
) -> str:
    """
    Add, replace or remove the comment block directly above a symbol, its
    doc comment. The block sits above the symbol's decorators, annotations,
    `export` and C++ `template <...>` header, and a new comment goes there,
    re-indented to the symbol. A comment indented deeper than the symbol
    ends the code above and is not part of the block. A symbol that other
    code comes before on its line is refused. In YAML and TOML the target
    is a key path or a TOML [table]; JSON has no comments and is refused.

    Use this when: adding, rewriting or deleting a symbol's doc comment.
    Don't use this when: writing a Python docstring (replace_docstring) or
    a comment inside a body (insert_in_body, replace_in_body).

    Example:
        target="LRUCache.get", op="add", comment="# Return the cached value."
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "edit_leading_comment: op='%s' target='%s' file='%s'",
            op,
            target,
            file_path,
        )
        applier = Applier(file_path)
        applier.edit_leading_comment(target, op, comment)
        verb_map = {"add": "Added", "replace": "Updated", "remove": "Removed"}
        return verb_map.get(op, "Updated")
    except ApplierError as e:
        logger.warning("edit_leading_comment: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("edit_leading_comment crashed")
        return f"Internal error in edit_leading_comment: {type(e).__name__}: {e}"



@mcp.tool(annotations=_ADDITIVE)
def insert_sibling(
    file_path: FilePath,
    target: Annotated[
        str,
        Field(
            description="Symbol name as list_symbols lists it, dotted for "
            "nesting (e.g. 'LRUCache', 'A.m')."
        ),
    ],
    content: Annotated[
        str,
        Field(
            description="Code to insert, re-indented to the target's level "
            "(in tabs where the file indents with them); read_symbol's text "
            "goes in as a whole."
        ),
    ],
    position: Annotated[
        str,
        Field(
            description="'before' or 'after' the target; other values are "
            "refused."
        ),
    ],
) -> str:
    """
    Insert code next to a named symbol, at its level. "before" goes above
    the symbol's leading comment, decorators and `export`; "after" below
    the symbol (after the `;` that ends a C/C++ class). The code is spaced
    like the gap it goes into: one-line code stacked without blank lines
    stays stacked, and next to a function or class it gets at least one
    blank line, two around a top-level Python def or class. A comment
    indented deeper than the target ends the code above, so "before" goes
    below it. "before" is refused when other code comes before the target
    on its line, "after" when code follows it. Refused in JSON, YAML and
    TOML files (use add_key).

    Use this when: placing code relative to a symbol, such as a helper
    above its caller.
    Don't use this when: appending at the end of the file (add_top_level),
    or inserting into a body (insert_in_body) or a class (add_method,
    add_field).

    Example:
        target="LRUCache"
        content="CACHE_SIZE = 100"
        position="before"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info(
            "insert_sibling: target='%s' position='%s' file='%s'",
            target,
            position,
            file_path,
        )
        applier = Applier(file_path)
        applier.insert_sibling(target, content, position)
        return "Added"
    except ApplierError as e:
        logger.warning("insert_sibling: %s", e)
        return f"Cannot perform edit: {e}"
    except Exception as e:
        logger.exception("insert_sibling crashed")
        return f"Internal error in insert_sibling: {type(e).__name__}: {e}"



def main():
    logger.info("Starting AST Code Editor MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
