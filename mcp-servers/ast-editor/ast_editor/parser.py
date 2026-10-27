import json
import os
import re
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

# Statements that wrap one TS declaration (`export ...`, `declare ...`), whose
# siblings are the declaration's own (see _refuse_ambiguous_ts).
_TS_DECLARATION_WRAPPERS = ("export_statement", "ambient_declaration")

# TS declarations that declare one kind of symbol under different node
# types (see _refuse_ambiguous_ts): a function's overload signatures and its
# implementation.
_TS_KINDS = {"function_signature": "function_declaration"}

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


def c_name(text: str) -> str:
    """A C++ destructor or operator name as list_symbols shows it and a
    target may write it: with the spaces between words only, so `~ A` is
    `~A`, `operator ==` is `operator==`, `operator new []` is `operator
    new[]` and `operator const char *` is `operator const char*`."""
    return re.sub(r" (?=\W)|(?<=\W) ", "", " ".join(text.split()))


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
        self.source_bytes = raw.replace(b"\r\n", b"\n")
        try:
            self.source_code = self.source_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            encoding = next((name for mark, name in _OTHER_BOMS if raw.startswith(mark)), None)
            what = (
                f"{encoding} text (it starts with a {encoding} byte order mark)"
                if encoding
                else f"not UTF-8 text ({e})"
            )
            raise ValueError(
                f"{filepath} is {what}; ast-editor reads and writes UTF-8 files only. "
                "Convert it to UTF-8, or make this edit with your normal edit tool."
            ) from e
        self.tree = self.parse(self.source_bytes)

    def parse(self, data: bytes):
        """Parse LF source with this file's grammar: the file itself, or an
        edited version of it for the save-time syntax check. JSON is parsed
        from a copy with its exponent signs masked (mask_json_exponents)."""
        if self.ext == ".json":
            data = mask_json_exponents(data)
        return self.parser.parse(data)

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
        and a `const`/`let`/`var` by the name it declares (the whole
        declaration is returned; js_bound_function gets the function bound
        to it). A TS name that two kinds of declaration in one scope declare
        (a type and a value: `const User` and `type User`) is refused as
        ambiguous with an ApplierError (_refuse_ambiguous_ts).
        C/C++ variables, fields, typedefs, `using` aliases, macros, function
        prototypes and methods declared in their class are found as well,
        by every name a declaration declares (`b` of `int a, *b;`, the whole
        declaration being returned), destructors as `~A` and operators as
        c_name writes them (`operator==`, `operator bool`); so are Java
        fields and Go type aliases and every name of a Go `var`/`const`
        spec. Where one scope declares a name more than once, a definition
        is found rather than its forward declaration, prototype, `extern`
        declaration or TS overload signature (definition_rank).
        In JSON, YAML and TOML files the target is a key path followed from
        the top level, a segment in double quotes (in TOML also single
        quotes) being one key with any dots in it (split_config_path), and
        the key's value node is returned (see _search_json_dotted,
        find_yaml_pair and toml_pair); a YAML key with no value has none.
        """
        parts = target_name.split(".")

        if self.ext == ".py":
            class_types = ["class_definition"]
            func_types = ["function_definition", "decorated_definition"]
            var_types = ["expression_statement"]
        elif self.ext in (".ts", ".tsx"):
            # JS/TS: try closure-in-object-literal first for dotted paths
            if len(parts) == 2:
                closure = self._find_js_closure_by_var(parts[0], parts[1])
                if closure is not None:
                    return closure
            class_types = [
                "class_declaration",
                "abstract_class_declaration",
                "interface_declaration",
                "internal_module",
                "module",
            ]
            func_types = [
                "function_declaration",
                "generator_function_declaration",
                "function_signature",
                "method_definition",
                "abstract_method_signature",
                "arrow_function",
                "variable_declaration",
            ]
            var_types = ["variable_declaration", "lexical_declaration", "enum_declaration", "type_alias_declaration"]
        elif self.ext in (".js", ".jsx", ".mjs", ".cjs"):
            if len(parts) == 2:
                closure = self._find_js_closure_by_var(parts[0], parts[1])
                if closure is not None:
                    return closure
            class_types = ["class_declaration"]
            func_types = [
                "function_declaration",
                "generator_function_declaration",
                "method_definition",
                "arrow_function",
                "variable_declaration",
                "lexical_declaration",
            ]
            var_types = ["variable_declaration", "lexical_declaration"]
        elif self.ext in C_EXTS:
            # A typedef of a struct holds its fields (`P.x` of `typedef
            # struct {...} P;`).
            class_types = ["struct_specifier", "union_specifier", "enum_specifier", "type_definition"]
            func_types = ["function_definition"]
            var_types = ["declaration", "field_declaration", "preproc_def", "preproc_function_def"]
        elif self.ext in CPP_EXTS:
            class_types = [
                "class_specifier",
                "struct_specifier",
                "union_specifier",
                "enum_specifier",
                "namespace_definition",
                "type_definition",
            ]
            func_types = ["function_definition"]
            var_types = ["declaration", "field_declaration", "alias_declaration", "preproc_def", "preproc_function_def"]
        elif self.ext in RUBY_EXTS:
            class_types = ["class", "module"]
            func_types = ["method", "singleton_method"]
            var_types = ["assignment"]
        elif self.ext in GO_EXTS:
            if len(parts) == 2:
                # Try: receiver-based method (Cache.Get)
                go_method = self._find_go_method_by_receiver(parts[0], parts[1])
                if go_method is not None:
                    return go_method
                # Try: func_literal stored in a composite-literal field (stdioCmd.RunE)
                go_closure = self._find_go_closure_in_var(parts[0], parts[1])
                if go_closure is not None:
                    return go_closure
            class_types = ["type_spec"]
            func_types = ["function_declaration", "method_declaration"]
            var_types = ["const_spec", "var_spec", "type_alias"]
        elif self.ext == ".java":
            class_types = ["class_declaration", "interface_declaration", "enum_declaration", "record_declaration"]
            func_types = ["method_declaration", "constructor_declaration"]
            var_types = ["field_declaration", "constant_declaration"]
        elif self.ext == ".json":
            return self._search_json_dotted(self.tree.root_node, target_name)
        elif self.ext in (".yml", ".yaml"):
            return self._search_yaml_dotted(self.tree.root_node, target_name)
        elif self.ext == ".toml":
            return self._search_toml_dotted(self.tree.root_node, target_name)
        else:
            return None

        return self._search_tree_dotted(self.tree.root_node, target_name, class_types, func_types, var_types)

    def _search_tree_dotted(
        self,
        root: Node,
        target_name: str,
        class_types: list[str],
        func_types: list[str],
        var_types: list[str],
    ) -> Node | None:
        """
        The node for the dotted target `target_name` under `root`: each part
        but the last a container (class_types) found in the ones before it,
        the last a symbol of any of the types (_find_child_with_name). A C++
        or TS namespace opened more than once in its scope, and a TS
        namespace merged with the class, function or enum of its name, are
        one container that holds the members of all of their blocks
        (merged_containers): of the nodes that declare a name in them, the
        target is the first of the lowest definition_rank, so a definition
        in a later block wins over a forward declaration in an earlier one.
        """
        parts = target_name.split(".")
        containers = [root]

        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            types = class_types + func_types + var_types if last else class_types
            found = [self._find_child_with_name(c, part, types) for c in containers]
            found = [node for node in found if node is not None]
            if not found:
                return None
            best = min(found, key=lambda node: self._rank(node, part))
            if last:
                return best
            containers = self.merged_containers(best, part, class_types)

        return None

    def _rank(self, node: Node, name: str) -> int:
        """The definition_rank of `node`, found for `name` (a Python
        decorated definition by its function's name)."""
        inner = node
        if node.type == "decorated_definition":
            inner = next((c for c in node.named_children if c.type == "function_definition"), node)
        declared = self.declared_name(inner, name)
        return self.definition_rank(node, declared) if declared is not None else 0

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
        declares, in order: its name field; in C/C++ the names
        c_declared_names finds; a Python or Ruby assignment's left side;
        every name of a Go `var`/`const` spec (`a, b = 1, 2`); and the
        declarators of a JS/TS `const`/`let`/`var` or a Java field (`int x,
        y;`).
        """
        if self.ext in C_EXTS + CPP_EXTS:
            return self.c_declared_names(node)
        if node.type in ("const_spec", "var_spec") and self.ext in GO_EXTS:
            return [c for c in node.children_by_field_name("name") if c.type == "identifier"]
        name = node.child_by_field_name("name")
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
        None."""
        if self.ext in C_EXTS + CPP_EXTS and name.lstrip().startswith(("~", "operator")):
            name = c_name(name)
        return next((n for n in self.declared_names(node) if self.symbol_name(n) == name), None)

    def definition_rank(self, node: Node, name: Node) -> int:
        """
        How `node`, found for the name node `name`, ranks among the nodes
        that declare one name in one scope, the lowest being the target
        (_find_child_with_name): 0 for a definition with a body (a C/C++
        function, class, struct, union, enum or namespace, a Java method or
        class) and for any symbol outside C, C++, Java and TS; 1 for another
        definition (a C/C++ variable, field, typedef, `using` alias or macro,
        a Java field, which shares its name with an accessor method, `int
        size;` and `int size()`, a TS namespace, which merges with the class,
        function or enum of its name); 2 for a declaration that only announces a
        definition: a C/C++ forward declaration (`struct S;`), a prototype
        or a method declared in its class, an `extern` variable without a
        value, and a TS overload signature or function declared without a
        body (`declare function f(): void;`).
        """
        if self.ext in (".ts", ".tsx"):
            if node.type in NAMESPACES:
                return 1
            return 2 if node.type == "function_signature" else 0
        if self.ext == ".java":
            return 1 if node.type in ("field_declaration", "constant_declaration") else 0
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

    def _find_child_with_name(self, node: Node, name: str, valid_types: list[str]) -> Node | None:
        # Search below `node` only: the container must not match itself, or
        # a Java constructor target such as `LRUCache.LRUCache` would resolve
        # to the class. Of the nodes that declare `name` in one scope, the
        # one with the lowest definition_rank is the target: a definition
        # rather than its forward declaration, prototype or overload
        # signatures, before or after it, and of those of one rank the first
        # (a preprocessor conditional or TS `namespace` statement around one
        # puts it deeper in the tree). The variables and types a C/C++
        # function declares are its own, no targets (_c_local).
        c_family = self.ext in C_EXTS + CPP_EXTS
        best, best_rank = None, None
        queue = list(node.named_children)
        while queue:
            curr = queue.pop(0)
            if name == "default" and curr.type == "export_statement":
                value = self.anonymous_default_export(curr)
                if value is not None and DEFAULT_EXPORT_KINDS[value.type] in valid_types:
                    return value
            if curr.type in valid_types:
                # For decorated definitions, preserve the wrapper node so that
                # replace_function/delete_symbol operate on the full block (decorators
                # included), but unwrap to the inner function for name matching.
                outer_node = curr
                if curr.type == "decorated_definition":
                    for child in curr.named_children:
                        if child.type == "function_definition":
                            curr = child
                            break
                declared = self.declared_name(curr, name)
                if declared is not None and not (c_family and self._c_local(curr)):
                    rank = self.definition_rank(outer_node, declared)
                    if best is None or (
                        (rank, outer_node.start_byte) < (best_rank, best.start_byte)
                        and self._scope(outer_node) == self._scope(best)
                    ):
                        best, best_rank = outer_node, rank
                    if best_rank == 0:
                        break
            queue.extend(curr.named_children)
        if best is not None:
            self._refuse_ambiguous_ts(best, name, valid_types)
        return best

    def _refuse_ambiguous_ts(self, match: Node, name: str, valid_types: list[str]) -> None:
        """
        In a TS file, refuse `name` when, beside the declaration `match`
        found for it, another kind of declaration in the same scope declares
        it too. TS keeps types apart from values, so one name can be both
        (`const User = z.object(...)` and `type User = z.infer<typeof User>`,
        or an interface and a function), and the tools would act on
        whichever comes first, perhaps not the one list_symbols showed.
        Declarations of one kind (merged interfaces, a function's overload
        signatures and its implementation, see _TS_KINDS) are not compared,
        nor are namespaces, which merge with the other declarations of their
        name (merged_containers).
        """
        if self.ext not in (".ts", ".tsx") or match.type in NAMESPACES:
            return
        statement = match
        while statement.parent is not None and statement.parent.type in _TS_DECLARATION_WRAPPERS:
            statement = statement.parent
        if statement.parent is None:
            return
        found = [(statement, match)]
        for sibling in statement.parent.named_children:
            if sibling == statement:
                continue
            decl = sibling
            while decl is not None and decl.type in _TS_DECLARATION_WRAPPERS:
                decl = decl.child_by_field_name("declaration") or next(
                    (c for c in decl.named_children if c.type in valid_types), None
                )
            if (
                decl is not None
                and decl.type in valid_types
                and decl.type not in NAMESPACES
                and _TS_KINDS.get(decl.type, decl.type) != _TS_KINDS.get(match.type, match.type)
                and self._ts_declares(decl, name)
            ):
                found.append((sibling, decl))
        if len(found) < 2:
            return
        found.sort(key=lambda f: f[0].start_byte)
        named = [f"`{self._ts_declaration_label(decl, name)}` (line {stmt.start_point[0] + 1})" for stmt, decl in found]
        raise ApplierError(
            f"'{name}' is ambiguous: {', '.join(named[:-1])} and {named[-1]} "
            f"{'both' if len(named) == 2 else 'all'} declare it, and a target "
            "cannot say which one it means. Edit these declarations with your "
            "normal edit tool."
        )

    def _ts_declares(self, decl: Node, name: str) -> bool:
        """Whether the TS declaration `decl` declares `name`: by its name
        field, or for a `const`/`let`/`var` by one of its declarators."""
        name_node = decl.child_by_field_name("name")
        if name_node is not None:
            return self.node_text(name_node) == name
        return any(
            child.type == "variable_declarator"
            and (declared := child.child_by_field_name("name")) is not None
            and self.node_text(declared) == name
            for child in decl.named_children
        )

    def _ts_declaration_label(self, decl: Node, name: str) -> str:
        """How _refuse_ambiguous_ts shows a declaration: its keywords and
        name, `const User`, `type User`, `abstract class A`."""
        if decl.type in ("lexical_declaration", "variable_declaration"):
            return f"{self.node_text(decl.children[0])} {name}"
        name_node = decl.child_by_field_name("name")
        start = next((c.start_byte for c in decl.children if c.type != "decorator"), decl.start_byte)
        head = self.source_bytes[start : name_node.start_byte].decode("utf-8")
        return " ".join(head.split() + [name])

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
