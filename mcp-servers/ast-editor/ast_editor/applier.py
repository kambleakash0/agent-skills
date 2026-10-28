import ast
import difflib
import functools
import json
import os
import re
import sys
import warnings
from ast_editor.parser import (
    C_EXTS,
    CPP_EXTS,
    DEFAULT_EXPORT_KINDS,
    JS_FUNCTION_VALUES,
    ApplierError,
    Target,
    TreeSitterParser,
    c_name,
    first_syntax_error,
    split_config_path,
    toml_key_names,
)


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
    """Number of blank lines (empty, or only spaces and tabs) that end
    `lines`. A form feed line (a Python page break) is text, not blank."""
    n = 0
    while n < len(lines) and not lines[-1 - n].strip(" \t"):
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
_CONFIG_EXTS = (".json", ".yml", ".yaml", ".toml")

# The tokens that end a statement or an entry where others may follow it
# on its line (`x = 1; y = 2`, `{ a: 1, b: 2 }`).
_SEPARATORS = (";", ",")

# Methods and functions declared without a body: TS abstract methods, method
# signatures (class overloads, interface members) and function overloads,
# and Java abstract and interface methods.
_BODILESS_FUNCTIONS = (
    "abstract_method_signature",
    "method_signature",
    "function_signature",
    "method_declaration",
)

# The C/C++ class, struct, union and enum nodes, which leave out the `;`
# after their `}` (see Applier._symbol_span).
_C_TYPE_SPECIFIERS = ("class_specifier", "struct_specifier", "union_specifier", "enum_specifier")

# The C/C++ preprocessor conditionals, whose branches hold declarations of
# the scope they are in (see Applier._scope_members).
_PREPROC_CONDITIONALS = ("preproc_if", "preproc_ifdef", "preproc_else", "preproc_elif", "preproc_elifdef")

# The constructs a symbol can end that only add what is written before it,
# so that an edit to the whole symbol takes them too (see
# Applier._symbol_unit): a Go `type`, `var` or `const` and a composite
# literal's key, a TS `declare`, a JS/TS `export` and object key, a C++
# `extern "C"` and a Ruby `private def`. Other containers hold the code
# before the symbol as siblings of their own (a Java enum's members after
# its constants, a C #else branch, a Ruby else branch).
_UNIT_WRAPPERS = (
    "type_declaration",
    "var_declaration",
    "const_declaration",
    "keyed_element",
    "literal_element",
    "ambient_declaration",
    "export_statement",
    "pair",
    "linkage_specification",
    "argument_list",
    "call",
)

# The start of a TS function or method and its name (`function f(`,
# `abstract m<T>(`), which a later member of its overload group starts with
# (see Applier._overload_member).
_TS_MEMBER_HEAD = (
    r"(?:(?:export|declare|default|async|function|public|private|protected|static|abstract|override|readonly)\s+)*"
    r"""\*?\s*(#?[\w$]+|'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")\s*[<(]"""
)

# The string literals that can span lines, by file extension (see
# Applier._literal_rows): Python strings (any prefix), JS/TS template
# literals and strings continued with a backslash, Ruby strings (`%q(...)`
# too), heredocs, backtick commands and regexps, Go raw strings, C/C++
# strings and C++ raw strings, Java text blocks and TOML multi-line strings.
# JSON strings stay on one line, and YAML values (block scalars, whose
# indentation YAML strips, included) move with the code.
_MULTILINE_STRINGS = {
    ".py": ("string",),
    ".rb": ("string", "heredoc_body", "subshell", "regex"),
    ".go": ("raw_string_literal",),
    ".java": ("string_literal",),
    ".toml": ("string",),
    **{ext: ("template_string", "string") for ext in _JS_EXTS},
    **{ext: ("string_literal",) for ext in C_EXTS},
    **{ext: ("string_literal", "raw_string_literal") for ext in CPP_EXTS},
}

# The nodes whose text is words rather than tokens of code, where a body
# snippet may start or end between any two words (see
# Applier._splits_token): comments (every node type with "comment" in its
# name), string literals and their parts, regular expressions, character
# literals and a C/C++ macro's body. The code of an interpolation in a
# string (`f"{x}"`, `${x}`, `#{x}`) is tokens again, and so are the tokens
# that open and close a string.
_TEXT_NODES = (
    "string",
    "string_content",
    "string_fragment",
    "escape_sequence",
    "concatenated_string",
    "template_string",
    "regex",
    "regex_pattern",
    "jsx_text",
    "interpreted_string_literal",
    "interpreted_string_literal_content",
    "raw_string_literal",
    "raw_string_literal_content",
    "rune_literal",
    "heredoc_body",
    "heredoc_content",
    "bare_string",
    "subshell",
    "character",
    "string_literal",
    "multiline_string_fragment",
    "character_literal",
    "raw_string_content",
    "char_literal",
    "system_lib_string",
    "preproc_arg",
)
_INTERPOLATIONS = ("interpolation", "template_substitution")
_STRING_DELIMITERS = ("string_start", "string_end", "raw_string_delimiter", "heredoc_end")
# A character that continues an identifier, number or keyword.
_WORD_CHARACTER = re.compile(r"\w")

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
# Content that starts a block sequence or block mapping (`- a`, `? k`,
# `x: 1`, `"x y": 1`, `x:`), which cannot follow `key:` on its line.
_YAML_BLOCK_START = re.compile(
    r"[ \t]*(?:[-?](?:[ \t]|$)"
    r"|(?:\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\n]|'')*'|[^\s#'\"{}\[\],&*!|>%@`-][^#\n]*?)[ \t]*:(?:[ \t]|$))"
)
# A line that is only a block scalar header (`|`, `>-`, `|2`) or node
# properties (`&anchor`, `!tag`), which the rest of a value follows on the
# lines below, maybe with a comment.
_YAML_NODE_HEADER = re.compile(
    r"(?:[&!][^\s#]*[ \t]+)*(?:[&!][^\s#]*|[|>][-+0-9]*)(?:[ \t]+#.*)?"
)
# An encoding declaration, which Python (PEP 263) and Ruby read on the first
# two lines, and a Ruby magic comment, read anywhere in the comments at the
# top of the file.
_CODING_COMMENT = re.compile(r"[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")
_RUBY_MAGIC_COMMENT = re.compile(
    r"[ \t]*#.*?\b(frozen_string_literal|warn_indent|shareable_constant_value)[ \t]*:"
)

# A comment on a line of its own that a tool reads as applying to the line
# below it: TypeScript's @ts-ignore and @ts-expect-error, an
# eslint/tslint/stylelint disable-next-line, pylint's disable-next, a
# biome-ignore, deno-lint-ignore or prettier-ignore, clang-tidy's and
# cpplint's NOLINTNEXTLINE, a Flow suppression, an istanbul/c8/v8 `ignore
# next`, a Go //nolint or //lint:ignore and a JetBrains noinspection.
_NEXT_LINE_DIRECTIVE = re.compile(
    r"@ts-(?:ignore|expect-error)\b|disable-next(?:-line)?\b|\b(?:biome|deno-lint)-ignore(?![-\w])"
    r"|prettier-ignore\b|NOLINTNEXTLINE\b|\$Flow(?:FixMe|ExpectedError|Ignore|Issue)\b"
    r"|\b(?:istanbul|c8|v8)\s+ignore\s+next\b|^\W*(?:nolint|lint:ignore)\b|\bnoinspection\b"
)


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


def _natural(text: str) -> list:
    """`text` split for a natural sort, as isort and ruff sort: its runs of
    digits as numbers, the text between them as text ('a9' before 'a10')."""
    return [int(part) if i % 2 else part for i, part in enumerate(re.split(r"(\d+)", text))]


def _name_type(name: str) -> int:
    """The type of an imported name in isort's and ruff's order by type: 0
    for CONSTANT_CASE (two characters or more), 1 for CamelCase, 2 for the
    rest."""
    if len(name) > 1 and name.isupper():
        return 0
    return 1 if name[:1].isupper() else 2


def _sorted_index(keys: list[tuple], new: tuple) -> int | None:
    """Where an item whose sort keys are `new` goes among items whose sort
    keys are `keys`: each a tuple of keys, one per order the items may
    follow, the first one preferred. In the first order the items follow,
    before the first one that sorts after the new one (at the end when
    none does); None when they follow none."""
    for order, key in enumerate(new):
        column = [k[order] for k in keys]
        if all(a <= b for a, b in zip(column, column[1:])):
            return next((i for i, k in enumerate(column) if k > key), len(column))
    return None


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


def _config_path(parent: str, name: str) -> str:
    """The JSON or YAML target path of key `name` under the path `parent`
    ('' for the root), the key in double quotes when it has to be one
    segment of its own (split_config_path): when it has a dot, starts with
    a quote or has spaces or tabs around it."""
    if "." in name or name[:1] in "\"'" or name != name.strip(" \t"):
        name = json.dumps(name, ensure_ascii=False)
    return f"{parent}.{name}" if parent else name


class _Span:
    """Consecutive entries of a list that _entry_deleted deletes as one (a
    Python parameter with the `*` or `/` it leaves without a parameter): the
    range from the first one's start to the last one's end."""

    type = "span"

    def __init__(self, first, last):
        self.start_byte, self.start_point = first.start_byte, first.start_point
        self.end_byte, self.end_point = last.end_byte, last.end_point


def _refusing_lone_surrogates(cls):
    """
    Class decorator for Applier: each public method first refuses a string
    argument that holds a lone surrogate. JSON lets a client send half of a
    surrogate pair as an escape; it is not a character and has no UTF-8
    form, so no edit holding one can be written. Checking the arguments up
    front gives one clear refusal, whichever step would encode them first.
    """

    def checking(method):
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            for value in (*args, *kwargs.values()):
                if isinstance(value, str):
                    try:
                        value.encode("utf-8")
                    except UnicodeEncodeError as e:
                        raise ApplierError(
                            f"Refused: the text holds a lone surrogate, U+{ord(value[e.start]):04X}, "
                            f"which is not a character and can't be written as UTF-8. "
                            f"{self.filepath} was not modified."
                        ) from e
            return method(self, *args, **kwargs)

        return wrapper

    for name, attr in list(vars(cls).items()):
        if not name.startswith("_") and callable(attr) and not isinstance(attr, (staticmethod, classmethod)):
            setattr(cls, name, checking(attr))
    return cls


@_refusing_lone_surrogates
class Applier:
    def __init__(self, filepath: str):
        self.filepath = filepath
        try:
            self.parser = TreeSitterParser(filepath)
        except ValueError as e:
            # tree-sitter parser raises ValueError for unsupported extensions
            # and files that are not UTF-8; convert to ApplierError so callers
            # can distinguish user errors from internal ones.
            raise ApplierError(str(e)) from e

        # LF-normalised text, so line indices match the tree's rows. The
        # lines as read stay apart, for the lines an edit leaves alone
        # (_save).
        self.lines = _split_lines(self.parser.source_code)
        self._read_lines = tuple(self.lines)

    def _get_indent(self, line: str) -> str:
        """The spaces and tabs a line starts with. A form feed, U+2028 or
        other whitespace after them is part of the line's text, not its
        indentation (Python reads a form feed there as a page break)."""
        return line[: len(line) - len(line.lstrip(" \t"))]

    def _reindent(self, content_lines: list[str], target_indent: str) -> list[str]:
        """
        content_lines with the indentation of the first one changed to
        target_indent, and the same change made to every line that starts
        with it; a line indented less than the first gets target_indent in
        place of its own. Blank lines stay as they are, and so do the lines
        that start inside a multi-line string literal of the content
        (_literal_rows), which are part of its value. Those of a literal
        whose language strips their common indentation (a Python docstring,
        a Ruby `<<~` heredoc, a Java text block) move with the code instead,
        all by the same number of columns, unless one of them is indented
        less than the code moves back (_shift_line): then they all stay.
        """
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
                # Only spaces and tabs are indentation (see _get_indent).
                result.append(target_indent + line.lstrip(" \t"))
        for rows, shifts in self._literal_rows(content_lines):
            kept = content_lines[rows.start : rows.stop]
            moved = [self._shift_line(line, old_indent, target_indent) for line in kept] if shifts else [None]
            result[rows.start : rows.stop] = kept if None in moved else moved
        return result

    def _literal_rows(self, lines: list[str]) -> list[tuple[range, bool]]:
        """
        For each multi-line string literal of the caller content `lines`
        (see _MULTILINE_STRINGS), the indices of the lines that start inside
        it (the lines after its first, up to the one it ends on) and whether
        its language strips their common indentation from its value: a
        Python docstring (the first statement of the content, a class or a
        function, when it is a string), a Ruby `<<~` heredoc or a Java text
        block. The content is parsed with the file's grammar, Python's
        dedented by its first line's indentation first; a literal with a
        syntax error in it is left out, so its lines are re-indented as code.
        A Ruby embedded document (`=begin` ... `=end`, which Ruby reads only
        from the start of a line) counts as such a literal with all of its
        lines, its `=begin` line too, when it starts at column 0; one that
        does not is no embedded document for Ruby, and its lines are code.
        """
        ext = self.parser.ext
        types = _MULTILINE_STRINGS.get(ext)
        if not types or len(lines) < 2:
            return []
        if ext == ".py":
            # Python parses only from column 0, and where a string ends does
            # not depend on how its lines are indented.
            old = self._get_indent(lines[0])
            lines = [line[len(old) :] if line.startswith(old) else line for line in lines]
        root = self.parser.parse("\n".join(lines).encode("utf-8")).root_node
        literals, openers, documents, stack = [], [], [], [root]
        while stack:
            node = stack.pop()
            if node.type == "heredoc_beginning":
                openers.append(node)
            if self._is_embedded_document(node) and node.start_point[1] == 0:
                documents.append(range(node.start_point[0], node.end_point[0] + 1))
            if node.type in types and node.end_point[0] > node.start_point[0]:
                if not node.has_error:
                    literals.append(node)
                continue
            stack.extend(reversed(node.children))
        # Ruby heredoc bodies come in the order of their `<<~EOS` openers.
        bodies = [node for node in literals if node.type == "heredoc_body"]
        squiggly = {}
        if len(bodies) == len(openers):
            squiggly = {body.start_byte: opener.text.startswith(b"<<~") for body, opener in zip(bodies, openers)}
        result = []
        for node in literals:
            if node.type == "heredoc_body":
                shifts = squiggly.get(node.start_byte, False)
            elif ext == ".java":
                shifts = node.text.startswith(b'"""')
            elif ext == ".py":
                shifts = self._is_docstring(node)
            else:
                shifts = False
            result.append((range(node.start_point[0] + 1, node.end_point[0] + 1), shifts))
        return result + [(rows, False) for rows in documents]

    @classmethod
    def _is_docstring(cls, string) -> bool:
        """Whether a Python string node is a docstring: the first statement
        (comments are none) of the module, a class or a function."""
        stmt = string.parent
        if stmt is None or not cls._is_docstring_node(stmt):
            return False
        body = stmt.parent
        if body.type == "block":
            if body.parent is None or body.parent.type not in ("function_definition", "class_definition"):
                return False
        elif body.type != "module":
            return False
        return next(c for c in body.named_children if c.type != "comment") == stmt

    def _is_embedded_document(self, node) -> bool:
        """Whether `node` is a Ruby embedded document (`=begin` ... `=end`),
        which tree-sitter-ruby reads as a comment wherever its `=begin` starts
        (Ruby, only at the start of a line)."""
        return self.parser.ext == ".rb" and node.type == "comment" and node.text.startswith(b"=begin")

    def _misplaced_document(self, root):
        """The first Ruby embedded document under `root` whose `=begin` does
        not start its line, which Ruby rejects although tree-sitter-ruby reads
        it, or None. Iterative, like first_syntax_error."""
        if self.parser.ext != ".rb":
            return None
        stack = [root]
        while stack:
            node = stack.pop()
            if self._is_embedded_document(node) and node.start_point[1] != 0:
                return node
            stack.extend(reversed(node.children))
        return None

    def _shift_line(self, line: str, old: str, new: str) -> str | None:
        """
        A line of a literal whose language strips the common indentation of
        its lines (see _reindent), moved by as many columns as a line of code
        indented `old` moves to `new`: its `old` replaced with `new`, the
        indentation `new` adds put before it, or the indentation `new` drops
        taken from it. None when it is indented less than that, or `old` and
        `new` differ in more than their length. A blank line stays as it is.
        """
        if not line.strip():
            return line
        if line.startswith(old):
            return new + line[len(old) :]
        if new.startswith(old):
            return new[len(old) :] + line
        cut = len(old) - len(new)
        if old.startswith(new) and len(self._get_indent(line)) >= cut:
            return line[cut:]
        return None

    def _from_read_shape(self, lines: list[str], indent: str) -> list[str]:
        """
        The lines of content for a whole symbol (replace_function, add_method,
        add_field, insert_sibling, add_top_level) that goes in at `indent`,
        written as read_symbol shows a symbol, turned into the absolute shape:
        the first line given the indentation it was read at (_read_shape_indent).
        Content in another shape is returned as it is.
        """
        read_at = self._read_shape_indent(lines, indent)
        return lines if read_at is None else [read_at + lines[0]] + lines[1:]

    def _read_shape_indent(self, lines: list[str], indent: str) -> str | None:
        """
        The indentation of the line that read_symbol read the content `lines`
        from, when they are in the shape it shows a symbol in, else None.
        read_symbol shows a symbol from its first byte: its first line without
        the indentation of its line, the later lines with all of theirs. The
        two other shapes of content give None: relative (the first line at
        column 0, the later ones indented from it) and absolute (every line at
        its file indentation, the first one too). Config files give None.

        Content whose first line has no indentation is in read_symbol's shape,
        read at the indentation P, when every later line of code starts with P
        and each one at P itself is a line that sits at the indentation of the
        symbol it is part of (_symbol_level_line): a closing `}`, `)`, `]` or
        `>`, a `{` on a line of its own, a C++ access label or initializer
        list, a Ruby `end`, `else`, `elsif`, `rescue`, `ensure`, `when` or
        `in`, or, when the first line is a decorator, annotation or template
        header, one of the symbol's other headers and the line they introduce
        (the `def` below `@property`, a method below the `)` that ends its
        decorator's arguments). Content for several members (two methods, a
        method and a decorated one) has more lines at P: each line that
        starts another member after the one before it ended (_next_member),
        with its headers and the line they introduce. Relative content has
        those lines at column 0, and a line of code at P that is none of
        them (a def's body, an expression continued on the next line, the
        `@property` of a nested method, a statement below a Whitesmiths `{`)
        makes it relative content indented by as much as P. The lines that
        start inside a multi-line string or a Ruby embedded document
        (_literal_rows), comment lines, C/C++ preprocessor lines, the lines
        a macro continues on, and labels may be at any column, so they do
        not count.

        P is tried first as the indentation of the last line when it closes
        the symbol (`}`, `end`), then as that of the line after a first line
        that is a decorator, annotation or template header, and in Python as
        that of the shallowest later line of code: content read at another
        depth (copied from another class) is recognised by that line, which
        must then be a line of code at P (in Python, a def, class or
        decorator that starts another member). Last, P is `indent`, the
        indentation of the place the content goes, for content read there
        or at the same depth; this reading needs no line at P, so a Python
        def or class whose later lines are all deeper than `indent` is taken
        as read_symbol shows it, also when it was written relative with a
        deeper indentation than the file's (a 4-space method for a 2-space
        class keeps its body 4 spaces in).
        """
        if (
            self.parser.ext in _CONFIG_EXTS
            or len(lines) < 2
            or not lines[0].strip(" \t")
            or self._get_indent(lines[0])
        ):
            return None
        if self.parser.ext == ".rb" and lines[0].startswith("=begin"):
            # An embedded document stays at column 0.
            return None
        later = [i for i in range(1, len(lines)) if lines[i].strip(" \t")]
        if not later:
            return None
        tried = []
        if self._symbol_level_line(lines[later[-1]], closing=True):
            tried.append((self._get_indent(lines[later[-1]]), later[-1]))
        if self._is_header_line(lines[0]):
            tried.append((self._get_indent(lines[later[0]]), later[0]))
        if self.parser.ext == ".py":
            # Several members read at another depth: the shallowest line of
            # code starts one of them, a def, class or decorator.
            free = {i for rows, _ in self._literal_rows(lines) for i in rows}
            code = [i for i in later if i not in free and not lines[i].lstrip(" \t").startswith("#")]
            if code:
                shallowest = min(code, key=lambda i: len(self._get_indent(lines[i])))
                if re.match(r"(@|class\b|def\b|async\s+def\b)", lines[shallowest].lstrip(" \t")):
                    tried.append((self._get_indent(lines[shallowest]), shallowest))
        tried.append((indent, None))
        for read_at, anchor in tried:
            if read_at and self._fits_read_shape(lines, read_at, anchor):
                return read_at
        return None

    def _fits_read_shape(self, lines: list[str], read_at: str, anchor: int | None) -> bool:
        """Whether the content `lines` reads as read_symbol shows a symbol
        read at the indentation `read_at` (see _read_shape_indent), with the
        line `anchor`, if given, one of its lines of code at `read_at`. The
        later members of an overload group start at `read_at` too
        (_overload_member), and so do the other members that content for
        several of them holds, each after the one before it ended
        (_next_member)."""
        absolute = [read_at + lines[0]] + lines[1:]
        free = {i for rows, _ in self._literal_rows(absolute) for i in rows}
        root = None
        if self.parser.ext not in (".py", ".rb"):
            root = self.parser.parse("\n".join(absolute).encode("utf-8")).root_node
        # Whether the lines at `read_at` so far are the symbol's headers (its
        # decorators, annotations or template header, a `)` that ends their
        # arguments), which the line they introduce follows at `read_at`.
        # After it, a header at `read_at` is one of a nested symbol (the
        # `@property` of a method, relative content).
        header = self._is_header_line(lines[0])
        anchored = anchor is None
        # The last line at `read_at` and the lines of code below it, and the
        # line the last member starts on.
        group, previous, below, start = self._overload_name(lines), lines[0].strip(" \t"), [], 0
        for i in range(1, len(lines)):
            line = lines[i]
            if not line.strip(" \t") or i in free or self._free_line(root, absolute, i):
                continue
            if not line.startswith(read_at):
                return False
            at_level = self._get_indent(line) == read_at
            if at_level and header:
                header = self._is_header_line(line) or self._symbol_level_line(line, closing=True)
            elif at_level and (self._is_header_line(line) or not self._symbol_level_line(line, closing=False)):
                if not (
                    self._overload_member(line, previous, below, group)
                    or self._next_member(lines, start, i, read_at, previous)
                ):
                    return False
                header, start = self._is_header_line(line), i
            if at_level:
                previous, below = line.strip(" \t"), []
            else:
                below.append(line.strip(" \t"))
            anchored = anchored or (i == anchor and at_level)
        return anchored

    def _overload_name(self, lines: list[str]) -> str | None:
        """The name of the function that the content `lines` starts with, for
        the later members of its overload group (_overload_member): a Python
        def's (after its decorators), a TS function's or method's; None in
        other languages or when the content starts with something else."""
        ext = self.parser.ext
        for line in lines:
            code = line.strip(" \t")
            if not code or (ext == ".py" and code.startswith("@")):
                continue
            if ext == ".py":
                found = re.match(r"(?:async\s+)?def\s+(\w+)", code)
            elif ext in (".ts", ".tsx"):
                found = re.match(_TS_MEMBER_HEAD, code)
            else:
                found = None
            return found.group(1) if found else None
        return None

    def _overload_member(self, line: str, previous: str, below: list[str], name: str | None) -> bool:
        """Whether `line`, at the indentation of the symbol it is part of,
        starts another member of the overload group of the function `name`
        (TreeSitterParser.python_overload, _overload_group), the line at that
        indentation before it being `previous` and the lines of code between
        them `below`: in TS a signature or the implementation after a
        signature that ends with `;`, in Python a decorator or a def of that
        name after an @overload stub, a def (or the `)` that ends its
        parameters) whose body is `...`, `pass` or a docstring, on its line
        (`def f(a: int) -> int: ...`) or below it."""
        if name is None:
            return False
        code = line.strip(" \t")
        if self.parser.ext in (".ts", ".tsx"):
            if not previous.rstrip().endswith(";"):
                return False
            # A decorator of the implementation, after the signatures.
            head = re.match(_TS_MEMBER_HEAD, code)
            return code.startswith("@") or (head is not None and head.group(1) == name)
        definition = rf"(?:async\s+)?def\s+{re.escape(name)}\b"
        if not (re.match(definition, previous) or previous.startswith(")")):
            return False
        inline = re.search(r":\s*\.\.\.\s*(?:#.*)?$", previous) is not None and not below
        empty = (
            re.search(r":\s*(?:#.*)?$", previous) is not None
            and below
            and all(text in ("...", "pass") or text.startswith(("'", '"')) for text in below)
        )
        if not (inline or empty):
            return False
        return code.startswith("@") or re.match(definition, code) is not None

    def _next_member(self, lines: list[str], start: int, row: int, read_at: str, previous: str) -> bool:
        """
        Whether the line `row` of the content `lines`, at `read_at`, the
        indentation of the symbol it is part of, starts another member
        after the one before it ended, in content that holds several
        (two methods, a method and the decorated one below it, two
        fields). In Python the lines of the member before it, from the line
        `start`, read at `read_at`, must be whole statements: Python parses
        them moved back by `read_at` (but the content's first line, which
        has no indentation). Elsewhere `previous`, the last line before it
        at `read_at`, must end a member: a `}`, `)`, `]` or Ruby `end`
        (_symbol_level_line), or a line that ends with `;` or `}` (in Go,
        one that does not end with a bracket that opens, a comma or an
        operator). A relative content's body line never follows one, as
        its first one comes right after the content's first line, which
        opens the body.
        """
        if self.parser.ext == ".py":
            moved = [
                line[len(read_at) :] if i and line.startswith(read_at) else line
                for i, line in enumerate(lines[start:row], start)
            ]
            return _python_syntax_error("\n".join(moved).encode("utf-8")) is None
        if self._symbol_level_line(previous, closing=True):
            return True
        code = re.sub(r"\s*(//.*|/\*.*\*/)$", "", previous)
        if self.parser.ext == ".go":
            # Go has no `;`, opens its blocks with a `{` at the end of the
            # line and continues a line only after an operator or a comma.
            return re.search(r"[{(\[,.=+\-*/%&|^<>!:]$", code) is None
        return code.endswith((";", "}"))

    def _symbol_level_line(self, line: str, closing: bool) -> bool:
        """Whether `line` is one that sits at the indentation of the symbol it
        is part of: one that closes it (`}`, `)`, `]`, `>`, a Ruby `end`), or,
        unless `closing`, a `{` on a line of its own, a decorator, annotation
        or template header, a C++ access label (`public:`) or constructor
        initializer list (`: x(1)`), or a Ruby `else`, `elsif`, `rescue`,
        `ensure`, `when` or `in`."""
        code = line.strip(" \t")
        if code[:1] in ("}", ")", "]", ">") or (self.parser.ext == ".rb" and re.match(r"end\b", code)):
            return True
        if closing:
            return False
        if self.parser.ext == ".rb":
            return re.match(r"(else|elsif|rescue|ensure|when|in)\b", code) is not None
        if self.parser.ext in CPP_EXTS and (
            re.match(r"(public|protected|private)\b[\w \t]*:(?!:)", code) or re.match(r":(?!:)", code)
        ):
            return True
        return code.startswith("{") or self._is_header_line(line)

    def _is_header_line(self, line: str) -> bool:
        """Whether `line` is a decorator or annotation (`@...`, in Python,
        JS/TS and Java), a C++ `template <...>` header or `[[attribute]]`,
        or the start of a Ruby Sorbet signature (`sig { void }`, `sig do`),
        which the rest of a symbol follows at the same indentation."""
        code = line.strip(" \t")
        if self.parser.ext in (".py", ".java") + _JS_EXTS:
            return code.startswith("@")
        if self.parser.ext in CPP_EXTS:
            return re.match(r"template\s*<", code) is not None or code.startswith("[[")
        if self.parser.ext == ".rb":
            return re.match(r"sig\b\s*(?:[({]|do\b)", code) is not None
        return False

    def _free_line(self, root, lines: list[str], row: int) -> bool:
        """Whether the line `row` of the content `lines`, parsed as `root` (None
        for Python and Ruby), may be at any column: a comment line, a C/C++
        preprocessor line or a line a macro continues on, or a label
        (`retry:`)."""
        code = lines[row].lstrip(" \t")
        if self.parser.ext in (".py", ".rb") or self.parser.ext in C_EXTS + CPP_EXTS:
            if code.startswith("#"):
                return True
        if root is None:
            return False
        column = len(lines[row][: len(lines[row]) - len(code)].encode("utf-8"))
        node = root.descendant_for_point_range((row, column), (row, column))
        if node is None:
            return False
        if "comment" in node.type:
            return True
        directive = node
        while directive is not None and directive.type not in ("preproc_def", "preproc_function_def", "preproc_call"):
            directive = directive.parent
        if directive is not None and directive.start_point[0] < row:
            # A line a macro continues on after a `\`.
            return True
        parent = node.parent
        return parent is not None and parent.type == "labeled_statement" and parent.start_byte == node.start_byte

    def _symbol_span(self, node):
        """
        The first and last nodes of a symbol's source as written, for the
        edits that take a whole symbol (read_symbol, replace_function,
        delete_symbol, insert_sibling, edit_leading_comment). That is the
        node itself, except that a JS/TS exported declaration spans its whole
        `export` statement (with any decorators written before `export`), a
        decorated Python class its decorated_definition, a C++ template its
        `template <...>` header (the outermost template_declaration, when a
        member template defined outside its class has two; a template
        class's ends with the `;` after its `}`), a C/C++ class, struct,
        union or enum ends with the `;` after it, as a template class does
        (a member one is its field_declaration), a Ruby statement that opens
        heredocs (`X = <<~EOS`) ends with their bodies, which the grammar
        places after it, a Ruby method starts at its Sorbet signature
        (`sig { void }`, _sorbet_signature), and a TS class
        member starts at the first of the decorators the grammar places
        beside it in the class body, comments between them included.
        Decorated Python functions are found as their decorated_definition,
        and JS method decorators and Java annotations are inside the node,
        already. A TS function's overload signatures and a Python function's
        @overload stubs are part of it (_overload_group).
        """
        group = self._overload_group(node)
        if group is not None:
            first, last = group
            prev = first.prev_named_sibling
            while prev is not None and (prev.type == "decorator" or "comment" in prev.type):
                if prev.type == "decorator":
                    first = prev
                prev = prev.prev_named_sibling
            return first, last
        parent = node.parent
        if parent is not None and parent.type in ("export_statement", "decorated_definition"):
            return parent, parent
        if self.parser.ext in C_EXTS + CPP_EXTS:
            while node.parent is not None and node.parent.type == "template_declaration":
                node = node.parent
            end = node.next_sibling
            if (
                node.type in _C_TYPE_SPECIFIERS
                and end is not None
                and end.type == ";"
                and not self.parser.source_bytes[node.end_byte : end.start_byte].strip()
            ):
                # A member class is a field_declaration of its own with its `;`.
                if node.parent.type == "field_declaration" and node.parent.child_count == 2:
                    return node.parent, node.parent
                return node, end
            return node, node
        if self.parser.ext == ".rb":
            # The bodies of the heredocs a statement opens (`X = <<~EOS`)
            # follow it, each from the line where the one before ends.
            last = node
            while (
                last.next_sibling is not None
                and last.next_sibling.type == "heredoc_body"
                and last.next_sibling.start_point[0] == last.end_point[0]
            ):
                last = last.next_sibling
            return self._sorbet_signature(node) or node, last
        if self.parser.ext not in _JS_EXTS:
            return node, node
        first = node
        prev = node.prev_named_sibling
        while prev is not None and (prev.type == "decorator" or "comment" in prev.type):
            if prev.type == "decorator":
                first = prev
            prev = prev.prev_named_sibling
        return first, node

    def _sorbet_signature(self, node):
        """
        The Sorbet signature of the Ruby method `node`, which is part of the
        method as a decorator is (_symbol_span): the `sig { ... }` or `sig
        do ... end` call (`sig(:final) { ... }` too) that is the statement
        right before the method, or before the `private def` it is in, with
        only comments and no blank line between them; else None.
        """
        if node.type not in ("method", "singleton_method"):
            return None
        statement = node
        while (
            statement.parent is not None
            and statement.parent.type == "argument_list"
            and statement.parent.parent is not None
            and statement.parent.parent.type == "call"
        ):
            statement = statement.parent.parent
        prev = statement.prev_named_sibling
        while prev is not None and prev.type == "comment":
            prev = prev.prev_named_sibling
        if prev is None or not self._is_sorbet_signature(prev):
            return None
        between = self.lines[prev.end_point[0] + 1 : statement.start_point[0]]
        return None if any(not line.strip(" \t") for line in between) else prev

    def _is_sorbet_signature(self, node) -> bool:
        """Whether `node` is a Ruby `sig` call with a block (`sig { void }`,
        `sig do ... end`), Sorbet's signature for the method below it."""
        method = node.child_by_field_name("method") if node.type == "call" else None
        return (
            self.parser.ext == ".rb"
            and method is not None
            and node.child_by_field_name("receiver") is None
            and node.child_by_field_name("block") is not None
            and self.parser.node_text(method) == "sig"
        )

    def _overload_group(self, node):
        """
        The first and last statements of the overload group of `node`, a
        function or method, when it has one, else None: in TS the overload
        signatures directly before an implementation (`function f(a:
        string): void;` before `function f(a: any) {...}`, `m(a: string):
        void;` before `m(a: any) {}`, through their `export` and `declare`)
        and in Python the @overload stubs directly before a function
        (TreeSitterParser.python_overload), comments between them included;
        a run of signatures or stubs with no implementation after them is a
        group of its own, from the first. The group is one symbol, as the
        decorators of a function are part of it.
        """
        parser = self.parser
        if parser.ext in (".ts", ".tsx"):
            wrappers = ("export_statement", "ambient_declaration")
            signatures = ("function_signature", "method_signature", "abstract_method_signature")
            functions = signatures + ("function_declaration", "generator_function_declaration", "method_definition")
        elif parser.ext == ".py":
            wrappers, signatures, functions = (), (), ("function_definition", "decorated_definition")
        else:
            return None
        if node.type not in functions:
            return None

        def declaration(statement):
            while statement is not None and statement.type in wrappers:
                statement = statement.child_by_field_name("declaration") or next(
                    (c for c in statement.named_children if "comment" not in c.type), None
                )
            return statement

        def name_of(declaration):
            if declaration is not None and declaration.type == "decorated_definition":
                declaration = declaration.child_by_field_name("definition")
            name = declaration.child_by_field_name("name") if declaration is not None else None
            return parser.node_text(name) if name is not None else None

        name = name_of(node)

        def announces(statement) -> bool:
            # A signature or stub of the same name.
            inner = declaration(statement)
            if inner is None or name_of(inner) != name:
                return False
            return inner.type in signatures or parser.python_overload(inner)

        statement = node
        while statement.parent is not None and statement.parent.type in wrappers:
            statement = statement.parent
        first = last = statement
        sibling = statement.prev_named_sibling
        # The decorators the TS grammar places beside a method come between
        # its signatures and it.
        while sibling is not None and ("comment" in sibling.type or sibling.type == "decorator" or announces(sibling)):
            if announces(sibling):
                first = sibling
            sibling = sibling.prev_named_sibling
        if announces(statement):
            sibling = statement.next_named_sibling
            while sibling is not None and ("comment" in sibling.type or announces(sibling)):
                if "comment" not in sibling.type:
                    last = sibling
                sibling = sibling.next_named_sibling
        if name is None or (first == statement and last == statement):
            return None
        return first, last

    @staticmethod
    def _template_entity(node):
        """What the C++ template_declaration `node` declares (through the
        nested headers of a member template defined outside its class), or
        None."""
        while node is not None and node.type == "template_declaration":
            node = next(
                (c for c in reversed(node.named_children)
                 if c.type != "template_parameter_list" and "comment" not in c.type),
                None,
            )
        return node

    def _symbol_unit(self, node):
        """
        The first and last nodes of the code that an edit to the whole symbol
        `node` takes in a source file: its span (_symbol_span), widened over
        the constructs it ends, which only add what is written before it: a
        Go `type`, `var` or `const` around its one spec, a TS `declare`, a C++
        `extern "C"`, a Ruby `private def`, the key of a closure in an object
        or composite literal (`handler: () => {}`), and the C/C++ typedef or
        declaration whose type a struct, union, enum or class is (`typedef
        struct Node {...} Node;`), all listed in _UNIT_WRAPPERS. Any other
        container (a class body, a Java enum's body declarations, a C #else
        or a Ruby else branch) holds the code before the symbol as siblings,
        never as part of it. A Ruby method's Sorbet signature starts the
        unit of a `private def` too.
        """
        first, last = self._symbol_span(node)
        # A Ruby method's Sorbet signature stays first, before the `private
        # def` the method is widened over.
        sig = first if first != node and self._is_sorbet_signature(first) else None
        if sig is not None:
            first = node
        if first != last or self.parser.ext in _CONFIG_EXTS:
            return sig or first, last
        while True:
            parent = last.parent
            if parent is None or parent.parent is None:
                break
            later = [
                c for c in parent.children
                if c != last and c.start_byte >= last.end_byte and "comment" not in c.type
            ]
            heads = (
                self.parser.ext in C_EXTS + CPP_EXTS
                and parent.type in ("type_definition", "declaration", "field_declaration")
                and parent.child_by_field_name("type") == last
            )
            if not heads and (later or parent.type not in _UNIT_WRAPPERS):
                break
            if parent.type == "argument_list" and any(
                c != last and "comment" not in c.type for c in parent.named_children
            ):
                # `private def f`, not `foo x, def f`
                break
            last = parent
        return sig or last, last

    def _same_line(self, end: int, start: int) -> bool:
        """Whether the code that ends at byte `end` and the code that starts
        at `start` share a line (a node such as a C #include can end with
        its line break). A block comment between them that goes on over
        lines (`int x; /* a\\n b */ int y;`) does not end the line: code on
        both sides of it shares the lines it takes."""
        src, root = self.parser.source_bytes, self.parser.tree.root_node
        pos = src.find(b"\n", max(end - 1, 0), start)
        while pos != -1:
            node = root.descendant_for_byte_range(pos, pos + 1)
            if node is None or "comment" not in node.type or node.start_byte < end:
                return False
            pos = src.find(b"\n", node.end_byte, start)
        return True

    @staticmethod
    def _is_separator(node) -> bool:
        """Whether `node` is a `;` or `,` between statements or entries
        (_SEPARATORS), including the `;` that JS/TS parse as an
        empty_statement of its own (`class A {};`)."""
        return node is not None and (
            (node.type in _SEPARATORS and not node.is_named) or node.type == "empty_statement"
        )

    def _line_sharing(self, first, last) -> tuple[bool, object, bool]:
        """
        How the symbol first..last (_symbol_unit) shares its lines with other
        code, as (before, separator, after): whether code comes before it on
        its first line; the `;` or `,` that ends it on its last line, if it
        has one (None otherwise); and whether code follows it, and that
        separator, on its last line. Whitespace and comments are not code. A
        whole-symbol edit takes the lines of a symbol that shares neither;
        config files are always edited by lines.
        """
        if self.parser.ext in _CONFIG_EXTS:
            return False, None, False

        def neighbour(node, forward: bool):
            # The code next to `node` in the file, comments skipped.
            while node is not None:
                sibling = node.next_sibling if forward else node.prev_sibling
                while sibling is not None and "comment" in sibling.type:
                    sibling = sibling.next_sibling if forward else sibling.prev_sibling
                if sibling is not None:
                    return sibling
                node = node.parent
            return None

        prev = neighbour(first, False)
        before = prev is not None and self._same_line(prev.end_byte, first.start_byte)
        separator = last.next_sibling
        if not (
            self._is_separator(separator)
            and not self.parser.source_bytes[last.end_byte : separator.start_byte].strip()
        ):
            separator = None
        end = last if separator is None else separator
        nxt = neighbour(end, True)
        after = nxt is not None and self._same_line(end.end_byte, nxt.start_byte)
        return before, separator, after

    def _line_starts_with_sibling(self, node) -> bool:
        """Whether the code that starts the first line of `node` is `node`
        or a sibling of it, rather than the code `node` is part of (the
        header of a one-line Python class, a `{`)."""
        row = node.start_point[0]
        line = self.lines[row]
        column = len(line[: len(line) - len(line.lstrip())].encode("utf-8"))
        start = self.parser.tree.root_node.descendant_for_point_range((row, column), (row, column))
        while start is not None and start.parent != node.parent:
            start = start.parent
        return start is not None and start.is_named and "comment" not in start.type

    def _comment_on_line(self, first):
        """The first of the comments that come before the symbol starting
        with `first` on its first line, where no code comes before it
        (`/** @type {X} */ let x;`, or a block comment that began on a line
        above, `/* a\\n b */ let x;`), or None when only spaces and tabs
        do."""
        if self._starts_line(first.start_byte):
            return None
        src = self.parser.source_bytes
        pos = src.rfind(b"\n", 0, first.start_byte) + 1
        while src[pos : pos + 1] in (b" ", b"\t"):
            pos += 1
        node = self.parser.tree.root_node.descendant_for_byte_range(pos, pos + 1)
        return node if node is not None and "comment" in node.type and node.end_byte <= first.start_byte else None

    def _callable(self, node, target: str):
        """
        The function that `node`, found for `target`, defines: the
        function_definition inside a Python decorated_definition, the arrow
        function, function expression or generator a JS/TS `const`/`let`/`var`
        binds to the target's name (`const f = () => {}`), the func literal
        a Go `var` gives it (`var f = func() {}`), else node itself.
        """
        if node.type == "decorated_definition":
            return next((c for c in node.named_children if c.type == "function_definition"), node)
        leaf = self.parser.target_leaf(target)
        bound = self.parser.js_bound_function(node, leaf)
        if bound is None:
            bound = self.parser.go_bound_function(node, leaf)
        return bound if bound is not None else node

    def _declares_c_function(self, node, target: str) -> bool:
        """Whether `node`, found for `target`, is a C/C++ declaration that
        declares the target as a function without a body: a prototype
        (`int f(int);`) or a method declared in its class (`int g();`,
        `~A();`, `operator bool() const;`)."""
        if self.parser.ext not in C_EXTS + CPP_EXTS or node.type not in ("declaration", "field_declaration"):
            return False
        name = self.parser.declared_name(node, self.parser.target_leaf(target))
        return name is not None and self.parser.c_declares_function(name)

    def _refuse_config(self, tool: str, target: str, instead: str) -> None:
        """
        Refuse `tool`, an edit of a whole symbol of a source file
        (replace_function, delete_symbol, insert_sibling), in a JSON, YAML or
        TOML file, where a target is a key path and read_symbol reads its
        value: `instead` names the key tool that makes the edit there.
        """
        ext = self.parser.ext
        if ext in _CONFIG_EXTS:
            raise ApplierError(
                f"{tool} is for symbols of source files, not the keys of a {ext} file: use {instead}"
            )

    def replace_function(self, target: str, content: str) -> str:
        """
        Replace the whole symbol `target` (decorators, a JS/TS `export` and a
        C++ `template <...>` header included, see _symbol_span, and the code
        it ends, see _symbol_unit) with content: the lines it takes up,
        re-indented to its own (a `;` or `,` after it on its last line kept,
        and a comment after it there, unless the content ends with one), or,
        when it shares a line with other code (`function a() {} function
        b() {}`) or a comment comes before it on its first line (`/**
        @type {X} */ let x;`), only its own text (_replace_inline). Content
        in the shape read_symbol shows the symbol in, the later lines at
        their file indentation, goes in as it is (_from_read_shape), so
        replace_function(t, read_symbol(t)) leaves the file as it was. A
        name declared together with others (`int a = 1, b = 2;`) has their
        declaration replaced, and content that drops them is refused
        (_check_declared_with). A comment that the JS/TS grammar puts inside
        the symbol after its code (`function f() {} // f`) is a comment
        after it (_code_end). In a JSON, YAML or TOML file, whose targets
        are keys, it is refused for replace_value (_refuse_config).
        """
        self._refuse_config(
            "replace_function",
            target,
            f"replace_value to change the value of '{target}', add_key to add a key, or delete_key to remove one",
        )
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        # line indexing is 0-based; decorators, a JS/TS `export` and a C++
        # `template <...>` are part of the definition (see _symbol_span and
        # _symbol_unit).
        first, last = self._symbol_unit(node)
        before, separator, after = self._line_sharing(first, last)
        others = self._declared_with(node, target)
        # A JS/TS class field's `;` goes when the content is a method.
        drop = self._field_separator_goes(node, separator, content)
        # A comment before the symbol on its first line (`/** @type {X} */
        # let x;`) is no part of it, and stays there as code would.
        if before or after or not self._starts_line(first.start_byte):
            return self._replace_inline(target, first, last, separator, content, others, drop)
        start_line = first.start_point[0]
        end_line = self._last_row(last) + 1

        original_indent = self._get_indent(self.lines[start_line])
        content_lines = _content_lines(content)
        if original_indent:
            # At column 0 read_symbol's shape is the relative and the absolute
            # one too, so the content goes in as written.
            content_lines = self._from_read_shape(content_lines, original_indent)
        content_lines = self._tabbed(content_lines, original_indent, range(start_line, end_line))
        if content_lines and self._get_indent(content_lines[0]) != original_indent:
            content_lines = self._reindent(content_lines, original_indent)
        # The `;` or `,` after the symbol on its last line (JS's `class A {};`)
        # is not part of it, so it stays unless the content ends with it.
        code = [i for i, line in enumerate(content_lines) if line.strip()]
        if separator is not None and code and separator.start_point[0] == last.end_point[0] and not drop:
            mark = self.parser.node_text(separator)
            if not content_lines[code[-1]].rstrip().endswith(mark):
                content_lines[code[-1]] = content_lines[code[-1]].rstrip() + mark
        # Nor is a comment after it on that line (`int x;  // the x`), which
        # stays after the content unless the content ends with a comment.
        end = separator if separator is not None and separator.start_point[0] == last.end_point[0] else last
        trailing, trailing_row = self._trailing_comment(end)
        end_line = max(end_line, trailing_row + 1)
        if trailing and code and not self._ends_with_comment(content_lines):
            first_line, *more = trailing.split("\n")
            content_lines[code[-1]] = content_lines[code[-1]].rstrip() + first_line
            content_lines[code[-1] + 1 : code[-1] + 1] = more

        lines = self.lines[:start_line] + content_lines + self.lines[end_line:]
        self._check_declared_with(target, others, "\n".join(lines).encode("utf-8"))
        self.lines = lines
        return self._save()

    def _field_separator_goes(self, node, separator, content: str) -> bool:
        """Whether replace_function drops `separator`, the `;` after `node`,
        for `content`: when `node` is a JS/TS class field, whose `;`
        read_symbol shows as its own, and the content ends with a member
        that is no field (a method, `k() {}`), which takes none."""
        if (
            self.parser.ext not in _JS_EXTS
            or node.type not in ("field_definition", "public_field_definition")
            or separator is None
            or separator.type != ";"
        ):
            return False
        root = self.parser.parse(("class _ {\n" + content + "\n}").encode("utf-8")).root_node
        body = root.named_children[0].child_by_field_name("body") if root.named_children else None
        members = [c for c in body.named_children if "comment" not in c.type] if body is not None else []
        return bool(members) and members[-1].type not in ("field_definition", "public_field_definition")

    def _trailing_comment(self, node) -> tuple[str, int]:
        """The comments after `node` on the line it ends on, with the spaces
        before them (`  // the x` after `int x;`), and the line the last of
        them ends on, which a block comment may take past that line (`int
        x; /* ... */` over two lines); ('', that line) when there are none,
        or code follows them. Config files have none. The comments that the
        JS/TS grammar puts inside `node` after its code count (_code_end)."""
        row = self._last_row(node)
        if self.parser.ext in _CONFIG_EXTS or row != node.end_point[0]:
            return "", row
        src, root = self.parser.source_bytes, self.parser.tree.root_node
        start = self._code_end(node)
        last = src.count(b"\n", 0, start)
        pos, end = start, src.find(b"\n", start)
        end = len(src) if end < 0 else end
        while pos < end:
            if src[pos : pos + 1] in (b" ", b"\t"):
                pos += 1
                continue
            found = root.descendant_for_byte_range(pos, pos + 1)
            if found is None or "comment" not in found.type:
                return "", row
            pos = max(found.end_byte, pos + 1)
            if found.end_point[0] > last:
                last = found.end_point[0]
                end = src.find(b"\n", pos)
                end = len(src) if end < 0 else end
        return src[start:end].decode("utf-8").rstrip(), last

    def _code_end(self, node) -> int:
        """
        The byte where the code of `node` ends: its end, but in JS and TS
        before the comments that the grammar puts last inside it, after its
        code. tree-sitter-javascript makes a comment after a function's or a
        namespace's `}` on its line part of the function's body, and one
        after a class or after a declaration with no `;` part of that node
        (`function f() {} // f`, `const x = 1 // x`); like a comment after
        a symbol in the other languages, it is no part of the symbol
        (read_symbol), and stays after it (_trailing_comment).
        """
        if self.parser.ext not in _JS_EXTS:
            return node.end_byte
        end = node
        while end.child_count:
            code = [c for c in end.children if "comment" not in c.type]
            if not code:
                break
            end = code[-1]
        return end.end_byte

    def _ends_with_comment(self, lines: list[str]) -> bool:
        """Whether the last line of code of the content `lines`, at its file
        indentation, ends with a comment (Python's dedented by its first
        line's indentation first, as in _literal_rows)."""
        rows = [i for i, line in enumerate(lines) if line.strip()]
        if not rows:
            return False
        if self.parser.ext == ".py":
            old = self._get_indent(lines[0])
            lines = [line[len(old) :] if line.startswith(old) else line for line in lines]
        row = rows[-1]
        column = len(lines[row].rstrip().encode("utf-8")) - 1
        root = self.parser.parse("\n".join(lines).encode("utf-8")).root_node
        node = root.descendant_for_point_range((row, column), (row, column))
        return node is not None and "comment" in node.type

    def _replace_inline(
        self, target: str, first, last, separator, content: str, others: list[str], drop: bool = False
    ) -> str:
        """
        replace_function for a symbol that shares a line with other code:
        its text, first..last, is replaced, and the code around it on its
        lines stays. The content goes in where the symbol started, without
        blank lines around it or a final line break, its first line's
        indentation dropped and the lines after it re-indented with it to
        the indentation of the symbol's line, or of the line where a block
        comment that ends before the symbol on its line starts (content in
        read_symbol's shape and absolute content keep theirs, as in
        replace_function). The `;`
        or `,` after the symbol (`separator`, or None) is replaced too when
        the content ends with it, as read_symbol shows a `;`, and stays
        otherwise, unless `drop` (_field_separator_goes). Content that ends
        with a line comment is refused when
        code follows the symbol on its line, and so is content that drops
        `others`, the names declared together with the target
        (_check_declared_with).
        """
        lines = _content_lines(content)
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        # The indentation of the symbol's line, or of the line a block
        # comment that ends before it there starts on (_indent_row).
        indent = self._get_indent(self.lines[self._indent_row(first)])
        if indent:
            lines = self._from_read_shape(lines, indent)
        lines = self._tabbed(lines, indent, range(first.start_point[0], last.end_point[0] + 1))
        if lines:
            if self._get_indent(lines[0]) != indent:
                lines = self._reindent(lines, indent)
            if lines[0].startswith(indent):
                lines[0] = lines[0][len(indent) :]
        text = "\n".join(lines).rstrip(" \t").encode("utf-8")
        src = self.parser.source_bytes
        end = self._code_end(last)
        if separator is not None and (drop or text.endswith(src[separator.start_byte : separator.end_byte])):
            end = separator.end_byte
        new = src[: first.start_byte] + text + src[end:]
        # The code after the symbol on its line, comments skipped, must stay
        # code: content ending in a `#` or `//` comment would take it in.
        root, pos = self.parser.tree.root_node, end
        while pos < len(src) and src[pos : pos + 1] != b"\n":
            if src[pos : pos + 1] in (b" ", b"\t", b"\r"):
                pos += 1
                continue
            node = root.descendant_for_byte_range(pos, pos + 1)
            if "comment" in node.type:
                pos = max(node.end_byte, pos + 1)
            else:
                moved = pos + len(new) - len(src)
                node = self.parser.parse(new).root_node.descendant_for_byte_range(moved, moved + 1)
                while node is not None and "comment" not in node.type:
                    node = node.parent
                if node is not None and node.start_byte < moved:
                    raise ApplierError(
                        f"The content ends with a comment, and the code after '{target}' on its "
                        "line would become part of it. Leave the comment out, or make this edit "
                        "with your normal edit tool."
                    )
                break
        self._check_declared_with(target, others, new)
        self._write_bytes(new, (first.start_byte, end))
        return "Update successful"

    def replace_value(self, target: str, content: str) -> str:
        """
        Replace the value of `target`: a config key's value, a Python dict
        or JS/TS object entry's (_find_entry_value), a closure in an object
        or composite literal, or the value of a source file's variable,
        constant or field, which a name declared without one gets
        (_declared_value).
        """
        node = self.parser.find_node_by_name(target)
        prefix = ""
        entry = node is None
        if not node:
            try:
                found = self._find_entry_value(target)
            except ApplierError as e:
                raise ApplierError(f"Target '{target}' not found ({e})") from e
            if found is not None:
                node, prefix = found
        if not node and self.parser.ext in (".yml", ".yaml"):
            # A key written with no value (`key:`) has no value node.
            pair = self.parser.find_yaml_pair(self.parser.tree.root_node, target)
            if pair is not None:
                return self._fill_yaml_value(pair, content.lstrip("\n"))
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
        start, end = node.start_byte, node.end_byte
        if not entry and ext not in _CONFIG_EXTS:
            # A variable, constant or field of a source file: its value
            # alone, not the declaration that find_node_by_name returns.
            start, end, prefix = self._declared_value(node, target)
        content_bytes = (prefix + content).encode("utf-8")

        new_bytes = source_bytes[:start] + content_bytes + source_bytes[end:]
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

    def _declared_value(self, node, target: str) -> tuple[int, int, str]:
        """
        For replace_value on `node`, which the source-file `target` found:
        the bytes of the value to replace, and the text to put before the
        new one. The value of a variable, constant or field is what follows
        its `=` (that of the target's own declarator in `let a = 1, b = 2;`,
        the k-th expression of a Go `var a, b = 1, 2` for its k-th name), of
        a C/C++ macro its replacement text, and of a C++ direct
        initialization (`int x(1);`, `int x{1};`) what is inside its
        parentheses or braces; a closure that a key path found
        (`app.handler`) is a value itself. A name declared without a value
        gets one where it can have one alone: the range is empty, after its
        name, type and C++ bit-field width, with ` = ` (for a macro, a
        space) before the content.

        Refused, with ApplierError: a symbol that is no variable, constant
        or field (a function, class or type), a name that gets one value
        with others (`a = b = 1`, `var a, b = f()`, `auto [a, b] = p;`), and
        one without a value that cannot get one alone (`var a, b int`, an
        `extern` or TS `declare` declaration, an abstract field, a field of
        a C struct, a Go constant that the constants after it repeat, see
        _repeating_constants). A C variable that its struct's name targets
        with it (`struct S {...} S = {0};`) has the declaration's value.
        """
        ext = self.parser.ext
        if node.type in JS_FUNCTION_VALUES + ("func_literal",):
            return node.start_byte, node.end_byte, ""
        shared = ApplierError(
            f"'{target}' gets its value together with other names, so it has none of its own to replace; "
            "rewrite the declaration with replace_function"
        )

        def cannot(reason: str) -> ApplierError:
            return ApplierError(f"'{target}' has no value, and {reason}")

        if (node.type == "expression_statement" and ext == ".py") or (node.type == "assignment" and ext == ".rb"):
            assignment = node.named_children[0] if node.type == "expression_statement" else node
            value = assignment.child_by_field_name("right")
            if value is None:
                # `x: int`
                return assignment.end_byte, assignment.end_byte, " = "
            if value.type in ("assignment", "augmented_assignment", "operator_assignment"):
                raise shared
            # The bodies of the heredocs a Ruby value opens (`X = <<~EOS`)
            # are part of it.
            return value.start_byte, max(value.end_byte, self._symbol_span(node)[1].end_byte), ""
        leaf = self.parser.target_leaf(target)
        if node.type in ("lexical_declaration", "variable_declaration") and ext in _JS_EXTS:
            declarator = self.parser.declared_name(node, leaf).parent
            value = declarator.child_by_field_name("value")
            if value is not None:
                return value.start_byte, value.end_byte, ""
            if self._ambient(node):
                raise cannot("a `declare` declaration cannot have one")
            return self._added_value(declarator)
        if node.type in ("field_definition", "public_field_definition"):
            value = node.child_by_field_name("value")
            if value is not None:
                return value.start_byte, value.end_byte, ""
            if any(c.type == "abstract" for c in node.children):
                raise cannot("an abstract field cannot have one")
            if any(c.type == "declare" for c in node.children) or self._ambient(node):
                raise cannot("a `declare` declaration cannot have one")
            return self._added_value(node)
        if node.type in ("var_spec", "const_spec") and ext == ".go":
            names = [c for c in node.children_by_field_name("name") if c.type == "identifier"]
            k = next(i for i, n in enumerate(names) if self.parser.node_text(n) == leaf)
            value = node.child_by_field_name("value")
            if value is None:
                if len(names) > 1:
                    raise ApplierError(
                        f"'{target}' is declared with other names and no values, and a value for it needs one "
                        "for each of them; rewrite the declaration with replace_function"
                    )
                repeating = self._repeating_constants(node)
                if repeating:
                    # They repeat the expression this one repeats now.
                    names = ", ".join(f"'{name}'" for name in repeating)
                    one = len(repeating) == 1
                    raise ApplierError(
                        f"'{target}' has no value of its own: it repeats the expression of the constant above it, "
                        f"and so {'does' if one else 'do'} {names} below it, which a value for '{target}' would "
                        f"change too; give {names} {'its own value' if one else 'their own values'} first"
                    )
                return node.end_byte, node.end_byte, " = "
            values = [c for c in value.named_children if "comment" not in c.type]
            if len(values) != len(names):
                raise shared
            return values[k].start_byte, values[k].end_byte, ""
        if node.type in ("field_declaration", "constant_declaration") and ext == ".java":
            declarator = self.parser.declared_name(node, leaf).parent
            value = declarator.child_by_field_name("value")
            if value is not None:
                return value.start_byte, value.end_byte, ""
            return declarator.end_byte, declarator.end_byte, " = "
        if ext in C_EXTS + CPP_EXTS:
            unit = node.parent
            if (
                node.type in _C_TYPE_SPECIFIERS
                and self.parser.parse_target(target).keyword is None
                and unit.type in ("declaration", "field_declaration")
                and unit.child_by_field_name("type") == node
                and self.parser.declared_name(unit, leaf) is not None
            ):
                # `struct S {...} S = {0};`: the variable the name targets
                # with its struct.
                node = unit
            if node.type in ("preproc_def", "preproc_function_def"):
                value = node.child_by_field_name("value")
                if value is not None:
                    return value.start_byte, self._macro_value_end(value), ""
                after = node.child_by_field_name("parameters") or node.child_by_field_name("name")
                return after.end_byte, after.end_byte, " "
            if node.type in ("declaration", "field_declaration") and not self._declares_c_function(node, target):
                return self._c_declared_value(node, target, shared, cannot)
        raise ApplierError(
            f"'{target}' is {self._value_kind(node, target)}, which has no value (replace_value is for keys and "
            "for the values of variables, constants and fields); rewrite it with replace_function"
        )

    def _repeating_constants(self, spec) -> list[str]:
        """For a Go const spec without a value in a `const (...)` group, the
        names of the specs right after it that have none either: Go gives
        them the expression the one before them repeats (`B` and `C` of `A =
        iota`, `B`, `C`), so a value for `spec` would be theirs too."""
        names = []
        sibling = spec.next_named_sibling
        while sibling is not None and (sibling.type == "comment" or sibling.type == "const_spec"):
            if sibling.type == "const_spec":
                if sibling.child_by_field_name("value") is not None:
                    break
                names.extend(self.parser.node_text(n) for n in sibling.children_by_field_name("name"))
            sibling = sibling.next_named_sibling
        return names

    def _added_value(self, node) -> tuple[int, int, str]:
        """_declared_value for a JS/TS declarator or class field without a
        value: the empty range after its code, with ` = ` before the
        content. A TS definite assignment `!`, which a declaration with a
        value cannot have, goes (`x!: number` gets `x: number = ...`)."""
        end = self._code_end(node)
        bang = next((c for c in node.children if c.type == "!"), None)
        if bang is None:
            return end, end, " = "
        return bang.start_byte, end, self.parser.source_bytes[bang.end_byte : end].decode("utf-8") + " = "

    def _c_declared_value(self, node, target: str, shared: ApplierError, cannot) -> tuple[int, int, str]:
        """_declared_value for a C/C++ variable or field: the value of the
        declarator of `node` that declares the target, or the empty range
        after that declarator (and a C++ bit-field's width) where it has
        none. A C++ field's declarators and default values are children of
        the field itself, in turn."""
        name = self.parser.declared_name(node, self.parser.target_leaf(target))
        declarator = name
        while declarator.parent is not None and declarator.parent != node:
            declarator = declarator.parent
        if node.type == "declaration":
            if declarator.type == "init_declarator":
                binding = declarator.child_by_field_name("declarator")
                if binding is not None and binding.type == "structured_binding_declarator":
                    raise shared
                direct = not any(c.type == "=" for c in declarator.children)
                return self._initializer(declarator.child_by_field_name("value"), direct)
            if any(c.type == "storage_class_specifier" and self.parser.node_text(c) == "extern" for c in node.children):
                raise cannot("an `extern` declaration takes none: the variable's definition holds its value")
            return declarator.end_byte, declarator.end_byte, " = "
        if self.parser.ext in C_EXTS:
            raise cannot("a field of a C struct cannot have one")
        value, direct, end = None, True, declarator.end_byte
        i = next(i for i, c in enumerate(node.children) if c == declarator) + 1
        while i < len(node.children) and node.children[i].type not in (",", ";"):
            child = node.children[i]
            if node.field_name_for_child(i) == "default_value":
                value = child
            elif child.type == "=":
                direct = False
            elif "comment" not in child.type:
                # `int f : 3`
                end = child.end_byte
            i += 1
        if value is not None:
            return self._initializer(value, direct)
        return end, end, " = "

    def _initializer(self, value, direct: bool) -> tuple[int, int, str]:
        """The range of a C/C++ initializer `value` that replace_value
        replaces: all of it after an `=`, and what is inside the
        parentheses or braces of a direct initialization (`x(1)`, `x{1}`),
        without the spaces around it there."""
        if not direct or value.type not in ("argument_list", "initializer_list"):
            return value.start_byte, value.end_byte, ""
        start, end = value.start_byte + 1, value.end_byte - 1
        inner = self.parser.source_bytes[start:end]
        if inner.strip():
            start += len(inner) - len(inner.lstrip())
            end -= len(inner) - len(inner.rstrip())
        return start, end, ""

    def _macro_value_end(self, value) -> int:
        """Where the replacement text of a C/C++ macro ends: before the
        spaces and a comment that the grammar ends its `preproc_arg` with
        (`#define N 3 // three`), a `//` or `/*` inside a string or
        character literal not counting."""
        text = self.parser.source_bytes[value.start_byte : value.end_byte]
        quote, i = None, 0
        while i < len(text):
            char = text[i : i + 1]
            if quote:
                if char == b"\\":
                    i += 1
                elif char == quote:
                    quote = None
            elif char in (b'"', b"'"):
                quote = char
            elif text[i : i + 2] in (b"//", b"/*"):
                text = text[:i]
                break
            i += 1
        return value.start_byte + len(text.rstrip())

    @staticmethod
    def _ambient(node) -> bool:
        """Whether a TS declaration is inside a `declare` (ambient)
        declaration, which gives no values: `declare let x: number;`, or a
        member of `declare namespace N { ... }`."""
        parent = node.parent
        while parent is not None:
            if parent.type == "ambient_declaration":
                return True
            parent = parent.parent
        return False

    def _value_kind(self, node, target: str) -> str:
        """What replace_value calls `node`, found for `target`, a symbol
        that has no value, with its article: a function, a class, struct,
        union, enum, interface, namespace or Ruby module, or what
        _symbol_kind calls a symbol of another kind (a type alias, a Go
        type definition)."""
        if node.type == "decorated_definition":
            node = node.child_by_field_name("definition") or node
        _, functions, _ = self.parser.target_types()
        if node.type in functions or node.type in _BODILESS_FUNCTIONS or self._declares_c_function(node, target):
            return "a function"
        if node.type in _C_TYPE_SPECIFIERS and node.child_by_field_name("body") is None:
            return self._symbol_kind(node, target)
        kinds = {
            "class_definition": "a class",
            "class_declaration": "a class",
            "abstract_class_declaration": "a class",
            "class_specifier": "a class",
            "class": "a class",
            "record_declaration": "a class",
            "struct_specifier": "a struct",
            "union_specifier": "a union",
            "enum_specifier": "an enum",
            "enum_declaration": "an enum",
            "interface_declaration": "an interface",
            "namespace_definition": "a namespace",
            "internal_module": "a namespace",
            "module": "a module" if self.parser.ext == ".rb" else "a namespace",
        }
        return kinds.get(node.type) or self._symbol_kind(node, target)

    def replace_function_body(self, target: str, content: str) -> str:
        """
        Replace the body of a function, keeping its signature: the lines
        between its `{` and `}` lines, or the lines of a Python or Ruby body,
        with content re-indented to the body's indentation, that of its first
        line of code or comment; an empty body (`{` and `}` on lines of their
        own, a Ruby method with nothing between its signature and its `end`)
        is one indentation unit deeper than the line the function starts on.
        A body that shares a line with its signature or braces
        (`function f() { return 1; }`, `def f(): return 1`) is rebuilt over
        lines of its own (_rebuild_body). The body of a Ruby method with
        rescue, else or ensure clauses is the code before them, and they
        stay, unless the content has clauses of its own (_ruby_clause).
        """
        func_node, block_node = self._get_function_body_node(target, empty_ok=True)
        if block_node is None:
            # An empty Ruby method: the lines between its signature and its
            # `end`, or, on one line (`def h; end`), rebuilt.
            open_row, end_row = self._empty_method_rows(func_node)
            if open_row == end_row:
                return self._rebuild_body(func_node, None, content)
            start_line, end_line = open_row + 1, end_row
        elif self._body_shares_line(func_node, block_node):
            return self._rebuild_body(func_node, block_node, content)
        elif self.parser.ext == ".py" or self.parser.ext in (".rb",):
            # Python and Ruby use indented body lines between def/class and end markers.
            start_line = block_node.start_point[0]
            end_line = block_node.end_point[0] + 1
        else:
            # JS/TS/C/C++/Go/Java: body is `{ ... }` -- skip the opening brace line.
            start_line = block_node.start_point[0] + 1
            end_line = block_node.end_point[0]
        code_end = end_line
        clause = self._ruby_clause(block_node)
        if clause is not None:
            # A Ruby method's rescue, else and ensure clauses stay, unless the
            # content has clauses of its own: the body is the code before
            # them, or the lines between the signature and them when there is
            # none, as in an empty method. A clause on the line of that code
            # moves to a line of its own (_rebuild_body).
            if not self._starts_line(clause.start_byte):
                return self._rebuild_body(func_node, block_node, content)
            before = [c for c in block_node.named_children if c.end_byte <= clause.start_byte]
            if all("comment" in c.type for c in before):
                start_line = self.parser.source_bytes.count(b"\n", 0, self._body_opening(func_node, block_node)) + 1
                code_end = clause.start_point[0]
            else:
                code_end = self._last_row(before[-1]) + 1
            if self._ruby_clause(self._ruby_method_body(content)) is None:
                end_line = code_end

        # The body's indentation is that of its first line with code or a
        # comment; an empty body (`{` and `}` on lines of their own, maybe
        # with blank lines between them) is one level deeper than the line
        # the function starts on.
        first = next((line for line in self.lines[start_line:code_end] if line.strip()), None)
        if first is not None:
            target_indent = self._get_indent(first)
        else:
            unit = self._indent_unit({".py": "    ", ".java": "    ", ".go": "\t"}.get(self.parser.ext, "  "))
            target_indent = self._get_indent(self.lines[func_node.start_point[0]]) + unit

        content_lines = self._reindent(self._tabbed(_content_lines(content), target_indent), target_indent)

        self.lines = self.lines[:start_line] + content_lines + self.lines[end_line:]
        return self._save()

    def _body_opening(self, func_node, body) -> int:
        """The byte where the body of func_node opens: after its `{`, after
        the `:` of a Python def or class, or after the name and parameters of
        a Ruby method (not a `;` after them), also of an empty one, whose
        body is None (_empty_method)."""
        ext = self.parser.ext
        if ext not in (".py", ".rb"):
            return body.start_byte + 1
        limit = body.start_byte if body is not None else func_node.children[-1].start_byte
        head = [
            c for c in func_node.children
            if c.end_byte <= limit and c.type != ";" and "comment" not in c.type
        ]
        if ext == ".py":
            head = [c for c in head if c.type == ":"]
        return head[-1].end_byte if head else limit

    def _body_shares_line(self, func_node, body) -> bool:
        """
        Whether the body of func_node shares a line with its signature or
        braces, for replace_function_body: its first statement is on the line
        where it opens (_body_opening), its last one on the line of its `}`
        (a Ruby body ends on the line of its `end`), or a braced body is on
        one line. Comments are no statements.
        """
        stmts = [c for c in body.named_children if "comment" not in c.type]
        if len(stmts) == 1 and stmts[0].type == "statement_list":
            stmts = [c for c in stmts[0].named_children if "comment" not in c.type]
        open_row = self.parser.source_bytes.count(b"\n", 0, self._body_opening(func_node, body))
        if stmts and stmts[0].start_point[0] == open_row:
            return True
        ext = self.parser.ext
        if ext == ".py":
            return False
        if ext == ".rb":
            end = func_node.children[-1]
            return bool(stmts) and end.type == "end" and body.end_point[0] == end.start_point[0]
        return body.start_point[0] == body.end_point[0] or bool(stmts and stmts[-1].end_point[0] == body.end_point[0])

    def _rebuild_body(self, func_node, body, content: str) -> str:
        """
        replace_function_body for a body that shares a line with its
        signature or braces: what is between where it opens (_body_opening)
        and its `}` or Ruby `end` becomes the content, on lines of its own one
        indentation level deeper than the line the function starts on, and
        the `}` or `end` goes on a line of its own at that line's indentation.
        Comments that follow the opening on its line, before any statement,
        stay there. A Python body ends with its last statement, and the
        comments after it on its line stay on the def's line, after the `:`
        (`def b():  # old`). A Ruby method's rescue, else and ensure clauses
        stay, from a line of their own on, unless the content has its own,
        and are rebuilt over lines of their own when they share lines
        (_ruby_clause_lines).
        """
        ext = self.parser.ext
        src = self.parser.source_bytes
        base = self._get_indent(self.lines[func_node.start_point[0]])
        unit = self._indent_unit({".py": "    ", ".java": "    ", ".go": "\t"}.get(ext, "  "))
        lines = _content_lines(content)
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        text = "\n".join(self._reindent(self._tabbed(lines, base + unit), base + unit)).encode("utf-8")
        opening = self._body_opening(func_node, body)
        if ext == ".py":
            # The comments after the last statement on its line (`def b():
            # pass  # old`) stay on the def's line, after the `:`.
            last = [c for c in body.children if "comment" not in c.type][-1]
            tail = [
                c
                for c in body.children
                if "comment" in c.type and c.start_byte >= last.end_byte and c.start_point[0] == last.end_point[0]
            ]
            end, comment = last.end_byte, b""
            if tail:
                start, end = tail[0].start_byte, tail[-1].end_byte
                while start > last.end_byte and src[start - 1 : start] in (b" ", b"\t"):
                    start -= 1
                comment = src[start:end]
            self._write_bytes(src[:opening] + comment + b"\n" + text + src[end:])
            return "Update successful"
        close = func_node.children[-1].start_byte if ext == ".rb" else self._code_end(body) - 1
        clause = self._ruby_clause(body)
        if clause is not None and self._ruby_clause(self._ruby_method_body(content)) is None:
            # A Ruby method's rescue, else and ensure clauses stay, from a
            # line of their own on (see replace_function_body).
            close = clause.start_byte
        line_end = src.find(b"\n", opening)
        # An empty Ruby method on one line has no body node (_empty_method).
        code = next((c for c in body.named_children if "comment" not in c.type), None) if body is not None else None
        if 0 <= line_end < close and (code is None or code.start_byte > line_end):
            opening = line_end
        tail = src[close:]
        if clause is not None and close == clause.start_byte:
            # Clauses that share lines with their code or the `end` are
            # rebuilt over lines of their own too (_ruby_clause_lines).
            tail = self._ruby_clause_lines(func_node, body, base, unit) or tail
        self._write_bytes(src[:opening] + b"\n" + text + b"\n" + base.encode("utf-8") + tail)
        return "Update successful"

    def add_method(self, class_target: str, content: str) -> str:
        """
        Add a new method to a class. Placement varies by language:
          - Python/JS/TS/Java/C++/Ruby: inside the class body, after its
                last member (see _insert_member for indentation and spacing;
                a Java enum gets the `;` its constants need before it), but
                in C++ after the class's last method when an access label
                follows it, so that it gets its access (_section_method).
          - Go: as a top-level sibling immediately after the type declaration
                (Go methods are not lexically inside struct definitions).
        """
        node = self._class_target(class_target)
        node = self._typedef_struct(node)

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
            # gofmt indents with tabs.
            content_lines = self._tabbed(_content_lines(content), "", range(target_node.start_point[0], insert_line))
            # A blank line between the method and the code on each side.
            sep_before = [""] if insert_line - 1 >= 0 and insert_line - 1 < len(self.lines) and self.lines[insert_line - 1].strip() else []
            sep_after = [""] if insert_line < len(self.lines) and self.lines[insert_line].strip() else []
            self.lines = self.lines[:insert_line] + sep_before + content_lines + sep_after + self.lines[insert_line:]
            return self._save()

        body = node.child_by_field_name("body")
        if body is None and self.parser.ext != ".rb":
            raise ApplierError(f"Could not find class body for '{class_target}'")
        return self._insert_member(class_target, node, body, content, at_end=True)

    def delete_symbol(self, target: str, include_leading_comments: bool = True) -> str:
        """
        Delete a function/class/method definition. By default also removes the
        contiguous leading comment block (Godoc, Javadoc, `#` comments, `//`
        comments, C-style `/* ... */` blocks or a Ruby `=begin` document)
        directly above the symbol -- pass `include_leading_comments=False` to
        keep that comment in place. A comment before the symbol on its first
        line (`/** @type {X} */ let x;`) goes with it too, or, kept, stays
        there on a line of its own. The comment lines right below the symbol
        that are indented deeper than it, which end its code, go with it
        (_rows_below). The blank lines that separated the symbol from its
        neighbours go with it (see _separator_lines). A symbol that shares a
        line with other code is cut out of it (_delete_inline). A name
        declared together with others (`int a, *b;`) is refused, as the
        declaration would go with them (_declared_with). In a JSON, YAML or
        TOML file it is refused for delete_key (_refuse_config).
        """
        self._refuse_config("delete_symbol", target, f"delete_key to remove '{target}' with its value")
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found")
        others = self._declared_with(node, target)
        if others:
            name = self.parser.target_leaf(target)
            quoted = [f"'{other}'" for other in others]
            listed = quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"
            raise ApplierError(
                f"'{name}' is declared together with {listed} in one declaration, so "
                f"delete_symbol would delete {'it' if len(others) == 1 else 'them'} too. Give "
                f"replace_function the declaration without '{name}' (read_symbol shows it), or "
                "make this edit with your normal edit tool."
            )

        # Decorators, a JS/TS `export` and a C++ `template <...>` go with the
        # symbol, and its leading comment is the one above them (see
        # _symbol_span and _symbol_unit).
        first, last = self._symbol_unit(node)
        before, separator, after = self._line_sharing(first, last)
        if before or after:
            return self._delete_inline(first, last, separator, before, after, include_leading_comments)
        start_line = first.start_point[0]
        end_line = self._rows_below(first, last, separator)

        # A comment before the symbol on its first line (`/** @type {X} */
        # let x;`) goes with it as one above it does, from its own first line
        # on; kept, it stays on a line of its own.
        comment = self._comment_on_line(first)
        if include_leading_comments:
            if comment is not None:
                start_line = comment.start_point[0]
            comment_range = self._find_leading_comment_range(start_line)
            if comment_range is not None:
                start_line = comment_range[0]
        elif comment is not None:
            src = self.parser.source_bytes
            line_start = src.rfind(b"\n", 0, first.start_byte) + 1
            self.lines[start_line] = src[line_start : first.start_byte].decode("utf-8").rstrip(" \t")
            start_line += 1

        start_line, end_line = self._separator_lines(first, last, start_line, end_line)
        self.lines = self.lines[:start_line] + self.lines[end_line:]
        return self._save()

    def _declared_with(self, node, target: str) -> list[str]:
        """
        The other names that the declaration holding `node`, found for
        `target`, declares: `a` for `b` of `int a, *b;`, `y` for `x` of a
        Java `int x, y;`, `b` for `a` of a JS `const a = 1, b = 2;` or a Go
        `var a, b = 1, 2`, and `y` for `x` of a C++ `auto [x, y] = p;`. []
        for a declaration of one name. A C/C++ class, struct, union or enum
        that a declaration defines counts as one of its names (`S` for `s`
        of `struct S {...} s;` and `s` for `S`, `N` for `Node` of `typedef
        struct N {...} Node;`), unless a typedef gives it its own name
        (`typedef struct Node {...} Node;`).
        """
        declaration = self._symbol_unit(node)[0] if node.type in _C_TYPE_SPECIFIERS else node
        names = [self.parser.symbol_name(n) for n in self.parser.declared_names(declaration)]
        tag = self._defined_tag(declaration)
        if tag is not None and tag not in names:
            names.insert(0, tag)
        if len(names) < 2:
            return []
        leaf = self.parser.target_leaf(target)
        own = self.parser.declared_name(declaration, leaf)
        name = self.parser.symbol_name(own) if own is not None else leaf
        if name in names:
            names.remove(name)
        return names

    def _defined_tag(self, declaration) -> str | None:
        """The name of the C/C++ class, struct, union or enum that the
        declaration, field or typedef `declaration` defines as its type, with
        a body (`S` of `struct S {...} s;`), or None."""
        if self.parser.ext not in C_EXTS + CPP_EXTS or declaration.type not in (
            "declaration",
            "field_declaration",
            "type_definition",
        ):
            return None
        kind = declaration.child_by_field_name("type")
        if kind is None or kind.type not in _C_TYPE_SPECIFIERS or kind.child_by_field_name("body") is None:
            return None
        name = kind.child_by_field_name("name")
        return self.parser.node_text(name) if name is not None else None

    def _check_declared_with(self, target: str, others: list[str], new_bytes: bytes) -> None:
        """
        Refuse replace_function on `target` when the file's text would
        become `new_bytes` without `others`, the names declared together
        with it (_declared_with): the whole declaration is replaced, so
        content that declares only the target (`int b = 3;` for `b` of `int
        a = 1, b = 2;`), or uses a struct it no longer defines (`struct S t;`
        for `s` of `struct S {...} s;`), would drop them without notice. A
        name counts as kept when it is still a target in its scope.
        """
        if not others:
            return
        # The others are in the target's container, its keyword and
        # parameter types not theirs.
        prefix = "".join(part + "." for part in self.parser.parse_target(target).parts[:-1])
        parser = self.parser
        saved = parser.tree, parser.source_bytes
        lost = []
        try:
            parser.tree, parser.source_bytes = parser.parse(new_bytes), new_bytes
            for other in others:
                try:
                    if parser.find_node_by_name(prefix + other) is None:
                        lost.append(other)
                except ApplierError:
                    pass
        finally:
            parser.tree, parser.source_bytes = saved
        if not lost:
            return
        name = self.parser.target_leaf(target)
        quoted = [f"'{other}'" for other in lost]
        listed = quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"
        raise ApplierError(
            f"'{name}' is declared together with {listed} in one declaration, which replace_function "
            f"replaces whole (read_symbol shows it), and the content would drop "
            f"{'it' if len(lost) == 1 else 'them'}. Keep {listed} in the content, or make this edit "
            "with your normal edit tool."
        )

    def _delete_inline(self, first, last, separator, before: bool, after: bool, include_leading_comments: bool) -> str:
        """
        delete_symbol for a symbol, first..last, that shares its first line
        (`before`) or its last line (`after`) with other code: its text is cut
        out of them, with the `;` or `,` that ends it (`separator`) and the
        spaces and tabs after it, so that the spaces that were before it are
        left between the code on both sides of it. A symbol that ends its
        line takes the rest of it (a comment there, as when deleting whole
        lines) and, if no separator of its own ends it (a C/C++ class's `;`
        is part of its span, see _symbol_span), the `;` or `,` before it that
        separated it from the code before (`x = 1; y = 2` loses `; y = 2`);
        so does a symbol that the `}` or `)` closing its container follows
        (`{ a: 1, b: 2 }` minus b is `{ a: 1 }`). A symbol that no code
        comes before on its line keeps the line's indentation for the code
        after it, and takes its leading comment and the comments before it
        on its line (_comment_on_line) with it unless
        include_leading_comments is False.
        """
        src = self.parser.source_bytes
        start = first.start_byte
        end = self._code_end(last) if separator is None else separator.end_byte
        # The `;` or `,` before the symbol goes with it when no separator of
        # its own parts it from what follows it: the rest of its line, or the
        # `}` or `)` closing the code it is part of.
        prev = first.prev_sibling
        following = last.next_sibling
        while following is not None and "comment" in following.type:
            following = following.next_sibling
        takes_prev = (
            separator is None
            and last.type not in _SEPARATORS
            and prev is not None
            and prev.type in _SEPARATORS
            and not prev.is_named
            and not src[prev.end_byte : start].strip()
            and (not after or following is None or not following.is_named)
        )
        if takes_prev:
            start = prev.start_byte
        if not after:
            line_end = src.find(b"\n", end)
            end = len(src) if line_end == -1 else line_end
        line_start = src.rfind(b"\n", 0, start) + 1
        cut = start
        if before:
            while start > line_start and src[start - 1 : start] in (b" ", b"\t"):
                start -= 1
        # Between the code on both sides stay the spaces that were before the
        # symbol, or, when it took the separator before it, those before the
        # code that closes it (`{ a: 1, b: 2 }` minus b is `{ a: 1 }`).
        gap = b""
        if after and not takes_prev:
            gap = src[start:cut]
            while src[end : end + 1] in (b" ", b"\t"):
                end += 1
        head = src[:start]
        if not before and include_leading_comments:
            # So do the comments before it on its line (_comment_on_line).
            row = first.start_point[0]
            comment = self._comment_on_line(first)
            if comment is not None:
                start, row = comment.start_byte, comment.start_point[0]
                line_start = src.rfind(b"\n", 0, start) + 1
                head = src[:start]
            comment_range = self._find_leading_comment_range(row)
            if comment_range is not None:
                # Whole comment lines go; the symbol's indentation stays.
                comment_start = sum(len(line.encode("utf-8")) + 1 for line in self.lines[: comment_range[0]])
                head = src[:comment_start] + src[line_start:start]
        self._write_bytes(head + gap + src[end:])
        return "Update successful"

    def _rows_below(self, first, last, separator) -> int:
        """
        The line after the last line of the symbol first..last (with the
        `;` or `,` that ends it, `separator`, or None), for the edits that
        take its lines or add lines below it (delete_symbol, insert_sibling
        "after"): after the line it ends on, a block comment after it there
        that goes on over lines (`int x; /* a\\n b */`), and the comment lines
        right below it that are indented deeper than its first line. Those
        end its code, as the Python grammar makes such comments the end of
        the body above them; a blank line, a line with code and a comment at
        the symbol's own indentation or less end them.
        """
        end = separator if separator is not None and separator.start_point[0] == last.end_point[0] else last
        row = max(self._last_row(last), self._trailing_comment(end)[1]) + 1
        indent = self._get_indent(self.lines[first.start_point[0]])
        src, root = self.parser.source_bytes, self.parser.tree.root_node
        while row < len(self.lines):
            line = self.lines[row]
            if not line.strip(" \t") or not self._indented_deeper(line, indent):
                break
            column = len(line[: len(line) - len(line.lstrip())].encode("utf-8"))
            node = root.descendant_for_point_range((row, column), (row, column))
            if node is None or "comment" not in node.type:
                break
            line_end = src.find(b"\n", node.end_byte)
            if src[node.end_byte : len(src) if line_end < 0 else line_end].strip():
                break
            row = node.end_point[0] + 1
        return row

    def _separator_lines(self, first, last, start_line: int, end_line: int) -> tuple[int, int]:
        """
        For delete_symbol: the lines [start_line, end_line) that the symbol
        spanning nodes first..last takes up, widened by the blank lines that
        separated it from its neighbours, so that the rest is spaced as the
        file spaces its symbols. A symbol that opens its file or body (no
        sibling above it; a C++ access label counts as an opening) takes the
        blank lines below it, so none are left at the top of the file or
        after the `{`; one that closes its body takes those above it, so
        none are left before the `}` and the next top-level symbol keeps its
        own separation; of a symbol between two others only the wider of
        its two gaps stays.
        """
        # Only spaces and tabs make a line blank: a form feed line (a Python
        # page break) is the file's text and stays.
        before = 0
        while start_line - before > 0 and not self.lines[start_line - before - 1].strip(" \t"):
            before += 1
        after = 0
        while end_line + after < len(self.lines) and not self.lines[end_line + after].strip(" \t"):
            after += 1
        # The node whose parent holds the symbol's siblings: past wrappers
        # that hold nothing else (a Go type_declaration around its one
        # type_spec), but not out of a class body.
        unit = first
        while (
            unit.parent is not None
            and unit.parent.parent is not None
            and unit.parent.type not in ("block", "body_statement")
            and unit.parent.start_point[0] >= first.start_point[0]
            and unit.parent.end_point[0] <= last.end_point[0]
        ):
            unit = unit.parent
        siblings = unit.parent.named_children if unit.parent is not None else []

        above = any(self._last_row(s) < start_line and s.type != "access_specifier" for s in siblings)
        below = any(s.start_point[0] >= end_line for s in siblings)
        if not above:
            end_line += after
        if not below:
            start_line -= before
        if above and below:
            if before >= after:
                end_line += after
            else:
                start_line -= before
        return start_line, end_line

    @staticmethod
    def _last_row(node) -> int:
        """The line `node` ends on. A node that ends with its line break (a
        C #include) ends at column 0 of the next line."""
        row, column = node.end_point
        return row - 1 if column == 0 and row > node.start_point[0] else row

    def _save(self) -> str:
        """
        Write self.lines back to the file. _split_lines dropped only the final
        newline, so adding it back rebuilds untouched lines exactly, blank
        lines at the end of the file included. An edit never leaves more of
        those than the file had, though: deleting the last symbol would
        otherwise strand the blank lines that separated it from the one
        before. The lines at either end that are still those read from the
        file (the same objects, which slicing self.lines keeps) are those
        the edit left alone, for _mixed_line_breaks.
        """
        lines = self.lines
        excess = _trailing_blank_lines(lines) - _trailing_blank_lines(
            _split_lines(self.parser.source_code)
        )
        if excess > 0:
            lines = lines[: len(lines) - excess]
        read = self._read_lines
        head = 0
        while head < min(len(lines), len(read)) and lines[head] is read[head]:
            head += 1
        tail = 0
        while tail < min(len(lines), len(read)) - head and lines[-1 - tail] is read[-1 - tail]:
            tail += 1
        # Only lines with a line break count: not a last one without.
        if tail and not self.parser.final_newline:
            tail -= 1
        self._write_text("\n".join(lines) + "\n", (head, tail))
        return "Update successful"

    def _write_text(self, new_source: str, kept: tuple[int, int] | None = None) -> None:
        """
        Single exit point for every edit (_save and _write_bytes both end
        here): normalise line endings, refuse a result that would not parse,
        then write the file in its own newline style (in a file that mixes
        CRLF and LF, each line's own, see _mixed_line_breaks, `kept` being
        what _save or _write_bytes know of the lines the edit left alone),
        its last line without a line break when the file's had none, and
        refresh the parser.
        """
        # Internal text is LF (see TreeSitterParser); caller-provided content
        # may still carry CRLF.
        new_source = new_source.replace("\r\n", "\n")
        # Nor does it include the byte order mark: content that starts the
        # file with one gives the file its mark, written once (below).
        bom = self.parser.bom or new_source.startswith("\ufeff")
        new_source = new_source.removeprefix("\ufeff")
        if not new_source.endswith("\n"):
            new_source += "\n"
        try:
            try:
                data = new_source.encode("utf-8")
            except UnicodeEncodeError as e:
                # A lone surrogate (JSON lets a client send half of a pair
                # as an escape) is not a character and has no UTF-8 form.
                raise ApplierError(
                    f"Edit refused: the new text holds a lone surrogate, "
                    f"U+{ord(new_source[e.start]):04X}, which is not a character and "
                    f"can't be written as UTF-8. {self.filepath} was not modified."
                ) from e
            self._check_syntax(data)
        except ApplierError:
            # Line-based edits change self.lines before saving; undo that so
            # this instance still mirrors the untouched file.
            self.lines = list(self._read_lines)
            raise
        if not self.parser.final_newline:
            # The file's last line had no line break (see TreeSitterParser),
            # and the new last line gets none either.
            new_source = new_source[:-1]
        if self.parser.line_breaks is not None:
            new_source = self._mixed_line_breaks(new_source, kept)
        elif self.parser.newline != "\n":
            new_source = new_source.replace("\n", self.parser.newline)
        if bom:
            # The file's UTF-8 byte order mark, which the text does not
            # include (see TreeSitterParser), stays first.
            new_source = "\ufeff" + new_source
        # newline="" writes the text verbatim, without platform translation.
        with open(self.filepath, "w", encoding="utf-8", newline="") as f:
            f.write(new_source)
        self._refresh_parser_state()

    def _mixed_line_breaks(self, text: str, kept: tuple[int, int] | None = None) -> str:
        """
        The LF text of an edit's result for a file that mixes CRLF and LF
        line breaks (TreeSitterParser.line_breaks), with a break for each of
        its lines: a line the edit left as it was (matched to the file's
        lines as difflib matches them) keeps its own, and a line it wrote
        takes the one the lines it replaces have, when they all have the
        same one, else the one the lines around it have, when the two agree
        (at the start or end of the file, the one line beside it), else the
        file's most common one (TreeSitterParser.newline). `kept`, when
        known, is how many of the file's lines with a break, at its start
        and at its end, the edit left alone: no more of them are taken for
        lines alike at both ends, so a line next to the edit that reads
        like one it removed or added keeps its own break.
        """
        breaks = self.parser.line_breaks
        old = self.parser.source_code.split("\n")[: len(breaks)]
        new = text.split("\n")
        rest = new.pop()
        heads, tails = kept if kept is not None else (len(old), len(old))
        # Only the lines between those alike at both ends are matched.
        head = 0
        while head < min(len(old), len(new), heads) and old[head] == new[head]:
            head += 1
        tail = 0
        while tail < min(min(len(old), len(new)) - head, tails) and old[-1 - tail] == new[-1 - tail]:
            tail += 1
        result = breaks[:head] + [self.parser.newline] * (len(new) - head - tail) + breaks[len(old) - tail :]
        matcher = difflib.SequenceMatcher(None, old[head : len(old) - tail], new[head : len(new) - tail], autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            i1, i2, j1, j2 = i1 + head, i2 + head, j1 + head, j2 + head
            if tag == "equal":
                result[j1:j2] = breaks[i1:i2]
                continue
            replaced = set(breaks[i1:i2])
            around = {breaks[k] for k in (i1 - 1, i2) if 0 <= k < len(breaks)}
            if len(replaced) == 1:
                result[j1:j2] = [replaced.pop()] * (j2 - j1)
            elif len(around) == 1:
                result[j1:j2] = [around.pop()] * (j2 - j1)
        return "".join(line + line_break for line, line_break in zip(new, result)) + rest

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
        library. A Ruby embedded document whose `=begin` does not start its
        line, which tree-sitter-ruby accepts, is an error too
        (_misplaced_document).
        """
        ext = self.parser.ext
        root = self.parser.tree.root_node
        ts_was_clean = not root.has_error and self._misplaced_document(root) is None
        if ext == ".py" or (ext == ".json" and not ts_was_clean):
            if self._stdlib_syntax_error(self.parser.source_bytes) is not None:
                return
        elif not ts_was_clean:
            return

        new_root = self.parser.parse(new_bytes).root_node
        bad = first_syntax_error(new_root) or self._misplaced_document(new_root)
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
        """Format an ERROR/MISSING node, or a Ruby embedded document whose
        `=begin` does not start its line, as 'line L, column C (what)',
        1-based."""
        line_start = data.rfind(b"\n", 0, node.start_byte) + 1
        column = len(data[line_start : node.start_byte].decode("utf-8", "replace")) + 1
        if node.is_missing:
            what = f"missing {node.type!r}"
        elif self._is_embedded_document(node):
            what = "an embedded document's =begin must start its line"
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
                    inserted inside that block (idiomatic Go), inline in
                    one written on one line; without one, a spec gets
                    its `import`.
          - Ruby:   "require 'foo'" or "require_relative 'bar'"
          - Java:   "import java.util.List;"
        Skips insertion if an identical import already exists.
        Places the new import in the group of imports it belongs with, at
        its sorted place when the group is sorted, else on the line after
        the group's last import (_import_groups, _import_place; a C/C++
        conditional that only includes counts as an import, and so do the
        includes inside a header's include guard and a JS CommonJS
        `require`, see _is_import). A first import goes
        after the preamble (_find_preamble_end: a package clause, `#!` and
        magic comments, a module docstring, 'use strict', `#pragma once`,
        an include guard's `#define`), with a blank line between them and
        one (two before a Python def or class) before the code after it,
        and so does a Python `from __future__` import that its group would
        put after code (_future_after_code).
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
            # Outside a block, a spec (`"fmt"`, `f "path/filepath"`) is
            # written as an import declaration.
            if not re.match(r"import\b", import_text.strip()):
                import_text = "import " + import_text.strip()

        stripped = import_text.strip()
        for line in self.lines:
            if line.strip() == stripped:
                return "Import already exists -- no change made"

        groups = self._import_groups(self._top_level_nodes(), self._is_import)
        if groups:
            insert_line = self._import_line(*self._import_place(groups, import_text))
            if not self._future_after_code(import_text, insert_line):
                self.lines = self.lines[:insert_line] + [import_text] + self.lines[insert_line:]
                return self._save()

        # The first import, or a Python `from __future__` import that its
        # group would put after code: after the preamble, a blank line on
        # each side.
        at = self._find_preamble_end()
        before, after = self.lines[:at], self.lines[at:]
        blank = 0
        while blank < len(after) and not after[blank].strip():
            blank += 1
        rest = after[blank:]
        gap = 0
        if rest:
            nodes = self.parser.tree.root_node.named_children
            code = next((c for c in nodes if c.start_point[0] >= at and "comment" not in c.type), None)
            pep8 = self.parser.ext == ".py" and code is not None and code.type in (
                "function_definition",
                "class_definition",
                "decorated_definition",
            )
            gap = max(blank, 2 if pep8 else 1)
        self.lines = before + ([""] if before else []) + [import_text] + [""] * gap + rest
        return self._save()

    def _future_after_code(self, import_text: str, row: int) -> bool:
        """Whether a Python `from __future__` import written on line `row`
        would follow code, which Python refuses (and ast.parse lets
        through): a statement other than the module docstring and other
        __future__ imports, comments aside, starts above that line."""
        if self.parser.ext != ".py" or not re.match(r"from\s+__future__\s+import\b", import_text.strip()):
            return False
        code = [
            c
            for c in self._top_level_nodes()
            if c.start_point[0] < row and "comment" not in c.type and c.type != "future_import_statement"
        ]
        first = next((c for c in self.parser.tree.root_node.named_children if "comment" not in c.type), None)
        if code and code[0] == first and self._string_statement(first):
            code = code[1:]
        return bool(code)

    def _import_groups(self, nodes, is_import) -> list[list]:
        """The groups of imports among `nodes` (the top-level nodes, or the
        specs of a Go import block) for add_import: the runs of the nodes
        that `is_import` takes for imports that no blank line or other code
        separates (comments may)."""
        groups: list[list] = []
        code = False
        for node in nodes:
            if not is_import(node):
                code = code or "comment" not in node.type
                continue
            if groups and not code:
                rows = range(self._last_row(groups[-1][-1]) + 1, node.start_point[0])
                if all(self.lines[row].strip() for row in rows):
                    groups[-1].append(node)
                    continue
            groups.append([node])
            code = False
        return groups

    def _import_place(self, groups: list[list], import_text: str) -> tuple[list, int]:
        """
        The group of imports (_import_groups) that add_import puts
        `import_text` in, and its index there. It goes in a group that
        holds imports of its kind (_import_info): of those, the one with an
        import of that kind whose path shares the most leading parts with
        its own, else the first, but in C/C++ not a group of only the
        file's own header (`"foo.h"` in foo.cpp). There it goes at its
        sorted place when the group is sorted (_sorted_index), else after
        the group's last import, but not right above a Go import "C", whose
        preamble comment cgo reads there. Without such a group, or when the
        text is no import of one module, it goes after the last group's last
        import.
        Python `from __future__` imports stay first: a new one goes after
        them, or before the file's first import, and other imports after
        them.
        """
        src = self.parser.source_bytes
        infos = [[self._import_info(node, src) for node in group] for group in groups]
        new = self._new_import_info(import_text)
        if new is None:
            return groups[-1], len(groups[-1])
        kind, path, keys = new
        stem = os.path.splitext(os.path.basename(self.filepath))[0]

        def own_header(info) -> bool:
            return (
                self.parser.ext in C_EXTS + CPP_EXTS
                and info is not None
                and info[0] == '"'
                and os.path.splitext(info[1][-1])[0] == stem
            )

        def shared(info) -> int:
            count = 0
            while count < min(len(path), len(info[1])) and path[count] == info[1][count]:
                count += 1
            return count

        fitting = [
            i
            for i, group in enumerate(infos)
            if any(info is not None and info[0] == kind for info in group)
            and not all(own_header(info) for info in group)
        ]
        if not fitting:
            if kind == "future":
                return groups[0], 0
            return groups[-1], len(groups[-1])
        best = max(
            fitting,
            key=lambda i: (max(shared(info) for info in infos[i] if info is not None and info[0] == kind), -i),
        )
        group, group_infos = groups[best], infos[best]
        index = None
        if all(info is not None for info in group_infos):
            index = _sorted_index([info[2] for info in group_infos], keys)
        if index is None:
            index = len(group)
        # Nothing goes between cgo's import "C" and its preamble, the
        # comment right above it.
        while (
            self.parser.ext == ".go"
            and index < len(group)
            and group_infos[index] is not None
            and group_infos[index][0] == "C"
        ):
            index += 1
        futures = [i for i, info in enumerate(group_infos) if info is not None and info[0] == "future"]
        if futures:
            index = min(index, futures[-1] + 1) if kind == "future" else max(index, futures[-1] + 1)
        return group, index

    def _new_import_info(self, import_text: str):
        """_import_info of the import add_import is given (a Go spec too,
        `"fmt"`), None when the text is not one import."""
        text = import_text.strip()
        if self.parser.ext == ".go":
            text = "package p\n" + (text if re.match(r"import\b", text) else f"import {text}")
        data = (text + "\n").encode("utf-8")
        root = self.parser.parse(data).root_node
        nodes = [c for c in root.named_children if "comment" not in c.type and c.type != "package_clause"]
        if len(nodes) != 1 or first_syntax_error(root) is not None:
            return None
        return self._import_info(nodes[0], data)

    def _import_info(self, node, data: bytes):
        """
        What an import node of `data` (the file's source, or the text of a
        new import) imports, for add_import: (kind, path, keys), or None
        when it imports no one module (a C/C++ conditional, an #include of
        a macro). Its kind picks its group: in Python 'future', 'stdlib'
        (sys.stdlib_module_names), 'other' or 'local' (a relative import);
        in C/C++ '<' or '"'; in Go whether the path is the standard
        library's (no dot in its first part), cgo's "C" a kind of its own;
        in JS/TS whether it is a `require` and whether its path is
        relative ('./', '../'); in Java whether it is static; in Ruby the
        method (`require`, `require_relative`). Its path is the module's,
        split into its parts (a Python relative import's dots one of
        them). Its keys sort it, one per order a group may follow
        (_sorted_index): in Python import lines before from-imports, else
        both together, by module name without case (numbers in numeric
        order), a `from __future__` import first; elsewhere by the path
        (in C/C++ as written, in its brackets or quotes).
        """

        def text(n) -> str:
            return data[n.start_byte : n.end_byte].decode("utf-8")

        ext = self.parser.ext
        if ext == ".py":
            if node.type == "future_import_statement":
                module = "__future__"
            elif node.type in ("import_statement", "import_from_statement"):
                name = node.child_by_field_name("name" if node.type == "import_statement" else "module_name")
                if name is not None and name.type == "aliased_import":
                    name = name.child_by_field_name("name")
                if name is None:
                    return None
                module = re.sub(r"\s+", "", text(name))
            else:
                return None
            dots = len(module) - len(module.lstrip("."))
            path = ([module[:dots]] if dots else []) + [part for part in module[dots:].split(".") if part]
            if dots:
                kind = "local"
            elif path[0] == "__future__":
                kind = "future"
            else:
                kind = "stdlib" if path[0] in sys.stdlib_module_names else "other"
            first = 0 if kind == "future" else 1
            name_key = (_natural(module.lower()), module)
            return kind, path, ((first, node.type != "import_statement", name_key), (first, name_key))
        if ext in _JS_EXTS:
            source = None
            if node.type == "import_statement":
                clause = next((c for c in node.named_children if c.type == "import_require_clause"), node)
                source = clause.child_by_field_name("source")
            else:
                stack = [node]
                while stack and source is None:
                    n = stack.pop()
                    function, arguments = n.child_by_field_name("function"), n.child_by_field_name("arguments")
                    if n.type == "call_expression" and function is not None and text(function) == "require":
                        strings = [c for c in arguments.named_children if "comment" not in c.type] if arguments is not None else []
                        source = strings[0] if len(strings) == 1 else None
                    stack.extend(reversed(n.named_children))
            if source is None or source.type not in ("string", "template_string"):
                return None
            path = _unquote(text(source))
            relative = path.startswith(("./", "../")) or path in (".", "..")
            return (node.type != "import_statement", relative), path.split("/"), (path,)
        if ext in C_EXTS + CPP_EXTS:
            path = node.child_by_field_name("path") if node.type == "preproc_include" else None
            if path is None or path.type not in ("system_lib_string", "string_literal"):
                return None
            written = text(path)
            return written[0], written[1:-1].split("/"), (written,)
        if ext == ".go":
            spec = node
            if node.type == "import_declaration":
                spec = next((c for c in node.named_children if c.type == "import_spec"), None)
            path = spec.child_by_field_name("path") if spec is not None and spec.type == "import_spec" else None
            if path is None:
                return None
            written = _unquote(text(path))
            parts = written.split("/")
            return ("C" if written == "C" else "." not in parts[0]), parts, (written,)
        if ext == ".java":
            name = next((c for c in node.named_children if c.type in ("scoped_identifier", "identifier")), None)
            if node.type != "import_declaration" or name is None:
                return None
            parts = [part.strip() for part in text(name).split(".")]
            if any(c.type == "asterisk" for c in node.named_children):
                parts.append("*")
            return any(c.type == "static" for c in node.children), parts, (".".join(parts),)
        if ext == ".rb":
            method, arguments = node.child_by_field_name("method"), node.child_by_field_name("arguments")
            if node.type != "call" or method is None or arguments is None:
                return None
            string = next((c for c in arguments.named_children if c.type == "string"), None)
            if string is None:
                return None
            path = _unquote(text(string))
            return text(method), path.split("/"), (path,)
        return None

    def _import_line(self, group: list, index: int) -> int:
        """The line add_import writes an import on to put it at `index` in
        `group` (_import_place): above group[index] and the comments right
        above it that go with it (_comments_above: above the group's first
        import only the directives for the next line, the others heading
        the group), else, and when group[index] follows other code on its
        line, below the group's last import (an #include ends with its line
        break)."""
        if index < len(group):
            node = group[index]
            row, column = node.start_point
            if not self.lines[row].encode("utf-8")[:column].strip():
                floor = self._last_row(group[index - 1]) if index else -1
                top = self._comments_above(node, floor, directives_only=not index)
                return row if top is None else top.start_point[0]
        return self._last_row(group[-1]) + 1

    def _comments_above(self, node, floor: int, directives_only: bool):
        """
        The topmost of the comments right above `node` that stay with it
        when an import or a name goes in above it (_import_line,
        _insert_entry), or None: those that start after row `floor`, or,
        with `directives_only` (above the first of a group or list, whose
        other comments head it), the directives for the next line
        (_NEXT_LINE_DIRECTIVE: `// @ts-ignore`, `// NOLINTNEXTLINE`) on
        lines of their own right above it.
        """
        top, row = None, node.start_point[0]
        above = node.prev_named_sibling
        while above is not None and "comment" in above.type and above.start_point[0] > floor:
            if directives_only and not (
                self._last_row(above) == row - 1
                and self._starts_line(above.start_byte)
                and _NEXT_LINE_DIRECTIVE.search(self.parser.node_text(above))
            ):
                break
            top, row = above, above.start_point[0]
            above = above.prev_named_sibling
        return top

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
        """Insert an import spec into an existing Go parenthesized import block,
        in its group of specs, as add_import places an import (_import_place),
        inline in a block written on one line (`import ("fmt"; "os")`).
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

        specs = [c for c in spec_list_node.named_children if c.type == "import_spec"]
        if spec_list_node.start_point[0] == spec_list_node.end_point[0]:
            # A block on one line (`import ("fmt"; "os")`, `import ()`)
            # takes the spec inline, at its place among the others.
            src = self.parser.source_bytes
            at, text = spec_list_node.end_byte - 1, spec_text
            if specs:
                groups = self._import_groups(spec_list_node.named_children, lambda node: node.type == "import_spec")
                group, index = self._import_place(groups, spec_text)
                if index < len(group):
                    at, text = group[index].start_byte, f"{spec_text}; "
                else:
                    at, text = group[-1].end_byte, f"; {spec_text}"
            self._write_bytes(src[:at] + text.encode("utf-8") + src[at:])
            return "Update successful"

        # On a new tab-indented line in the group of specs it belongs with
        # (_import_place), or before the closing `)` of an empty block
        # (and not below the `)` that closes the last spec's line).
        line = spec_list_node.end_point[0]
        if any(c.type == "import_spec" for c in spec_list_node.named_children):
            groups = self._import_groups(spec_list_node.named_children, lambda node: node.type == "import_spec")
            line = min(line, self._import_line(*self._import_place(groups, spec_text)))
        self.lines = self.lines[:line] + ["\t" + spec_text] + self.lines[line:]
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
        self._read_lines = tuple(self.lines)

    def _write_bytes(self, new_bytes: bytes, span: tuple[int, int] | None = None) -> None:
        """Write new LF source bytes to disk (via _write_text) and refresh
        parser state. `span`, when given, is the bytes [start, end) of the
        file that the edit replaced, all else being as it was: the lines
        before the one `start` is on, and those after the one `end` is on
        (from that one when it starts at `end` and stays whole), are left
        alone (_mixed_line_breaks)."""
        kept = None
        if span is not None:
            src = self.parser.source_bytes
            start, end = span
            suffix = len(src) - end
            tail = src.count(b"\n", end)
            whole = (end == 0 or src[end - 1 : end] == b"\n") and (
                len(new_bytes) == suffix or new_bytes[len(new_bytes) - suffix - 1 : len(new_bytes) - suffix] == b"\n"
            )
            kept = (src.count(b"\n", 0, start), tail if whole else max(tail - 1, 0))
        self._write_text(new_bytes.decode("utf-8"), kept)

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
        pad_empty: bool = True,
        at: int | None = None,
    ) -> None:
        """
        Write `entry` (e.g. '"key": value') after the last of `entries` in a
        brace- or bracket-delimited container (JSON object or array, Python
        dict, JS/TS object literal, YAML flow mapping or sequence, TOML
        inline table or array, the names of a JS/TS named import or of a
        Python `from m import (...)`), following the container's layout:
        entries one per line get a new line at the last entry's indentation
        (also when the bracket closes the last entry's line, as in a list
        aligned under its `[`, see _one_per_line), an inline container stays
        inline, and a trailing comma after the last entry is kept (the new
        entry gets one too). A comment on the last entry's line stays there,
        and an entry that ends with a comment of its own gets its comma
        before it (_with_separator). An empty container becomes `{ entry }`
        (`[entry]` without `pad_empty`), or with `expand_empty` is opened
        onto separate lines (`empty_trailing_comma` adds a comma). With
        `at`, an index into `entries`, the entry goes before entries[at]
        instead: on a line of its own at that entry's indentation, above
        it and the comments right above it that go with it
        (_comments_above: above the first entry only the directives for
        the next line, the others heading the list), when the entry starts
        its line, else inline before it (`a, new, b`).
        """
        src = self.parser.source_bytes
        open_brace, close_brace = container.children[0], container.children[-1]
        base_indent = self._get_indent(self.lines[open_brace.start_point[0]])
        inner_indent = base_indent + self._indent_unit(default_unit)
        edits: list[tuple[int, int, str]] = []  # (start, end, replacement)

        if at is not None and at < len(entries):
            # Before entries[at]: on a line of its own above it and the
            # comments right above it when it starts its line, else inline.
            target = entries[at]
            start = target.start_byte - target.start_point[1]
            if src[start : target.start_byte].strip():
                edits.append((target.start_byte, target.start_byte, f"{entry}, "))
            else:
                indent = src[start : target.start_byte].decode("utf-8")
                floor = self._last_row(entries[at - 1]) if at else open_brace.end_point[0]
                top = self._comments_above(target, floor, directives_only=not at)
                if top is not None:
                    start = top.start_byte - top.start_point[1]
                edits.append((start, start, f"{indent}{self._with_separator(entry, ',')}\n"))
        elif entries:
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
                new_line = "\n" + indent + self._with_separator(entry, "," if comma else "")
                edits.append((line_end, line_end, new_line))
                if comma is None:
                    edits.append((last.end_byte, last.end_byte, ","))
            elif self._one_per_line(entries):
                # The bracket closes the last entry's line (`[1,\n     2]`):
                # a new line at its indentation, the bracket after it.
                indent = self._get_indent(self.lines[last.start_point[0]])
                edits.append((end, end, "\n" + indent + self._with_separator(entry, "," if comma else "")))
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
                line = self._with_separator(entry, comma)
                if src[line_start : close_brace.start_byte].strip():
                    text = f"\n{indent}{line}\n{base_indent}"
                    edits.append((close_brace.start_byte, close_brace.start_byte, text))
                else:
                    edits.append((line_start, line_start, f"{indent}{line}\n"))
            elif interior.strip():
                # Only a comment between the braces: keep it, add after it.
                pad = "" if interior[-1:].isspace() else " "
                text = f"{pad}{entry} "
                edits.append((close_brace.start_byte, close_brace.start_byte, text))
            elif expand_empty:
                text = f"\n{inner_indent}{self._with_separator(entry, comma)}\n{base_indent}"
                edits.append((open_brace.end_byte, close_brace.start_byte, text))
            else:
                text = f" {entry} " if pad_empty else entry
                edits.append((open_brace.end_byte, close_brace.start_byte, text))

        # Apply back to front. The sort is stable, so of two edits at the same
        # offset the one listed later ends up first (the comma before the new
        # line).
        new_bytes = src
        for start, end, text in sorted(edits, key=lambda e: e[0], reverse=True):
            new_bytes = new_bytes[:start] + text.encode("utf-8") + new_bytes[end:]
        self._write_bytes(new_bytes)

    def _one_per_line(self, entries: list) -> bool:
        """Whether a container's `entries` are written one per line: two or
        more, each on a line of its own, the last one first on its line (the
        first may follow the opening bracket, as in a list aligned under its
        `[`)."""
        if len(entries) < 2 or len({e.start_point[0] for e in entries}) < len(entries):
            return False
        row, column = entries[-1].start_point
        return not self.lines[row].encode("utf-8")[:column].strip()

    def _with_separator(self, entry: str, mark: str) -> str:
        """`entry`, written on a line of its own, followed by `mark` (`,` or
        ''): before a comment that the entry ends with (`3,  # new` for `3  #
        new`), which would otherwise take the mark in."""
        data = entry.encode("utf-8")
        end = len(data.rstrip())
        if not mark or end == 0:
            return entry + mark
        node = self.parser.parse(data).root_node.descendant_for_byte_range(end - 1, end)
        while node is not None and "comment" not in node.type:
            node = node.parent
        code = data[: node.start_byte].rstrip() if node is not None else b""
        if not code:
            return entry + mark
        return (code + mark.encode("utf-8") + data[len(code) :]).decode("utf-8")

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
        """Delete entries[idx] from a delimited container, as _entry_deleted
        says, and write the file."""
        self._write_bytes(self._entry_deleted(container, entries, idx))

    def _entry_deleted(self, container, entries: list, idx: int, count: int = 1) -> bytes:
        """
        The source with entries[idx] deleted from a brace-, bracket- or
        parenthesis-delimited container (JSON object or array, Python dict
        or list, JS/TS object literal, YAML flow sequence, TOML array, a
        parameter list, import names) along with one adjacent comma; with
        `count`, the entries from there to entries[idx + count - 1] go as
        one (_Span). An entry on lines of its own goes with those whole
        lines, a comment on its last line included; if it was the last entry
        and had no trailing comma, the comma after the entry before it goes
        too (JSON rejects a trailing comma). An entry sharing a line with
        another one is cut up to the next entry when it starts its line (or
        is the first entry), else from the end of the one before it, so one
        separating comma goes with it; a comment between the two stays, with
        the closing bracket moved below it when it ends its line. Deleting
        the only entry leaves `{}` (when nothing but whitespace, a trailing
        comma and comments on the entry's line surround it) rather than a
        stray comma, which JS would reject. Comments are no entries: they
        are left out of `entries`, and those on lines other than the
        entry's stay.
        """
        src = self.parser.source_bytes
        if count > 1:
            entries = entries[:idx] + [_Span(entries[idx], entries[idx + count - 1])] + entries[idx + count :]
        entry = entries[idx]
        open_brace, close_brace = container.children[0], container.children[-1]
        inner = container.children[1:-1]
        # The entry's comma, then any comments on the same row.
        after = [c for c in inner if c.start_byte >= entry.end_byte]
        comma = after[0] if after and after[0].type == "," else None
        end = (comma or entry).end_byte
        row = (comma or entry).end_point[0]
        for c in after[1 if comma else 0 :]:
            if "comment" not in c.type or c.start_point[0] != row:
                break
            end = c.end_byte
        # What stays: the comments on the entry's row after it go with it.
        others = [
            c
            for c in inner
            if c != entry
            and not entry.start_byte <= c.start_byte < entry.end_byte
            and not (c.type == "," and c.start_byte >= entry.end_byte)
            and not (entry.end_byte <= c.start_byte and c.end_byte <= end)
        ]
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
        elif idx > 0 and not any(
            "comment" in c.type and entries[idx - 1].end_byte <= c.start_byte < entry.start_byte
            for c in inner
        ):
            cuts = [(entries[idx - 1].end_byte, entry.end_byte)]
        elif idx > 0:
            # A comment after the entry before stays with it. That entry's
            # comma goes, except in Go, which needs it before a line break,
            # and the closing bracket takes this entry's place, at the
            # indentation of the container's first line when the entry
            # started its line.
            cuts = []
            prev_comma = next(
                (
                    c
                    for c in inner
                    if c.type == "," and entries[idx - 1].end_byte <= c.start_byte < entry.start_byte
                ),
                None,
            )
            if prev_comma is not None and self.parser.ext != ".go":
                cuts.append((prev_comma.start_byte, prev_comma.end_byte))
            if starts_line and self.parser.ext in (".yml", ".yaml"):
                # YAML wants the lines of a flow sequence indented past its key.
                cuts.append((entry.start_byte, entry.end_byte))
            elif starts_line:
                opener_line = src[src.rfind(b"\n", 0, container.start_byte) + 1 : container.start_byte]
                indent = opener_line[: len(opener_line) - len(opener_line.lstrip(b" \t"))]
                cuts.append((line_start, entry.end_byte, indent))
            else:
                start = entry.start_byte
                while src[start - 1 : start] in (b" ", b"\t"):
                    start -= 1
                cuts.append((start, entry.end_byte))
        else:
            cuts = [(entry.start_byte, (comma or entry).end_byte)]

        new_bytes = src
        for start, stop, *text in sorted(cuts, reverse=True):
            new_bytes = new_bytes[:start] + b"".join(text) + new_bytes[stop:]
        return new_bytes

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
            raise self._duplicate_key(name, parent_target, _config_path(parent_target, name))

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
        parent_target names (TreeSitterParser.find_yaml_pair), in a flow
        mapping too. A block mapping gets a new line at its keys'
        indentation and a flow mapping ({a: 1} or {}) an inline entry, as
        _insert_entry writes it. A key with no value (`parent:`) gets a
        nested block mapping on the line below, one indentation unit deeper
        (inside a flow mapping, `{parent:}` or `{parent}`, the inline
        `parent: { key: value }`), and a file with nothing in it yet (empty
        or only comments) the new line at its end. The key is quoted only
        when it has to be (_yaml_key_source).
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

        entries = self.parser.yaml_entries(mapping)
        for entry in entries:
            key_node = self.parser.yaml_entry_key(entry)
            if key_node is not None and self.parser.yaml_key_name(self.parser.node_text(key_node)) == name:
                raise self._duplicate_key(key, parent_target, _config_path(parent_target, name))

        new_entry = f"{key_text}: {value}"
        if mapping is None and pair is not None and pair.type != "block_mapping_pair":
            # A key with no value inside a flow mapping gets an inline one.
            return self._fill_yaml_value(pair, f"{{ {new_entry} }}")
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

    def _fill_yaml_value(self, pair, content: str) -> str:
        """
        Give a YAML key written with no value (`key:`, or in a flow mapping
        `{key:}` or `{key}`) the value `content`. One line goes after the
        colon, before a comment there (`key: 3 # note`), and `{key}` gets
        its colon too. In a block mapping, content of several lines, or one
        line that starts a block sequence or mapping (`- a`, `x: 1`), goes
        on the lines below the key instead, one indentation unit deeper
        than the key, keeping its relative indentation; a first line that
        is only a block scalar header or node properties (`|`, `>-`,
        `&anchor`, `!tag`) stays after the colon, as YAML writes it. An
        explicit key with no value (`? key`) gets a `: value` line below it,
        in the column of its `?`.
        """
        src = self.parser.source_bytes
        lines = _content_lines(content)
        inline, below = content, []
        if pair.type == "block_mapping_pair" and (len(lines) > 1 or _YAML_BLOCK_START.match(content)):
            inline, below = "", lines
            if len(lines) > 1 and _YAML_NODE_HEADER.fullmatch(lines[0].strip(" \t")):
                inline, below = lines[0].strip(" \t"), lines[1:]

        colon = next((c for c in pair.children if c.type == ":"), None)
        if pair.type == "block_mapping_pair" and colon is None and pair.children and pair.children[0].type == "?":
            # An explicit key with no value (`? a`): `? a: 3` would make the
            # mapping {a: 3} the key, so the value gets a `:` line of its
            # own, in the `?`'s column, after the key's last line.
            line_start = src.rfind(b"\n", 0, pair.start_byte) + 1
            column = len(src[line_start : pair.start_byte].decode("utf-8"))
            line_end = src.find(b"\n", pair.end_byte)
            if line_end == -1:
                line_end = len(src)
            text = "\n" + " " * column + ":" + (f" {inline}" if inline else "")
            indent = " " * column + self._indent_unit("  ")
            text += "".join("\n" + line for line in self._reindent(below, indent))
            self._write_bytes(src[:line_end] + text.encode("utf-8") + src[line_end:])
            return "Update successful"

        edits: list[tuple[int, str]] = []  # (offset, text to insert)
        if below:
            line_start = src.rfind(b"\n", 0, pair.start_byte) + 1
            column = len(src[line_start : pair.start_byte].decode("utf-8"))
            indent = " " * column + self._indent_unit("  ")
            line_end = src.find(b"\n", pair.end_byte)
            if line_end == -1:
                line_end = len(src)
            edits.append((line_end, "".join("\n" + line for line in self._reindent(below, indent))))
        if inline:
            if colon is None:
                edits.append((pair.end_byte, f": {inline}"))
            elif src[colon.end_byte : colon.end_byte + 1] in (b" ", b"\t"):
                # Keep the space after the colon; a comment after the value
                # needs one before its `#`.
                pos = colon.end_byte + 1
                pad = "" if src[pos : pos + 1] in (b"", b" ", b"\t", b"\n", b",", b"}", b"]") else " "
                edits.append((pos, inline + pad))
            else:
                edits.append((colon.end_byte, f" {inline}"))
        # Back to front; the sort is stable, so at one offset (`key:` at the
        # end of its line) the text after the colon ends up first.
        new_bytes = src
        for pos, text in sorted(edits, key=lambda e: e[0], reverse=True):
            new_bytes = new_bytes[:pos] + text.encode("utf-8") + new_bytes[pos:]
        self._write_bytes(new_bytes)
        return "Update successful"

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
        table twice. Keys compare by the names they spell (toml_key_names)."""
        new = toml_key_names(key)
        for pair in pairs:
            have = toml_key_names(self.parser.node_text(pair.children[0]))
            n = min(len(have), len(new))
            if have[:n] == new[:n]:
                return True
        parent = toml_key_names(parent_target) if parent_target else []
        full = parent + new
        for node in root.named_children:
            if node.type not in ("table", "table_array_element"):
                continue
            h = self.parser.toml_header_names(node)
            # Headers of the parent table and its ancestors do not count.
            if h is not None and len(h) > len(parent) and (h[: len(full)] == full or full[: len(h)] == h):
                return True
        return False

    def _add_key_toml(self, parent_target: str, key: str, value: str) -> str:
        """
        Add `key = value` to a TOML table: the root (parent_target ''), a
        [table] whose header spells the path (TreeSitterParser.toml_table:
        [a."b.c"] is 'a."b.c"'), or an inline table (`t = { a = 1 }` or
        `{}`, nested ones too) that parent_target names as a key path
        (toml_pair), which gets the entry inline as _insert_entry writes it.
        The key is quoted only when it is not a bare key (_toml_key_source).
        """
        root = self.parser.tree.root_node
        key_text = self._toml_key_source(key)
        inline = None
        if parent_target:
            table = self.parser.toml_table(root, parent_target)
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
            # key_text is written like a path, so it extends parent_target.
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
        (a.b is key b in table a), as in TOML itself and in TOML target
        paths, so '"a.b"' or "'a.b'" is one name. Each part that is a
        bare key (ASCII letters, digits, `_` and `-`) or is already in
        quotes is kept as given; any other part (with a space, `:`, `#`,
        non-ASCII letters, ...) becomes a basic string ("...", escaped). A
        key with an empty part ('', 'a..b') is quoted whole.
        """
        key = key.strip()
        # Split as a TOML target path is (toml_key_names), quotes kept.
        parts = split_config_path(key, "\"'", strip=True, raw=True)
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
        """The key-value pair at a JSON/YAML/TOML key path (also inside a
        YAML flow mapping or TOML inline table), or None. In YAML that is
        the entry itself, so a key with no value (`key:`, `{key}`) is found
        too."""
        root = self.parser.tree.root_node
        ext = self.parser.ext
        if ext == ".json":
            value_node = self.parser._search_json_dotted(root, dotted_path)
            if value_node and value_node.parent and value_node.parent.type == "pair":
                return value_node.parent
        elif ext in (".yml", ".yaml"):
            return self.parser.find_yaml_pair(root, dotted_path)
        elif ext == ".toml":
            return self.parser.toml_pair(root, dotted_path)
        return None

    def delete_key(self, target: str) -> str:
        """
        Delete a key-value pair from a container:
          - JSON / YAML / TOML config files (key path from the top level,
            into YAML flow mappings and TOML inline tables too).
          - Python module-level dict literals (target is 'DictName' + '.' + key-literal,
            e.g. 'CONFIG."foo"').
          - JS / TS module-level const/let/var object literals (target is
            'VarName.keyName' or 'VarName."quoted-key"', or a longer path into
            nested objects such as 'CONFIG.server.port'). Handles regular
            `{ key: value }` pairs, shorthand `{ key }` properties and methods,
            inside `export const` too.
          - Python targets may also continue into nested dicts
            ('CONFIG."db"."host"').

        For JSON, JS/TS, YAML flow mappings and TOML inline tables, also
        removes the adjacent comma to keep the file valid.
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

        # JSON objects, YAML flow mappings and TOML inline tables are cut
        # like brace-delimited literals, keeping the inline style.
        parent = pair.parent
        if ext == ".json" or parent.type in ("flow_mapping", "inline_table"):
            if parent.type == "flow_mapping":
                entries = self.parser.yaml_entries(parent)
            else:
                entries = [c for c in parent.named_children if c.type == "pair"]
            self._delete_entry(parent, entries, entries.index(pair))
            return "Update successful"

        # YAML block mappings / TOML tables: remove the pair's line(s)
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
          - JSON arrays, TOML arrays and YAML flow sequences (via the key
            path to the array), in the array's layout as _insert_entry
            writes it: an inline array stays inline (`[1, 2, 3]`; an empty
            one becomes `[3]`), one with an element per line gets a new line
            at the elements' indentation, and a trailing comma is kept.
          - YAML block sequences: a `- value` item after the last one.
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
        elif ext == ".toml":
            arr = self.parser._search_toml_dotted(root, target)
            if arr is None or arr.type != "array":
                raise ApplierError(f"TOML array at '{target}' not found")
        elif ext in (".yml", ".yaml"):
            value_node = self.parser._search_yaml_dotted(root, target)
            arr = self._resolve_yaml_value(value_node)
            if arr is None or arr.type not in ("block_sequence", "flow_sequence"):
                raise ApplierError(f"YAML sequence at '{target}' not found")
            if arr.type == "block_sequence":
                return self._append_yaml_block_item(arr, value)
        else:
            raise ApplierError(f"append_to_array is not supported for {ext}")

        self._insert_entry(
            arr,
            [c for c in arr.named_children if "comment" not in c.type],
            value,
            expand_empty=False,
            empty_trailing_comma=False,
            default_unit="  ",
            pad_empty=False,
        )
        return "Update successful"

    def _append_yaml_block_item(self, seq, value: str) -> str:
        """Add `- value` after the last item of a YAML block sequence, at its
        items' indentation. Multi-line values (e.g. a mapping with several
        keys) get the `-` marker on the first line and a 2-space hanging
        indent on continuation lines so they nest under the item."""
        items = [c for c in seq.named_children if c.type == "block_sequence_item"]
        if not items:
            raise ApplierError("Cannot append to empty YAML block sequence (unsupported in v1)")
        last = items[-1]
        indent = self._get_indent(self.lines[last.start_point[0]])
        insert_line = last.end_point[0] + 1
        value_lines = _content_lines(value) or [""]
        new_item_lines = [f"{indent}- {value_lines[0]}"]
        for cont in value_lines[1:]:
            new_item_lines.append(f"{indent}  {cont}")
        self.lines = self.lines[:insert_line] + new_item_lines + self.lines[insert_line:]
        return self._save()

    def remove_from_array(self, target: str, value_match: str) -> str:
        """
        Remove the first element matching value_match (stripped text equality) from
        an array/list in a config file OR a Python module-level list literal.
        Comments are no elements. A JSON or TOML array or a YAML flow
        sequence loses the element the way _delete_entry deletes an entry:
        one on a line of its own goes with that line, a comment at its end
        included (comments on other lines stay), and a last element with no
        comma after it takes the comma before it. A YAML block sequence item
        goes with its lines; the only one leaves `[]` after its key
        (_empty_yaml_sequence).
        """
        ext = self.parser.ext
        if ext == ".py":
            return self.remove_from_list(target, value_match)

        root = self.parser.tree.root_node
        stripped_match = value_match.strip()

        def _remove_element(arr_node):
            elements = [c for c in arr_node.named_children if "comment" not in c.type]
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
            self._delete_entry(arr_node, elements, idx)

        if ext == ".json":
            arr = self.parser._search_json_dotted(root, target)
            if arr is None or arr.type != "array":
                raise ApplierError(f"JSON array at '{target}' not found")
            _remove_element(arr)
            return "Update successful"

        if ext == ".toml":
            arr = self.parser._search_toml_dotted(root, target)
            if arr is None or arr.type != "array":
                raise ApplierError(f"TOML array at '{target}' not found")
            _remove_element(arr)
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
                _remove_element(collection)
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
            end_line = self._last_row(items[match_idx]) + 1
            if len(items) == 1:
                # The only item: the sequence becomes an empty flow sequence
                # after its key's `:` (or its anchor or tag), as a value of
                # its own (no value would be null).
                return self._empty_yaml_sequence(collection, start_line, end_line)
            self.lines = self.lines[:start_line] + self.lines[end_line:]
            return self._save()

        raise ApplierError(f"remove_from_array is not supported for {ext}")

    def _empty_yaml_sequence(self, seq, start_line: int, end_line: int) -> str:
        """
        For remove_from_array: remove the lines [start_line, end_line) of the
        only item of the YAML block sequence `seq`, and write `[]` after the
        code its value follows (`a:` gives `a: []`, `a: &x` gives `a: &x
        []`), so that the key keeps an empty sequence rather than becoming
        null. A comment after that code stays after the `[]`, and comment
        lines between the key and the item stay where they are. A sequence
        with no code before it (a document's root) loses the item's lines.
        """
        before = seq
        while before is not None:
            prev = before.prev_sibling
            while prev is not None and "comment" in prev.type:
                prev = prev.prev_sibling
            if prev is not None:
                break
            before = before.parent
        lines = self.lines[:start_line] + self.lines[end_line:]
        if before is not None:
            row, column = prev.end_point
            line = lines[row]
            at = len(line.encode("utf-8")[:column].decode("utf-8"))
            lines[row] = line[:at] + " []" + line[at:]
        self.lines = lines
        return self._save()

    def add_field(self, class_target: str, content: str) -> str:
        """
        Add a field/attribute/member at the top of a class body (fields-before-methods
        convention): before its first member, but after a Python class
        docstring, a Java enum's constants or the access label a C++ class
        body opens with. Indentation and spacing as for add_method
        (_insert_member).

        Design decision: option (a) -- the caller provides the literal text to insert.
        The tool does NOT auto-wrap in language-specific constructs (e.g. no implicit
        `attr_accessor :foo` for Ruby, no implicit type inference for Go). Pass exactly
        what you want to appear in the source.
        """
        node = self._class_target(class_target)
        node = self._typedef_struct(node)

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

    def _class_target(self, class_target: str):
        """
        For add_method and add_field: the container `class_target` names
        (TreeSitterParser.find_container: a struct rather than a function
        or variable of its name). A target that names no container is
        refused: a function, whose body insert_in_body adds to, and a TS
        enum or type alias (_refuse_ts_non_class).
        """
        node = self.parser.find_container(class_target) or self.parser.find_node_by_name(class_target)
        if not node:
            raise ApplierError(f"Target class '{class_target}' not found")
        self._refuse_ts_non_class(class_target, node)
        functions = self._interface_func_types() | set(_BODILESS_FUNCTIONS)
        if (
            node.type in functions
            or self._callable(node, class_target) is not node
            or self._declares_c_function(node, class_target)
        ):
            raise ApplierError(
                f"'{class_target}' is a function, not a class, so add_method and add_field cannot add to it; "
                "add to its body with insert_in_body"
            )
        return node

    def _refuse_ts_non_class(self, class_target: str, node) -> None:
        """
        For add_method and add_field: refuse a TS enum or type alias. They
        are targets like classes, but hold no methods or fields (an enum's
        members are its constants).
        """
        kinds = {"enum_declaration": "an enum", "type_alias_declaration": "a type alias"}
        if self.parser.ext in (".ts", ".tsx") and node.type in kinds:
            raise ApplierError(
                f"'{class_target}' is {kinds[node.type]}, not a class or interface, "
                "so add_method and add_field cannot add to it; rewrite it with "
                "replace_function"
            )

    @staticmethod
    def _typedef_struct(node, enums: bool = False):
        """For add_method and add_field: the struct, union or class that a
        C/C++ typedef found for the target defines (`typedef struct {...}
        P;`), whose body holds the typedef's members; else node itself. With
        `enums`, an enum too (`typedef enum {...} E;`), which the signature
        and interface depths read the typedef as."""
        if node.type == "type_definition":
            spec = node.child_by_field_name("type")
            kinds = ("class_specifier", "struct_specifier", "union_specifier") + (("enum_specifier",) if enums else ())
            if spec is not None and spec.type in kinds and spec.child_by_field_name("body") is not None:
                return spec
        return node

    def _insert_member(self, class_target: str, node, body, content: str, at_end: bool) -> str:
        """
        Insert content as a member of the class `node`, whose members `body`
        holds (None for an empty Ruby class): after the last member for
        add_method (at_end=True), or after the last method of a C++ class
        when an access label follows it (_section_method); else before the
        first one, but after a Python class docstring, for add_field. A
        Java enum's members are those after its constants, which stay first
        (_java_enum_members), and a C++ body that opens with an access label
        (`public:`) has the field below it, in the first member's section
        (_insert_under_label).

        The content is re-indented like the class's existing members (see
        _member_indent), keeping its own relative indentation (content in
        read_symbol's shape from the indentation it was read at, see
        _from_read_shape), written in tabs when the members are indented
        with tabs (_tab_indent). A
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
        if body is not None and body.type == "enum_body" and ext == ".java":
            start, semi, members = self._java_enum_members(body)
            indent_from = members or indent_from
        member_indent = self._member_indent(node, indent_from)
        lines = self._from_read_shape(lines, member_indent)
        if "\t" in member_indent:
            lines = self._tab_indent(lines)
        lines = self._reindent(lines, member_indent)
        method_types = self._interface_func_types() | {"method_signature", "abstract_method_signature"}
        # A C++ method goes after the class's last method when an access
        # label follows it, in its section (_section_method), spaced from it
        # as from the last member.
        anchor = self._section_method(members) if at_end else None
        above = members if anchor is None else members[: members.index(anchor) + 1]
        gap_before = self._method_gap(body, above, method_types) if at_end and members else 0
        # A one-line field after stacked one-line fields is stacked too.
        code = [m for m in above if not self._is_aside(m)]
        if at_end and code and not self._is_block(lines) and not self._is_block(code[-1]):
            comment_range = self._find_leading_comment_range(code[-1].start_point[0])
            far = self._sibling_above(code[-1], comment_range[0] if comment_range is not None else code[-1].start_point[0])
            if far is not None and far[0] is not None and not self._is_block(far[0]):
                gap_before = self._sibling_gaps(body, (code[-1], code[-1]), lines, None, far)[0]
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
        gap = b"\n" if not at_end and following is not None and self._is_method(following, method_types) else b""
        constants = src[open_b + 1 : start].strip()
        label = next((m for m in members if "comment" not in m.type), None)
        if not at_end and label is not None and label.type == "access_specifier":
            new = self._insert_under_label(body, members, label, text, method_types, class_indent, indent)
        elif (body.start_point[0] == body.end_point[0] and (members or constants)) or (semi and not constants):
            # A body on one line (or an enum with no constants) is rebuilt
            # over several lines: the enum constants (or a lone `;`), the
            # existing members and the new one each on their own.
            existing = src[start:close_b].strip()
            parts = [indent + constants + semi, b""] if semi or constants else []
            if not existing:
                parts.append(text)
            elif anchor is not None:
                # The code after that method goes on a line of its own below
                # the new one.
                parts += [indent + src[start : anchor.end_byte].strip()] + [b""] * gap_before + [text]
                parts.append(indent + src[anchor.end_byte : close_b].strip())
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
            separator, after = self._line_sharing(anchor, anchor)[1:] if anchor is not None else (None, False)
            if anchor is not None and after:
                # Code follows the method on its line (`private:`): it moves
                # to a line of its own below the new method, an access label
                # indented like the class's others (_label_indent).
                end = self._code_end(anchor) if separator is None else separator.end_byte
                following = next((m for m in members if m.start_byte >= end), None)
                lead = indent
                if following is not None and following.type == "access_specifier":
                    lead = self._label_indent(members, following, class_indent)
                new = src[:end] + b"\n" + spacing + text + b"\n" + lead + src[end:].lstrip(b" \t")
            elif anchor is not None:
                # After the method's lines (_rows_below: a comment after it
                # there, and those indented deeper below it).
                row = self._rows_below(anchor, anchor, separator)
                pos = sum(len(line.encode("utf-8")) + 1 for line in self.lines[:row])
                new = src[:pos] + spacing + text + b"\n" + src[pos:]
            elif self._starts_line(close_b):
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

    def _insert_under_label(self, body, members, label, text: bytes, method_types, class_indent: bytes, indent: bytes) -> bytes:
        """
        add_field's new source for the C++ class body `body` whose first
        member is an access label (`public:`), `label`: the field, `text`
        (indented already), goes below the label, before the members of its
        section, so that it gets their access rather than the class's
        default. Comments after the label on its line stay there, and a
        blank line goes after the field when a method follows it directly.
        A member (or the `}`) on the label's line moves to a line of its own
        below the field, and a body on one line is rebuilt over several, the
        label on a line of its own at the class's indentation.
        """
        src = self.parser.source_bytes
        close_b = body.end_byte - 1
        colon = label.next_sibling
        end = colon.end_byte if colon is not None and colon.type == ":" else label.end_byte
        rest = [m for m in members if m.start_byte >= end]
        following = next((m for m in rest if not self._is_aside(m)), None)
        gap = b"\n" if following is not None and self._is_method(following, method_types) else b""
        if body.start_point[0] == body.end_point[0]:
            existing = src[end:close_b].strip()
            parts = [class_indent + src[label.start_byte : end], text]
            if existing:
                parts += [b""] * len(gap) + [indent + existing]
            return src[: body.start_byte + 1] + b"\n" + b"\n".join(parts) + b"\n" + class_indent + src[close_b:]
        n, row = 0, label.start_point[0]
        while n < len(rest) and "comment" in rest[n].type and rest[n].start_point[0] == row:
            row = rest[n].end_point[0]
            n += 1
        after = rest[n - 1].end_byte if n else end
        nl = src.find(b"\n", after)
        if n < len(rest) and rest[n].start_point[0] == row:
            # A member follows the label on its line.
            return src[:after] + b"\n" + text + b"\n" + gap + indent + src[after:].lstrip(b" \t")
        if not 0 <= nl < close_b:
            # The `}` follows the label on its line.
            return src[:after] + b"\n" + text + b"\n" + class_indent + src[after:].lstrip(b" \t")
        pos = nl + 1
        if n < len(rest) and b"\n" in src[pos : rest[n].start_byte]:
            gap = b""
        return src[:pos] + text + b"\n" + gap + src[pos:]

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

    def _tab_indent(self, lines: list[str], extra=None) -> list[str]:
        """
        `lines` with the indentation they have beyond their first line's
        written in tabs: one per indentation step of the content (the
        smallest such indentation it has), any spaces left over kept. Lines
        indented less than the first, the lines that start inside a
        multi-line string literal (_literal_rows), and content that already
        uses tabs for it, are left as they are; the lines of a literal that
        moves with the code (a docstring) get tabs only for as far as the
        line it starts on is indented, so they stay in line with it, and so
        do the lines that spaces align with a line above (_aligned_rows): the
        later lines of a block comment, and a line continued inside a
        bracket that code follows on its line. `extra` adds the lines that
        start inside a string of the file (_context_literals).
        """
        first = lines[0]
        base = first[: len(first) - len(first.lstrip(" \t"))]
        literals = self._literal_rows(lines) + (extra or [])
        literal = {i for rows, _ in literals for i in rows}
        extra = []
        for i, line in enumerate(lines):
            rest = line[len(base) :] if line.strip() and line.startswith(base) else ""
            extra.append(rest[: len(rest) - len(rest.lstrip(" \t"))])
        aligned = {i: row for i, row in self._aligned_rows(lines).items() if i not in literal}
        # How much of a line's indentation may become tabs: all of a code
        # line's, as much of a moving literal's lines as its first line has,
        # and of an aligned line as much as the line it aligns with has.
        limit = {i: len(ws) for i, ws in enumerate(extra) if i not in literal and i not in aligned}
        for rows, shifts in literals:
            for i in rows:
                if shifts and rows.start - 1 in limit:
                    limit[i] = min(len(extra[i]), limit[rows.start - 1])
        for i in sorted(aligned):
            limit[i] = min(len(extra[i]), limit.get(aligned[i], 0))
        widths = [len(ws) for i, ws in enumerate(extra) if ws and i not in literal and i not in aligned]
        if not widths or any("\t" in extra[i] for i in limit):
            return lines
        step = min(widths)
        result = []
        for i, (line, ws) in enumerate(zip(lines, extra)):
            if limit.get(i):
                tabs, spaces = divmod(limit[i], step)
                line = base + "\t" * tabs + " " * spaces + line[len(base) + limit[i] :]
            result.append(line)
        return result

    def _aligned_rows(self, lines: list[str]) -> dict[int, int]:
        """
        The lines of the caller content `lines` that spaces align with a
        line above rather than indent, for _tab_indent, each with the row of
        the line it aligns with: the later lines of a block comment, which
        align with its first, and a line continued inside a `(` or `[` that
        code follows on its own line (`def f(a,` above `      b):`), which
        aligns with that line; inside a `{` (a block, an object) lines are
        indented. The content is parsed with the file's grammar, Python's
        dedented by its first line's indentation first.
        """
        ext = self.parser.ext
        if ext in _CONFIG_EXTS or len(lines) < 2:
            return {}
        if ext == ".py":
            old = self._get_indent(lines[0])
            lines = [line[len(old) :] if line.startswith(old) else line for line in lines]
        root = self.parser.parse("\n".join(lines).encode("utf-8")).root_node
        # One walk down the tree (a node's parent is slow to get): the
        # comments over several lines, and the brackets as (the byte after
        # the bracket, the end of what it opens, its row, whether code
        # follows it on that row and it is a `(` or `[`).
        aligned, brackets, stack = {}, [], [root]
        while stack:
            node = stack.pop()
            if "comment" in node.type:
                for row in range(node.start_point[0] + 1, node.end_point[0] + 1):
                    aligned.setdefault(row, node.start_point[0])
                continue
            children = node.children
            if children and children[0].type in ("(", "[", "{"):
                bracket = children[0]
                after = children[1] if len(children) > 1 else None
                aligns = (
                    bracket.type != "{"
                    and after is not None
                    and after.start_point[0] == bracket.start_point[0]
                    and "comment" not in after.type
                )
                brackets.append((bracket.end_byte, node.end_byte, bracket.start_point[0], aligns))
            stack.extend(reversed(children))
        brackets.sort()
        # The brackets around the start of each line, innermost last.
        around, k, offset = [], 0, 0
        for row, line in enumerate(lines):
            start, offset = offset, offset + len(line.encode("utf-8")) + 1
            code = line.lstrip(" \t")
            if not code:
                continue
            at = start + len(line[: len(line) - len(code)].encode("utf-8"))
            while k < len(brackets) and brackets[k][0] <= at:
                while around and around[-1][1] <= brackets[k][0]:
                    around.pop()
                around.append(brackets[k])
                k += 1
            while around and around[-1][1] <= at:
                around.pop()
            if row and row not in aligned and around and around[-1][2] < row and around[-1][3]:
                aligned[row] = around[-1][2]
        return aligned

    def _tabs_at(self, indent: str, rows: range | None = None) -> bool:
        """
        Whether content that goes in at `indent` is written in tabs
        (_tab_indent): when `indent` has one, or, at column 0, when most of
        the indented lines of the file's lines `rows` (the code it replaces
        or goes beside) start with a tab, the lines that start inside a
        multi-line string (_literal_rows) and those that spaces align with
        a line above (_aligned_rows) aside, or, when none of them is
        indented, in a Go file (gofmt indents with tabs) or one whose
        indentation unit is a tab (_indent_unit). Never in a JSON, YAML or
        TOML file.
        """
        if self.parser.ext in _CONFIG_EXTS:
            return False
        if indent:
            return "\t" in indent
        lines = [self.lines[row] for row in (rows or ()) if row < len(self.lines)]
        aside = {i for found, _ in self._literal_rows(lines) for i in found} | set(self._aligned_rows(lines))
        indents = [self._get_indent(line) for i, line in enumerate(lines) if i not in aside and line.strip(" \t")]
        indents = [ws for ws in indents if ws]
        if indents:
            return sum(ws.startswith("\t") for ws in indents) * 2 > len(indents)
        return self.parser.ext == ".go" or self._indent_unit(" ") == "\t"

    def _tabbed(self, lines: list[str], indent: str, rows: range | None = None, extra=None) -> list[str]:
        """The lines of caller content that goes in at `indent` (beside or
        in place of the file's lines `rows`), in tabs when the file indents
        with them there (_tabs_at, _tab_indent; `extra` the lines that go
        into a string of the file, see _context_literals)."""
        if len(lines) < 2 or not self._tabs_at(indent, rows):
            return lines
        return self._tab_indent(lines, extra)

    def _starts_line(self, byte: int) -> bool:
        """Whether only whitespace precedes `byte` on its line."""
        src = self.parser.source_bytes
        return not src[src.rfind(b"\n", 0, byte) + 1 : byte].strip()

    def _is_aside(self, node) -> bool:
        """Class-body nodes that are not members of their own: comments,
        decorators (TS puts a method's beside it), C++ access labels and
        Ruby Sorbet signatures (`sig { void }`, part of the method below)."""
        return (
            node.type in ("decorator", "access_specifier")
            or "comment" in node.type
            or self._is_sorbet_signature(node)
        )

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
        before it, the way the class separates its methods (C++ member
        templates included, _is_method): 1 if any method has a blank line
        between it (or its decorators, Sorbet signature and leading comment)
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
            if not self._is_method(cur, method_types):
                continue
            start = self._symbol_span(cur)[0].start_point[0]
            if any(not line.strip() for line in self.lines[prev.end_point[0] + 1 : start]):
                return 1
            stacked = True
        if stacked:
            return 0
        return 0 if body.type == "interface_body" and self.parser.ext in _JS_EXTS else 1

    def _is_method(self, node, method_types) -> bool:
        """Whether the class member `node` is a method, one of method_types:
        a C++ member template is what its `template <...>` declares."""
        entity = self._template_entity(node)
        return entity is not None and entity.type in method_types

    def _section_method(self, members):
        """
        For add_method in a C++ class whose body holds `members` (comments
        and access labels included): its last method when an access label
        (`private:`) follows it, which the new method goes after so that it
        gets that method's access rather than the last section's; else None.
        A method is a function the class defines or declares (`int f();`,
        `~A();`, `A& operator=(const A&) = default;`) or a member template
        of one; a friend is no member, and a pointer to a function a field.
        An #if or #ifdef block with a method in one of its branches counts
        as that method (the new one goes after its #endif); one with an
        access label in it leaves today's placement.
        """
        if self.parser.ext not in CPP_EXTS:
            return None

        def is_method(member) -> bool:
            entity = self._template_entity(member)
            return entity is not None and (
                entity.type == "function_definition"
                or (
                    entity.type in ("field_declaration", "declaration")
                    and any(self.parser.c_declares_function(name) for name in self.parser.declared_names(entity))
                )
            )

        def inner(block) -> list:
            # The members in a preprocessor block's branches, nested ones too.
            found = []
            for child in block.named_children:
                found += inner(child) if child.type in _PREPROC_CONDITIONALS else [child]
            return found

        labelled = False
        for member in reversed(members):
            if member.type == "access_specifier":
                labelled = True
                continue
            if member.type in _PREPROC_CONDITIONALS:
                held = inner(member)
                if any(m.type == "access_specifier" for m in held):
                    return None
                if any(is_method(m) for m in held):
                    return member if labelled else None
                continue
            if is_method(member):
                return member if labelled else None
        return None

    def _label_indent(self, members, label, class_indent: bytes) -> bytes:
        """The indentation for the C++ access label `label` when add_method
        moves it to a line of its own: that of the class's first other label
        that starts its line, else the class's own, `class_indent`."""
        for member in members:
            if member.type == "access_specifier" and member.start_byte != label.start_byte and self._starts_line(member.start_byte):
                return self._get_indent(self.lines[member.start_point[0]]).encode("utf-8")
        return class_indent

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
        So is a C++ template's `template <...>` header: a new_signature that
        starts with `template` replaces it (all of them, when a member
        template defined outside its class has two).
        For a JS/TS function bound to a name, a new_signature that starts
        with const/let/var (`const f = (x) =>`) replaces the declaration's
        head as well, and one that does not (`(x) =>`) only the function's.
        So does the other code that starts the signature as
        read_symbol(depth="signature") reads it (_signature_head): a
        new_signature that starts with a key (`handler: (x) =>`, `RunE:
        func() error`), with something else than `def` for a Ruby `private
        def`, or with the first word of that code (`declare`, `extern`,
        `typedef`, a Go `type`) replaces it, and one without keeps it
        (_brings_head). A typedef of a struct without a tag has the header
        of its struct (`typedef struct`). A Ruby endless method's signature
        ends before its `=`.
        A method declared without a body (a TS abstract method, a Java
        interface or abstract method, a C++ `A() = default;`, a Go function
        without one, a C/C++ prototype or a method declared in its class)
        is all signature but its final `;`, which stays whether
        or not new_signature ends with one. A Go struct or interface type and
        an empty Ruby class, module or method have the header
        read_symbol(depth="signature") gives them (_header_span); any other
        symbol (a variable, a constant) is refused.
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = self._typedef_struct(self._callable(node, target), enums=True)

        body = func_node.child_by_field_name("body")
        header = self._header_span(func_node) if body is None else None
        if (
            body is None
            and header is None
            and func_node.type not in _BODILESS_FUNCTIONS
            and func_node.type not in self._interface_func_types()
            and not self._declares_c_function(func_node, target)
        ):
            raise ApplierError(
                f"'{target}' is {self._symbol_kind(func_node, target)}, which has no signature to "
                "replace (replace_signature is for functions and class headers); rewrite "
                "it with replace_function"
            )

        # The signature ends where the body starts; a function declared
        # without one (`abstract m(): void;`, `A() = default;`) is all
        # signature but the `;` that ends it, and a class the grammar gives
        # no body (a Go struct, an empty Ruby class) its header, as
        # _get_signature reads them.
        sig_end = self._signature_end(func_node, body)
        if header is not None:
            sig_end = header[1]
        elif body is None:
            # The final `;` can sit in a child (C++ `= default;`).
            source = self.parser.source_bytes
            sig_end = func_node.end_byte
            if source[sig_end - 1 : sig_end] == b";":
                sig_end -= 1
            while source[sig_end - 1 : sig_end] in (b" ", b"\t"):
                sig_end -= 1

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
        if body is None:
            # The `;` after a bodiless declaration stays in the file.
            new_signature = new_signature.removesuffix(";").rstrip()

        # Decorators and annotations stay unless new_signature brings its
        # own, which then replace them. Python's and TS's sit outside
        # func_node (TS's as siblings in the class body), so new ones widen
        # the span back over them; Java annotations (in `modifiers`) and JS
        # decorators are inside it, so keeping them narrows the span.
        replace_from, kept = func_node.start_byte, ""
        if func_node is not node and node.type in ("lexical_declaration", "variable_declaration"):
            # A JS/TS function bound to a name: `const f = (x) =>`, as
            # read_symbol(depth="signature") gives it, replaces the
            # declaration's head too; `(x) =>` only the function's own.
            if re.match(r"(const|let|var)\b", new_signature):
                replace_from = node.start_byte
        elif node.type == "decorated_definition":
            if new_signature.startswith("@"):
                replace_from = node.start_byte
        elif self.parser.ext in CPP_EXTS:
            # A C++ template's `template <...>` header stays unless the new
            # signature brings its own.
            if re.match(r"template\b", new_signature):
                replace_from = self._symbol_span(func_node)[0].start_byte
        elif self._signature_has_annotations(new_signature):
            prev = func_node.prev_named_sibling
            while prev is not None and prev.type == "decorator":
                replace_from = prev.start_byte
                prev = prev.prev_named_sibling
        else:
            replace_from, kept = self._annotation_span(func_node)
        # The code that wraps the function and starts its signature as
        # read_symbol(depth="signature") reads it (a Go `type`, a closure's
        # key, a TS `declare`, a C++ `extern "C"`, a Ruby `private`, a C
        # typedef) stays unless new_signature brings its own.
        head = self._signature_head(node, func_node)
        if (
            head is not func_node
            and head.type not in ("lexical_declaration", "variable_declaration", "template_declaration")
            and self._brings_head(head, func_node, new_signature)
        ):
            replace_from, kept = head.start_byte, ""
        # So does a Ruby method's Sorbet signature, as decorators do.
        sig = self._sorbet_signature(func_node) if self.parser.ext == ".rb" else None
        if sig is not None and re.match(r"sig\b\s*(?:[({]|do\b)", new_signature.lstrip()):
            replace_from, kept = sig.start_byte, ""

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
        Return a formatted outline of the file's symbols: its top-level
        functions, classes and other declarations, the members of each
        class (nested classes and their members included) and of namespaces
        and modules. Read-only. Output is a multi-line string: one entry per
        line, formatted as `<kind> <name> (line N)`, the name being the
        symbol's target (`A.B.m`), each member indented two spaces deeper
        than its container (see _list_scope). Data is listed in every
        language: a Python module-level name is a `variable` and a class
        attribute a `field` (one assigned again is listed once), a JS/TS
        `const` a `constant` and a `let` or `var` a `variable`, each name of
        it, a JS/TS class field a `field`, a Ruby constant a `constant` and
        a Ruby local a `variable`; names that a pattern binds (`a, b = 1,
        2`), which are no targets, and fields named by a string or computed
        key are not listed. In JS/TS, generator functions and each name of a
        `const`/`let`/`var` bound to an arrow function or function
        expression are functions; TS abstract classes
        are classes (their abstract methods listed with the other methods,
        an overloaded one once), enums, type aliases, interfaces and
        namespaces are `enum`, `type`, `interface` and `namespace`, and a
        function declared without a body (`declare function f(): void;`, an
        overload signature) is a function. C/C++ structs, unions, enums and
        namespaces are listed under those names, typedefs and `using`
        aliases as `type`, `#define`s as `macro`, data members as `field`
        and other data as `variable`, or `constant` when `const` or
        `constexpr`; prototypes and methods declared in their class are
        functions and methods, and the declarations in preprocessor
        conditionals and `extern "C"` are listed as the others are. Of the
        declarations of one name in a scope, the target's are listed
        (_list_scope): a definition rather than what only announces it
        (`struct S;`, a prototype, an `extern` variable, a TS overload
        signature, a Python @overload stub), which is listed once when the
        scope has no definition of it. In C, C++, Java, JS and TS each entry
        is listed under the target that finds it (_listed_names): C++ and
        Java overloads with their parameter types (`A.m(int)`), a method
        beside a field of its name too (`A.x()`), and a C/C++ tag or TS type
        that shares its name with another symbol after its keyword (`struct
        stat`, `type User`), so that the line reads `struct struct stat`.
        C++ templates (functions, classes and member templates) are listed
        as what they declare, at the line of their `template <...>` header;
        a definition outside its class is a function under its qualified
        name (`A::f`, `A::A`), and destructors and operators are named `~A`,
        `operator==`, `operator bool`. Java fields are fields, and Ruby
        methods include `private def` ones and those in `class << self`. Go
        has its own listing (_list_symbols_go).
        """
        ext = self.parser.ext
        root = self.parser.tree.root_node
        if ext == ".go":
            return self._list_symbols_go(root)
        if ext not in (".py", ".rb", ".java") + _JS_EXTS + C_EXTS + CPP_EXTS:
            raise ApplierError(f"list_symbols is not supported for file type {ext}")
        lines_out: list[str] = []
        self._list_scope([(root, False)], "", 0, lines_out)
        if not lines_out:
            return "(no top-level symbols found)"
        return "\n".join(lines_out)

    def _list_scope(self, scopes: list, prefix: str, depth: int, out: list[str]) -> None:
        """
        Append to `out` the list_symbols entries for the symbols that the
        `scopes` of one container declare, as (scope, in_class) pairs: the
        file's root, a class, namespace or module body, or the blocks of a
        merged namespace (below). `prefix` (`A.`) goes before their names,
        each entry is indented two spaces per `depth`, and each container is
        followed by its own members. In C, C++, Java, JS and TS each entry
        is listed under the target that finds it (_listed_names), and one
        that no target finds is left out: a declaration that only announces
        a definition (`struct S;`, a prototype, an `extern` variable, a TS
        overload signature), a second alternative in a C/C++ preprocessor
        conditional (`#ifdef X` ... `#else` ... `#endif`), a repeated
        declaration, a TS setter beside its getter, a JS/TS class field
        beside a method of its name; the members of the one container of a
        name that something else takes (a Java class and a field of its
        name) are still listed, at its depth, as they are found through it.
        A TS interface merged with a class and a namespace lists no members
        of its own, theirs being under the first. In Python and Ruby, of
        the entries for one name (_list_entries), those of the rank the
        target has (TreeSitterParser.definition_rank) are listed, the first
        of them once when they only announce it (Python @overload stubs);
        a name defined again is listed again, but a name assigned again
        (`X = 1` ... `X = 2`, or after a def of its name) is not, as its
        name targets the first. A namespace opened more than
        once in a scope, or merged with a TS class, function or enum, is
        listed once, as what its name targets, with the members of all of
        its blocks (TreeSitterParser.merged_containers).
        """
        entries = [
            e for scope, in_class in scopes for child in self._scope_members(scope) for e in self._list_entries(child, in_class)
        ]
        merged = {name for kind, name, _node, _rank, _body in entries if kind == "namespace"}
        best: dict[str, int] = {}
        bodies: dict[str, list] = {}
        for kind, name, _node, rank, body in entries:
            best[name] = min(best.get(name, rank), rank)
            if body is not None:
                bodies.setdefault(name, []).append((body, kind != "namespace"))
        targeted = self.parser.ext in C_EXTS + CPP_EXTS + _JS_EXTS + (".java",)
        shown = self._listed_names(entries, [scope for scope, _ in scopes]) if targeted else None
        listed = set()
        for i, (kind, name, node, rank, body) in enumerate(entries):
            if shown is not None:
                if shown[i] is None:
                    if body is not None and name not in merged and not any(
                        j != i and e[1] == name and e[4] is not None for j, e in enumerate(entries)
                    ):
                        # The one container of a name that something else
                        # takes (a Java field and a class of its name): its
                        # members are found through it (`A.B.m`).
                        self._list_scope([(body, kind != "namespace")], f"{prefix}{name}.", depth, out)
                    continue
                keyword, label = shown[i]
                label = f"{keyword} {prefix}{label}" if keyword is not None else f"{prefix}{label}"
            elif rank > best[name] or (
                name in listed and (rank == 2 or name in merged or kind in ("variable", "field", "constant"))
            ):
                continue
            else:
                label = f"{prefix}{name}"
            listed.add(name)
            line = self._symbol_span(node)[0].start_point[0] + 1
            out.append(f"{'  ' * depth}{kind} {label} (line {line})")
            if name in merged:
                # Under the first entry of the name only (a TS interface
                # merged with them too is listed apart, without them).
                members = bodies.pop(name, [])
            else:
                members = [(body, kind != "namespace")] if body is not None else []
            if members:
                self._list_scope(members, f"{prefix}{name}.", depth + 1, out)

    def _listed_names(self, entries: list, scopes: list) -> list:
        """
        For the list_symbols entries of one container (_list_entries tuples)
        declared in `scopes`, the target each is listed under, as (keyword or
        None, last part), or None for one that no target finds: its name
        when that finds it (a C++ definition outside its class by its
        qualified name, `A::A`); else, for a C/C++ tag or TS type, its name
        after its keyword (`struct stat`, `type User`); else, for a C, C++
        or Java function that its name does not find another declaration
        of (an overload, a method beside a field of its name), its name with
        its parameter types (`m(int)`), and its C++ qualifiers when those
        tell it apart (`get(int) const`). The declarations weighed are those
        TreeSitterParser.select picks a target among, so each name targets
        its entry. An entry that is no such declaration (an anonymous
        `export default`) is listed under its name, once.
        """
        parser = self.parser
        class_types, func_types, var_types = parser.target_types()
        types = class_types + func_types + var_types
        declared_in = set(scopes) | {parser._scope(node) for _kind, _name, node, _rank, _body in entries}
        found = parser.scope_declarations(sorted(declared_in, key=lambda s: s.start_byte), types)
        shown, taken = [], set()
        for _kind, name, node, _rank, _body in entries:
            own = next((c for c in found.get(name, []) if c.node == node), None)
            if own is None:
                label = None if (None, name) in taken else (None, name)
            else:
                label = self._listed_target(own, found[name])
            if label is not None:
                taken.add(label)
            shown.append(label)
        return shown

    def _listed_target(self, own, found: list):
        """_listed_names for the declaration `own` among `found`, the
        declarations of its name in its scope (TreeSitterParser.Candidate
        tuples)."""
        parser = self.parser

        def finds(keyword, params, qualifiers):
            try:
                return parser.select(found, Target("", keyword, [""], own.names, params, qualifiers))
            except ApplierError:
                return None

        name = "::".join(own.names)
        alone = finds(None, None, None)
        if alone == own.node:
            return None, name
        if own.keyword is not None and finds(own.keyword, None, None) == own.node:
            return own.keyword, name
        typed = parser.ext in C_EXTS + CPP_EXTS + (".java",)
        if not (own.function and typed) or any(c.node == alone and c.function for c in found):
            return None
        label = f"{name}({', '.join(own.params)})"
        if finds(None, own.key, None) == own.node:
            return None, label
        if own.qualifiers and finds(None, own.key, own.qualifiers) == own.node:
            return None, f"{label} {own.qualifiers}"
        return None

    def _scope_members(self, scope):
        """The nodes that list_symbols looks at in `scope`, in document
        order: its named children, with what C/C++ preprocessor
        conditionals (not their conditions), `extern "C"` and anonymous
        namespaces hold, a Java enum's members after its constants and the
        methods of a Ruby `class << self` in their place."""
        for i, child in enumerate(scope.children):
            if not child.is_named or (
                scope.type in _PREPROC_CONDITIONALS and scope.field_name_for_child(i) in ("name", "condition")
            ):
                continue
            if child.type in _PREPROC_CONDITIONALS:
                yield from self._scope_members(child)
            elif child.type == "linkage_specification":
                body = child.child_by_field_name("body")
                if body is not None and body.type == "declaration_list":
                    yield from self._scope_members(body)
                elif body is not None:
                    yield body
            elif (
                child.type == "namespace_definition" and child.child_by_field_name("name") is None
            ) or child.type in ("enum_body_declarations", "singleton_class"):
                yield from self._scope_members(child.child_by_field_name("body") or child)
            else:
                yield child

    def _list_entries(self, node, in_class: bool) -> list:
        """
        The list_symbols entries for `node`, a statement or member of a
        scope (_scope_members), as (kind, name, node, rank, body) tuples:
        what it is, the name it is targeted by, the node whose span gives
        its line, its definition_rank and, for a class, namespace or module,
        the body holding its members (else None). Wrappers (a JS/TS `export`
        or `declare`, a Python decorator, a C++ template, a Ruby `private`)
        are looked through. A function is a `method` in a class or module.
        Data is a `variable`, `constant` or `field`, as in C/C++ and Go: a
        Python assignment to a name (a `field` in a class), each name of a
        JS/TS `const` (a `constant`) or `let`/`var` (bound to a function, a
        function), a JS/TS class field, a Ruby constant or local.
        """
        parser, ext = self.parser, self.parser.ext
        function = "method" if in_class else "function"
        if node.type == "export_statement":
            declaration = node.child_by_field_name("declaration")
            if declaration is None:
                value = parser.anonymous_default_export(node)
                if value is None:
                    return []
                if value.type == "class":
                    return [("class", "default", value, 0, value.child_by_field_name("body"))]
                return [(function, "default", value, 0, None)]
            node = declaration
        if ext in _JS_EXTS and node.type in ("ambient_declaration", "expression_statement"):
            # `declare ...`, and a TS `namespace N {}`, which the grammar
            # makes an expression statement.
            inner = node.named_children[0] if len(node.named_children) == 1 else None
            if inner is None or (node.type == "expression_statement" and inner.type != "internal_module"):
                return []
            return self._list_entries(inner, in_class)
        if node.type == "decorated_definition":
            definition = node.child_by_field_name("definition")
            if definition is None:
                return []
            if definition.type == "class_definition":
                node = definition
            else:
                # An @overload stub ranks below its implementation.
                name = definition.child_by_field_name("name")
                return [(function, parser.node_text(name), node, parser.definition_rank(node, name), None)] if name is not None else []
        if node.type == "template_declaration":
            node = self._template_entity(node) or node
        if ext == ".rb" and node.type == "call":
            # `private def m`
            node = self._ruby_wrapped_method(node)
            if node is None:
                return []
        if ext in C_EXTS + CPP_EXTS:
            return self._c_list_entries(node, in_class)

        name_node = node.child_by_field_name("name")
        name = parser.node_text(name_node) if name_node is not None else None
        kind = {
            "class_definition": "class",
            "class_declaration": "class",
            "abstract_class_declaration": "class",
            "class": "class",
            "module": "namespace" if ext in _JS_EXTS else "module",
            "internal_module": "namespace",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "record_declaration": "record",
        }.get(node.type)
        if kind is not None:
            if name is None or (name_node.type not in ("identifier", "constant", "type_identifier", "scope_resolution")):
                return []
            # TS interfaces and enums list no members.
            listed = ext not in _JS_EXTS or kind in ("class", "namespace")
            body = node.child_by_field_name("body") if listed else None
            return [(kind, name, node, parser.definition_rank(node, name_node), body)]
        if node.type in (
            "function_definition",
            "function_declaration",
            "generator_function_declaration",
            "method_definition",
            "method",
            "singleton_method",
            "method_declaration",
            "constructor_declaration",
        ):
            return [(function, name or "<anonymous>", node, 0, None)]
        if node.type in ("function_signature", "abstract_method_signature"):
            # Overloads, an abstract method's included, are listed once.
            return [(function, name, node, 2, None)] if name is not None else []
        if node.type == "type_alias_declaration":
            return [("type", name, node, 0, None)]
        if node.type in ("field_declaration", "constant_declaration") and ext == ".java":
            return [("field", parser.node_text(n), node, parser.definition_rank(node, n), None) for n in parser.declared_names(node)]
        if node.type in ("lexical_declaration", "variable_declaration") and ext in _JS_EXTS:
            # Each name of a `const`/`let`/`var`: a function when the name's
            # declarator binds one (`const f = () => {}`).
            data = "constant" if node.children[0].type == "const" else "variable"
            entries = []
            for declarator in (c for c in node.named_children if c.type == "variable_declarator"):
                name_node, value = declarator.child_by_field_name("name"), declarator.child_by_field_name("value")
                if name_node is not None and name_node.type == "identifier":
                    bound = value is not None and value.type in JS_FUNCTION_VALUES
                    entries.append((function if bound else data, parser.node_text(name_node), node, 0, None))
            return entries
        if node.type in ("public_field_definition", "field_definition"):
            # A JS/TS class field; one named by a string or computed key
            # (`'a-b' = 1`, `[k] = 1`) is left out.
            names = [n for n in parser.declared_names(node) if n.type in ("property_identifier", "private_property_identifier")]
            return [("field", parser.node_text(n), node, 0, None) for n in names]
        if node.type == "expression_statement" and ext == ".py":
            # An assignment to a name (`X = 1`, `x: int`), not a pattern.
            names = [n for n in parser.declared_names(node) if n.type == "identifier"]
            return [("field" if in_class else "variable", parser.node_text(n), node, 0, None) for n in names]
        if node.type == "assignment" and ext == ".rb":
            return [
                ("constant" if n.type == "constant" else "variable", parser.node_text(n), node, 0, None)
                for n in parser.declared_names(node)
            ]
        return []

    def _c_list_entries(self, node, in_class: bool) -> list:
        """_list_entries for a C/C++ node: a function, a class, struct,
        union, enum or namespace, a declaration (its type when that is
        defined there, `struct B {...} b;`, then each name it declares), a
        typedef (a struct it defines, then its names; the struct of `typedef
        struct {...} P;` is P's body), a `using` alias or a macro."""
        parser = self.parser
        function = "method" if in_class else "function"
        kinds = {"class_specifier": "class", "struct_specifier": "struct", "union_specifier": "union", "enum_specifier": "enum"}
        if node.type == "function_definition":
            names = parser.c_declared_names(node)
            return [(function, parser.symbol_name(names[0]), node, 0, None)] if names else []
        if node.type in kinds or node.type == "namespace_definition":
            names = parser.c_declared_names(node)
            if not names:
                return []
            body = node.child_by_field_name("body")
            kind = kinds.get(node.type, "namespace")
            rank = parser.definition_rank(node, names[0])
            members = body if body is not None and kind != "enum" else None
            return [(kind, parser.node_text(names[0]), node, rank, members)]
        if node.type in ("alias_declaration", "preproc_def", "preproc_function_def"):
            names = parser.c_declared_names(node)
            kind = "type" if node.type == "alias_declaration" else "macro"
            return [(kind, parser.node_text(names[0]), node, 1, None)] if names else []
        if node.type not in ("declaration", "field_declaration", "type_definition"):
            return []
        entries = []
        type_node = node.child_by_field_name("type")
        tag = None
        if type_node is not None and type_node.type in kinds:
            entries = self._c_list_entries(type_node, in_class)
            tag = entries[0][1] if entries else None
        for name in parser.c_declared_names(node):
            text = parser.symbol_name(name)
            if node.type == "type_definition":
                if text == tag:
                    continue
                inner = None
                if tag is None and type_node is not None and type_node.type in kinds and not any(e[0] == "type" for e in entries):
                    # The anonymous struct of `typedef struct {...} P;`.
                    body = type_node.child_by_field_name("body")
                    inner = body if body is not None and type_node.type != "enum_specifier" else None
                entries.append(("type", text, node, 1, inner))
            elif parser.c_declares_function(name):
                entries.append((function, text, node, 2, None))
            else:
                kind = "field" if node.type == "field_declaration" else "constant" if self._c_constant(node, name) else "variable"
                entries.append((kind, text, node, parser.definition_rank(node, name), None))
        return entries

    def _c_constant(self, declaration, name) -> bool:
        """Whether the C/C++ declaration of `name` declares a constant: it is
        `constexpr`, or `const` and no pointer (`const char *p` points at
        constants, but is a variable)."""
        qualifiers = {self.parser.node_text(c) for c in declaration.children if c.type == "type_qualifier"}
        if "constexpr" in qualifiers:
            return True
        if "const" not in qualifiers:
            return False
        node = name.parent
        while node is not None and node != declaration:
            if node.type == "pointer_declarator":
                return False
            node = node.parent
        return True

    def _get_signature(self, target: str) -> str:
        """
        Return the signature text of a function (everything before its body),
        with surrounding whitespace stripped. Read-only. It starts where
        read_symbol's full text does, but after a JS/TS `export` and Python
        decorators (_signature_head): at the `const`/`let`/`var` a JS/TS
        function is bound to (`const f = (x) =>`), a closure's key
        (`handler: () =>`), a C++ template's `template <...>` header or
        `extern "C"`, a TS `declare`, a Ruby `private` and the C/C++ typedef
        or declaration a struct is the type of (`typedef struct N`); a
        typedef of a struct, union or enum without a tag is that type's
        (`typedef struct`). A Ruby endless method's ends before its `=`
        (_signature_end). A method or function with no body (a TS abstract
        method, a Java interface method, a C++ `A() = default;`, a Go
        function declared without one, a C/C++ prototype or method declared
        in its class, see _declares_c_function) is its whole text, without
        the final `;`. A class's signature is its header, also when the
        grammar gives it no body (_header_without_body). Any other symbol (a
        variable, a constant, a type alias, a macro) has no signature and is
        refused (_depth_refusal).
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = self._typedef_struct(self._callable(node, target), enums=True)
        head = self._signature_head(node, func_node)
        src = self.parser.source_bytes

        body = func_node.child_by_field_name("body")
        if body is None:
            span = self._header_span(func_node)
            if span is not None:
                return src[min(head.start_byte, span[0]) : span[1]].decode("utf-8")
            if (
                func_node.type in _BODILESS_FUNCTIONS
                or func_node.type in self._interface_func_types()
                or self._declares_c_function(func_node, target)
            ):
                text = src[head.start_byte : func_node.end_byte].decode("utf-8")
                return text.strip().rstrip(";").rstrip()
            raise self._depth_refusal(target, func_node, "signature")

        signature = src[head.start_byte : self._signature_end(func_node, body)].decode("utf-8")
        return signature.strip()

    def _signature_head(self, node, func_node):
        """
        The node whose start the signature of func_node, the function or
        class found as `node`, starts at: the outermost of the nodes around
        it that the symbol's full text starts with (_symbol_unit), short of
        a JS/TS `export` and a Python decorated_definition, which the
        signature leaves out. That is a Go `type` declaring only it, the key
        of a closure (`handler: () => {}`, `RunE: func() error {}`), a TS
        `declare`, a C++ `extern "C"` or `template <...>` header, a Ruby
        `private def`, the `const`/`let`/`var` a JS/TS function is bound to
        and the C/C++ typedef or declaration a struct is the type of; else
        func_node itself, as when the full text starts with other nodes (a
        TS function's overload signatures, a Python function's @overload
        stubs, the decorators the TS grammar places beside a method) and for
        a Go func literal that is one of several values (`var p, q =
        func() {}, func() {}`).
        """
        values = func_node.parent if func_node.type == "func_literal" else None
        if values is not None and values.type == "expression_list" and len(values.named_children) > 1:
            # One of the values of a Go `var p, q = func() {...}, func()
            # {...}`: the others are no part of it.
            return func_node
        first, last = self._symbol_unit(node)
        if self._is_sorbet_signature(first):
            # A Ruby method's Sorbet signature is no part of its own.
            first = last
        path, cur = [], func_node
        while cur is not None and cur != first:
            cur = cur.parent
            path.append(cur)
        head = func_node
        if cur is None:
            return head
        for parent in path:
            if parent.type in ("export_statement", "decorated_definition"):
                break
            head = parent
        return head

    def _brings_head(self, head, func_node, signature: str) -> bool:
        """
        For replace_signature: whether the new `signature` of func_node
        starts with code of its own in place of what `head`
        (_signature_head) writes before the function, which it then
        replaces: a key and its `:` for a closure (`handler: (a) =>`, `RunE:
        func() error`), anything before the `def` of a Ruby method that
        follows other code (`protected def m`), and else the first word of
        that code (`declare`, `extern`, `typedef`, `type`, `template`).
        """
        prefix = self.parser.source_bytes[head.start_byte : func_node.start_byte].decode("utf-8")
        signature = signature.lstrip()
        if head.type in ("pair", "keyed_element"):
            key = r"""(?:[\w$]+|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\[[^\]]*\])"""
            return re.match(key + r"\s*:(?!:)", signature) is not None
        if self.parser.ext == ".rb":
            return re.match(r"def\b", signature) is None
        word = re.match(r"[\w$]+", prefix.lstrip())
        return word is not None and re.match(re.escape(word.group(0)) + r"\b", signature) is not None

    def _signature_end(self, func_node, body) -> int:
        """The byte where the signature of func_node, the function or class
        whose body is `body`, ends: after its last child before the body,
        or, for a Ruby endless method (`def f(x) = x + 1`), before its `=`."""
        endless = self.parser.ext == ".rb" and func_node.type in ("method", "singleton_method")
        end = func_node.start_byte
        for child in func_node.children:
            if child == body or (endless and child.type == "="):
                break
            end = child.end_byte
        return end

    def _header_without_body(self, node) -> str | None:
        """
        The signature read_symbol(depth="signature") gives a class, method
        or function `node` that the grammar gives no body: a Go struct or
        interface type is its header up to the `{` (`type A struct`, from its
        `type` when that declares only it), and a Ruby class, module or
        method with nothing in its body is its text before the `end`
        (`class A < B`). None for any other node. See _header_span.
        """
        span = self._header_span(node)
        if span is None:
            return None
        return self.parser.source_bytes[span[0] : span[1]].decode("utf-8")

    def _header_span(self, node) -> tuple[int, int] | None:
        """The bytes [start, end) of the header _header_without_body gives
        `node`, which replace_signature replaces, or None."""
        src = self.parser.source_bytes
        if node.type == "type_spec":
            kind = node.child_by_field_name("type")
            if kind is None or kind.type not in ("struct_type", "interface_type"):
                return None
            start = node.parent if node.prev_sibling is not None and node.prev_sibling.type == "type" else node
            return start.start_byte, kind.children[0].end_byte
        if self.parser.ext in (".rb",) and node.type in ("class", "module", "method", "singleton_method"):
            end = node.children[-1]
            if end.type != "end":
                return None
            header = src[node.start_byte : end.start_byte].rstrip().rstrip(b";").rstrip()
            return node.start_byte, node.start_byte + len(header)
        return None

    def _symbol_kind(self, node, target: str = "") -> str:
        """
        What _depth_refusal calls `node`, a symbol that is neither a function
        nor a class, found for `target`, with its article: a constant (a
        JS/TS or Go `const`, a Ruby constant, a C/C++ `const` or `constexpr`
        that is no pointer), a variable (a Python assignment outside a class,
        too), a field (a Python class attribute, a JS/TS class field, a Java
        field, a C/C++ data member), a type alias (a TS or Go alias, a C/C++ typedef or `using`
        alias), a macro, a Go type definition (`type N int`) or a C/C++
        forward declaration (`struct S;`).
        """
        if node.type in ("lexical_declaration", "variable_declaration"):
            return "a constant" if node.children[0].type == "const" else "a variable"
        if node.type == "assignment" and self.parser.ext in (".rb",):
            left = node.named_children[0] if node.named_children else None
            return "a constant" if left is not None and left.type == "constant" else "a variable"
        if node.type == "expression_statement":
            block = node.parent
            in_class = block is not None and block.parent is not None and block.parent.type == "class_definition"
            return "a field" if in_class else "a variable"
        if node.type in _C_TYPE_SPECIFIERS:
            return "a forward declaration"
        if node.type == "declaration" and self.parser.ext in C_EXTS + CPP_EXTS:
            name = self.parser.declared_name(node, self.parser.target_leaf(target))
            return "a constant" if name is not None and self._c_constant(node, name) else "a variable"
        kinds = {
            "const_spec": "a constant",
            "var_spec": "a variable",
            "field_declaration": "a field",
            "constant_declaration": "a field",
            "public_field_definition": "a field",
            "field_definition": "a field",
            "type_alias_declaration": "a type alias",
            "type_alias": "a type alias",
            "type_definition": "a type alias",
            "alias_declaration": "a type alias",
            "preproc_def": "a macro",
            "preproc_function_def": "a macro",
            "type_spec": "a type definition",
        }
        return kinds.get(node.type, "a declaration")

    def _depth_refusal(self, target: str, node, depth: str) -> ApplierError:
        """
        The error for read_symbol(depth="signature") or depth="interface" on
        `node`, found for `target`, a symbol that is neither a function nor a
        class: what it is (_symbol_kind) and what the depth is for. A Go
        type's interface lists its methods, so a Go type's signature refusal
        points there too.
        """
        if depth == "signature":
            reason = "which has no signature (depth='signature' is for functions and class headers)"
        else:
            reason = "which has no interface (depth='interface' is for classes and functions)"
        hint = "depth='full'"
        if node.type == "type_spec":
            hint = "depth='interface' for its methods, or depth='full'"
        spec = node.child_by_field_name("type") if node.type == "type_definition" else None
        tag = spec.child_by_field_name("name") if spec is not None and spec.type in _C_TYPE_SPECIFIERS else None
        if tag is not None and spec.child_by_field_name("body") is None and self.parser.find_container(target) != node:
            # `typedef struct Node Node;` names a struct declared apart.
            keyword = spec.type.split("_")[0]
            path = ".".join(self.parser.parse_target(target).parts[:-1] + [self.parser.node_text(tag)])
            hint += f", and the {keyword} it names with '{keyword} {path}'"
        return ApplierError(f"'{target}' is {self._symbol_kind(node, target)}, {reason}; read it with {hint}")

    def _get_function_body_node(self, target: str, empty_ok: bool = False):
        """Resolve target to (function node, body block node): the
        block/statement_block/compound_statement/body_statement/constructor_body
        of the function (see _callable). An arrow function whose body is an
        expression (`() => x`) has no block, and is refused, as is a Ruby
        endless method (`def f = x`). An empty Ruby method (_empty_method)
        has no body node either: with `empty_ok` the body is None, else it
        is refused, as there is nothing in it to match."""
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = self._callable(node, target)
        if (
            self.parser.ext == ".rb"
            and func_node.type in ("method", "singleton_method")
            and func_node.children[-1].type != "end"
        ):
            raise ApplierError(
                f"'{target}' is an endless method (`def name = expression`), not a body "
                "of statements; rewrite it with replace_function"
            )

        body = func_node.child_by_field_name("body")
        if body is None:
            for child in func_node.children:
                if child.type in ("block", "statement_block", "compound_statement", "body_statement", "constructor_body"):
                    body = child
                    break
        if body is None and self._empty_method(func_node):
            if empty_ok:
                return func_node, None
            raise ApplierError(
                f"The body of '{target}' is empty, so no snippet or anchor can match in it. "
                "Add code with insert_in_body(at='top') or replace_function_body."
            )
        if body is None:
            raise ApplierError(f"Could not find body block for target '{target}'")
        if func_node.type == "arrow_function" and body.type != "statement_block":
            tool = "replace_function" if func_node.parent.type == "variable_declarator" else "replace_value"
            raise ApplierError(
                f"'{target}' is an arrow function with an expression body "
                f"(`(...) => expression`), not a block of statements; rewrite it "
                f"with {tool}"
            )
        return func_node, body

    def _empty_method(self, func_node) -> bool:
        """Whether func_node is a Ruby method with an empty body (`def f`
        over `end`, `def h; end`), which tree-sitter gives no body node: no
        code between its signature and its `end`, maybe comments."""
        return (
            self.parser.ext == ".rb"
            and func_node.type in ("method", "singleton_method")
            and func_node.children[-1].type == "end"
            and func_node.child_by_field_name("body") is None
            and not any(c.type == "body_statement" for c in func_node.children)
        )

    def _empty_method_rows(self, func_node) -> tuple[int, int]:
        """The row where the signature of an empty Ruby method
        (_empty_method) ends (_body_opening) and the row of its `end`, the
        same for a method on one line (`def h; end`)."""
        opening = self._body_opening(func_node, None)
        return self.parser.source_bytes.count(b"\n", 0, opening), func_node.children[-1].start_point[0]

    @staticmethod
    def _ruby_clause(body):
        """The first rescue, else or ensure clause of the Ruby method body
        `body` (a body_statement), or None; the code before it is what the
        method runs (replace_function_body replaces only that)."""
        if body is None or body.type != "body_statement":
            return None
        return next((c for c in body.named_children if c.type in ("rescue", "else", "ensure")), None)

    def _ruby_method_body(self, content: str):
        """The body_statement that Ruby body `content` parses to as the body
        of a method, for _ruby_clause, or None."""
        root = self.parser.parse(("def _\n" + content + "\nend\n").encode("utf-8")).root_node
        method = next((c for c in root.named_children if c.type == "method"), None)
        return next((c for c in method.children if c.type == "body_statement"), None) if method is not None else None

    def _ruby_clause_lines(self, func_node, body, base: str, unit: str) -> bytes | None:
        """
        For _rebuild_body: the source from the first rescue, else or ensure
        clause of the Ruby method func_node to the end of the file, with the
        clauses rebuilt over lines of their own when they share a line with
        their code or the method's `end` (`rescue; y; end`): each clause's
        header (`rescue A => e`) on a line of its own at `base`, each of its
        statements on one at `base` and `unit`, and the `end` at `base`; a
        comment after a statement on its line stays there. None when they
        are on lines of their own already, and when a statement goes over
        several lines or a comment is outside the clauses' statements, which
        keep their text then.
        """
        src = self.parser.source_bytes
        end = func_node.children[-1]
        clauses = [c for c in body.named_children if c.type in ("rescue", "else", "ensure")]
        if end.type != "end" or not clauses:
            return None
        parts, held = [], set()
        laid_out = self._starts_line(end.start_byte)
        for clause in clauses:
            then = next((c for c in clause.named_children if c.type == "then"), None)
            if clause.type == "rescue":
                head = [c for c in clause.children if c.type not in ("then", ";") and "comment" not in c.type]
                items = (list(then.named_children) if then is not None else []) + [
                    c for c in clause.named_children if "comment" in c.type
                ]
            else:
                head = clause.children[:1]
                items = list(clause.named_children)
            items = sorted((c for c in items if c.type != "empty_statement"), key=lambda c: c.start_byte)
            header = src[clause.start_byte : head[-1].end_byte]
            laid_out = laid_out and self._starts_line(clause.start_byte)
            lines, row, last = [header], head[-1].end_point[0], head[-1].end_byte
            for item in items:
                if item.start_point[0] != item.end_point[0]:
                    return None
                code = src[item.start_byte : item.end_byte]
                if "comment" in item.type:
                    held.add(item.start_byte)
                    if item.start_point[0] == row:
                        gap = src[last : item.start_byte]
                        lines[-1] += gap if gap and not gap.strip(b" \t") else b" "
                        lines[-1] += code
                        last = item.end_byte
                        continue
                laid_out = laid_out and self._starts_line(item.start_byte)
                lines.append((base + unit).encode("utf-8") + code)
                row, last = item.end_point[0], item.end_byte
            parts.append(lines)
        # A comment or heredoc elsewhere between the first clause and the
        # `end` would be lost.
        stack = [func_node]
        while stack:
            node = stack.pop()
            if node.end_byte <= clauses[0].start_byte or node.start_byte >= end.start_byte:
                continue
            if node.type == "heredoc_body" or ("comment" in node.type and node.start_byte not in held):
                return None
            stack.extend(node.named_children)
        if laid_out:
            return None
        indent = base.encode("utf-8")
        rebuilt = []
        for i, clause_lines in enumerate(parts):
            rebuilt.append((indent if i else b"") + clause_lines[0])
            rebuilt.extend(clause_lines[1:])
        return b"\n".join(rebuilt) + b"\n" + indent + src[end.start_byte :]

    def replace_in_body(self, target: str, old_snippet: str, new_snippet: str) -> str:
        """
        Replace a snippet inside a function body with new_snippet
        (_replace_in_body_bytes). The match is scoped to the target's body
        so accidental matches elsewhere in the file are impossible, and is
        found as _find_snippet finds it: the snippet's exact text at token
        boundaries, else its whole lines with their indentation shifted.

        Raises if the snippet is not found, or if it matches more than one
        place (include more context to disambiguate).
        """
        func_node, body = self._get_function_body_node(target)
        return self._replace_in_body_bytes(body, old_snippet, new_snippet, target)

    def delete_in_body(self, target: str, snippet: str) -> str:
        """
        Delete a snippet inside a function body, matched as replace_in_body
        matches one, with the lines it leaves without code (_deleted_span).
        Scoped to the target's body. Raises if not found or if the snippet
        matches more than one place -- include more context to disambiguate.
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
          - after=<snippet>:  insert after an anchor.
          - before=<snippet>: insert before an anchor.

        The anchor (for `after`/`before`) is matched as replace_in_body
        matches a snippet, scoped to the target's body, and must be unique;
        multiple matches raise. Where new_snippet goes, and how it is
        indented, is _insert_in_body_bytes's.
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
        """
        Replace the one place old_snippet matches in a body (_find_snippet)
        with new_snippet, indented as the snippet was matched
        (_matched_content): moved with a shifted match's lines, and, after
        an exact one-line snippet that left out (some of) the indentation of
        its line, its later lines given that indentation too, unless they
        have it already; in Python the reading of its indentation that
        parses wins (_parsing_choice). After an exact snippet of several
        lines, which matched them at their file indentation, it goes in as
        written, but for indentation steps in spaces where the file indents
        with tabs, which become tabs (_tabbed). The lines of new_snippet
        that go into a string of the file keep their text
        (_context_literals). An empty new_snippet deletes the match, with
        the lines it leaves without code (_deleted_span), and is refused
        when that would leave a Python body without a statement.
        """
        start, end, shift = self._find_snippet(body_node, old_snippet, target)
        source_bytes = self.parser.source_bytes
        if not new_snippet:
            start, end = self._deleted_span(start, end)
            self._keep_a_statement(body_node, start, end, target)
            text = ""
        else:
            given = new_snippet.replace("\r\n", "\n")
            extra = self._context_literals(start, end, given)
            if shift is not None:
                text, other = self._matched_content(given, shift, lead=True, extra=extra)
            elif sum(1 for line in _content_lines(old_snippet) if line.strip(" \t")) == 1:
                text, other = self._matched_content(given, self._snippet_frame(start, end), lead=False, extra=extra)
            else:
                depth = self._snippet_frame(start, end)[2]
                text, other = "\n".join(self._tabbed(given.split("\n"), depth, extra=extra)), None
            text = self._parsing_choice(
                lambda t: source_bytes[:start] + t.encode("utf-8") + source_bytes[end:], text, other
            )
        self._write_bytes(source_bytes[:start] + text.encode("utf-8") + source_bytes[end:], (start, end))
        return "Update successful"

    def _insert_in_body_bytes(self, body_node, anchor_snippet, new_snippet, place, target):
        """
        Insert new_snippet after or before the one place anchor_snippet
        matches in a body (_find_snippet). An anchor that ends its line
        (after: it ends with its line break, or only spaces, tabs and a
        comment follow it there) or starts it (before: only indentation
        precedes it), on a line of the body and not in the text of a
        string, has new_snippet go in as lines of their own, below or above
        the anchor's lines, indented as the anchor was matched
        (_matched_content, with _snippet_frame for an exact match; content
        at column 0 beside an anchor that left out no indentation as if it
        had left out all of it), and moved into the block that the anchor's
        last line opens (_into_block); in Python the reading of its
        indentation that parses wins (_parsing_choice). A line break that
        starts new_snippet after an anchor without its own stands for the
        anchor line's break, and spaces and tabs after its last line break
        for the indentation of the anchor's line, so content written to be
        placed byte for byte goes in as before. In the middle of a line, in
        the text of a string, or on the line of a signature that the body
        shares (`def f(): return 1`), new_snippet is placed byte for byte.
        After an anchor that ends with the closing brace of the body is
        refused, as that is outside it.
        """
        start, end, shift = self._find_snippet(body_node, anchor_snippet, target, anchor=True)
        body_start, body_end = self._body_search_range(body_node)
        if place == "after" and self.parser.ext not in (".py", ".rb") and end >= body_end:
            raise ApplierError(
                f"The anchor ends with the closing brace of '{target}', so code after it would be "
                "outside the body. Anchor on the code before the brace, or insert with at='bottom'."
            )
        source_bytes = self.parser.source_bytes
        text = new_snippet.replace("\r\n", "\n")
        # Lines of their own go between lines of the body only, not after
        # a signature the body shares its line with (`def f(): return 1`),
        # nor into the text of a string.
        point = line_end = None
        if place == "after":
            breaks = source_bytes[end - 1 : end] == b"\n"
            line_end = end - 1 if breaks else self._rest_of_line_free(end)
            # The line below starts outside the text of a string (not in a
            # heredoc that the anchor's line opens); a docstring's lines are
            # indented like code.
            if (
                line_end is not None
                and source_bytes.rfind(b"\n", 0, line_end) + 1 >= body_start
                and not self._in_fixed_literal(min(line_end + 1, len(source_bytes)))
            ):
                point = min(line_end + 1, len(source_bytes))
                if not breaks and text.startswith("\n"):
                    text = text[1:]
        else:
            line_start = source_bytes.rfind(b"\n", 0, start) + 1
            if (
                line_start >= body_start
                and not source_bytes[line_start:start].strip(b" \t")
                and not self._in_fixed_literal(line_start)
            ):
                point = line_start
        if point is None or not new_snippet:
            point = end if place == "after" else start
            text = new_snippet
        else:
            lines = text.split("\n")
            if len(lines) > 1 and not lines[-1].strip(" \t"):
                lines.pop()
            frame = shift if shift is not None else self._snippet_frame(start, end)
            first = next((line for line in lines if line.strip(" \t")), "")
            if frame[0] == frame[1] == "" and frame[2] and not self._get_indent(first):
                # Content at column 0 beside an anchor written with all of
                # its indentation goes at the anchor's.
                frame = ("", frame[2], frame[2])
            content = "\n".join(lines)
            extra = self._context_literals(point, point, content + "\n")
            text, other = self._matched_content(content, frame, lead=True, extra=extra, read=shift is None)
            if place == "after":
                text = self._into_block(point, line_end, body_end, text, extra)
                other = other if other is None else self._into_block(point, line_end, body_end, other, extra)
            text = self._parsing_choice(
                lambda t: source_bytes[:point] + (t + "\n").encode("utf-8") + source_bytes[point:], text, other
            ) + "\n"
        self._write_bytes(source_bytes[:point] + text.encode("utf-8") + source_bytes[point:], (point, point))
        return "Update successful"

    def _find_snippet(self, body_node, snippet: str, target: str, anchor: bool = False):
        """
        Where snippet (CRLF read as LF) is in the body of `target` (see
        _body_search_range), as (start, end, shift): the bytes [start, end)
        it covers, and None for an exact match, or else the (old, new,
        depth) of a match with its indentation shifted, whose lines are the
        snippet's lines with an indentation `old` turned into `new`
        (_shift_line), the first of them of code indented `depth` in the
        file.

        An exact match wins: the snippet's own bytes, where they neither
        start nor end inside a token (_splits_match), so `x = 1` is not
        found in `max = 10`. Without one, the snippet's lines may match
        whole lines of the body with one indentation shift
        (_shifted_matches); when every exact match is inside a string or a
        comment (_within_text), the shifted ones elsewhere count too, so
        that the text of a string is not taken for the code the snippet
        was written for at another indentation. Either way the match must
        be unique: none, or several, is refused, naming the lines they are
        on. `anchor` words the refusals for insert_in_body's after and
        before.
        """
        what = "Anchor" if anchor else "Snippet"
        needle = snippet.replace("\r\n", "\n").encode("utf-8")
        if not needle:
            raise ApplierError(f"Empty {what.lower()} cannot be matched")
        body_start, body_end = self._body_search_range(body_node)
        source_bytes = self.parser.source_bytes
        exact, inside = [], []
        at = source_bytes.find(needle, body_start, body_end)
        while at != -1:
            span = (at, at + len(needle))
            (inside if self._splits_match(*span) else exact).append(span)
            at = source_bytes.find(needle, at + 1, body_end)
        textual = bool(exact) and all(self._within_text(*span) for span in exact)
        shifted = []
        if not exact or textual:
            shifted = [
                match
                for match in self._shifted_matches(needle, body_start, body_end)
                if not self._splits_match(match[0], match[1])
            ]
        if textual:
            # The shifted matches at other places than the exact ones.
            starts = {self._first_code(*span) for span in exact}
            shifted = [match for match in shifted if self._first_code(match[0], match[1]) not in starts]
            if shifted:
                places = sorted(exact + [match[:2] for match in shifted])
                raise ApplierError(
                    f"{what} matches {len(places)} places in body of '{target}' ({self._match_lines(places)}): "
                    "as written inside a string or comment, and with its indentation shifted. Include more "
                    "surrounding context to make the match unique."
                )
        if len(exact) == 1:
            return exact[0][0], exact[0][1], None
        if exact:
            raise ApplierError(
                f"{what} matches {len(exact)} places in body of '{target}' ({self._match_lines(exact)}). "
                "Include more surrounding context to make the match unique."
            )
        if len(shifted) == 1:
            return shifted[0]
        if shifted:
            raise ApplierError(
                f"{what} matches {len(shifted)} places in body of '{target}' with its indentation "
                f"shifted ({self._match_lines(shifted)}). Include more surrounding context to make "
                "the match unique."
            )
        noun = "Anchor snippet" if anchor else "Snippet"
        if inside:
            raise ApplierError(
                f"{noun} not found in body of '{target}' as whole tokens: it occurs only inside "
                f"longer tokens, on {self._match_lines(inside)}. A match must start and end at the "
                "edges of identifiers, numbers, keywords and operators (in strings and comments, "
                "of words); include the whole token."
            )
        raise ApplierError(
            f"{noun} not found in body of '{target}'. Check whitespace and indentation: the text "
            "must match the body exactly, or as whole lines with the same indentation added to or "
            "removed from each of them (tabs and spaces differ)."
        )

    def _shifted_matches(self, needle: bytes, body_start: int, body_end: int) -> list:
        """
        The places in the bytes [body_start, body_end) of a body where the
        snippet `needle` matches whole lines with its indentation shifted,
        as (start, end, (old, new, depth)) for _find_snippet: each of its
        lines of code is a line there with the same spaces and tabs put in
        front of it (old is '' and new what is put there) or taken from it
        (old what is taken, new ''), spaces and tabs at the ends of the
        lines aside, and each of its blank lines a blank line, whatever its
        whitespace. A line that starts inside a multi-line string whose
        text does not move with the code (_literal_moves) must be as the
        snippet writes it, as its indentation is part of the string. A line
        break that ends the snippet ends the match too. depth is the
        indentation of its first line of code there. A snippet that starts
        or ends in the middle of a line matches exactly or not at all.
        """
        source_bytes = self.parser.source_bytes
        want = needle.split(b"\n")
        breaks = not want[-1]
        if breaks:
            want.pop()
        code = [i for i, line in enumerate(want) if line.strip(b" \t")]
        if not code:
            return []
        first = body_start
        if first and source_bytes[first - 1 : first] != b"\n":
            first = source_bytes.find(b"\n", first, body_end) + 1
            if not first:
                return []
        rows = []
        while first <= body_end:
            stop = source_bytes.find(b"\n", first)
            if stop == -1:
                stop = len(source_bytes)
            if stop > body_end:
                break
            rows.append((first, stop))
            first = stop + 1
        lines = [source_bytes[a:b] for a, b in rows]
        fixed = {}

        def kept(i: int) -> bool:
            # Whether line i starts inside a string whose text stays put.
            if i not in fixed:
                fixed[i] = self._in_fixed_literal(rows[i][0])
            return fixed[i]

        matches = []
        for k in range(len(rows) - len(want) + 1):
            line, mine = lines[k + code[0]].rstrip(b" \t"), want[code[0]].rstrip(b" \t")
            if line.lstrip(b" \t") != mine.lstrip(b" \t"):
                continue
            have = line[: len(line) - len(line.lstrip(b" \t"))]
            given = mine[: len(mine) - len(mine.lstrip(b" \t"))]
            if have.endswith(given):
                old, new = b"", have[: len(have) - len(given)]
            elif given.endswith(have):
                old, new = given[: len(given) - len(have)], b""
            else:
                continue
            if all(
                got == wanted
                if kept(k + j)
                else (wanted.startswith(old) and got.rstrip(b" \t") == new + wanted[len(old) :].rstrip(b" \t"))
                if wanted.strip(b" \t")
                else not got.strip(b" \t")
                for j, (got, wanted) in enumerate(zip(lines[k : k + len(want)], want))
            ):
                end = rows[k + len(want) - 1][1] + (1 if breaks else 0)
                if end <= body_end:
                    shift = (old.decode("utf-8"), new.decode("utf-8"), have.decode("utf-8"))
                    matches.append((rows[k][0], end, shift))
        return matches

    def _match_lines(self, spans) -> str:
        """'line N' or 'lines N, M' for matches of a snippet, tuples that
        start with their start and end bytes: the lines their first code is
        on (_first_code), at most ten of them."""
        source_bytes = self.parser.source_bytes
        rows = []
        for span in spans:
            row = source_bytes.count(b"\n", 0, self._first_code(span[0], span[1])) + 1
            if row not in rows:
                rows.append(row)
            if len(rows) > 10:
                break
        shown = ", ".join(str(row) for row in rows[:10]) + (", ..." if len(rows) > 10 else "")
        return f"line {shown}" if len(rows) == 1 else f"lines {shown}"

    def _first_code(self, start: int, end: int) -> int:
        """The first byte in [start, end) that is not a space, tab or line
        break, or `start` when they all are."""
        source_bytes = self.parser.source_bytes
        for at in range(start, end):
            if source_bytes[at] not in b" \t\n":
                return at
        return start

    def _splits_match(self, start: int, end: int) -> bool:
        """Whether a match of a snippet, the bytes [start, end), starts or
        ends inside a token (_splits_token)."""
        source_bytes = self.parser.source_bytes
        # A match starts and ends between characters, and the character on
        # either side of a boundary is in the four bytes there.
        before = source_bytes[max(start - 4, 0) : start].decode("utf-8", "ignore")[-1:]
        first = source_bytes[start : start + 4].decode("utf-8", "ignore")[:1]
        last = source_bytes[max(end - 4, start) : end].decode("utf-8", "ignore")[-1:]
        after = source_bytes[end : end + 4].decode("utf-8", "ignore")[:1]
        return self._splits_token(start, first, before) or self._splits_token(end, last, after)

    def _splits_token(self, at: int, inner: str, outer: str) -> bool:
        """
        Whether a match boundary at byte `at`, with the character `inner`
        inside the match and `outer` outside it, splits a token: when both
        continue an identifier, number or keyword (letters, digits, `_`),
        or when `at` is inside a token of code (_node_around), such as an
        operator (the `=` of `==`), a Ruby `foo?` or a JS `$el`. In comments
        and strings (_in_text), whose text is words, only the first holds.
        A Python backslash continuation, which tree-sitter reads as one
        token with its line break, may be split there, so a snippet may end
        with the backslash.
        """
        if _WORD_CHARACTER.match(inner) and _WORD_CHARACTER.match(outer):
            return True
        node = self._node_around(at)
        return (
            node is not None
            and not node.child_count
            and node.type != "line_continuation"
            and not self._in_text(node)
        )

    def _node_around(self, at: int):
        """The smallest node of the file that starts before byte `at` and
        ends after it, or None at the ends of the file."""
        if not 0 < at < len(self.parser.source_bytes):
            return None
        # The smallest node that holds the bytes on both sides of `at`.
        node = self.parser.tree.root_node.descendant_for_byte_range(at - 1, at + 1)
        while node is not None and not node.start_byte < at < node.end_byte:
            node = node.parent
        return node

    def _in_text(self, node) -> bool:
        """Whether `node` (from _node_around) is text, the words of a comment
        or string literal (_TEXT_NODES), rather than code: no token that
        opens or closes a string, and not in an interpolation's code."""
        if not node.child_count and (not node.is_named or node.type in _STRING_DELIMITERS):
            return False
        while node is not None:
            if "comment" in node.type or node.type in _TEXT_NODES:
                return True
            if node.type in _INTERPOLATIONS:
                return False
            node = node.parent
        return False

    def _comment_from(self, at: int):
        """The comment that starts at byte `at`, or None."""
        node = self.parser.tree.root_node.descendant_for_byte_range(at, at + 1)
        if node is None or node.start_byte != at or "comment" not in node.type:
            return None
        return node

    def _rest_of_line_free(self, at: int) -> int | None:
        """The end of the line byte `at` is on (its line break) when nothing
        but spaces, tabs and a comment that ends on it follow `at` there,
        else None."""
        source_bytes = self.parser.source_bytes
        line_end = source_bytes.find(b"\n", at)
        if line_end == -1:
            line_end = len(source_bytes)
        code = source_bytes[at:line_end].lstrip(b" \t")
        if code:
            comment = self._comment_from(line_end - len(code))
            if (
                comment is None
                or comment.end_byte > line_end
                or source_bytes[comment.end_byte : line_end].strip(b" \t")
            ):
                return None
        return line_end

    def _literal_around(self, at: int):
        """The multi-line string literal of the file (_MULTILINE_STRINGS)
        that byte `at` is inside, after its first byte and before its last,
        or None: a line that starts there is text of the literal, its
        indentation included."""
        types = _MULTILINE_STRINGS.get(self.parser.ext)
        if not types or not 0 < at < len(self.parser.source_bytes):
            return None
        node = self.parser.tree.root_node.descendant_for_byte_range(at, at)
        while node is not None:
            if node.type in types and node.start_byte < at < node.end_byte:
                return node
            node = node.parent
        return None

    def _literal_moves(self, node, source: bytes) -> bool:
        """Whether the lines of the multi-line string literal `node`, of
        the source `source`, move with the code (see _literal_rows): a
        Python docstring, a Ruby `<<~` heredoc or a Java text block, whose
        languages strip their common indentation from the value."""
        ext = self.parser.ext
        if ext == ".py":
            return self._is_docstring(node)
        if ext == ".java":
            return source[node.start_byte : node.start_byte + 3] == b'"""'
        if node.type != "heredoc_body":
            return False
        # The body starts at the line break of the line its `<<~EOS` is on.
        end = next((c for c in node.children if c.type == "heredoc_end"), None)
        if end is None:
            return False
        name = re.escape(source[end.start_byte : end.end_byte].strip())
        opener = source[source.rfind(b"\n", 0, node.start_byte) + 1 : node.start_byte]
        return re.search(rb"<<~[\"'`]?" + name + rb"\b", opener) is not None

    def _in_fixed_literal(self, at: int) -> bool:
        """Whether byte `at` is inside a multi-line string literal of the
        file (_literal_around) whose lines do not move with the code
        (_literal_moves): text whose indentation is part of its value, and
        that a new line of code must not go into. A docstring's lines are
        indented like code."""
        literal = self._literal_around(at)
        return literal is not None and not self._literal_moves(literal, self.parser.source_bytes)

    def _within_text(self, start: int, end: int) -> bool:
        """Whether the bytes [start, end) of the file are all in one comment
        or string literal (_in_text): its text, not code."""
        node = self.parser.tree.root_node.descendant_for_byte_range(start, max(start, end - 1))
        return node is not None and self._in_text(node)

    def _context_literals(self, start: int, end: int, text: str) -> list[tuple[range, bool]]:
        """
        The lines of the content `text`, written in place of the file's
        bytes [start, end), that start inside a multi-line string literal
        it holds only part of, one that the code before or after it opens
        or closes (as when the content goes into the text of a string), in
        the form _literal_rows gives them: their indices in `text`, and
        whether the literal's lines move with the code (_literal_moves).
        The result is parsed to find them; the literals the content holds
        all of are _literal_rows's.
        """
        types = _MULTILINE_STRINGS.get(self.parser.ext)
        if not types or "\n" not in text:
            return []
        src = self.parser.source_bytes
        data = text.replace("\r\n", "\n").encode("utf-8")
        new = src[:start] + data + src[end:]
        stop = start + len(data)
        # Where the lines of the content after its first start in `new`.
        offsets, at = [], data.find(b"\n")
        while at != -1:
            offsets.append(start + at + 1)
            at = data.find(b"\n", at + 1)
        result, stack = [], [self.parser.parse(new).root_node]
        while stack:
            node = stack.pop()
            if node.end_byte <= start or node.start_byte >= stop:
                continue
            if node.type in types:
                if node.start_byte < start or node.end_byte > stop:
                    rows = [i for i, at in enumerate(offsets, 1) if node.start_byte < at < node.end_byte]
                    if rows:
                        moves = self._context_literal_moves(node, new, start, stop - end)
                        result.append((range(rows[0], rows[-1] + 1), moves))
                continue
            stack.extend(node.children)
        return result

    def _context_literal_moves(self, node, new: bytes, start: int, delta: int) -> bool:
        """_literal_moves for the literal `node` of an edit's result `new`
        (_context_literals), whose content starts at byte `start` and made
        the file `delta` bytes longer: told from the file's own literal
        that starts where `node` does before the content, or ends where it
        does after it, as the content, not yet indented as it will be, may
        have taken a docstring out of its function in `new`."""
        at = node.start_byte + 1 if node.start_byte < start else node.end_byte - delta - 1
        origin = self._literal_around(at)
        if origin is None:
            return self._literal_moves(node, new)
        return self._literal_moves(origin, self.parser.source_bytes)

    def _parsing_choice(self, make, text: str, other: str | None) -> str:
        """The content `text` for an edit, or `other`, the other reading of
        its indentation (_matched_content), when the file is Python and the
        result `make(text)` would not parse while `make(other)` would."""
        if other is None or other == text or self.parser.ext != ".py":
            return text
        if _python_syntax_error(make(text)) is None or _python_syntax_error(make(other)) is not None:
            return text
        return other

    def _into_block(self, point: int, line_end: int, body_end: int, text: str, extra) -> str:
        """
        The lines `text` that insert_in_body puts at `point`, below an
        anchor whose line ends at `line_end`, moved into the block that
        line opens (`if (x) {`, `if x:`): when the next line of the body
        that is not blank, before `body_end`, is indented deeper than the
        anchor's line, and the first line of code of `text` is at the
        anchor line's indentation, the lines move as far as that next line
        is (_shift_content, `extra` the lines that start inside a string of
        the file, see _context_literals). In the text of a docstring or a
        block comment, the lines are text: a deeper line below is aligned
        text, no block.
        """
        around = self.parser.tree.root_node.descendant_for_byte_range(line_end, line_end)
        if self._literal_around(point) is not None or (
            around is not None and "comment" in around.type and around.end_byte > line_end
        ):
            return text
        src = self.parser.source_bytes
        own = self._get_indent(self.lines[src.count(b"\n", 0, line_end)])
        pos = point
        while pos < body_end:
            stop = src.find(b"\n", pos)
            stop = len(src) if stop == -1 else stop
            if src[pos:stop].strip(b" \t"):
                break
            pos = stop + 1
        else:
            return text
        below = self._get_indent(src[pos:stop].decode("utf-8"))
        lines = text.split("\n")
        first = next((line for line in lines if line.strip(" \t")), None)
        if first is None or self._get_indent(first) != own or len(below) <= len(own) or not below.startswith(own):
            return text
        return "\n".join(self._shift_content(lines, own, below, extra))

    def _indent_row(self, node) -> int:
        """The row whose indentation is that of the code of `node`: the one
        it starts on, or, when that line starts inside a block comment
        begun on a line above (the ` */` of a doc comment before `node` on
        its line), the row that comment starts on."""
        src = self.parser.source_bytes
        line_start = src.rfind(b"\n", 0, node.start_byte) + 1
        line = src[line_start : node.start_byte]
        at = line_start + len(line) - len(line.lstrip(b" \t"))
        comment = self.parser.tree.root_node.descendant_for_byte_range(at, at + 1)
        if comment is not None and "comment" in comment.type and comment.start_byte < line_start:
            return comment.start_point[0]
        return node.start_point[0]

    def _snippet_frame(self, start: int, end: int) -> tuple[str, str, str]:
        """
        The shift, as _find_snippet gives one, for the content that goes
        with an exact match [start, end): the indentation that its first
        line of code left out, as ('', that, the indentation of the line in
        the file). That is what precedes the match on the line when it is
        only indentation, nothing when the match starts on a line before
        (that line's break and the indentation after it are in the snippet),
        and the line's whole indentation when code precedes it there, as if
        the snippet started at column 0.
        """
        source_bytes = self.parser.source_bytes
        code = self._first_code(start, end)
        line_start = source_bytes.rfind(b"\n", 0, code) + 1
        depth = self._get_indent(self.lines[source_bytes.count(b"\n", 0, code)])
        if line_start > start:
            return "", "", depth
        before = source_bytes[line_start:start].decode("utf-8")
        return "", before if not before.strip(" \t") else depth, depth

    def _matched_content(
        self, content: str, shift: tuple[str, str, str], lead: bool, extra=None, read: bool = False
    ) -> tuple[str, str | None]:
        """
        content (CRLF read as LF) indented as the snippet it goes with was
        matched, for `shift` = (old, new, depth) from _find_snippet or
        _snippet_frame: its lines moved as a line indented `old` moves to
        `new`, keeping their indentation relative to each other
        (_shift_content). Only the lines that begin a line in the file move:
        all of them when `lead`, else those after the first, which goes
        where the match starts. When the shift adds indentation and each of
        those lines of code is indented `depth` already, the file's
        indentation there, the content goes in as written; so it does in
        read_symbol's shape, when `lead` and `read` (beside an exact
        anchor, whose frame is the file's), its first line has no
        indentation and the others are that deep, the first line then
        indented `depth`.
        Where the file indents with tabs, its indentation steps are tabs
        first (_tabbed). `extra` are the lines that start inside a string
        of the file (_context_literals), which keep their text as those of
        the content's own strings do.

        Returns the text and the other reading of the content's indentation
        (moved where it goes in as written, and the reverse), or None when
        there is none: in Python, a text that would not parse gives way to
        the other (_parsing_choice).
        """
        old, new, depth = shift
        given = content.replace("\r\n", "\n").split("\n")
        lines = self._tabbed(given, depth, extra=extra)
        text = "\n".join(lines)
        if old == new:
            return text, None
        # The lines of the file's strings that move with the code (a
        # docstring's) count as code here.
        literal = {row for rows, _ in self._literal_rows(given) for row in rows} | {
            row for rows, moves in extra or [] if not moves for row in rows
        }
        # The shape is told from the lines as given, before tabs.
        begins = [i for i, line in enumerate(given) if (lead or i) and line.strip(" \t") and i not in literal]
        moved = self._shift_content(lines, old, new, extra)
        if not lead:
            moved[0] = lines[0]
        moved = "\n".join(moved)
        if old:
            return moved, None
        later = [i for i in begins if i]
        if all(given[i].startswith(depth) for i in begins):
            return text, moved
        if read and lead and later and not self._get_indent(given[0]) and all(given[i].startswith(depth) for i in later):
            return "\n".join([depth + lines[0]] + lines[1:]), moved
        return moved, None if lead else text

    def _shift_content(self, lines: list[str], old: str, new: str, extra=None) -> list[str]:
        """
        Caller content `lines` moved as a line of code indented `old` moves
        to `new` (_shift_line), each line keeping its indentation relative
        to the others; a line indented less than what the move takes away
        loses all of its indentation. Blank lines stay as they are, and so
        do the lines that start inside a multi-line string literal or a Ruby
        embedded document of the content, except those of a literal whose
        language strips their common indentation, which move with the code
        unless one of them cannot (as in _reindent); `extra` adds the lines
        that start inside a string of the file (_context_literals).
        """
        result = []
        for line in lines:
            moved = self._shift_line(line, old, new)
            result.append(moved if moved is not None else new + line.lstrip(" \t"))
        for rows, shifts in self._literal_rows(lines) + (extra or []):
            kept = lines[rows.start : rows.stop]
            moved = [self._shift_line(line, old, new) for line in kept] if shifts else [None]
            result[rows.start : rows.stop] = kept if None in moved else moved
        return result

    def _deleted_span(self, start: int, end: int) -> tuple[int, int]:
        """
        The bytes that deleting the match [start, end) of a snippet removes:
        the match, or the whole lines it takes all the code of, with their
        indentation and line break, when only indentation precedes it on its
        first line and only spaces and tabs follow it on its last (or it
        ends with that line's break). When a comment follows it there, the
        code goes up to the comment, which stays at the line's indentation.
        """
        source_bytes = self.parser.source_bytes
        line_start = source_bytes.rfind(b"\n", 0, start) + 1
        if not source_bytes[start:end].strip() or source_bytes[line_start:start].strip(b" \t"):
            return start, end
        if source_bytes[end - 1 : end] == b"\n":
            return line_start, end
        line_end = self._rest_of_line_free(end)
        if line_end is None:
            return start, end
        rest = source_bytes[end:line_end]
        if not rest.strip(b" \t"):
            return line_start, min(line_end + 1, len(source_bytes))
        first_line = source_bytes[line_start : source_bytes.find(b"\n", line_start)]
        code = line_start + len(first_line) - len(first_line.lstrip(b" \t"))
        return code, line_end - len(rest.lstrip(b" \t"))

    def _keep_a_statement(self, body_node, start: int, end: int, target: str) -> None:
        """Refuse to delete the bytes [start, end) of a Python body when they
        hold all of its statements: Python needs one."""
        if self.parser.ext != ".py":
            return
        statements = [c for c in body_node.named_children if c.type != "comment"]
        if statements and all(start <= c.start_byte and c.end_byte <= end for c in statements):
            raise ApplierError(
                f"Deleting the snippet would leave the body of '{target}' without a statement, "
                "which Python does not allow. Replace it with `pass` (replace_in_body), or delete "
                "the whole function (delete_symbol)."
            )

    def _body_search_range(self, body_node) -> tuple[int, int]:
        """Return (start_byte, end_byte) byte range within which to search for
        a snippet inside a function body. For Python/Ruby, extends the start
        back to the beginning of the first body line so leading indentation is
        part of the searchable text, when only that indentation comes before
        it there (not the signature of a one-line function, or other code),
        and the end over the line break after the last statement, so that a
        snippet may end with its line's break there too.
        For brace-delimited languages, returns
        the body node's native byte range (which includes `{` and `}`), up
        to its `}`: a comment after that, which the JS/TS grammar puts in
        the body, is no part of it (_code_end)."""
        start_byte = body_node.start_byte
        end_byte = self._code_end(body_node)
        if self.parser.ext in (".py", ".rb"):
            source_bytes = self.parser.source_bytes
            line_start = source_bytes.rfind(b"\n", 0, start_byte) + 1
            if not source_bytes[line_start:start_byte].strip(b" \t"):
                start_byte = line_start
            if source_bytes[end_byte : end_byte + 1] == b"\n":
                end_byte += 1
        return start_byte, end_byte

    def _body_insert_point(self, target: str, at: str) -> tuple[int, str]:
        """
        Line index and indentation for inserting at the top or bottom of a
        function body. The indentation comes from the body's own statements, not
        from whichever line happens to be first or last, so a body that ends in a
        nested block still gets the new lines at body level. In Python the new
        lines go after a leading docstring so it stays the docstring; in Ruby a
        bottom insert goes before any rescue/else/ensure clause, and an empty
        method (_empty_method) takes the lines between its signature and its
        `end`. A body that shares a line with its signature or braces has no
        line to insert on and is refused.
        """
        func_node, body = self._get_function_body_node(target, empty_ok=True)
        ext = self.parser.ext
        # Not a comment after the `}` that the JS/TS grammar puts in the body.
        # An empty Ruby method has no body node (_empty_method).
        stmts = [] if body is None else [c for c in body.named_children if c.end_byte <= self._code_end(body)]
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
            # Where the body opens: after a signature over several lines, too.
            open_row = self.parser.source_bytes.count(b"\n", 0, self._body_opening(func_node, body))
            compact = bool(stmts) and stmts[0].start_point[0] == open_row
            if ext == ".rb" and func_node.children[-1].type == "end":
                last_row = body.end_point[0] if body is not None else open_row
                compact = compact or last_row == func_node.children[-1].start_point[0]
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
            if body is None:
                return open_row + 1, indent
            return (stmts[0].start_point[0] if stmts else body.start_point[0]), indent
        if braced:
            return body.end_point[0], indent
        if clause is not None:
            return clause.start_point[0], indent
        if body is None:
            return func_node.children[-1].start_point[0], indent
        return (stmts[-1].end_point[0] + 1 if stmts else body.end_point[0] + 1), indent

    @staticmethod
    def _is_docstring_node(node) -> bool:
        """True for a Python statement that is just a string literal (a
        docstring), but not an f-string, t-string or bytes literal, which
        Python never takes for one (its prefix may only be r or u)."""
        if node.type != "expression_statement" or node.named_child_count != 1:
            return False
        string = node.named_children[0]
        if string.type not in ("string", "concatenated_string"):
            return False
        parts = [c for c in string.named_children if c.type == "string"] if string.type == "concatenated_string" else [string]
        return all(not re.match(rb"[a-zA-Z]*", part.text).group().lower().strip(b"ru") for part in parts)

    def _prepend_to_body(self, target: str, content: str) -> str:
        """
        Insert content at the top of a function body, preserving existing statements.
        """
        insert_line, target_indent = self._body_insert_point(target, "top")
        content_lines = self._reindent(self._tabbed(_content_lines(content), target_indent), target_indent)
        self.lines = self.lines[:insert_line] + content_lines + self.lines[insert_line:]
        return self._save()

    def _append_to_body(self, target: str, content: str) -> str:
        """
        Insert content at the bottom of a function body, preserving existing statements.
        """
        insert_line, target_indent = self._body_insert_point(target, "bottom")
        content_lines = self._reindent(self._tabbed(_content_lines(content), target_indent), target_indent)
        self.lines = self.lines[:insert_line] + content_lines + self.lines[insert_line:]
        return self._save()

    def _insert_before(self, target: str, content: str) -> str:
        """
        Insert content as a sibling immediately before a named symbol (function, class,
        method, or top-level assignment): above its leading comment block,
        decorators, JS/TS `export` and C++ `template <...>`, separated from it
        and from the sibling above it as _sibling_gaps says. Blank lines below
        a comment above it, or below the `{` or access label that opens its
        body, are left as they are. A symbol that shares its first line with
        other code is refused: lines above that line would land before that
        code.
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        # Above the symbol's decorators and a JS/TS `export` (see
        # _symbol_span), and above its leading comment, which documents the
        # symbol and must stay on top of it.
        first, last = self._symbol_unit(node)
        before, separator, _ = self._line_sharing(first, last)
        if before:
            raise ApplierError(
                f"'{target}' shares its first line with other code, so new lines above "
                "that line would not land right before it. Make this edit with your "
                "normal edit tool."
            )
        insert_line = first.start_point[0]
        comment_range = self._find_leading_comment_range(insert_line)
        if comment_range is not None:
            insert_line = comment_range[0]
        # The symbol's indentation, which a comment above it need not have
        # (a Ruby `=begin` is at column 0).
        target_indent = self._get_indent(self.lines[first.start_point[0]])
        content_lines = self._sibling_content(content, target_indent, range(first.start_point[0], last.end_point[0] + 1))

        # The sibling above, a comment at the end of its line not counted.
        # A comment above keeps the blank lines below it, unless it is
        # indented deeper, as the end of the code above it.
        near = self._sibling_above(first, insert_line)
        top = insert_line - near[1] if near is not None else insert_line
        far = self._sibling_below(first, last, separator)
        below, above = self._sibling_gaps(
            first.parent, (first, last), content_lines, near, far, self._stacked_beyond(near, upward=True)
        )
        gap_above = [""] * above if near is not None else []
        gap_below = [""] * below

        self.lines = (
            self.lines[:top]
            + gap_above
            + content_lines
            + gap_below
            + self.lines[insert_line:]
        )
        return self._save()

    def _insert_after(self, target: str, content: str) -> str:
        """
        Insert content as a sibling immediately after a named symbol (function, class,
        method, or top-level assignment), separated from it and from the
        sibling below it (with that sibling's leading comment, decorators and
        `export`) as _sibling_gaps says. The comment lines right below the
        symbol that are indented deeper than it end its code, so the content
        goes below them (_rows_below). When nothing but the end of its body or
        file, or a C++ access label, follows the symbol, the blank lines after
        it stay below the new code. A symbol that shares its last line with
        other code is refused, as is one on the line where the code it is part
        of starts (`class A: x = 1`): lines below would land after that code.
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        first, last = self._symbol_unit(node)
        before, separator, after = self._line_sharing(first, last)
        if after:
            raise ApplierError(
                f"'{target}' shares its last line with other code, so new lines below "
                "that line would not land right after it. Make this edit with your "
                "normal edit tool."
            )
        if before and not self._line_starts_with_sibling(first):
            raise ApplierError(
                f"'{target}' shares its line with the start of the code it is part of, "
                "so new lines below it would land outside that code. Make this edit "
                "with your normal edit tool."
            )
        # Below the comment lines that end its code (_rows_below).
        insert_line = self._rows_below(first, last, separator)
        target_indent = self._get_indent(self.lines[first.start_point[0]])
        content_lines = self._sibling_content(content, target_indent, range(first.start_point[0], last.end_point[0] + 1))

        # The next symbol's leading comment, decorators or `export` start
        # it; the blank lines before it are replaced.
        near = self._sibling_below(first, last, separator)
        bottom = insert_line + near[1] if near is not None else insert_line
        top = first.start_point[0]
        comment_range = self._find_leading_comment_range(top)
        far = self._sibling_above(first, comment_range[0] if comment_range is not None else top)
        above, below = self._sibling_gaps(
            last.parent, (first, last), content_lines, near, far, self._stacked_beyond(near, upward=False)
        )
        gap_above = [""] * above
        gap_below = [""] * below if near is not None else []

        self.lines = (
            self.lines[:insert_line]
            + gap_above
            + content_lines
            + gap_below
            + self.lines[bottom:]
        )
        return self._save()

    def _sibling_content(self, content: str, indent: str, rows: range) -> list[str]:
        """The lines of insert_sibling's content, without blank lines around
        them, re-indented to `indent` (content in read_symbol's shape from
        the indentation it was read at, see _from_read_shape), in tabs where
        the file indents with them beside the target's lines `rows`, as
        add_method writes them (_tabbed)."""
        lines = _content_lines(content)
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            raise ApplierError("content is empty: pass the source of the code to insert")
        lines = self._from_read_shape(lines, indent)
        return self._reindent(self._tabbed(lines, indent, rows), indent)

    def _sibling_gap(self, parent, a, b) -> int:
        """
        Blank lines between neighbouring siblings `a` and `b` (nodes, or the
        lines of new content) of `parent`: two at the top level of a Python
        module when either is a def or a class, decorated or not (PEP 8),
        else one.
        """
        if self.parser.ext != ".py" or parent is None or parent.parent is not None:
            return 1

        def definition(item) -> bool:
            if isinstance(item, list):
                code = next((line.strip() for line in item if line.strip() and not line.strip().startswith("#")), "")
                return re.match(r"(@|class\b|def\b|async\s+def\b)", code) is not None
            return item is not None and item.type in (
                "function_definition",
                "class_definition",
                "decorated_definition",
            )

        return 2 if definition(a) or definition(b) else 1

    def _is_block(self, item) -> bool:
        """
        Whether `item`, a sibling (a node, or the first and last nodes of a
        symbol) or the lines of new content, is a block for the spacing of
        siblings (_sibling_gaps): code over several lines, comments aside,
        or a definition with a body on one line (_block_line). None (no
        sibling) is not.
        """
        if item is None:
            return False
        if isinstance(item, list):
            lines = item
            if self.parser.ext == ".py":
                old = self._get_indent(lines[0])
                lines = [line[len(old) :] if line.startswith(old) else line for line in lines]
            rows, stack = set(), [self.parser.parse("\n".join(lines).encode("utf-8")).root_node]
            while stack:
                node = stack.pop()
                if "comment" in node.type:
                    continue
                if node.child_count:
                    stack.extend(node.children)
                elif node.end_byte > node.start_byte:
                    rows.update(range(node.start_point[0], node.end_point[0] + 1))
            return len(rows) > 1 or any(self._block_line(item[row]) for row in rows if row < len(item))
        first, last = item if isinstance(item, tuple) else (item, item)
        if first.type in ("function_definition", "class_definition", "decorated_definition"):
            return True
        return self._last_row(last) > first.start_point[0] or self._block_line(self.lines[first.start_point[0]])

    def _block_line(self, line: str) -> bool:
        """Whether a line of code is a definition with a body, for
        _is_block: a Python def or class (or a decorator), a Ruby def, class
        or module, and elsewhere code that ends with a `}`, a `;` after it
        and a comment aside (`function f() {}`, `struct S {};`)."""
        code = line.strip(" \t")
        if self.parser.ext == ".py":
            return re.match(r"(@|class\b|def\b|async\s+def\b)", code) is not None
        if self.parser.ext == ".rb":
            return re.match(r"(def|class|module)\b", code) is not None
        code = re.sub(r"\s*(//.*|/\*.*?\*/)$", "", code)
        return code.rstrip("; \t").endswith("}")

    def _sibling_gaps(self, parent, target, content: list[str], near, far, beyond=None) -> tuple[int, int]:
        """
        The blank lines that insert_sibling puts between `target` (the
        first and last nodes of the symbol that the content goes beside)
        and the lines `content`, and between them and `near`, the target's
        sibling on that side, given as (its node, the blank lines that
        separated it from the target), the node None when only comments
        follow, or None when there is none (the start or end of the body or
        file, a C++ access label); `far` is the sibling on the target's
        other side, in the same form, and `beyond` the blank lines between
        a one-line `near` and its own one-line neighbour on the side away
        from the target, or None (_stacked_beyond).

        Where a block (_is_block) is one of the two, the gap is the usual
        one (_sibling_gap) or the wider one that separated the target from
        `near`. Between one-line content and a one-line target it is the
        smallest gap between the target and a one-line neighbour (that on
        the far side counted up to the usual gap), and between one-line
        content and a one-line `near` the gap that separated a one-line
        target from it, or, beside a block target, the gap `beyond` (up to
        the usual gap); else the usual one. So stacked declarations and
        fields stay stacked, and the gap the content went into stays on
        the side of `near`.
        """
        near_node, near_gap = near if near is not None else (None, 0)
        target_block, content_block = self._is_block(target), self._is_block(content)
        usual = self._sibling_gap(parent, target[0], content)
        gaps = []
        if not target_block:
            if near is not None and not self._is_block(near_node):
                gaps.append(near_gap)
            if far is not None and far[0] is not None and not self._is_block(far[0]):
                gaps.append(min(far[1], usual))
        if target_block or content_block:
            toward = max(usual, near_gap)
        else:
            toward = min(gaps) if gaps else usual
        usual = self._sibling_gap(parent, content, near_node)
        if content_block or self._is_block(near_node):
            away = max(usual, near_gap)
        elif near is not None and not target_block:
            away = near_gap
        elif beyond is not None:
            # Beside a block, one-line content joins the stack of `near`.
            away = min(beyond, usual)
        else:
            away = usual
        return toward, away

    def _stacked_beyond(self, near, upward: bool):
        """
        For `near`, the sibling of insert_sibling's target on the side the
        content goes (as _sibling_above, `upward`, or _sibling_below give
        it), when it is one-line code: the blank lines between it and its
        own neighbour on the side away from the target, when that is
        one-line code too, else None. One-line content that goes between a
        block and `near` joins that stack (_sibling_gaps).
        """
        if near is None or near[0] is None or self._is_block(near[0]):
            return None
        node = near[0]
        if upward:
            comment_range = self._find_leading_comment_range(node.start_point[0])
            other = self._sibling_above(node, comment_range[0] if comment_range is not None else node.start_point[0])
        else:
            other = self._sibling_below(node, node, self._line_sharing(node, node)[1])
        if other is None or other[0] is None or self._is_block(other[0]):
            return None
        return other[1]

    def _sibling_above(self, first, top: int):
        """
        The sibling above the symbol that starts with the node `first`, its
        lines starting at row `top` (its leading comment's first), for the
        spacing of insert_sibling: (the code above, and the blank lines
        between them), or None when the start of its body or file, a C++
        access label, or a comment that is not indented deeper than the
        symbol comes first. A comment indented deeper ends the code above
        it, which counts.
        """
        siblings = first.parent.named_children if first.parent is not None else []
        above = [
            s for s in siblings
            if self._last_row(s) < top and ("comment" not in s.type or self._starts_line(s.start_byte))
        ]
        if not above or above[-1].type == "access_specifier":
            return None
        indent = self._get_indent(self.lines[first.start_point[0]])
        if "comment" in above[-1].type and not self._indented_deeper(self.lines[above[-1].start_point[0]], indent):
            return None
        row = top
        while row > 0 and not self.lines[row - 1].strip(" \t"):
            row -= 1
        return next((s for s in reversed(above) if "comment" not in s.type), None), top - row

    def _sibling_below(self, first, last, separator):
        """
        The sibling below the symbol first..last (`separator` the `;` or
        `,` that ends it, or None), for the spacing of insert_sibling: (the
        first code below it, None when only comments follow, and the blank
        lines between them), or None when the end of its body or file or a
        C++ access label comes first. The comment lines that end its code
        (_rows_below) are part of the symbol.
        """
        start = self._rows_below(first, last, separator)
        siblings = last.parent.named_children if last.parent is not None else []
        below = [s for s in siblings if s.start_point[0] >= start]
        if not below or below[0].type == "access_specifier":
            return None
        row = start
        while row < len(self.lines) and not self.lines[row].strip(" \t"):
            row += 1
        return next((s for s in below if "comment" not in s.type), None), row - start

    def _gap_after(self, parent, last, content: list[str], start=None) -> int:
        """The blank lines between `last`, the last code of `parent`, and
        the lines `content` added after it (add_top_level, add_method), as
        insert_sibling would put them after it (_sibling_gaps): one-line
        content after stacked one-line code is stacked too. The code that
        `start` (an include guard's `#define`) ends, and that node itself,
        do not count. After a comment, or with no code, the usual gap
        (_sibling_gap), and so after imports, includes or a package clause
        for content that is none (_is_import_line)."""
        if last is None or "comment" in last.type:
            return self._sibling_gap(parent, last, content)
        preamble = self._is_import(last) or last.type in ("package_clause", "package_declaration")
        if preamble and not self._is_import_line(content):
            return self._sibling_gap(parent, last, content)
        comment_range = self._find_leading_comment_range(last.start_point[0])
        far = self._sibling_above(last, comment_range[0] if comment_range is not None else last.start_point[0])
        if far is not None and start is not None and (far[0] is None or far[0].start_byte <= start.start_byte):
            far = None
        return self._sibling_gaps(parent, (last, last), content, None, far)[0]

    def _is_import_line(self, lines: list[str]) -> bool:
        """Whether the first line of code of the content `lines` is an
        import, an include or a `require` (for _gap_after, which stacks it
        under the file's own)."""
        code = next((line.strip() for line in lines if line.strip() and not self._is_comment_line(line)), "")
        return re.match(r"(import|from|require|require_relative)\b|#\s*include\b", code) is not None

    def insert_sibling(self, target: str, content: str, position: str) -> str:
        """
        Insert `content` as a sibling of the named symbol. `position` must be
        'before' or 'after'. Dispatches to insert_before / insert_after. In
        a JSON, YAML or TOML file it is refused for add_key (_refuse_config).
        """
        self._refuse_config(
            "insert_sibling",
            target,
            f"add_key to add a key next to '{target}', its parent's path being the parent_target",
        )
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
        The list keeps its layout, as config arrays do (_insert_entry): an
        inline list stays inline (`[]` becomes `[3]`), one with an element
        per line gets a new line at the elements' indentation (an empty one
        written over two lines gets the value with a comma, as add_key
        writes a dict's first entry), and a trailing comma is kept. Comments
        are no elements: one at the end of the last element's line stays
        there, after that element's comma.
        """
        list_node = self._find_python_literal(target, "list")
        self._insert_entry(
            list_node,
            [c for c in list_node.named_children if "comment" not in c.type],
            value,
            expand_empty=False,
            empty_trailing_comma=True,
            default_unit="    ",
            pad_empty=False,
        )
        return "Update successful"

    def remove_from_list(self, target: str, value_match: str) -> str:
        """
        Remove the first element matching value_match (stripped text equality) from
        a Python list literal, the way _delete_entry deletes an entry (see
        remove_from_array). Comments are no elements.
        """
        list_node = self._find_python_literal(target, "list")
        elements = [c for c in list_node.named_children if c.type != "comment"]

        stripped = value_match.strip()
        idx = None
        for i, el in enumerate(elements):
            if self.parser.node_text(el).strip() == stripped:
                idx = i
                break
        if idx is None:
            raise ApplierError(f"Value {value_match} not found in list '{target}'")

        self._delete_entry(list_node, elements, idx)
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
        Raises if no matching import statement exists. The new name goes
        at its sorted place when the names are sorted (_name_position),
        else after the last one. Names in braces or parentheses follow
        their layout (_insert_entry): written one per line, the new one
        gets a line of its own at their indentation, with a comma after it
        when the last one has one (else the last one gets the comma); an
        inline list stays inline, as does a Python list without
        parentheses.
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

        index = self._name_position(name_nodes, name)
        if stmt.children[-1].type == ")":
            # Names in parentheses follow their layout, one per line or
            # inline (_insert_entry). The statement stands in for the
            # parentheses: it ends with the `)`, and its `from` starts the
            # line of the `(`.
            self._insert_entry(
                stmt, name_nodes, name, expand_empty=False, empty_trailing_comma=False, default_unit="    ", at=index
            )
            return "Update successful"
        if index < len(name_nodes):
            offset, insertion = name_nodes[index].start_byte, f"{name}, "
        else:
            offset, insertion = name_nodes[-1].end_byte, f", {name}"
        source_bytes = self.parser.source_bytes
        new_bytes = source_bytes[:offset] + insertion.encode("utf-8") + source_bytes[offset:]
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

        # One name per line or inline, as the braces have them.
        self._insert_entry(
            named_imports,
            specs,
            name,
            expand_empty=False,
            empty_trailing_comma=False,
            default_unit="  ",
            at=self._name_position(specs, name),
        )
        return "Update successful"

    def _name_position(self, names: list, name: str) -> int:
        """The index in an import's list of names (Python names, JS/TS
        specifiers) that add_import_name puts `name` at: its place in their
        order when they are sorted (_sorted_index), in plain, case-sensitive
        order (as one name is) or else in isort's and ruff's order by type
        (_name_type, each type without case, numbers in numeric order);
        else the end. A name sorts by the name it imports: `b` for `b as c`
        and for a TS `type b`."""

        def imported(node, data: bytes) -> str:
            inner = node.child_by_field_name("name") if node.type in ("aliased_import", "import_specifier") else None
            node = node if inner is None else inner
            return data[node.start_byte : node.end_byte].decode("utf-8")

        def keys(text: str) -> tuple:
            return text, (_name_type(text), _natural(text.lower()), text)

        if self.parser.ext == ".py":
            data = f"from m import {name}\n".encode("utf-8")
            statement = next(iter(self.parser.parse(data).root_node.named_children), None)
            new = []
            if statement is not None and statement.type == "import_from_statement":
                new = statement.children_by_field_name("name")
        else:
            data = f'import {{ {name} }} from "m";\n'.encode("utf-8")
            clause = self._find_js_named_imports_clause(self.parser.parse(data).root_node)
            new = [c for c in clause.named_children if c.type == "import_specifier"] if clause is not None else []
        text = imported(new[0], data) if len(new) == 1 else name.strip()
        src = self.parser.source_bytes
        index = _sorted_index([keys(imported(node, src)) for node in names], keys(text))
        return len(names) if index is None else index

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
        (when the statement consists of only named imports). In braces or
        parentheses the name goes as _delete_entry deletes an entry: on a
        line of its own with that line and the comment at its end, else
        with one comma next to it.
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

        if stmt.children[-1].type == ")":
            # A name on a line of its own goes with that line and its
            # comment (_delete_entry; the statement stands in for the
            # parentheses, as in _add_import_name_python).
            self._delete_entry(stmt, name_nodes, idx)
            return "Update successful"
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

        # Multiple specs: remove this one with an adjacent comma, or with its
        # line and the comment at its end when it has a line of its own.
        self._delete_entry(named_imports, specs, idx)
        return "Update successful"

    def _find_parameter_list(self, target: str):
        """Locate the parameter list node for a function/method across
        languages. For a JS/TS arrow function with one unparenthesized
        parameter (`x => ...`) that parameter's identifier is returned
        (see _is_bare_arrow_parameter)."""
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        func_node = self._callable(node, target)

        params = func_node.child_by_field_name("parameters")
        if params is not None:
            return params
        if func_node.type == "arrow_function":
            bare = func_node.child_by_field_name("parameter")
            if bare is not None:
                return bare

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

    def _is_bare_arrow_parameter(self, params) -> bool:
        """Whether the node _find_parameter_list returned is the lone
        unparenthesized parameter of a JS/TS arrow function (`x => ...`),
        which add_parameter and remove_parameter rewrite with parentheses:
        `(x, y) =>`, `() =>`."""
        parent = params.parent
        return (
            parent is not None
            and parent.type == "arrow_function"
            and parent.child_by_field_name("parameter") == params
        )

    def _parameter_name(self, param_node, src: bytes | None = None) -> str:
        """Extract the identifier name from a parameter node across languages,
        reading it from `src` (the file's source when None)."""
        # Python: identifier, typed_parameter, default_parameter, typed_default_parameter
        # JS/TS: identifier, required_parameter, optional_parameter
        # C/C++: parameter_declaration
        if param_node.type == "identifier":
            return self._text(param_node, src)
        pattern = param_node.child_by_field_name("pattern")
        if pattern is not None and pattern.type == "this":
            # A TS `this` parameter (`this: Window`).
            return "this"
        # Try field name first
        name_field = param_node.child_by_field_name("name")
        if name_field is not None:
            if name_field.type == "identifier":
                return self._text(name_field, src)
            # Could be typed_parameter wrapper; recurse
            return self._parameter_name(name_field, src)
        # Fallback: search for first identifier in descendants
        queue = list(param_node.named_children)
        while queue:
            c = queue.pop(0)
            if c.type == "identifier":
                return self._text(c, src)
            queue.extend(c.named_children)
        return ""

    def _parameter_names(self, param_node, src: bytes | None = None) -> list[str]:
        """The names a parameter node declares, read from `src` (the file's
        source when None): every name of a Go parameter declaration that
        lists several for one type (`a, b int`) and none of one that gives
        only a type (`int`, `func(x int)`); those a JS/TS or Ruby
        destructuring pattern binds (`{a: x, b}` binds x and b, see
        _bound_names); elsewhere the one _parameter_name finds, if any."""
        pattern = self._parameter_pattern(param_node)
        if pattern is not None:
            return [self._text(n, src) for n in self._bound_names(pattern, src)]
        if param_node.type in ("parameter_declaration", "variadic_parameter_declaration") and (
            self.parser.ext == ".go"
        ):
            return [self._text(n, src) for n in param_node.children_by_field_name("name")]
        name = self._parameter_name(param_node, src)
        return [name] if name else []

    def _text(self, node, src: bytes | None = None) -> str:
        """The text of `node` in `src`, the file's source when None (an
        edited version of it parsed apart, as add_parameter checks)."""
        if src is None:
            return self.parser.node_text(node)
        return src[node.start_byte : node.end_byte].decode("utf-8")

    @staticmethod
    def _parameter_pattern(param_node):
        """The destructuring pattern a parameter is, or None: a JS/TS object
        or array pattern (`{a, b}`, `[a, b]`, also with a type or a default,
        `{a}: P = {}`) or a Ruby destructured parameter (`(a, b)`)."""
        node = param_node
        if node.type in ("required_parameter", "optional_parameter"):
            node = node.child_by_field_name("pattern")
        if node is not None and node.type == "assignment_pattern":
            node = node.child_by_field_name("left")
        if node is not None and node.type in ("object_pattern", "array_pattern", "destructured_parameter"):
            return node
        return None

    def _bound_names(self, node, src: bytes | None = None) -> list:
        """
        The name nodes that a destructuring pattern, or an element of one,
        binds, in order: through renamed keys (`{a: x}` binds x), defaults
        (`{a = 1}`, `[a = 1]`), rest elements (`...rest`, Ruby `*rest`) and
        nested patterns. A Ruby `_` holds a position and binds no name.
        """
        if node is None:
            return []
        if node.type in ("identifier", "shorthand_property_identifier_pattern"):
            return [] if self.parser.ext == ".rb" and self._text(node, src) == "_" else [node]
        if node.type == "pair_pattern":
            return self._bound_names(node.child_by_field_name("value"), src)
        if node.type in ("object_assignment_pattern", "assignment_pattern"):
            return self._bound_names(node.child_by_field_name("left"), src)
        if node.type == "splat_parameter":
            name = node.child_by_field_name("name")
            return [name] if name is not None else []
        if node.type in ("rest_pattern", "object_pattern", "array_pattern", "destructured_parameter"):
            return [n for c in node.named_children if "comment" not in c.type for n in self._bound_names(c, src)]
        return []

    def _remove_bound_name(self, pattern, name: str) -> None:
        """
        Remove `name` from the destructuring pattern `pattern`, which binds
        other names too, and write the file. The element that binds it goes,
        in an object pattern with its comma as _delete_entry deletes an
        entry, and one that binds others too (a nested pattern) loses the
        name inside. The elements of an array pattern and of a Ruby one bind
        by position, so one before others keeps its place, as a hole (`[,
        b]`) or a `_` (`(_, b)`); the last one goes with the comma, and the
        holes, before it.
        """
        elements = [c for c in pattern.named_children if "comment" not in c.type]
        idx = next(i for i, e in enumerate(elements) if name in [self._text(n) for n in self._bound_names(e)])
        element = elements[idx]
        if [self._text(n) for n in self._bound_names(element)] != [name]:
            nested = element
            while nested.type not in ("object_pattern", "array_pattern", "destructured_parameter"):
                field = {"pair_pattern": "value", "object_assignment_pattern": "left", "assignment_pattern": "left"}
                if nested.type in field:
                    nested = nested.child_by_field_name(field[nested.type])
                else:
                    nested = nested.named_children[0]
            self._remove_bound_name(nested, name)
            return
        if pattern.type == "object_pattern":
            self._delete_entry(pattern, elements, idx)
            return
        src = self.parser.source_bytes
        if idx == len(elements) - 1:
            new_bytes = src[: elements[idx - 1].end_byte] + src[element.end_byte :]
        else:
            hole = b"_" if pattern.type == "destructured_parameter" else b""
            new_bytes = src[: element.start_byte] + hole + src[element.end_byte :]
        self._write_bytes(new_bytes)

    def add_parameter(self, target: str, parameter: str, position: str = "end") -> str:
        """
        Add a parameter to a function signature. position must be 'end' (default)
        or 'start'; anything else raises ApplierError. parameter should be the
        literal source text of the new parameter (e.g. 'default=None' or
        'const int* buf'). A JS/TS arrow function's one unparenthesized
        parameter gets parentheses: `x => x` becomes `(x, y) => x`. A list
        written one parameter per line gets the new one on a line of its own
        (_add_parameter_line), and so does an empty one whose `)` is on a
        line below its `(` (_add_parameter_below); comments are no
        parameters. The end of a list is before the parameters that must
        stay last (_stays_last: a Python `**kwargs`, a JS/TS rest parameter,
        a Go or Java variadic one, a C or C++ `...`, a GNU named variadic
        macro parameter `args...`), in Ruby before those whose kind comes
        after the new one's (_end_index: `b` before keyword parameters,
        `b = 1` before the splat), and in the old C++ form `int a...`
        before its `...` (_old_variadic); the start is after one that must
        stay first (_stays_first: a TS `this`, a Java receiver parameter).
        The `void` of a C or C++
        `(void)` gives way to the parameter (_void_parameter). A name the
        function already has is refused (_refuse_repeated_parameter).
        """
        if position not in ("start", "end"):
            raise ApplierError(
                f"add_parameter: position must be 'start' or 'end', got '{position}'"
            )
        params = self._find_parameter_list(target)
        existing = self._parameter_entries(params)
        # The index of the parameter the new one goes before, None for after
        # the last: those that must stay last (_end_index) or first
        # (_stays_first) keep their places.
        if position == "start":
            before = 0
            while before < len(existing) and self._stays_first(existing[before]):
                before += 1
        else:
            before = self._end_index(existing, parameter)
        if before == len(existing):
            before = None

        source_bytes = self.parser.source_bytes
        new_bytes = None
        void = self._void_parameter(existing)
        ellipsis = self._old_variadic(params, existing) if position == "end" else None
        if ellipsis is not None:
            # `int a...` is `int a, ...`: the new parameter goes before the
            # `...`, which stays on it (`int a, int b...`).
            new_bytes = source_bytes[:ellipsis] + f", {parameter}".encode("utf-8") + source_bytes[ellipsis:]
        elif void is not None:
            # A C or C++ `(void)` lists no parameters: the new one takes the
            # place of the `void`.
            new_bytes = source_bytes[: void.start_byte] + parameter.encode("utf-8") + source_bytes[void.end_byte :]
        elif self._is_bare_arrow_parameter(params):
            # `x => ...` takes a second parameter only in parentheses.
            old = self.parser.node_text(params)
            pair = f"{parameter}, {old}" if position == "start" else f"{old}, {parameter}"
            new_bytes = (
                source_bytes[: params.start_byte]
                + f"({pair})".encode("utf-8")
                + source_bytes[params.end_byte :]
            )
        elif existing:
            new_bytes = self._add_parameter_line(params, existing, parameter, before)
        else:
            new_bytes = self._add_parameter_below(params, parameter)

        if new_bytes is None:
            if not existing:
                # Empty parameter list: insert between ( and )
                insert_byte = params.start_byte + 1
                insertion = parameter
            elif before is not None:
                insert_byte = existing[before].start_byte
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
        self._refuse_repeated_parameter(target, params, new_bytes)
        self._write_bytes(new_bytes)
        return "Update successful"

    def _add_parameter_line(self, params, existing: list, parameter: str, before: int | None) -> bytes | None:
        """
        The source with `parameter` added to a parameter list written one
        parameter per line, on a line of its own at the indentation of the
        parameter next to it, or None when the list is not written that way
        (two parameters share a line, or a lone one follows the `(`) and the
        parameter goes inline instead.

        At the end it goes on the line after the last parameter's (after the
        comma and a comment there), with a comma of its own when the last
        one has one; else the last one gets the comma. A `)` on the last
        parameter's line (`def f(a,\\n      b):`) stays after the new one.
        Before the parameter existing[before] (the first at the start, or the
        one after a TS `this`; at the end the first of those that must stay
        last, _stays_last) it goes where that parameter is, above
        the comments on lines of their own right before it, and that
        parameter moves to the next line, indented like the parameter after
        it when it follows the `(` (aligned parameters).
        """
        # Every parameter after the first starts its line (the first may
        # follow the `(`), and a lone one starts its own.
        if not all(self._starts_line(p.start_byte) for p in existing[1:]) or (
            len(existing) == 1 and not self._starts_line(existing[0].start_byte)
        ):
            return None
        src = self.parser.source_bytes
        if before is not None:
            first = existing[before]
            if self._starts_line(first.start_byte):
                indent = self._own_line_indent([first], "")
            elif before == 0 and len(existing) > 1 and self._starts_line(existing[1].start_byte):
                indent = self._own_line_indent([existing[1]], "")
            else:
                return None
            at = first
            for c in reversed([c for c in params.children if c.end_byte <= first.start_byte]):
                if "comment" not in c.type or not self._starts_line(c.start_byte):
                    break
                if c.end_point[0] + 1 < at.start_point[0]:
                    break
                at = c
            text = f"{parameter},\n{indent}".encode("utf-8")
            return src[: at.start_byte] + text + src[at.start_byte :]

        last = existing[-1]
        if not self._starts_line(last.start_byte):
            return None
        indent = self._own_line_indent([last], "")
        after = [c for c in params.children if c.start_byte >= last.end_byte]
        comma = after[0] if after and after[0].type == "," else None
        end = (comma or last).end_byte
        row = (comma or last).end_point[0]
        for c in after[1 if comma else 0 :]:
            if "comment" not in c.type or c.start_point[0] != row:
                break
            end = c.end_byte
        close = params.children[-1]
        if close.type == ")" and close.start_point[0] == row:
            at = (comma or last).end_byte
            text = f"\n{indent}{parameter}," if comma else f",\n{indent}{parameter}"
            return src[:at] + text.encode("utf-8") + src[at:]
        line_end = src.find(b"\n", end)
        if line_end == -1:
            line_end = len(src)
        text = f"\n{indent}{parameter}" + ("," if comma else "")
        new_bytes = src[:line_end] + text.encode("utf-8") + src[line_end:]
        if comma is None:
            new_bytes = new_bytes[: last.end_byte] + b"," + new_bytes[last.end_byte :]
        return new_bytes

    def _add_parameter_below(self, params, parameter: str) -> bytes | None:
        """
        The source with `parameter` added to an empty parameter list whose
        `)` is on a line below its `(` (`def f(\\n):`), on a line of its own
        one indentation level deeper than the line of the `(`, after the
        comments that end before the `)` line; the `)` keeps its line. It
        gets a trailing comma where the language takes one and the file
        writes them (_trailing_parameter_comma). None for a list on one
        line, which gets the parameter inline.
        """
        open_paren, close_paren = params.children[0], params.children[-1]
        if open_paren.type != "(" or close_paren.type != ")" or close_paren.start_point[0] == open_paren.end_point[0]:
            return None
        src = self.parser.source_bytes
        after = open_paren
        for child in params.children[1:-1]:
            if "comment" in child.type and child.end_point[0] < close_paren.start_point[0]:
                after = child
        opener_line = src[src.rfind(b"\n", 0, open_paren.start_byte) + 1 : open_paren.start_byte].decode("utf-8")
        ext = self.parser.ext
        unit = self._indent_unit({".py": "    ", ".java": "    ", ".go": "\t"}.get(ext, "  "))
        indent = opener_line[: len(opener_line) - len(opener_line.lstrip(" \t"))] + unit
        comma = "," if self._trailing_parameter_comma(params) else ""
        close_line = src.rfind(b"\n", 0, close_paren.start_byte) + 1
        line = f"\n{indent}{parameter}{comma}\n".encode("utf-8")
        return src[: after.end_byte] + line + src[close_line:]

    def _trailing_parameter_comma(self, params) -> bool:
        """
        Whether a parameter on a line of its own, last in a list like
        `params`, takes a comma after it: always in Go, which needs one
        before a line break; never in C, C++, Java and Ruby, which take
        none; in Python, JS and TS as the file's other lists of that kind
        written one parameter per line mostly do (with one when none does).
        """
        ext = self.parser.ext
        if ext == ".go":
            return True
        if ext != ".py" and ext not in _JS_EXTS:
            return False
        counts = {True: 0, False: 0}
        stack = [self.parser.tree.root_node]
        while stack:
            node = stack.pop()
            stack.extend(node.named_children)
            if node.type != params.type or node.children[-1].type != ")":
                continue
            items = [c for c in node.named_children if "comment" not in c.type]
            if not items or node.children[-1].start_point[0] == items[-1].end_point[0]:
                continue
            following = items[-1].next_sibling
            counts[following is not None and following.type == ","] += 1
        return counts[True] >= counts[False]

    def _refuse_repeated_parameter(self, target: str, params, new_bytes: bytes) -> None:
        """
        Refuse add_parameter's `new_bytes` when the new parameter declares a
        name that the function already has, or declares one twice: the
        parameter list at the old one's place in the edited source, parsed
        apart, is compared with the old one by the names their parameters
        declare (_parameter_names). Go, Java and Ruby take several `_`.
        """
        tree = self.parser.parse(new_bytes)
        bare = self._is_bare_arrow_parameter(params)
        wanted = "formal_parameters" if bare else params.type
        node = tree.root_node.descendant_for_byte_range(params.start_byte, params.start_byte)
        while node is not None and not (node.type == wanted and node.start_byte == params.start_byte):
            node = node.parent
        if node is None:
            return
        if bare:
            before = [self.parser.node_text(params)]
        else:
            before = [n for c in params.named_children if "comment" not in c.type for n in self._parameter_names(c)]
        after = [n for c in node.named_children if "comment" not in c.type for n in self._parameter_names(c, new_bytes)]
        blank = ("_",) if self.parser.ext in (".go", ".java", ".rb") else ()
        for name in after:
            if name not in blank and after.count(name) > max(1, before.count(name)):
                raise ApplierError(f"Parameter '{name}' already exists in '{target}'")

    def _void_parameter(self, existing: list):
        """The `void` of a C or C++ parameter list that declares no
        parameters (`f(void)`), or None: the list's one parameter is the
        type `void` alone, with no declarator (`void *p` is a parameter)."""
        if self.parser.ext not in C_EXTS + CPP_EXTS or len(existing) != 1:
            return None
        node = existing[0]
        if node.type != "parameter_declaration" or node.child_by_field_name("declarator") is not None:
            return None
        return node if self.parser.node_text(node).strip() == "void" else None

    def _is_kwargs(self, param_node) -> bool:
        """Whether a parameter is a Python `**kwargs` (typed or not), which
        must come last."""
        return self._python_parameter_kind(param_node) == "dictionary_splat_pattern"

    def _is_args(self, param_node) -> bool:
        """Whether a parameter is a Python `*args` (typed or not), which
        makes the parameters after it keyword-only."""
        return self._python_parameter_kind(param_node) == "list_splat_pattern"

    def _python_parameter_kind(self, param_node) -> str:
        """The node type of a Python parameter without its annotation
        (`*args: int` is a list_splat_pattern), '' outside Python."""
        if self.parser.ext != ".py":
            return ""
        node = param_node
        if node.type == "typed_parameter" and node.named_children:
            node = node.named_children[0]
        return node.type

    def _parameter_entries(self, params) -> list:
        """The parameters of a parameter list, comments left out, and the
        `...` of a C++ variadic function (`f(int a, ...)`), which is a bare
        token there rather than a node of its own like C's."""
        return [c for c in params.children if (c.is_named and "comment" not in c.type) or c.type == "..."]

    def _stays_last(self, param_node) -> bool:
        """
        Whether a parameter must come after the others, so that add_parameter
        puts a new one before it at the end: a Python `**kwargs` (_is_kwargs),
        a JS/TS rest parameter (`...rest`, with a type too), a Go or Java
        variadic one (`xs ...int`, `String... xs`), the `...` of a C or C++
        variadic function and a C++ parameter pack (`Ts... xs`), which is
        deduced only there, a GNU named variadic macro parameter (`args...`,
        its name and its `...`), and a Ruby `**opts`, `**nil`, `&blk` or
        `...` (_end_index orders Ruby's other kinds).
        """
        ext = self.parser.ext
        kind = param_node.type
        if ext == ".py":
            return self._is_kwargs(param_node)
        if ext in _JS_EXTS:
            pattern = param_node.child_by_field_name("pattern") if kind == "required_parameter" else None
            return (pattern.type if pattern is not None else kind) == "rest_pattern"
        if ext == ".go":
            return kind == "variadic_parameter_declaration"
        if ext == ".java":
            return kind == "spread_parameter"
        if ext == ".rb":
            return kind in ("hash_splat_parameter", "hash_splat_nil", "block_parameter", "forward_parameter")
        if ext in C_EXTS + CPP_EXTS:
            if kind in ("variadic_parameter", "...", "variadic_parameter_declaration"):
                return True
            # A GNU named variadic macro parameter (`args...`): the name,
            # then the `...` in an ERROR node of its own.
            def ellipsis(node) -> bool:
                return node is not None and node.type == "ERROR" and self.parser.node_text(node).strip() == "..."

            return ellipsis(param_node) or (kind == "identifier" and ellipsis(param_node.next_sibling))
        return False

    def _stays_first(self, param_node) -> bool:
        """Whether a parameter must come before the others, so that
        add_parameter puts a new one after it at the start: a TS `this`
        parameter (`this: Window`) and a Java receiver parameter (`A this`)."""
        if self.parser.ext == ".java":
            return param_node.type == "receiver_parameter"
        if self.parser.ext in _JS_EXTS and param_node.type == "required_parameter":
            pattern = param_node.child_by_field_name("pattern")
            return pattern is not None and pattern.type == "this"
        return False

    def _end_index(self, existing: list, parameter: str) -> int:
        """
        The index among a parameter list's entries `existing` that
        add_parameter's "end" puts `parameter` at: before the run of those
        at the end that must stay last (_stays_last). In Ruby, whose
        parameters come in an order of kinds (_ruby_parameter_ranks), it is
        before those of a kind that comes after the new one's: a required
        parameter goes after the splat (Ruby takes required parameters
        there too) but before keyword parameters, `**opts` and `&blk`, an
        optional one before the splat, a keyword one before `**opts`.
        """
        before = len(existing)
        if self.parser.ext == ".rb":
            data = f"def _({parameter})\nend\n".encode("utf-8")
            root = self.parser.parse(data).root_node
            method = root.named_children[0] if root.named_children else None
            params = method.child_by_field_name("parameters") if method is not None else None
            new = [c for c in params.named_children if "comment" not in c.type] if params is not None else []
            if len(new) == 1 and first_syntax_error(root) is None:
                rank = self._ruby_parameter_ranks(new)[0]
                # A required parameter goes as late as Ruby takes one.
                rank = 3 if rank == 0 else rank
                ranks = self._ruby_parameter_ranks(existing)
                while before > 0 and ranks[before - 1] > rank:
                    before -= 1
                return before
        while before > 0 and self._stays_last(existing[before - 1]):
            before -= 1
        return before

    @staticmethod
    def _ruby_parameter_ranks(params: list) -> list[int]:
        """The place of each of the Ruby parameters `params` in Ruby's order
        of parameter kinds: 0 for a required parameter (a name or a
        destructured one), 1 an optional one (`b = 1`), 2 the splat
        (`*rest`), 3 a required one after an optional one or the splat, 4
        a keyword one (`k:`, `k: 1`), 5 `**opts` or `**nil`, 6 `&blk`, 7
        `...`; comments are no parameters."""
        kinds = {
            "optional_parameter": 1,
            "splat_parameter": 2,
            "keyword_parameter": 4,
            "hash_splat_parameter": 5,
            "hash_splat_nil": 5,
            "block_parameter": 6,
            "forward_parameter": 7,
        }
        ranks, late = [], False
        for param in params:
            rank = kinds.get(param.type, 3 if late else 0)
            late = late or rank in (1, 2)
            ranks.append(rank)
        return ranks

    def _old_variadic(self, params, existing: list) -> int | None:
        """
        For add_parameter's "end" in C++: where a new parameter goes when
        the list ends with the old form of a C variadic function, a last
        named parameter followed by `...` without a comma (`int a...`, the
        name an ERROR node to tree-sitter), which is `int a, ...`: the byte
        after that parameter, before the `...`. None for any other list
        (`int...` takes the new one before it, as tree-sitter cannot read
        `int, int b...`), and in a template, where `T a...` may be a
        parameter pack (`Ts... xs` is one anywhere).
        """
        if self.parser.ext not in CPP_EXTS or not existing or existing[-1].type != "variadic_parameter_declaration":
            return None
        last = existing[-1]
        declarator = last.child_by_field_name("declarator")
        if declarator is None or declarator.type != "variadic_declarator" or declarator.named_children:
            return None
        node = params.parent
        while node is not None:
            if node.type == "template_declaration":
                return None
            node = node.parent
        head = [c for c in last.named_children if c.end_byte <= declarator.start_byte]
        return head[-1].end_byte if head and head[-1].type == "ERROR" else None

    def remove_parameter(self, target: str, parameter_name: str) -> str:
        """
        Remove a parameter by name from a function signature. A JS/TS arrow
        function left without its one unparenthesized parameter (`x => 1`)
        becomes `() => 1`. A parenthesized list loses the parameter the way
        _delete_entry deletes an entry: one on a line of its own goes with
        that line, a comment at its end included (comments on other lines
        stay), and a last parameter with no comma after it takes the comma
        before it. Comments are no parameters; a C++ `...` is one
        (_parameter_entries). A name of a Go declaration
        of several (`a, b int`) goes alone with its comments, the others
        keep the type and theirs (_remove_grouped_name); a Go
        parameter given only as a type (`int`) has no name, and a method's
        receiver and named results are not parameters. A name that a JS/TS
        or Ruby destructuring pattern binds with others goes alone
        (_remove_bound_name: `{a: x, b}` without x is `{b}`, `[a, b]`
        without a is `[, b]`, `(a, b)` without a is `(_, b)`); the
        pattern's last name takes the whole parameter. A Python `*` or `/`
        left without the parameter it needs goes with it (_marker_span), a
        Python `*args` before keyword-only parameters leaves a bare `*` in
        its place (`f(a, *args, b)` gives `f(a, *, b)`), and a C function
        left with none gets `(void)` (_void_filled). In C (.c, .h), the last
        named parameter before a `...` is refused: `f(...)` is C++ or C23.
        """
        params = self._find_parameter_list(target)
        if self._is_bare_arrow_parameter(params):
            # `x => ...` without its one parameter is `() => ...`.
            if self.parser.node_text(params) != parameter_name:
                raise ApplierError(f"Parameter '{parameter_name}' not found in '{target}'")
            source_bytes = self.parser.source_bytes
            self._write_bytes(source_bytes[: params.start_byte] + b"()" + source_bytes[params.end_byte :])
            return "Update successful"
        existing = self._parameter_entries(params)

        idx = None
        for i, p in enumerate(existing):
            if parameter_name in self._parameter_names(p):
                idx = i
                break
        if idx is None:
            raise ApplierError(f"Parameter '{parameter_name}' not found in '{target}'")

        pattern = self._parameter_pattern(existing[idx])
        if pattern is not None and [self.parser.node_text(n) for n in self._bound_names(pattern)] != [parameter_name]:
            # One name of a destructured parameter that binds others.
            self._remove_bound_name(pattern, parameter_name)
            return "Update successful"

        names = self._parameter_names(existing[idx])
        if pattern is None and len(names) > 1:
            self._remove_grouped_name(existing[idx], names.index(parameter_name))
            return "Update successful"

        if self._is_args(existing[idx]) and not all(self._is_kwargs(p) for p in existing[idx + 1 :]):
            # The parameters after `*args` but a `**kwargs` are keyword-only:
            # a bare `*` takes its place to keep them so.
            source_bytes = self.parser.source_bytes
            args = existing[idx]
            self._write_bytes(source_bytes[: args.start_byte] + b"*" + source_bytes[args.end_byte :])
            return "Update successful"

        if params.children[0].type == "(" and params.children[-1].type == ")":
            first, count = self._marker_span(existing, idx)
            left = existing[:first] + existing[first + count :]
            if self.parser.ext in C_EXTS and left and all(p.type == "variadic_parameter" for p in left):
                raise ApplierError(
                    f"Removing '{parameter_name}' would leave only `...` in '{target}', and C needs a named "
                    "parameter before `...` (before C23; C++ allows `f(...)`). Keep another parameter before "
                    "it, or rewrite the list with replace_signature."
                )
            new_bytes = self._entry_deleted(params, existing, first, count)
            if count == len(existing) and self.parser.ext in C_EXTS:
                new_bytes = self._void_filled(params, existing[idx], new_bytes)
            self._write_bytes(new_bytes)
            return "Update successful"

        # A Ruby parameter list without parentheses (`def f a, b`).
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

    def _marker_span(self, existing: list, idx: int) -> tuple[int, int]:
        """
        The parameters that remove_parameter deletes for existing[idx], as
        (index of the first, count): in Python also a bare `*` right before
        it when only `**kwargs` would follow the `*` (which must mark a
        keyword-only parameter), and a `/` right after it when it is the
        only parameter before the `/` (which must follow one).
        """
        if self.parser.ext != ".py":
            return idx, 1
        rest = existing[idx + 1 :]
        if idx > 0 and existing[idx - 1].type == "keyword_separator" and all(self._is_kwargs(p) for p in rest):
            return idx - 1, 2
        if idx == 0 and rest and rest[0].type == "positional_separator":
            return 0, 2
        return idx, 1

    def _void_filled(self, params, param, new_bytes: bytes) -> bytes:
        """
        `new_bytes`, the source with `param`, the last parameter of the C
        parameter list `params`, deleted (_entry_deleted), with `void` in
        the emptied list, since `()` declares unspecified parameters in C
        before C23: `(void)`, or, when comments stay in the list, the
        parameter's own text replaced by `void` (`(/* x */ void)`).
        """
        open_end = params.start_byte + 1
        close = params.end_byte - 1 - (len(self.parser.source_bytes) - len(new_bytes))
        if not new_bytes[open_end:close].strip():
            return new_bytes[:open_end] + b"void" + new_bytes[close:]
        src = self.parser.source_bytes
        return src[: param.start_byte] + b"void" + src[param.end_byte :]

    def _remove_grouped_name(self, declaration, k: int) -> None:
        """
        Remove the name `k` of a Go parameter declaration of several (`a, b
        int`), the type staying for the others. A name before the last goes
        with the comma after it and the comments after that, up to the next
        name or a comment on a line of its own, which is the next name's.
        The last name goes with the comma before it, the comments before
        that comma staying (`a /* x */ int`); one that starts a line that
        holds only it, its type and their comma and comments, written one
        per line, takes that line, and its type moves up to the name before
        it, ahead of that name's comma and comments (`b int, // b`). The
        comments after that comma stay too: on the name's line the type
        follows them (`a, /* x */ b int` gives `a /* x */ int`), and when
        they end that line the type moves up before the comma, which stays
        there, and the next parameter or the `)` takes the removed name's
        place (`a, // x` over `b int) {}` gives `a int, // x` over `) {}`).
        """
        src = self.parser.source_bytes
        nodes = declaration.children_by_field_name("name")
        own = nodes[k]
        if k + 1 < len(nodes):
            start, end = own.start_byte, nodes[k + 1].start_byte
            for child in declaration.children:
                if (
                    "comment" in child.type
                    and start < child.start_byte < end
                    and child.start_point[0] > own.end_point[0]
                ):
                    end = child.start_byte
                    break
            self._write_bytes(src[:start] + src[end:])
            return
        prev = nodes[k - 1]
        kind = declaration.child_by_field_name("type")
        line_start = src.rfind(b"\n", 0, own.start_byte) + 1
        if (
            own.start_point[0] > prev.end_point[0]
            and not src[line_start : own.start_byte].strip()
            and kind is not None
            and kind.end_point[0] == own.start_point[0]
        ):
            end = declaration
            after = declaration.next_sibling
            if after is not None and after.type == "," and after.start_point[0] == own.start_point[0]:
                end = after
            line_end = src.find(b"\n", end.end_byte)
            line_end = len(src) if line_end < 0 else line_end
            comment, comment_row = self._trailing_comment(end)
            if comment_row == end.end_point[0] and (comment or not src[end.end_byte : line_end].strip()):
                prev_end = src.find(b"\n", prev.end_byte)
                moved = src[own.end_byte : declaration.end_byte]
                self._write_bytes(src[: prev.end_byte] + moved + src[prev.end_byte : prev_end] + src[line_end:])
                return
        comma = next(
            (c for c in declaration.children if c.type == "," and prev.end_byte <= c.start_byte < own.start_byte), None
        )
        if comma is not None and any(
            "comment" in c.type and comma.end_byte <= c.start_byte < own.start_byte for c in declaration.children
        ):
            # Comments after the comma stay, the type joining the name before.
            kind_text = src[own.end_byte : declaration.end_byte]
            if own.start_point[0] == prev.end_point[0]:
                # `a, /* x */ b int` gives `a /* x */ int`.
                comments = src[comma.end_byte : own.start_byte]
                self._write_bytes(
                    src[: comma.start_byte] + comments + kind_text.lstrip() + src[declaration.end_byte :]
                )
                return
            # `a, // x` over `b int)` gives `a int, // x` over `)`: the comma
            # stays before the line break, as Go needs, and the next
            # parameter or the `)` takes the name's place.
            rest = declaration.end_byte
            after = declaration.next_sibling
            if after is not None and after.type == ",":
                rest = after.end_byte
                while src[rest : rest + 1] in (b" ", b"\t"):
                    rest += 1
            between = src[prev.end_byte : own.start_byte]
            if src[rest : rest + 1] == b")":
                params = declaration.parent
                opener = src[src.rfind(b"\n", 0, params.start_byte) + 1 : params.start_byte]
                between = between.rstrip(b" \t") + opener[: len(opener) - len(opener.lstrip(b" \t"))]
            self._write_bytes(src[: prev.end_byte] + kind_text + between + src[rest:])
            return
        start = comma.start_byte if comma is not None and comma.start_point[0] == prev.end_point[0] else prev.end_byte
        self._write_bytes(src[:start] + src[own.end_byte :])

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
        Replace or insert a Python docstring on a function or class, or on
        the module for the target "" (_replace_module_docstring). The
        new_docstring must be one Python string literal including its
        surrounding quotes, normally triple quotes; anything else is refused
        (_refuse_non_literal). Python-specific. A new docstring for a
        body that shares the line of its signature (`def f(): return 1`) is
        refused.
        """
        if self.parser.ext != ".py":
            raise ApplierError(
                f"replace_docstring only supports .py files (got {self.parser.ext})"
            )

        self._refuse_non_literal(new_docstring)
        if target == "":
            return self._replace_module_docstring(new_docstring)
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
        open_row = source_bytes.count(b"\n", 0, self._body_opening(func_node, body))
        if first_stmt is not None and first_stmt.start_point[0] == open_row:
            raise ApplierError(
                f"The body of '{target}' shares a line with its signature, so a new "
                "docstring has no line of its own to go on. Use replace_function_body "
                "to rewrite the body over several lines, docstring first."
            )
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

    def _replace_module_docstring(self, new_docstring: str) -> str:
        """
        replace_docstring for the target "", the module (as add_key's "" is
        a config file's root). The string statement the module starts with
        is replaced. Without one, the docstring goes in before the first
        statement, so a `from __future__` import stays after it, and below
        the comments before that statement but those right above it, which
        are its own: a `#!` line and an encoding comment
        (_file_directive_lines) with no blank line after them, a header
        comment with the blank lines it has below it. One blank line follows
        the docstring, two before a def or class (_sibling_gap). In a file
        with no statement it goes last, a blank line below a comment.
        replace_docstring has refused a new_docstring that is no string
        literal (_refuse_non_literal).
        """
        nodes = self.parser.tree.root_node.named_children
        first = next((c for c in nodes if "comment" not in c.type), None)
        if first is not None and self._is_docstring_node(first):
            string = first.named_children[0]
            src = self.parser.source_bytes
            self._write_bytes(src[: string.start_byte] + new_docstring.encode("utf-8") + src[string.end_byte :])
            return "Update successful (docstring replaced)"

        doc = _content_lines(new_docstring)
        while doc and not doc[0].strip():
            doc.pop(0)
        while doc and not doc[-1].strip():
            doc.pop()
        directives = self._file_directive_lines()
        comments = [
            c
            for c in nodes
            if "comment" in c.type
            and c.start_point[0] >= directives
            and (first is None or c.end_byte <= first.start_byte)
        ]
        if first is None:
            row = self._last_row(comments[-1]) + 1 if comments else min(directives, len(self.lines))
            above = [""] if comments else []
            self.lines = self.lines[:row] + above + doc + self.lines[row:]
            return self._save() + " (docstring inserted)"
        # The comments right above the first statement are its own.
        row = first.start_point[0]
        for comment in reversed(comments):
            if self._last_row(comment) < row - 1:
                break
            row = comment.start_point[0]
        below = [""] * self._sibling_gap(self.parser.tree.root_node, doc, first)
        self.lines = self.lines[:row] + doc + below + self.lines[row:]
        return self._save() + " (docstring inserted)"

    @staticmethod
    def _refuse_non_literal(new_docstring: str) -> None:
        """Refuse a new_docstring that is not one Python string literal with
        its quotes (`\"\"\"Summary.\"\"\"`), which a docstring must be: bare
        text would go in as code, or be a syntax error. An f-string or bytes
        literal is no docstring either."""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                value = ast.parse(new_docstring.strip(), mode="eval").body
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            value = None
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            raise ApplierError(
                "new_docstring is not a Python string literal: write it with its quotes, "
                "as in '\"\"\"Summary.\"\"\"'."
            )

    def find_references(self, target: str) -> str:
        """
        Return all occurrences of an identifier named `target` in the file, as a
        formatted multi-line string: 'line N: <source line>', in the order
        they come in the file (by line, then column). Read-only, syntactic
        only (no scope awareness). In C++, destructor and operator names
        count as identifiers, named as the targets name them (`~A`,
        `operator==`, `operator bool`, see TreeSitterParser.symbol_name).
        """
        identifier_types = {
            "identifier",
            "field_identifier",
            "type_identifier",
            "property_identifier",
        }
        names = set()
        if self.parser.ext in C_EXTS + CPP_EXTS:
            names = {"destructor_name", "operator_name", "operator_cast"}
            if target.lstrip().startswith(("~", "operator")):
                target = c_name(target)
        results = []
        queue = [self.parser.tree.root_node]
        while queue:
            curr = queue.pop(0)
            if (
                curr.type in identifier_types and self.parser.node_text(curr) == target
            ) or (curr.type in names and self.parser.symbol_name(curr) == target):
                line_num = curr.start_point[0]
                context = self.lines[line_num] if line_num < len(self.lines) else ""
                results.append((curr.start_point, context.strip()))
            queue.extend(curr.named_children)

        if not results:
            return f"(no references to '{target}' found in {self.filepath})"
        # The walk is breadth first; the file reads top to bottom.
        results.sort(key=lambda result: result[0])
        return "\n".join(f"line {point[0] + 1}: {ctx}" for point, ctx in results)

    # ──────────────────────────────────────────────
    # AST Reader tools (read-only, token-efficient)
    # ──────────────────────────────────────────────

    def read_symbol(self, target: str, depth: str = "full") -> str:
        """
        Return source text for a named symbol. `depth` controls how much is
        returned:
          - "full" (default): entire source of the symbol (function body,
            class body, etc.): the code replace_function and delete_symbol
            take (_symbol_unit), from its first byte, with the `;` that ends
            it when one follows it (a TS abstract method's, a JS/TS class
            field's) and without the line break a C/C++ macro ends with or a
            comment after it that the JS/TS grammar puts inside it
            (_code_end). Given back to replace_function as it is, it leaves
            the file unchanged (see _read_shape_indent). Equivalent to the
            old `read_symbol`.
          - "interface": for a class -> header + field declarations + method
            signatures with bodies replaced by ' ...'. For a function (a
            closure in an object or composite literal too) -> just the
            signature. Equivalent to the old `read_interface`.
          - "signature": signature-only. For a function -> the line(s)
            before the body. For a class -> the class header. Equivalent to
            the old `get_signature`.
        "interface" and "signature" start where "full" does, after a JS/TS
        `export` and Python decorators for a function's or class's signature
        (_signature_head), and refuse a symbol that is neither a function
        nor a class, saying what it is (_depth_refusal).

        For config files (JSON/YAML/TOML), "full" returns the value node's
        source ('' for a YAML key with no value) and the other depths raise.
        """
        if depth == "full":
            node = self.parser.find_node_by_name(target)
            if not node and self.parser.ext in (".yml", ".yaml"):
                # A key written with no value (`key:`) reads as no text.
                if self.parser.find_yaml_pair(self.parser.tree.root_node, target) is not None:
                    return ""
            if not node:
                raise ApplierError(f"Target '{target}' not found in {self.filepath}")
            # What replace_function and delete_symbol take, and the `;` that
            # ends a TS abstract method or a JS/TS class field, without a
            # comment after it (_code_end).
            src = self.parser.source_bytes
            first, last = self._symbol_unit(node)
            end = self._code_end(last)
            semi = last.next_sibling
            if (
                self.parser.ext not in _CONFIG_EXTS
                and end == last.end_byte
                and semi is not None
                and semi.type == ";"
                and not semi.is_named
                and not src[last.end_byte : semi.start_byte].strip()
            ):
                end = semi.end_byte
            if end > first.start_byte and src[end - 1 : end] == b"\n":
                # A C/C++ macro ends with its line break.
                end -= 1
            return src[first.start_byte : end].decode("utf-8")
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
        signatures (with bodies replaced by ' ...'), each member at its
        indentation relative to the class's header (see _interface_line) and
        ending as written (_member_text), and its closing (a C/C++ class's
        `};`), from where read_symbol's full text starts to where it ends (a
        TS `declare`, the C typedef or declaration a struct is the type of,
        `} N;`, included; a typedef of a struct, union or enum without a tag
        shows that type's members). For a function target (a closure in an
        object or composite literal too), returns just its signature, and
        for a Go type its declaration as read_symbol reads it (a type in a
        `type (...)` group alone) with its methods' signatures. Any other
        symbol (a variable, a constant, a type alias) is refused
        (_depth_refusal). Read-only.
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

        # Function target (a bodiless method, a C/C++ prototype, a JS/TS
        # function bound to a name or a closure in an object or composite
        # literal, too) -- return signature only
        if (
            inner.type in func_types
            or inner.type in _BODILESS_FUNCTIONS
            or (ext in _JS_EXTS and inner.type in JS_FUNCTION_VALUES)
            or inner.type == "func_literal"
            or self._callable(node, target) is not node
            or self._declares_c_function(node, target)
        ):
            return self._get_signature(target)

        # Go: struct/interface definition + top-level receiver methods
        # (checked before body lookup because type_spec has no 'body' field)
        if ext in (".go",) and inner.type == "type_spec":
            return self._read_interface_go(node, inner)

        # A C/C++ typedef of a struct, union or enum without a tag has the
        # members of that type.
        inner = self._typedef_struct(inner, enums=True)
        body = inner.child_by_field_name("body")
        if body is None:
            # A Ruby class or module with nothing in it is its whole text.
            if self._header_without_body(inner) is None:
                raise self._depth_refusal(target, inner, "interface")
            return self.parser.node_text(node)

        source = self.parser.source_bytes

        # Header: everything from the symbol's start (decorators, a JS/TS
        # `export` and `declare` and a C typedef included, where read_symbol
        # starts it, see _symbol_unit) up to body content. `base`, the
        # indentation of the class's own line, comes off every line shown.
        first, last = self._symbol_unit(node)
        head = first.start_byte
        base = self._get_indent(self.lines[first.start_point[0]])
        if ext in (".py", ".rb"):
            header = source[head:body.start_byte].decode("utf-8").rstrip()
        else:
            # Brace-delimited: body node starts with {, include it in header
            header = source[head:body.start_byte + 1].decode("utf-8").rstrip()

        parts = [self._interface_line(head, header, base, base)]

        # Walk body members: signatures for methods, full text for fields
        indent = self._member_indent(inner, list(body.named_children))
        self._collect_interface_members(body, func_types, parts, base, indent)

        # Closing token
        if ext in (".rb",):
            tail = source[body.end_byte:node.end_byte].decode("utf-8").strip()
            if tail:
                tail_start = node.end_byte - len(tail.encode("utf-8"))
                parts.append(self._interface_line(tail_start, tail, base, base))
        elif ext not in (".py",):
            # Brace-delimited: closing } (or }; for C/C++, see _symbol_span,
            # and `} N;` for a typedef), without a comment after it, which
            # the JS/TS grammar puts inside a namespace's body (_code_end).
            brace = self._code_end(body) - 1
            end = max(self._code_end(last), brace + 1)
            closing = source[brace:end].decode("utf-8").rstrip()
            parts.append(self._interface_line(brace, closing, base, base))

        return "\n".join(parts)

    def _interface_func_types(self) -> set:
        """Return the set of AST node types that represent functions/methods for this language."""
        ext = self.parser.ext
        if ext == ".py":
            return {"function_definition", "decorated_definition"}
        if ext in _JS_EXTS:
            return {"function_declaration", "generator_function_declaration", "method_definition"}
        if ext in (".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh"):
            return {"function_definition"}
        if ext in (".rb",):
            return {"method", "singleton_method"}
        if ext in (".go",):
            return {"function_declaration", "method_declaration"}
        if ext == ".java":
            return {"method_declaration", "constructor_declaration"}
        return set()

    @staticmethod
    def _ruby_wrapped_method(call):
        """The method that a Ruby `call` node takes as its one argument
        (`private def m`, `private_class_method def self.f`), or None."""
        arguments = call.child_by_field_name("arguments")
        methods = [c for c in arguments.named_children if "comment" not in c.type] if arguments is not None else []
        if len(methods) != 1 or methods[0].type not in ("method", "singleton_method"):
            return None
        return methods[0]

    def _extract_method_sig(self, child, func_types) -> str | None:
        """Extract the signature of a method node with ' ...' appended, or
        None if not a method. It starts at the member's start: decorators, a
        C++ member template's header, a TS namespace's `export` and a Ruby
        `private` included. A Ruby method with nothing in it shows its header
        (_header_span), an endless one what comes before its `=`
        (_signature_end)."""
        c_inner = child
        if child.type == "decorated_definition":
            for cc in child.named_children:
                if cc.type == "function_definition":
                    c_inner = cc
                    break
        elif child.type == "template_declaration":
            # A C++ member template: its signature starts at its header.
            c_inner = self._template_entity(child) or child
        elif child.type == "export_statement":
            # A function a TS namespace exports: from its `export`.
            c_inner = child.child_by_field_name("declaration") or child
        elif child.type == "call" and self.parser.ext == ".rb":
            # `private def m`: from its `private`.
            c_inner = self._ruby_wrapped_method(child) or child

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
            header = self._header_span(c_inner)
            if header is not None:
                # An empty Ruby method (`def f; end`).
                sig_end = header[1]
            else:
                # Abstract/interface method with no body -- include full text
                return self.parser.node_text(child)
        else:
            sig_end = self._signature_end(c_inner, c_body)

        sig = self.parser.source_bytes[child.start_byte:sig_end].decode("utf-8").rstrip()
        return sig + " ..."

    def _collect_interface_members(self, container, func_types, parts, base: str, indent: str):
        """Walk a class body, appending signatures for methods and full text
        for fields, at their indentation relative to the class (see
        _interface_line; `indent` for a member that follows other code on
        its line). A Ruby `class << self` shows its header, its members and
        its `end`. A comment after the body's `}`, which the JS/TS grammar
        puts inside it (_code_end), is none of its members."""
        close = self._code_end(container)
        for child in container.named_children:
            if child.start_byte >= close:
                break
            sig = self._extract_method_sig(child, func_types)
            if sig is not None:
                parts.append(self._interface_line(child.start_byte, sig, base, indent))
            elif child.type in ("enum_body_declarations", "class_body", "interface_body"):
                semi, prev = child.child(0), child.prev_sibling
                if child.type == "enum_body_declarations" and semi.type == ";" and not prev.is_named:
                    # A Java enum's `;` that no constant or comment before it
                    # shows (_member_text): after a trailing comma, or with
                    # no constants before it.
                    if prev.type == "," and self._same_line(prev.end_byte, semi.start_byte) and parts:
                        parts[-1] += ";"
                    else:
                        parts.append(self._interface_line(semi.start_byte, ";", base, indent))
                self._collect_interface_members(child, func_types, parts, base, indent)
            elif child.type == "singleton_class":
                # Ruby's `class << self`, a block of the class's own methods:
                # its header, their signatures and its `end`.
                body, end = child.child_by_field_name("body"), child.children[-1]
                header_end = body.start_byte if body is not None else end.start_byte
                header = self.parser.source_bytes[child.start_byte : header_end].decode("utf-8").rstrip()
                parts.append(self._interface_line(child.start_byte, header, base, indent))
                if body is not None:
                    self._collect_interface_members(body, func_types, parts, base, indent)
                if end.type == "end":
                    parts.append(self._interface_line(end.start_byte, "end", base, indent))
            else:
                text = self._member_text(child)
                if child.type == "access_specifier":
                    # The grammar leaves the `:` of a C++ `public:` outside.
                    text += ":"
                parts.append(self._interface_line(child.start_byte, text, base, indent))

    def _member_text(self, member) -> str:
        """
        The source of a class member other than a method, as
        read_symbol(depth="interface") shows it: with the `;` or `,` that
        ends it where the grammar leaves that outside the member (TS and JS
        fields, TS interface members, enum members, a Python or Ruby
        statement before a `;`), and for a Java enum's last constant the `;`
        that ends the constants.
        """
        src = self.parser.source_bytes
        after = member.next_sibling
        if after is not None and after.type == "enum_body_declarations":
            after = after.child(0)
        end = member.end_byte
        if (
            after is not None
            and after.type in _SEPARATORS
            and not after.is_named
            and not src[end : after.start_byte].strip()
        ):
            end = after.end_byte
        return src[member.start_byte : end].decode("utf-8")

    def _interface_line(self, start_byte: int, text: str, base: str, indent: str) -> str:
        """
        `text`, source that starts at start_byte (a class's header, a member
        or its signature, the closing brace), as read_symbol(depth="interface")
        shows it: its first line at the indentation of its line in the file,
        or at `indent` when other code comes before it there, and every line
        without `base`, the indentation of the class's own line, so members
        keep their indentation relative to the class header. A line indented
        less than `base` is left as it is.
        """
        src = self.parser.source_bytes
        prefix = src[src.rfind(b"\n", 0, start_byte) + 1 : start_byte].decode("utf-8")
        lines = ((prefix if not prefix.strip() else indent) + text).split("\n")
        return "\n".join(line[len(base):] if line.startswith(base) else line for line in lines)

    def _read_interface_go(self, node, inner) -> str:
        """Go-specific: struct/interface definition + all receiver method signatures."""
        # The type as read_symbol shows it: with its `type` when that declares
        # only it, a type in a `type (...)` group alone.
        first, last = self._symbol_unit(node)
        parts = [self.parser.source_bytes[first.start_byte : last.end_byte].decode("utf-8")]
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
          - "bottom" (default): append to end of file, or in a C/C++ header
                   whose code is all inside an include guard
                   (_include_guard), before its `#endif`, which keeps the
                   blank lines it had above it.
          - "top": insert after the preamble (package/imports/includes/leading
                   comments and, for Python, the module docstring) and before
                   the first non-preamble declaration. For files with no
                   preamble, inserts at line 0.
        The content is separated from the code on each side as siblings are
        (_sibling_gap): by two blank lines in a Python module when it or that
        code is a def or class (PEP 8), else by one; at the bottom, one-line
        content after one-line code stacked with the code above it is
        stacked too (_gap_after); at the top, the blank lines the file had
        after its preamble stay below the content when they are more. The
        content goes in as written, except that read_symbol's text of a
        nested symbol, whose later lines keep the indentation they have in
        its class, is moved to column 0 with them (_from_read_shape), and
        that its indentation steps are tabs in a Go file or one indented
        with tabs (_tabbed).
        """
        if position not in ("bottom", "top"):
            raise ApplierError(f"position must be 'bottom' or 'top', got: {position}")

        content_lines = _content_lines(content)
        read = self._from_read_shape(content_lines, "")
        if read is not content_lines:
            # read_symbol's text of a nested symbol, moved to the top level.
            content_lines = self._reindent(read, "")
        content_lines = self._tabbed(content_lines, "")

        root = self.parser.tree.root_node
        guard = self._include_guard() if position == "bottom" else None
        if guard is not None:
            # A header's code is inside its include guard: the content goes
            # before its `#endif`, as far from it as the code above was.
            node, define = guard
            endif = node.children[-1]
            inside = [
                c for c in node.named_children if c.start_byte >= define.start_byte and c.end_byte <= endif.start_byte
            ]
            row = endif.start_point[0]
            before = self.lines[:row]
            blank = 0
            while before and not before[-1].strip():
                before.pop()
                blank += 1
            code = [c for c in inside if c.start_byte > define.start_byte]
            gap = self._gap_after(node, code[-1], content_lines, define) if code else self._sibling_gap(node, define, content_lines)
            self.lines = before + [""] * gap + content_lines + [""] * blank + self.lines[row:]
            return self._save()
        if position == "bottom":
            while self.lines and not self.lines[-1].strip():
                self.lines.pop()
            if self.lines:
                last = root.named_children[-1] if root.named_children else None
                self.lines += [""] * self._gap_after(root, last, content_lines)
            self.lines.extend(content_lines)
            return self._save()

        # position == "top": after the preamble, separated from it and from
        # the code below it as siblings are (_sibling_gap), or by the blank
        # lines the file had there when they are more.
        at = self._find_preamble_end()
        before, after = self.lines[:at], self.lines[at:]
        blank = 0
        while blank < len(after) and not after[blank].strip():
            blank += 1
        rest = after[blank:]
        following = next((c for c in root.named_children if c.start_point[0] >= at and "comment" not in c.type), None)
        gap_above = self._sibling_gap(root, None, content_lines) if before else 0
        gap_below = max(blank, self._sibling_gap(root, content_lines, following)) if rest else 0
        self.lines = before + [""] * gap_above + content_lines + [""] * gap_below + rest
        return self._save()

    def _find_preamble_end(self) -> int:
        """
        The line at which the code after the file's preamble starts, 0 when
        it has none (add_top_level's position "top", add_import's first
        import). The preamble is what comes first in a file: the directives
        that only work there (a `#!` line, a Python or Ruby encoding or Ruby
        magic comment, a JS/TS hash-bang line and directive prologue such
        as 'use strict', a TS `///` directive or `// @ts-nocheck`, C/C++
        `#pragma once` and the `#ifndef`/`#define` of an include guard that
        holds all the code), a Go package clause or Java package
        declaration, the Python module docstring, imports and includes
        (_is_import), and the comments before the last of them. Before the
        first of them, the file's first block of comments is its header and
        part of the preamble too, unless it is the leading comment of the
        code right below it (no blank line between); other comments after
        the preamble belong to the code after it.
        """
        ext = self.parser.ext
        guard = self._include_guard()
        directive_lines = self._file_directive_lines()
        last = directive_lines - 1
        pending: list = []
        stop = None
        # Still where a Python docstring or a JS/TS directive can be.
        prologue = True
        # Whether a preamble node other than a directive line came yet.
        seen = False
        for child in self._top_level_nodes():
            if "comment" in child.type:
                if child.start_point[0] < directive_lines:
                    last = max(last, self._last_row(child))
                else:
                    pending.append(child)
                continue
            preamble = (
                self._is_import(child)
                or child.type in ("package_clause", "package_declaration", "hash_bang_line")
                or self._pragma_once(child)
                or (guard is not None and child == guard[1])
            )
            if not preamble and prologue and ext in (".py",) + _JS_EXTS and self._string_statement(child):
                preamble = True
                prologue = ext != ".py"
            elif child.type != "hash_bang_line":
                prologue = False
            if not preamble:
                stop = child
                break
            last = max(last, self._last_row(child))
            pending = []
            seen = seen or child.type != "hash_bang_line"
        keep = len(pending)
        if stop is not None:
            # The comments right above the code are its own.
            attached = len(pending)
            row = stop.start_point[0]
            while attached and self._last_row(pending[attached - 1]) >= row - 1:
                attached -= 1
                row = pending[attached].start_point[0]
            keep = 0
            if not seen and attached:
                # The file's header: its first block of comments.
                keep = 1
                while keep < attached and pending[keep].start_point[0] <= self._last_row(pending[keep - 1]) + 1:
                    keep += 1
            keep = max([keep] + [i + 1 for i, c in enumerate(pending) if self._directive_comment(c)])
        if keep:
            last = max(last, self._last_row(pending[keep - 1]))
        return last + 1

    def _include_guard(self):
        """
        The include guard of a C/C++ header that holds all of its code, as
        (the `#ifndef X_H` node, its `#define X_H` node): nothing but
        comments is outside it, and the first directive inside defines the
        name it tests, with no value. None for any other file.
        """
        if self.parser.ext not in C_EXTS + CPP_EXTS:
            return None
        code = [c for c in self.parser.tree.root_node.named_children if "comment" not in c.type]
        if len(code) != 1 or code[0].type != "preproc_ifdef" or code[0].children[0].type != "#ifndef":
            return None
        guard = code[0]
        name = guard.child_by_field_name("name")
        define = next((c for c in guard.named_children if c != name and "comment" not in c.type), None)
        if (
            name is None
            or define is None
            or define.type != "preproc_def"
            or define.child_by_field_name("value") is not None
            or self.parser.node_text(define.child_by_field_name("name")) != self.parser.node_text(name)
        ):
            return None
        return guard, define

    def _top_level_nodes(self) -> list:
        """The nodes among which the file's preamble and imports are: the
        root's named children, the include guard of a C/C++ header that
        holds all of its code (_include_guard) giving way to its `#define`
        and the nodes after it."""
        nodes = list(self.parser.tree.root_node.named_children)
        guard = self._include_guard()
        if guard is None:
            return nodes
        node, define = guard
        inside = [c for c in node.named_children if c.start_byte >= define.start_byte]
        return [c for c in nodes if c.end_byte <= node.start_byte] + inside + [
            c for c in nodes if c.start_byte >= node.end_byte
        ]

    def _is_import(self, node) -> bool:
        """Whether a top-level node is an import (_import_node_types): a
        Ruby `call` only when it is a `require`, in JS/TS also a CommonJS
        `require` (_is_js_require), and in C/C++ also a preprocessor
        conditional that holds includes and no code (_include_block)."""
        ext = self.parser.ext
        if ext == ".rb" and node.type == "call":
            return self._is_ruby_require_call(node)
        if node.type in self._import_node_types():
            return True
        if ext in _JS_EXTS:
            return self._is_js_require(node)
        return ext in C_EXTS + CPP_EXTS and node.type in _PREPROC_CONDITIONALS and self._include_block(node)

    def _is_js_require(self, node) -> bool:
        """Whether a JS/TS statement only loads modules with CommonJS
        `require`: `require('x');`, or a `const`/`let`/`var` each of whose
        names is given one (`const fs = require('fs');`, `const { a } =
        require('b').c;`)."""

        def required(value) -> bool:
            while value is not None and value.type == "member_expression":
                value = value.child_by_field_name("object")
            if value is None or value.type != "call_expression":
                return False
            function, arguments = value.child_by_field_name("function"), value.child_by_field_name("arguments")
            strings = [c for c in arguments.named_children if "comment" not in c.type] if arguments is not None else []
            return (
                function is not None
                and self.parser.node_text(function) == "require"
                and len(strings) == 1
                and strings[0].type in ("string", "template_string")
            )

        if node.type == "expression_statement":
            return len(node.named_children) == 1 and required(node.named_children[0])
        if node.type not in ("lexical_declaration", "variable_declaration"):
            return False
        declarators = [c for c in node.named_children if c.type == "variable_declarator"]
        return bool(declarators) and all(required(d.child_by_field_name("value")) for d in declarators)

    def _include_block(self, node) -> bool:
        """Whether a C/C++ preprocessor conditional holds includes and
        nothing but them, other directives and comments, in all of its
        branches (`#ifdef _WIN32` / `#include <windows.h>` / `#endif`)."""
        directives = ("preproc_include", "preproc_def", "preproc_function_def", "preproc_call") + _PREPROC_CONDITIONALS
        found = False
        stack = [node]
        while stack:
            block = stack.pop()
            for i, child in enumerate(block.children):
                if not child.is_named or "comment" in child.type:
                    continue
                if block.field_name_for_child(i) in ("name", "condition"):
                    continue
                if child.type not in directives:
                    return False
                if child.type == "preproc_include":
                    found = True
                elif child.type in _PREPROC_CONDITIONALS:
                    stack.append(child)
        return found

    def _pragma_once(self, node) -> bool:
        """Whether a node is a C/C++ `#pragma once`."""
        if node.type != "preproc_call":
            return False
        directive, argument = node.child_by_field_name("directive"), node.child_by_field_name("argument")
        return (
            directive is not None
            and self.parser.node_text(directive) == "#pragma"
            and argument is not None
            and self.parser.node_text(argument).strip() == "once"
        )

    @staticmethod
    def _string_statement(node) -> bool:
        """Whether a node is a statement that is only a string: a Python
        docstring, a JS/TS directive such as 'use strict'."""
        return node.type == "expression_statement" and [c.type for c in node.named_children] == ["string"]

    def _directive_comment(self, node) -> bool:
        """Whether a comment is a JS/TS directive that must come before the
        code: a `///` directive (`/// <reference types="node" />`) or a
        pragma of TypeScript, Flow or JSX (`// @ts-nocheck`, `// @flow`,
        `/** @jsx h */`)."""
        if self.parser.ext not in _JS_EXTS:
            return False
        return bool(re.match(r"///|(//|/\*)\*?\s*@(ts-|flow\b|jsx)", self.parser.node_text(node)))

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
          - Ruby embedded documents (`=begin` ... `=end`, at column 0
            whatever the symbol's indentation)
        Stops at the first blank line or non-comment code line, and at the
        lines that only look like a comment on the symbol: a line with code
        before or between block comments (`int x = 1; /* n */`), a line
        inside a multi-line string, template literal or YAML block scalar
        (_comment_starts_line), and a comment (for a block comment, its
        first line) indented deeper than the symbol's first line
        (_indented_deeper), which ends the code above it, such as a comment
        under the last statement of the function before. Python and Ruby
        directives at the top of the file (a `#!` line, encoding and magic
        comments) are never included (_file_directive_lines).
        """
        prefixes = self._comment_prefixes()
        if not prefixes:
            return None

        supports_block = self._supports_block_comments()
        # A comment indented deeper than the symbol is inside the code above
        # it (`    # end of f` under the last line of f's body, a comment in
        # a YAML mapping above the next top-level key), not on the symbol.
        indent = self._get_indent(self.lines[start_line]) if start_line < len(self.lines) else ""
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
                    if (
                        not stripped.startswith("/*")
                        or not self._comment_starts_line(i)
                        or self._indented_deeper(line, indent)
                    ):
                        # `code; /* ...` -- the block trails code, so it is
                        # not part of the leading comment; nor is a `/*`
                        # inside a string or one indented deeper.
                        i = block_end
                        break
                i -= 1
                continue

            if not stripped:
                # Blank line separator -- stop walking
                break

            if self.parser.ext == ".rb" and line.startswith("=end"):
                # The end of a Ruby embedded document (`=begin` ... `=end`,
                # both at column 0), which is one comment.
                node = self.parser.tree.root_node.descendant_for_point_range((i, 0), (i, 0))
                if node is None or not self._is_embedded_document(node) or node.end_point[0] != i:
                    break
                i = node.start_point[0] - 1
                continue

            # Line comment (#, //, etc.)
            if any(stripped.startswith(p) for p in prefixes):
                if not self._comment_starts_line(i) or self._indented_deeper(line, indent):
                    # A `#` or `//` line inside a multi-line string,
                    # template literal or YAML block scalar is text, and
                    # one indented deeper is in the code above.
                    break
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
                    if not self._comment_starts_line(i) or self._indented_deeper(line, indent):
                        break
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
        # A `#!` line and the encoding and magic comments after it are not
        # part of any symbol's comment.
        first_comment_line = max(i + 1, self._file_directive_lines())
        if first_comment_line >= start_line:
            return None
        return (first_comment_line, start_line)

    def _comment_starts_line(self, row: int) -> bool:
        """
        Whether the text on line `row` starts with a comment in the parse
        tree, not only by its characters: a line inside a multi-line string,
        template literal or YAML block scalar that starts with `#`, `//` or
        `/*` is part of that string, and never a symbol's leading comment.
        The text starts after any whitespace, as _find_leading_comment_range
        strips it (a form feed before a `#` included).
        """
        line = self.lines[row]
        column = len(line[: len(line) - len(line.lstrip())].encode("utf-8"))
        node = self.parser.tree.root_node.descendant_for_point_range((row, column), (row, column))
        return node is not None and "comment" in node.type

    def _indented_deeper(self, line: str, indent: str) -> bool:
        """Whether `line` is indented deeper than a line indented by
        `indent`: its own indentation is longer and starts with `indent`.
        With tabs and spaces mixed the other way, neither is deeper."""
        own = self._get_indent(line)
        return len(own) > len(indent) and own.startswith(indent)

    def _file_directive_lines(self) -> int:
        """
        The number of lines at the top of a Python or Ruby file that are
        directives rather than comments: a `#!` line, an encoding
        declaration on one of the first two lines (`# -*- coding: utf-8 -*-`)
        and, in Ruby, the magic comments after them (`# frozen_string_literal:
        true`). They only work there, so they never count as a symbol's
        leading comment, which edits move or remove.
        """
        ext = self.parser.ext
        if ext not in (".py", ".rb"):
            return 0
        n = 0
        while n < len(self.lines):
            line = self.lines[n]
            if not (
                (n == 0 and line.startswith("#!"))
                or (n < 2 and _CODING_COMMENT.match(line))
                or (ext == ".rb" and _RUBY_MAGIC_COMMENT.match(line))
            ):
                break
            n += 1
        return n

    def _find_symbol_for_comment(self, target: str):
        """
        Resolve a comment target. In YAML and TOML it is the whole key-value
        pair at the key path (_find_config_pair_by_path, so a YAML key with
        no value is found too) or, in TOML, a [table] whose header spells
        the path (TreeSitterParser.toml_table); comment tools operate on
        positional anchors, so tables are valid targets. A key that does not
        start its line (inside a flow mapping or inline table) is refused,
        as the comment line above belongs to the key the line starts with.
        In source files it is the first node of the symbol find_node_by_name
        finds (_symbol_unit), so the comment goes above its decorators, a
        JS/TS `export` and a C++ `template <...>`; a symbol that does not
        start its line is refused the same way.
        """
        if self.parser.ext in (".yml", ".yaml", ".toml"):
            node = self._find_config_pair_by_path(target)
            if node is None and self.parser.ext == ".toml":
                node = self.parser.toml_table(self.parser.tree.root_node, target)
            if node is not None and not self._starts_line(node.start_byte):
                raise ApplierError(
                    f"'{target}' does not start its line (it is inside a flow mapping or "
                    "inline table), so it has no leading comment of its own; a comment "
                    "line above it would belong to the key the line starts with"
                )
            return node
        node = self.parser.find_node_by_name(target)
        if node is None:
            return None
        first, last = self._symbol_unit(node)
        if self._line_sharing(first, last)[0]:
            raise ApplierError(
                f"'{target}' does not start its line (other code comes before it there), "
                "so it has no leading comment of its own; a comment line above it would "
                "belong to the code the line starts with. Edit the comment with your "
                "normal edit tool."
            )
        return first

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
        Types come first (a type alias as `type`), then each name a `var` or
        `const` declares (`variable`, `constant`), then functions.
        """
        types_by_name: dict[str, dict] = {}
        values: list[tuple[str, str, int]] = []
        top_level_funcs: list[tuple[str, int]] = []
        methods_by_receiver: dict[str, list[tuple[str, int]]] = {}

        for child in root.named_children:
            if child.type == "type_declaration":
                for spec in child.named_children:
                    if spec.type in ("type_spec", "type_alias"):
                        name_node = spec.child_by_field_name("name")
                        if name_node:
                            name = self.parser.node_text(name_node)
                            kind = "type"
                            for inner in spec.named_children if spec.type == "type_spec" else []:
                                if inner.type == "struct_type":
                                    kind = "struct"
                                    break
                                if inner.type == "interface_type":
                                    kind = "interface"
                                    break
                            types_by_name[name] = {"kind": kind, "line": spec.start_point[0] + 1}
            elif child.type in ("var_declaration", "const_declaration"):
                kind = "variable" if child.type == "var_declaration" else "constant"
                specs = [c for c in child.named_children if c.type in ("var_spec", "const_spec")]
                for group in child.named_children:
                    if group.type in ("var_spec_list", "const_spec_list"):
                        specs += [c for c in group.named_children if c.type in ("var_spec", "const_spec")]
                for spec in specs:
                    for name_node in self.parser.declared_names(spec):
                        values.append((kind, self.parser.node_text(name_node), spec.start_point[0] + 1))
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

        for kind, name, line in values:
            lines_out.append(f"{kind} {name} (line {line})")

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
