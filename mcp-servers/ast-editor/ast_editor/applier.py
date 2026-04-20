import os
from ast_editor.parser import TreeSitterParser


class ApplierError(Exception):
    pass


class Applier:
    def __init__(self, filepath: str):
        self.filepath = filepath
        try:
            self.parser = TreeSitterParser(filepath)
        except ValueError as e:
            # tree-sitter parser raises ValueError for unsupported extensions;
            # convert to ApplierError so callers can distinguish user errors from internal ones.
            raise ApplierError(str(e)) from e

        with open(filepath, "r", encoding="utf-8") as f:
            self.lines = f.read().splitlines()

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

    def replace_function(self, target: str, content: str) -> str:
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        # line indexing is 0-based
        start_line = node.start_point[0]
        end_line = node.end_point[0] + 1

        original_indent = self._get_indent(self.lines[start_line])
        content_lines = content.splitlines()
        if content_lines and self._get_indent(content_lines[0]) != original_indent:
            content_lines = self._reindent(content_lines, original_indent)

        self.lines = self.lines[:start_line] + content_lines + self.lines[end_line:]
        return self._save()

    def replace_value(self, target: str, content: str) -> str:
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found")

        source_bytes = self.parser.source_bytes
        content_bytes = content.encode("utf-8")

        new_bytes = (
            source_bytes[: node.start_byte]
            + content_bytes
            + source_bytes[node.end_byte :]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

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

        content_lines = self._reindent(content.splitlines(), target_indent)

        self.lines = self.lines[:start_line] + content_lines + self.lines[end_line:]
        return self._save()

    def add_method(self, class_target: str, content: str) -> str:
        """
        Add a new method to a class. Placement varies by language:
          - Python/JS/TS/C++/Ruby: inside the class body at the end.
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
            content_lines = content.splitlines()
            # Add a blank separator before and the method content (and a trailing blank for readability)
            sep_before = [""] if insert_line - 1 >= 0 and insert_line - 1 < len(self.lines) and self.lines[insert_line - 1].strip() else []
            self.lines = self.lines[:insert_line] + sep_before + content_lines + self.lines[insert_line:]
            return self._save()

        if self.parser.ext != ".py" and self.parser.ext not in (".rb",):
             # For non-Python/Ruby, insert before the closing `}` of the class body.
             body = node.child_by_field_name("body")
             insert_line = body.end_point[0] if body else node.end_point[0]
             indent = self._get_indent(self.lines[node.start_point[0]]) + "  "
        else:
             # Python and Ruby: body is an indented block; insert at end of body
             if self.parser.ext == ".rb":
                 # Ruby's class body ends at `end` keyword; insert just before the `end` line
                 body = node.child_by_field_name("body")
                 if body is not None:
                     insert_line = body.end_point[0] + 1
                 else:
                     insert_line = node.end_point[0]
                 indent = self._get_indent(self.lines[node.start_point[0]]) + "  "
             else:
                 insert_line = node.end_point[0] + 1
                 indent = self._get_indent(self.lines[node.start_point[0]]) + "    "

        content_lines = self._reindent(content.splitlines(), indent)
        if self.parser.ext not in (".py", ".rb"):
            self.lines = self.lines[:insert_line] + [""] + content_lines + [""] + self.lines[insert_line:]
        else:
            self.lines = self.lines[:insert_line] + [""] + content_lines + self.lines[insert_line:]
        return self._save()

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

        start_line = node.start_point[0]
        end_line = node.end_point[0] + 1

        if include_leading_comments:
            comment_range = self._find_leading_comment_range(start_line)
            if comment_range is not None:
                start_line = comment_range[0]

        self.lines = self.lines[:start_line] + self.lines[end_line:]
        return self._save()

    def _save(self) -> str:
        new_source = "\n".join(self.lines)
        if not new_source.endswith("\n"):
            new_source += "\n"
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(new_source)
        return "Update successful"

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
        """Re-parse the file after a byte-level mutation so subsequent edits see fresh AST."""
        from ast_editor.parser import TreeSitterParser

        self.parser = TreeSitterParser(self.filepath)
        self.lines = self.parser.source_code.splitlines()

    def _write_bytes(self, new_bytes: bytes) -> None:
        """Write new source bytes to disk and refresh parser state."""
        new_source = new_bytes.decode("utf-8")
        if not new_source.endswith("\n"):
            new_source += "\n"
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(new_source)
        self._refresh_parser_state()

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

    def _add_key_json(self, parent_target: str, key: str, value: str) -> str:
        parent = self._find_json_object_at_path(parent_target)
        if parent is None:
            raise ApplierError(
                f"JSON object at '{parent_target or '<root>'}' not found"
            )

        pairs = [c for c in parent.named_children if c.type == "pair"]
        source_bytes = self.parser.source_bytes

        if pairs:
            last_pair = pairs[-1]
            indent = self._get_indent(self.lines[last_pair.start_point[0]])
            insertion = f',\n{indent}"{key}": {value}'
            insert_byte = last_pair.end_byte
        else:
            # Empty object `{}` -- insert between braces
            close_line = parent.end_point[0]
            close_indent = (
                self._get_indent(self.lines[close_line])
                if close_line < len(self.lines)
                else ""
            )
            inner_indent = close_indent + "  "
            insertion = f'\n{inner_indent}"{key}": {value}\n{close_indent}'
            insert_byte = parent.start_byte + 1  # immediately after `{`

        new_bytes = (
            source_bytes[:insert_byte]
            + insertion.encode("utf-8")
            + source_bytes[insert_byte:]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

    def _add_key_yaml(self, parent_target: str, key: str, value: str) -> str:
        root = self.parser.tree.root_node
        if parent_target:
            parent_value = self.parser._search_yaml_dotted(root, parent_target)
            if parent_value is None:
                raise ApplierError(f"YAML key '{parent_target}' not found")
            # parent_value should be a block_node containing a block_mapping
            block_mapping = None
            if parent_value.type == "block_node":
                for child in parent_value.named_children:
                    if child.type == "block_mapping":
                        block_mapping = child
                        break
            elif parent_value.type == "block_mapping":
                block_mapping = parent_value
            if block_mapping is None:
                raise ApplierError(f"YAML value at '{parent_target}' is not a mapping")
        else:
            # Root: find top-level block_mapping
            block_mapping = None
            stack = [root]
            while stack:
                curr = stack.pop()
                if curr.type == "block_mapping":
                    block_mapping = curr
                    break
                stack.extend(curr.named_children)
            if block_mapping is None:
                raise ApplierError("No YAML mapping found at root")

        pairs = [
            c for c in block_mapping.named_children if c.type == "block_mapping_pair"
        ]
        if not pairs:
            raise ApplierError(
                "Cannot add key to empty YAML mapping (unsupported in v1)"
            )

        last_pair = pairs[-1]
        indent = self._get_indent(self.lines[last_pair.start_point[0]])
        insert_line = last_pair.end_point[0] + 1
        new_line = f"{indent}{key}: {value}"
        self.lines = self.lines[:insert_line] + [new_line] + self.lines[insert_line:]
        return self._save()

    def _add_key_toml(self, parent_target: str, key: str, value: str) -> str:
        root = self.parser.tree.root_node
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
                raise ApplierError(f"TOML table '[{parent_target}]' not found")
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

        new_line = f"{indent}{key} = {value}"
        self.lines = self.lines[:insert_line] + [new_line] + self.lines[insert_line:]
        return self._save()

    def add_key(self, parent_target: str, key: str, value: str) -> str:
        """
        Add a new key-value pair inside a container:
          - JSON objects / YAML mappings / TOML tables (via dotted path to parent)
          - Python module-level dict literals (parent_target is the variable name)
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
            value_node = self.parser._search_yaml_dotted(root, dotted_path)
            if value_node:
                p = value_node.parent
                while p and p.type != "block_mapping_pair":
                    p = p.parent
                return p
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
            'VarName.keyName' or 'VarName."quoted-key"'). Handles both regular
            `{ key: value }` pairs and shorthand `{ key }` properties, inside
            `export const` too.

        For JSON and JS/TS, also removes the adjacent comma to keep the file valid.
        """
        ext = self.parser.ext
        if ext == ".py":
            if "." not in target:
                raise ApplierError(
                    f"For Python dicts, target must be 'DictName.keyExpr' (e.g. 'CONFIG.\"foo\"'), got '{target}'"
                )
            dict_name, key_part = target.rsplit(".", 1)
            return self.delete_dict_entry(dict_name, key_part)

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
            idx = sibling_pairs.index(pair)

            source_bytes = self.parser.source_bytes
            start = pair.start_byte
            end = pair.end_byte

            if idx > 0:
                prev_pair = sibling_pairs[idx - 1]
                start = prev_pair.end_byte
            elif idx + 1 < len(sibling_pairs):
                next_pair = sibling_pairs[idx + 1]
                end = next_pair.start_byte

            new_bytes = source_bytes[:start] + source_bytes[end:]
            self._write_bytes(new_bytes)
            return "Update successful"

        # YAML / TOML: remove the pair's line(s)
        start_line = pair.start_point[0]
        end_line = pair.end_point[0] + 1
        self.lines = self.lines[:start_line] + self.lines[end_line:]
        return self._save()

    def _delete_key_js(self, target: str) -> str:
        """Delete a key from a JS/TS object literal assigned at module level.
        Target format: 'VarName.keyName' or 'VarName."quoted-key"'."""
        if "." not in target:
            raise ApplierError(
                f"For JS/TS objects, target must be 'VarName.keyName' (e.g. 'CONFIG.port'), got '{target}'"
            )
        var_name, key = target.rsplit(".", 1)

        obj_node = self._find_js_object_literal(var_name)
        if obj_node is None:
            raise ApplierError(
                f"'{var_name}' not found as a module-level const/let/var assigned to an object literal"
            )

        entries = [
            c
            for c in obj_node.named_children
            if c.type in ("pair", "shorthand_property_identifier")
        ]

        key_stripped = key.strip()
        # Normalize: strip matching quotes so 'port' matches 'port' and '"complex-key"' matches '"complex-key"'.
        def _unquote(s: str) -> str:
            if len(s) >= 2 and s[0] in "\"'`" and s[-1] in "\"'`":
                return s[1:-1]
            return s
        target_unquoted = _unquote(key_stripped)

        target_idx = None
        for i, entry in enumerate(entries):
            if entry.type == "shorthand_property_identifier":
                if self.parser.node_text(entry) == key_stripped:
                    target_idx = i
                    break
                continue
            # pair node: check its key
            key_node = entry.child_by_field_name("key")
            if key_node is None and entry.named_children:
                key_node = entry.named_children[0]
            if key_node is None:
                continue
            k_text = self.parser.node_text(key_node).strip()
            if k_text == key_stripped or _unquote(k_text) == target_unquoted:
                target_idx = i
                break

        if target_idx is None:
            raise ApplierError(f"Key '{key}' not found in {var_name}")

        target_node = entries[target_idx]
        source_bytes = self.parser.source_bytes
        start = target_node.start_byte
        end = target_node.end_byte

        if target_idx > 0:
            start = entries[target_idx - 1].end_byte
        elif target_idx + 1 < len(entries):
            end = entries[target_idx + 1].start_byte

        new_bytes = source_bytes[:start] + source_bytes[end:]
        self._write_bytes(new_bytes)
        return "Update successful"

    def _find_js_object_literal(self, var_name: str):
        """Find a module-level const/let/var assigned an object literal.
        Handles plain declarations and ones nested inside `export` statements.
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
                        if value is not None and value.type == "object":
                            return value
                elif child.type == "export_statement":
                    result = walk(child)
                    if result is not None:
                        return result
            return None
        return walk(self.parser.tree.root_node)

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
            self.lines = (
                self.lines[:insert_line]
                + [f"{indent}- {value}"]
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
        convention).

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
            # Insert inside the struct braces, after the opening line
            insert_line = struct_node.start_point[0] + 1
            # Infer indent from existing field, or fallback
            indent = ""
            for i in range(insert_line, min(len(self.lines), struct_node.end_point[0])):
                stripped = self.lines[i].strip()
                if stripped and stripped not in ("{", "}"):
                    indent = self._get_indent(self.lines[i])
                    break
            if not indent:
                struct_indent = self._get_indent(self.lines[node.start_point[0]])
                indent = struct_indent + "\t"
            content_lines = self._reindent(content.splitlines(), indent)
            self.lines = self.lines[:insert_line] + content_lines + self.lines[insert_line:]
            return self._save()

        body = node.child_by_field_name("body")
        if body is None:
            raise ApplierError(f"Could not find class body for '{class_target}'")

        if self.parser.ext == ".py":
            insert_line = body.start_point[0]
            indent = self._get_indent(self.lines[insert_line]) if insert_line < len(self.lines) else ""
            if not indent:
                class_indent = self._get_indent(self.lines[node.start_point[0]])
                indent = class_indent + "    "
        elif self.parser.ext == ".rb":
            # Ruby body_statement starts at the first statement inside the class
            insert_line = body.start_point[0]
            indent = self._get_indent(self.lines[insert_line]) if insert_line < len(self.lines) else ""
            if not indent:
                class_indent = self._get_indent(self.lines[node.start_point[0]])
                indent = class_indent + "  "
        else:
            # JS/TS class_body / C++ field_declaration_list: body.start_point[0] is the `{` line
            insert_line = body.start_point[0] + 1
            indent = ""
            for i in range(insert_line, min(len(self.lines), body.end_point[0])):
                stripped = self.lines[i].strip()
                if stripped and stripped not in ("{", "}", "public:", "private:", "protected:"):
                    indent = self._get_indent(self.lines[i])
                    break
            if not indent:
                class_indent = self._get_indent(self.lines[node.start_point[0]])
                indent = class_indent + "    "

        content_lines = self._reindent(content.splitlines(), indent)
        self.lines = self.lines[:insert_line] + content_lines + self.lines[insert_line:]
        return self._save()

    def replace_signature(self, target: str, new_signature: str) -> str:
        """
        Replace only the signature of a function (everything before its body),
        preserving the body. The new_signature should include any trailing
        punctuation expected by the language (e.g. ':' for Python, '(' style
        for JS/C/C++). Decorators are preserved.
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

        source_bytes = self.parser.source_bytes
        new_bytes = (
            source_bytes[: func_node.start_byte]
            + new_signature.encode("utf-8")
            + source_bytes[sig_end:]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

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
                if child.type in func_types:
                    methods.append((get_name(child), child.start_point[0] + 1))
                else:
                    # Descend into sub-containers (e.g. enum_body_declarations)
                    if child.type in ("enum_body_declarations", "class_body", "interface_body"):
                        queue.extend(child.named_children)
            return methods

        lines_out = []
        for child in root.named_children:
            if child.type in class_types:
                name = get_name(child)
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
                lines_out.append(f"{kind} {name} (line {child.start_point[0] + 1})")
                for mname, mline in walk_class_methods(child):
                    lines_out.append(f"  method {name}.{mname} (line {mline})")
            elif child.type in func_types:
                name = get_name(child)
                lines_out.append(f"function {name} (line {child.start_point[0] + 1})")

        if not lines_out:
            return "(no top-level symbols found)"
        return "\n".join(lines_out)

    def get_signature(self, target: str) -> str:
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
                return self.prepend_to_body(target, new_snippet)
            if at_val == "bottom":
                return self.append_to_body(target, new_snippet)
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
        old_bytes = old_snippet.encode("utf-8")
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
        anchor_bytes = anchor_snippet.encode("utf-8")
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

    def prepend_to_body(self, target: str, content: str) -> str:
        """
        Insert content at the top of a function body, preserving existing statements.
        """
        func_node, body = self._get_function_body_node(target)

        if self.parser.ext == ".py":
            # Python: body is a block. First statement determines the indent.
            # Insert before body.start_point[0] (the first statement's line).
            insert_line = body.start_point[0]
            target_indent = (
                self._get_indent(self.lines[insert_line])
                if insert_line < len(self.lines)
                else ""
            )
            if not target_indent:
                sig_indent = self._get_indent(self.lines[func_node.start_point[0]])
                target_indent = sig_indent + "    "
        else:
            # JS/TS/C/C++: body is `{...}`. Insert after the opening brace line.
            insert_line = body.start_point[0] + 1
            target_indent = ""
            for i in range(insert_line, min(len(self.lines), body.end_point[0])):
                stripped = self.lines[i].strip()
                if stripped and stripped not in ("{", "}"):
                    target_indent = self._get_indent(self.lines[i])
                    break
            if not target_indent:
                sig_indent = self._get_indent(self.lines[func_node.start_point[0]])
                target_indent = sig_indent + "  "

        content_lines = self._reindent(content.splitlines(), target_indent)
        self.lines = self.lines[:insert_line] + content_lines + self.lines[insert_line:]
        return self._save()

    def append_to_body(self, target: str, content: str) -> str:
        """
        Insert content at the bottom of a function body, preserving existing statements.
        """
        func_node, body = self._get_function_body_node(target)

        if self.parser.ext == ".py":
            # Python: body is a block. Last statement's end_point gives the last line of body.
            insert_line = body.end_point[0] + 1
            # Infer indent from the last non-blank line of the body
            target_indent = ""
            for i in range(body.end_point[0], body.start_point[0] - 1, -1):
                if 0 <= i < len(self.lines) and self.lines[i].strip():
                    target_indent = self._get_indent(self.lines[i])
                    break
            if not target_indent:
                sig_indent = self._get_indent(self.lines[func_node.start_point[0]])
                target_indent = sig_indent + "    "
        else:
            # JS/TS/C/C++: body is `{...}`. Insert before the closing brace line.
            insert_line = body.end_point[0]
            target_indent = ""
            for i in range(insert_line - 1, body.start_point[0], -1):
                if (
                    0 <= i < len(self.lines)
                    and self.lines[i].strip()
                    and self.lines[i].strip() not in ("{", "}")
                ):
                    target_indent = self._get_indent(self.lines[i])
                    break
            if not target_indent:
                sig_indent = self._get_indent(self.lines[func_node.start_point[0]])
                target_indent = sig_indent + "  "

        content_lines = self._reindent(content.splitlines(), target_indent)
        self.lines = self.lines[:insert_line] + content_lines + self.lines[insert_line:]
        return self._save()

    def insert_before(self, target: str, content: str) -> str:
        """
        Insert content as a sibling immediately before a named symbol (function, class,
        method, or top-level assignment).
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        insert_line = node.start_point[0]
        target_indent = (
            self._get_indent(self.lines[insert_line])
            if insert_line < len(self.lines)
            else ""
        )
        content_lines = self._reindent(content.splitlines(), target_indent)

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

    def insert_after(self, target: str, content: str) -> str:
        """
        Insert content as a sibling immediately after a named symbol (function, class,
        method, or top-level assignment).
        """
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        insert_line = node.end_point[0] + 1
        target_indent = self._get_indent(self.lines[node.start_point[0]])
        content_lines = self._reindent(content.splitlines(), target_indent)

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
            return self.insert_before(target, content)
        if position == "after":
            return self.insert_after(target, content)
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

    def add_dict_entry(self, target: str, key: str, value: str) -> str:
        """
        Add a new key-value pair to a Python dictionary literal at a module-level assignment.
        key and value should be literal source expressions (e.g. key='"foo"', value='42').
        """
        dict_node = self._find_python_literal(target, "dictionary")
        pairs = [c for c in dict_node.named_children if c.type == "pair"]

        source_bytes = self.parser.source_bytes
        if pairs:
            last_pair = pairs[-1]
            indent = self._get_indent(self.lines[last_pair.start_point[0]])
            insertion = f",\n{indent}{key}: {value}"
            insert_byte = last_pair.end_byte
        else:
            close_line = dict_node.end_point[0]
            close_indent = (
                self._get_indent(self.lines[close_line])
                if close_line < len(self.lines)
                else ""
            )
            inner_indent = close_indent + "    "
            insertion = f"\n{inner_indent}{key}: {value},\n{close_indent}"
            insert_byte = dict_node.start_byte + 1  # after `{`

        new_bytes = (
            source_bytes[:insert_byte]
            + insertion.encode("utf-8")
            + source_bytes[insert_byte:]
        )
        self._write_bytes(new_bytes)
        return "Update successful"

    def delete_dict_entry(self, target: str, key: str) -> str:
        """
        Delete a key-value pair from a Python dictionary literal. key should be the
        literal source expression of the key as it appears in source (e.g. '"foo"').
        """
        dict_node = self._find_python_literal(target, "dictionary")
        pairs = [c for c in dict_node.named_children if c.type == "pair"]

        stripped_key = key.strip()
        idx = None
        for i, pair in enumerate(pairs):
            key_node = pair.child_by_field_name("key")
            if key_node is None and pair.named_children:
                key_node = pair.named_children[0]
            if (
                key_node is not None
                and self.parser.node_text(key_node).strip() == stripped_key
            ):
                idx = i
                break
        if idx is None:
            raise ApplierError(f"Key {key} not found in dict '{target}'")

        source_bytes = self.parser.source_bytes
        start = pairs[idx].start_byte
        end = pairs[idx].end_byte
        if idx > 0:
            start = pairs[idx - 1].end_byte
        elif idx + 1 < len(pairs):
            end = pairs[idx + 1].start_byte

        new_bytes = source_bytes[:start] + source_bytes[end:]
        self._write_bytes(new_bytes)
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
        Add a parameter to a function signature. position may be 'end' (default) or
        'start'. parameter should be the literal source text of the new parameter
        (e.g. 'default=None' or 'const int* buf').
        """
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

    def add_comment_before(self, target: str, comment: str) -> str:
        """
        Insert comment line(s) immediately before a named symbol. The comment must
        include its own comment marker (e.g. '# foo' for Python/YAML/TOML, '// foo'
        for JS/C/C++). Existing content is shifted down.
        """
        if not self._comment_prefixes():
            raise ApplierError(f"add_comment_before not supported for {self.parser.ext}")

        node = self._find_symbol_for_comment(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        insert_line = node.start_point[0]
        target_indent = self._get_indent(self.lines[insert_line]) if insert_line < len(self.lines) else ""
        comment_lines = self._reindent(comment.splitlines(), target_indent)
        self.lines = self.lines[:insert_line] + comment_lines + self.lines[insert_line:]
        return self._save()

    def remove_leading_comment(self, target: str) -> str:
        """
        Remove the contiguous block of comment lines immediately above a named symbol.
        Handles both line comments and C-style /* ... */ block comments. Stops at
        the first blank line or non-comment code line.
        """
        if not self._comment_prefixes():
            raise ApplierError(f"remove_leading_comment not supported for {self.parser.ext}")

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

    def replace_leading_comment(self, target: str, new_comment: str) -> str:
        """
        Replace the contiguous leading comment block above a named symbol with
        new_comment. Handles line comments and C-style /* ... */ block comments.
        If no leading comment exists, inserts new_comment.
        """
        if not self._comment_prefixes():
            raise ApplierError(f"replace_leading_comment not supported for {self.parser.ext}")

        node = self._find_symbol_for_comment(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        start_line = node.start_point[0]
        target_indent = self._get_indent(self.lines[start_line]) if start_line < len(self.lines) else ""
        comment_lines = self._reindent(new_comment.splitlines(), target_indent)

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
          - "add"     -> add_comment_before(target, comment)
          - "replace" -> replace_leading_comment(target, comment)
          - "remove"  -> remove_leading_comment(target)
        For "add" and "replace", `comment` must be a non-empty string including
        the language's comment marker (e.g. "# foo", "// bar", "/** ... */").
        For "remove", `comment` is ignored.
        """
        if op == "add":
            if not comment:
                raise ApplierError(
                    "edit_leading_comment: `comment` is required when op='add'"
                )
            return self.add_comment_before(target, comment)
        if op == "replace":
            if not comment:
                raise ApplierError(
                    "edit_leading_comment: `comment` is required when op='replace'"
                )
            return self.replace_leading_comment(target, comment)
        if op == "remove":
            return self.remove_leading_comment(target)
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
            return self.parser.node_text(node)
        if depth == "interface":
            return self.read_interface(target)
        if depth == "signature":
            return self.get_signature(target)
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

    def read_interface(self, target: str) -> str:
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
            raise ApplierError(f"read_interface is not supported for {ext}")

        func_types = self._interface_func_types()

        inner = node
        if node.type == "decorated_definition":
            for c in node.named_children:
                if c.type in ("function_definition", "class_definition"):
                    inner = c
                    break

        # Function target -- return signature only
        if inner.type in func_types:
            return self.get_signature(target)

        # Go: struct/interface definition + top-level receiver methods
        # (checked before body lookup because type_spec has no 'body' field)
        if ext in (".go",) and inner.type == "type_spec":
            return self._read_interface_go(node, inner)

        body = inner.child_by_field_name("body")
        if body is None:
            return self.parser.node_text(node)

        source = self.parser.source_bytes

        # Header: everything from node start up to body content
        if ext in (".py", ".rb"):
            header = source[node.start_byte:body.start_byte].decode("utf-8").rstrip()
        else:
            # Brace-delimited: body node starts with {, include it in header
            header = source[node.start_byte:body.start_byte + 1].decode("utf-8").rstrip()

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

        content_lines = content.splitlines()

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
        Stops at the first blank line or non-comment code line.
        """
        prefixes = self._comment_prefixes()
        if not prefixes:
            return None

        supports_block = self._supports_block_comments()
        i = start_line - 1
        in_block = False

        while i >= 0:
            line = self.lines[i]
            stripped = line.strip()

            if in_block:
                # Inside a multi-line block comment (scanning backwards)
                if "/*" in stripped:
                    # Reached the start of the block
                    in_block = False
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
                # Pure single-line block comment: /* ... */
                if stripped.startswith("/*") and stripped.endswith("*/"):
                    i -= 1
                    continue
                # End of a multi-line block comment
                if stripped.endswith("*/"):
                    in_block = True
                    i -= 1
                    continue

            # Not a comment line -- stop
            break

        first_comment_line = i + 1
        if first_comment_line >= start_line:
            return None
        return (first_comment_line, start_line)

    def _find_symbol_for_comment(self, target: str):
        """
        Resolve a comment target like find_node_by_name, but with a TOML-specific
        fallback: if the target doesn't match a pair, try matching a [table] header.
        Comment tools operate on positional anchors, so tables are valid targets.
        """
        node = self.parser.find_node_by_name(target)
        if node is not None:
            return node

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
