import os
from ast_editor.parser import TreeSitterParser

class ApplierError(Exception): pass

class Applier:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.parser = TreeSitterParser(filepath)
        
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
                result.append(target_indent + line[len(old_indent):])
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
            
        # Optional: Reindent multiline config values (like nested JSON objects)
        content_lines = content.splitlines()
        if len(content_lines) > 1:
            key_indent = self._get_indent(self.lines[node.start_point[0]])
            # For nested objects, we might want it indented one level deeper, but we'll trust the LLM's spacing or align it to the key.
            # To be safe, mostly rely on the passed content for configs.
            pass
            
        source_bytes = self.parser.source_code.encode('utf-8')
        content_bytes = content.encode('utf-8')
        
        new_bytes = source_bytes[:node.start_byte] + content_bytes + source_bytes[node.end_byte:]
        new_source = new_bytes.decode('utf-8')
        
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(new_source)
            
        # sync state
        self.parser.source_code = new_source
        self.lines = new_source.splitlines()
        return "Update successful"

    def replace_function_body(self, target: str, content: str) -> str:
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found in {self.filepath}")

        # If node is a decorated_definition, drill into the inner function for the body block
        func_node = node
        if node.type == "decorated_definition":
            for child in node.named_children:
                if child.type == "function_definition":
                    func_node = child
                    break

        block_node = None
        for child in func_node.children:
            if child.type in ("block", "statement_block"):
                block_node = child
                break
        
        if not block_node:
            raise ApplierError(f"Could not find body block for target '{target}'")

        if self.parser.ext == ".py":
            start_line = block_node.start_point[0]
            end_line = block_node.end_point[0] + 1
        else:
            start_line = block_node.start_point[0] + 1
            end_line = block_node.end_point[0]
            if start_line > end_line:
                start_line = block_node.start_point[0]
                end_line = start_line + 1

        target_indent = self._get_indent(self.lines[start_line]) if start_line < len(self.lines) else ""
        if not target_indent and start_line < len(self.lines) and self.lines[start_line].strip() == "":
             sig_indent = self._get_indent(self.lines[node.start_point[0]])
             target_indent = sig_indent + ("    " if self.parser.ext == ".py" else "  ")

        content_lines = self._reindent(content.splitlines(), target_indent)

        self.lines = self.lines[:start_line] + content_lines + self.lines[end_line:]
        return self._save()

    def add_method(self, class_target: str, content: str) -> str:
        node = self.parser.find_node_by_name(class_target)
        if not node:
            raise ApplierError(f"Target class '{class_target}' not found")
        
        if self.parser.ext != ".py":
             insert_line = node.end_point[0]
             indent = self._get_indent(self.lines[node.start_point[0]]) + "  "
        else:
             insert_line = node.end_point[0] + 1
             indent = self._get_indent(self.lines[node.start_point[0]]) + "    "

        content_lines = self._reindent(content.splitlines(), indent)
        if self.parser.ext != ".py":
            self.lines = self.lines[:insert_line] + [""] + content_lines + [""] + self.lines[insert_line:]
        else:
            self.lines = self.lines[:insert_line] + [""] + content_lines + self.lines[insert_line:]
        return self._save()
        
    def delete_node(self, target: str) -> str:
        node = self.parser.find_node_by_name(target)
        if not node:
            raise ApplierError(f"Target '{target}' not found")
            
        start_line = node.start_point[0]
        end_line = node.end_point[0] + 1
        
        self.lines = self.lines[:start_line] + self.lines[end_line:]
        return self._save()

    def _save(self) -> str:
        new_source = "\n".join(self.lines)
        if not new_source.endswith("\n"):
            new_source += "\n"
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(new_source)
        return "Update successful"
