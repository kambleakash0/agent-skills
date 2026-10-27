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
    ".toml files: you name a target and the server finds it, so prefer these "
    "tools over text edits there. file_path must be absolute.\n\n"
    "Source files: call list_symbols first for exact, case-sensitive names "
    "(Class.method), read_symbol to read one symbol, find_references before a "
    "rename. Config files: a target is the key path from the top level "
    "(project.version); quote a key that contains dots (\"editor.fontSize\").\n\n"
    "Use the narrowest tool: replace_in_body, insert_in_body or "
    "delete_in_body for a few lines (snippets must match exactly, once) "
    "rather than replace_function or replace_function_body; "
    "add_parameter/remove_parameter rather than replace_signature for one "
    "parameter; add_key for a new key, replace_value for an existing one; "
    "add_import_name to extend an existing import. Decorators and a JS/TS "
    "export belong to their symbol.\n\n"
    "Every edit is parse-checked: one that would add a syntax error is "
    "refused with its line and column, and the file is left unchanged. Fix "
    "the content and retry; if the code is valid but the parser does not "
    "support it, make that edit with your normal edit tool. Line endings are "
    "kept; write \\n.\n\n"
    "Escape hatches: to delete several symbols, call delete_symbol once per "
    "symbol; use your normal edit tool for arbitrary sub-expression changes "
    "and your write tool for whole-file rewrites."
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
    str,
    Field(
        description="Absolute path to an existing source or config file; its "
        "extension selects the language."
    ),
]
FunctionTarget = Annotated[
    str,
    Field(
        description="Case-sensitive function or method name, dotted for nested "
        "symbols (e.g. 'LRUCache.get'); call list_symbols for exact names. A "
        "JS/TS const/let/var bound to an arrow function or function expression "
        "is a function too; the body tools need a `{ }` body, so they refuse "
        "an arrow function whose body is an expression."
    ),
]
ClassTarget = Annotated[
    str,
    Field(
        description="Case-sensitive name of the class (TS abstract classes "
        "too, or a TS interface, C++ struct, Go struct type) to add to; an "
        "anonymous JS/TS `export default class` is 'default'. A TS enum or "
        "type alias is refused."
    ),
]
BodySnippet = Annotated[
    str,
    Field(
        description="Exact text to match, byte-identical including indentation "
        "and newlines (\\n also matches CRLF line breaks); it must occur "
        "exactly once in the target's body."
    ),
]
LiteralValue = Annotated[
    str,
    Field(
        description="Value as literal source text in the file's own syntax "
        "(e.g. '\"2.0.0\"' or '42'); quote strings where the format requires it."
    ),
]
ArrayTarget = Annotated[
    str,
    Field(
        description="Full key path from the top level to the array in a "
        "JSON/YAML/TOML file (e.g. 'project.dependencies'; a key containing "
        "dots goes in double quotes, '\"a.b\".list'), or the name of a "
        "Python module-level list."
    ),
]
ImportModule = Annotated[
    str,
    Field(
        description="Module of the existing named import as written, without "
        "quotes (e.g. 'typing' or './utils')."
    ),
]
ImportName = Annotated[
    str,
    Field(description="A single imported name, e.g. 'Optional' or 'baz'."),
]


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
            description="Complete replacement definition including decorators "
            "(and a JS/TS `export`), signature and body, as read_symbol returns "
            "it; re-indented to the original's level."
        ),
    ],
) -> str:
    """
    Replace an entire function definition with new content -- signature, body, and decorators.
    The replaced span is what read_symbol returns: decorators (TS method
    decorators too) and a JS/TS `export` included, so keep them in `content`.

    Use this when: You're rewriting a function top-to-bottom (e.g., renaming it,
    changing parameters AND implementation together).
    Don't use this when: You only need to change the body -> use `replace_function_body`.
    You only need to change the signature -> use `replace_signature`.

    Example:
        target="LRUCache.get"
        content='    def get(self, key, default=None):\\n        return self.items.get(key, default)'
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
            description="New body statements only, without the signature or "
            "enclosing braces; re-indented as a block to the body's indentation."
        ),
    ],
) -> str:
    """
    Replace only the body of a function, preserving its signature and decorators.

    Use this when: You're changing the implementation while keeping the interface stable.
    Don't use this when: You're also changing parameters or return type -> use
    `replace_signature` or `replace_function`.

    Example:
        target="LRUCache.get"
        content='        if key in self.items:\\n            return self.items[key]\\n        return None'
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
            description="Replacement text, written exactly as given (include the "
            "indentation and newlines you need)."
        ),
    ],
) -> str:
    """
    Replace a byte-identical snippet inside a named function/method body,
    without touching the surrounding code. The match is scoped to the target's
    body so accidental matches elsewhere in the file cannot happen.

    Raises if the snippet is not found, or if it appears more than once in the
    body (include more surrounding context to disambiguate).

    Use this when: You need to change a specific statement or block inside a
    large function body without rewriting the whole body. The single biggest
    token-saver for long functions with ~30 similar lines where you only want
    to change one of them.
    Don't use this when: You're replacing the entire body -> use
    `replace_function_body`. You need to change a sub-expression inside a
    method chain that string matching can't uniquely locate -> use the default
    `Edit` tool instead.

    Example:
        target="init"
        old_snippet="viper.BindPFlag(\\"port\\", cmd.Flags().Lookup(\\"port\\"))"
        new_snippet="viper.BindPFlag(\\"port\\", cmd.PersistentFlags().Lookup(\\"port\\"))"
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
    Delete a byte-identical snippet inside a named function/method body. Scoped
    to the target's body so global file matches don't apply.

    Raises if the snippet is not found, or if it appears more than once in the
    body (include more surrounding context to make the match unique).

    Use this when: You want to remove a specific statement, block, or line
    inside a function body without rewriting the whole body. Also useful for
    removing a single entry from an inline object-literal passed as a function
    argument -- target the enclosing function and delete the entry text.
    Don't use this when: You're deleting the entire function/class -> use
    `delete_symbol`.

    Example (remove a mount call inside a function):
        target="RegisterRoutes"
        snippet='\\tr.Mount("/kb", kbHandler)\\n'

    Example (remove a key from an inline object arg):
        target="main"
        snippet="\\t\\tclassification,\\n"
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
            description="Text to insert: placed byte for byte with after/before "
            "(include your own newlines and indentation), or re-indented as a "
            "block (relative indentation kept) to the body's indentation with at."
        ),
    ],
    after: Annotated[
        str,
        Field(
            description="Unique, byte-identical anchor in the target's body to "
            "insert after; '' (default) leaves this mode unused."
        ),
    ] = "",
    before: Annotated[
        str,
        Field(
            description="Unique, byte-identical anchor in the target's body to "
            "insert before; '' (default) leaves this mode unused."
        ),
    ] = "",
    at: Annotated[
        str,
        Field(
            description="'top' or 'bottom' of the body, at the body's own "
            "indentation level (top goes after a Python docstring); '' (default) "
            "leaves this mode unused, and exactly one of at, after or before must "
            "be set. Refused for a body written on one line with its signature or braces."
        ),
    ] = "",
) -> str:
    """
    Insert new_snippet inside a named function/method body. Pass EXACTLY ONE
    of `at`, `after`, or `before` -- this one tool covers four placement
    modes that used to be spread across three separate tools.

      - at="top":    insert at the top of the body (after a Python docstring).
      - at="bottom": insert at the bottom of the body, at body level even when
        the last statement is a nested block.
    `at` needs the body on its own lines: a one-line body such as
    `def f(): return 1` or `function f() { return 1; }` is refused; rewrite
    it with `replace_function_body` instead.
      - after=<snippet>:  insert immediately after a byte-identical anchor.
      - before=<snippet>: insert immediately before a byte-identical anchor.

    The anchor match (for `after`/`before`) is scoped to the target's body
    and must be unique -- multiple matches raise an error telling you to
    include more surrounding context. Caller is responsible for any
    leading/trailing newlines and indentation in new_snippet.

    Use this when: You're inserting new lines into a function body. Use
    `at="top"`/`at="bottom"` for simple prepend/append, or `after`/`before`
    for anchored insertion.
    Don't use this when: You're replacing the whole body -> use
    `replace_function_body`. You're adding a top-level symbol -> use
    `add_top_level`. You're changing an existing snippet in the body ->
    use `replace_in_body`.

    Example (prepend):
        target="handle"
        new_snippet='    log("start")\\n'
        at="top"

    Example (append):
        target="handle"
        new_snippet='    log("end")\\n'
        at="bottom"

    Example (after anchor):
        target="handle"
        new_snippet='    metrics.incr("calls")\\n'
        after='    validate(request)\\n'

    Example (before anchor):
        target="handle"
        new_snippet='    auth_check(request)\\n'
        before='    validate(request)\\n'
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
            description="Complete method source, added after the class's last "
            "member and re-indented like its existing members, keeping its own "
            "relative indentation (Go: a receiver func placed after the type "
            "declaration)."
        ),
    ],
) -> str:
    """
    Add a new method at the end of a class body.

    The method is indented like the class's existing members (else one indent
    unit of the file, or the language default, deeper than the class),
    keeping the content's relative indentation (in tabs when the members are
    tab-indented), and follows the last member after one blank line, or none
    if the class's methods have no blank lines between them or the last
    member is a C++ access label. No blank line is added before the closing
    brace; a braced body on one line (`class K {}`, `class K { a() {} }`) is
    opened up over several lines. A Java enum gets the method after its
    constants, with the `;` they need. A one-line Python or Ruby class is
    refused.

    Use this when: You're adding a method to an existing class.
    Don't use this when: You're adding a field/attribute -> use `add_field`. You're
    adding a top-level function (not inside a class) -> use `add_top_level`.

    Example:
        class_target="LRUCache"
        content='    def clear(self):\\n        self.items.clear()'
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
            description="Case-sensitive name of the function, method, or class to "
            "delete, dotted for nested symbols (e.g. 'LRUCache.old_method')."
        ),
    ],
    include_leading_comments: Annotated[
        bool,
        Field(
            description="If true (default), also delete the contiguous comment "
            "block directly above the symbol and its decorators; false keeps it."
        ),
    ] = True,
) -> str:
    """
    Delete an entire function or class definition, including its decorators
    (TS method decorators too) and a JS/TS `export`.
    By default, also removes the contiguous leading comment block above the
    symbol and its decorators (Godoc, Javadoc `/** ... */`, `#` or `//`
    comment runs) so the doc doesn't become orphaned floating text. Pass
    `include_leading_comments=False` to leave that comment in place.

    The blank lines that separated the symbol go with it, so the rest keeps
    the file's spacing: no blank lines are left at the top of the file or
    of a class body (after the first member is deleted) or before a closing
    brace (after the last), and between two remaining symbols only the
    wider of the two gaps stays.

    Use this when: You want to remove a function, method, or class entirely from a
    source file -- along with its doc comment by default.
    Don't use this when: You want to remove a config key -> use `delete_key`. You
    want to remove an import -> use `remove_import`. You want to remove lines
    inside a function -> use `delete_in_body` (or `replace_function_body` to
    rewrite the whole body without the unwanted lines).

    Example:
        target="LRUCache.old_method"              # deletes a method + its leading comment
        target="DeprecatedClass"                  # deletes class, all methods, and preceding Javadoc
        target="Foo", include_leading_comments=False   # keep the comment, delete only the symbol
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
            description="Existing key: full key path from the top level in a "
            "JSON, YAML, or TOML file (e.g. 'project.version'; a deeper "
            "x.project.version never matches; a key containing dots goes in "
            "double quotes, as in '\"editor.fontSize\"' or 'a.\"b.c\".d', and "
            "TOML also takes single quotes; keys inside YAML flow mappings and "
            "TOML inline tables count, and a YAML key with no value gets one), "
            "'DictName.keyExpr' for a Python module-level dict (e.g. "
            "'CONFIG.\"timeout\"'), or 'VarName.key' for a JS/TS module-level "
            "object literal; Python and JS/TS paths may continue into nested "
            "literals."
        ),
    ],
    content: LiteralValue,
) -> str:
    """
    Replace the value of an existing key in a JSON, YAML, or TOML file, or of an
    entry in a Python module-level dict literal or JS/TS module-level object
    literal (same target forms as `delete_key`). A JS/TS shorthand `{ key }`
    becomes `key: <content>`.

    Config targets are key paths from the top level, one key per dot; put a
    key that contains dots in double quotes ('"editor.fontSize"',
    'a."b.c".d'; TOML also takes single quotes). Keys inside YAML flow
    mappings and TOML inline tables are addressable too and stay inline
    (`a: {x: 1}` is 'a.x', `t = { a = 1 }` is 't.a'). A YAML key with no
    value (`a:`) gets one: `a: 3`, or for several lines (or a block
    sequence or mapping) a nested block below the key, one level deeper (a
    first line such as `|` or `&anchor` stays after the colon); an explicit
    key with no value (`? a`) gets a `: 3` line below it. Array elements
    are not addressable.

    Use this when: A key already exists and you want to update its value.
    Don't use this when: The key doesn't exist yet -> use `add_key`. You're modifying
    an array -> use `append_to_array` or `remove_from_array`.

    Example:
        target="project.version"
        content='"2.0.0"'
    Example (JSON key with dots):
        target='"editor.fontSize"'
        content="14"
    Example (Python):
        target='CONFIG."timeout"'
        content="60"
    Example (TS):
        target="CONFIG.server.port"
        content="8080"
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
            description="Complete import line in the file's language (e.g. 'from "
            "typing import Optional' or '#include <stdlib.h>'); in Go a bare spec "
            "like '\"fmt\"' works only when a parenthesized import ( ... ) block "
            "already exists; skipped if an identical line exists."
        ),
    ],
) -> str:
    """
    Add an import statement to a source file. Skips exact duplicates. Places new
    imports after existing ones, or at the top of the file if none exist.

    Use this when: You need to import something the file does not already reference.
    Don't use this when: You're adding a single name to an existing multi-name
    import statement like `from X import a, b` -> use `add_import_name`.

    Example:
        import_text="from typing import Optional"    # Python
        import_text="import { readFile } from 'fs';" # JS/TS
        import_text="#include <stdlib.h>"             # C/C++
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
        Field(
            description="Exact import line to remove, compared after stripping "
            "surrounding whitespace (e.g. 'import os')."
        ),
    ],
) -> str:
    """
    Remove a matching import statement from a source file. Matching is by stripped
    text equality -- pass the exact import line you want to remove.

    Use this when: You want to remove an unused import.
    Don't use this when: You want to remove one name from a multi-name import -> use
    `remove_import_name`.

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
            description="Parent container: full key path from the top level "
            "to a JSON object or YAML mapping (including `{}`, a flow mapping, "
            "one nested in a flow mapping, or a YAML key with no value), a TOML "
            "[table] by its header's names or an inline table by its key path, "
            "'' for a config file's root (a key containing dots goes in double "
            "quotes, e.g. 'a.\"b.c\"'; TOML also takes single quotes); in source "
            "files the name of a Python module-level dict or JS/TS module-level "
            "object literal, dotted further into nested literals (e.g. "
            "'CONFIG.\"db\"', 'CONFIG.server')."
        ),
    ],
    key: Annotated[
        str,
        Field(
            description="Key to add, refused if the container already has it: "
            "for JSON and YAML one name, dots included (quoted for you, in YAML "
            "only when it needs quotes; a name already in quotes is used as "
            "given); for TOML a dotted key written like a TOML path (quoted for "
            "you only when it needs quotes, and dots separate its parts, so "
            "quote a name that contains one yourself, e.g. '\"example.com\"'); "
            "for JS/TS a name, quoted for you only if it is not a valid "
            "identifier; for Python a key expression, so quote string keys "
            "(e.g. '\"timeout\"')."
        ),
    ],
    value: LiteralValue,
) -> str:
    """
    Add a new key-value pair inside a dict-like container. Works for JSON objects,
    YAML mappings, TOML tables, Python dict literals, AND JS/TS object literals.

    For JSON/YAML/TOML: parent_target is the full key path from the top level
    to the parent (use "" for root), into YAML flow mappings and TOML inline
    tables too; for a TOML [table], its header's names ([a."b.c"] is
    'a."b.c"'). As in every config target, a key containing dots goes in
    double quotes ('"a.b"'; TOML also takes single quotes). `key` is one name
    for JSON and YAML (dots included), and YAML and TOML keys are quoted for
    you only when they need quotes (`my key` stays plain in YAML; TOML dots
    separate the parts of a dotted key, so quote a name containing one
    yourself: '"example.com"').
    For Python (.py): parent_target is the module-level variable name (e.g. 'CONFIG'),
    optionally followed by keys into nested dicts (e.g. 'CONFIG."db"').
    For JS/TS: parent_target names a module-level `const`/`let`/`var` (exported
    or not; `as const` and `satisfies` are fine) assigned an object literal,
    optionally followed by keys into nested objects (e.g. 'CONFIG.server').
    value should be a literal source expression in the target file's syntax (e.g.
    JSON '"foo"' or '42'; Python '"foo"' or '42').

    The new entry follows the container's layout: one key per line stays one
    per line, an inline object stays inline, and a trailing comma is kept. An
    empty JS/TS or YAML `{}` becomes `{ key: value }` (an empty TOML inline
    table `{ key = value }`), and non-empty YAML flow mappings and TOML inline
    tables (`{a: 1}`, `t = { a = 1 }`) get the entry inline too. A YAML key
    with no value (`parent:`) gets a nested block mapping (inside a flow
    mapping, an inline `parent: { key: value }`). A key the container
    already has is refused, with the target to pass to `replace_value`.

    Use this when: The key does not exist yet and you want to add it.
    Don't use this when: The key already exists -> use `replace_value`. You're
    adding an item to a list/array -> use `append_to_array`.

    Example (JSON):
        parent_target="dependencies"
        key="mcp"
        value='"^1.2.0"'
    Example (Python):
        parent_target="CONFIG"    # module-level CONFIG = {...}
        key='"timeout"'            # include quotes if key is a string literal
        value="30"
    Example (TS):
        parent_target="CONFIG.server"   # const CONFIG = { server: { ... } }
        key="port"                       # quoted for you only when needed
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
            description="Key to delete: full key path from the top level for "
            "JSON/YAML/TOML (e.g. 'dependencies.tree-sitter'; a key containing "
            "dots goes in double quotes, '\"editor.fontSize\"', and TOML also "
            "takes single quotes; keys inside YAML flow mappings and TOML "
            "inline tables count), 'DictName.keyExpr' for a Python module-level "
            "dict (e.g. 'CONFIG.\"timeout\"'), or 'VarName.key' for a JS/TS "
            "module-level object literal; Python and JS/TS paths may continue "
            "into nested literals (e.g. 'CONFIG.server.port')."
        ),
    ],
) -> str:
    """
    Delete a key-value pair from a dict-like container.
      - JSON / YAML / TOML: key path from the top level ('"a.b"' for a key
        containing dots), into YAML flow mappings and TOML inline tables too.
      - Python (.py) module-level dict literals: target is 'DictName.keyExpr'
        (e.g. 'CONFIG."timeout"'), or a longer path into nested dicts
        (e.g. 'CONFIG."db"."host"').
      - JS / TS module-level `const` / `let` / `var` object literals
        (including `export const ... = { ... }`): target is 'VarName.keyName'
        or 'VarName."quoted-key"', or a longer path into nested objects
        (e.g. 'CONFIG.server.port'). Handles regular `{ key: value }` pairs,
        shorthand `{ key }` properties and methods.

    For JSON, Python, JS/TS, YAML flow mappings and TOML inline tables, the
    adjacent comma is also removed to keep the file valid; deleting the only
    entry leaves `{}`. Other YAML and TOML keys go with their lines.

    Use this when: You want to remove an entire entry.
    Don't use this when: You want to remove an item from a list/array -> use
    `remove_from_array`. You need to edit an inline object literal passed as a
    function argument (`foo({ x })`) -- use `delete_in_body` scoped to the
    enclosing function instead.

    Example (JSON):
        target="dependencies.tree-sitter"
    Example (Python):
        target='CONFIG."timeout"'
    Example (TS):
        target="CONFIG.port"             # regular pair
        target="CONFIG.name"              # shorthand `{ name }`
        target='CONFIG."complex-key"'     # quoted key
        target="CONFIG.server.port"       # nested object
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
    Append a literal value to an array/list. Works for JSON arrays, YAML sequences,
    TOML arrays, AND Python module-level list literals.

    For JSON/YAML/TOML: target is the key path to the array from the top level
    ('"a.b".list' for a key containing dots).
    For Python (.py): target is the module-level variable name (e.g. 'ITEMS').

    The value follows the array's layout: an inline array stays inline
    (`[1, 2]` becomes `[1, 2, 3]`, `[]` becomes `[3]`), an array with one
    element per line gets a new line at the elements' indentation, and a
    trailing comma is kept; a YAML block sequence gets a new `- value` item.

    Use this when: You want to add an item to a list (dependencies, keywords,
    include paths, fixtures, etc.).
    Don't use this when: You're adding a key-value pair -> use `add_key`.

    Example (TOML):
        target="project.dependencies"
        value='"new-package"'
    Example (Python):
        target="ITEMS"
        value='"new-item"'
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
            description="Element to remove, compared with each element's source "
            "text after stripping whitespace (e.g. '\"old-package\"'); only the "
            "first match is removed."
        ),
    ],
) -> str:
    """
    Remove the first element matching value_match (stripped text equality) from an
    array/list. Works for JSON/YAML/TOML config arrays AND Python module-level
    list literals.

    For JSON/YAML/TOML: target is the key path to the array from the top level
    ('"a.b".list' for a key containing dots).
    For Python (.py): target is the module-level variable name.

    Use this when: You want to remove a specific item from a list.
    Don't use this when: You want to remove a whole key -> use `delete_key`.

    Example (TOML):
        target="project.dependencies"
        value_match='"old-package"'
    Example (Python):
        target="ITEMS"
        value_match='"old-item"'
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
            description="Literal field or member declaration (e.g. 'version = "
            "\"1.0\"' or Go 'version int'), re-indented like the class's "
            "existing members and inserted before the first of them (after a "
            "Python class docstring or a Java enum's constants), with no "
            "auto-wrapping."
        ),
    ],
) -> str:
    """
    Add a field/attribute/member at the top of a class body (fields-before-methods
    convention): before the first member, after a Python class docstring or
    a Java enum's constants (adding the `;` they need). Indented like
    add_method, with a blank line after it when the member below is a
    method; comments after the `{` on its line stay there.

    Use this when: You're adding a class attribute (Python), class field (JS/TS),
    or member variable (C++).
    Don't use this when: You're adding a method -> use `add_method`.

    Example:
        class_target="LRUCache"
        content='    version = "1.0"'
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
            description="Everything from the start of the definition up to its "
            "body (e.g. 'def get(self, key, default=None):' or JS 'get(key, d)' "
            "without the '{'); indentation on its first line is ignored, and "
            "following lines (parameters, or the def after a decorator line) "
            "may be indented relative to it. The existing decorators and Java "
            "annotations are kept unless it includes its own, which then "
            "replace them. For a JS/TS function bound to a name, "
            "'const f = (a, b) =>' replaces from the const on, '(a, b) =>' only "
            "the function's own part. For a method with no body (a TS abstract "
            "or Java interface method), the ';' after it stays."
        ),
    ],
) -> str:
    """
    Replace only the signature of a function, preserving its body and decorators.

    Decorators (Python, JS/TS) and Java annotations such as `@Override` are kept
    when new_signature has none, in their original layout. If new_signature
    includes decorators or annotations, they replace the existing ones.

    The signature lands at the definition's own column: indentation on its
    first line is ignored, and the lines after it may be indented relative
    to that line (as in the decorator example below) or written as
    read_symbol(depth="signature") returns them.

    For a JS/TS function bound to a name (`const f = (a) => {...}`), a
    new_signature starting with const/let/var, as read_symbol returns it,
    replaces the declaration from there (an `export` stays); one without
    (`async (a, b) =>`) replaces only the function's own part.

    A method declared without a body (a TS abstract method, a Java interface
    or abstract method) is all signature but the `;` that ends it, which
    stays whether or not new_signature ends with one.

    Use this when: You're changing parameters, return type, or function name
    without modifying the implementation.
    Don't use this when: You also want to change the body -> use `replace_function`.
    You're adding/removing one parameter -> use `add_parameter`/`remove_parameter`.

    Example:
        target="LRUCache.get"
        new_signature="def get(self, key, default=None):"
    Example (Python method; the new decorator replaces any existing ones):
        target="LRUCache.get"
        new_signature="@staticmethod\\ndef get(key):"
    Example (Java; the method's existing @Override line stays):
        target="LRUCache.toString"
        new_signature="public synchronized String toString()"
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
    Return a formatted outline of all top-level functions, classes, and methods in
    a source file (Python, JS, TS, C, C++, Ruby, Go, Java), with line numbers.
    Read-only. JS/TS exported declarations are listed under their own names,
    an anonymous `export default function/class` as `default`, and every
    listed name is a valid target for the other tools, except a TS name
    that a type and a value share in one scope (`const User` and `type
    User`), which they refuse as ambiguous. A symbol's line is that of its
    first decorator or `export`. In JS/TS, generator functions and a
    `const`/`let`/`var` that declares one name bound to an arrow function
    or function expression are listed as `function`, TS abstract classes as
    `class` (abstract methods among their methods, an overloaded one once),
    and enums, type aliases and interfaces as `enum`, `type` and
    `interface`.

    Use this when: You're about to edit an unfamiliar file and want to see its
    structure and exact symbol names. ALWAYS a good first call before editing --
    avoids guessing at target names.
    Don't use this when: You already know the exact target name.

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
    Add a name to an existing named-import statement. Idempotent: skips if
    the name is already present.

      - Python (.py): `from <module> import a, b`
      - JS/TS:        `import { a, b } from "<module>"`

    Use this when: The module is already imported via a named-import form and
    you want to add another name to that existing statement.
    Don't use this when: The import statement doesn't exist yet -> use
    `add_import`. You want a default or namespace import (`import Foo from ...`
    or `import * as ns from ...`) -> use `add_import` with the full line.

    Example (Python):
        module="typing"
        name="Optional"
    Example (TS):
        module="./utils"
        name="baz"
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
    Remove a name from a named-import statement.

      - Python (.py): `from <module> import a, b, c`
      - JS/TS:        `import { a, b, c } from "<module>"`

    If the name removed is the only remaining one AND there are no other
    bindings (default / namespace) in the same statement, the entire import
    line is removed. Raises an error if removing the last name would leave
    an invalid `import Default, {} from "mod"` fragment.

    Use this when: You want to remove a single name from a multi-name import.
    Don't use this when: You want to remove the entire import line -> use
    `remove_import`.

    Example (Python):
        module="typing"
        name="List"
    Example (TS):
        module="./utils"
        name="bar"
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
            description="Literal source text of one parameter (e.g. 'default=None' "
            "or 'const int* buf'); the separating comma is added for you."
        ),
    ],
    position: Annotated[
        str,
        Field(
            description="'end' (default) appends after the last parameter; "
            "'start' inserts before the first. Any other value is refused."
        ),
    ] = "end",
) -> str:
    """
    Add a parameter to a function signature at position 'end' (default) or 'start'
    (any other position is refused). Leaves the body untouched. A JS/TS arrow
    function's one unparenthesized parameter gets parentheses: `x => ...`
    becomes `(x, y) => ...`.

    Use this when: You need to add one or two parameters without retyping the whole
    signature.
    Don't use this when: You need to replace the entire signature -> use
    `replace_signature`. You also want to change the body -> use `replace_function`.

    Example:
        target="LRUCache.get"
        parameter="default=None"
        position="end"
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
            description="Bare name of the parameter to remove (e.g. 'default'), "
            "without its type or default value."
        ),
    ],
) -> str:
    """
    Remove a parameter by name from a function signature. Leaves the body
    untouched. A JS/TS arrow function's one unparenthesized parameter leaves
    `()` behind: `x => 1` becomes `() => 1`.

    Use this when: You need to remove one parameter without retyping the whole
    signature.
    Don't use this when: You need to replace the whole signature -> use
    `replace_signature`.

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
            description="Case-sensitive name of the Python function, method, or "
            "class, dotted for nested symbols (e.g. 'LRUCache.get')."
        ),
    ],
    new_docstring: Annotated[
        str,
        Field(
            description="Python string literal including its quotes, normally "
            "triple-quoted; replaces the existing docstring or becomes the first "
            "body statement."
        ),
    ],
) -> str:
    """
    Replace or insert a Python docstring on a function or class. Python-only. The
    new_docstring should be a valid Python string literal including its surrounding
    triple quotes.

    Use this when: You want to add or update a Python docstring without touching
    the function body.
    Don't use this when: You're editing a `#` comment above the symbol -> use
    `edit_leading_comment`. You're in a non-Python file -> no equivalent tool.

    Example:
        target="LRUCache.get"
        new_docstring=(triple-quoted string, e.g. with three double-quotes before and after the summary text)
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
            description="Exact identifier to find, matched per identifier rather "
            "than as a dotted path (e.g. 'LRUCache')."
        ),
    ],
) -> str:
    """
    Return all occurrences of an identifier named `target` in a source file, as
    'line N: <source line>'. Read-only, syntactic only (no scope awareness), so
    results may include unrelated identifiers that happen to share the same name.

    Use this when: You're about to rename or refactor a symbol and need a quick
    survey of where it appears in the file.
    Don't use this when: You need cross-file or scope-aware analysis -> use a full
    language server.

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
            description="Top-level source inserted as-is (function, class, "
            "constant, or any statement), separated from existing code by a "
            "blank line."
        ),
    ],
    position: Annotated[
        str,
        Field(
            description="'bottom' (default) appends at the end of the file; 'top' "
            "inserts after the preamble (package, imports, includes, leading "
            "comments, Python module docstring)."
        ),
    ] = "bottom",
) -> str:
    """
    Insert top-level content into the file: a function, class, constant, type
    alias, or any other top-level statement. `position` controls placement:

      - "bottom" (default): append to end of file.
      - "top": insert after the preamble (package/imports/includes/leading
               comments, plus the Python module docstring if present) and
               before the first real declaration.

    Use this when: You're adding any kind of top-level code. Use position="top"
    when inserting multiple declarations at the top of a file without the
    reverse-order problem of repeated `insert_sibling(position="before")` calls.
    Don't use this when: You need placement relative to a specific symbol ->
    use `insert_sibling`. You're adding to a class body -> use
    `add_method` / `add_field`. You're adding a line inside an existing
    function body -> use `insert_in_body` (`at="top"` / `at="bottom"`).

    Example:
        content="def parse_version(text):\\n    return tuple(int(x) for x in text.split('.'))"
        content="class Logger:\\n    pass", position="top"
        content="MAX_CONNECTIONS = 10", position="top"
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
            description="Case-sensitive symbol name, dotted for nesting (e.g. "
            "'LRUCache.get'), or a config key's full key path from the top "
            "level (e.g. 'project.version'; a key containing dots goes in "
            "double quotes, '\"editor.fontSize\"', and TOML also takes single "
            "quotes; keys inside YAML flow mappings and TOML inline tables "
            "count, and a YAML key with no value reads as '')."
        ),
    ],
    depth: Annotated[
        str,
        Field(
            description="'full' (default) returns the whole source, 'interface' a "
            "class skeleton (members indented as in the class) or function "
            "signature, 'signature' only the signature or class header (a TS "
            "type alias has none); config files support only 'full'."
        ),
    ] = "full",
) -> str:
    """
    Return source text for a single named symbol (function, class, method,
    config key) without reading the entire file. Read-only.

    `depth` controls how much is returned:

      - "full" (default): Entire source of the symbol, decorators and a
        JS/TS `export` included. Typical savings: 10-20x fewer tokens than
        reading the whole file.
      - "interface": For a class -> header + field declarations + method
        signatures with bodies replaced by ' ...', each member indented
        as it is relative to the class header (a nested class's own
        indentation removed). For a function -> just the signature.
      - "signature": Signature-only. For a function -> the line(s) before
        the body (for a JS/TS `const f = (x) => ...`, from its `const`;
        for a method with no body, such as a TS abstract method, its whole
        declaration). For a class -> the class header. A TS type alias has
        no signature and is refused.

    Use this when: You need to read a specific symbol without reading the
    whole file. Pick the narrowest depth that contains what you need.
    Don't use this when: You need a structural overview of the whole file
    -> use `list_symbols`. You need to see the file's imports -> use
    `read_imports`.

    Example:
        target="LRUCache.get"                       # full method source
        target="LRUCache", depth="interface"         # class skeleton
        target="LRUCache.get", depth="signature"     # just the def line
        target="project.version"                     # config value
        target='"editor.fontSize"'                   # config key with dots
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
    Return all import statements in a source file as a multi-line string. Read-only.

    Use this when: You need to see a file's dependencies without reading the entire
    file (e.g. before adding a new import, or to understand what a module uses).
    Don't use this when: You want to add/remove imports -> use `add_import` /
    `remove_import`.

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
            description="Case-sensitive name of the symbol whose leading comment "
            "to edit, dotted for nesting (e.g. 'LRUCache.get'), or a YAML/TOML "
            "key's full key path from the top level (a key containing dots in "
            "double quotes, '\"a.b\"'; a YAML key with no value works too, but a "
            "key that does not start its line, inside a flow mapping or inline "
            "table, is refused); a TOML [table] by its header's names (e.g. "
            "'project', 'tool.uv') also works."
        ),
    ],
    op: Annotated[
        str,
        Field(
            description="'add' inserts a new comment (refused if the symbol "
            "already has one; the error quotes it so that a 'replace' can keep "
            "lines such as lint or compiler directives), 'replace' swaps the "
            "existing block (or inserts one if none), 'remove' deletes the block."
        ),
    ],
    comment: Annotated[
        str,
        Field(
            description="Full comment text including its markers (e.g. '# note', "
            "'// note', '/** ... */'), re-indented to the symbol; required for "
            "'add' and 'replace', ignored for 'remove'."
        ),
    ] = "",
) -> str:
    """
    Edit the contiguous leading-comment block above a named symbol. One tool
    covering three operations on the same comment block. The block sits above
    the symbol's decorators or annotations (TS method decorators too) and a
    JS/TS `export`, so a new comment goes above the first of them. A `#!`
    line and encoding or magic comments at the top of a Python or Ruby file
    are never part of it, nor is a line that starts with `#` or `//` inside
    a multi-line string, template literal or YAML block scalar. In YAML and
    TOML the target is a key path (as for
    `replace_value`) or a TOML [table]; a key inside a flow mapping or
    inline table that does not start its line is refused, since the line
    above it belongs to the key that line starts with.

    Supported values for `op`:
      - "add":     Insert a new comment block above the symbol. Requires
                   `comment`. Refused if the symbol already has a leading
                   comment, which the new lines would merge into; the error
                   quotes those lines -> use "replace" with a block that
                   repeats any you want to keep (lint or compiler
                   directives such as `// eslint-disable-next-line` or
                   `//go:noinline`), or "remove" first.
      - "replace": Replace the existing leading comment block with `comment`;
                   if no leading comment exists, inserts one. Requires
                   `comment`.
      - "remove":  Delete the existing leading comment block. `comment` is
                   ignored.

    The comment must include the language's comment marker (`#` for
    Python/Ruby/YAML/TOML, `//` or `/* ... */` for JS/TS/C/C++/Go/Java,
    `/** ... */` Javadoc for Java). Supports multi-line C-style block
    comments as a single contiguous run.

    Use this when: You want to document, update, or delete a leading
    comment on a function/class/method.
    Don't use this when: You want a Python docstring (which lives inside
    the function body) -> use `replace_docstring`. You want to edit text
    inside the function body itself -> use `replace_in_body`.

    Example:
        target="LRUCache.get", op="add",
        comment="    # Retrieve an item by key, returning None if absent"

        target="LRUCache.get", op="replace",
        comment="    # Retrieve an item from the cache"

        target="LRUCache.get", op="remove"
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
            description="Case-sensitive name of the function, class, method, or "
            "top-level assignment to insert next to, dotted for nesting (e.g. "
            "'LRUCache')."
        ),
    ],
    content: Annotated[
        str,
        Field(
            description="Source to insert, re-indented to the target's level and "
            "separated from it by a blank line."
        ),
    ],
    position: Annotated[
        str,
        Field(description="Where to insert relative to the target: 'before' or 'after'."),
    ],
) -> str:
    """
    Insert content as a sibling of a named symbol (function, class, method,
    or top-level assignment). Pass `position="before"` or `position="after"`.
    "before" goes above the symbol's leading comment block (doc comment,
    Javadoc, Godoc), decorators and a JS/TS `export`, so the comment stays
    on the symbol it documents; a `#!` line and encoding or magic comments
    at the top of a Python or Ruby file stay first.

    Use this when: You need precise placement relative to another top-level
    symbol -- e.g. a helper function immediately before its caller, a
    constant immediately above the class that uses it.
    Don't use this when: You just want to append to the end of the file ->
    use `add_top_level`. You're inserting inside a function body ->
    use `insert_in_body` (with `at`, `after`, or `before`).

    Example:
        target="LRUCache"
        content="CACHE_SIZE = 100"
        position="before"

        target="LRUCache"
        content="RELATED_CONSTANT = 42"
        position="after"
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
