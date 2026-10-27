"""
RmdManager: cell-level editing of .rmd R Markdown documents.

Mirrors notebook-editor's NotebookManager API where possible so agents can
reuse the same mental model. The underlying storage is a .rmd text file
parsed into a Frontmatter + ordered list of Cells via rmd_editor.parser.
"""
from __future__ import annotations

import os
from collections import OrderedDict
from typing import Optional

from rmd_editor.parser import Cell, Frontmatter, FrontmatterError, dump_yaml, parse, serialize, yaml_string, _lines, _with_newline


class RmdManagerError(Exception):
    pass


def create_rmd(
    file_path: str,
    title: str = "",
    author: str = "",
    output_format: str = "html_document",
    overwrite: bool = False,
) -> str:
    """
    Create a new empty .rmd file with a minimal YAML frontmatter. An empty
    title, author or output_format leaves that key out.

    Refuses to overwrite an existing file unless overwrite=True.
    Fails if the parent directory does not exist.
    """
    _validate_path(file_path, must_exist=False)
    if os.path.exists(file_path) and not overwrite:
        raise RmdManagerError(f"File already exists: {file_path}")
    parent = os.path.dirname(file_path) or "."
    if not os.path.isdir(parent):
        raise RmdManagerError(f"Parent directory does not exist: {parent}")
    # Quoted and escaped as YAML, so any string (quotes, backslashes, newlines) stays valid.
    fm_lines = ["---\n"]
    if title:
        fm_lines.append(f"title: {yaml_string(title, quote=True)}\n")
    if author:
        fm_lines.append(f"author: {yaml_string(author, quote=True)}\n")
    if output_format:
        fm_lines.append(f"output: {yaml_string(output_format)}\n")
    fm_lines.append("---\n\n")
    # newline="": LF line breaks on every platform.
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        f.write("".join(fm_lines))
    return "Created"


def _validate_path(file_path: str, *, must_exist: bool = True) -> None:
    if not os.path.isabs(file_path):
        raise RmdManagerError(f"file_path must be absolute: {file_path}")
    if not file_path.lower().endswith(".rmd"):
        raise RmdManagerError(f"File is not a .rmd document: {file_path}")
    if must_exist and not os.path.isfile(file_path):
        raise RmdManagerError(f"File does not exist: {file_path}")


def _check_timeout(timeout: float) -> None:
    """Reject a timeout that is not a positive number of seconds; 0 does not mean "no limit"."""
    if not timeout > 0:
        raise RmdManagerError(f"timeout must be a positive number of seconds, got {timeout}")


class RmdManager:
    """
    Open, edit, and save a .rmd file. Mutations are written to disk on each
    successful operation. Parse state is rebuilt per-instance; create a new
    RmdManager after any external edit. Cell sources use "\\n" line breaks
    whatever the file uses; saving keeps the file's own, and a UTF-8 byte order
    mark the file starts with (see parser). Line counts, split offsets and line
    numbers all split lines as the parser does.
    """

    def __init__(self, file_path: str):
        _validate_path(file_path, must_exist=True)
        self.filepath = file_path
        # newline="": line breaks arrive as written, so _save can keep the file's own.
        with open(file_path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        self.frontmatter, self.cells = parse(text)

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _save(self) -> str:
        text = serialize(self.frontmatter, self.cells)
        # Written as serialized: edited parts already use the document's line break.
        with open(self.filepath, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return "Saved"

    def _validate_index(self, index: int, *, allow_end: bool = False) -> int:
        n = len(self.cells)
        if allow_end and index == n:
            return n
        if index == -1 and n > 0:
            return n - 1
        if n == 0:
            raise RmdManagerError(f"Cell index {index} out of range: the document has no cells")
        if index < 0 or index >= n:
            raise RmdManagerError(f"Cell index {index} out of range (0..{n-1})")
        return index

    def _require_code_cell(self, index: int) -> Cell:
        idx = self._validate_index(index)
        cell = self.cells[idx]
        if cell.cell_type != "code":
            raise RmdManagerError(f"Cell {index} is a markdown cell, not a code chunk")
        return cell

    # ──────────────────────────────────────────────
    # Cell structure & navigation
    # ──────────────────────────────────────────────

    def list_cells(self) -> str:
        if not self.cells:
            return "(document has no cells)"
        lines = []
        for i, cell in enumerate(self.cells):
            # Lines as the parser splits them, so counts match split_cell and find_in_rmd.
            line_count = len(_lines(cell.source))
            stripped = cell.source.strip()
            preview = _lines(stripped)[0].rstrip("\r\n") if stripped else ""
            if len(preview) > 60:
                preview = preview[:57] + "..."
            if cell.cell_type == "code":
                meta = f"{cell.language}"
                if cell.label:
                    meta += f" label={cell.label}"
                if cell.options:
                    meta += f" opts={len(cell.options)}"
                lines.append(f"[{i}] code ({meta}) {line_count}L  {preview}")
            else:
                lines.append(f"[{i}] markdown {line_count}L  {preview}")
        return "\n".join(lines)

    def get_cell(self, index: int) -> str:
        idx = self._validate_index(index)
        return self.cells[idx].source

    def add_cell(self, index: int, source: str = "", cell_type: str = "code") -> str:
        if cell_type not in ("code", "markdown"):
            raise RmdManagerError(f"Unknown cell_type: {cell_type!r}")
        n = len(self.cells)
        if index == -1:
            insert_at = n
        else:
            insert_at = self._validate_index(index, allow_end=True)
        new_cell = Cell(cell_type=cell_type, source=_with_newline(source, "\n"))
        new_cell.mark_dirty()
        self.cells.insert(insert_at, new_cell)
        return self._save()

    def delete_cell(self, index: int) -> str:
        idx = self._validate_index(index)
        del self.cells[idx]
        return self._save()

    def move_cell(self, from_index: int, to_index: int) -> str:
        src = self._validate_index(from_index)
        n = len(self.cells)
        if to_index == -1:
            dst = n - 1
        else:
            dst = self._validate_index(to_index)
        cell = self.cells.pop(src)
        self.cells.insert(dst, cell)
        return self._save()

    def split_cell(self, index: int, line_offset: int) -> str:
        idx = self._validate_index(index)
        cell = self.cells[idx]
        # Only a line break ends a line, as list_cells counts them: a form feed or U+2028 stays inside one.
        lines = _lines(cell.source)
        if line_offset < 1 or line_offset >= len(lines):
            raise RmdManagerError(
                f"line_offset {line_offset} out of range (1..{len(lines)-1}) for cell with {len(lines)} line(s)"
            )
        first_src = "".join(lines[:line_offset])
        second_src = "".join(lines[line_offset:])
        # Strip a trailing newline from the first half so the chunk fence sits on its own line
        if cell.cell_type == "code" and first_src.endswith("\n"):
            first_src = first_src[:-1]
        cell.source = first_src
        cell.mark_dirty()
        new_cell = Cell(cell_type=cell.cell_type, source=second_src)
        if cell.cell_type == "code":
            new_cell.language = cell.language
        new_cell.mark_dirty()
        self.cells.insert(idx + 1, new_cell)
        return self._save()

    def merge_cells(self, start_index: int, end_index: int) -> str:
        s = self._validate_index(start_index)
        e = self._validate_index(end_index)
        if e <= s:
            raise RmdManagerError(f"end_index ({end_index}) must be greater than start_index ({start_index})")
        base = self.cells[s]
        parts: list[str] = [base.source]
        for k in range(s + 1, e + 1):
            c = self.cells[k]
            if c.cell_type != base.cell_type:
                raise RmdManagerError(
                    f"Cannot merge cells of different types: cell {s} is {base.cell_type}, cell {k} is {c.cell_type}"
                )
            if base.cell_type == "code" and c.language != base.language:
                raise RmdManagerError(
                    f"Cannot merge code chunks with different languages: cell {s} is {base.language}, cell {k} is {c.language}"
                )
            parts.append(c.source)
        sep = "\n" if base.cell_type == "code" else ""
        base.source = sep.join(parts) if base.cell_type == "code" else "".join(parts)
        base.mark_dirty()
        del self.cells[s + 1:e + 1]
        return self._save()

    # ──────────────────────────────────────────────
    # Cell content editing
    # ──────────────────────────────────────────────

    def replace_cell_source(self, index: int, new_source: str) -> str:
        idx = self._validate_index(index)
        cell = self.cells[idx]
        cell.source = _with_newline(new_source, "\n")
        cell.mark_dirty()
        return self._save()

    def prepend_to_cell(self, index: int, source: str) -> str:
        idx = self._validate_index(index)
        cell = self.cells[idx]
        # As "\n" text, so the separator check sees "\r\n" and "\r" breaks too.
        source = _with_newline(source, "\n")
        sep = "" if cell.source.startswith("\n") or not source or source.endswith("\n") else "\n"
        cell.source = source + sep + cell.source
        cell.mark_dirty()
        return self._save()

    def append_to_cell(self, index: int, source: str) -> str:
        idx = self._validate_index(index)
        cell = self.cells[idx]
        # As "\n" text, so the separator check sees "\r\n" and "\r" breaks too.
        source = _with_newline(source, "\n")
        sep = "" if cell.source.endswith("\n") or not cell.source or source.startswith("\n") else "\n"
        cell.source = cell.source + sep + source
        cell.mark_dirty()
        return self._save()

    # ──────────────────────────────────────────────
    # Chunk options
    # ──────────────────────────────────────────────

    def get_chunk_options(self, index: int) -> str:
        cell = self._require_code_cell(index)
        lines = [f"language: {cell.language}"]
        if cell.label:
            lines.append(f"label: {cell.label}")
        else:
            lines.append("label: (none)")
        if not cell.options:
            lines.append("options: (none)")
        else:
            for k, v in cell.options.items():
                lines.append(f"  {k}={v}" if v != "" else f"  {k}")
        return "\n".join(lines)

    def set_chunk_option(self, index: int, key: str, value: str) -> str:
        cell = self._require_code_cell(index)
        key = key.strip()
        if not key:
            raise RmdManagerError("Option key must not be empty")
        if key == "label":
            cell.label = value.strip() or None
        else:
            cell.options[key] = value
        cell.mark_dirty()
        return self._save()

    def remove_chunk_option(self, index: int, key: str) -> str:
        cell = self._require_code_cell(index)
        key = key.strip()
        if key == "label":
            if cell.label is None:
                raise RmdManagerError(f"Cell {index} has no label to remove")
            cell.label = None
        else:
            if key not in cell.options:
                raise RmdManagerError(f"Cell {index} has no option {key!r}")
            del cell.options[key]
        cell.mark_dirty()
        return self._save()

    # ──────────────────────────────────────────────
    # YAML frontmatter
    # ──────────────────────────────────────────────

    def get_frontmatter(self) -> str:
        fm = self.frontmatter
        if not fm.present:
            return "(no frontmatter)"
        if fm.error is not None:
            return f"(the YAML header could not be parsed: {fm.error}; its raw text follows)\n{fm.text()}".rstrip("\n")
        if not fm.data:
            return "(empty frontmatter)"
        return dump_yaml(fm.data).rstrip("\n")

    def set_frontmatter_key(self, key: str, value: str) -> str:
        key = key.strip()
        if not key:
            raise RmdManagerError("Frontmatter key must not be empty")
        had_header = self.frontmatter.present
        try:
            # Rewrites only this key's lines; the rest of the header is kept byte for byte.
            self.frontmatter.set_key(key, value)
        except FrontmatterError as e:
            raise RmdManagerError(str(e)) from e
        if not had_header:
            # A new header gets a blank line before the body, as create_rmd writes it.
            newline = self.frontmatter.newline
            body = serialize(Frontmatter(newline=newline), self.cells)
            if body and not body.startswith(("\n", "\r")):
                self.frontmatter.raw += newline
        return self._save()

    def remove_frontmatter_key(self, key: str) -> str:
        try:
            self.frontmatter.remove_key(key.strip())
        except FrontmatterError as e:
            raise RmdManagerError(str(e)) from e
        return self._save()

    # ──────────────────────────────────────────────
    # Discovery (read-only)
    # ──────────────────────────────────────────────

    def find_in_rmd(self, pattern: str) -> str:
        if not pattern:
            return "(empty pattern)"
        hits: list[str] = []
        for i, cell in enumerate(self.cells):
            # Numbered as list_cells counts lines and split_cell takes offsets.
            for ln, line in enumerate(_lines(cell.source), start=1):
                line = line.rstrip("\r\n")
                if pattern in line:
                    hits.append(f"cell[{i}] line {ln}: {line}")
        if not hits:
            return "(no matches)"
        return "\n".join(hits)

    # ──────────────────────────────────────────────
    # Kernel execution (returns outputs INLINE — never persisted to the .rmd)
    # ──────────────────────────────────────────────

    def execute_cell(self, index: int, timeout: float = 60.0) -> str:
        """
        Execute one code chunk and return captured outputs as a formatted
        string. Outputs are NOT written to the file (R Markdown regenerates
        them on render). Markdown cells are rejected. Non-R chunks are
        executed via the kernel whose name matches the chunk language (python,
        julia, etc.) only if a matching Jupyter kernelspec is installed; the
        default kernel per-file is driven by the first executed chunk's
        language.
        """
        from rmd_editor import kernel as _kernel
        _check_timeout(timeout)
        cell = self._require_code_cell(index)
        kernel_name = _language_to_kernel_name(cell.language)
        try:
            sess = _kernel.get_or_start_kernel(self.filepath, kernel_name=kernel_name)
        except _kernel.KernelError as e:
            raise RmdManagerError(str(e)) from e
        try:
            outputs = sess.execute(cell.source, timeout=timeout)
        except _kernel.KernelError as e:
            raise RmdManagerError(f"Execution failed: {e}") from e
        return _kernel.format_outputs(outputs)

    def execute_all_cells(self, timeout: float = 60.0, stop_on_error: bool = True) -> str:
        """
        Execute all code chunks in order. Outputs are returned inline, not
        persisted. Returns a cell-by-cell transcript.
        """
        from rmd_editor import kernel as _kernel
        _check_timeout(timeout)
        transcript: list[str] = []
        executed = 0
        errored = 0
        stopped_at: Optional[int] = None
        for i, cell in enumerate(self.cells):
            if cell.cell_type != "code":
                continue
            if not cell.source.strip():
                continue
            kernel_name = _language_to_kernel_name(cell.language)
            try:
                sess = _kernel.get_or_start_kernel(self.filepath, kernel_name=kernel_name)
            except _kernel.KernelError as e:
                raise RmdManagerError(str(e)) from e
            try:
                outputs = sess.execute(cell.source, timeout=timeout)
            except _kernel.KernelError as e:
                raise RmdManagerError(f"Execution failed at cell {i}: {e}") from e
            executed += 1
            transcript.append(f"── cell[{i}] ──\n{_kernel.format_outputs(outputs)}")
            if any(o.get("output_type") == "error" for o in outputs):
                errored += 1
                if stop_on_error:
                    stopped_at = i
                    break
        header = f"Executed {executed} cell(s), {errored} error(s)"
        if stopped_at is not None:
            header += f", stopped at cell {stopped_at}"
        return header + "\n\n" + "\n\n".join(transcript)


def _language_to_kernel_name(lang: str) -> str:
    """Map .rmd chunk language identifiers to Jupyter kernelspec names."""
    lang = lang.lower()
    if lang == "julia":
        # IJulia installs versioned kernelspecs (julia-1.11), so look up the installed one.
        from rmd_editor import kernel as _kernel
        return _kernel.julia_kernel_name()
    mapping = {
        "r": "ir",
        "python": "python3",
    }
    return mapping.get(lang, lang)
