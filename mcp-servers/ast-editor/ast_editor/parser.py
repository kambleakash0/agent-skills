import os
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_json
import tree_sitter_yaml
import tree_sitter_toml
from tree_sitter import Language, Parser, Node

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
            else:
                raise ValueError(f"Unsupported file extension: {self.ext}")
        except TypeError:
             # TODO: This fallback handles older tree-sitter versions that require a second
             # argument (language name string) to the Language constructor. Since pyproject.toml
             # requires tree-sitter>=0.21.0 (which uses the new single-arg API), this block is
             # likely dead code. It's also missing .mjs/.cjs for JS and has no fallback for
             # YAML/TOML. Consider removing this entirely once we confirm minimum supported
             # tree-sitter versions, or fix the missing extensions if we want to keep it.
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

        # Newer tree_sitter versions take Language in Parser constructor directly
        self.parser = Parser(self.language)
        
        with open(filepath, "r", encoding="utf-8") as f:
            self.source_code = f.read()
        self.tree = self.parser.parse(bytes(self.source_code, "utf8"))

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
        elif self.ext == ".json":
            return self._search_json_dotted(self.tree.root_node, target_name)
        elif self.ext in (".yml", ".yaml"):
            return self._search_yaml_dotted(self.tree.root_node, target_name)
        elif self.ext == ".toml":
            return self._search_toml_dotted(self.tree.root_node, target_name)
        else:
            return None

        return self._search_tree_dotted(self.tree.root_node, target_name, class_types, func_types, var_types)

    def _search_tree_dotted(self, root: Node, target_name: str, class_types: list[str], func_types: list[str], var_types: list[str]) -> Node | None:
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

    def _find_child_with_name(self, node: Node, name: str, valid_types: list[str]) -> Node | None:
        queue = [node]
        while queue:
            curr = queue.pop(0)
            if curr.type in valid_types:
                # For decorated definitions, preserve the wrapper node so that
                # replace_function/delete_node operate on the full block (decorators
                # included), but unwrap to the inner function for name matching.
                outer_node = curr
                if curr.type == "decorated_definition":
                    for child in curr.named_children:
                        if child.type == "function_definition":
                            curr = child
                            break

                name_node = curr.child_by_field_name("name")

                # Check for python assignment
                if not name_node and curr.type == "expression_statement":
                    assignment = curr.named_children[0] if curr.named_children else None
                    if assignment and assignment.type == "assignment":
                        name_node = assignment.named_children[0]

                # Check for JS/TS variable declarators
                if not name_node and curr.type in ("variable_declaration", "lexical_declaration"):
                    for child in curr.named_children:
                        if child.type == "variable_declarator":
                            name_node = child.child_by_field_name("name")
                            if name_node:
                                node_name = self.source_code[name_node.start_byte:name_node.end_byte]
                                if node_name == name:
                                    return outer_node

                if name_node:
                    node_name = self.source_code[name_node.start_byte:name_node.end_byte]
                    if node_name == name:
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
                                name = self.source_code[child.start_byte:child.end_byte]
                        if name == part:
                            current_node = curr.child_by_field_name("value")
                            found = True
                            break
                queue.extend(curr.named_children)
            if not found: return None
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
                        name = self.source_code[key_node.start_byte:key_node.end_byte].strip()
                        if name == part or name == f'"{part}"' or name == f"'{part}'":
                            current_node = curr.child_by_field_name("value")
                            found = True
                            break
                queue.extend(curr.named_children)
            if not found: return None
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
                    name = self.source_code[header.start_byte:header.end_byte].strip("[] \n")
                    if name == table_name:
                        for child in curr.named_children:
                            if child.type == "pair":
                                # TOML pairs don't use named fields for key/value
                                k_node = child.children[0]
                                k_name = self.source_code[k_node.start_byte:k_node.end_byte]
                                if k_name == target_key:
                                    return child.children[2]  # child 1 is '='
                queue.extend(curr.named_children)
        else:
            # Root level pair
            while queue:
                curr = queue.pop(0)
                if curr.type == "pair":
                    k_node = curr.children[0]
                    k_name = self.source_code[k_node.start_byte:k_node.end_byte]
                    if k_name == parts[0]:
                        return curr.children[2]
                queue.extend(curr.named_children)
        return None
