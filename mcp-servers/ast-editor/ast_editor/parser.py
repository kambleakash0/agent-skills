import os
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


class TreeSitterParser:
    def __init__(self, filepath: str):
        self.filepath = filepath
        _, self.ext = os.path.splitext(filepath)

        try:
            if self.ext == ".py":
                self.language = Language(tree_sitter_python.language())
            elif self.ext in (".js", ".jsx", ".mjs", ".cjs"):
                self.language = Language(tree_sitter_javascript.language())
            elif self.ext in (".ts", ".tsx"):
                self.language = Language(tree_sitter_typescript.language_typescript())
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
            self.source_bytes = f.read()
        self.source_code = self.source_bytes.decode("utf-8")
        self.tree = self.parser.parse(self.source_bytes)

    def find_node_by_name(self, target_name: str) -> Node | None:
        """
        Locates an AST node by its semantic name.
        Supports dotted paths (e.g., ClassName.methodName).
        """
        if self.ext == ".py":
            class_types = ["class_definition"]
            func_types = ["function_definition", "decorated_definition"]
            var_types = ["expression_statement"]
        elif self.ext in (".ts", ".tsx"):
            class_types = ["class_declaration", "interface_declaration"]
            func_types = ["function_declaration", "method_definition", "arrow_function", "variable_declaration"]
            var_types = ["variable_declaration", "lexical_declaration"]
        elif self.ext in (".js", ".jsx", ".mjs", ".cjs"):
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
            parts = target_name.split(".")
            if len(parts) == 2:
                go_method = self._find_go_method_by_receiver(parts[0], parts[1])
                if go_method is not None:
                    return go_method
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
        queue = [node]
        while queue:
            curr = queue.pop(0)
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

    def _search_json_dotted(self, root: Node, target_name: str) -> Node | None:
        parts = target_name.split(".")
        current_node = root
        for part in parts:
            found = False
            queue = [current_node]
            while queue and not found:
                curr = queue.pop(0)
                if curr.type == "pair":
                    key_node = curr.child_by_field_name("key")
                    if key_node and key_node.type == "string":
                        name = ""
                        for child in key_node.children:
                            if child.type == "string_content":
                                name = self.node_text(child)
                        if name == part:
                            current_node = curr.child_by_field_name("value")
                            found = True
                            break
                queue.extend(curr.named_children)
            if not found:
                return None
        return current_node

    def _search_yaml_dotted(self, root: Node, target_name: str) -> Node | None:
        parts = target_name.split(".")
        current_node = root
        for part in parts:
            found = False
            queue = [current_node]
            while queue and not found:
                curr = queue.pop(0)
                if curr.type == "block_mapping_pair":
                    key_node = curr.child_by_field_name("key")
                    if key_node:
                        name = self.node_text(key_node).strip()
                        if name == part or name == f'"{part}"' or name == f"'{part}'":
                            current_node = curr.child_by_field_name("value")
                            found = True
                            break
                queue.extend(curr.named_children)
            if not found:
                return None
        return current_node

    def _search_toml_dotted(self, root: Node, target_name: str) -> Node | None:
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
            # Root level pair
            while queue:
                curr = queue.pop(0)
                if curr.type == "pair":
                    k_node = curr.children[0]
                    if self.node_text(k_node) == parts[0]:
                        return curr.children[2]
                queue.extend(curr.named_children)
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
