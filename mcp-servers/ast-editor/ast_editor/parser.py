import json
import os
import re
from typing import NamedTuple
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_json
import tree_sitter_yaml
import tree_sitter_toml
import tree_sitter_c
import tree_sitter_cpp
from tree_sitter import Language, Parser, Node
import tree_sitter_ruby
import tree_sitter_go
import tree_sitter_java

C_EXTS = (".c", ".h")
CPP_EXTS = (".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".hh")

RUBY_EXTS = (".rb",)
GO_EXTS = (".go",)
JS_EXTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

# The anonymous value of `export default function () {}` / `export default
# class {}`, named `default`, counts as this kind of declaration.
DEFAULT_EXPORT_KINDS = {
    "function_expression": "function_declaration",
    "class": "class_declaration",
}

# Values that make a JS/TS `const`/`let`/`var` a function in all but name
# (`const f = () => {}`), which list_symbols lists and the tools target as
# functions; "function" is older grammars' name for function_expression.
JS_FUNCTION_VALUES = ("arrow_function", "function_expression", "function", "generator_function")

# The C/C++ tags and TS type-only declarations, which a target names with
# their keyword in front (`struct stat`, `type User`) when another
# declaration of their scope, a function, variable or typedef, or a TS
# value, shares their name (TreeSitterParser.select).
_C_TAG_KEYWORDS = {
    "struct_specifier": "struct",
    "union_specifier": "union",
    "enum_specifier": "enum",
    "class_specifier": "class",
}
_TS_TYPE_KEYWORDS = {"type_alias_declaration": "type", "interface_declaration": "interface"}

# The C++ method qualifiers that tell overloads with the same parameter
# types apart (`int &get(int);`, `int get(int) const;`), which a target may
# write after its parameter types.
_CPP_METHOD_QUALIFIERS = ("type_qualifier", "ref_qualifier")
_QUALIFIERS_AT_END = re.compile(r"\)((?:\s*(?:\bconst\b|\bvolatile\b|&&|&))+)\s*$")

# The C++ and TS namespace nodes: a namespace is one container with the
# other blocks of its name in its scope and, in TS, with the class, function
# or enum of its name (merged_containers).
NAMESPACES = ("namespace_definition", "internal_module", "module")

# The C/C++ class, struct, union and enum nodes.
C_TYPE_SPECIFIERS = ("class_specifier", "struct_specifier", "union_specifier", "enum_specifier")

# The C/C++ nodes that name what a declarator declares: a variable, field,
# function or typedef name, a namespace, a destructor (`~A`) or operator
# (`operator==`, the conversion `operator bool`).
_C_NAMES = (
    "identifier",
    "field_identifier",
    "type_identifier",
    "namespace_identifier",
    "destructor_name",
    "operator_name",
    "operator_cast",
)

# The nodes between a declaration and the scope it declares its name in
# (see TreeSitterParser._scope): C preprocessor conditionals, `extern "C"`,
# C++ templates, the C/C++ declarations around a struct (`struct S {...}
# s;`, `typedef struct N {...} N;`) and the TS `export` and `declare`.
_SCOPE_WRAPPERS = (
    "preproc_if",
    "preproc_ifdef",
    "preproc_else",
    "preproc_elif",
    "preproc_elifdef",
    "linkage_specification",
    "template_declaration",
    "declaration",
    "field_declaration",
    "type_definition",
    "export_statement",
    "ambient_declaration",
)

# The JS/TS functions and methods, which a name they share with data (a
# class field, a `var`) targets (TreeSitterParser.select).
_JS_FUNCTIONS = (
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "function_signature",
    "method_signature",
    "abstract_method_signature",
)

# The names of a C++ class or namespace declared with its scope (`struct
# A::B {...}`, `namespace a::b {}`), which name it by their last part too
# (TreeSitterParser.declared_name).
_QUALIFIED_NAMES = ("qualified_identifier", "nested_namespace_specifier")


def c_name(text: str) -> str:
    """A C++ destructor or operator name as list_symbols shows it and a
    target may write it: with the spaces between words only, so `~ A` is
    `~A`, `operator ==` is `operator==`, `operator new []` is `operator
    new[]` and `operator const char *` is `operator const char*`."""
    return re.sub(r" (?=\W)|(?<=\W) ", "", " ".join(text.split()))


def parameter_key(text: str) -> str:
    """A parameter type as an overload is matched by it: one space between
    words and none around other characters, so that `const A &`, `const
    A&` and `const A& ` are one type, as are `std::map<int, int>` and
    `std::map<int,int>`, or `String ...` and `String...`."""
    return re.sub(r"\s*([^\w\s])\s*", r"\1", " ".join(text.split()))


_C_INTEGER_WORDS = {"signed", "unsigned", "short", "long", "int", "char"}


def c_parameter_key(text: str) -> str:
    """
    A C/C++ parameter type as an overload is matched by it: parameter_key,
    with the spellings of one type made one, so that a prototype and a
    definition that write it differently declare one function:
      - without a `const` or `volatile` on the parameter itself (`const int`
        and `int`, `char *const` and `char *`), which is no part of its
        type, and with one on what it points to written first (`char const
        *` is `const char *`);
      - an integer type by its shortest name (`unsigned int` is `unsigned`
        and `long long int` is `long long`, `signed` and `signed int` are
        `int`; `signed char` stays);
      - an array as the pointer it is (`int[]` and `int[3]` are `int *`,
        `char *[]` is `char **`, `int[2][3]` is `int (*)[3]`);
      - a class, struct, union or enum without its keyword (`struct S *` is
        `S *`), and a type without `typename`.
    """
    key = re.sub(r"\b(?:struct|class|union|enum|typename) (?=[\w:])", "", parameter_key(text))
    depth, cut = 0, len(key)
    for i, char in enumerate(key):
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(depth - 1, 0)
        elif depth == 0 and char in "*&([":
            cut = i
            break
    specifiers, declarator = key[:cut].strip(), key[cut:]
    words = split_top_level(specifiers, " ", "<>")
    qualifiers = [w for w in ("const", "volatile") if w in words]
    base = [w for w in words if w not in ("const", "volatile")]
    if base and set(base) <= _C_INTEGER_WORDS:
        sign = "unsigned " if "unsigned" in base else ""
        if "char" in base:
            base = [("signed " if "signed" in base else sign) + "char"]
        elif "short" in base:
            base = [sign + "short"]
        elif "long" in base:
            base = [sign + " ".join(["long"] * base.count("long"))]
        else:
            base = [sign.strip() or "int"]
    array = re.fullmatch(r"([*&]*)\[[^\]]*\]((?:\[[^\]]*\])*)", declarator)
    if array is not None:
        declarator = array.group(1) + ("(*)" + array.group(2) if array.group(2) else "*")
    # A qualifier after the last `*` is the parameter's own.
    declarator = re.sub(r"(?<=\*)(?: ?(?:const|volatile))+$", "", declarator)
    if not declarator:
        qualifiers = []
    return " ".join(qualifiers + base) + declarator


def parameter_display(text: str) -> str:
    """A parameter type as list_symbols and refusals show it: as written
    without the parameter's name, one space between words, and none
    inside brackets or before a comma or bracket (`int b[]` is `int[]`,
    `int (*cb)(int)` is `int (*)(int)`)."""
    return re.sub(r"\s+(?=[\[\]),>])|(?<=[(<\[])\s+", "", " ".join(text.split()))


def split_top_level(text: str, separator: str, brackets: str = "()<>[]") -> list[str]:
    """`text` split at each `separator` that no pair of `brackets` (opening
    and closing characters in turn) holds."""
    opening, closing = brackets[0::2], brackets[1::2]
    parts, depth, start = [], 0, 0
    for i, char in enumerate(text):
        if char in opening:
            depth += 1
        elif char in closing:
            depth = max(depth - 1, 0)
        elif char == separator and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def split_cpp_name(name: str) -> tuple[str, ...]:
    """The names of a C++ qualified name: ('A', 'B', 'f') for `A::B::f`, a
    destructor or operator last as c_name writes it (('A', 'operator
    std::string') for `A::operator std::string`), and template arguments
    kept whole (('S<std::vector<U>>',) for a partial specialization)."""
    mark = re.search(r"(?:^|::)\s*(?=operator\b|~)", name)
    head, tail = (name[: mark.start()], name[mark.end() :]) if mark else (name, "")
    parts = split_top_level(head.replace("::", "\0"), "\0", "<>")
    names = [part.replace("\0", "::").strip() for part in parts if part.strip()]
    if tail.strip():
        names.append(c_name(tail))
    return tuple(names) or (name.strip(),)


def split_member_path(path: str) -> list[str]:
    """A JS/TS target's dotted path split into its parts, a dot inside a
    quoted or computed member name not splitting it: "E.'a.b'" is ['E',
    "'a.b'"] and 'E.[Symbol.iterator]' is ['E', '[Symbol.iterator]']."""
    parts, start, quote, depth, i = [], 0, None, 0, 0
    while i < len(path):
        char = path[i]
        if quote is not None:
            if char == "\\":
                i += 1
            elif char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth = max(depth - 1, 0)
        elif char == "." and depth == 0:
            parts.append(path[start:i])
            start = i + 1
        i += 1
    parts.append(path[start:])
    return parts


class Target(NamedTuple):
    """
    A source-file target as TreeSitterParser.parse_target reads it:
      - text: the target as written, for messages;
      - keyword: the `struct`, `union`, `enum` or C++ `class`, or TS `type`
        or `interface`, written before it (`struct stat`), or None;
      - parts: its dotted path, the last part without its parameter types;
      - names: the last part's names, split at C++ `::` (('A', 'g') for
        `A::g`);
      - params: the parameter types written in parentheses after it, as
        parameter_key writes them (c_parameter_key in C and C++; () for `f()`
        and C's `f(void)`), or None;
      - qualifiers: the C++ method qualifiers written after those (`const`,
        `&&`), or None.
    """

    text: str
    keyword: str | None
    parts: list[str]
    names: tuple[str, ...]
    params: tuple[str, ...] | None
    qualifiers: str | None


class Candidate(NamedTuple):
    """
    A declaration of a target's name in its scope, as
    TreeSitterParser.select weighs it (see TreeSitterParser.candidate):
      - node: the node find_node_by_name returns for it;
      - names: its qualified name (('A', 'g') for a C++ `int A::g()`);
      - keyword: the keyword of a C/C++ tag (`struct`) or of a TS type alias
        or interface (`type`, `interface`), else None;
      - unit: the typedef or declaration a C/C++ tag is the type of
        (`typedef struct N {...} N;`), else None;
      - function: whether it is a C, C++ or Java function, method or
        constructor;
      - params: a function's parameter types as parameter_display shows
        them, else None;
      - key: the same as parameter_key writes them (c_parameter_key in C
        and C++), else None;
      - qualifiers: a C++ method's qualifiers (`const`), else '';
      - rank: its TreeSitterParser.definition_rank.
    """

    node: Node
    names: tuple[str, ...]
    keyword: str | None
    unit: Node | None
    function: bool
    params: tuple[str, ...] | None
    key: tuple[str, ...] | None
    qualifiers: str
    rank: int


class ApplierError(Exception):
    """An edit or lookup the tools refuse, with a message for the caller.
    Defined here so that find_node_by_name can refuse an ambiguous target;
    ast_editor.applier, whose edits raise it, imports it from here."""


# The UTF-8 byte order mark, which TreeSitterParser takes off the text and
# the Applier writes back, and the marks of the encodings the tools cannot
# read (UTF-32 first, as its little-endian mark starts with UTF-16's).
UTF8_BOM = b"\xef\xbb\xbf"
_OTHER_BOMS = (
    (b"\xff\xfe\x00\x00", "UTF-32"),
    (b"\x00\x00\xfe\xff", "UTF-32"),
    (b"\xff\xfe", "UTF-16"),
    (b"\xfe\xff", "UTF-16"),
)


def _not_utf8_text(raw: bytes) -> str | None:
    """What a file that is not UTF-8 text is, said after its name ("is
    UTF-16 text (it starts with a UTF-16 byte order mark)"), when its bytes
    show it before they are decoded; None otherwise. UTF-8 text has no NUL
    bytes. UTF-16 and UTF-32 text without a byte order mark does: in each
    code unit of an ASCII character, at the same positions of the units,
    so that the bytes decode in one of those encodings. A file with NUL
    bytes laid out otherwise is not text."""
    encoding = next((name for mark, name in _OTHER_BOMS if raw.startswith(mark)), None)
    if encoding:
        return f"is {encoding} text (it starts with a {encoding} byte order mark)"
    nul = raw.find(b"\0")
    if nul == -1:
        return None
    candidates = [("UTF-32", "utf-32-le"), ("UTF-32", "utf-32-be")] if len(raw) % 4 == 0 else []
    # Most code units of source text are ASCII, so at least a quarter of
    # the UTF-16 units have a NUL, nearly all of them in one byte.
    odd, even = raw[1::2].count(0), raw[0::2].count(0)
    if len(raw) % 2 == 0 and max(odd, even) * 8 >= len(raw) and min(odd, even) * 4 <= max(odd, even):
        candidates.append(("UTF-16", "utf-16-le" if odd > even else "utf-16-be"))
    for name, codec in candidates:
        try:
            text = raw.decode(codec)
        except UnicodeDecodeError:
            continue
        if "\0" not in text:
            return f"looks like {name} text without a byte order mark"
    line = raw.count(b"\n", 0, nul) + 1
    return f"is not text (it has a NUL byte on line {line})"


def detect_newline(data: bytes) -> str:
    """Return the file's line-ending style: "\\r\\n" when most of its line
    breaks are CRLF, otherwise "\\n" (also for files with no line breaks)."""
    crlf = data.count(b"\r\n")
    return "\r\n" if crlf * 2 > data.count(b"\n") else "\n"


def first_syntax_error(root: Node) -> Node | None:
    """Return the first ERROR or MISSING node under root in document order,
    or None if the tree parsed cleanly. Iterative, so deeply nested trees
    cannot hit the recursion limit."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            return node
        if node.has_error:
            stack.extend(reversed(node.children))
    return None


# A JSON string, or the `+` of a number's exponent (6.02E+23).
_JSON_STRING_OR_EXPONENT_PLUS = re.compile(rb'"(?:[^"\\\n]|\\.)*"|(?<=[0-9][eE])\+(?=[0-9])')


def mask_json_exponents(data: bytes) -> bytes:
    """Return JSON source with each `+` that signs a number's exponent
    turned into `0`. tree-sitter-json has no `+` in its number rule, so it
    parses 6.02E+23 as the number 6.02 followed by an ERROR node, and an
    edit to that value would change only the 6.02. 6.02E023 is the same
    length, so a tree built from the masked copy has every node where it is
    in the real source (node text is always read from the real bytes), and
    its number nodes cover the whole token. Strings are left alone."""

    def keep_strings(match: re.Match) -> bytes:
        return b"0" if match.group(0) == b"+" else match.group(0)

    return _JSON_STRING_OR_EXPONENT_PLUS.sub(keep_strings, data)


# A backslash escape in a double-quoted key or path segment: \uXXXX,
# \UXXXXXXXX, \xHH or a single character.
_KEY_ESCAPE = re.compile(r"\\(?:u([0-9A-Fa-f]{4})|U([0-9A-Fa-f]{8})|x([0-9A-Fa-f]{2})|(.))", re.S)
_KEY_SIMPLE_ESCAPES = {
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "f": "\f",
    "r": "\r",
    "e": "\x1b",
    '"': '"',
    "\\": "\\",
    "/": "/",
}


def decode_quoted_key(text: str) -> str:
    """
    The name a quoted key or path segment spells. A double-quoted one is
    read as a JSON string or, failing that, with the escapes TOML basic
    strings add (\\UXXXXXXXX, \\xHH, \\e); an unknown escape stays as
    written. A single-quoted one (a TOML literal string) is the text
    between its quotes.
    """
    if text[:1] == "'":
        return text[1:-1]
    try:
        name = json.loads(text)
    except ValueError:
        name = None
    if isinstance(name, str):
        return name

    def unescape(match: re.Match) -> str:
        code = match.group(1) or match.group(2) or match.group(3)
        if code is None:
            return _KEY_SIMPLE_ESCAPES.get(match.group(4), match.group(0))
        try:
            return chr(int(code, 16))
        except ValueError:  # beyond U+10FFFF
            return match.group(0)

    return _KEY_ESCAPE.sub(unescape, text[1:-1])


def _closing_quote(text: str, start: int) -> int:
    """Index of the quote that closes the one at text[start], or -1. Inside
    double quotes a backslash escapes the next character; single quotes
    have no escapes."""
    quote = text[start]
    i = start + 1
    while i < len(text):
        if text[i] == "\\" and quote == '"':
            i += 2
            continue
        if text[i] == quote:
            return i
        i += 1
    return -1


def split_config_path(path: str, quotes: str = '"', strip: bool = False, raw: bool = False) -> list[str]:
    """
    The key names a JSON, YAML or TOML target path spells, one per segment.
    Dots separate the segments, and a segment wrapped in one of `quotes`
    (double quotes; for TOML also single quotes) is one name taken
    literally, dots included: '"editor.fontSize"' is the single key
    editor.fontSize and 'a."b.c".d' the keys a, b.c and d. Spaces and tabs
    around a quoted segment are ignored and its escapes resolved
    (decode_quoted_key). Any other segment is taken as written (with
    `strip`, without spaces and tabs around it), as is one whose closing
    quote is missing or followed by something other than a dot. With
    `raw`, quoted segments are returned as written, quotes included.
    """
    names: list[str] = []
    i = 0
    while True:
        j = i
        while j < len(path) and path[j] in " \t":
            j += 1
        if j < len(path) and path[j] in quotes:
            end = _closing_quote(path, j)
            k = end + 1
            while 0 < k < len(path) and path[k] in " \t":
                k += 1
            if end != -1 and (k == len(path) or path[k] == "."):
                segment = path[j : end + 1]
                names.append(segment if raw else decode_quoted_key(segment))
                if k == len(path):
                    return names
                i = k + 1
                continue
        dot = path.find(".", i)
        segment = path[i:] if dot == -1 else path[i:dot]
        names.append(segment.strip(" \t") if strip else segment)
        if dot == -1:
            return names
        i = dot + 1


def toml_key_names(text: str) -> list[str]:
    """The names a TOML key (`a."b.c"`, `'x y'`, `a . b`) or a TOML target
    path spells: the two share one syntax (split_config_path with double
    and single quotes, spaces around dots ignored)."""
    return split_config_path(text, "\"'", strip=True)


class TreeSitterParser:
    def __init__(self, filepath: str):
        self.filepath = filepath
        _, self.ext = os.path.splitext(filepath)

        try:
            if self.ext == ".py":
                self.language = Language(tree_sitter_python.language())
            elif self.ext in (".js", ".jsx", ".mjs", ".cjs"):
                self.language = Language(tree_sitter_javascript.language())
            elif self.ext == ".ts":
                self.language = Language(tree_sitter_typescript.language_typescript())
            elif self.ext == ".tsx":
                # The plain TypeScript grammar rejects JSX, which would make
                # the save-time syntax check refuse valid .tsx edits.
                self.language = Language(tree_sitter_typescript.language_tsx())
            elif self.ext == ".json":
                self.language = Language(tree_sitter_json.language())
            elif self.ext in (".yml", ".yaml"):
                self.language = Language(tree_sitter_yaml.language())
            elif self.ext == ".toml":
                self.language = Language(tree_sitter_toml.language())
            elif self.ext in C_EXTS:
                # Default .h files to C. Use .hpp/.hxx/.hh for C++ headers.
                self.language = Language(tree_sitter_c.language())
            elif self.ext in CPP_EXTS:
                self.language = Language(tree_sitter_cpp.language())
            elif self.ext in RUBY_EXTS:
                self.language = Language(tree_sitter_ruby.language())
            elif self.ext in GO_EXTS:
                self.language = Language(tree_sitter_go.language())
            elif self.ext == ".java":
                self.language = Language(tree_sitter_java.language())
            else:
                raise ValueError(f"Unsupported file extension: {self.ext}")
        except TypeError:
             # TODO: Older tree-sitter version fallback -- see note in parser source.
             if self.ext == ".py":
                self.language = Language(tree_sitter_python.language(), "python")
             elif self.ext in (".js", ".jsx"):
                self.language = Language(tree_sitter_javascript.language(), "javascript")
             elif self.ext in (".ts", ".tsx"):
                self.language = Language(tree_sitter_typescript.language_typescript(), "typescript")
             elif self.ext == ".json":
                self.language = Language(tree_sitter_json.language(), "json")
             elif self.ext in (".yml", ".yaml"):
                self.language = Language(tree_sitter_yaml.language(), "yaml")
             elif self.ext == ".toml":
                self.language = Language(tree_sitter_toml.language(), "toml")

        self.parser = Parser(self.language)

        with open(filepath, "rb") as f:
            raw = f.read()
        # A UTF-8 byte order mark is not text: tree-sitter would read it as
        # code, Python accepts it only as the very first character, and new
        # lines above the first one would move it into the file. It is taken
        # off here, so that node positions, lines and the syntax check start
        # after it, and the Applier writes it back first (`bom`).
        self.bom = raw.startswith(UTF8_BOM)
        if self.bom:
            raw = raw[len(UTF8_BOM) :]
        # Everything works on LF text internally (node positions, caller
        # snippets, inserted code); the Applier writes the file back with
        # its own `newline` style.
        self.newline = detect_newline(raw)
        # The line break of each line when the file mixes CRLF and LF ones
        # (None when it has one kind): the lines an edit leaves alone keep
        # theirs (Applier._write_text).
        crlf = raw.count(b"\r\n")
        self.line_breaks = None
        if crlf and crlf != raw.count(b"\n"):
            self.line_breaks = ["\r\n" if line.endswith(b"\r") else "\n" for line in raw.split(b"\n")[:-1]]
        self.source_bytes = raw.replace(b"\r\n", b"\n")
        # A last line without a line break is read as if it had one, so that
        # code added after it starts a line of its own; the Applier leaves
        # the break off again when it writes the file (`final_newline`). An
        # empty file has no last line, and gets one from an edit.
        self.final_newline = not raw or raw.endswith(b"\n")
        if not self.final_newline:
            self.source_bytes += b"\n"
        what = _not_utf8_text(raw)
        try:
            if what is None:
                self.source_code = self.source_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            what = f"is not UTF-8 text ({e})"
        if what is not None:
            raise ValueError(
                f"{filepath} {what}; ast-editor reads and writes UTF-8 files only. "
                "Convert it to UTF-8, or make this edit with your normal edit tool."
            )
        self.tree = self.parse(self.source_bytes)

    def parse(self, data: bytes):
        """Parse LF source with this file's grammar: the file itself, or an
        edited version of it for the save-time syntax check. JSON is parsed
        from a copy with its exponent signs masked (mask_json_exponents)."""
        if self.ext == ".json":
            data = mask_json_exponents(data)
        return self.parser.parse(data)

    def target_types(self) -> tuple[list[str], list[str], list[str]]:
        """The node types that a source-file target finds in this language,
        as (containers, functions, other symbols): the parts of a dotted
        target before the last are containers, the last is any of them.
        Empty lists for config files."""
        ext = self.ext
        if ext == ".py":
            return ["class_definition"], ["function_definition", "decorated_definition"], ["expression_statement"]
        if ext in (".ts", ".tsx"):
            return (
                ["class_declaration", "abstract_class_declaration", "interface_declaration", "internal_module", "module"],
                [
                    "function_declaration",
                    "generator_function_declaration",
                    "function_signature",
                    "method_definition",
                    "abstract_method_signature",
                    "arrow_function",
                    "variable_declaration",
                ],
                [
                    "variable_declaration",
                    "lexical_declaration",
                    "enum_declaration",
                    "type_alias_declaration",
                    "public_field_definition",
                ],
            )
        if ext in JS_EXTS:
            return (
                ["class_declaration"],
                [
                    "function_declaration",
                    "generator_function_declaration",
                    "method_definition",
                    "arrow_function",
                    "variable_declaration",
                    "lexical_declaration",
                ],
                ["variable_declaration", "lexical_declaration", "field_definition"],
            )
        if ext in C_EXTS:
            # A typedef of a struct holds its fields (`P.x` of `typedef
            # struct {...} P;`).
            return (
                ["struct_specifier", "union_specifier", "enum_specifier", "type_definition"],
                ["function_definition"],
                ["declaration", "field_declaration", "preproc_def", "preproc_function_def"],
            )
        if ext in CPP_EXTS:
            return (
                [
                    "class_specifier",
                    "struct_specifier",
                    "union_specifier",
                    "enum_specifier",
                    "namespace_definition",
                    "type_definition",
                ],
                ["function_definition"],
                ["declaration", "field_declaration", "alias_declaration", "preproc_def", "preproc_function_def"],
            )
        if ext in RUBY_EXTS:
            return ["class", "module"], ["method", "singleton_method"], ["assignment"]
        if ext in GO_EXTS:
            return ["type_spec"], ["function_declaration", "method_declaration"], ["const_spec", "var_spec", "type_alias"]
        if ext == ".java":
            return (
                ["class_declaration", "interface_declaration", "enum_declaration", "record_declaration"],
                ["method_declaration", "constructor_declaration"],
                ["field_declaration", "constant_declaration"],
            )
        return [], [], []

    def parse_target(self, target: str) -> Target:
        """
        A source-file target read into its parts (see Target). It may start
        with a keyword, which names a tag or type that shares its name with
        another symbol of its scope: `struct`, `union` or `enum` in C and
        C++, `class` in C++, `type` or `interface` in TS; with a dotted path
        the keyword goes in front of it all, and names the last part's kind
        (`type N.User`, `struct outer.inner`). The path is split at its
        dots, in C, C++ and Java at those outside parentheses
        (`A.m(java.util.List)`), in JS and TS at those outside quotes and
        brackets (`E.'a.b'`, `E.[Symbol.iterator]`, split_member_path). In C, C++ and Java the last part may end
        with parameter types in parentheses, `m(int, String)` (`m()` for
        none, which C's `f(void)` also is), and in C++ with the method
        qualifiers after them (`get(int) const`); the parentheses of
        `operator()` are part of its name, so `A.operator()(int)` gives it
        parameter types (c_parameter_key in C and C++). In C and C++ the
        last part's name may be qualified (`A::B::f`, `A::~A`).
        """
        text = target
        c_family = self.ext in C_EXTS + CPP_EXTS
        keywords: tuple[str, ...] = ()
        if c_family:
            keywords = ("struct", "union", "enum") + (("class",) if self.ext in CPP_EXTS else ())
        elif self.ext in (".ts", ".tsx"):
            keywords = ("type", "interface")
        keyword = None
        head = target.split(None, 1)
        if len(head) == 2 and head[0] in keywords:
            keyword, target = head[0], head[1].strip()
        typed = c_family or self.ext == ".java"
        if typed:
            parts = split_top_level(target, ".", "()")
        elif self.ext in JS_EXTS:
            parts = split_member_path(target)
        else:
            parts = target.split(".")
        last, params, qualifiers = parts[-1], None, None
        if typed:
            rest, written = last.rstrip(), None
            mark = _QUALIFIERS_AT_END.search(rest) if self.ext in CPP_EXTS else None
            if mark is not None:
                written = " ".join(re.findall(r"const|volatile|&&|&", mark.group(1)))
                rest = rest[: mark.start() + 1]
            opening = self._opening_paren(rest)
            if opening is not None and not (c_family and re.search(r"\boperator\s*$", rest[:opening])):
                key = c_parameter_key if c_family else parameter_key
                types = [key(t) for t in split_top_level(rest[opening + 1 : -1], ",")]
                if types == [""] or (c_family and types == ["void"]):
                    types = []
                last, params, qualifiers = rest[:opening].rstrip(), tuple(types), written
        parts[-1] = last
        names = split_cpp_name(last) if c_family else (last,)
        return Target(text, keyword, parts, names, params, qualifiers)

    @staticmethod
    def _opening_paren(text: str) -> int | None:
        """The index of the `(` that the `)` ending `text` closes, or None."""
        if not text.endswith(")"):
            return None
        depth = 0
        for i in range(len(text) - 1, -1, -1):
            if text[i] == ")":
                depth += 1
            elif text[i] == "(":
                depth -= 1
                if depth == 0:
                    return i
        return None

    def target_leaf(self, target: str) -> str:
        """The name that a source-file target's last part declares, without
        its keyword, parameter types and C++ qualification: `m` of
        `A.m(int)`, `stat` of `struct stat`, `g` of `A::g`."""
        return self.parse_target(target).names[-1]

    def find_node_by_name(self, target_name: str) -> Node | None:
        """
        Locates an AST node by its semantic name.
        Supports dotted paths:
          - Class.method: descend into class body.
          - Go: Struct.Method (via receiver), or Var.Field for func_literals
            stored in composite-literal fields (`cmd.RunE`).
          - JS/TS: Var.Field for arrow_function / function_expression values
            of object-literal properties (`app.handler`).
        JS/TS exported declarations are found by their own names (the
        declaration inside the export statement is returned); an anonymous
        `export default function/class` is named `default`. Generator
        functions, TS abstract classes and their abstract methods, enums,
        type aliases, namespaces and functions declared without a body
        (`declare function f(): void;`) are found like other declarations,
        a `const`/`let`/`var` by the name it declares (the whole
        declaration is returned; js_bound_function gets the function bound
        to it), and a class field by its name (`A.x`, `A.#y`).
        C/C++ variables, fields, typedefs, `using` aliases, macros, function
        prototypes and methods declared in their class are found as well,
        by every name a declaration declares (`b` of `int a, *b;`, the whole
        declaration being returned), destructors as `~A` and operators as
        c_name writes them (`operator==`, `operator bool`), and a C++
        definition outside its class by its qualified name (`A::g`,
        `A::B::f`) or the end of it (`g`, `B::f`); so are Java fields and Go
        type aliases and every name of a Go `var`/`const` spec.
        The last part of a C, C++ or Java target may name a function by its
        parameter types (`A.m(int, String)`, `A::A()`, C++ `A.get(int)
        const`), and a C/C++ or TS target may start with a keyword that
        names a tag or type sharing its name with another symbol (`struct
        stat`, `type User`), see parse_target. Of the declarations of the
        name in its scope, select picks the target: a definition rather
        than its forward declaration, prototype, `extern` declaration, TS
        overload signature or Python @overload stub, and refuses a name
        that C++ or Java overloads with an ApplierError naming each
        overload's target.
        In JSON, YAML and TOML files the target is a key path followed from
        the top level, a segment in double quotes (in TOML also single
        quotes) being one key with any dots in it (split_config_path), and
        the key's value node is returned (see _search_json_dotted,
        find_yaml_pair and toml_pair); a YAML key with no value has none.
        """
        if self.ext == ".json":
            return self._search_json_dotted(self.tree.root_node, target_name)
        if self.ext in (".yml", ".yaml"):
            return self._search_yaml_dotted(self.tree.root_node, target_name)
        if self.ext == ".toml":
            return self._search_toml_dotted(self.tree.root_node, target_name)
        class_types, func_types, var_types = self.target_types()
        if not class_types:
            return None
        target = self.parse_target(target_name)
        if target.keyword is None and target.params is None and len(target.parts) == 2:
            first, second = target.parts
            if self.ext in JS_EXTS:
                # A closure in an object literal (`app.handler`).
                closure = self._find_js_closure_by_var(first, second)
                if closure is not None:
                    return closure
            elif self.ext in GO_EXTS:
                # A receiver-based method (Cache.Get), or a func_literal
                # stored in a composite-literal field (stdioCmd.RunE).
                found = self._find_go_method_by_receiver(first, second)
                if found is None:
                    found = self._find_go_closure_in_var(first, second)
                if found is not None:
                    return found
        return self._search_tree_dotted(
            self.tree.root_node, target, class_types, class_types + func_types + var_types
        )

    def find_container(self, target_name: str) -> Node | None:
        """
        The class, struct, interface, namespace or module that add_method and
        add_field add to for `target_name`, or None: the target found among
        the containers of its scope only (the first of target_types), so
        that a name a struct shares with a function or variable (`struct
        stat` and `int stat(...)`, a TS interface and a function of its
        name) is the struct. A C/C++ typedef of a struct declared apart
        (`typedef struct Node Node;`) gives that struct (`struct Node`).
        """
        class_types = self.target_types()[0]
        if not class_types:
            return None
        root = self.tree.root_node
        target = self.parse_target(target_name)
        node = self._search_tree_dotted(root, target, class_types, class_types)
        spec = node.child_by_field_name("type") if node is not None and node.type == "type_definition" else None
        tag = spec.child_by_field_name("name") if spec is not None and spec.type in _C_TAG_KEYWORDS else None
        if tag is not None and spec.child_by_field_name("body") is None:
            name = self.node_text(tag)
            keyword = _C_TAG_KEYWORDS[spec.type]
            tagged = target._replace(keyword=keyword, parts=target.parts[:-1] + [name], names=(name,))
            node = self._search_tree_dotted(root, tagged, class_types, class_types) or node
        return node

    def _search_tree_dotted(
        self,
        root: Node,
        target: Target,
        class_types: list[str],
        types: list[str],
    ) -> Node | None:
        """
        The node for the dotted `target` under `root`: each part but the last
        a container (class_types) found in the ones before it, the last the
        symbol of any of the `types` that select picks among the declarations
        of its name in their scope (candidates). A C++ or TS namespace opened
        more than once in its scope, and a TS namespace merged with the class,
        function or enum of its name, are one container that holds the members
        of all of their blocks (merged_containers), a declaration in one of
        the blocks being found before one nested deeper in another (a
        member of a class there). Of several containers of
        one name (a struct and a typedef of its name, a Ruby class reopened),
        the first of the lowest definition_rank is searched first, then the
        others, so that the members of each are found.
        """
        return self._search_from([root], target, 0, class_types, types)

    def _search_from(
        self, containers: list[Node], target: Target, i: int, class_types: list[str], types: list[str]
    ) -> Node | None:
        """_search_tree_dotted from part i of `target` on, in `containers`."""
        if i == len(target.parts) - 1:
            found = [c for container in containers for c in self.candidates(container, target.names[-1], types)]
            if len(containers) > 1:
                # The blocks of a namespace opened again: a declaration in
                # one of them, rather than one nested deeper in another.
                scopes = containers + [block.child_by_field_name("body") for block in containers]
                own = [c for c in found if self._scope(c.node) in scopes]
                found = own or found
            return self.select(found, target)
        part = target.parts[i]
        found = [c for container in containers for c in self.candidates(container, part, class_types)]
        searched: list[Node] = []
        for candidate in sorted(found, key=lambda c: (c.rank, c.node.start_byte)):
            if candidate.node in searched:
                continue
            blocks = self.merged_containers(candidate.node, part, class_types)
            searched.extend(blocks)
            node = self._search_from(blocks, target, i + 1, class_types, types)
            if node is not None:
                return node
        return None

    def merged_containers(self, found: Node, name: str, class_types: list[str]) -> list[Node]:
        """
        `found`, the container that one part of a dotted target names, with
        the other declarations of `name` in its scope that are one container
        with it, in document order, when one of them is a namespace: the
        blocks of a C++ or TS namespace opened again (`namespace n {...}`
        twice), and in TS a namespace merged with the class, function or enum
        of its name. Else [found].
        """
        if self.ext not in CPP_EXTS + (".ts", ".tsx"):
            return [found]
        scope = self._scope(found)
        if scope is None:
            return [found]
        merged, stack = [], list(scope.named_children)
        while stack:
            curr = stack.pop()
            if curr.type in _SCOPE_WRAPPERS + ("expression_statement",) or (
                curr.type == "declaration_list" and curr.parent.type == "linkage_specification"
            ):
                stack.extend(curr.named_children)
            elif (
                curr.type in tuple(class_types) + ("function_declaration", "enum_declaration")
                and self._scope(curr) == scope
                and self.declared_name(curr, name) is not None
            ):
                merged.append(curr)
        if found not in merged or not any(node.type in NAMESPACES for node in merged):
            return [found]
        return sorted(merged, key=lambda node: node.start_byte)

    def _extract_c_function_name(self, func_node: Node) -> Node | None:
        """
        For C/C++ function_definition nodes, the name is nested inside the declarator chain:
        function_definition -> declarator (function_declarator) -> declarator (identifier/field_identifier/qualified_identifier)
        Handles pointer/reference declarators, qualified names (Class::method)
        and C++ explicit specializations (`template <> int id<int>(int)`),
        which are named for the template they specialize (`id`). See
        c_declarator_name.
        """
        return self.c_declarator_name(func_node.child_by_field_name("declarator"))

    def c_declarator_name(self, declarator: Node | None) -> Node | None:
        """
        The node that names what a C/C++ declarator declares (one of
        _C_NAMES), found through the declarators around it (`*p`, `&r`,
        `a[3]`, `f(int)`, `(*fp)(int)`, `x = 1`), a qualified name (the `f`
        of `A::f`, the `~A` of `A::~A`) and a template's arguments (the `id`
        of `id<int>`), or None.
        """
        while declarator is not None:
            if declarator.type in _C_NAMES:
                return declarator
            if declarator.type in ("qualified_identifier", "template_function"):
                declarator = declarator.child_by_field_name("name")
                continue
            inner = declarator.child_by_field_name("declarator")
            if inner is None and declarator.type.endswith("declarator"):
                # `&r`, `(*fp)` and `x [[maybe_unused]]` hold theirs unnamed.
                inner = next(
                    (
                        c
                        for c in declarator.named_children
                        if c.type.endswith("declarator")
                        or c.type in _C_NAMES + ("qualified_identifier", "template_function")
                    ),
                    None,
                )
            declarator = inner
        return None

    def c_declared_names(self, node: Node) -> list[Node]:
        """
        The nodes naming what a C/C++ node declares, in order: a function
        definition's name, a class, struct, union, enum or namespace name
        (a type without a body only when it stands alone, `struct S;`, not
        where it is just used, `struct S *p;`), a `using` alias or macro
        name, and the names of the declarators of a declaration, field or
        typedef (`a` and `b` of `int a, *b;`, `x` and `y` of a C++ `auto [x,
        y] = p;`).
        """
        if node.type == "function_definition":
            name = self._extract_c_function_name(node)
            return [name] if name is not None else []
        if node.type in C_TYPE_SPECIFIERS + ("namespace_definition", "alias_declaration", "preproc_def", "preproc_function_def"):
            name = node.child_by_field_name("name")
            if name is None or (node.type in C_TYPE_SPECIFIERS and not self.c_declares_type(node)):
                return []
            return [name]
        if node.type in ("declaration", "field_declaration", "type_definition"):
            names = []
            for declarator in node.children_by_field_name("declarator"):
                binding = declarator
                while binding is not None and binding.type in ("init_declarator", "reference_declarator"):
                    binding = binding.child_by_field_name("declarator") or next(
                        (c for c in binding.named_children if c.type.endswith("declarator")), None
                    )
                if binding is not None and binding.type == "structured_binding_declarator":
                    # `auto [x, y] = p;`
                    names.extend(c for c in binding.named_children if c.type == "identifier")
                    continue
                name = self.c_declarator_name(declarator)
                if name is not None:
                    names.append(name)
            return names
        return []

    @staticmethod
    def c_declares_type(node: Node) -> bool:
        """Whether a C/C++ class, struct, union or enum node declares its
        type: it has a body, or stands alone as a forward declaration
        (`struct S;`, `class B;` in a class, `template <class T> class X;`).
        Without a body, the type of a declaration, parameter or cast only
        refers to it (`struct S *p;`)."""
        if node.child_by_field_name("body") is not None:
            return True
        parent = node.parent
        if parent is None or parent.child_by_field_name("declarator") is not None:
            return False
        return parent.type in (
            "translation_unit",
            "declaration_list",
            "field_declaration_list",
            "field_declaration",
            "declaration",
            "template_declaration",
            "linkage_specification",
            "preproc_if",
            "preproc_ifdef",
            "preproc_else",
            "preproc_elif",
            "preproc_elifdef",
        )

    def c_declares_function(self, name: Node) -> bool:
        """Whether the declarator that `name` names (c_declarator_name)
        declares a function: a prototype `int f(int);`, a method declared in
        its class, a conversion operator. A pointer to a function (`int
        (*fp)(int);`) is a variable."""
        if name.type == "operator_cast":
            return True
        parent = name.parent
        while parent is not None and parent.type in ("qualified_identifier", "template_function"):
            parent = parent.parent
        return parent is not None and parent.type == "function_declarator"

    def symbol_name(self, name: Node) -> str:
        """The name a name node gives its symbol as a target: its text, a
        C++ destructor or operator name written as c_name writes it, and a
        conversion operator without its parameters (`operator bool`)."""
        if self.ext not in C_EXTS + CPP_EXTS or name.type not in ("destructor_name", "operator_name", "operator_cast"):
            return self.node_text(name)
        end = name.end_byte
        if name.type == "operator_cast":
            stack = [name]
            while stack:
                node = stack.pop()
                if node.type == "parameter_list":
                    end = node.start_byte
                    break
                stack.extend(reversed(node.named_children))
        return c_name(self.source_bytes[name.start_byte : end].decode("utf-8"))

    def declared_names(self, node: Node) -> list[Node]:
        """
        The nodes naming what `node`, a node of a type that targets find,
        declares, in order: its name field (a JS class field's `property`);
        in C/C++ the names c_declared_names finds; a Python or Ruby
        assignment's left side;
        every name of a Go `var`/`const` spec (`a, b = 1, 2`); and the
        declarators of a JS/TS `const`/`let`/`var` or a Java field (`int x,
        y;`).
        """
        if self.ext in C_EXTS + CPP_EXTS:
            return self.c_declared_names(node)
        if node.type in ("const_spec", "var_spec") and self.ext in GO_EXTS:
            return [c for c in node.children_by_field_name("name") if c.type == "identifier"]
        # A JS class field names itself in its `property`, a TS one in `name`.
        name = node.child_by_field_name("property" if node.type == "field_definition" else "name")
        if name is not None:
            return [name]
        if node.type == "expression_statement":
            assignment = node.named_children[0] if node.named_children else None
            if assignment is not None and assignment.type == "assignment":
                return assignment.named_children[:1]
            return []
        if node.type == "assignment" and self.ext in RUBY_EXTS:
            first = node.named_children[0] if node.named_children else None
            return [first] if first is not None and first.type in ("constant", "identifier") else []
        if node.type in ("variable_declaration", "lexical_declaration", "field_declaration", "constant_declaration"):
            names = (
                c.child_by_field_name("name")
                for c in node.named_children
                if c.type == "variable_declarator"
            )
            return [name for name in names if name is not None]
        return []

    def declared_name(self, node: Node, name: str) -> Node | None:
        """The node of declared_names(node) that names `name` (a C/C++
        destructor or operator name compared as c_name writes it), or
        None. A C++ class or namespace named with its scope (`struct A::B
        {...}`, `namespace a::b {}`) names both its whole name and its last
        one (`A::B` and `B`)."""
        if self.ext in C_EXTS + CPP_EXTS and name.lstrip().startswith(("~", "operator")):
            name = c_name(name)
        for n in self.declared_names(node):
            text = self.symbol_name(n)
            if text == name or (n.type in _QUALIFIED_NAMES and split_cpp_name(text)[-1] == name):
                return n
        return None

    def definition_rank(self, node: Node, name: Node) -> int:
        """
        How `node`, found for the name node `name`, ranks among the
        declarations of one symbol in one scope, the lowest being the target
        (select): 0 for a definition with a body (a C/C++ function, class,
        struct, union, enum or namespace) and for any symbol outside C, C++,
        TS and Python; 1 for another definition (a C/C++ variable, field,
        typedef, `using` alias or macro, which a struct of its name is
        searched before as a container, and a TS namespace, which merges
        with the class, function or enum of its name); 2 for a declaration
        that only announces a definition: a C/C++ forward declaration
        (`struct S;`), a prototype or a method declared in its class, an
        `extern` variable without a value, a TS overload signature or
        function declared without a body (`declare function f(): void;`)
        and a Python @overload stub (python_overload).
        """
        if self.ext in (".ts", ".tsx"):
            if node.type in NAMESPACES:
                return 1
            return 2 if node.type == "function_signature" else 0
        if self.ext == ".py":
            return 2 if self.python_overload(node) else 0
        if self.ext not in C_EXTS + CPP_EXTS:
            return 0
        if node.type in C_TYPE_SPECIFIERS:
            return 0 if node.child_by_field_name("body") is not None else 2
        if node.type in ("function_definition", "namespace_definition"):
            return 0
        if node.type in ("declaration", "field_declaration"):
            if self.c_declares_function(name):
                return 2
            extern = any(c.type == "storage_class_specifier" and self.node_text(c) == "extern" for c in node.children)
            valued = name
            while valued is not None and valued != node and valued.type != "init_declarator":
                valued = valued.parent
            if extern and valued is not None and valued.type != "init_declarator":
                return 2
        return 1

    @staticmethod
    def _scope(node: Node) -> Node | None:
        """The node whose scope `node` declares its name in: its parent,
        past the wrappers in _SCOPE_WRAPPERS, the block of an `extern "C"
        { ... }` and the expression statement the grammar makes of a TS
        `namespace N { ... }`."""
        parent = node.parent
        while (
            parent is not None
            and parent.parent is not None
            and (
                parent.type in _SCOPE_WRAPPERS
                or (parent.type == "declaration_list" and parent.parent.type == "linkage_specification")
                or (parent.type == "expression_statement" and node.type in NAMESPACES)
            )
        ):
            parent = parent.parent
        return parent

    @staticmethod
    def _c_local(node: Node) -> bool:
        """Whether a C/C++ declaration, field, typedef or `using` alias is
        local to a function: inside a body (`int i;`, `for (int i = 0;
        ...)`) before any class or namespace (the fields of a struct defined
        in a function are its own). Macros, functions and types are never
        local."""
        if node.type not in ("declaration", "field_declaration", "type_definition", "alias_declaration"):
            return False
        parent = node.parent
        while parent is not None:
            if parent.type == "compound_statement":
                return True
            if parent.type in ("field_declaration_list", "declaration_list", "translation_unit"):
                return False
            parent = parent.parent
        return False

    def candidates(self, node: Node, name: str, valid_types: list[str]) -> list[Candidate]:
        """
        The declarations of `name` of the valid_types below `node`, in one
        scope: that of the first one found breadth first, its other
        declarations being found wherever a preprocessor conditional or TS
        `namespace` statement puts them in it (scope_candidates). Only below
        `node`: the container must not match itself, or a Java constructor
        target such as `LRUCache.LRUCache` would find the class. The
        variables and types a C/C++ function declares are its own, no
        targets (_c_local). An anonymous `export default function/class` is
        the one declaration of `default`.
        """
        queue = list(node.named_children)
        while queue:
            curr = queue.pop(0)
            if name == "default" and curr.type == "export_statement":
                value = self.anonymous_default_export(curr)
                if value is not None and DEFAULT_EXPORT_KINDS[value.type] in valid_types:
                    return [Candidate(value, ("default",), None, None, False, None, None, "", 0)]
            for match in self._declarations_in(curr, valid_types, name):
                found = self.scope_candidates([self._scope(match[0])], name, valid_types)
                if not any(c.node == match[0] for c in found):
                    found.append(self.candidate(*match))
                return found
            if curr.type == "decorated_definition":
                # A decorated Python function is found as its decorated_definition.
                curr = next((c for c in curr.named_children if c.type == "function_definition"), curr)
            queue.extend(curr.named_children)
        return []

    def _declarations_in(self, node: Node, valid_types: list[str], name: str | None) -> list[tuple[Node, Node]]:
        """(node, name node) for each name that `node`, of one of the
        valid_types, declares (only `name`, when it is given), a decorated
        Python function by its function's name, so that the edits take its
        decorators too; [] for any other node and for a C/C++ function's own
        variables and types (_c_local)."""
        if node.type not in valid_types:
            return []
        inner = node
        if node.type == "decorated_definition":
            inner = next((c for c in node.named_children if c.type == "function_definition"), node)
        if self.ext in C_EXTS + CPP_EXTS and self._c_local(inner):
            return []
        if name is None:
            return [(node, declared) for declared in self.declared_names(inner)]
        declared = self.declared_name(inner, name)
        return [(node, declared)] if declared is not None else []

    def scope_candidates(self, scopes: list[Node], name: str, valid_types: list[str]) -> list[Candidate]:
        """The declarations of `name` of the valid_types that `scopes`
        declare it in, in document order (scope_declarations), however the
        name is spaced (`operator ==`)."""
        groups = self.scope_declarations(scopes, valid_types, name).values()
        return sorted((c for group in groups for c in group), key=lambda c: c.node.start_byte)

    def scope_declarations(
        self, scopes: list[Node], valid_types: list[str], name: str | None = None
    ) -> dict[str, list[Candidate]]:
        """
        The declarations of the valid_types that `scopes` declare names in
        (_scope), by the name they declare (symbol_name), each list in
        document order; only those of `name` when it is given. They are the
        scopes' children and what the wrappers among them hold
        (_SCOPE_WRAPPERS, the block of an `extern "C" { ... }`, a TS
        `namespace` statement). One pass gives list_symbols the
        declarations of every name of a container.
        """
        found: dict[str, list[Candidate]] = {}
        for scope in scopes:
            queue = list(scope.named_children)
            while queue:
                curr = queue.pop(0)
                for node, declared in self._declarations_in(curr, valid_types, name):
                    if self._scope(node) == scope:
                        found.setdefault(self.symbol_name(declared), []).append(self.candidate(node, declared))
                if curr.type in _SCOPE_WRAPPERS + ("expression_statement",) or (
                    curr.type == "declaration_list" and curr.parent.type == "linkage_specification"
                ):
                    queue.extend(curr.named_children)
        for group in found.values():
            group.sort(key=lambda c: c.node.start_byte)
        return found

    def candidate(self, node: Node, name: Node) -> Candidate:
        """`node`, a declaration found for its name node `name`, as select
        weighs it (see Candidate)."""
        c_family = self.ext in C_EXTS + CPP_EXTS
        keyword = unit = None
        if c_family:
            keyword = _C_TAG_KEYWORDS.get(node.type)
            parent = node.parent
            if (
                keyword is not None
                and parent.type in ("type_definition", "declaration", "field_declaration")
                and parent.child_by_field_name("type") == node
            ):
                unit = parent
        elif self.ext in (".ts", ".tsx"):
            keyword = _TS_TYPE_KEYWORDS.get(node.type)
        function, params, key, qualifiers = False, None, None, ""
        if c_family and (
            node.type == "function_definition"
            or (node.type in ("declaration", "field_declaration") and self.c_declares_function(name))
        ):
            function = True
            params, qualifiers = self._c_parameters(name)
        elif self.ext == ".java" and node.type in ("method_declaration", "constructor_declaration"):
            function = True
            params = self._java_parameters(node.child_by_field_name("parameters"))
        if params is not None:
            key = tuple((c_parameter_key if c_family else parameter_key)(text) for text in params)
        return Candidate(
            node, self.qualified_name(name), keyword, unit, function, params, key, qualifiers, self.definition_rank(node, name)
        )

    def qualified_name(self, name: Node) -> tuple[str, ...]:
        """The name a name node gives its symbol, as a tuple: in C++ after the
        scopes it is qualified with (('A', 'B', 'f') for `int A::B::f()`, a
        template's without its arguments, ('Box', 'get') for `Box<T>::get`,
        and ('A', 'B') for `struct A::B {...}` and `namespace A::B {}`), else
        (symbol_name(name),)."""
        if self.ext in CPP_EXTS and name.type in _QUALIFIED_NAMES:
            return split_cpp_name(self.symbol_name(name))
        names = [self.symbol_name(name)]
        if self.ext in CPP_EXTS:
            child, parent = name, name.parent
            while parent is not None and parent.type in ("qualified_identifier", "template_function"):
                scope = parent.child_by_field_name("scope")
                if parent.type == "qualified_identifier" and scope is not None and scope != child:
                    if scope.type == "template_type":
                        scope = scope.child_by_field_name("name") or scope
                    names.insert(0, self.node_text(scope))
                child, parent = parent, parent.parent
        return tuple(names)

    def _c_parameters(self, name: Node) -> tuple[tuple[str, ...], str]:
        """The parameter types of the C/C++ function that the name node `name`
        names, as parameter_display shows them without names, defaults and
        attributes (_c_parameter_names; a lone `void` being none, `...`
        itself), and its method qualifiers (`const`, `&&`) or ''."""
        declarator = name.parent
        while declarator is not None and declarator.type in ("qualified_identifier", "template_function"):
            declarator = declarator.parent
        if name.type == "operator_cast":
            # `operator bool() const` holds its own parameters.
            declarator = next((c for c in name.named_children if c.type == "abstract_function_declarator"), None)
        params = declarator.child_by_field_name("parameters") if declarator is not None else None
        if params is None:
            return (), ""
        shown = []
        for child in params.children:
            if child.type in ("(", ")", ",") or "comment" in child.type:
                continue
            if child.type in ("...", "variadic_parameter"):
                shown.append("...")
                continue
            end = child.end_byte
            if child.type == "optional_parameter_declaration":
                # Without its default value (`int n = 1`).
                end = next((c.start_byte for c in child.children if c.type == "="), end)
            shown.append(parameter_display(self._text_without(child.start_byte, end, self._c_parameter_names(child))))
        if shown == ["void"]:
            shown = []
        qualifiers = " ".join(self.node_text(c) for c in declarator.children if c.type in _CPP_METHOD_QUALIFIERS)
        return tuple(shown), qualifiers

    def _c_parameter_names(self, param: Node) -> list[Node]:
        """The nodes that a C/C++ parameter's type is shown without
        (_c_parameters): its name, its attributes (`[[maybe_unused]]`,
        `__attribute__((unused))`) and those of the parameters of a function
        type it has (`x` of `int (*cb)(int x)`)."""
        found = [self.c_declarator_name(param.child_by_field_name("declarator"))]
        stack = [param]
        while stack:
            node = stack.pop()
            for child in node.named_children:
                if child.type in ("attribute_declaration", "attribute_specifier"):
                    found.append(child)
                    continue
                if node.type == "parameter_list" and child.type in (
                    "parameter_declaration",
                    "optional_parameter_declaration",
                ):
                    found.append(self.c_declarator_name(child.child_by_field_name("declarator")))
                stack.append(child)
        return [n for n in found if n is not None]

    def _java_parameters(self, params: Node | None) -> tuple[str, ...]:
        """The parameter types of a Java method or constructor whose
        formal_parameters are `params`, as parameter_display shows them:
        without modifiers and annotations (`final`, `@NonNull`), a varargs
        one as `String...`, an array as `int[]` either way it is written."""
        shown = []
        for child in params.named_children if params is not None else []:
            if child.type not in ("formal_parameter", "spread_parameter"):
                continue
            start = next((c.start_byte for c in child.named_children if c.type != "modifiers"), child.start_byte)
            own = child.child_by_field_name("name")
            if child.type == "spread_parameter":
                declarator = next((c for c in child.named_children if c.type == "variable_declarator"), None)
                own = declarator.child_by_field_name("name") if declarator is not None else None
            shown.append(parameter_display(self._text_without(start, child.end_byte, own)))
        return tuple(shown)

    def _text_without(self, start: int, end: int, nodes) -> str:
        """The source from byte start to end, with a space for each of
        `nodes` (a node or a list of them, such as a parameter's name and
        attributes) that lies inside."""
        src = self.source_bytes
        if not isinstance(nodes, list):
            nodes = [nodes]
        parts, pos = [], start
        for node in sorted((n for n in nodes if n is not None), key=lambda n: n.start_byte):
            if node.start_byte < pos or node.end_byte > end:
                continue
            parts.append(src[pos : node.start_byte] + b" ")
            pos = node.end_byte
        parts.append(src[pos:end])
        return b"".join(parts).decode("utf-8")

    def select(self, found: list[Candidate], target: Target) -> Node | None:
        """
        The node that the last part of `target` names among `found`, the
        declarations of its name in one scope (candidates), or None:
          - Its names: a declaration of that qualified name, or in C++, when
            there is none, one whose qualified name ends with them (`f` and
            `B::f` find `int A::B::f()`).
          - A keyword (`struct stat`, `type User`) names a C/C++ tag or TS type
            alias or interface written with it. Without one, a tag or TS type
            that shares its name with another kind of declaration (a function,
            variable or typedef, a TS value) is not named, unless that is the
            typedef or declaration it is the type of (`typedef struct N {...}
            N;` is one symbol).
          - In C, C++ and Java, parameter types (`m(int)`) name a function with
            those types, and C++ qualifiers (`get(int) const`) one with those;
            without qualifiers, of overloads that differ in them only, the one
            with none. Without parameter types, a name that functions share
            with a variable, field, macro or type names the latter (Java's
            `int x;` and `int x()`). A keyword target has no parameter types
            (`struct A(int)` names nothing).
          - In JS and TS, a name that a function or method shares with data
            names the function (`static run = false;` and `run() {}`, `var f`
            and `function f`).
        In C++ and Java, functions whose parameter types or qualifiers differ
        are several symbols, as are symbols of different qualified names (`A::g`
        and `B::g` for `g`), and a target that names several is refused,
        naming each by the target that finds it (_refuse_several). Of the
        declarations of one symbol the target is the first of the lowest
        definition_rank: a definition rather than its forward declaration,
        prototype, overload signatures or @overload stubs, then one in fewer
        C/C++ preprocessor conditionals (_conditional_depth: a definition
        outside them rather than one in `#if 0`), and of alternatives in
        `#ifdef` branches the first.
        """
        names = target.names
        match = [c for c in found if c.names == names]
        if not match and self.ext in CPP_EXTS:
            match = [c for c in found if len(c.names) > len(names) and c.names[-len(names) :] == names]
        if target.keyword is not None:
            match = [c for c in match if c.keyword == target.keyword and target.params is None]
        else:
            others = [c for c in match if c.keyword is None]
            if others:
                match = [c for c in match if c.keyword is None or any(c.unit == o.node for o in others)]
            if target.params is not None:
                match = [c for c in match if c.function and c.key == target.params]
                if target.qualifiers is not None:
                    match = [c for c in match if c.qualifiers == target.qualifiers]
                elif any(not c.qualifiers for c in match):
                    match = [c for c in match if not c.qualifiers]
            elif self.ext in C_EXTS + CPP_EXTS + (".java",) and any(not c.function for c in match):
                match = [c for c in match if not c.function]
            elif self.ext in JS_EXTS and any(c.node.type in _JS_FUNCTIONS for c in match):
                match = [c for c in match if c.node.type in _JS_FUNCTIONS]
        symbols: dict[tuple, list[Candidate]] = {}
        for c in match:
            overloads = c.function and self.ext in CPP_EXTS + (".java",)
            symbols.setdefault((c.names, c.key, c.qualifiers) if overloads else (c.names,), []).append(c)
        firsts = [
            min(group, key=lambda c: (c.rank, self._conditional_depth(c.node), c.node.start_byte))
            for group in symbols.values()
        ]
        if len(firsts) > 1:
            raise self._refuse_several(target, firsts)
        return firsts[0].node if firsts else None

    @staticmethod
    def _conditional_depth(node: Node) -> int:
        """How many C/C++ preprocessor conditionals (`#if`, `#ifdef`, an
        include guard too) hold `node`; an `#else` or `#elif` branch is part
        of its `#if`."""
        depth, parent = 0, node.parent
        while parent is not None:
            depth += parent.type in ("preproc_if", "preproc_ifdef")
            parent = parent.parent
        return depth

    def _refuse_several(self, target: Target, symbols: list[Candidate]) -> ApplierError:
        """The refusal of `target`, which names each of `symbols` (the first
        declaration of each, see select): each by the target that finds it,
        its qualified name, with its parameter types when another of them has
        that name and its qualifiers when another has those types too, and
        by its line."""
        prefix = "".join(part + "." for part in target.parts[:-1])
        named = []
        for c in sorted(symbols, key=lambda c: c.node.start_byte):
            label = "::".join(c.names)
            same = [o for o in symbols if o is not c and o.names == c.names]
            if same:
                label += f"({', '.join(c.params or ())})"
                if c.qualifiers and any(o.key == c.key for o in same):
                    label += " " + c.qualifiers
            named.append(f"{prefix}{label} (line {self.listed_line(c.node)})")
        if all(c.names == symbols[0].names for c in symbols):
            hint = "add the parameter types" if target.params is None else "add the method qualifiers"
            return ApplierError(f"'{target.text}' is overloaded: {', '.join(named)}; {hint}.")
        return ApplierError(f"'{target.text}' is ambiguous: {', '.join(named)}; use one of these targets.")

    def listed_line(self, node: Node) -> int:
        """The line list_symbols gives the symbol `node`: that of its C++
        `template <...>` header when it has one, else its own."""
        while self.ext in CPP_EXTS and node.parent is not None and node.parent.type == "template_declaration":
            node = node.parent
        return node.start_point[0] + 1

    def python_overload(self, node: Node) -> bool:
        """Whether `node` is a Python function decorated with typing.overload
        (`@overload`, `@typing.overload`): a stub that only announces the
        definition after it."""
        return self.ext == ".py" and node.type == "decorated_definition" and any(
            c.type == "decorator" and re.fullmatch(r"@\s*(?:\w+\s*\.\s*)*overload", self.node_text(c).strip())
            for c in node.children
        )

    def anonymous_default_export(self, node: Node) -> Node | None:
        """For a JS/TS `export default function () {}` or `export default
        class {}` statement, the anonymous function_expression or class it
        exports, which list_symbols lists and the tools target as `default`
        (a reserved word, so no declaration can have that name). None for any
        other node, including named default exports, which keep their names."""
        if node.type != "export_statement" or self.ext not in JS_EXTS:
            return None
        if not any(child.type == "default" for child in node.children):
            return None
        value = node.child_by_field_name("value")
        if value is None or value.type not in DEFAULT_EXPORT_KINDS:
            return None
        if value.child_by_field_name("name") is not None:
            return None
        return value

    def _search_json_dotted(self, root: Node, target_name: str) -> Node | None:
        """
        The value at a key path in a JSON document, or None. The path is
        followed from the top-level object one key per segment: 'a.b' is
        key b of the object under the top-level key a, never an a.b nested
        deeper, and a segment in double quotes is one key, dots included
        ('"editor.fontSize"', see split_config_path). Keys compare by their
        decoded text (json_key_name).
        """
        node = next((c for c in root.named_children if c.type != "comment"), None)
        for part in split_config_path(target_name):
            if node is None or node.type != "object":
                return None
            node = next(
                (
                    pair.child_by_field_name("value")
                    for pair in node.named_children
                    if pair.type == "pair" and self.json_key_name(pair) == part
                ),
                None,
            )
        return node

    def json_key_name(self, pair: Node) -> str | None:
        """The decoded key of a JSON pair, escapes resolved; None if it has
        no key."""
        key_node = pair.child_by_field_name("key")
        if key_node is None:
            return None
        try:
            name = json.loads(self.node_text(key_node))
        except ValueError:
            name = None
        if isinstance(name, str):
            return name
        return "".join(
            self.node_text(c) for c in key_node.children if c.type == "string_content"
        )

    def _search_yaml_dotted(self, root: Node, target_name: str) -> Node | None:
        """The value node of the pair find_yaml_pair finds, or None (also
        for a key written with no value, `key:`)."""
        pair = self.find_yaml_pair(root, target_name)
        return pair.child_by_field_name("value") if pair is not None else None

    def find_yaml_pair(self, root: Node, target_name: str) -> Node | None:
        """
        The entry (yaml_entries) at a key path in a YAML stream, or None.
        The path is followed from a document's top-level mapping one key per
        segment: 'a.b' is key b of the mapping under the top-level key a,
        never an a.b nested deeper. Block and flow mappings are followed
        alike, so 'a.x' is x in `a: {x: 1}`. A segment in double quotes is
        one key, dots included ('"a.b"', see split_config_path). The
        documents of a multi-document stream are tried in order. A key
        written in quotes matches the name it spells, escapes resolved
        ('it''s' is it's, "caf\\u00e9" café), as add_key compares keys.
        """
        parts = split_config_path(target_name, strip=True)
        for doc in root.named_children:
            if doc.type != "document":
                continue
            pair, node = None, self.yaml_mapping(doc)
            for part in parts:
                pair = next(
                    (e for e in self.yaml_entries(node) if self._yaml_key_is(e, part)), None
                )
                if pair is None:
                    break
                node = self.yaml_mapping(pair.child_by_field_name("value"))
            if pair is not None:
                return pair
        return None

    def _yaml_key_is(self, pair: Node, name: str) -> bool:
        """Whether a YAML entry's key is `name`: the name its source spells
        (yaml_key_name: quotes removed, escapes resolved), or its source
        text as written."""
        key_node = self.yaml_entry_key(pair)
        if key_node is None:
            return False
        key = self.node_text(key_node).strip()
        return key == name or self.yaml_key_name(key) == name

    @staticmethod
    def yaml_entries(mapping: Node | None) -> list[Node]:
        """The entries of a YAML mapping (as yaml_mapping returns it): its
        pairs and, in a flow mapping, the keys written without a value (the
        `b` of `{a: 1, b}`), which are flow_nodes. Comments are left out."""
        if mapping is None:
            return []
        if mapping.type == "block_mapping":
            return [c for c in mapping.named_children if c.type == "block_mapping_pair"]
        if mapping.type == "flow_mapping":
            return [c for c in mapping.named_children if c.type in ("flow_pair", "flow_node")]
        return []

    @staticmethod
    def yaml_entry_key(entry: Node) -> Node | None:
        """The key node of a YAML mapping entry: a pair's key field, or the
        flow_node itself for a key written without a value in a flow
        mapping."""
        if entry.type == "flow_node":
            return entry
        return entry.child_by_field_name("key")

    @staticmethod
    def yaml_key_name(text: str) -> str:
        """The name a YAML key's source text spells: a quoted key without
        its quotes, its escapes resolved ('' in single quotes, JSON-style
        ones in double quotes)."""
        text = text.strip()
        if len(text) >= 2 and text[0] == text[-1] == "'":
            return text[1:-1].replace("''", "'")
        if len(text) >= 2 and text[0] == text[-1] == '"':
            try:
                name = json.loads(text)
            except ValueError:
                name = None
            return name if isinstance(name, str) else text[1:-1]
        return text

    def yaml_mapping(self, node: Node | None) -> Node | None:
        """The block_mapping or flow_mapping that a YAML document or value
        node holds (past directives, an anchor or a tag), or None if it holds
        something else or nothing."""
        if node is not None and node.type == "document":
            node = next(
                (c for c in node.named_children if c.type in ("block_node", "flow_node")), None
            )
        while node is not None and node.type in ("block_node", "flow_node"):
            node = next(
                (c for c in node.named_children if c.type not in ("anchor", "tag", "comment")),
                None,
            )
        if node is not None and node.type in ("block_mapping", "flow_mapping"):
            return node
        return None

    def _search_toml_dotted(self, root: Node, target_name: str) -> Node | None:
        """The value of the pair toml_pair finds, or None."""
        pair = self.toml_pair(root, target_name)
        return self.toml_value(pair) if pair is not None else None

    def toml_pair(self, root: Node, target_name: str) -> Node | None:
        """
        The pair that defines the key a TOML target path names, or None. The
        path is the key's full name from the top level, written like a TOML
        dotted key (toml_key_names: '"a.b"' or "'a.b'" is one name), and
        names compare by what they spell, so [a."b.c"] and [ a . 'b.c' ]
        are the same table. It can name a top-level key ('version'), a key
        in a [table] ('project.version', 'a.b.key' in [a.b]), a dotted key
        (`x.y = 1` is 'x.y'; in [t], 't.x.y') or a key in an inline table
        ('t.a' in `t = { a = 1 }`, nested ones too). Like the JSON and YAML
        lookups, a path never resolves to a key somewhere deeper: a
        top-level target does not match a key inside a table. [[array]]
        tables are not searched, as array elements are not addressable.
        """
        want = toml_key_names(target_name)
        for names, pair in self._toml_pairs(root):
            if names == want:
                return pair
        return None

    def _toml_pairs(self, root: Node):
        """Yield (full key names, pair) for each pair of a TOML document
        outside [[array]] tables, in document order, the pairs of inline
        tables included."""
        for child in root.named_children:
            if child.type == "pair":
                yield from self._toml_pair_names([], child)
            elif child.type == "table":
                prefix = self.toml_header_names(child)
                if prefix is None:
                    continue
                for pair in child.named_children:
                    if pair.type == "pair":
                        yield from self._toml_pair_names(prefix, pair)

    def _toml_pair_names(self, prefix: list[str], pair: Node):
        """Yield (full key names, pair) for a TOML pair under `prefix` and for
        the pairs of the inline table it holds, if any."""
        names = prefix + toml_key_names(self.node_text(pair.children[0]))
        yield names, pair
        value = self.toml_value(pair)
        if value is not None and value.type == "inline_table":
            for inner in value.named_children:
                if inner.type == "pair":
                    yield from self._toml_pair_names(names, inner)

    @staticmethod
    def toml_value(pair: Node) -> Node | None:
        """The value node of a TOML pair (the node after its `=`), or None."""
        seen_equals = False
        for child in pair.children:
            if seen_equals and child.is_named:
                return child
            seen_equals = seen_equals or child.type == "="
        return None

    def toml_header_names(self, table: Node) -> list[str] | None:
        """The names a TOML [table] or [[array]] header spells, or None if
        the node has no header key."""
        header = table.named_children[0] if table.named_children else None
        if header is None or header.type not in ("bare_key", "quoted_key", "dotted_key"):
            return None
        return toml_key_names(self.node_text(header))

    def toml_table(self, root: Node, target_name: str) -> Node | None:
        """The [table] whose header spells the names of the TOML target path
        target_name (as toml_pair compares them), or None."""
        want = toml_key_names(target_name)
        return next(
            (
                c
                for c in root.named_children
                if c.type == "table" and self.toml_header_names(c) == want
            ),
            None,
        )

    def node_text(self, node) -> str:
        """Return the source text for a node using its byte offsets (safe for multi-byte chars)."""
        return self.source_bytes[node.start_byte : node.end_byte].decode("utf-8")

    def _extract_go_receiver_type(self, recv_param_list: Node) -> str | None:
        """
        Extract the receiver type name from a Go method_declaration's receiver
        parameter list (e.g. '(c *Cache)' -> 'Cache', '(s Store)' -> 'Store').
        """
        for param in recv_param_list.named_children:
            if param.type != "parameter_declaration":
                continue
            for c in param.named_children:
                if c.type == "type_identifier":
                    return self.node_text(c)
                if c.type == "pointer_type":
                    for sub in c.named_children:
                        if sub.type == "type_identifier":
                            return self.node_text(sub)
        return None

    def _find_go_method_by_receiver(self, receiver_type: str, method_name: str) -> Node | None:
        """
        Walk top-level method_declarations and match (receiver_type, method_name).
        Go methods are top-level siblings to their receiver type, so we can't use
        the normal class-descendant search.
        """
        for child in self.tree.root_node.named_children:
            if child.type != "method_declaration":
                continue
            name_node = child.child_by_field_name("name")
            recv_node = child.child_by_field_name("receiver")
            if name_node is None or recv_node is None:
                continue
            if self.node_text(name_node) != method_name:
                continue
            recv_type = self._extract_go_receiver_type(recv_node)
            if recv_type == receiver_type:
                return child
        return None

    def _find_go_closure_in_var(self, var_name: str, field_name: str) -> Node | None:
        """
        Go: find a `func_literal` stored as the value of a keyed_element
        matching `field_name`, inside a composite_literal assigned to a
        top-level var_spec named `var_name`. Handles plain `var x = ...`,
        `var ( x = ... )` blocks, and `&T{...}` pointer wrappers.
        """
        for child in self.tree.root_node.named_children:
            if child.type not in ("var_declaration", "const_declaration"):
                continue
            specs = []
            for sub in child.named_children:
                if sub.type in ("var_spec", "const_spec"):
                    specs.append(sub)
                elif sub.type in ("var_spec_list", "const_spec_list"):
                    for inner in sub.named_children:
                        if inner.type in ("var_spec", "const_spec"):
                            specs.append(inner)
            for spec in specs:
                name_node = None
                for c in spec.named_children:
                    if c.type == "identifier":
                        name_node = c
                        break
                if name_node is None or self.node_text(name_node) != var_name:
                    continue
                # Find the value: usually wrapped in an expression_list
                for c in spec.named_children:
                    if c.type == "identifier":
                        continue
                    closure = self._walk_for_keyed_func_literal(c, field_name)
                    if closure is not None:
                        return closure
        return None

    def _walk_for_keyed_func_literal(self, node: Node, field_name: str) -> Node | None:
        """Walk through expression_list / unary_expression wrappers to a
        composite_literal, then locate a keyed_element with matching key and
        return its func_literal value."""
        if node is None:
            return None
        if node.type == "composite_literal":
            body = node.child_by_field_name("body")
            if body is None:
                for c in node.named_children:
                    if c.type == "literal_value":
                        body = c
                        break
            if body is None:
                return None
            for elem in body.named_children:
                if elem.type != "keyed_element":
                    continue
                # First named child is the key (wrapped in literal_element);
                # last named child is the value (wrapped in literal_element).
                if len(elem.named_children) < 2:
                    continue
                key_wrapper = elem.named_children[0]
                val_wrapper = elem.named_children[-1]
                key_inner = key_wrapper
                if key_wrapper.type == "literal_element" and key_wrapper.named_children:
                    key_inner = key_wrapper.named_children[0]
                if key_inner.type not in ("identifier", "field_identifier"):
                    continue
                if self.node_text(key_inner) != field_name:
                    continue
                val_inner = val_wrapper
                if val_wrapper.type == "literal_element" and val_wrapper.named_children:
                    val_inner = val_wrapper.named_children[0]
                if val_inner.type == "func_literal":
                    return val_inner
            return None
        # Unwrap common wrappers: expression_list, unary_expression, parenthesized_expression
        if node.type in ("expression_list", "unary_expression", "parenthesized_expression"):
            for c in node.named_children:
                result = self._walk_for_keyed_func_literal(c, field_name)
                if result is not None:
                    return result
        return None

    def _find_js_closure_by_var(self, var_name: str, field_name: str) -> Node | None:
        """
        JS/TS: find an arrow_function / function_expression / function value of
        a pair whose key matches `field_name`, inside an object literal assigned
        to `var_name`. Works for plain `const/let/var` declarations and ones
        wrapped in `export`.
        """
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
                        if name_node is None or self.node_text(name_node) != var_name:
                            continue
                        value = decl.child_by_field_name("value")
                        if value is None:
                            for c in decl.named_children:
                                if c.type == "object":
                                    value = c
                                    break
                        if value is None or value.type != "object":
                            continue
                        for entry in value.named_children:
                            if entry.type != "pair":
                                continue
                            key_node = entry.child_by_field_name("key")
                            if key_node is None and entry.named_children:
                                key_node = entry.named_children[0]
                            if key_node is None:
                                continue
                            k_text = self.node_text(key_node).strip()
                            # Strip quotes for string keys
                            if len(k_text) >= 2 and k_text[0] in "\"'`" and k_text[-1] in "\"'`":
                                k_text = k_text[1:-1]
                            if k_text != field_name:
                                continue
                            val_node = entry.child_by_field_name("value")
                            if val_node is None and len(entry.named_children) >= 2:
                                val_node = entry.named_children[-1]
                            if val_node is not None and val_node.type in (
                                "arrow_function",
                                "function_expression",
                                "function",
                            ):
                                return val_node
                elif child.type == "export_statement":
                    result = walk(child)
                    if result is not None:
                        return result
            return None
        return walk(self.tree.root_node)

    def js_bound_function(self, node: Node, name: str | None = None) -> Node | None:
        """For a JS/TS `const`/`let`/`var` declaration, the arrow function,
        function expression or generator bound to `name` (`const f = () => {}`),
        or, when name is None, to the only name it declares (None if it
        declares several, or destructures). None if that value is something
        else, or node is no such declaration. The variable_declarator holding
        the name is the returned node's parent."""
        if self.ext not in JS_EXTS or node.type not in ("lexical_declaration", "variable_declaration"):
            return None
        declarators = [c for c in node.named_children if c.type == "variable_declarator"]
        if name is None:
            only = declarators[0].child_by_field_name("name") if len(declarators) == 1 else None
            if only is None or only.type != "identifier":
                return None
            name = self.node_text(only)
        for decl in declarators:
            name_node = decl.child_by_field_name("name")
            if name_node is None or self.node_text(name_node) != name:
                continue
            value = decl.child_by_field_name("value")
            return value if value is not None and value.type in JS_FUNCTION_VALUES else None
        return None

    def go_bound_function(self, node: Node, name: str) -> Node | None:
        """For a Go `var` spec, the func literal it gives `name` (`var f =
        func(a int) {...}`, the k-th value for its k-th name), or None if
        that value is something else, or node is no such spec."""
        if self.ext not in GO_EXTS or node.type != "var_spec":
            return None
        names = [c for c in node.children_by_field_name("name") if c.type == "identifier"]
        value = node.child_by_field_name("value")
        values = [c for c in value.named_children if "comment" not in c.type] if value is not None else []
        for k, name_node in enumerate(names):
            if self.node_text(name_node) == name and len(values) == len(names):
                return values[k] if values[k].type == "func_literal" else None
        return None
