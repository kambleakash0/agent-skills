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
        # Everything works on LF text internally (node positions, caller
        # snippets, inserted code); the Applier writes the file back with
        # its own `newline` style.
        self.newline = detect_newline(raw)
        self.source_bytes = raw.replace(b"\r\n", b"\n")
        self.source_code = self.source_bytes.decode("utf-8")
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
        `export default function/class` is named `default`.
        In JSON, YAML and TOML files the target is a key path followed from
        the top level, and the key's value node is returned (see
        _search_json_dotted, find_yaml_pair and _search_toml_dotted).
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
            class_types = ["class_declaration", "interface_declaration"]
            func_types = ["function_declaration", "method_definition", "arrow_function", "variable_declaration"]
            var_types = ["variable_declaration", "lexical_declaration"]
        elif self.ext in (".js", ".jsx", ".mjs", ".cjs"):
            if len(parts) == 2:
                closure = self._find_js_closure_by_var(parts[0], parts[1])
                if closure is not None:
                    return closure
            class_types = ["class_declaration"]
            func_types = ["function_declaration", "method_definition", "arrow_function", "variable_declaration", "lexical_declaration"]
            var_types = ["variable_declaration", "lexical_declaration"]
        elif self.ext in C_EXTS:
            class_types = ["struct_specifier", "union_specifier", "enum_specifier"]
            func_types = ["function_definition"]
            var_types = []
        elif self.ext in CPP_EXTS:
            class_types = ["class_specifier", "struct_specifier", "union_specifier", "enum_specifier", "namespace_definition"]
            func_types = ["function_definition"]
            var_types = []
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
            var_types = ["const_spec", "var_spec"]
        elif self.ext == ".java":
            class_types = ["class_declaration", "interface_declaration", "enum_declaration", "record_declaration"]
            func_types = ["method_declaration", "constructor_declaration"]
            var_types = ["field_declaration"]
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
        parts = target_name.split(".")
        current_node = root

        for i, part in enumerate(parts):
            if i < len(parts) - 1:
                found = self._find_child_with_name(current_node, part, class_types)
                if not found:
                    return None
                current_node = found
            else:
                valid_types = class_types + func_types + var_types
                found = self._find_child_with_name(current_node, part, valid_types)
                if not found:
                    return None
                return found

        return None

    def _extract_c_function_name(self, func_node: Node) -> Node | None:
        """
        For C/C++ function_definition nodes, the name is nested inside the declarator chain:
        function_definition -> declarator (function_declarator) -> declarator (identifier/field_identifier/qualified_identifier)
        Handles pointer/reference declarators and qualified names (Class::method).
        """
        declarator = func_node.child_by_field_name("declarator")
        while declarator:
            if declarator.type in ("identifier", "field_identifier", "type_identifier"):
                return declarator
            if declarator.type == "qualified_identifier":
                # For Class::method, return the inner name
                inner = declarator.child_by_field_name("name")
                return inner if inner else declarator
            declarator = declarator.child_by_field_name("declarator")
        return None

    def _find_child_with_name(self, node: Node, name: str, valid_types: list[str]) -> Node | None:
        # Search below `node` only: the container must not match itself, or
        # a Java constructor target such as `LRUCache.LRUCache` would resolve
        # to the class.
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

                name_node = curr.child_by_field_name("name")

                # C/C++ function_definition: name is nested in declarator chain
                if not name_node and curr.type == "function_definition" and self.ext in C_EXTS + CPP_EXTS:
                    name_node = self._extract_c_function_name(curr)

                # Check for python assignment
                if not name_node and curr.type == "expression_statement":
                    assignment = curr.named_children[0] if curr.named_children else None
                    if assignment and assignment.type == "assignment":
                        name_node = assignment.named_children[0]

                # Ruby top-level assignment: first child is constant/identifier
                if not name_node and curr.type == "assignment" and self.ext in RUBY_EXTS:
                    if curr.named_children:
                        first = curr.named_children[0]
                        if first.type in ("constant", "identifier"):
                            name_node = first

                # Go const_spec / var_spec: name is via `name` field or first identifier child
                if not name_node and curr.type in ("const_spec", "var_spec") and self.ext in GO_EXTS:
                    for c in curr.named_children:
                        if c.type == "identifier":
                            name_node = c
                            break

                # Check for JS/TS variable declarators
                if not name_node and curr.type in ("variable_declaration", "lexical_declaration"):
                    for child in curr.named_children:
                        if child.type == "variable_declarator":
                            name_node = child.child_by_field_name("name")
                            if name_node:
                                if self.node_text(name_node) == name:
                                    return outer_node

                if name_node:
                    if self.node_text(name_node) == name:
                        return outer_node

            queue.extend(curr.named_children)
        return None

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
        The value at a dotted key path in a JSON document, or None. The path
        is followed from the top-level object one key per segment: 'a.b' is
        key b of the object under the top-level key a, never an a.b nested
        deeper. Keys compare by their decoded text (json_key_name).
        """
        node = next((c for c in root.named_children if c.type != "comment"), None)
        for part in target_name.split("."):
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
        The block_mapping_pair at a dotted key path in a YAML stream, or
        None. The path is followed from a document's top-level mapping one
        key per segment: 'a.b' is key b of the mapping under the top-level
        key a, never an a.b nested deeper. The documents of a multi-document
        stream are tried in order. A key written in quotes matches the name
        it spells, escapes resolved ('it''s' is it's, "caf\\u00e9" café), as
        add_key compares keys. Keys inside flow mappings ({a: 1}) are not
        addressable.
        """
        parts = target_name.split(".")
        for doc in root.named_children:
            if doc.type != "document":
                continue
            pair, node = None, self.yaml_mapping(doc)
            for part in parts:
                pairs = node.named_children if node is not None and node.type == "block_mapping" else []
                pair = next(
                    (p for p in pairs if p.type == "block_mapping_pair" and self._yaml_key_is(p, part)),
                    None,
                )
                if pair is None:
                    break
                node = self.yaml_mapping(pair.child_by_field_name("value"))
            if pair is not None:
                return pair
        return None

    def _yaml_key_is(self, pair: Node, name: str) -> bool:
        """Whether a YAML pair's key is `name`: the name its source spells
        (yaml_key_name: quotes removed, escapes resolved), or its source
        text as written."""
        key_node = pair.child_by_field_name("key")
        if key_node is None:
            return False
        key = self.node_text(key_node).strip()
        return key == name or self.yaml_key_name(key) == name

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
        """
        The value at a dotted key path in a TOML document, or None: 'key' is
        a top-level key and 'a.b.key' is `key` in the [a.b] table, written
        as it is in the file (a quoted key with its quotes). Like the JSON
        and YAML lookups, a path never resolves to a key somewhere deeper:
        a top-level target does not match a key inside a table.
        """
        parts = target_name.split(".")
        queue = [root]
        # In TOML, we look for table blocks like [part1.part2] or pairs part1 = ...
        # For simplicity, we search for pair nodes matching the last part inside a table matching the prefix.
        if len(parts) > 1:
            table_name = ".".join(parts[:-1])
            target_key = parts[-1]
            while queue:
                curr = queue.pop(0)
                if curr.type == "table":
                    header = curr.named_children[0]
                    name = self.node_text(header).strip("[] \n")
                    if name == table_name:
                        for child in curr.named_children:
                            if child.type == "pair":
                                # TOML pairs don't use named fields for key/value
                                k_node = child.children[0]
                                if self.node_text(k_node) == target_key:
                                    return child.children[2]  # child 1 is '='
                queue.extend(curr.named_children)
        else:
            # A top-level pair (one before the first [table] header); the
            # keys of tables are not searched.
            for curr in root.named_children:
                if curr.type == "pair" and self.node_text(curr.children[0]) == parts[0]:
                    return curr.children[2]
        return None

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
