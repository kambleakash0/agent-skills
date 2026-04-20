import logging
import os

from mcp.server.fastmcp import FastMCP
from ast_editor.applier import Applier, ApplierError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("ast-editor")

mcp = FastMCP("AST-Code-Editor")


def _validate_file(file_path: str) -> str | None:
    """Return an error message if file_path is invalid, else None."""
    if not os.path.isabs(file_path):
        return f"file_path must be an absolute path, got: {file_path}"
    if not os.path.isfile(file_path):
        return f"File not found: {file_path}"
    return None


@mcp.tool()
def replace_function(file_path: str, target: str, content: str) -> str:
    """
    Replace an entire function definition with new content -- signature, body, and decorators.

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


@mcp.tool()
def replace_function_body(file_path: str, target: str, content: str) -> str:
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

@mcp.tool()
def replace_in_body(file_path: str, target: str, old_snippet: str, new_snippet: str) -> str:
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


@mcp.tool()
def delete_in_body(file_path: str, target: str, snippet: str) -> str:
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


@mcp.tool()
def insert_in_body(
    file_path: str,
    target: str,
    new_snippet: str,
    after: str = "",
    before: str = "", at: str = "",
) -> str:
    """
    Insert new_snippet inside a named function/method body. Pass EXACTLY ONE
    of `at`, `after`, or `before` -- this one tool covers four placement
    modes that used to be spread across three separate tools.

      - at="top":    insert at the top of the body.
      - at="bottom": insert at the bottom of the body.
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


@mcp.tool()
def add_method(file_path: str, class_target: str, content: str) -> str:
    """
    Add a new method at the end of a class body.

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


@mcp.tool()
def delete_symbol(file_path: str, target: str, include_leading_comments: bool = True) -> str:
    """
    Delete an entire function or class definition, including its decorators.
    By default, also removes the contiguous leading comment block above the
    symbol (Godoc, Javadoc `/** ... */`, `#` or `//` comment runs) so the
    doc doesn't become orphaned floating text. Pass
    `include_leading_comments=False` to leave that comment in place.

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


@mcp.tool()
def replace_value(file_path: str, target: str, content: str) -> str:
    """
    Replace the value of an existing key in a JSON, YAML, or TOML file.

    Use this when: A key already exists and you want to update its value.
    Don't use this when: The key doesn't exist yet -> use `add_key`. You're modifying
    an array -> use `append_to_array` or `remove_from_array`.

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


@mcp.tool()
def add_import(file_path: str, import_text: str) -> str:
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


@mcp.tool()
def remove_import(file_path: str, import_text: str) -> str:
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


@mcp.tool()
def add_key(file_path: str, parent_target: str, key: str, value: str) -> str:
    """
    Add a new key-value pair inside a dict-like container. Works for JSON objects,
    YAML mappings, TOML tables, AND Python module-level dict literals.

    For JSON/YAML/TOML: parent_target is the dotted path to the parent (use "" for root).
    For Python (.py): parent_target is the module-level variable name (e.g. 'CONFIG').
    value should be a literal source expression in the target file's syntax (e.g.
    JSON '"foo"' or '42'; Python '"foo"' or '42').

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


@mcp.tool()
def delete_key(file_path: str, target: str) -> str:
    """
    Delete a key-value pair from a dict-like container.
      - JSON / YAML / TOML: dotted path to the key.
      - Python (.py) module-level dict literals: target is 'DictName.keyExpr'
        (e.g. 'CONFIG."timeout"').
      - JS / TS module-level `const` / `let` / `var` object literals
        (including `export const ... = { ... }`): target is 'VarName.keyName'
        or 'VarName."quoted-key"'. Handles both regular `{ key: value }` pairs
        and shorthand `{ key }` properties.

    For JSON and JS/TS, the adjacent comma is also removed to keep the file valid.

    Use this when: You want to remove an entire entry.
    Don't use this when: You want to remove an item from a list/array -> use
    `remove_from_array`. You need to edit an inline object literal passed as a
    function argument (`foo({ x })`) -- use `delete_in_body` (Phase 3) scoped
    to the enclosing function instead.

    Example (JSON):
        target="dependencies.tree-sitter"
    Example (Python):
        target='CONFIG."timeout"'
    Example (TS):
        target="CONFIG.port"             # regular pair
        target="CONFIG.name"              # shorthand `{ name }`
        target='CONFIG."complex-key"'     # quoted key
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


@mcp.tool()
def append_to_array(file_path: str, target: str, value: str) -> str:
    """
    Append a literal value to an array/list. Works for JSON arrays, YAML sequences,
    TOML arrays, AND Python module-level list literals.

    For JSON/YAML/TOML: target is the dotted path to the array.
    For Python (.py): target is the module-level variable name (e.g. 'ITEMS').

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


@mcp.tool()
def remove_from_array(file_path: str, target: str, value_match: str) -> str:
    """
    Remove the first element matching value_match (stripped text equality) from an
    array/list. Works for JSON/YAML/TOML config arrays AND Python module-level
    list literals.

    For JSON/YAML/TOML: target is the dotted path to the array.
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


@mcp.tool()
def add_field(file_path: str, class_target: str, content: str) -> str:
    """
    Add a field/attribute/member at the top of a class body (fields-before-methods
    convention).

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


@mcp.tool()
def replace_signature(file_path: str, target: str, new_signature: str) -> str:
    """
    Replace only the signature of a function, preserving its body and decorators.

    Use this when: You're changing parameters, return type, or function name
    without modifying the implementation.
    Don't use this when: You also want to change the body -> use `replace_function`.
    You're adding/removing one parameter -> use `add_parameter`/`remove_parameter`.

    Example:
        target="LRUCache.get"
        new_signature="    def get(self, key, default=None):"
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


@mcp.tool()
def list_symbols(file_path: str) -> str:
    """
    Return a formatted outline of all top-level functions, classes, and methods in
    a source file (Python, JS, TS, C, C++), with line numbers. Read-only.

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












@mcp.tool()
def add_import_name(file_path: str, module: str, name: str) -> str:
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


@mcp.tool()
def remove_import_name(file_path: str, module: str, name: str) -> str:
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


@mcp.tool()
def add_parameter(
    file_path: str, target: str, parameter: str, position: str = "end"
) -> str:
    """
    Add a parameter to a function signature at position 'end' (default) or 'start'.
    Leaves the body untouched.

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


@mcp.tool()
def remove_parameter(file_path: str, target: str, parameter_name: str) -> str:
    """
    Remove a parameter by name from a function signature. Leaves the body untouched.

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








@mcp.tool()
def replace_docstring(file_path: str, target: str, new_docstring: str) -> str:
    """
    Replace or insert a Python docstring on a function or class. Python-only. The
    new_docstring should be a valid Python string literal including its surrounding
    triple quotes.

    Use this when: You want to add or update a Python docstring without touching
    the function body.
    Don't use this when: You're editing a `#` comment above the symbol -> use
    `replace_leading_comment`. You're in a non-Python file -> no equivalent tool.

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


@mcp.tool()
def find_references(file_path: str, target: str) -> str:
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


@mcp.tool()
def add_top_level(file_path: str, content: str, position: str = "bottom") -> str:
    """
    Insert top-level content into the file: a function, class, constant, type
    alias, or any other top-level statement. `position` controls placement:

      - "bottom" (default): append to end of file.
      - "top": insert after the preamble (package/imports/includes/leading
               comments, plus the Python module docstring if present) and
               before the first real declaration.

    Use this when: You're adding any kind of top-level code. Use position="top"
    when inserting multiple declarations at the top of a file without the
    `insert_before <target>` reverse-order problem.
    Don't use this when: You need placement relative to a specific symbol ->
    use `insert_before` / `insert_after`. You're adding to a class body -> use
    `add_method` / `add_field`. You're adding a line inside an existing
    function body -> use `prepend_to_body` / `append_to_body`.

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


@mcp.tool()
def read_symbol(file_path: str, target: str, depth: str = "full") -> str:
    """
    Return source text for a single named symbol (function, class, method,
    config key) without reading the entire file. Read-only.

    `depth` controls how much is returned:

      - "full" (default): Entire source of the symbol. Typical savings:
        10-20x fewer tokens than reading the whole file.
      - "interface": For a class -> header + field declarations + method
        signatures with bodies replaced by ' ...'. For a function ->
        just the signature.
      - "signature": Signature-only. For a function -> the line(s) before
        the body. For a class -> the class header.

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


@mcp.tool()
def read_imports(file_path: str) -> str:
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




@mcp.tool()
def edit_leading_comment(
    file_path: str,
    target: str,
    op: str,
    comment: str = "",
) -> str:
    """
    Edit the contiguous leading-comment block above a named symbol. One tool
    covering three operations on the same comment block.

    Supported values for `op`:
      - "add":     Insert a new comment block above the symbol. Requires
                   `comment`. Raises if a leading comment already exists and
                   would be pushed down as a separate block.
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



@mcp.tool()
def insert_sibling(file_path: str, target: str, content: str, position: str) -> str:
    """
    Insert content as a sibling of a named symbol (function, class, method,
    or top-level assignment). Pass `position="before"` or `position="after"`.

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
