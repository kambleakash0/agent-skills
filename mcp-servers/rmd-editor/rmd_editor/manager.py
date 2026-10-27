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

from rmd_editor.parser import (
    Cell, Frontmatter, FrontmatterError, dump_yaml, parse, serialize, yaml_string,
    _KNITR_CHUNK_BEGIN, _KNITR_CHUNK_END, _chunk_body, _chunk_source, _closed, _join, _layout, _lines, _pipe_labels,
    _r_string_value, _r_trouble, _read_chunk_header, _render_chunk_header, _with_newline,
)


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


def _check_header_text(what: str, text: str) -> None:
    """
    Reject text for a chunk header (what names it, e.g. "Chunk label") that would
    split the header's line or swallow the options written after it. knitr reads
    keys and values as R code, so in those a backtick, # or second = counts too;
    it quotes the label itself.
    """
    if "\n" in text or "\r" in text:
        hint = ": inside an R string, write it as \\n" if what == "Chunk option value" else ""
        raise RmdManagerError(f"{what} {text!r} contains a line break, but a chunk header is a single line{hint}")
    trouble = None if what == "Chunk label" else _r_trouble(text)
    if trouble == "`" or not _closed(text):
        raise RmdManagerError(
            f"{what} {text!r} has an unmatched bracket or quote, which would swallow the options after it in the chunk header"
        )
    if trouble == "#":
        raise RmdManagerError(
            f"{what} {text!r} has a # outside a quoted string, which R reads as a comment running to the end of the chunk header"
        )
    # In a key, any = makes the header read back as other options, which _set_header reports.
    if trouble == "=" and what == "Chunk option value":
        raise RmdManagerError(
            f"{what} {text!r} has an = outside a quoted string or brackets, which knitr can't read after key=: "
            "write text as a quoted R string"
        )


def _check_chunk_text(text: str) -> None:
    """Reject new chunk text with a line knitr would read as the chunk's closing fence."""
    for number, line in enumerate(_lines(text), start=1):
        line = line.rstrip("\n")
        if _KNITR_CHUNK_END.match(line):
            raise RmdManagerError(
                f"Line {number} of the new text, {line!r}, is a closing fence for knitr (backticks alone on a line, "
                "after nothing but spaces, tabs or >), which would end the chunk there"
            )


def _check_prose_text(text: str) -> None:
    """
    Reject new prose with a line this parser or knitr would read as a chunk's
    opening fence, which would make the prose after it chunk code.
    """
    for number, line in enumerate(_lines(text), start=1):
        line = line.rstrip("\n")
        if _read_chunk_header(line) or _KNITR_CHUNK_BEGIN.match(line):
            raise RmdManagerError(
                f"Line {number} of the new text, {line!r}, opens a code chunk (backticks, then {{engine}} or "
                "{engine options}), which would make the prose after it chunk code: add a chunk with "
                "add_cell(cell_type=\"code\"), or put `r ''` before the backticks to show the line as text"
            )


def _describe(shape: tuple) -> str:
    """A cell as parser._layout gives it, in a few words for an error message."""
    lines = _lines(shape[-1])
    size = f"{len(lines)} line" + ("" if len(lines) == 1 else "s")
    start = f" starting {lines[0].rstrip(chr(10))[:30]!r}" if lines else ""
    if shape[0] == "markdown":
        return f"markdown of {size}{start}"
    return f"a {shape[1]} chunk of {size}{start}" if lines else f"an empty {shape[1]} chunk"


def _read_back_problem(frontmatter: Frontmatter, cells: list[Cell], text: str) -> Optional[str]:
    """
    Why text, written for the given header and cells, reads back as another
    document (see parser._layout), or None if it reads back as them.
    """
    read_frontmatter, read_cells = parse(text)
    (header, want), (read_header, got) = _layout(frontmatter, cells), _layout(read_frontmatter, read_cells)
    if header is None and read_header is not None:
        return (
            f"Saving would make lines 1 to {len(_lines(read_frontmatter.raw))} of the file read back as the YAML header "
            "(a --- line at the top and the next --- line enclose it), so the file was left unchanged: start the first "
            "cell with something other than a --- line, and set header keys with set_frontmatter_key"
        )
    if header != read_header:
        return "Saving would change how the YAML header reads back, so the file was left unchanged"
    if [shape for _, shape in want] == [shape for _, shape in got]:
        return None
    at = next((p for p, (a, b) in enumerate(zip(want, got)) if a[1] != b[1]), min(len(want), len(got)))
    index = want[at][0] if at < len(want) else len(cells)
    expected = _describe(want[at][1]) if at < len(want) else "nothing (the end of the document)"
    found = _describe(got[at][1]) if at < len(got) else "nothing (the end of the document)"
    return (
        f"Saving would change the document's cells, so the file was left unchanged: read back, cell {index} would be "
        f"{found} instead of {expected}. A line that opens or closes a chunk (such as ```{{r}} or ```) in the prose "
        "next to the edit does this"
    )


def _label_spellings(cell: Cell) -> list[tuple[str, str, str]]:
    """
    Every place a chunk's label is written, as (where, label, text) in the order
    knitr gives them precedence, so the first is the chunk's label: "pipe" for a
    label: (else id:) key in the "#| " lines at the top of its body (knitr merges
    those options over the header's), "option" for a label= option, and "header"
    for the bare name first in the header (knitr's parse_params makes it the label
    only when no label= is given). text is how it is written.
    """
    spellings = []
    lines = _lines(cell.source)
    for start, end, _, label in _pipe_labels(cell.source):
        spellings.append(("pipe", label, "".join(lines[start:end]).rstrip("\n")))
    value = cell.options.get("label", "")
    # Without a value it is a bare name, not a label= option
    if value:
        # Not a string: knitr deparses the R expression and drops its spaces
        label = _r_string_value(value)
        spellings.append(("option", value.replace(" ", "") if label is None else label, f"label={value}"))
    if cell.label:
        # knitr quotes a bare name; one already quoted is an R string
        label = _r_string_value(cell.label)
        spellings.append(("header", cell.label if label is None else label, f"the bare label {cell.label}"))
    return spellings


def _options_shown(cell: Cell) -> list[tuple[str, str]]:
    """A chunk's options as list_cells and get_chunk_options show them: a label= option is its label, not one of them."""
    return [(key, value) for key, value in cell.options.items() if not (key == "label" and value)]


def _one_line(text: str) -> str:
    """text with its line breaks written as \\n and \\r, so output that gives each item a line keeps it on one."""
    return text.replace("\r", "\\r").replace("\n", "\\n")


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
        # The file's text as last read or written: a save that is refused goes back to it.
        self._text = text

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _save(self) -> str:
        """
        Write the document to the file if its text reads back as the same header
        and cells (adjacent markdown cells as one, see parser._layout). If not,
        raise, leaving the file as it was and the manager as the file reads.
        """
        text = serialize(self.frontmatter, self.cells)
        problem = _read_back_problem(self.frontmatter, self.cells, text)
        if problem is not None:
            self.frontmatter, self.cells = parse(self._text)
            raise RmdManagerError(problem)
        # Written as serialized: edited parts already use the document's line break.
        with open(self.filepath, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        self._text = text
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

    def _set_source(self, cell: Cell, source: str, new_text: str) -> None:
        """
        Give a cell new text, with "\\n" line breaks, made with new_text, the text
        the caller passed. The text it already has leaves the cell's bytes as they
        are. In a chunk, new_text can't hold a line knitr would read as the
        chunk's closing fence, and in prose, a line that would open a chunk; lines
        the cell already had aren't checked again.
        """
        if source == cell.source:
            return
        if cell.cell_type == "code":
            _check_chunk_text(new_text)
        else:
            _check_prose_text(new_text)
        cell.source = source
        cell.mark_dirty()

    def _set_header(self, cell: Cell, label: Optional[str], options: "OrderedDict[str, str]", change: str) -> None:
        """
        Give a chunk this label and options, rewriting only its header line, if
        that line reads back as exactly them; otherwise raise, leaving the chunk
        as it was. change starts the error message.
        """
        if (label, options) == (cell.label, cell.options):
            return
        header = _render_chunk_header(cell.language, label, options)
        read = _read_chunk_header(header)
        if read != (cell.language, label, options):
            _, read_label, read_options = read or (None, None, {})
            raise RmdManagerError(
                f"{change}: the chunk header {header} would read back as label {read_label!r} and options "
                f"{dict(read_options)} (a comma, '=', or an unmatched bracket or quote outside a quoted string "
                "changes how a header reads), so the file was left unchanged"
            )
        cell.label, cell.options = label, options
        cell.mark_header_dirty()

    def _set_label(self, cell: Cell, value: str) -> None:
        """
        Set a chunk's label to value, or clear it if value is empty. It is written
        where knitr reads it from (see _label_spellings): a "#| label:" (or id:)
        line, a label= option (an R string, in the quotes it had), or else the bare
        name first in the header; the spellings knitr reads it over go, so one is
        left. Raises, leaving the chunk as it was, for a label that place can't hold.
        """
        spellings = _label_spellings(cell)
        where = (spellings[0][0] if spellings else "header") if value else None
        if where == "header":
            _check_header_text("Chunk label", value)
        elif "\n" in value or "\r" in value:
            place = "a #| option line" if where == "pipe" else "a chunk header"
            raise RmdManagerError(f"Chunk label {value!r} contains a line break, but {place} is a single line")
        options = OrderedDict(cell.options)
        if where == "option":
            quote = options["label"][0] if _r_string_value(options["label"]) is not None else '"'
            options["label"] = quote + value.replace("\\", "\\\\").replace(quote, "\\" + quote) + quote
        else:
            options.pop("label", None)
        # The first label in the #| lines gets the value as one line, under its own key; the others' lines go
        pipe = _pipe_labels(cell.source)
        edits = [(start, end, "") for start, end, _, _ in pipe]
        if where == "pipe":
            start, end, key, _ = pipe[0]
            edits[0] = (start, end, f"#| {key}: {yaml_string(value)}\n")
        self._set_header(cell, value if where == "header" else None, options,
                         f"Can't set the chunk label to {value!r}" if value else "Can't remove the chunk label")
        if edits:
            self._set_body_lines(cell, edits)

    def _set_body_lines(self, cell: Cell, edits: list[tuple[int, int, str]]) -> None:
        """
        In a chunk, replace lines [start, end) of its source with text, whole lines
        each ending in "\\n" ("" drops them), for each (start, end, text) in edits,
        which don't overlap. Only those lines are written anew, with the document's
        line break: the header line, the other lines and the closing fence keep
        their bytes. Each text is checked as _set_source checks new chunk text.
        """
        lines = _lines(_chunk_body(cell.source))
        raw = _lines(cell.raw)
        newline = self.frontmatter.newline
        for start, end, text in sorted(edits, reverse=True):
            _check_chunk_text(text)
            lines[start:end] = [text] if text else []
            # The raw text's line 0 is the header line
            raw[start + 1:end + 1] = [_with_newline(text, newline)] if text else []
        source = _chunk_source("".join(lines))
        if cell.dirty or not cell.raw:
            self._set_source(cell, source, "".join(text for _, _, text in edits))
            return
        # _join keeps a lone "\r" ending a line apart from a "\n" line that dropped lines bring next to it.
        cell.raw = _join(raw, newline)
        cell.source = source

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
                # The label knitr uses, wherever it is written; a label= option is not counted as an option
                spellings = _label_spellings(cell)
                if spellings:
                    meta += f" label={_one_line(spellings[0][1])}"
                options = _options_shown(cell)
                if options:
                    meta += f" opts={len(options)}"
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
        if cell_type == "code":
            _check_chunk_text(new_cell.source)
        else:
            _check_prose_text(new_cell.source)
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
        if cell.cell_type == "code":
            # Split the chunk's body, then take each half's source: every body line keeps its place.
            second_src = _chunk_source(_chunk_body(cell.source)[len(first_src):])
            first_src = _chunk_source(first_src)
        else:
            second_src = "".join(lines[line_offset:])
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
        if base.cell_type == "code":
            # The chunks' bodies joined as they are: an empty chunk adds no line.
            base.source = _chunk_source("".join(_chunk_body(part) for part in parts))
        else:
            base.source = "".join(parts)
        base.mark_dirty()
        del self.cells[s + 1:e + 1]
        return self._save()

    # ──────────────────────────────────────────────
    # Cell content editing
    # ──────────────────────────────────────────────

    def replace_cell_source(self, index: int, new_source: str) -> str:
        idx = self._validate_index(index)
        new_source = _with_newline(new_source, "\n")
        self._set_source(self.cells[idx], new_source, new_source)
        return self._save()

    def prepend_to_cell(self, index: int, source: str) -> str:
        idx = self._validate_index(index)
        cell = self.cells[idx]
        # As "\n" text, so the separator check sees "\r\n" and "\r" breaks too.
        source = _with_newline(source, "\n")
        sep = "" if cell.source.startswith("\n") or not cell.source or not source or source.endswith("\n") else "\n"
        self._set_source(cell, source + sep + cell.source, source)
        return self._save()

    def append_to_cell(self, index: int, source: str) -> str:
        idx = self._validate_index(index)
        cell = self.cells[idx]
        # As "\n" text, so the separator check sees "\r\n" and "\r" breaks too.
        source = _with_newline(source, "\n")
        sep = "" if cell.source.endswith("\n") or not cell.source or not source or source.startswith("\n") else "\n"
        self._set_source(cell, cell.source + sep + source, source)
        return self._save()

    # ──────────────────────────────────────────────
    # Chunk options
    # ──────────────────────────────────────────────

    def get_chunk_options(self, index: int) -> str:
        cell = self._require_code_cell(index)
        lines = [f"language: {cell.language}"]
        # The label knitr uses; one not written as the bare name first in the header says where it is.
        # Line breaks are escaped, so the label stays on its line.
        spellings = _label_spellings(cell)
        if not spellings:
            lines.append("label: (none)")
        elif spellings[0][0] == "header":
            lines.append(f"label: {_one_line(spellings[0][1])}")
        else:
            (_, label, text), others = spellings[0], spellings[1:]
            over = ", which knitr reads over " + " and ".join(t for _, _, t in others) if others else ""
            lines.append(_one_line(f"label: {label} (from {text}{over})"))
        options = _options_shown(cell)
        if not options:
            lines.append("options: (none)")
        else:
            for k, v in options:
                lines.append(f"  {k}={v}" if v != "" else f"  {k}")
        return "\n".join(lines)

    def set_chunk_option(self, index: int, key: str, value: str) -> str:
        cell = self._require_code_cell(index)
        # Surrounding whitespace goes, as reading the header drops it.
        key, value = key.strip(), value.strip()
        if not key:
            raise RmdManagerError("Option key must not be empty")
        if key == "label":
            self._set_label(cell, value)
            return self._save()
        _check_header_text("Option key", key)
        _check_header_text("Chunk option value", value)
        if not value:
            raise RmdManagerError(
                "Option value must not be empty: knitr reads a bare name in a chunk header as the chunk label, "
                "so give a value such as TRUE, or remove the option with remove_chunk_option"
            )
        options = OrderedDict(cell.options)
        options[key] = value
        self._set_header(cell, cell.label, options, f"Can't set chunk option {key!r} to {value!r}")
        return self._save()

    def remove_chunk_option(self, index: int, key: str) -> str:
        cell = self._require_code_cell(index)
        key = key.strip()
        if key == "label":
            if not _label_spellings(cell):
                raise RmdManagerError(f"Cell {index} has no label to remove")
            self._set_label(cell, "")
        else:
            if key not in cell.options:
                raise RmdManagerError(f"Cell {index} has no option {key!r}")
            options = OrderedDict(cell.options)
            del options[key]
            self._set_header(cell, cell.label, options, f"Can't remove chunk option {key!r}")
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
