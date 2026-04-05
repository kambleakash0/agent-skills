"""
NotebookManager -- cell-level operations for Jupyter .ipynb files.

Uses nbformat for schema-safe read/write and Python's stdlib `ast` module for
lightweight symbol extraction within code cells (no tree-sitter dependency).
"""
import ast as pyast
import json as _json
import os
from typing import Any

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_raw_cell


class NotebookManagerError(Exception):
    """Raised for user-facing errors: invalid index, wrong cell type, schema errors."""
    pass


class NotebookManager:
    def __init__(self, filepath: str):
        self.filepath = filepath
        if not os.path.isfile(filepath):
            raise NotebookManagerError(f"File not found: {filepath}")
        try:
            self.nb = nbformat.read(filepath, as_version=4)
        except Exception as e:
            raise NotebookManagerError(f"Failed to read notebook: {e}") from e

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _save(self) -> str:
        nbformat.write(self.nb, self.filepath)
        return "Update successful"

    def _validate_index(self, index: int, *, allow_end: bool = False) -> int:
        n = len(self.nb.cells)
        limit = n if allow_end else n - 1
        if index < 0 or index > limit:
            raise NotebookManagerError(
                f"Cell index {index} out of range (notebook has {n} cells)"
            )
        return index

    def _cell_source_as_string(self, cell) -> str:
        """nbformat normalizes source to a string on read, but handle list just in case."""
        src = cell.source
        if isinstance(src, list):
            return "".join(src)
        return src or ""

    def _new_cell(self, cell_type: str, source: str):
        if cell_type == "code":
            return new_code_cell(source=source)
        if cell_type == "markdown":
            return new_markdown_cell(source=source)
        if cell_type == "raw":
            return new_raw_cell(source=source)
        raise NotebookManagerError(
            f"Invalid cell_type '{cell_type}' (must be 'code', 'markdown', or 'raw')"
        )

    # ──────────────────────────────────────────────
    # Cell structure & navigation
    # ──────────────────────────────────────────────

    def list_cells(self) -> str:
        """Return a formatted outline of all cells: index, type, line count, preview."""
        if not self.nb.cells:
            return "(notebook has no cells)"
        lines = []
        for i, cell in enumerate(self.nb.cells):
            src = self._cell_source_as_string(cell)
            line_count = src.count("\n") + (1 if src and not src.endswith("\n") else 0)
            first_line = src.split("\n", 1)[0] if src else ""
            preview = first_line[:60] + ("..." if len(first_line) > 60 else "")
            exec_count = ""
            if cell.cell_type == "code" and cell.get("execution_count") is not None:
                exec_count = f" [exec {cell.execution_count}]"
            lines.append(f"[{i}] {cell.cell_type:8} ({line_count} lines){exec_count}  {preview!r}")
        return "\n".join(lines)

    def get_cell(self, index: int) -> str:
        """Return the source text of a cell."""
        self._validate_index(index)
        return self._cell_source_as_string(self.nb.cells[index])

    def add_cell(self, index: int, source: str = "", cell_type: str = "code") -> str:
        """
        Insert a new cell at the given index, shifting existing cells down.
        Default cell_type is 'code'. Use -1 or len(cells) to append at the end.
        """
        n = len(self.nb.cells)
        if index == -1:
            index = n
        self._validate_index(index, allow_end=True)
        cell = self._new_cell(cell_type, source)
        self.nb.cells.insert(index, cell)
        return self._save()

    def delete_cell(self, index: int) -> str:
        """Remove the cell at the given index."""
        self._validate_index(index)
        del self.nb.cells[index]
        return self._save()

    def move_cell(self, from_index: int, to_index: int) -> str:
        """Move a cell from one index to another. Other cells shift to accommodate."""
        self._validate_index(from_index)
        self._validate_index(to_index)
        cell = self.nb.cells.pop(from_index)
        self.nb.cells.insert(to_index, cell)
        return self._save()

    def split_cell(self, index: int, line_offset: int) -> str:
        """
        Split a cell at a line boundary. The original cell keeps lines [0:line_offset],
        and a new cell (of the same type) is inserted immediately after with the rest.
        Outputs and execution_count on the new cell are cleared since they would be stale.
        """
        self._validate_index(index)
        cell = self.nb.cells[index]
        src = self._cell_source_as_string(cell)
        lines = src.split("\n")
        if line_offset < 0 or line_offset > len(lines):
            raise NotebookManagerError(
                f"line_offset {line_offset} out of range (cell has {len(lines)} lines)"
            )
        first_part = "\n".join(lines[:line_offset])
        second_part = "\n".join(lines[line_offset:])
        cell.source = first_part
        # Clear outputs/execution on the first part since they no longer match the code
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
        new_cell = self._new_cell(cell.cell_type, second_part)
        self.nb.cells.insert(index + 1, new_cell)
        return self._save()

    def merge_cells(self, start_index: int, end_index: int) -> str:
        """
        Merge consecutive cells [start_index..end_index] (inclusive) into one.
        All cells in the range must be the same cell_type. Outputs are cleared
        on the merged result since they would be stale.
        """
        self._validate_index(start_index)
        self._validate_index(end_index)
        if start_index >= end_index:
            raise NotebookManagerError(
                "merge_cells requires end_index > start_index (at least two cells)"
            )
        cells_to_merge = self.nb.cells[start_index : end_index + 1]
        cell_type = cells_to_merge[0].cell_type
        for c in cells_to_merge:
            if c.cell_type != cell_type:
                raise NotebookManagerError(
                    f"Cannot merge cells of different types ({cell_type} vs {c.cell_type})"
                )
        merged_source = "\n".join(self._cell_source_as_string(c) for c in cells_to_merge)
        merged_cell = self._new_cell(cell_type, merged_source)
        self.nb.cells[start_index : end_index + 1] = [merged_cell]
        return self._save()

    # ──────────────────────────────────────────────
    # Cell content editing
    # ──────────────────────────────────────────────

    def replace_cell_source(self, index: int, new_source: str) -> str:
        """Replace the entire source of a cell. Clears outputs if it's a code cell."""
        self._validate_index(index)
        cell = self.nb.cells[index]
        cell.source = new_source
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
        return self._save()

    def prepend_to_cell(self, index: int, source: str) -> str:
        """Prepend source text to the top of a cell. Clears outputs if code cell."""
        self._validate_index(index)
        cell = self.nb.cells[index]
        existing = self._cell_source_as_string(cell)
        sep = "" if source.endswith("\n") or not existing else "\n"
        cell.source = source + sep + existing
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
        return self._save()

    def append_to_cell(self, index: int, source: str) -> str:
        """Append source text to the bottom of a cell. Clears outputs if code cell."""
        self._validate_index(index)
        cell = self.nb.cells[index]
        existing = self._cell_source_as_string(cell)
        sep = "" if existing.endswith("\n") or not existing else "\n"
        cell.source = existing + sep + source
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
        return self._save()

    # ──────────────────────────────────────────────
    # Outputs & metadata
    # ──────────────────────────────────────────────

    def clear_outputs(self, index: int | None = None) -> str:
        """
        Clear outputs of a specific code cell, or of all code cells if index is None.
        Does not touch markdown/raw cells.
        """
        if index is None:
            for cell in self.nb.cells:
                if cell.cell_type == "code":
                    cell.outputs = []
                    cell.execution_count = None
            return self._save()
        self._validate_index(index)
        cell = self.nb.cells[index]
        if cell.cell_type != "code":
            raise NotebookManagerError(
                f"Cell at index {index} is a {cell.cell_type} cell -- only code cells have outputs"
            )
        cell.outputs = []
        cell.execution_count = None
        return self._save()

    def clear_execution_counts(self) -> str:
        """Reset execution_count to None on all code cells (outputs preserved)."""
        for cell in self.nb.cells:
            if cell.cell_type == "code":
                cell.execution_count = None
        return self._save()

    def get_outputs(self, index: int) -> str:
        """
        Return a formatted text representation of a cell's outputs. Handles stream,
        execute_result, display_data, and error output types.
        """
        self._validate_index(index)
        cell = self.nb.cells[index]
        if cell.cell_type != "code":
            return f"(cell at index {index} is a {cell.cell_type} cell -- no outputs)"
        outputs = cell.get("outputs", [])
        if not outputs:
            return "(no outputs)"
        lines = []
        for out in outputs:
            otype = out.get("output_type", "unknown")
            if otype == "stream":
                name = out.get("name", "stdout")
                text = out.get("text", "")
                if isinstance(text, list):
                    text = "".join(text)
                lines.append(f"[stream {name}]\n{text.rstrip()}")
            elif otype == "execute_result":
                data = out.get("data", {})
                text_plain = data.get("text/plain", "")
                if isinstance(text_plain, list):
                    text_plain = "".join(text_plain)
                ec = out.get("execution_count", "?")
                lines.append(f"[execute_result {ec}]\n{text_plain.rstrip()}")
            elif otype == "display_data":
                data = out.get("data", {})
                text_plain = data.get("text/plain", "")
                if isinstance(text_plain, list):
                    text_plain = "".join(text_plain)
                mime_types = ", ".join(data.keys())
                lines.append(f"[display_data mime: {mime_types}]\n{text_plain.rstrip()}")
            elif otype == "error":
                ename = out.get("ename", "Error")
                evalue = out.get("evalue", "")
                tb = out.get("traceback", [])
                if isinstance(tb, list):
                    tb_text = "\n".join(tb)
                else:
                    tb_text = str(tb)
                lines.append(f"[error] {ename}: {evalue}\n{tb_text}")
            else:
                lines.append(f"[{otype}] (unrecognized output type)")
        return "\n\n".join(lines)

    def set_cell_metadata(self, index: int, key: str, value: str) -> str:
        """
        Set a metadata key on a cell. value is parsed as JSON if possible (so you
        can set booleans, numbers, nested objects). Falls back to storing as string.
        Example: set_cell_metadata(0, "collapsed", "true")
        """
        self._validate_index(index)
        cell = self.nb.cells[index]
        try:
            parsed = _json.loads(value)
        except _json.JSONDecodeError:
            parsed = value
        if "metadata" not in cell:
            cell.metadata = {}
        cell.metadata[key] = parsed
        return self._save()

    # ──────────────────────────────────────────────
    # Discovery (read-only)
    # ──────────────────────────────────────────────

    def list_notebook_symbols(self) -> str:
        """
        Walk all code cells and list Python symbols (functions, classes, methods)
        with the cell index and line number. Uses the stdlib `ast` module so works
        only for Python code cells. Cells with syntax errors are reported but skipped.
        """
        lines_out: list[str] = []
        for i, cell in enumerate(self.nb.cells):
            if cell.cell_type != "code":
                continue
            src = self._cell_source_as_string(cell)
            if not src.strip():
                continue
            try:
                tree = pyast.parse(src)
            except SyntaxError as e:
                lines_out.append(f"cell[{i}]: <syntax error at line {e.lineno}: {e.msg}>")
                continue
            for node in tree.body:
                if isinstance(node, pyast.FunctionDef) or isinstance(node, pyast.AsyncFunctionDef):
                    lines_out.append(f"cell[{i}] function {node.name} (line {node.lineno})")
                elif isinstance(node, pyast.ClassDef):
                    lines_out.append(f"cell[{i}] class {node.name} (line {node.lineno})")
                    for sub in node.body:
                        if isinstance(sub, (pyast.FunctionDef, pyast.AsyncFunctionDef)):
                            lines_out.append(
                                f"cell[{i}]   method {node.name}.{sub.name} (line {sub.lineno})"
                            )
                elif isinstance(node, pyast.Assign):
                    # Top-level assignments: show target names if simple
                    for tgt in node.targets:
                        if isinstance(tgt, pyast.Name):
                            lines_out.append(f"cell[{i}] variable {tgt.id} (line {node.lineno})")
                elif isinstance(node, pyast.Import):
                    for alias in node.names:
                        lines_out.append(f"cell[{i}] import {alias.name} (line {node.lineno})")
                elif isinstance(node, pyast.ImportFrom):
                    mod = node.module or ""
                    names = ", ".join(a.name for a in node.names)
                    lines_out.append(f"cell[{i}] import from {mod}: {names} (line {node.lineno})")
        if not lines_out:
            return "(no symbols found in code cells)"
        return "\n".join(lines_out)

    def find_in_notebook(self, pattern: str) -> str:
        """
        Text search across all cell sources. Returns matches as `cell[i] line N: <text>`.
        Case-sensitive substring match -- no regex.
        """
        if not pattern:
            return "(empty pattern)"
        results: list[str] = []
        for i, cell in enumerate(self.nb.cells):
            src = self._cell_source_as_string(cell)
            for ln_idx, line in enumerate(src.split("\n")):
                if pattern in line:
                    results.append(f"cell[{i}] line {ln_idx + 1} ({cell.cell_type}): {line.strip()}")
        if not results:
            return f"(pattern {pattern!r} not found)"
        return "\n".join(results)

    def execute_cell(self, index: int, timeout: float = 60.0) -> str:
        """
        Execute a single code cell using the notebook's Python kernel. Updates the
        cell's outputs and execution_count with the results, then saves the notebook.
        Non-code cells are rejected.
        """
        from notebook_editor import kernel as _kernel
        self._validate_index(index)
        cell = self.nb.cells[index]
        if cell.cell_type != "code":
            raise NotebookManagerError(
                f"Cell at index {index} is a {cell.cell_type} cell -- cannot execute"
            )
        code = self._cell_source_as_string(cell)
        sess = _kernel.get_or_start_kernel(self.filepath)
        try:
            outputs, exec_count = sess.execute(code, timeout=timeout)
        except _kernel.KernelError as e:
            raise NotebookManagerError(f"Execution failed: {e}") from e
        cell.outputs = outputs
        cell.execution_count = exec_count
        return self._save()

    def execute_all_cells(self, timeout: float = 60.0, stop_on_error: bool = True) -> str:
        """
        Execute all code cells in order, updating outputs and execution_count on each.
        Non-code cells are skipped. If stop_on_error is True, execution stops at the
        first cell that raises an error. Returns a summary string.
        """
        from notebook_editor import kernel as _kernel
        sess = _kernel.get_or_start_kernel(self.filepath)
        executed = 0
        errored = 0
        stopped_at: int | None = None
        for i, cell in enumerate(self.nb.cells):
            if cell.cell_type != "code":
                continue
            code = self._cell_source_as_string(cell)
            if not code.strip():
                continue
            try:
                outputs, exec_count = sess.execute(code, timeout=timeout)
            except _kernel.KernelError as e:
                raise NotebookManagerError(f"Execution failed at cell {i}: {e}") from e
            cell.outputs = outputs
            cell.execution_count = exec_count
            executed += 1
            # Did the cell error out?
            has_error = any(o.get("output_type") == "error" for o in outputs)
            if has_error:
                errored += 1
                if stop_on_error:
                    stopped_at = i
                    break
        self._save()
        summary_parts = [f"Executed {executed} cells"]
        if errored:
            summary_parts.append(f"{errored} errored")
        if stopped_at is not None:
            summary_parts.append(f"stopped at cell {stopped_at}")
        return ", ".join(summary_parts)
