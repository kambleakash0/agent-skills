import ast
import json
import os
import re
import warnings
from ast_editor.parser import TreeSitterParser, first_syntax_error, DEFAULT_EXPORT_KINDS


class ApplierError(Exception):
    pass


def _split_lines(text: str) -> list[str]:
    """Split text into lines on "\\n" only. str.splitlines() also breaks on
    form feeds, U+2028 and other separators, which would turn them into
    newlines and shift line numbers away from tree-sitter's rows."""
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def _content_lines(text: str) -> list[str]:
    """Split caller content (code, comments, values) into lines the same
    way: on "\\n" only, after turning CRLF into LF, so a form feed, U+2028
    or other separator inside a string literal stays where it was written.
    A final line break ends the last line rather than adding an empty one."""
    return _split_lines(text.replace("\r\n", "\n"))


def _trailing_blank_lines(lines: list[str]) -> int:
    """Number of blank (empty or whitespace-only) lines that end `lines`."""
    n = 0
    while n < len(lines) and not lines[-1 - n].strip():
        n += 1
    return n


def _python_syntax_error(source: bytes) -> SyntaxError | None:
    """Return the error Python's own parser raises for source, or None.
    tree-sitter-python accepts inconsistent indentation, so Python files get
    this extra check."""
    try:
        with warnings.catch_warnings():
            # SyntaxWarnings (e.g. invalid escapes) are not errors, even
            # under -W error.
            warnings.simplefilter("ignore")
            ast.parse(source)
    except SyntaxError as e:  # includes IndentationError and TabError
        return e
    except (ValueError, RecursionError, MemoryError) as e:
        # Null bytes (before Python 3.12) or nesting too deep for the parser;
        # CPython cannot compile such source either.
        return SyntaxError(str(e) or type(e).__name__)
    return None


def _json_syntax_error(source: bytes) -> ValueError | None:
    """Return the error the json module raises for source, or None. NaN and
    Infinity, which json accepts but RFC 8259 does not, count as errors."""

    def reject(name: str):
        raise ValueError(f"{name} is not valid JSON")

    try:
        json.loads(source, parse_constant=reject)
    except ValueError as e:  # includes JSONDecodeError and UnicodeDecodeError
        return e
    except RecursionError:
        return ValueError("nesting too deep")
    return None


_JS_EXTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

# YAML keys that may stay plain scalars (see Applier._yaml_key_source),
# and the plain scalars YAML 1.1 (PyYAML) or 1.2 reads as booleans or null.
_YAML_PLAIN_KEY = re.compile(r"[^\W\d][\w\-./ ]*")
_YAML_RESERVED = re.compile(
    r"y|Y|yes|Yes|YES|n|N|no|No|NO|true|True|TRUE|false|False|FALSE"
    r"|on|On|ON|off|Off|OFF|null|Null|NULL"
)
# What a double-quoted YAML scalar has to escape beyond what json.dumps
# escapes: the other non-printable characters and the Unicode line breaks.
_YAML_ESCAPE = re.compile(r"[\x7f-\x9f\u2028\u2029\ufeff\ufffe\uffff]")


def _split_key_path(path: str) -> list[str]:
    """Split a dotted key path into its segments: 'CONFIG."a.b".port' gives
    ['CONFIG', '"a.b"', 'port']. Dots inside quotes or brackets do not split,
    so quoted keys (and Python tuple keys) may contain them."""
    parts: list[str] = []
    buf: list[str] = []
    quote = None
    escaped = False
    depth = 0
    for ch in path:
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(depth - 1, 0)
        elif ch == "." and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf).strip())
    return parts


def _unquote(text: str) -> str:
    """Strip one pair of matching quotes ('x', "x" or `x`) from text."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'`":
        return text[1:-1]
    return text


def _python_keys_equal(a: str, b: str) -> bool:
    """Whether two Python key expressions name the same dict key. Literals
    compare by value, so "a" matches 'a' (and 1 matches 1.0, as in a dict);
    anything else compares as source text."""
    a, b = a.strip(), b.strip()
    if a == b:
        return True
    try:
        return ast.literal_eval(a) == ast.literal_eval(b)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False


class Applier:
    def __init__(self, filepath: str):
        self.filepath = filepath
        try:
            self.parser = TreeSitterParser(filepath)
        except ValueError as e:
            # tree-sitter parser raises ValueError for unsupported extensions;
            # convert to ApplierError so callers can distinguish user errors from internal ones.
            raise ApplierError(str(e)) from e

        # LF-normalised text, so line indices match the tree's rows.
        self.lines = _split_lines(self.parser.source_code)

    def _get_indent(self, line: str) -> str:
        return line[: len(line) - len(line.lstrip())]

    def _reindent(self, content_lines: list[str], target_indent: str) -> list[str]:
        if not content_lines:
            return content_lines
        old_indent = self._get_indent(content_lines[0])
        result = []
        for line in content_lines:
            if not line.strip():
                result.append(line)
            elif line.startswith(old_indent):
                result.append(target_indent + line[len(old_indent) :])
            else:
                result.append(target_indent + line.lstrip())
        return result

    def _symbol_span(self, node):
        """
        The first and last nodes of a symbol's source as written, for the
        edits that take a whole symbol (read_symbol, replace_function,
        delete_symbol, insert_sibling, edit_leading_comment). That is the
        node itself, except that a JS/TS exported declaration spans its whole
        `export` statement (with any decorators written before `export`), a
        decorated Python class its decorated_definition, and a TS class
        member starts at the first of the decorators the grammar places
        beside it in the class body, comments between them included.
        Decorated Python functions are found as their decorated_definition,
        and JS method decorators and Java annotations are inside the node,
        already.
        """
        parent = node.parent
        if parent is not None and parent.type in ("export_statement", "decorated_definition"):
            return parent, parent
        if self.parser.ext not in _JS_EXTS:
            return node, node
        first = node
        prev = node.prev_named_sibling
        while prev is not None and (prev.type == "decorator" or "comment" in prev.type):
            if prev.type == "decorator":
                first = prev
            prev = prev.prev_named_sibling
        return first, node

    def replace_function(self, target: str, content: str) -> str:
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        # line indexing is 0-based; decorators and a JS/TS `export` are part
        # of the definition (see _symbol_span).
        first, last = self._symbol_span(node)
        start_line = first.start_point[0]
        end_line = last.end_point[0] + 1

        original_indent = self._get_indent(self.lines[start_line])
        content_lines = _content_lines(content)
        if content_lines and self._get_indent(content_lines[0]) != original_indent:
            content_lines = self._reindent(content_lines, original_indent)

        self.lines = self.lines[:start_line] + content_lines + self.lines[end_line:]
        return self._save()

    def replace_value(self, target: str, content: str) -> str:
        node = self.parser.find_node_by_name(target)
        prefix = ""
        if not node:
            try:
                found = self._find_entry_value(target)
            except ApplierError as e:
                raise ApplierError(f"Target '{target}' not found ({e})") from e
            if found is not None:
                node, prefix = found
        if not node:
            raise ApplierError(f"Target '{target}' not found")

        # Strip a leading newline from content. replace_value substitutes the
        # AST value node, which starts AT the value character itself (not at
        # column 0), so the key's trailing whitespace is already contained in
        # source[:start_byte]. A leading \n in content would produce a
        # gratuitous blank line between the key and its value in any supported
        # format (JSON / YAML / TOML / Python literal).
        if content.startswith("\n"):
            content = content.lstrip("\n")

        # YAML block sequences need line-based replacement with reindenting:
        # the sequence's AST range starts at the first `-` character (not at
        # column 0), so a byte-level substitution of caller content that
        # already has leading indent would double the indent on the first
        # item. Snap to whole-line boundaries and reindent against the
        # existing column of the first `-`.
        ext = self.parser.ext
        if ext in (".yml", ".yaml"):
            resolved = self._resolve_yaml_value(node)
            if resolved is not None and resolved.type == "block_sequence":
                return self._replace_yaml_block_sequence(resolved, content)

        source_bytes = self.parser.source_bytes
        content_bytes = (prefix + content).encode("utf-8")

        new_bytes = (
            source_bytes[: node.start_byte]
            + content_bytes
            + source_bytes[node.end_byte :]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

    def _find_entry_value(self, target: str):
        """
        For replace_value in source files: resolve 'DictName.keyExpr' (a
        Python dict literal) or 'VarName.key' (a JS/TS object literal), also
        through nested literals, to (node to replace, text to put before the
        new value). A JS shorthand `{ key }` is replaced whole, becoming
        `key: <value>`. Returns None when target is no such path.
        """
        ext = self.parser.ext
        if ext != ".py" and ext not in _JS_EXTS:
            return None
        parts = _split_key_path(target)
        if len(parts) < 2 or not all(parts):
            return None
        parent = ".".join(parts[:-1])
        if ext == ".py":
            pair = self._find_python_pair(self._find_python_dict(parent), parts[-1])
            if pair is None:
                raise ApplierError(f"Key {parts[-1]} not found in dict '{parent}'")
            return pair.child_by_field_name("value"), ""
        entry = self._find_js_entry(self._resolve_js_object(parts[:-1]), parts[-1])
        if entry is None:
            raise ApplierError(f"Key '{parts[-1]}' not found in {parent}")
        if entry.type == "shorthand_property_identifier":
            return entry, self.parser.node_text(entry) + ": "
        if entry.type != "pair":
            kind = entry.type.replace("_", " ")
            raise ApplierError(f"'{target}' is a {kind}, not a key-value pair")
        return entry.child_by_field_name("value"), ""

    def replace_function_body(self, target: str, content: str) -> str:
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = node
        if node.type == "decorated_definition":
            for child in node.named_children:
                if child.type == "function_definition":
                    func_node = child
                    break

        block_node = func_node.child_by_field_name("body")
        if not block_node:
            for child in func_node.children:
                if child.type in ("block", "statement_block", "compound_statement", "body_statement", "constructor_body"):
                    block_node = child
                    break

        if not block_node:
            raise ApplierError(f"Could not find body block for target '{target}'")

        # Python and Ruby use indented body lines between def/class and end markers.
        if self.parser.ext == ".py" or self.parser.ext in (".rb",):
            start_line = block_node.start_point[0]
            end_line = block_node.end_point[0] + 1
        else:
            # JS/TS/C/C++/Go/Java: body is `{ ... }` -- skip the opening brace line.
            start_line = block_node.start_point[0] + 1
            end_line = block_node.end_point[0]
            if start_line > end_line:
                start_line = block_node.start_point[0]
                end_line = start_line + 1

        target_indent = self._get_indent(self.lines[start_line]) if start_line < len(self.lines) else ""
        if not target_indent and start_line < len(self.lines) and self.lines[start_line].strip() == "":
             sig_indent = self._get_indent(self.lines[node.start_point[0]])
             default_indent = "    " if self.parser.ext in (".py", ".rb", ".java") else "  "
             target_indent = sig_indent + default_indent

        content_lines = self._reindent(_content_lines(content), target_indent)

        self.lines = self.lines[:start_line] + content_lines + self.lines[end_line:]
        return self._save()

    def add_method(self, class_target: str, content: str) -> str:
        """
        Add a new method to a class. Placement varies by language:
          - Python/JS/TS/Java/C++/Ruby: inside the class body, after its
                last member (see _insert_member for indentation and spacing;
                a Java enum gets the `;` its constants need before it).
          - Go: as a top-level sibling immediately after the type declaration
                (Go methods are not lexically inside struct definitions).
        """
        node = self.parser.find_node_by_name(class_target)
        if not node:
            raise ApplierError(f"Target class '{class_target}' not found")

        # Go: methods live outside the struct. Insert after the enclosing type_declaration.
        if self.parser.ext == ".go":
            # find_node_by_name returns the type_spec; walk up to the enclosing type_declaration
            target_node = node
            parent = node.parent
            while parent and parent.type != "type_declaration":
                parent = parent.parent
            if parent is not None:
                target_node = parent

            insert_line = target_node.end_point[0] + 1
            content_lines = _content_lines(content)
            # Add a blank separator before and the method content (and a trailing blank for readability)
            sep_before = [""] if insert_line - 1 >= 0 and insert_line - 1 < len(self.lines) and self.lines[insert_line - 1].strip() else []
            self.lines = self.lines[:insert_line] + sep_before + content_lines + self.lines[insert_line:]
            return self._save()

        body = node.child_by_field_name("body")
        if body is None and self.parser.ext != ".rb":
            raise ApplierError(f"Could not find class body for '{class_target}'")
        return self._insert_member(class_target, node, body, content, at_end=True)

    def delete_symbol(self, target: str, include_leading_comments: bool = True) -> str:
        """
        Delete a function/class/method definition. By default also removes the
        contiguous leading comment block (Godoc, Javadoc, `#` comments, `//`
        comments, or C-style `/* ... */` blocks) directly above the symbol --
        pass `include_leading_comments=False` to keep that comment in place.
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found")

        # Decorators and a JS/TS `export` go with the symbol, and its
        # leading comment is the one above them (see _symbol_span).
        first, last = self._symbol_span(node)
        start_line = first.start_point[0]
        end_line = last.end_point[0] + 1

        if include_leading_comments:
            comment_range = self._find_leading_comment_range(start_line)
            if comment_range is not None:
                start_line = comment_range[0]

        self.lines = self.lines[:start_line] + self.lines[end_line:]
        return self._save()

    def _save(self) -> str:
        """
        Write self.lines back to the file. _split_lines dropped only the final
        newline, so adding it back rebuilds untouched lines exactly, blank
        lines at the end of the file included. An edit never leaves more of
        those than the file had, though: deleting the last symbol would
        otherwise strand the blank lines that separated it from the one
        before.
        """
        lines = self.lines
        excess = _trailing_blank_lines(lines) - _trailing_blank_lines(
            _split_lines(self.parser.source_code)
        )
        if excess > 0:
            lines = lines[: len(lines) - excess]
        self._write_text("\n".join(lines) + "\n")
        return "Update successful"

    def _write_text(self, new_source: str) -> None:
        """
        Single exit point for every edit (_save and _write_bytes both end
        here): normalise line endings, refuse a result that would not parse,
        then write the file in its own newline style and refresh the parser.
        """
        # Internal text is LF (see TreeSitterParser); caller-provided content
        # may still carry CRLF.
        new_source = new_source.replace("\r\n", "\n")
        if not new_source.endswith("\n"):
            new_source += "\n"
        try:
            self._check_syntax(new_source.encode("utf-8"))
        except ApplierError:
            # Line-based edits change self.lines before saving; undo that so
            # this instance still mirrors the untouched file.
            self.lines = _split_lines(self.parser.source_code)
            raise
        if self.parser.newline != "\n":
            new_source = new_source.replace("\n", self.parser.newline)
        # newline="" writes the text verbatim, without platform translation.
        with open(self.filepath, "w", encoding="utf-8", newline="") as f:
            f.write(new_source)
        self._refresh_parser_state()

    def _check_syntax(self, new_bytes: bytes) -> None:
        """
        Raise ApplierError if new_bytes would not parse although the current
        file does. A file that already has syntax errors is not guarded, so
        edits to broken files are never blocked.

        tree-sitter grammars lag behind their languages, so for .py and .json
        the standard library's parser (_stdlib_syntax_error) has the last
        word: content it accepts is never refused, even where tree-sitter
        cannot parse it (PEP 696 type parameter defaults). JSON exponents
        written with a `+` (1e+2), which tree-sitter-json cannot parse, are
        masked before parsing (TreeSitterParser.parse), here as for the
        file itself, so json is only a safety net there. For Python it is
        also the judge on its own: it decides
        whether the file was already broken, and it rejects inconsistent
        indentation that tree-sitter accepts. json only ever lifts a refusal
        (and lets a file tree-sitter misparses still count as clean), because
        it also rejects the comments that JSONC files allow. The
        error position comes from tree-sitter while the file parsed cleanly
        there and both parsers agree on the line, else from the standard
        library.
        """
        ext = self.parser.ext
        ts_was_clean = not self.parser.tree.root_node.has_error
        if ext == ".py" or (ext == ".json" and not ts_was_clean):
            if self._stdlib_syntax_error(self.parser.source_bytes) is not None:
                return
        elif not ts_was_clean:
            return

        bad = first_syntax_error(self.parser.parse(new_bytes).root_node)
        stdlib = None
        if ext == ".py" or (ext == ".json" and bad is not None):
            stdlib = self._stdlib_syntax_error(new_bytes)
            if stdlib is None:
                return
        elif bad is None:
            return
        if (
            bad is not None
            and ts_was_clean
            and (stdlib is None or stdlib[0] in (None, bad.start_point[0] + 1))
        ):
            problem = self._describe_syntax_error(bad, new_bytes)
        else:
            problem = stdlib[1]
        raise ApplierError(
            f"Edit refused: the result would have a syntax error at {problem}. "
            f"{self.filepath} was not modified. If you are sure the code is "
            "valid (the parser may not support very new or macro-heavy syntax), "
            "make this edit with your normal edit tool."
        )

    def _stdlib_syntax_error(self, data: bytes) -> tuple[int | None, str] | None:
        """
        Check data with the standard library's parser for a .py or .json file:
        Python's own (that of the interpreter running the server), or json
        with NaN and Infinity rejected as RFC 8259 requires. Return None if it
        accepts data, else the 1-based line of the first error (None when
        unknown) and a 'line L, column C (message)' description of it.
        """
        if self.parser.ext == ".py":
            err = _python_syntax_error(data)
            if err is None:
                return None
            line, column, msg = err.lineno, err.offset, err.msg
        else:
            err = _json_syntax_error(data)
            if err is None:
                return None
            line = getattr(err, "lineno", None)
            column = getattr(err, "colno", None)
            msg = getattr(err, "msg", None) or str(err)
        if not line:
            return None, f"an unknown position ({msg})"
        where = f"line {line}, column {column}" if column else f"line {line}"
        return line, f"{where} ({msg})"

    def _describe_syntax_error(self, node, data: bytes) -> str:
        """Format an ERROR/MISSING node as 'line L, column C (what)', 1-based."""
        line_start = data.rfind(b"\n", 0, node.start_byte) + 1
        column = len(data[line_start : node.start_byte].decode("utf-8", "replace")) + 1
        if node.is_missing:
            what = f"missing {node.type!r}"
        else:
            text = data[node.start_byte : node.end_byte].decode("utf-8", "replace")
            text = text.strip().split("\n")[0]
            if len(text) > 40:
                text = text[:40] + "..."
            what = f"cannot parse {text!r}" if text else "unexpected input"
        return f"line {node.start_point[0] + 1}, column {column} ({what})"

    def _import_node_types(self) -> tuple[str, ...]:
        """Return the AST node types that represent import statements for this file's language."""
        ext = self.parser.ext
        if ext == ".py":
            return ("import_statement", "import_from_statement", "future_import_statement")
        if ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
            return ("import_statement",)
        if ext in (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"):
            return ("preproc_include",)
        if ext == ".go":
            return ("import_declaration",)
        if ext == ".java":
            return ("import_declaration",)
        if ext == ".rb":
            return ("call",)
        return ()

    def add_import(self, import_text: str) -> str:
        """
        Add an import statement to the file. Accepts literal source text:
          - Python: "import foo" or "from foo import bar"
          - JS/TS:  "import { foo } from 'bar';"
          - C/C++:  "#include <foo.h>"
          - Go:     Either a full `import "fmt"` line, or just `"fmt"` /
                    `alias "pkg/path"` as a spec. When a parenthesized
                    `import ( ... )` block already exists, the spec is
                    inserted inside that block (idiomatic Go).
          - Ruby:   "require 'foo'" or "require_relative 'bar'"
          - Java:   "import java.util.List;"
        Skips insertion if an identical import already exists.
        Places the new import after existing imports, or at the top of the file if none exist.
        """
        valid_types = self._import_node_types()
        if not valid_types:
            raise ApplierError(f"add_import is not supported for file type {self.parser.ext}")

        # Go-specific: if there's a parenthesized import block, insert INSIDE it
        # rather than as a new bare line after `)` (which would be a syntax error
        # for spec-only input like `"path/filepath"`).
        if self.parser.ext == ".go":
            go_block = self._find_go_import_block()
            if go_block is not None:
                return self._add_import_to_go_block(go_block, import_text)

        stripped = import_text.strip()
        for line in self.lines:
            if line.strip() == stripped:
                return "Import already exists -- no change made"

        last_import_end = -1
        for child in self.parser.tree.root_node.named_children:
            if child.type not in valid_types:
                continue
            # Ruby: filter "call" to only require/require_relative calls
            if self.parser.ext == ".rb" and child.type == "call":
                if not self._is_ruby_require_call(child):
                    continue
            if child.end_point[0] > last_import_end:
                last_import_end = child.end_point[0]

        if last_import_end >= 0:
            insert_line = last_import_end + 1
        else:
            insert_line = 0

        self.lines = self.lines[:insert_line] + [import_text] + self.lines[insert_line:]
        return self._save()

    def _find_go_import_block(self):
        """Return the first Go `import_spec_list` node (parenthesized block content) if one exists, else None."""
        for child in self.parser.tree.root_node.named_children:
            if child.type != "import_declaration":
                continue
            for sub in child.named_children:
                if sub.type == "import_spec_list":
                    return sub
        return None

    def _add_import_to_go_block(self, spec_list_node, import_text: str) -> str:
        """Insert an import spec into an existing Go parenthesized import block.
        Accepts either a full `import "foo"` line or just `"foo"` / `alias "foo"`."""
        stripped = import_text.strip()
        # Callers may pass either `import "foo"` or just `"foo"`; strip the keyword.
        if stripped.startswith("import "):
            spec_text = stripped[len("import "):].strip()
        else:
            spec_text = stripped

        # Dedupe against existing specs in the block
        for child in spec_list_node.named_children:
            if child.type != "import_spec":
                continue
            existing = self.parser.node_text(child).strip()
            if existing == spec_text:
                return "Import already exists -- no change made"

        # Insert on a new tab-indented line immediately before the closing `)`
        end_line = spec_list_node.end_point[0]
        self.lines = self.lines[:end_line] + ["\t" + spec_text] + self.lines[end_line:]
        return self._save()

    def remove_import(self, import_text: str) -> str:
        """
        Remove a matching import statement from the file. Matches by stripped text content.
        """
        valid_types = self._import_node_types()
        if not valid_types:
            raise ApplierError(
                f"remove_import is not supported for file type {self.parser.ext}"
            )

        stripped = import_text.strip()
        for i, line in enumerate(self.lines):
            if line.strip() == stripped:
                self.lines = self.lines[:i] + self.lines[i + 1 :]
                return self._save()

        raise ApplierError(f"Import '{import_text}' not found in {self.filepath}")

    def _refresh_parser_state(self) -> None:
        """Re-parse the file after a write so subsequent edits see fresh AST."""
        from ast_editor.parser import TreeSitterParser

        self.parser = TreeSitterParser(self.filepath)
        self.lines = _split_lines(self.parser.source_code)

    def _write_bytes(self, new_bytes: bytes) -> None:
        """Write new LF source bytes to disk (via _write_text) and refresh parser state."""
        self._write_text(new_bytes.decode("utf-8"))

    def _indent_unit(self, default: str) -> str:
        """
        One indentation level as this file writes it: a tab if most indented
        lines start with one, otherwise the most common step by which the
        indentation grows from one line to the next; `default` when no line
        is indented.
        """
        steps: dict[int, int] = {}
        tabs = spaces = prev = 0
        for line in self.lines:
            code = line.lstrip(" \t")
            if not code:
                continue
            ws = line[: len(line) - len(code)]
            if "\t" in ws:
                tabs += 1
                continue
            if ws:
                spaces += 1
            if len(ws) > prev:
                steps[len(ws) - prev] = steps.get(len(ws) - prev, 0) + 1
            prev = len(ws)
        if tabs > spaces:
            return "\t"
        if not steps:
            return default
        return " " * max(steps, key=lambda step: (steps[step], -step))

    def _own_line_indent(self, nodes, fallback: str) -> str:
        """Indentation of the last of `nodes` that starts its own line, or
        `fallback` if each of them follows other code on its line."""
        src = self.parser.source_bytes
        for node in reversed(nodes):
            line_start = src.rfind(b"\n", 0, node.start_byte) + 1
            prefix = src[line_start : node.start_byte]
            if not prefix.strip():
                return prefix.decode("utf-8")
        return fallback

    def _insert_entry(
        self,
        container,
        entries: list,
        entry: str,
        *,
        expand_empty: bool,
        empty_trailing_comma: bool,
        default_unit: str,
    ) -> None:
        """
        Write `entry` (e.g. '"key": value') after the last of `entries` in a
        brace-delimited container (JSON object, Python dict, JS/TS object
        literal), following the container's layout: entries one per line get
        a new line at the last entry's indentation, an inline container stays
        inline, and a trailing comma after the last entry is kept (the new
        entry gets one too). A comment on the last entry's line stays there.
        An empty container becomes `{ entry }`, or with `expand_empty` is
        opened onto separate lines (`empty_trailing_comma` adds a comma).
        """
        src = self.parser.source_bytes
        open_brace, close_brace = container.children[0], container.children[-1]
        base_indent = self._get_indent(self.lines[open_brace.start_point[0]])
        inner_indent = base_indent + self._indent_unit(default_unit)
        edits: list[tuple[int, int, str]] = []  # (start, end, replacement)

        if entries:
            last = entries[-1]
            after = [
                c
                for c in container.children
                if c.start_byte >= last.end_byte and c.end_byte <= close_brace.start_byte
            ]
            comma = after[0] if after and after[0].type == "," else None
            end = (comma or last).end_byte
            row = (comma or last).end_point[0]
            for c in after[1 if comma else 0 :]:
                if "comment" not in c.type or c.start_point[0] != row:
                    break
                end, row = c.end_byte, c.end_point[0]
            if close_brace.start_point[0] > row:
                indent = self._own_line_indent(entries, inner_indent)
                line_end = src.find(b"\n", end)
                new_line = "\n" + indent + entry + ("," if comma else "")
                edits.append((line_end, line_end, new_line))
                if comma is None:
                    edits.append((last.end_byte, last.end_byte, ","))
            elif comma is not None:
                edits.append((comma.end_byte, comma.end_byte, f" {entry},"))
            else:
                edits.append((last.end_byte, last.end_byte, f", {entry}"))
        else:
            comma = "," if empty_trailing_comma else ""
            interior = src[open_brace.end_byte : close_brace.start_byte]
            if close_brace.start_point[0] > open_brace.end_point[0]:
                # `{` and `}` on different lines: add a line above the `}`,
                # indented like a comment already inside, if any.
                comments = [c for c in container.named_children if "comment" in c.type]
                indent = self._own_line_indent(comments, inner_indent)
                line_start = src.rfind(b"\n", 0, close_brace.start_byte) + 1
                if src[line_start : close_brace.start_byte].strip():
                    text = f"\n{indent}{entry}{comma}\n{base_indent}"
                    edits.append((close_brace.start_byte, close_brace.start_byte, text))
                else:
                    edits.append((line_start, line_start, f"{indent}{entry}{comma}\n"))
            elif interior.strip():
                # Only a comment between the braces: keep it, add after it.
                pad = "" if interior[-1:].isspace() else " "
                text = f"{pad}{entry} "
                edits.append((close_brace.start_byte, close_brace.start_byte, text))
            elif expand_empty:
                text = f"\n{inner_indent}{entry}{comma}\n{base_indent}"
                edits.append((open_brace.end_byte, close_brace.start_byte, text))
            else:
                edits.append((open_brace.end_byte, close_brace.start_byte, f" {entry} "))

        # Apply back to front. The sort is stable, so of two edits at the same
        # offset the one listed later ends up first (the comma before the new
        # line).
        new_bytes = src
        for start, end, text in sorted(edits, key=lambda e: e[0], reverse=True):
            new_bytes = new_bytes[:start] + text.encode("utf-8") + new_bytes[end:]
        self._write_bytes(new_bytes)

    def _duplicate_key(self, key: str, parent_target: str, value_target: str) -> ApplierError:
        """The error add_key raises for a key its container already has."""

        def quoted(text: str) -> str:
            return f'"{text}"' if "'" in text else f"'{text}'"

        where = quoted(parent_target) if parent_target else "the root"
        return ApplierError(
            f"Key {quoted(key.strip())} already exists in {where}; use replace_value "
            f"with target {quoted(value_target)} to change its value."
        )

    def _delete_entry(self, container, entries: list, idx: int) -> None:
        """
        Delete entries[idx] from a brace-delimited container (JSON object,
        Python dict, JS/TS object literal) along with one adjacent comma, and
        write the file. An entry on lines of its own goes with those whole
        lines, a comment on its last line included; if it was the last entry
        and had no trailing comma, the comma after the entry before it goes
        too (JSON rejects a trailing comma). An entry sharing a line with
        another one is cut up to the next entry when it starts its line (or
        is the first entry), else from the end of the one before it, so one
        separating comma goes with it. Deleting the only entry leaves `{}`
        (when nothing but whitespace and a trailing comma surrounds it)
        rather than a stray comma, which JS would reject.
        """
        src = self.parser.source_bytes
        entry = entries[idx]
        open_brace, close_brace = container.children[0], container.children[-1]
        inner = container.children[1:-1]
        others = [
            c
            for c in inner
            if c != entry and not (c.type == "," and c.start_byte >= entry.end_byte)
        ]
        # The entry's comma, then any comments on the same row.
        after = [c for c in inner if c.start_byte >= entry.end_byte]
        comma = after[0] if after and after[0].type == "," else None
        end = (comma or entry).end_byte
        row = (comma or entry).end_point[0]
        for c in after[1 if comma else 0 :]:
            if "comment" not in c.type or c.start_point[0] != row:
                break
            end = c.end_byte
        line_start = src.rfind(b"\n", 0, entry.start_byte) + 1
        line_end = src.find(b"\n", end)
        starts_line = not src[line_start : entry.start_byte].strip()
        own_lines = (
            starts_line
            and line_end != -1
            and not src[end:line_end].strip()
            and (comma is not None or idx == len(entries) - 1)
        )

        if not others:
            cuts = [(open_brace.end_byte, close_brace.start_byte)]
        elif own_lines:
            cuts = [(line_start, line_end + 1)]
            if comma is None and idx > 0:
                prev_comma = next(
                    (
                        c
                        for c in inner
                        if c.type == ","
                        and entries[idx - 1].end_byte <= c.start_byte < entry.start_byte
                    ),
                    None,
                )
                if prev_comma is not None:
                    cuts.append((prev_comma.start_byte, prev_comma.end_byte))
        elif (starts_line or idx == 0) and idx + 1 < len(entries):
            cuts = [(entry.start_byte, entries[idx + 1].start_byte)]
        elif idx > 0:
            cuts = [(entries[idx - 1].end_byte, entry.end_byte)]
        else:
            cuts = [(entry.start_byte, (comma or entry).end_byte)]

        new_bytes = src
        for start, stop in sorted(cuts, reverse=True):
            new_bytes = new_bytes[:start] + new_bytes[stop:]
        self._write_bytes(new_bytes)

    def _find_json_object_at_path(self, dotted_path: str):
        """Return the JSON object node at the dotted path, or the root object if path is empty."""
        root = self.parser.tree.root_node
        if not dotted_path:
            for child in root.named_children:
                if child.type == "object":
                    return child
            return None
        value_node = self.parser._search_json_dotted(root, dotted_path)
        if value_node and value_node.type == "object":
            return value_node
        return None

    def _json_key_name(self, pair) -> str | None:
        """Decoded key of a JSON pair."""
        return self.parser.json_key_name(pair)

    def _add_key_json(self, parent_target: str, key: str, value: str) -> str:
        parent = self._find_json_object_at_path(parent_target)
        if parent is None:
            raise ApplierError(
                f"JSON object at '{parent_target or '<root>'}' not found"
            )

        # The key is quoted (and escaped) here; one passed already quoted is
        # used as given.
        name = None
        if key.strip().startswith('"'):
            try:
                name = json.loads(key.strip())
            except ValueError:
                pass
        if isinstance(name, str):
            key_text = key.strip()
        else:
            name, key_text = key, json.dumps(key, ensure_ascii=False)

        pairs = [c for c in parent.named_children if c.type == "pair"]
        if any(self._json_key_name(p) == name for p in pairs):
            dotted = f"{parent_target}.{name}" if parent_target else name
            raise self._duplicate_key(name, parent_target, dotted)

        self._insert_entry(
            parent,
            pairs,
            f"{key_text}: {value}",
            expand_empty=True,
            empty_trailing_comma=False,
            default_unit="  ",
        )
        return "Update successful"

    def _add_key_yaml(self, parent_target: str, key: str, value: str) -> str:
        """
        Add `key: value` to a YAML mapping: the top-level mapping of the
        first document with content (parent_target ''), or the value of the key
        parent_target names (TreeSitterParser.find_yaml_pair). A block
        mapping gets a new line at its keys' indentation and a flow mapping
        ({a: 1} or {}) an inline entry, as _insert_entry writes it. A key with no value
        (`parent:`) gets a nested block mapping on the line below, one
        indentation unit deeper, and a file with nothing in it yet (empty or
        only comments) the new line at its end. The key is quoted only when
        it has to be (_yaml_key_source).
        """
        root = self.parser.tree.root_node
        key_text = self._yaml_key_source(key)
        name = self.parser.yaml_key_name(key_text)
        pair = None
        if parent_target:
            pair = self.parser.find_yaml_pair(root, parent_target)
            if pair is None:
                raise ApplierError(f"YAML key '{parent_target}' not found")
            content = pair.child_by_field_name("value")
        else:
            # The first document with content: a stream may start with an
            # empty one (`---` straight after `---`).
            doc = next(
                (
                    c
                    for c in root.named_children
                    if c.type == "document"
                    and any(ch.type in ("block_node", "flow_node") for ch in c.named_children)
                ),
                None,
            )
            content = None
            if doc is not None:
                content = next(
                    (c for c in doc.named_children if c.type in ("block_node", "flow_node")), None
                )
        mapping = self.parser.yaml_mapping(content)
        if content is not None and mapping is None:
            where = f"value at '{parent_target}'" if parent_target else "document root"
            raise ApplierError(
                f"YAML {where} is not a mapping (only a mapping, `{{}}` or a key "
                "with no value can take a new key)"
            )

        entries = [] if mapping is None else [
            c for c in mapping.named_children if "comment" not in c.type
        ]
        for entry in entries:
            key_node = entry
            if entry.type in ("block_mapping_pair", "flow_pair"):
                key_node = entry.child_by_field_name("key")
            if key_node is None or self.parser.yaml_key_name(self.parser.node_text(key_node)) != name:
                continue
            if mapping.type == "flow_mapping":
                # Keys inside a flow mapping are not addressable.
                where = f"'{parent_target}'" if parent_target else "the root"
                raise ApplierError(
                    f"Key '{name}' already exists in the flow mapping at {where}; "
                    "to change its value, rewrite the mapping with replace_value"
                    + (f" on '{parent_target}'." if parent_target else ".")
                )
            dotted = f"{parent_target}.{name}" if parent_target else name
            raise self._duplicate_key(key, parent_target, dotted)

        new_entry = f"{key_text}: {value}"
        if mapping is not None and mapping.type == "flow_mapping":
            self._insert_entry(
                mapping,
                entries,
                new_entry,
                expand_empty=False,
                empty_trailing_comma=False,
                default_unit="  ",
            )
            return "Update successful"

        if mapping is not None:
            last_pair = entries[-1]
            indent = self._get_indent(self.lines[last_pair.start_point[0]])
            insert_line = last_pair.end_point[0] + 1
        elif pair is not None:
            # `parent:` with no value: its new mapping goes below it, deeper
            # than the key's own column.
            src = self.parser.source_bytes
            line_start = src.rfind(b"\n", 0, pair.start_byte) + 1
            column = len(src[line_start : pair.start_byte].decode("utf-8"))
            indent = " " * column + self._indent_unit("  ")
            insert_line = pair.end_point[0] + 1
        else:
            # Nothing in the file yet: the key goes after its last non-blank line.
            indent = ""
            insert_line = len(self.lines)
            while insert_line and not self.lines[insert_line - 1].strip():
                insert_line -= 1
        self.lines = self.lines[:insert_line] + [indent + new_entry] + self.lines[insert_line:]
        return self._save()

    def _yaml_key_source(self, key: str) -> str:
        """
        A key as written in a YAML mapping. A key already in quotes is used
        as given. A name that starts with a letter or `_` and goes on with
        letters, digits, `_`, `-`, `.`, `/` and spaces stays plain, unless
        YAML would read it as a boolean or null (yes, off, null, ...).
        Anything else (a leading digit or indicator such as `-`, `?`, `&`,
        `*`, `!`, `[`; a `:`, `#` or `,`; a tab) is quoted, in the quote
        style most of the file's quoted scalars use, or in double quotes if
        it needs escapes.
        """
        key = key.strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            return key
        if _YAML_PLAIN_KEY.fullmatch(key) and not _YAML_RESERVED.fullmatch(key):
            return key
        needs_escapes = re.search(r"[\x00-\x1f]", key) or _YAML_ESCAPE.search(key)
        quoted = ("single_quote_scalar", "double_quote_scalar")
        if not needs_escapes and self._majority_quote(quoted) == "'":
            return "'" + key.replace("'", "''") + "'"
        text = json.dumps(key, ensure_ascii=False)
        return _YAML_ESCAPE.sub(lambda m: f"\\u{ord(m.group()):04x}", text)


    def _majority_quote(self, string_types: tuple[str, ...]) -> str:
        """The quote character (' or ") that most of the file's string
        nodes (those of `string_types`) start with; '"' on a tie."""
        counts = {'"': 0, "'": 0}
        stack = [self.parser.tree.root_node]
        while stack:
            node = stack.pop()
            if node.type in string_types:
                quote = self.parser.node_text(node)[:1]
                if quote in counts:
                    counts[quote] += 1
                continue
            stack.extend(node.children)
        return "'" if counts["'"] > counts['"'] else '"'

    def _toml_key_taken(self, root, parent_target: str, pairs: list, key: str) -> bool:
        """Whether `key` is already defined in a TOML table (or the root): as
        one of its keys, as the start of a dotted key (`key.x = 1`), or as a
        sub-table header (`[parent.key]`, `[[parent.key]]`). A dotted key
        whose leading parts name a table that has its own header
        (`a.c = 1` beside `[a]`) counts too, since TOML forbids defining that
        table twice."""
        new = [_unquote(p) for p in _split_key_path(key)]
        for pair in pairs:
            have = [_unquote(p) for p in _split_key_path(self.parser.node_text(pair.children[0]))]
            n = min(len(have), len(new))
            if have[:n] == new[:n]:
                return True
        parent = [_unquote(p) for p in _split_key_path(parent_target)] if parent_target else []
        full = parent + new
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in ("table", "table_array_element") and node.named_children:
                header = self.parser.node_text(node.named_children[0])
                h = [_unquote(p) for p in _split_key_path(header)]
                # Headers of the parent table and its ancestors do not count.
                if len(h) > len(parent) and (h[: len(full)] == full or full[: len(h)] == h):
                    return True
            stack.extend(node.named_children)
        return False

    def _add_key_toml(self, parent_target: str, key: str, value: str) -> str:
        """
        Add `key = value` to a TOML table: the root (parent_target ''), a
        [table] named as in its header, or an inline table (`t = { a = 1 }`
        or `{}`) that parent_target names as a key path, which gets the
        entry inline as _insert_entry writes it. The key is quoted only when
        it is not a bare key (_toml_key_source).
        """
        root = self.parser.tree.root_node
        key_text = self._toml_key_source(key)
        inline = None
        if parent_target:
            # Find the table matching parent_target
            table = None
            queue = [root]
            while queue:
                curr = queue.pop(0)
                if curr.type == "table":
                    header = curr.named_children[0] if curr.named_children else None
                    if header:
                        name = self.parser.node_text(header).strip("[] \n")
                        if name == parent_target:
                            table = curr
                            break
                queue.extend(curr.named_children)
            if table is None:
                inline = self.parser._search_toml_dotted(root, parent_target)
                if inline is None:
                    raise ApplierError(f"TOML table '[{parent_target}]' not found")
                if inline.type != "inline_table":
                    raise ApplierError(f"TOML value at '{parent_target}' is not a table")
                pairs = [c for c in inline.named_children if c.type == "pair"]
            else:
                pairs = [c for c in table.named_children if c.type == "pair"]
                if pairs:
                    last_pair = pairs[-1]
                    insert_line = last_pair.end_point[0] + 1
                    indent = self._get_indent(self.lines[last_pair.start_point[0]])
                else:
                    # Empty table: insert on the line after the header
                    header = table.named_children[0]
                    insert_line = header.end_point[0] + 1
                    indent = ""
        else:
            # Root-level pair (before any table)
            top_pairs = [c for c in root.named_children if c.type == "pair"]
            if top_pairs:
                last_pair = top_pairs[-1]
                insert_line = last_pair.end_point[0] + 1
                indent = self._get_indent(self.lines[last_pair.start_point[0]])
            else:
                insert_line = 0
                indent = ""

        siblings = pairs if parent_target else top_pairs
        if self._toml_key_taken(root, parent_target, siblings, key_text):
            if inline is not None:
                # Keys inside an inline table are not addressable.
                raise ApplierError(
                    f"Key '{key_text}' already exists in the inline table at "
                    f"'{parent_target}'; to change its value, rewrite the table "
                    f"with replace_value on '{parent_target}'."
                )
            dotted = f"{parent_target}.{key_text}" if parent_target else key_text
            raise self._duplicate_key(key_text, parent_target, dotted)

        if inline is not None:
            self._insert_entry(
                inline,
                pairs,
                f"{key_text} = {value}",
                expand_empty=False,
                empty_trailing_comma=False,
                default_unit="  ",
            )
            return "Update successful"
        new_line = f"{indent}{key_text} = {value}"
        self.lines = self.lines[:insert_line] + [new_line] + self.lines[insert_line:]
        return self._save()

    def _toml_key_source(self, key: str) -> str:
        """
        A key as written in TOML. Dots separate the parts of a dotted key
        (a.b is key b in table a), as in TOML itself. Each part that is a
        bare key (ASCII letters, digits, `_` and `-`) or is already in
        quotes is kept as given; any other part (with a space, `:`, `#`,
        non-ASCII letters, ...) becomes a basic string ("...", escaped). A
        key with an empty part ('', 'a..b') is quoted whole.
        """
        key = key.strip()
        parts = _split_key_path(key)
        if not all(parts):
            parts = [key]
        out = []
        for part in parts:
            if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
                out.append(part)
            elif re.fullmatch(r"[A-Za-z0-9_-]+", part):
                out.append(part)
            else:
                # json.dumps escapes everything TOML requires except DEL.
                out.append(json.dumps(part, ensure_ascii=False).replace("\x7f", "\\u007f"))
        return ".".join(out)

    def add_key(self, parent_target: str, key: str, value: str) -> str:
        """
        Add a new key-value pair inside a container:
          - JSON objects / YAML mappings / TOML tables (via dotted path to
            parent, from the top level), including YAML flow mappings and
            keys with no value and TOML inline tables (see _add_key_yaml,
            _add_key_toml)
          - Python dict literals (parent_target is the variable name, e.g.
            'CONFIG', optionally followed by keys into nested dicts:
            'CONFIG."db"')
          - JS/TS object literals in module-level const/let/var declarations,
            exported or not (parent_target is 'VarName', or a dotted path into
            nested objects: 'CONFIG.server')
        Raises ApplierError if the container already has the key (use
        replace_value to change an existing value).
        """
        ext = self.parser.ext
        if ext == ".json":
            return self._add_key_json(parent_target, key, value)
        if ext in (".yml", ".yaml"):
            return self._add_key_yaml(parent_target, key, value)
        if ext == ".toml":
            return self._add_key_toml(parent_target, key, value)
        if ext == ".py":
            return self.add_dict_entry(parent_target, key, value)
        if ext in _JS_EXTS:
            return self._add_key_js(parent_target, key, value)
        raise ApplierError(f"add_key is not supported for {ext}")

    def _find_config_pair_by_path(self, dotted_path: str):
        """Find the key-value pair node for a dotted path in JSON/YAML/TOML."""
        root = self.parser.tree.root_node
        ext = self.parser.ext
        if ext == ".json":
            value_node = self.parser._search_json_dotted(root, dotted_path)
            if value_node and value_node.parent and value_node.parent.type == "pair":
                return value_node.parent
        elif ext in (".yml", ".yaml"):
            # The pair itself, so a key with no value (`key:`) is found too.
            return self.parser.find_yaml_pair(root, dotted_path)
        elif ext == ".toml":
            value_node = self.parser._search_toml_dotted(root, dotted_path)
            if value_node and value_node.parent and value_node.parent.type == "pair":
                return value_node.parent
        return None

    def delete_key(self, target: str) -> str:
        """
        Delete a key-value pair from a container:
          - JSON / YAML / TOML config files (dotted path to key).
          - Python module-level dict literals (target is 'DictName' + '.' + key-literal,
            e.g. 'CONFIG."foo"').
          - JS / TS module-level const/let/var object literals (target is
            'VarName.keyName' or 'VarName."quoted-key"', or a longer path into
            nested objects such as 'CONFIG.server.port'). Handles regular
            `{ key: value }` pairs, shorthand `{ key }` properties and methods,
            inside `export const` too.
          - Python targets may also continue into nested dicts
            ('CONFIG."db"."host"').

        For JSON and JS/TS, also removes the adjacent comma to keep the file valid.
        """
        ext = self.parser.ext
        if ext == ".py":
            parts = _split_key_path(target)
            if len(parts) < 2 or not all(parts):
                raise ApplierError(
                    f"For Python dicts, target must be 'DictName.keyExpr' (e.g. 'CONFIG.\"foo\"'), got '{target}'"
                )
            return self.delete_dict_entry(".".join(parts[:-1]), parts[-1])

        if ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
            return self._delete_key_js(target)

        if ext not in (".json", ".yml", ".yaml", ".toml"):
            raise ApplierError(
                f"delete_key is only supported for config files, .py, or JS/TS, not {ext}"
            )

        pair = self._find_config_pair_by_path(target)
        if pair is None:
            raise ApplierError(f"Key '{target}' not found in {self.filepath}")

        if ext == ".json":
            parent = pair.parent
            sibling_pairs = [c for c in parent.named_children if c.type == "pair"]
            self._delete_entry(parent, sibling_pairs, sibling_pairs.index(pair))
            return "Update successful"

        # YAML / TOML: remove the pair's line(s)
        start_line = pair.start_point[0]
        end_line = pair.end_point[0] + 1
        self.lines = self.lines[:start_line] + self.lines[end_line:]
        return self._save()

    def _delete_key_js(self, target: str) -> str:
        """Delete a key from a JS/TS object literal assigned at module level.
        Target format: 'VarName.keyName' or 'VarName."quoted-key"', or a longer
        path into nested object literals ('CONFIG.server.port')."""
        parts = _split_key_path(target)
        if len(parts) < 2 or not all(parts):
            raise ApplierError(
                f"For JS/TS objects, target must be 'VarName.keyName' (e.g. 'CONFIG.port'), got '{target}'"
            )
        obj_node = self._resolve_js_object(parts[:-1])
        key = parts[-1]
        entries = self._js_entries(obj_node)
        target_node = self._find_js_entry(obj_node, key)
        if target_node is None:
            raise ApplierError(f"Key '{key}' not found in {'.'.join(parts[:-1])}")
        self._delete_entry(obj_node, entries, entries.index(target_node))
        return "Update successful"

    def _add_key_js(self, parent_target: str, key: str, value: str) -> str:
        """Add `key: value` to a JS/TS object literal. parent_target is
        'VarName' or a dotted path into nested objects ('CONFIG.server')."""
        parts = _split_key_path(parent_target)
        if not all(parts):
            raise ApplierError(
                "For JS/TS objects, parent_target must be the name of a module-level "
                "const/let/var object literal, dotted for nested objects (e.g. "
                f"'CONFIG' or 'CONFIG.server'), got '{parent_target}'"
            )
        obj_node = self._resolve_js_object(parts)
        key_text = self._js_key_source(key)
        if self._find_js_entry(obj_node, key_text) is not None:
            raise self._duplicate_key(key, parent_target, f"{parent_target}.{key_text}")
        self._insert_entry(
            obj_node,
            self._js_entries(obj_node),
            f"{key_text}: {value}",
            expand_empty=False,
            empty_trailing_comma=True,
            default_unit="  ",
        )
        return "Update successful"

    def _find_js_object_literal(self, var_name: str):
        """Find a module-level const/let/var assigned an object literal.
        Handles plain declarations and ones nested inside `export` statements,
        and TS wrappers such as `{ ... } as const` or `satisfies T`.
        Returns the `object` node or None."""
        def walk(parent):
            for child in parent.named_children:
                if child.type in ("lexical_declaration", "variable_declaration"):
                    for decl in child.named_children:
                        if decl.type != "variable_declarator":
                            continue
                        name_node = decl.child_by_field_name("name")
                        if name_node is None:
                            for c in decl.named_children:
                                if c.type == "identifier":
                                    name_node = c
                                    break
                        if name_node is None:
                            continue
                        if self.parser.node_text(name_node) != var_name:
                            continue
                        value = decl.child_by_field_name("value")
                        if value is None:
                            for c in decl.named_children:
                                if c.type == "object":
                                    value = c
                                    break
                        value = self._unwrap_js_value(value)
                        if value is not None and value.type == "object":
                            return value
                elif child.type == "export_statement":
                    result = walk(child)
                    if result is not None:
                        return result
            return None
        return walk(self.parser.tree.root_node)

    def _unwrap_js_value(self, node):
        """Look through parentheses and TS `as` / `satisfies` / `<T>` / `!`
        wrappers around a value, e.g. to the object in `{ ... } as const`."""
        while node is not None and node.type in (
            "parenthesized_expression",
            "as_expression",
            "satisfies_expression",
            "type_assertion",
            "non_null_expression",
        ):
            inner = node.named_children
            if not inner:
                return None
            # `<T>value` puts the type first; the others start with the value.
            node = inner[-1] if node.type == "type_assertion" else inner[0]
        return node

    def _js_entries(self, obj_node) -> list:
        """Entries of a JS/TS object literal (pairs, shorthand properties,
        methods, spreads), without the comments between them."""
        return [c for c in obj_node.named_children if "comment" not in c.type]

    def _js_entry_name(self, entry) -> str | None:
        """Property name an object-literal entry defines ('a' for a, "a" and
        'a'; a computed key keeps its brackets), or None for a spread."""
        if entry.type == "shorthand_property_identifier":
            return self.parser.node_text(entry)
        if entry.type == "pair":
            key_node = entry.child_by_field_name("key")
            if key_node is None and entry.named_children:
                key_node = entry.named_children[0]
        elif entry.type == "method_definition":
            key_node = entry.child_by_field_name("name")
        else:
            return None
        if key_node is None:
            return None
        return _unquote(self.parser.node_text(key_node).strip())

    def _find_js_entry(self, obj_node, key: str):
        """The entry of a JS/TS object literal that defines `key` (bare,
        quoted, or a computed '[expr]' as written), or None."""
        name = _unquote(key.strip())
        for entry in self._js_entries(obj_node):
            if self._js_entry_name(entry) == name:
                return entry
        return None

    def _resolve_js_object(self, parts: list[str]):
        """
        Return the JS/TS object literal a key path names: parts[0] is a
        module-level const/let/var (see _find_js_object_literal), and each
        further part a key whose value is a nested object literal.
        """
        obj_node = self._find_js_object_literal(parts[0])
        if obj_node is None:
            raise ApplierError(
                f"'{parts[0]}' not found as a module-level const/let/var assigned to an object literal"
            )
        for i in range(1, len(parts)):
            entry = self._find_js_entry(obj_node, parts[i])
            if entry is None:
                raise ApplierError(f"Key '{parts[i]}' not found in {'.'.join(parts[:i])}")
            value = None
            if entry.type == "pair":
                value = self._unwrap_js_value(entry.child_by_field_name("value"))
            if value is None or value.type != "object":
                raise ApplierError(f"'{'.'.join(parts[: i + 1])}' is not an object literal")
            obj_node = value
        return obj_node

    def _js_key_source(self, key: str) -> str:
        """
        A key as written in a JS/TS object literal. Identifiers and plain
        non-negative integers stay bare, a key already in quotes or a computed
        '[expr]' key is used as given, and anything else is quoted with the
        quote character most of the file's strings use.
        """
        key = key.strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            return key
        if key.startswith("[") and key.endswith("]"):
            return key
        if len(key) >= 2 and key[0] == key[-1] == "`":
            key = key[1:-1]  # template literals cannot be property names
        if re.fullmatch(r"[A-Za-z_$][\w$]*|0|[1-9][0-9]*", key, re.ASCII):
            return key

        if self._majority_quote(("string",)) == "'":
            escaped = key.replace("\\", "\\\\").replace("'", "\\'")
            return "'" + escaped.replace("\n", "\\n").replace("\r", "\\r") + "'"
        return json.dumps(key, ensure_ascii=False)

    def _resolve_yaml_value(self, value_node):
        """Unwrap a YAML block_node/flow_node to get the underlying collection (block_sequence, flow_sequence, block_mapping, flow_mapping)."""
        if value_node is None:
            return None
        if value_node.type in (
            "block_sequence",
            "flow_sequence",
            "block_mapping",
            "flow_mapping",
        ):
            return value_node
        for child in value_node.named_children:
            inner = self._resolve_yaml_value(child)
            if inner:
                return inner
        return None

    def append_to_array(self, target: str, value: str) -> str:
        """
        Append a value to an array/list:
          - JSON arrays / YAML sequences / TOML arrays (via dotted path to array)
          - Python module-level list literals (target is the variable name)
        """
        ext = self.parser.ext
        if ext == ".py":
            return self.append_to_list(target, value)

        root = self.parser.tree.root_node

        if ext == ".json":
            arr = self.parser._search_json_dotted(root, target)
            if arr is None or arr.type != "array":
                raise ApplierError(f"JSON array at '{target}' not found")
            elements = [c for c in arr.named_children]
            source_bytes = self.parser.source_bytes
            if elements:
                last = elements[-1]
                indent = self._get_indent(self.lines[last.start_point[0]])
                insertion = f",\n{indent}{value}"
                insert_byte = last.end_byte
            else:
                close_line = arr.end_point[0]
                close_indent = (
                    self._get_indent(self.lines[close_line])
                    if close_line < len(self.lines)
                    else ""
                )
                inner_indent = close_indent + "  "
                insertion = f"\n{inner_indent}{value}\n{close_indent}"
                insert_byte = arr.start_byte + 1
            new_bytes = (
                source_bytes[:insert_byte]
                + insertion.encode("utf-8")
                + source_bytes[insert_byte:]
            )
            self._write_bytes(new_bytes)
            return "Update successful"

        if ext == ".toml":
            arr = self.parser._search_toml_dotted(root, target)
            if arr is None or arr.type != "array":
                raise ApplierError(
                    f"TOML array at '{target}' not found (is it an inline array?)"
                )
            elements = [c for c in arr.named_children]
            source_bytes = self.parser.source_bytes
            if elements:
                last = elements[-1]
                if arr.start_point[0] == arr.end_point[0]:
                    insertion = f", {value}"
                    insert_byte = last.end_byte
                else:
                    indent = self._get_indent(self.lines[last.start_point[0]])
                    insertion = f",\n{indent}{value}"
                    insert_byte = last.end_byte
            else:
                insertion = f"{value}"
                insert_byte = arr.start_byte + 1
            new_bytes = (
                source_bytes[:insert_byte]
                + insertion.encode("utf-8")
                + source_bytes[insert_byte:]
            )
            self._write_bytes(new_bytes)
            return "Update successful"

        if ext in (".yml", ".yaml"):
            value_node = self.parser._search_yaml_dotted(root, target)
            collection = self._resolve_yaml_value(value_node)
            if collection is None or collection.type not in (
                "block_sequence",
                "flow_sequence",
            ):
                raise ApplierError(f"YAML sequence at '{target}' not found")
            if collection.type == "flow_sequence":
                elements = [c for c in collection.named_children]
                source_bytes = self.parser.source_bytes
                if elements:
                    insertion = f", {value}"
                    insert_byte = elements[-1].end_byte
                else:
                    insertion = f"{value}"
                    insert_byte = collection.start_byte + 1
                new_bytes = (
                    source_bytes[:insert_byte]
                    + insertion.encode("utf-8")
                    + source_bytes[insert_byte:]
                )
                self._write_bytes(new_bytes)
                return "Update successful"
            items = [
                c for c in collection.named_children if c.type == "block_sequence_item"
            ]
            if not items:
                raise ApplierError(
                    "Cannot append to empty YAML block sequence (unsupported in v1)"
                )
            last = items[-1]
            indent = self._get_indent(self.lines[last.start_point[0]])
            insert_line = last.end_point[0] + 1
            # Multi-line values (e.g. a mapping with several keys) get the
            # `-` marker on the first line and a 2-space hanging indent on
            # continuation lines so they nest under the sequence item.
            value_lines = _content_lines(value) or [""]
            new_item_lines = [f"{indent}- {value_lines[0]}"]
            for cont in value_lines[1:]:
                new_item_lines.append(f"{indent}  {cont}")
            self.lines = (
                self.lines[:insert_line]
                + new_item_lines
                + self.lines[insert_line:]
            )
            return self._save()

        raise ApplierError(f"append_to_array is not supported for {ext}")

    def remove_from_array(self, target: str, value_match: str) -> str:
        """
        Remove the first element matching value_match (stripped text equality) from
        an array/list in a config file OR a Python module-level list literal.
        """
        ext = self.parser.ext
        if ext == ".py":
            return self.remove_from_list(target, value_match)

        root = self.parser.tree.root_node
        stripped_match = value_match.strip()

        def _remove_element_bytes(arr_node, elements):
            if not elements:
                raise ApplierError(f"Array at '{target}' is empty")
            idx = None
            for i, el in enumerate(elements):
                text = self.parser.node_text(el).strip()
                if text == stripped_match:
                    idx = i
                    break
            if idx is None:
                raise ApplierError(
                    f"Value '{value_match}' not found in array at '{target}'"
                )
            source_bytes = self.parser.source_bytes
            start = elements[idx].start_byte
            end = elements[idx].end_byte
            if idx > 0:
                start = elements[idx - 1].end_byte
            elif idx + 1 < len(elements):
                end = elements[idx + 1].start_byte
            new_bytes = source_bytes[:start] + source_bytes[end:]
            self._write_bytes(new_bytes)

        if ext == ".json":
            arr = self.parser._search_json_dotted(root, target)
            if arr is None or arr.type != "array":
                raise ApplierError(f"JSON array at '{target}' not found")
            _remove_element_bytes(arr, [c for c in arr.named_children])
            return "Update successful"

        if ext == ".toml":
            arr = self.parser._search_toml_dotted(root, target)
            if arr is None or arr.type != "array":
                raise ApplierError(f"TOML array at '{target}' not found")
            _remove_element_bytes(arr, [c for c in arr.named_children])
            return "Update successful"

        if ext in (".yml", ".yaml"):
            value_node = self.parser._search_yaml_dotted(root, target)
            collection = self._resolve_yaml_value(value_node)
            if collection is None or collection.type not in (
                "block_sequence",
                "flow_sequence",
            ):
                raise ApplierError(f"YAML sequence at '{target}' not found")
            if collection.type == "flow_sequence":
                _remove_element_bytes(
                    collection, [c for c in collection.named_children]
                )
                return "Update successful"
            items = [
                c for c in collection.named_children if c.type == "block_sequence_item"
            ]
            match_idx = None
            for i, it in enumerate(items):
                text = self.parser.node_text(it).strip().lstrip("-").strip()
                if text == stripped_match:
                    match_idx = i
                    break
            if match_idx is None:
                raise ApplierError(
                    f"Value '{value_match}' not found in YAML sequence at '{target}'"
                )
            start_line = items[match_idx].start_point[0]
            end_line = items[match_idx].end_point[0] + 1
            self.lines = self.lines[:start_line] + self.lines[end_line:]
            return self._save()

        raise ApplierError(f"remove_from_array is not supported for {ext}")

    def add_field(self, class_target: str, content: str) -> str:
        """
        Add a field/attribute/member at the top of a class body (fields-before-methods
        convention): before its first member, but after a Python class
        docstring or a Java enum's constants. Indentation and spacing as for
        add_method (_insert_member).

        Design decision: option (a) -- the caller provides the literal text to insert.
        The tool does NOT auto-wrap in language-specific constructs (e.g. no implicit
        `attr_accessor :foo` for Ruby, no implicit type inference for Go). Pass exactly
        what you want to appear in the source.
        """
        node = self.parser.find_node_by_name(class_target)
        if not node:
            raise ApplierError(f"Target class '{class_target}' not found")

        # Go: field goes inside the struct_type's braces (which live inside type_spec)
        if self.parser.ext == ".go":
            struct_node = None
            for c in node.named_children:
                if c.type == "struct_type":
                    struct_node = c
                    break
            if struct_node is None:
                raise ApplierError(f"'{class_target}' is not a struct; add_field needs a struct_type")
            body = next(
                (c for c in struct_node.named_children if c.type == "field_declaration_list"),
                None,
            )
        else:
            body = node.child_by_field_name("body")
        if body is None and self.parser.ext != ".rb":
            raise ApplierError(f"Could not find class body for '{class_target}'")
        return self._insert_member(class_target, node, body, content, at_end=False)

    def _insert_member(self, class_target: str, node, body, content: str, at_end: bool) -> str:
        """
        Insert content as a member of the class `node`, whose members `body`
        holds (None for an empty Ruby class): after the last member for
        add_method (at_end=True), else before the first one, but after a
        Python class docstring, for add_field. A Java enum's members are
        those after its constants, which stay first (_java_enum_members).

        The content is re-indented like the class's existing members (see
        _member_indent), keeping its own relative indentation, written in
        tabs when the members are indented with tabs (_tab_indent). A
        method is separated from the member before it as the class separates
        its methods (_method_gap); a field gets a blank line after it when
        the member it lands above is a method with no blank line between
        them. No blank line is added before the closing brace. A braced body
        on one line (`class K {}`, `class K { a() {} }`) is rebuilt over
        several lines, the existing members on one of their own, and
        comments that follow the `{` on its line stay there. A Python or
        Ruby class whose body shares a line with its header (or its `end`)
        has no line to insert on and is refused.
        """
        ext = self.parser.ext
        lines = _content_lines(content)
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            raise ApplierError("content is empty: pass the source of the member to add")
        members = list(body.named_children) if body is not None else []
        # Members start after the `{`; a Java enum's after its constants
        # and the `;` that ends them (`semi`, written when they have none).
        start, semi, indent_from = (body.start_byte + 1 if body is not None else 0), b"", members
        if body is not None and body.type == "enum_body":
            start, semi, members = self._java_enum_members(body)
            indent_from = members or indent_from
        member_indent = self._member_indent(node, indent_from)
        if "\t" in member_indent:
            lines = self._tab_indent(lines)
        lines = self._reindent(lines, member_indent)
        method_types = self._interface_func_types() | {"method_signature", "abstract_method_signature"}
        gap_before = self._method_gap(body, members, method_types) if at_end and members else 0
        compact = ApplierError(
            f"The body of '{class_target}' shares a line with its header or its "
            "end, so there is no line of its own to add a member on. Rewrite the "
            "class over several lines with replace_function."
        )

        if ext in (".py", ".rb"):
            rest = members
            if ext == ".py":
                if members and not self._starts_line(members[0].start_byte):
                    raise compact
                if at_end:
                    insert_line = node.end_point[0] + 1
                elif members and self._is_docstring_node(members[0]):
                    insert_line = members[0].end_point[0] + 1
                    rest = members[1:]
                else:
                    insert_line = members[0].start_point[0] if members else body.start_point[0]
            else:
                end = node.children[-1]
                if end.type != "end" or not self._starts_line(end.start_byte):
                    raise compact
                if not members:
                    insert_line = end.start_point[0]
                elif not self._starts_line(members[0].start_byte) or body.end_point[0] >= end.start_point[0]:
                    raise compact
                else:
                    insert_line = body.end_point[0] + 1 if at_end else members[0].start_point[0]
            gap_after = 0
            if not at_end:
                following = next((m for m in rest if not self._is_aside(m)), None)
                if (
                    following is not None
                    and following.type in method_types
                    and all(line.strip() for line in self.lines[insert_line : rest[0].start_point[0]])
                ):
                    gap_after = 1
            new_lines = [""] * gap_before + lines + [""] * gap_after
            self.lines = self.lines[:insert_line] + new_lines + self.lines[insert_line:]
            return self._save()

        src = self.parser.source_bytes
        open_b, close_b = body.start_byte, body.end_byte - 1
        if src[open_b : open_b + 1] != b"{" or src[close_b : close_b + 1] != b"}":
            raise ApplierError(f"Could not find the braces of the body of '{class_target}'")
        class_indent = self._get_indent(self.lines[node.start_point[0]]).encode("utf-8")
        indent = member_indent.encode("utf-8")
        text = "\n".join(lines).encode("utf-8")
        following = next((m for m in members if not self._is_aside(m)), None)
        gap = b"\n" if not at_end and following is not None and following.type in method_types else b""
        constants = src[open_b + 1 : start].strip()
        if (body.start_point[0] == body.end_point[0] and (members or constants)) or (semi and not constants):
            # A body on one line (or an enum with no constants) is rebuilt
            # over several lines: the enum constants (or a lone `;`), the
            # existing members and the new one each on their own.
            existing = src[start:close_b].strip()
            parts = [indent + constants + semi, b""] if semi or constants else []
            if not existing:
                parts.append(text)
            elif at_end:
                parts += [indent + existing] + [b""] * gap_before + [text]
            else:
                parts += [text] + [b""] * len(gap) + [indent + existing]
            new = src[: open_b + 1] + b"\n" + b"\n".join(parts) + b"\n" + class_indent + src[close_b:]
        elif not members and constants:
            # A Java enum with only its constants: the member goes on a line
            # of its own after them, one blank line between.
            last = max([start] + [c.end_byte for c in body.named_children])
            nl = src.find(b"\n", last)
            if 0 <= nl < close_b:
                pos = nl + 1
                new = src[:start] + semi + src[start:pos] + b"\n" + text + b"\n" + src[pos:]
            else:
                new = (
                    src[:start] + semi + src[start:close_b].rstrip(b" \t") + b"\n\n"
                    + text + b"\n" + class_indent + src[close_b:]
                )
        elif not members:
            # Only whitespace between the braces: the member goes on lines
            # of its own, and the `}` keeps its line (or gets one).
            close_start = src.rfind(b"\n", 0, close_b) + 1
            close_indent = src[close_start:close_b] if self._starts_line(close_b) else class_indent
            new = src[: open_b + 1] + b"\n" + text + b"\n" + close_indent + src[close_b:]
        elif at_end:
            spacing = b"\n" * gap_before
            if self._starts_line(close_b):
                # After the last member's line; blank lines that were
                # before the `}` stay there.
                pos = src.find(b"\n", members[-1].end_byte) + 1
                new = src[:pos] + spacing + text + b"\n" + src[pos:]
            else:
                new = src[:close_b].rstrip(b" \t") + b"\n" + spacing + text + b"\n" + class_indent + src[close_b:]
        else:
            # Comments right after the `{` (or an enum's `;`) on its line.
            n, row = 0, src.count(b"\n", 0, start)
            while n < len(members) and "comment" in members[n].type and members[n].start_point[0] == row:
                row = members[n].end_point[0]
                n += 1
            nl = src.find(b"\n", members[n - 1].end_byte) if n else -1
            if self._starts_line(members[0].start_byte):
                pos = src.rfind(b"\n", 0, members[0].start_byte) + 1
                new = src[:pos] + text + b"\n" + gap + src[pos:]
            elif n and (n == len(members) or members[n].start_point[0] > row) and 0 <= nl < close_b:
                # Only comments follow the `{` on its line: they stay there
                # (a NOSONAR or NOLINT there applies to that line), and the
                # member goes on the next line, above any blank lines.
                pos = nl + 1
                if n < len(members) and b"\n" in src[pos : members[n].start_byte]:
                    gap = b""
                new = src[:pos] + text + b"\n" + gap + src[pos:]
            else:
                # The first member follows the `{` (or an enum's `;`) on its
                # line: it moves to a line of its own below the new one, and
                # a blank line separates enum constants from the new member.
                new = (
                    src[:start] + b"\n" + (b"\n" if constants else b"") + text + b"\n" + gap
                    + indent + src[start:].lstrip(b" \t")
                )
        self._write_bytes(new)
        return "Update successful"

    def _java_enum_members(self, body):
        """
        Where the members of the Java enum `body` start, as (byte, semi,
        members): after the `;` that ends its constants, with the members
        that follow it, or, when it has none of those, after the last
        constant (and its trailing comma), with semi b";" for the `;` Java
        needs there before any other member, and no members.
        """
        decls = next((c for c in body.named_children if c.type == "enum_body_declarations"), None)
        if decls is not None:
            return decls.children[0].end_byte, b"", list(decls.named_children)
        constants = [c for c in body.children if c.type in ("enum_constant", ",")]
        return (constants[-1].end_byte if constants else body.start_byte + 1), b";", []

    @staticmethod
    def _tab_indent(lines: list[str]) -> list[str]:
        """
        `lines` with the indentation they have beyond their first line's
        written in tabs: one per indentation step of the content (the
        smallest such indentation it has), any spaces left over kept. Lines
        indented less than the first, and content that already uses tabs
        for it, are left as they are.
        """
        first = lines[0]
        base = first[: len(first) - len(first.lstrip(" \t"))]
        extra = []
        for line in lines:
            rest = line[len(base) :] if line.strip() and line.startswith(base) else ""
            extra.append(rest[: len(rest) - len(rest.lstrip(" \t"))])
        widths = [len(ws) for ws in extra if ws]
        if not widths or any("\t" in ws for ws in extra):
            return lines
        step = min(widths)
        result = []
        for line, ws in zip(lines, extra):
            if ws:
                tabs, spaces = divmod(len(ws), step)
                line = base + "\t" * tabs + " " * spaces + line[len(base) + len(ws) :]
            result.append(line)
        return result

    def _starts_line(self, byte: int) -> bool:
        """Whether only whitespace precedes `byte` on its line."""
        src = self.parser.source_bytes
        return not src[src.rfind(b"\n", 0, byte) + 1 : byte].strip()

    @staticmethod
    def _is_aside(node) -> bool:
        """Class-body nodes that are not members of their own: comments,
        decorators (TS puts a method's beside it) and C++ access labels."""
        return node.type in ("decorator", "access_specifier") or "comment" in node.type

    def _member_indent(self, node, members) -> str:
        """
        Indentation for a new member of the class `node`: that of its last
        member on a line of its own (comments and decorators only when there
        is no such member; C++ access labels never), else the class line's
        indentation plus one indent unit of the file, or of the language when
        no line in the file is indented.
        """
        indent = self._own_line_indent([m for m in members if not self._is_aside(m)], None)
        if indent is None:
            indent = self._own_line_indent(
                [m for m in members if m.type != "access_specifier"], None
            )
        if indent is None:
            default = {".py": "    ", ".java": "    ", ".go": "\t"}.get(self.parser.ext, "  ")
            indent = self._get_indent(self.lines[node.start_point[0]]) + self._indent_unit(default)
        return indent

    def _method_gap(self, body, members, method_types) -> int:
        """
        Blank lines (0 or 1) to put between a new method and the member
        before it, the way the class separates its methods: 1 if any method
        has a blank line between it (or its decorators and leading comment)
        and the member before it, 0 if there are such pairs and none does.
        A class with no such pair gets 1, a TS interface 0, as interface
        members are usually written one per line. A method added right
        after a C++ access label (`public:`) goes directly under it.
        """
        labels = [m for m in members if "comment" not in m.type]
        if labels and labels[-1].type == "access_specifier":
            return 0
        code = [m for m in members if not self._is_aside(m)]
        stacked = False
        for prev, cur in zip(code, code[1:]):
            if cur.type not in method_types:
                continue
            start = self._symbol_span(cur)[0].start_point[0]
            if any(not line.strip() for line in self.lines[prev.end_point[0] + 1 : start]):
                return 1
            stacked = True
        if stacked:
            return 0
        return 0 if body.type == "interface_body" and self.parser.ext in _JS_EXTS else 1

    def replace_signature(self, target: str, new_signature: str) -> str:
        """
        Replace only the signature of a function (everything before its body),
        preserving the body. The new_signature should include any trailing
        punctuation expected by the language (e.g. ':' for Python, '(' style
        for JS/C/C++). Indentation on the first line is ignored, so indented
        and unindented signatures both work; continuation lines (parameters,
        or the def after a decorator line) are re-based with the first line
        when it is indented or when one of them is indented less than the
        definition, and are otherwise taken as written.

        Decorators (Python, JS/TS) and Java annotations are preserved when
        new_signature has none; if it includes its own, those replace them.
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = node
        if node.type == "decorated_definition":
            for child in node.named_children:
                if child.type == "function_definition":
                    func_node = child
                    break

        body = func_node.child_by_field_name("body")
        if body is None:
            raise ApplierError(f"Could not find body for target '{target}'")

        sig_end = func_node.start_byte
        for child in func_node.children:
            if child == body:
                break
            sig_end = child.end_byte

        # The signature is spliced in at the definition's own column, so drop
        # the caller's indentation from its first line (a copied
        # "    def get(self):" used to come out doubly indented). Continuation
        # lines keep their indentation relative to that first line when it
        # was indented, or when one of them sits left of the definition (an
        # unindented "@staticmethod\ndef b(x):"); otherwise they are taken
        # as written, as read_symbol(depth="signature") returns them.
        sig_lines = new_signature.replace("\r\n", "\n").split("\n")
        while len(sig_lines) > 1 and not sig_lines[0].strip():
            sig_lines.pop(0)
        given_indent = self._get_indent(sig_lines[0])
        file_indent = self._get_indent(self.lines[func_node.start_point[0]])
        if given_indent or any(
            line.strip() and len(self._get_indent(line)) < len(file_indent)
            for line in sig_lines[1:]
        ):
            sig_lines = [sig_lines[0][len(given_indent) :]] + [
                file_indent + line[len(given_indent) :]
                if line.startswith(given_indent)
                else line
                for line in sig_lines[1:]
            ]
        new_signature = "\n".join(sig_lines).rstrip()

        # Decorators and annotations stay unless new_signature brings its
        # own, which then replace them. Python's and TS's sit outside
        # func_node (TS's as siblings in the class body), so new ones widen
        # the span back over them; Java annotations (in `modifiers`) and JS
        # decorators are inside it, so keeping them narrows the span.
        replace_from, kept = func_node.start_byte, ""
        if node.type == "decorated_definition":
            if new_signature.startswith("@"):
                replace_from = node.start_byte
        elif self._signature_has_annotations(new_signature):
            prev = func_node.prev_named_sibling
            while prev is not None and prev.type == "decorator":
                replace_from = prev.start_byte
                prev = prev.prev_named_sibling
        else:
            replace_from, kept = self._annotation_span(func_node)

        source_bytes = self.parser.source_bytes
        new_bytes = (
            source_bytes[:replace_from]
            + (kept + new_signature).encode("utf-8")
            + source_bytes[sig_end:]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

    def _signature_has_annotations(self, signature: str) -> bool:
        """
        Whether a Java signature has annotations among its modifiers, or a
        JS/TS one its own decorators. The signature is parsed as a method of a
        stub class, so annotations and decorators on parameters do not count.
        """
        ext = self.parser.ext
        if ext != ".java" and ext not in _JS_EXTS:
            return False
        stub = f"class __Signature__ {{\n{signature}\n{{}}\n}}\n".encode("utf-8")
        stack = [self.parser.parser.parse(stub).root_node]
        while stack:
            node = stack.pop()
            if ext == ".java":
                if node.type in (
                    "method_declaration",
                    "constructor_declaration",
                    "compact_constructor_declaration",
                ):
                    mods = next((c for c in node.children if c.type == "modifiers"), None)
                    return mods is not None and any(
                        c.type in ("marker_annotation", "annotation") for c in mods.children
                    )
            elif node.type == "decorator":
                # JS puts a method's decorators inside method_definition,
                # TS beside it in the class body; either way before the
                # parameters, which are skipped below.
                return True
            if node.type != "formal_parameters":
                stack.extend(reversed(node.named_children))
        # Not parseable as a method: go by its first character.
        return signature.lstrip().startswith("@")

    def _annotation_span(self, func_node) -> tuple[int, str]:
        """
        For replace_signature on Java and JS: the byte where the replaced span
        starts, just after the definition's leading annotations or decorators
        (and any comments among them), so they stay as written; and the text
        of annotations that only follow other modifiers (`public @Deprecated
        String f()`), which is put in front of the new signature.
        """
        ext = self.parser.ext
        if ext == ".java":
            mods = next((c for c in func_node.children if c.type == "modifiers"), None)
            if mods is None:
                return func_node.start_byte, ""
            tokens = list(mods.children) + [
                c for c in func_node.children if c.start_byte >= mods.end_byte
            ]
            kinds = ("marker_annotation", "annotation")
        elif ext in _JS_EXTS:
            tokens = list(func_node.children)
            kinds = ("decorator",)
        else:
            return func_node.start_byte, ""
        i = 0
        while i < len(tokens) and (
            tokens[i].type in kinds or (i > 0 and "comment" in tokens[i].type)
        ):
            i += 1
        start = func_node.start_byte
        if 0 < i < len(tokens):
            start = tokens[i].start_byte
        later = [t for t in tokens[i:] if t.type in kinds]
        return start, "".join(self.parser.node_text(t) + " " for t in later)

    def list_symbols(self) -> str:
        """
        Return a formatted outline of top-level functions, classes, and methods in
        the file. Read-only. Output is a multi-line string: one entry per line,
        formatted as `<type> <name> (line N)`.
        """
        ext = self.parser.ext
        root = self.parser.tree.root_node

        if ext == ".py":
            class_types = {"class_definition"}
            func_types = {"function_definition", "decorated_definition"}
        elif ext in (".ts", ".tsx"):
            class_types = {"class_declaration", "interface_declaration"}
            func_types = {"function_declaration", "method_definition"}
        elif ext in (".js", ".jsx", ".mjs", ".cjs"):
            class_types = {"class_declaration"}
            func_types = {"function_declaration", "method_definition"}
        elif ext in (".c", ".h"):
            class_types = {"struct_specifier", "union_specifier", "enum_specifier"}
            func_types = {"function_definition"}
        elif ext in (".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"):
            class_types = {"class_specifier", "struct_specifier", "union_specifier", "enum_specifier", "namespace_definition"}
            func_types = {"function_definition"}
        elif ext == ".rb":
            class_types = {"class", "module"}
            func_types = {"method", "singleton_method"}
        elif ext == ".go":
            return self._list_symbols_go(root)
        elif ext == ".java":
            class_types = {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"}
            func_types = {"method_declaration", "constructor_declaration"}
        else:
            raise ApplierError(f"list_symbols is not supported for file type {ext}")

        def get_name(node):
            inner = node
            if node.type == "decorated_definition":
                for c in node.named_children:
                    if c.type == "function_definition":
                        inner = c
                        break
            name_node = inner.child_by_field_name("name")
            if name_node is None and inner.type == "function_definition":
                name_node = self.parser._extract_c_function_name(inner) if hasattr(self.parser, "_extract_c_function_name") else None
            if name_node is None:
                return "<anonymous>"
            return self.parser.node_text(name_node)

        def walk_class_methods(class_node):
            body = class_node.child_by_field_name("body")
            if body is None:
                return []
            methods = []
            # BFS walk of the class body so we catch methods nested inside
            # containers like Java's `enum_body_declarations`.
            queue = list(body.named_children)
            while queue:
                child = queue.pop(0)
                if child.type == "decorated_definition":
                    definition = child.child_by_field_name("definition")
                    if definition is not None and definition.type == "class_definition":
                        # A nested class, decorated: not listed, like an
                        # undecorated one.
                        continue
                if child.type in func_types:
                    methods.append((get_name(child), first_line(child)))
                else:
                    # Descend into sub-containers (e.g. enum_body_declarations)
                    if child.type in ("enum_body_declarations", "class_body", "interface_body"):
                        queue.extend(child.named_children)
            return methods

        def first_line(node):
            # A symbol starts at its decorators or JS/TS `export`.
            return self._symbol_span(node)[0].start_point[0] + 1

        lines_out = []
        for child in root.named_children:
            name, kind_type = None, child.type
            if child.type == "export_statement":
                # JS/TS: list the exported declaration under its own name;
                # an anonymous `export default function/class` is `default`.
                decl = child.child_by_field_name("declaration")
                if decl is not None:
                    child, kind_type = decl, decl.type
                else:
                    child = self.parser.anonymous_default_export(child)
                    if child is None:
                        continue
                    name, kind_type = "default", DEFAULT_EXPORT_KINDS[child.type]
            elif child.type == "decorated_definition":
                # Python: a decorated class is listed as a class.
                definition = child.child_by_field_name("definition")
                if definition is not None and definition.type == "class_definition":
                    child, kind_type = definition, definition.type
            if kind_type in class_types:
                name = name or get_name(child)
                kind_map = {
                    "class_definition": "class",
                    "class_declaration": "class",
                    "class_specifier": "class",
                    "class": "class",
                    "module": "module",
                    "interface_declaration": "interface",
                    "enum_declaration": "enum",
                    "record_declaration": "record",
                }
                kind = kind_map.get(child.type, child.type)
                lines_out.append(f"{kind} {name} (line {first_line(child)})")
                for mname, mline in walk_class_methods(child):
                    lines_out.append(f"  method {name}.{mname} (line {mline})")
            elif kind_type in func_types:
                name = name or get_name(child)
                lines_out.append(f"function {name} (line {first_line(child)})")

        if not lines_out:
            return "(no top-level symbols found)"
        return "\n".join(lines_out)

    def _get_signature(self, target: str) -> str:
        """
        Return the signature text of a function (everything before its body),
        with surrounding whitespace stripped. Read-only.
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = node
        if node.type == "decorated_definition":
            for child in node.named_children:
                if child.type == "function_definition":
                    func_node = child
                    break

        body = func_node.child_by_field_name("body")
        if body is None:
            raise ApplierError(f"Could not find body for target '{target}'")

        sig_end = func_node.start_byte
        for child in func_node.children:
            if child == body:
                break
            sig_end = child.end_byte

        signature = self.parser.source_bytes[func_node.start_byte : sig_end].decode(
            "utf-8"
        )
        return signature.strip()

    def _get_function_body_node(self, target: str):
        """Resolve target to the body block node (block/statement_block/compound_statement/body_statement/constructor_body)."""
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = node
        if node.type == "decorated_definition":
            for child in node.named_children:
                if child.type == "function_definition":
                    func_node = child
                    break

        body = func_node.child_by_field_name("body")
        if body is None:
            for child in func_node.children:
                if child.type in ("block", "statement_block", "compound_statement", "body_statement", "constructor_body"):
                    body = child
                    break
        if body is None:
            raise ApplierError(f"Could not find body block for target '{target}'")
        return func_node, body

    def replace_in_body(self, target: str, old_snippet: str, new_snippet: str) -> str:
        """
        Replace a byte-identical snippet inside a function body with new_snippet.
        The match is scoped to the target's body so accidental matches elsewhere
        in the file are impossible.

        Raises if the snippet is not found, or if it appears more than once
        (include more surrounding context to disambiguate).
        """
        func_node, body = self._get_function_body_node(target)
        return self._replace_in_body_bytes(body, old_snippet, new_snippet, target)

    def delete_in_body(self, target: str, snippet: str) -> str:
        """
        Delete a byte-identical snippet inside a function body. Scoped to the
        target's body. Raises if not found or if the snippet appears more than
        once -- include more context to disambiguate.
        """
        func_node, body = self._get_function_body_node(target)
        return self._replace_in_body_bytes(body, snippet, "", target)

    def insert_in_body(
        self,
        target: str,
        new_snippet: str,
        at: str | None = None,
        after: str | None = None,
        before: str | None = None,
    ) -> str:
        """
        Insert new_snippet inside a function/method body. Pass exactly ONE of:
          - at="top":    insert at the top of the body (was: prepend_to_body).
          - at="bottom": insert at the bottom of the body (was: append_to_body).
          - after=<snippet>:  insert immediately after a byte-identical anchor.
          - before=<snippet>: insert immediately before a byte-identical anchor.

        The anchor match (for `after`/`before`) is scoped to the target's body
        and must be unique; multiple matches raise. Caller is responsible for
        any leading/trailing newlines and indentation in new_snippet.
        """
        at_val = at or None
        after_val = after or None
        before_val = before or None
        provided = [x for x in (at_val, after_val, before_val) if x is not None]
        if len(provided) != 1:
            raise ApplierError(
                "insert_in_body: pass exactly one of `at`, `after`, or `before`"
            )

        if at_val is not None:
            if at_val == "top":
                return self._prepend_to_body(target, new_snippet)
            if at_val == "bottom":
                return self._append_to_body(target, new_snippet)
            raise ApplierError(
                f"insert_in_body: `at` must be 'top' or 'bottom', got '{at_val}'"
            )

        func_node, body = self._get_function_body_node(target)
        anchor = after_val if after_val is not None else before_val
        place = "after" if after_val is not None else "before"
        return self._insert_in_body_bytes(body, anchor, new_snippet, place, target)

    def _replace_in_body_bytes(self, body_node, old_snippet, new_snippet, target):
        """Byte-level replace within a body. Empty new_snippet = delete."""
        body_start, body_end = self._body_search_range(body_node)
        source_bytes = self.parser.source_bytes
        body_bytes = source_bytes[body_start:body_end]
        # Source text is LF internally, so a snippet copied with CRLF still matches.
        old_bytes = old_snippet.replace("\r\n", "\n").encode("utf-8")
        if not old_bytes:
            raise ApplierError("Empty snippet cannot be matched")

        count = body_bytes.count(old_bytes)
        if count == 0:
            raise ApplierError(
                f"Snippet not found in body of '{target}'. Check whitespace and indentation."
            )
        if count > 1:
            raise ApplierError(
                f"Snippet matches {count} places in body of '{target}'. Include more "
                "surrounding context to make the match unique."
            )

        idx = body_bytes.index(old_bytes)
        abs_start = body_start + idx
        abs_end = abs_start + len(old_bytes)

        new_bytes_data = new_snippet.encode("utf-8")
        new_bytes = source_bytes[:abs_start] + new_bytes_data + source_bytes[abs_end:]
        self._write_bytes(new_bytes)
        return "Update successful"

    def _insert_in_body_bytes(self, body_node, anchor_snippet, new_snippet, place, target):
        """Byte-level insert anchored to a snippet within a body."""
        body_start, body_end = self._body_search_range(body_node)
        source_bytes = self.parser.source_bytes
        body_bytes = source_bytes[body_start:body_end]
        # Source text is LF internally, so an anchor copied with CRLF still matches.
        anchor_bytes = anchor_snippet.replace("\r\n", "\n").encode("utf-8")
        if not anchor_bytes:
            raise ApplierError("Empty anchor cannot be matched")

        count = body_bytes.count(anchor_bytes)
        if count == 0:
            raise ApplierError(
                f"Anchor snippet not found in body of '{target}'. Check whitespace and indentation."
            )
        if count > 1:
            raise ApplierError(
                f"Anchor matches {count} places in body of '{target}'. Include more "
                "surrounding context to make the match unique."
            )

        idx = body_bytes.index(anchor_bytes)
        abs_start = body_start + idx
        abs_end = abs_start + len(anchor_bytes)
        insert_point = abs_end if place == "after" else abs_start

        new_bytes_data = new_snippet.encode("utf-8")
        new_bytes = source_bytes[:insert_point] + new_bytes_data + source_bytes[insert_point:]
        self._write_bytes(new_bytes)
        return "Update successful"

    def _body_search_range(self, body_node) -> tuple[int, int]:
        """Return (start_byte, end_byte) byte range within which to search for
        a snippet inside a function body. For Python/Ruby, extends the start
        back to the beginning of the first body line so leading indentation is
        part of the searchable text. For brace-delimited languages, returns
        the body node's native byte range (which includes `{` and `}`)."""
        start_byte = body_node.start_byte
        end_byte = body_node.end_byte
        if self.parser.ext in (".py", ".rb"):
            source_bytes = self.parser.source_bytes
            while start_byte > 0 and source_bytes[start_byte - 1:start_byte] != b"\n":
                start_byte -= 1
        return start_byte, end_byte

    def _body_insert_point(self, target: str, at: str) -> tuple[int, str]:
        """
        Line index and indentation for inserting at the top or bottom of a
        function body. The indentation comes from the body's own statements, not
        from whichever line happens to be first or last, so a body that ends in a
        nested block still gets the new lines at body level. In Python the new
        lines go after a leading docstring so it stays the docstring; in Ruby a
        bottom insert goes before any rescue/else/ensure clause. A body that
        shares a line with its signature or braces has no line to insert on and
        is refused.
        """
        func_node, body = self._get_function_body_node(target)
        ext = self.parser.ext
        stmts = list(body.named_children)
        if len(stmts) == 1 and stmts[0].type == "statement_list":
            # Go wraps a block's statements in a statement_list that ends on the `}` line
            stmts = list(stmts[0].named_children)
        sig_line = func_node.start_point[0]
        braced = ext not in (".py", ".rb")
        clause = None
        if ext == ".rb":
            clauses = [c for c in stmts if c.type in ("rescue", "else", "ensure")]
            clause = clauses[0] if clauses else None
            stmts = [c for c in stmts if c.type not in ("rescue", "else", "ensure")]
        if braced:
            compact = body.start_point[0] == body.end_point[0] or bool(
                stmts
                and (
                    stmts[0].start_point[0] == body.start_point[0]
                    or stmts[-1].end_point[0] == body.end_point[0]
                )
            )
        else:
            compact = bool(stmts) and stmts[0].start_point[0] == sig_line
        if compact:
            raise ApplierError(
                f"The body of '{target}' shares a line with its signature or braces, so "
                f"at='{at}' has no line of its own to insert on. Use replace_function_body "
                f"to rewrite the body over several lines."
            )
        if stmts:
            anchor = stmts[0] if at == "top" else stmts[-1]
            indent = self._get_indent(self.lines[anchor.start_point[0]])
        else:
            unit = self._indent_unit({".py": "    ", ".go": "\t"}.get(ext, "  "))
            indent = self._get_indent(self.lines[sig_line]) + unit
        if at == "top":
            if braced:
                return body.start_point[0] + 1, indent
            if ext == ".py" and stmts and self._is_docstring_node(stmts[0]):
                return stmts[0].end_point[0] + 1, indent
            return (stmts[0].start_point[0] if stmts else body.start_point[0]), indent
        if braced:
            return body.end_point[0], indent
        if clause is not None:
            return clause.start_point[0], indent
        return (stmts[-1].end_point[0] + 1 if stmts else body.end_point[0] + 1), indent

    @staticmethod
    def _is_docstring_node(node) -> bool:
        """True for a Python statement that is just a string literal (a docstring)."""
        if node.type != "expression_statement" or node.named_child_count != 1:
            return False
        return node.named_children[0].type in ("string", "concatenated_string")

    def _prepend_to_body(self, target: str, content: str) -> str:
        """
        Insert content at the top of a function body, preserving existing statements.
        """
        insert_line, target_indent = self._body_insert_point(target, "top")
        content_lines = self._reindent(_content_lines(content), target_indent)
        self.lines = self.lines[:insert_line] + content_lines + self.lines[insert_line:]
        return self._save()

    def _append_to_body(self, target: str, content: str) -> str:
        """
        Insert content at the bottom of a function body, preserving existing statements.
        """
        insert_line, target_indent = self._body_insert_point(target, "bottom")
        content_lines = self._reindent(_content_lines(content), target_indent)
        self.lines = self.lines[:insert_line] + content_lines + self.lines[insert_line:]
        return self._save()

    def _insert_before(self, target: str, content: str) -> str:
        """
        Insert content as a sibling immediately before a named symbol (function, class,
        method, or top-level assignment).
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        # Above the symbol's decorators and a JS/TS `export` (see _symbol_span).
        insert_line = self._symbol_span(node)[0].start_point[0]
        target_indent = (
            self._get_indent(self.lines[insert_line])
            if insert_line < len(self.lines)
            else ""
        )
        content_lines = self._reindent(_content_lines(content), target_indent)

        # Add a blank separator line after the inserted content if the target line is non-blank
        separator = (
            [""]
            if insert_line < len(self.lines) and self.lines[insert_line].strip()
            else []
        )

        self.lines = (
            self.lines[:insert_line]
            + content_lines
            + separator
            + self.lines[insert_line:]
        )
        return self._save()

    def _insert_after(self, target: str, content: str) -> str:
        """
        Insert content as a sibling immediately after a named symbol (function, class,
        method, or top-level assignment).
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        first, last = self._symbol_span(node)
        insert_line = last.end_point[0] + 1
        target_indent = self._get_indent(self.lines[first.start_point[0]])
        content_lines = self._reindent(_content_lines(content), target_indent)

        # Blank separator before the inserted content if the preceding line is non-blank
        separator = (
            [""]
            if insert_line - 1 >= 0
            and insert_line - 1 < len(self.lines)
            and self.lines[insert_line - 1].strip()
            else []
        )

        self.lines = (
            self.lines[:insert_line]
            + separator
            + content_lines
            + self.lines[insert_line:]
        )
        return self._save()

    def insert_sibling(self, target: str, content: str, position: str) -> str:
        """
        Insert `content` as a sibling of the named symbol. `position` must be
        'before' or 'after'. Dispatches to insert_before / insert_after.
        """
        if position == "before":
            return self._insert_before(target, content)
        if position == "after":
            return self._insert_after(target, content)
        raise ApplierError(
            f"insert_sibling: position must be 'before' or 'after', got '{position}'"
        )

    def _find_python_literal(self, target: str, expected_type: str):
        """Resolve target (module-level assignment name) to its right-hand dictionary/list literal."""
        if self.parser.ext != ".py":
            raise ApplierError(
                f"Python literal ops only support .py files, not {self.parser.ext}"
            )
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")
        # node should be an expression_statement containing an assignment
        assignment = None
        if node.type == "expression_statement":
            for c in node.named_children:
                if c.type == "assignment":
                    assignment = c
                    break
        if assignment is None:
            raise ApplierError(f"Target '{target}' is not a module-level assignment")
        value = assignment.child_by_field_name("right")
        if value is None and len(assignment.named_children) >= 2:
            value = assignment.named_children[1]
        if value is None:
            raise ApplierError(f"Could not find assigned value for '{target}'")
        if value.type != expected_type:
            raise ApplierError(
                f"Target '{target}' is a {value.type}, not a {expected_type}"
            )
        return value

    def _find_python_pair(self, dict_node, key: str):
        """The pair of a Python dict literal whose key is `key` (a key
        expression such as '"foo"'; literals compare by value, so 'foo' in
        either quote style matches), or None."""
        for pair in dict_node.named_children:
            if pair.type != "pair":
                continue
            key_node = pair.child_by_field_name("key")
            if key_node is None and pair.named_children:
                key_node = pair.named_children[0]
            if key_node is not None and _python_keys_equal(self.parser.node_text(key_node), key):
                return pair
        return None

    def _find_python_dict(self, target: str):
        """
        Resolve a Python dict target to its dictionary node: the name of a
        module-level (or class-level, 'Settings.DEFAULTS') assignment,
        optionally followed by keys into nested dict literals
        ('CONFIG."db"').
        """
        parts = _split_key_path(target)
        if not all(parts):
            raise ApplierError(f"Invalid dict target '{target}'")
        # The longest prefix that names an assignment is the variable; the
        # rest are keys.
        n = len(parts)
        while n > 1:
            node = self.parser.find_node_by_name(".".join(parts[:n]))
            if node is not None and node.type == "expression_statement":
                break
            n -= 1
        dict_node = self._find_python_literal(".".join(parts[:n]), "dictionary")
        for i in range(n, len(parts)):
            pair = self._find_python_pair(dict_node, parts[i])
            if pair is None:
                raise ApplierError(f"Key {parts[i]} not found in dict '{'.'.join(parts[:i])}'")
            value = pair.child_by_field_name("value")
            if value is None or value.type != "dictionary":
                raise ApplierError(f"'{'.'.join(parts[: i + 1])}' is not a dict literal")
            dict_node = value
        return dict_node

    def add_dict_entry(self, target: str, key: str, value: str) -> str:
        """
        Add a new key-value pair to a Python dictionary literal at a module-level
        assignment (target may continue into nested dicts, see _find_python_dict).
        key and value should be literal source expressions (e.g. key='"foo"',
        value='42'). Raises ApplierError if the dict already has the key.
        """
        dict_node = self._find_python_dict(target)
        key = key.strip()
        if self._find_python_pair(dict_node, key) is not None:
            raise self._duplicate_key(key, target, f"{target}.{key}")
        entries = [
            c for c in dict_node.named_children if c.type in ("pair", "dictionary_splat")
        ]
        self._insert_entry(
            dict_node,
            entries,
            f"{key}: {value}",
            expand_empty=True,
            empty_trailing_comma=True,
            default_unit="    ",
        )
        return "Update successful"

    def delete_dict_entry(self, target: str, key: str) -> str:
        """
        Delete a key-value pair from a Python dictionary literal (target may
        continue into nested dicts, see _find_python_dict). key should be the
        literal source expression of the key (e.g. '"foo"'); literal keys also
        match when written with the other quote style.
        """
        dict_node = self._find_python_dict(target)
        pair = self._find_python_pair(dict_node, key)
        if pair is None:
            raise ApplierError(f"Key {key} not found in dict '{target}'")
        entries = [
            c for c in dict_node.named_children if c.type in ("pair", "dictionary_splat")
        ]
        self._delete_entry(dict_node, entries, entries.index(pair))
        return "Update successful"

    def append_to_list(self, target: str, value: str) -> str:
        """
        Append a value to a Python list literal at a module-level assignment.
        value should be a literal source expression (e.g. value='"foo"' or '42').
        """
        list_node = self._find_python_literal(target, "list")
        elements = list(list_node.named_children)

        source_bytes = self.parser.source_bytes
        if elements:
            last = elements[-1]
            # Determine if multi-line or inline
            if list_node.start_point[0] == list_node.end_point[0]:
                insertion = f", {value}"
                insert_byte = last.end_byte
            else:
                indent = self._get_indent(self.lines[last.start_point[0]])
                insertion = f",\n{indent}{value}"
                insert_byte = last.end_byte
        else:
            insertion = f"{value}"
            insert_byte = list_node.start_byte + 1

        new_bytes = (
            source_bytes[:insert_byte]
            + insertion.encode("utf-8")
            + source_bytes[insert_byte:]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

    def remove_from_list(self, target: str, value_match: str) -> str:
        """
        Remove the first element matching value_match (stripped text equality) from
        a Python list literal.
        """
        list_node = self._find_python_literal(target, "list")
        elements = list(list_node.named_children)

        stripped = value_match.strip()
        idx = None
        for i, el in enumerate(elements):
            if self.parser.node_text(el).strip() == stripped:
                idx = i
                break
        if idx is None:
            raise ApplierError(f"Value {value_match} not found in list '{target}'")

        source_bytes = self.parser.source_bytes
        start = elements[idx].start_byte
        end = elements[idx].end_byte
        if idx > 0:
            start = elements[idx - 1].end_byte
        elif idx + 1 < len(elements):
            end = elements[idx + 1].start_byte

        new_bytes = source_bytes[:start] + source_bytes[end:]
        self._write_bytes(new_bytes)
        return "Update successful"

    def _find_python_from_import(self, module: str):
        """Find a Python `from <module> import ...` statement."""
        for child in self.parser.tree.root_node.named_children:
            if child.type == "import_from_statement":
                mod_node = child.child_by_field_name("module_name")
                if mod_node and self.parser.node_text(mod_node) == module:
                    return child
        return None

    def add_import_name(self, module: str, name: str) -> str:
        """
        Add a name to an existing named-import statement:
          - Python:  `from <module> import a, b`  -> adds as a new name
          - JS/TS:   `import { a, b } from "module"`  -> adds as a new specifier
        Idempotent: if the name is already present, returns without changes.
        Raises if no matching import statement exists.
        """
        ext = self.parser.ext
        if ext == ".py":
            return self._add_import_name_python(module, name)
        if ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
            return self._add_import_name_js(module, name)
        raise ApplierError(
            f"add_import_name is supported for Python and JS/TS, not {ext}"
        )

    def _add_import_name_python(self, module: str, name: str) -> str:
        stmt = self._find_python_from_import(module)
        if stmt is None:
            raise ApplierError(
                f"'from {module} import ...' not found in {self.filepath}"
            )

        name_nodes = stmt.children_by_field_name("name")
        existing = [self.parser.node_text(n) for n in name_nodes]
        if name in existing:
            return "Name already present -- no change made"
        if not name_nodes:
            raise ApplierError("Cannot add to an empty import list")

        last = name_nodes[-1]
        insertion = f", {name}"
        source_bytes = self.parser.source_bytes
        new_bytes = (
            source_bytes[: last.end_byte]
            + insertion.encode("utf-8")
            + source_bytes[last.end_byte :]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

    def _add_import_name_js(self, module: str, name: str) -> str:
        stmt, named_imports, specs = self._find_js_named_import(module)
        if stmt is None:
            raise ApplierError(
                f"Named import from '{module}' not found in {self.filepath}"
            )
        if not specs:
            raise ApplierError(
                "Cannot add to an empty named import list -- use add_import instead"
            )

        # Dedupe against existing specifier names (not aliases)
        for spec in specs:
            name_node = spec.child_by_field_name("name")
            if name_node and self.parser.node_text(name_node) == name:
                return "Name already present -- no change made"

        last = specs[-1]
        insertion = f", {name}"
        source_bytes = self.parser.source_bytes
        new_bytes = (
            source_bytes[: last.end_byte]
            + insertion.encode("utf-8")
            + source_bytes[last.end_byte :]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

    def _find_js_named_import(self, module: str):
        """For JS/TS: find `import { ... } from "module"` matching the module.
        Returns (import_statement_node, named_imports_node, list of import_specifier nodes)
        or (None, None, []) if no match."""
        for child in self.parser.tree.root_node.named_children:
            if child.type != "import_statement":
                continue
            # Find source string (direct child of import_statement)
            source_text = None
            for c in child.named_children:
                if c.type == "string":
                    text = self.parser.node_text(c).strip()
                    # Strip surrounding quotes (single/double/backtick)
                    if len(text) >= 2 and text[0] in "\"'`" and text[-1] in "\"'`":
                        text = text[1:-1]
                    source_text = text
                    break
            if source_text != module:
                continue
            # Find named_imports node (typically inside import_clause)
            named_imports = self._find_js_named_imports_clause(child)
            if named_imports is None:
                continue
            specs = [c for c in named_imports.named_children if c.type == "import_specifier"]
            return child, named_imports, specs
        return None, None, []

    def _find_js_named_imports_clause(self, import_stmt):
        """Locate the named_imports node anywhere inside an import_statement."""
        queue = list(import_stmt.named_children)
        while queue:
            curr = queue.pop(0)
            if curr.type == "named_imports":
                return curr
            queue.extend(curr.named_children)
        return None

    def remove_import_name(self, module: str, name: str) -> str:
        """
        Remove a name from a named-import statement:
          - Python:  `from <module> import a, b, c`
          - JS/TS:   `import { a, b, c } from "module"`
        If removing the only remaining name, removes the entire import statement
        (when the statement consists of only named imports).
        """
        ext = self.parser.ext
        if ext == ".py":
            return self._remove_import_name_python(module, name)
        if ext in (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
            return self._remove_import_name_js(module, name)
        raise ApplierError(
            f"remove_import_name is supported for Python and JS/TS, not {ext}"
        )

    def _remove_import_name_python(self, module: str, name: str) -> str:
        stmt = self._find_python_from_import(module)
        if stmt is None:
            raise ApplierError(
                f"'from {module} import ...' not found in {self.filepath}"
            )

        name_nodes = stmt.children_by_field_name("name")
        idx = None
        for i, n in enumerate(name_nodes):
            if self.parser.node_text(n) == name:
                idx = i
                break
        if idx is None:
            raise ApplierError(f"Name '{name}' not found in 'from {module} import ...'")

        if len(name_nodes) == 1:
            start_line = stmt.start_point[0]
            end_line = stmt.end_point[0] + 1
            self.lines = self.lines[:start_line] + self.lines[end_line:]
            return self._save()

        source_bytes = self.parser.source_bytes
        start = name_nodes[idx].start_byte
        end = name_nodes[idx].end_byte
        if idx > 0:
            start = name_nodes[idx - 1].end_byte
        elif idx + 1 < len(name_nodes):
            end = name_nodes[idx + 1].start_byte

        new_bytes = source_bytes[:start] + source_bytes[end:]
        self._write_bytes(new_bytes)
        return "Update successful"

    def _remove_import_name_js(self, module: str, name: str) -> str:
        stmt, named_imports, specs = self._find_js_named_import(module)
        if stmt is None:
            raise ApplierError(
                f"Named import from '{module}' not found in {self.filepath}"
            )

        idx = None
        for i, spec in enumerate(specs):
            name_node = spec.child_by_field_name("name")
            if name_node and self.parser.node_text(name_node) == name:
                idx = i
                break
        if idx is None:
            raise ApplierError(
                f"Name '{name}' not found in named import from '{module}'"
            )

        # If removing the only named import, and there are no other bindings
        # (default / namespace imports) on the same statement, remove the whole
        # statement. Otherwise removing the last named import would leave a
        # mixed `import Default, {} from "mod"` fragment that's invalid.
        if len(specs) == 1:
            import_clause = named_imports.parent
            siblings = [c for c in import_clause.named_children if c.type != "named_imports"] if import_clause else []
            if not siblings:
                start_line = stmt.start_point[0]
                end_line = stmt.end_point[0] + 1
                self.lines = self.lines[:start_line] + self.lines[end_line:]
                return self._save()
            raise ApplierError(
                f"Removing the last name from `import Default, {{ {name} }} from \"{module}\"` "
                "would leave an invalid empty braces fragment. Use `remove_import` to remove the whole "
                "statement, then re-add the default binding with `add_import`."
            )

        # Multiple specs: remove this one + adjacent comma
        source_bytes = self.parser.source_bytes
        start = specs[idx].start_byte
        end = specs[idx].end_byte
        if idx > 0:
            start = specs[idx - 1].end_byte
        elif idx + 1 < len(specs):
            end = specs[idx + 1].start_byte

        new_bytes = source_bytes[:start] + source_bytes[end:]
        self._write_bytes(new_bytes)
        return "Update successful"

    def _find_parameter_list(self, target: str):
        """Locate the parameter list node for a function/method across languages."""
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = node
        if node.type == "decorated_definition":
            for c in node.named_children:
                if c.type == "function_definition":
                    func_node = c
                    break

        params = func_node.child_by_field_name("parameters")
        if params is not None:
            return params

        # C/C++: parameters live inside the declarator chain
        declarator = func_node.child_by_field_name("declarator")
        while declarator:
            if declarator.type == "function_declarator":
                p = declarator.child_by_field_name("parameters")
                if p is not None:
                    return p
                break
            declarator = declarator.child_by_field_name("declarator")

        raise ApplierError(f"Could not find parameter list for '{target}'")

    def _parameter_name(self, param_node) -> str:
        """Extract the identifier name from a parameter node across languages."""
        # Python: identifier, typed_parameter, default_parameter, typed_default_parameter
        # JS/TS: identifier, required_parameter, optional_parameter
        # C/C++: parameter_declaration
        if param_node.type == "identifier":
            return self.parser.node_text(param_node)
        # Try field name first
        name_field = param_node.child_by_field_name("name")
        if name_field is not None:
            if name_field.type == "identifier":
                return self.parser.node_text(name_field)
            # Could be typed_parameter wrapper; recurse
            return self._parameter_name(name_field)
        # Fallback: search for first identifier in descendants
        queue = list(param_node.named_children)
        while queue:
            c = queue.pop(0)
            if c.type == "identifier":
                return self.parser.node_text(c)
            queue.extend(c.named_children)
        return ""

    def add_parameter(self, target: str, parameter: str, position: str = "end") -> str:
        """
        Add a parameter to a function signature. position must be 'end' (default)
        or 'start'; anything else raises ApplierError. parameter should be the
        literal source text of the new parameter (e.g. 'default=None' or
        'const int* buf').
        """
        if position not in ("start", "end"):
            raise ApplierError(
                f"add_parameter: position must be 'start' or 'end', got '{position}'"
            )
        params = self._find_parameter_list(target)
        existing = [c for c in params.named_children]

        source_bytes = self.parser.source_bytes

        if not existing:
            # Empty parameter list: insert between ( and )
            insert_byte = params.start_byte + 1
            insertion = parameter
        elif position == "start":
            first = existing[0]
            insert_byte = first.start_byte
            insertion = f"{parameter}, "
        else:  # end
            last = existing[-1]
            insert_byte = last.end_byte
            insertion = f", {parameter}"

        new_bytes = (
            source_bytes[:insert_byte]
            + insertion.encode("utf-8")
            + source_bytes[insert_byte:]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

    def remove_parameter(self, target: str, parameter_name: str) -> str:
        """
        Remove a parameter by name from a function signature.
        """
        params = self._find_parameter_list(target)
        existing = [c for c in params.named_children]

        idx = None
        for i, p in enumerate(existing):
            if self._parameter_name(p) == parameter_name:
                idx = i
                break
        if idx is None:
            raise ApplierError(f"Parameter '{parameter_name}' not found in '{target}'")

        source_bytes = self.parser.source_bytes
        start = existing[idx].start_byte
        end = existing[idx].end_byte
        if idx > 0:
            start = existing[idx - 1].end_byte
        elif idx + 1 < len(existing):
            end = existing[idx + 1].start_byte

        new_bytes = source_bytes[:start] + source_bytes[end:]
        self._write_bytes(new_bytes)
        return "Update successful"

    def _comment_prefixes(self) -> tuple[str, ...]:
        if self.parser.ext == ".py":
            return ("#",)
        if self.parser.ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            return ("//",)
        if self.parser.ext in (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"):
            return ("//",)
        if self.parser.ext == ".go":
            return ("//",)
        if self.parser.ext == ".java":
            return ("//",)
        if self.parser.ext == ".rb":
            return ("#",)
        if self.parser.ext in (".yml", ".yaml", ".toml"):
            return ("#",)
        return ()

    def _is_comment_line(self, line: str) -> bool:
        stripped = line.lstrip()
        return any(stripped.startswith(p) for p in self._comment_prefixes())

    def _add_comment_before(self, target: str, comment: str) -> str:
        """
        Insert comment line(s) immediately before a named symbol. The comment must
        include its own comment marker (e.g. '# foo' for Python/YAML/TOML, '// foo'
        for JS/C/C++). Existing content is shifted down. Raises ApplierError if
        the symbol already has a leading comment, which the new lines would
        merge into.
        """
        if not self._comment_prefixes():
            raise ApplierError(
                f"edit_leading_comment is not supported for {self.parser.ext} files"
            )

        node = self._find_symbol_for_comment(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        insert_line = node.start_point[0]
        existing = self._find_leading_comment_range(insert_line)
        if existing is not None:
            first, stop = existing
            where = f"line {first + 1}" if stop - first == 1 else f"lines {first + 1}-{stop}"
            # Show the lines: they may be tool directives
            # (// eslint-disable-next-line, //go:noinline) that a replace
            # must carry over.
            text = "\n".join(line.strip() for line in self.lines[first:stop])
            raise ApplierError(
                f"'{target}' already has a leading comment ({where}):\n{text}\n"
                "Use op='replace' with a comment block that includes any of these "
                "lines you want to keep (e.g. lint or compiler directives), or "
                "op='remove' first"
            )
        target_indent = self._get_indent(self.lines[insert_line]) if insert_line < len(self.lines) else ""
        comment_lines = self._reindent(_content_lines(comment), target_indent)
        self.lines = self.lines[:insert_line] + comment_lines + self.lines[insert_line:]
        return self._save()

    def _remove_leading_comment(self, target: str) -> str:
        """
        Remove the contiguous block of comment lines immediately above a named symbol.
        Handles both line comments and C-style /* ... */ block comments. Stops at
        the first blank line or non-comment code line.
        """
        if not self._comment_prefixes():
            raise ApplierError(
                f"edit_leading_comment is not supported for {self.parser.ext} files"
            )

        node = self._find_symbol_for_comment(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        start_line = node.start_point[0]
        comment_range = self._find_leading_comment_range(start_line)
        if comment_range is None:
            raise ApplierError(f"No leading comment found above '{target}'")

        first, stop = comment_range
        self.lines = self.lines[:first] + self.lines[stop:]
        return self._save()

    def _replace_leading_comment(self, target: str, new_comment: str) -> str:
        """
        Replace the contiguous leading comment block above a named symbol with
        new_comment. Handles line comments and C-style /* ... */ block comments.
        If no leading comment exists, inserts new_comment.
        """
        if not self._comment_prefixes():
            raise ApplierError(
                f"edit_leading_comment is not supported for {self.parser.ext} files"
            )

        node = self._find_symbol_for_comment(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        start_line = node.start_point[0]
        target_indent = self._get_indent(self.lines[start_line]) if start_line < len(self.lines) else ""
        comment_lines = self._reindent(_content_lines(new_comment), target_indent)

        comment_range = self._find_leading_comment_range(start_line)
        if comment_range is None:
            self.lines = self.lines[:start_line] + comment_lines + self.lines[start_line:]
        else:
            first, stop = comment_range
            self.lines = self.lines[:first] + comment_lines + self.lines[stop:]
        return self._save()

    def edit_leading_comment(
        self,
        target: str,
        op: str,
        comment: str = "",
    ) -> str:
        """
        Unified entry point for editing the contiguous leading-comment block
        above a named symbol. Dispatches by op:
          - "add"     -> _add_comment_before(target, comment); refused if the
                         symbol already has a leading comment
          - "replace" -> _replace_leading_comment(target, comment)
          - "remove"  -> _remove_leading_comment(target)
        For "add" and "replace", `comment` must be a non-empty string including
        the language's comment marker (e.g. "# foo", "// bar", "/** ... */").
        For "remove", `comment` is ignored.
        """
        if op == "add":
            if not comment:
                raise ApplierError(
                    "edit_leading_comment: `comment` is required when op='add'"
                )
            return self._add_comment_before(target, comment)
        if op == "replace":
            if not comment:
                raise ApplierError(
                    "edit_leading_comment: `comment` is required when op='replace'"
                )
            return self._replace_leading_comment(target, comment)
        if op == "remove":
            return self._remove_leading_comment(target)
        raise ApplierError(
            f"edit_leading_comment: unknown op '{op}'. Use 'add', 'replace', or 'remove'."
        )

    def replace_docstring(self, target: str, new_docstring: str) -> str:
        """
        Replace or insert a Python docstring on a function or class. The new_docstring
        should be a valid Python string literal including its surrounding triple
        quotes. Python-specific.
        """
        if self.parser.ext != ".py":
            raise ApplierError(
                f"replace_docstring only supports .py files (got {self.parser.ext})"
            )

        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = node
        if node.type == "decorated_definition":
            for c in node.named_children:
                if c.type == "function_definition":
                    func_node = c
                    break

        body = func_node.child_by_field_name("body")
        if body is None:
            raise ApplierError(f"Could not find body for '{target}'")

        # Check if first statement is an existing docstring (string expression)
        first_stmt = body.named_children[0] if body.named_children else None
        source_bytes = self.parser.source_bytes

        if (
            first_stmt
            and first_stmt.type == "expression_statement"
            and first_stmt.named_children
            and first_stmt.named_children[0].type == "string"
        ):
            string_node = first_stmt.named_children[0]
            new_bytes = (
                source_bytes[: string_node.start_byte]
                + new_docstring.encode("utf-8")
                + source_bytes[string_node.end_byte :]
            )
            self._write_bytes(new_bytes)
            return "Update successful (docstring replaced)"

        # No existing docstring -- insert at the start of the body
        insert_byte = body.start_byte
        indent = (
            self._get_indent(self.lines[body.start_point[0]])
            if body.start_point[0] < len(self.lines)
            else "    "
        )
        insertion = f"{new_docstring}\n{indent}"
        new_bytes = (
            source_bytes[:insert_byte]
            + insertion.encode("utf-8")
            + source_bytes[insert_byte:]
        )
        self._write_bytes(new_bytes)
        return "Update successful (docstring inserted)"

    def find_references(self, target: str) -> str:
        """
        Return all occurrences of an identifier named `target` in the file, as a
        formatted multi-line string: 'line N: <source line>'. Read-only, syntactic
        only (no scope awareness).
        """
        identifier_types = {
            "identifier",
            "field_identifier",
            "type_identifier",
            "property_identifier",
        }
        results = []
        queue = [self.parser.tree.root_node]
        while queue:
            curr = queue.pop(0)
            if curr.type in identifier_types and self.parser.node_text(curr) == target:
                line_num = curr.start_point[0]
                context = self.lines[line_num] if line_num < len(self.lines) else ""
                results.append((line_num + 1, context.strip()))
            queue.extend(curr.named_children)

        if not results:
            return f"(no references to '{target}' found in {self.filepath})"
        return "\n".join(f"line {ln}: {ctx}" for ln, ctx in results)

    # ──────────────────────────────────────────────
    # AST Reader tools (read-only, token-efficient)
    # ──────────────────────────────────────────────

    def read_symbol(self, target: str, depth: str = "full") -> str:
        """
        Return source text for a named symbol. `depth` controls how much is
        returned:
          - "full" (default): entire source of the symbol (function body,
            class body, etc.). Equivalent to the old `read_symbol`.
          - "interface": for a class -> header + field declarations + method
            signatures with bodies replaced by ' ...'. For a function ->
            just the signature. Equivalent to the old `read_interface`.
          - "signature": signature-only. For a function -> the line(s)
            before the body. For a class -> the class header. Equivalent to
            the old `get_signature`.

        For config files (JSON/YAML/TOML), "full" returns the value node's
        source and the other depths raise.
        """
        if depth == "full":
            node = self.parser.find_node_by_name(target)
            if not node:
                raise ApplierError(f"Target '{target}' not found in {self.filepath}")
            first, last = self._symbol_span(node)
            return self.parser.source_bytes[first.start_byte : last.end_byte].decode("utf-8")
        if depth == "interface":
            return self._read_interface(target)
        if depth == "signature":
            return self._get_signature(target)
        raise ApplierError(
            f"read_symbol: unknown depth '{depth}'. Use 'full', 'interface', or 'signature'."
        )

    def read_imports(self) -> str:
        """
        Return all import statements in the file as a multi-line string. Read-only.
        """
        valid_types = self._import_node_types()
        if not valid_types:
            raise ApplierError(f"read_imports is not supported for {self.parser.ext}")

        import_lines = []
        for child in self.parser.tree.root_node.named_children:
            if child.type not in valid_types:
                continue
            if self.parser.ext in (".rb",) and child.type == "call":
                if not self._is_ruby_require_call(child):
                    continue
            import_lines.append(self.parser.node_text(child))

        if not import_lines:
            return "(no imports found)"
        return "\n".join(import_lines)

    def _read_interface(self, target: str) -> str:
        """
        Return a stub view of a class: its header, field declarations, and method
        signatures (with bodies replaced by ' ...'). For a function target, returns
        just its signature. Read-only.
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        ext = self.parser.ext
        if ext in (".json", ".yml", ".yaml", ".toml"):
            raise ApplierError(f"read_symbol(depth='interface') is not supported for {ext}")

        func_types = self._interface_func_types()

        inner = node
        if node.type == "decorated_definition":
            for c in node.named_children:
                if c.type in ("function_definition", "class_definition"):
                    inner = c
                    break

        # Function target -- return signature only
        if inner.type in func_types:
            return self._get_signature(target)

        # Go: struct/interface definition + top-level receiver methods
        # (checked before body lookup because type_spec has no 'body' field)
        if ext in (".go",) and inner.type == "type_spec":
            return self._read_interface_go(node, inner)

        body = inner.child_by_field_name("body")
        if body is None:
            return self.parser.node_text(node)

        source = self.parser.source_bytes

        # Header: everything from the symbol's start (decorators and a JS/TS
        # `export` included) up to body content
        head = self._symbol_span(node)[0].start_byte
        if ext in (".py", ".rb"):
            header = source[head:body.start_byte].decode("utf-8").rstrip()
        else:
            # Brace-delimited: body node starts with {, include it in header
            header = source[head:body.start_byte + 1].decode("utf-8").rstrip()

        parts = [header]

        # Walk body members: signatures for methods, full text for fields
        self._collect_interface_members(body, func_types, parts)

        # Closing token
        if ext in (".rb",):
            tail = source[body.end_byte:node.end_byte].decode("utf-8").strip()
            if tail:
                indent = self._get_indent(self.lines[inner.start_point[0]])
                parts.append(indent + tail)
        elif ext not in (".py",):
            # Brace-delimited: closing } (or }; for C++)
            indent = self._get_indent(self.lines[inner.start_point[0]])
            closing = source[body.end_byte - 1:node.end_byte].decode("utf-8").rstrip()
            parts.append(indent + closing)

        return "\n".join(parts)

    def _interface_func_types(self) -> set:
        """Return the set of AST node types that represent functions/methods for this language."""
        ext = self.parser.ext
        if ext == ".py":
            return {"function_definition", "decorated_definition"}
        if ext in (".ts", ".tsx"):
            return {"function_declaration", "method_definition"}
        if ext in (".js", ".jsx", ".mjs", ".cjs"):
            return {"function_declaration", "method_definition"}
        if ext in (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"):
            return {"function_definition"}
        if ext in (".rb",):
            return {"method", "singleton_method"}
        if ext in (".go",):
            return {"function_declaration", "method_declaration"}
        if ext == ".java":
            return {"method_declaration", "constructor_declaration"}
        return set()

    def _extract_method_sig(self, child, func_types) -> str | None:
        """Extract the signature of a method node with ' ...' appended, or None if not a method."""
        c_inner = child
        if child.type == "decorated_definition":
            for cc in child.named_children:
                if cc.type == "function_definition":
                    c_inner = cc
                    break

        if c_inner.type not in func_types:
            return None

        c_body = c_inner.child_by_field_name("body")
        if c_body is None:
            for cc in c_inner.children:
                if cc.type in ("block", "statement_block", "compound_statement",
                              "body_statement", "constructor_body"):
                    c_body = cc
                    break

        if c_body is None:
            # Abstract/interface method with no body -- include full text
            return self.parser.node_text(child)

        sig_end = c_inner.start_byte
        for fc in c_inner.children:
            if fc == c_body:
                break
            sig_end = fc.end_byte

        sig = self.parser.source_bytes[child.start_byte:sig_end].decode("utf-8").rstrip()
        return sig + " ..."

    def _collect_interface_members(self, container, func_types, parts):
        """Walk a class body, appending signatures for methods and full text for fields."""
        for child in container.named_children:
            sig = self._extract_method_sig(child, func_types)
            if sig is not None:
                parts.append(sig)
            elif child.type in ("enum_body_declarations", "class_body", "interface_body"):
                self._collect_interface_members(child, func_types, parts)
            else:
                parts.append(self.parser.node_text(child))

    def _read_interface_go(self, node, inner) -> str:
        """Go-specific: struct/interface definition + all receiver method signatures."""
        # Use parent type_declaration for full text including 'type' keyword
        decl = node.parent if node.parent and node.parent.type == "type_declaration" else node
        parts = [self.parser.node_text(decl)]
        name_node = inner.child_by_field_name("name")
        if name_node is None:
            return parts[0]
        type_name = self.parser.node_text(name_node)

        for child in self.parser.tree.root_node.named_children:
            if child.type != "method_declaration":
                continue
            recv = child.child_by_field_name("receiver")
            if recv is None:
                continue
            recv_type = self.parser._extract_go_receiver_type(recv)
            if recv_type != type_name:
                continue
            m_body = child.child_by_field_name("body")
            if m_body:
                sig_end = child.start_byte
                for fc in child.children:
                    if fc == m_body:
                        break
                    sig_end = fc.end_byte
                sig = self.parser.source_bytes[child.start_byte:sig_end].decode("utf-8").rstrip()
                parts.append(sig + " ...")
            else:
                parts.append(self.parser.node_text(child))

        return "\n\n".join(parts)

    def add_top_level(self, content: str, position: str = "bottom") -> str:
        """
        Insert top-level content into the file. Position controls placement:
          - "bottom" (default): append to end of file.
          - "top": insert after the preamble (package/imports/includes/leading
                   comments and, for Python, the module docstring) and before
                   the first non-preamble declaration. For files with no
                   preamble, inserts at line 0.
        """
        if position not in ("bottom", "top"):
            raise ApplierError(f"position must be 'bottom' or 'top', got: {position}")

        content_lines = _content_lines(content)

        if position == "bottom":
            while self.lines and not self.lines[-1].strip():
                self.lines.pop()
            if self.lines:
                self.lines.append("")
            self.lines.extend(content_lines)
            return self._save()

        # position == "top": find preamble end and insert there
        insert_line = self._find_preamble_end()
        if insert_line == 0:
            # Prepend at file start; add a trailing blank so downstream code is separated
            self.lines = content_lines + [""] + self.lines
        else:
            # Insert after preamble with a blank separator before the new content
            self.lines = self.lines[:insert_line] + [""] + content_lines + self.lines[insert_line:]
        return self._save()

    def _find_preamble_end(self) -> int:
        """Return the line number at which non-preamble code starts.
        Preamble includes: package declarations (Go/Java), import/include
        statements, leading comments, and (Python only) the module docstring.
        Returns 0 if there is no preamble."""
        ext = self.parser.ext
        preamble_types = set(self._import_node_types())
        if ext == ".go":
            preamble_types.add("package_clause")
        if ext == ".java":
            preamble_types.add("package_declaration")

        last_preamble_end = -1
        seen_docstring = False

        for child in self.parser.tree.root_node.named_children:
            if child.type == "comment":
                last_preamble_end = child.end_point[0]
                continue
            if child.type in preamble_types:
                # Ruby: only `require`-like calls count as imports
                if ext == ".rb" and child.type == "call":
                    if not self._is_ruby_require_call(child):
                        break
                last_preamble_end = child.end_point[0]
                continue
            # Python module docstring: first expression_statement with a string
            if ext == ".py" and child.type == "expression_statement" and not seen_docstring:
                inner = child.named_children[0] if child.named_children else None
                if inner is not None and inner.type == "string":
                    last_preamble_end = child.end_point[0]
                    seen_docstring = True
                    continue
            # Non-preamble node reached
            break

        return last_preamble_end + 1 if last_preamble_end >= 0 else 0

    def _supports_block_comments(self) -> bool:
        """Languages that support C-style /* ... */ block comments."""
        return self.parser.ext in (
            ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
            ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh",
            ".go",
            ".java",
        )

    def _find_leading_comment_range(self, start_line: int):
        """
        Walk backwards from start_line, collecting the contiguous block of comment
        lines immediately above it. Returns (first_line, stop_line_exclusive) or
        None if no leading comment exists. Handles:
          - Line comments: `#` (Python/YAML/TOML), `//` (JS/TS/C/C++)
          - C-style block comments: /* ... */ (single-line and multi-line)
        Stops at the first blank line or non-comment code line; a line with
        code before or between block comments (`int x = 1; /* n */`) counts
        as code.
        """
        prefixes = self._comment_prefixes()
        if not prefixes:
            return None

        supports_block = self._supports_block_comments()
        i = start_line - 1
        in_block = False
        block_end = i  # line of the `*/` that opened in_block

        while i >= 0:
            line = self.lines[i]
            stripped = line.strip()

            if in_block:
                # Inside a multi-line block comment (scanning backwards)
                if "/*" in stripped:
                    # Reached the start of the block
                    in_block = False
                    if not stripped.startswith("/*"):
                        # `code; /* ...` -- the block trails code, so it is
                        # not part of the leading comment.
                        i = block_end
                        break
                i -= 1
                continue

            if not stripped:
                # Blank line separator -- stop walking
                break

            # Line comment (#, //, etc.)
            if any(stripped.startswith(p) for p in prefixes):
                i -= 1
                continue

            # C-style block comment handling
            if supports_block:
                # Pure single-line block comment: /* ... */ (but not
                # `/* a */ code(); /* b */`, whose first `*/` comes earlier)
                if (
                    stripped.startswith("/*")
                    and stripped.endswith("*/")
                    and stripped.find("*/", 2) == len(stripped) - 2
                ):
                    i -= 1
                    continue
                if stripped.endswith("*/"):
                    if "/*" in stripped:
                        # Code followed by a /* ... */ on the same line
                        break
                    # End of a multi-line block comment
                    in_block = True
                    block_end = i
                    i -= 1
                    continue

            # Not a comment line -- stop
            break

        if in_block:
            # No `/*` above the `*/` (e.g. a JS regex /a*/): not a comment.
            i = block_end
        first_comment_line = i + 1
        if first_comment_line >= start_line:
            return None
        return (first_comment_line, start_line)

    def _find_symbol_for_comment(self, target: str):
        """
        Resolve a comment target like find_node_by_name, but anchored on the
        whole key-value pair for YAML/TOML keys and on the first node of a
        source symbol (_symbol_span), and with a TOML-specific fallback: if
        the target doesn't match a pair, try matching a [table] header.
        Comment tools operate on positional anchors, so tables are valid targets.
        """
        node = self.parser.find_node_by_name(target)
        if node is not None:
            # Config lookups return the value, but the comment belongs above
            # its key: a YAML mapping value starts on the line after `key:`.
            if self.parser.ext in (".yml", ".yaml", ".toml"):
                pair = node
                while pair is not None and pair.type not in (
                    "block_mapping_pair",
                    "flow_pair",
                    "pair",
                ):
                    pair = pair.parent
                if pair is not None:
                    node = pair
                return node
            # The comment belongs above the symbol's decorators and a JS/TS
            # `export` (see _symbol_span).
            return self._symbol_span(node)[0]

        if self.parser.ext == ".toml" and "." not in target:
            queue = [self.parser.tree.root_node]
            while queue:
                curr = queue.pop(0)
                if curr.type == "table":
                    header = curr.named_children[0] if curr.named_children else None
                    if header:
                        name = self.parser.node_text(header).strip("[] \n")
                        if name == target:
                            return curr
                queue.extend(curr.named_children)
        return None

    def _is_ruby_require_call(self, call_node) -> bool:
        """Return True if a Ruby `call` node is a require/require_relative/load statement."""
        if not call_node.named_children:
            return False
        first = call_node.named_children[0]
        if first.type != "identifier":
            return False
        name = self.parser.node_text(first)
        return name in ("require", "require_relative", "load", "autoload")

    def _list_symbols_go(self, root) -> str:
        """
        Go-specific symbol listing. Groups methods under their receiver type, since
        Go methods live at top level but logically belong to their struct/interface.
        """
        types_by_name: dict[str, dict] = {}
        top_level_funcs: list[tuple[str, int]] = []
        methods_by_receiver: dict[str, list[tuple[str, int]]] = {}

        for child in root.named_children:
            if child.type == "type_declaration":
                for spec in child.named_children:
                    if spec.type == "type_spec":
                        name_node = spec.child_by_field_name("name")
                        if name_node:
                            name = self.parser.node_text(name_node)
                            kind = "type"
                            for inner in spec.named_children:
                                if inner.type == "struct_type":
                                    kind = "struct"
                                    break
                                if inner.type == "interface_type":
                                    kind = "interface"
                                    break
                            types_by_name[name] = {"kind": kind, "line": spec.start_point[0] + 1}
            elif child.type == "function_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    top_level_funcs.append((self.parser.node_text(name_node), child.start_point[0] + 1))
            elif child.type == "method_declaration":
                name_node = child.child_by_field_name("name")
                recv_node = child.child_by_field_name("receiver")
                if name_node and recv_node:
                    recv_type = self.parser._extract_go_receiver_type(recv_node)
                    if recv_type:
                        methods_by_receiver.setdefault(recv_type, []).append(
                            (self.parser.node_text(name_node), child.start_point[0] + 1)
                        )

        lines_out = []
        for name, info in types_by_name.items():
            lines_out.append(f"{info['kind']} {name} (line {info['line']})")
            for mname, mline in methods_by_receiver.get(name, []):
                lines_out.append(f"  method {name}.{mname} (line {mline})")

        for name, line in top_level_funcs:
            lines_out.append(f"function {name} (line {line})")

        # Orphan methods (receiver type not declared in this file)
        for recv, methods in methods_by_receiver.items():
            if recv not in types_by_name:
                for mname, mline in methods:
                    lines_out.append(f"method {recv}.{mname} (line {mline}) [external receiver]")

        if not lines_out:
            return "(no top-level symbols found)"
        return "\n".join(lines_out)

    def _replace_yaml_block_sequence(self, seq_node, content: str) -> str:
        """
        Replace a YAML block_sequence node with new content, snapping to whole
        lines and reindenting content to the column of the existing first `-`.

        Handles these caller styles cleanly:
          - Bare items ("- a\\n- b") -- indented to match the existing sequence.
          - Pre-indented items ("    - a\\n    - b") -- dedented then reindented
            so the existing column is preserved and no doubling occurs.
          - Multi-line mapping items with hanging indent preserved relative
            to the first `-` column.
        """
        start_line = seq_node.start_point[0]
        end_line = seq_node.end_point[0] + 1
        target_indent = " " * seq_node.start_point[1]

        lines = _content_lines(content)
        non_blank = [ln for ln in lines if ln.strip()]
        if not non_blank:
            raise ApplierError("Cannot replace YAML sequence with empty content")

        def _leading_spaces(s: str) -> int:
            n = 0
            for c in s:
                if c == " ":
                    n += 1
                else:
                    return n
            return n

        min_indent = min(_leading_spaces(ln) for ln in non_blank)
        reindented: list[str] = []
        for ln in lines:
            if not ln.strip():
                reindented.append("")
            else:
                reindented.append(target_indent + ln[min_indent:])

        self.lines = self.lines[:start_line] + reindented + self.lines[end_line:]
        return self._save()
