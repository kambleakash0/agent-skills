"""
RmdManager: cell-level editing of .rmd R Markdown documents.

Mirrors notebook-editor's NotebookManager API where possible so agents can
reuse the same mental model. The underlying storage is a .rmd text file
parsed into a Frontmatter + ordered list of Cells via rmd_editor.parser.
"""
from __future__ import annotations

import os
import re
from typing import NamedTuple, Optional

from rmd_editor.parser import (
    Cell, Frontmatter, FrontmatterError, dump_yaml, parse, serialize, yaml_string,
    _KNITR_CHUNK_BEGIN, _KNITR_CHUNK_END, _OptionBlock, _OptionEntry, _R_SPACE, _chunk_body, _chunk_source, _chunk_stop,
    _closed, _fence_close, _fence_indent, _indented, _join, _layout, _lines, _option_block, _option_extent,
    _option_text, _pipe_labels, _r_string_value, _r_to_yaml, _r_trouble, _read_chunk_opening, _read_header,
    _render_chunk_header, _with_newline,
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
    """
    Reject new chunk text with a line knitr would read as the chunk's closing
    fence, or as a chunk header, which would end the chunk there and start
    another: lines with any fence are refused, not only those with the chunk's
    own (see parser._chunk_stop), as which fence a line must have to count
    changes with where the chunk is.
    """
    for number, line in enumerate(_lines(text), start=1):
        line = line.rstrip("\n")
        if _KNITR_CHUNK_END.match(line):
            raise RmdManagerError(
                f"Line {number} of the new text, {line!r}, is a closing fence for knitr (backticks alone on a line, "
                "after nothing but spaces, tabs or >), which would end the chunk there"
            )
        if _KNITR_CHUNK_BEGIN.match(line):
            raise RmdManagerError(
                f"Line {number} of the new text, {line!r}, is a chunk header for knitr (backticks after nothing but "
                "spaces, tabs or >, then {engine} or {engine options}), which would end the chunk there and start another"
            )


def _check_prose_text(text: str) -> None:
    """
    Reject new prose with a line knitr would read as a chunk's opening fence
    (as the parser does), which would make the prose after it chunk code.
    """
    for number, line in enumerate(_lines(text), start=1):
        line = line.rstrip("\n")
        if _KNITR_CHUNK_BEGIN.match(line):
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
        "next to the edit does this, and so does a chunk holding a closing fence of another fence (such as ````) "
        "brought to the first line of the file, where knitr closes a chunk at any closing fence"
    )


# knitr's chunk options with a dot in their name: those of opts_chunk and opts_chunk_attr in its R/defaults.R. Its
# dot_names reads a dashed spelling of one of these (fig-width) as the dotted name, over it; others stay as written.
_KNITR_DOTTED_OPTIONS = frozenset({
    "tidy.opts", "strip.white", "cache.path", "cache.vars", "cache.lazy", "cache.rebuild", "cache.comments",
    "cache.globals", "fig.keep", "fig.show", "fig.align", "fig.path", "dev.args", "fig.ext", "fig.width", "fig.height",
    "fig.env", "fig.cap", "fig.scap", "fig.note", "fig.lp", "fig.subcap", "fig.pos", "out.width", "out.height",
    "out.extra", "fig.retina", "ref.label", "fig.showtext", "fig.format", "fig.dpi", "fig.process", "fig.asp",
    "fig.ncol", "fig.dim", "fig.id", "opts.label", "resize.width", "resize.height", "fig.alt", "fig.link", "fig.sep",
    "tab.cap", "ffmpeg.bitrate", "ffmpeg.format", "R.options", "animation.hook",
    *(f"{kind}.{part}" for kind in ("class", "attr")
      for part in ("source", "output", "message", "warning", "error", "chunk")),
    *(f"{name}.print" for name in ("max", "sql.max", "paged", "rows", "cols", "cols.min", "pages", "rownames")),
})
# A name R reads as itself, so it can stand for a label after other options in a header: a letter, then letters,
# digits, dots and underscores, and not one of R's reserved words.
_R_NAME = re.compile(r"[A-Za-z][A-Za-z0-9._]*")
_R_RESERVED = frozenset({
    "if", "else", "repeat", "while", "function", "for", "next", "break", "in", "TRUE", "FALSE", "NULL", "Inf", "NaN",
    "NA", "NA_integer_", "NA_real_", "NA_character_", "NA_complex_",
})
# What a key repeated in a chunk's option lines does.
_REPEATED = "R's yaml package, which knitr reads #| lines with, rejects a repeated key, so knitr fails on this chunk"


def _option_name(key: str) -> str:
    """
    The option knitr reads key as: a dashed name such as fig-width, as Quarto
    writes them, is the dotted one when knitr knows that (its dot_names), else
    key is itself.
    """
    dotted = key.replace("-", ".")
    return dotted if dotted in _KNITR_DOTTED_OPTIONS else key


def _first_named(cell: Cell) -> int:
    """The index into cell.options of the header's first key=value (or lone =); len(cell.options) if it has none."""
    return next((i for i, (key, value) in enumerate(cell.options) if value or not key), len(cell.options))


def _bare_names(cell: Cell) -> list[list[int]]:
    """
    The names without a value in a chunk's header, as knitr's xfun::csv_options
    reads them: each list is one unnamed element, as indexes into cell.options,
    -1 standing for cell.label (the bare name first). Its quote_label quotes the
    names written before the first key=value as one string, so they are one
    element, commas and all, unless the first is a quoted string already or one
    character, which it quotes alone; each later one is an element of its own.
    knitr takes the one unnamed element for the label, and fails on a header
    with more than one.
    """
    names = ([-1] if cell.label else []) + [i for i, (key, value) in enumerate(cell.options) if key and not value]
    named = _first_named(cell)
    first = [i for i in names if i < named]
    if not first or _bare_text(cell, first[:1])[0] in "'\"" or len(_bare_text(cell, first[:1])) == 1:
        return [[i] for i in names]
    return [first] + [[i] for i in names if i >= named]


def _bare_text(cell: Cell, names: list[int]) -> str:
    """The names of an unnamed element of a chunk's header (see _bare_names) as written, joined by commas."""
    return ", ".join(cell.label if i == -1 else cell.options[i][0] for i in names)


def _unread_names(cell: Cell, names: list[list[int]]) -> str:
    """The unnamed elements of a header knitr fails on (see _bare_names), each quoted, for a message."""
    return " and ".join(f"'{_bare_text(cell, element)}'" for element in names)


def _label_spellings(cell: Cell, block: Optional[_OptionBlock]) -> list[tuple[str, str, str]]:
    """
    Every place a chunk's label is written, as (where, label, text) in the order
    knitr gives them precedence, so the first is the chunk's label: "pipe" for a
    label: (else id:) key in block, the option lines at the top of its body (knitr
    merges those options over the header's), "option" for a label= option (each
    copy, if it is repeated), and "header" for the bare name or names knitr reads
    as one unnamed element (see _bare_names; its csv_options makes that the label
    only when no label= is given). text is how it is written. A header with more
    than one unnamed element has no "header" spelling: knitr fails on it.
    """
    spellings = []
    for entry, label in _pipe_labels(block):
        spellings.append(("pipe", label, block.entries[entry].text))
    for key, value in cell.options:
        # Without a value it is a bare name, not a label= option
        if key == "label" and value:
            # Not a string: knitr deparses the R expression and drops its spaces
            label = _r_string_value(value)
            spellings.append(("option", value.replace(" ", "") if label is None else label, f"label={value}"))
    names = _bare_names(cell)
    if len(names) == 1:
        text = _bare_text(cell, names[0])
        if names[0][0] < _first_named(cell) and text[0] not in "'\"":
            # Written before any key=value: knitr quotes the text as it is
            label = text
        else:
            # R code: a string's text, or else the code as knitr deparses it, without its spaces
            label = _r_string_value(text)
            label = text.replace(" ", "") if label is None else label
        spellings.append(("header", label, f"the bare label {text}"))
    return spellings


class _Spelling(NamedTuple):
    where: str   # "header" for a part of the header, "pipe" for an entry of the option lines
    index: int   # into cell.options (-1 for cell.label), or into the option block's entries
    key: str     # the key as written
    text: str    # how it is written: "echo=FALSE", a bare name, or the option lines


def _option_spellings(cell: Cell, block: Optional[_OptionBlock]) -> list[tuple[str, list[_Spelling]]]:
    """
    A chunk's options, its label aside, merged as knitr merges them: (name,
    spellings) for each option knitr reads (see _option_name), in the order
    first written, header first. The spelling knitr uses comes first: an option
    line's over the header's (parse_block's merge_list), a dashed name's over
    the dotted one (dot_names), and else the header's last copy (opts_chunk$merge
    assigns the copies in turn), which a key the header has twice also keeps
    over an option line, as merge_list puts that line's value in the first copy.
    The others follow in the order written. A name without a value is an option
    here only in a header knitr fails on (see _bare_names); label= options, and
    label: and id: keys in the option lines, are the label (see _label_spellings).
    """
    names = _bare_names(cell)
    label = {i for element in names for i in element} if len(names) == 1 else set()
    parts = ([(-1, (cell.label, ""))] if cell.label else []) + list(enumerate(cell.options))
    options: dict[str, list[_Spelling]] = {}
    for i, (key, value) in parts:
        if (key == "label" and value) or i in label:
            continue
        text = f"{key}={value}" if value or not key else key
        options.setdefault(_option_name(key), []).append(_Spelling("header", i, key, text))
    for i, entry in enumerate(block.entries if block else []):
        if entry.key is not None and entry.key not in ("label", "id"):
            options.setdefault(_option_name(entry.key), []).append(_Spelling("pipe", i, entry.key, entry.text))
    merged = []
    for name, spellings in options.items():
        header = [s for s in spellings if s.where == "header"]
        pipe = [s for s in spellings if s.where == "pipe"]
        dashed = [s for s in pipe if s.key != name]
        exact = [s for s in pipe if s.key == name]
        if dashed:
            used = dashed[0]
        elif exact and sum(s.key == name for s in header) < 2:
            used = exact[0]
        else:
            used = header[-1]
        merged.append((name, [used] + [s for s in spellings if s is not used]))
    return merged


def _option_line(spellings: list[_Spelling]) -> str:
    """
    One option as get_chunk_options lists it (see _option_spellings): the
    spelling knitr uses as written, then the copies of its key the option lines
    repeat, which knitr fails on, or else the spellings knitr reads it over.
    """
    used, others = spellings[0], spellings[1:]
    pipe = [s for s in spellings if s.where == "pipe"]
    repeats = [s.text for i, s in enumerate(pipe) if any(t.key == s.key for t in pipe[:i])]
    if repeats:
        return f"{used.text} (repeated as {' and '.join(repeats)}: {_REPEATED})"
    if others:
        return f"{used.text} (knitr reads it over {' and '.join(s.text for s in others)})"
    return used.text


def _r_string(text: str, quote: str = '"') -> str:
    """text as an R string in the given quotes, with backslashes and those quotes escaped."""
    return quote + text.replace("\\", "\\\\").replace(quote, "\\" + quote) + quote


def _r_name(text: str) -> str:
    """text as a name in a header after other options: as written if R reads it as that name, else an R string."""
    return text if _R_NAME.fullmatch(text) and text not in _R_RESERVED else _r_string(text)


def _pipe_line(block: _OptionBlock, entry: _OptionEntry, value: str) -> str:
    """entry of block written anew on one option line holding value, YAML text, under its key as written."""
    return f"{block.start}{entry.prefix} {value}" + (f" {block.end}" if block.end else "") + "\n"


def _pipe_edits(
    cell: Cell, block: _OptionBlock, removed: set[int], rewritten: dict[int, str]
) -> list[tuple[int, int, str]]:
    """
    Edits for RmdManager._set_body_lines that remove the lines of the entries of
    block, the option lines of chunk cell, in removed and write those in
    rewritten (entry to new lines, ending in "\\n") anew. knitr reads the
    option lines as YAML only when the first is a "key:" line, so comment and
    blank lines that would be left at the top move to just after the first key
    left, or go too when no key is left. Raises for lines that are one comment
    over several ("/*| a: 1", then "b: 2 */"): they aren't edited line by line.
    """
    language = cell.language
    one_per_line = all(line.startswith(block.start) and line.rstrip(_R_SPACE).endswith(block.end)
                       for line in block.lines)
    if block.end and not one_per_line:
        raise RmdManagerError(
            f"The option lines of this {language} chunk are one {block.start}... {block.end} comment over several "
            "lines, which can't be edited line by line, so the file was left unchanged"
        )
    entries = block.entries
    edits = {entries[i].start: (entries[i].start, entries[i].end, "") for i in removed}
    for i, text in rewritten.items():
        edits[entries[i].start] = (entries[i].start, entries[i].end, text)
    kept = [i for i in range(len(entries)) if i not in removed]
    top = entries[kept[0]].start if kept else len(block.lines)
    gone = {line for i in removed for line in range(entries[i].start, entries[i].end)}
    lead = [line for line in range(top) if line not in gone]
    if lead and all(not block.meta[line].strip() or block.meta[line].lstrip().startswith("#") for line in lead):
        # Every line above the first key left is rewritten: the comment and blank lines among them go after it
        edits = {start: edit for start, edit in edits.items() if start > top}
        if kept:
            first = entries[kept[0]]
            text = rewritten.get(kept[0], "".join(block.lines[first.start:first.end]))
            edits[0] = (0, first.end, text + "".join(block.lines[line] for line in lead))
        else:
            edits[0] = (0, len(block.lines), "")
    # The lines left, read with the code after them as knitr reads them, must be the option lines, as YAML with the
    # keys left, as before: removing an anchor would break its aliases, and code that ends with */ in a c chunk, or
    # starts with #| in a sql one, can become option lines
    lines = list(block.lines)
    for start, end, text in sorted(edits.values(), reverse=True):
        lines[start:end] = _lines(text)
    code = [line.rstrip("\n") + "\n" for line in _lines(cell.source)][len(block.lines):]
    extent = _option_extent(language, lines + code)
    after = _option_block(language, "".join(lines + code))
    keys = [entry.key for entry in after.entries] if after else []
    broken = after is not None and _read_header("".join(after.meta))[1] is not None
    if ((extent[2] if extent else 0) != len(lines) or keys != [entries[i].key for i in kept]
            or (broken and _read_header("".join(block.meta))[1] is None)):
        raise RmdManagerError(
            "Editing the option lines of this chunk would change how the rest of them read (for example an alias "
            "to an anchor that goes) or make code below them option lines, so the file was left unchanged"
        )
    return list(edits.values())


def _closed_by_another_fence(cell: Cell) -> bool:
    """
    Whether cell is a chunk replayed from the file whose last line is a closing
    fence other than its own ("  ```" or "> ```" for ```{r}), which knitr
    closes a chunk at only on the file's first line (see parser._chunk_stop).
    """
    if cell.cell_type != "code" or cell.dirty or not cell.raw or not cell.closed:
        return False
    line = _lines(cell.raw)[-1].rstrip("\r\n")
    fence = _fence_close(cell.fence)
    return not (line.startswith(fence) and not line[len(fence):].strip())


def _one_line(text: str) -> str:
    """text with its line breaks written as \\n and \\r, so output that gives each item a line keeps it on one."""
    return text.replace("\r", "\\r").replace("\n", "\\n")


def _with_added(cell: Cell, text: str, *, before: bool) -> str:
    """
    cell's source with text, "\\n" text, added before or after it. The two are
    separated by exactly one line break, which text may end with (before) or
    start with (after) itself; none of the cell's own line breaks is taken for
    it, so its blank lines all stay. A chunk's source is its lines joined by
    "\\n", a last "\\n" being a blank line before the fence (see
    parser._chunk_source), and text added after it keeps that rule: "y\\n"
    leaves a blank line before the fence. A prose cell's last line ends with its
    line break already, unless it is the file's last line without one.
    """
    if not text or not cell.source:
        return text + cell.source if before else cell.source + text
    if cell.cell_type == "markdown":
        if before:
            return text + ("" if text.endswith("\n") else "\n") + cell.source
        return cell.source + ("" if cell.source.endswith("\n") or text.startswith("\n") else "\n") + text
    lines = [line.rstrip("\n") for line in _lines(_chunk_body(cell.source))]
    if before:
        lines = (text[:-1] if text.endswith("\n") else text).split("\n") + lines
    else:
        lines += (text[1:] if text.startswith("\n") else text).split("\n")
    return _chunk_source("".join(line + "\n" for line in lines))


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
        A chunk that a closing fence of another fence closed, as knitr closes
        one on the file's first line (see parser._chunk_stop), is written anew,
        with its own closing fence, once something comes before it.
        """
        # The cell written first: the cells before it write nothing
        lead = next((i for i, c in enumerate(self.cells) if c.cell_type != "markdown" or c.source), len(self.cells))
        for index, cell in enumerate(self.cells):
            if (self.frontmatter.present or index > lead) and _closed_by_another_fence(cell):
                cell.mark_dirty()
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
        are. In a chunk, new_text can't hold a line knitr would read as a closing
        fence or a chunk header, and in prose, a line that would open a chunk;
        lines the cell already had aren't checked again.
        """
        if source == cell.source:
            return
        if cell.cell_type == "code":
            _check_chunk_text(new_text)
        else:
            _check_prose_text(new_text)
        cell.source = source
        cell.mark_dirty()

    def _set_header(self, cell: Cell, label: Optional[str], options: list[tuple[str, str]], change: str) -> None:
        """
        Give a chunk this label and options, rewriting only its header line, if
        that line reads back as exactly them, under the chunk's fence; otherwise
        raise, leaving the chunk as it was. change starts the error message.
        """
        if (label, options) == (cell.label, cell.options):
            return
        header = _render_chunk_header(cell.language, label, options, cell.fence)
        read = _read_chunk_opening(header)
        if read != (cell.fence, cell.language, label, options):
            _, _, read_label, read_options = read or (None, None, None, {})
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
        name or names of the header, in their place (after other options, as an R
        name or string); a chunk without a label gets it first in the header. The
        spellings knitr reads it over go, so one is left. Raises, leaving the chunk
        as it was, for a label that place can't hold, or a header knitr fails on
        for its names without a value.
        """
        change = "Can't set the chunk label" if value else "Can't remove the chunk label"
        names = _bare_names(cell)
        if len(names) > 1:
            raise RmdManagerError(
                f"{change}: knitr fails on this chunk header, which has more than one name without a value "
                f"({_unread_names(cell, names)}): give them values with set_chunk_option, or remove them with "
                "remove_chunk_option, first"
            )
        block = _option_block(cell.language, cell.source)
        spellings = _label_spellings(cell, block)
        where = (spellings[0][0] if spellings else "header") if value else None
        bare = names[0] if names else []
        # Written first in the header: in the place of the bare name there, or as a new label
        first = where == "header" and (not bare or -1 in bare)
        if first:
            _check_header_text("Chunk label", value)
        elif "\n" in value or "\r" in value:
            place = "a #| option line" if where == "pipe" else "a chunk header"
            raise RmdManagerError(f"Chunk label {value!r} contains a line break, but {place} is a single line")
        options = []
        for i, (key, text) in enumerate(cell.options):
            if key == "label" and text:
                # The first label= option gets the value, in the quotes it had; the others go
                if where == "option" and not any(k == "label" and v for k, v in options):
                    options.append(("label", _r_string(value, text[0] if _r_string_value(text) is not None else '"')))
                continue
            if i in bare:
                # The bare label after other options: its first name gets the value, the others go
                if where == "header" and not first and i == bare[0]:
                    options.append((_r_name(value), ""))
                continue
            options.append((key, text))
        # The first label in the option lines gets the value as one line, under its own key; the others' lines go
        pipe = _pipe_labels(block)
        removed = {entry for entry, _ in pipe}
        rewritten = {}
        if where == "pipe":
            entry = pipe[0][0]
            removed.discard(entry)
            rewritten[entry] = _pipe_line(block, block.entries[entry], _option_text(value))
        edits = _pipe_edits(cell, block, removed, rewritten) if pipe else []
        self._set_header(cell, value if first else None, options,
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
            # The raw text's line 0 is the header line; its lines are indented as the fence is
            raw[start + 1:end + 1] = [_with_newline(_indented(text, _fence_indent(cell.fence)), newline)] if text else []
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
                # The label knitr uses, wherever it is written, and the options it merges from the header and
                # the option lines; a label= option is not counted as an option
                block = _option_block(cell.language, cell.source)
                spellings = _label_spellings(cell, block)
                if spellings:
                    meta += f" label={_one_line(spellings[0][1])}"
                options = _option_spellings(cell, block)
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
            new_cell.language, new_cell.fence = cell.language, cell.fence
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
            # The other chunks' lines go under the first one's fence, where a fence line knitr read as code in its own
            # chunk can close the merged one or start another (see parser._chunk_stop)
            lines = [(k, number, line.rstrip("\n")) for k in range(s, e + 1)
                     for number, line in enumerate(_lines(_chunk_body(self.cells[k].source)), start=1)]
            indent = _fence_indent(base.fence)
            first = not self.frontmatter.present and all(c.cell_type == "markdown" and not c.source for c in self.cells[:s])
            texts = [f"{base.fence}{{{base.language}}}"] + [_indented(line, indent) for _, _, line in lines]
            stop, closed = _chunk_stop(texts, 0, exact=not first)
            if closed or stop < len(texts):
                k, number, line = lines[stop - 1 - closed]
                what = "a closing fence for knitr, which would end the chunk there" if closed else (
                    "a chunk header for knitr, which would end the chunk there and start another")
                raise RmdManagerError(
                    f"Can't merge cells {s} to {e}: in the merged chunk, line {number} of cell {k}, {line!r}, would be "
                    f"{what}, so the file was left unchanged"
                )
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
        self._set_source(cell, _with_added(cell, source, before=True), source)
        return self._save()

    def append_to_cell(self, index: int, source: str) -> str:
        idx = self._validate_index(index)
        cell = self.cells[idx]
        # As "\n" text, so the separator check sees "\r\n" and "\r" breaks too.
        source = _with_newline(source, "\n")
        self._set_source(cell, _with_added(cell, source, before=False), source)
        return self._save()

    # ──────────────────────────────────────────────
    # Chunk options
    # ──────────────────────────────────────────────

    def get_chunk_options(self, index: int) -> str:
        cell = self._require_code_cell(index)
        block = _option_block(cell.language, cell.source)
        lines = [f"language: {cell.language}"]
        # The label knitr uses; one not written as the bare name or names in the header says where it is.
        # Line breaks are escaped, so the label stays on its line.
        names = _bare_names(cell)
        spellings = _label_spellings(cell, block)
        if len(names) > 1:
            lines.append("label: (none: knitr fails on this chunk header, which has more than one name without a "
                         f"value: {_unread_names(cell, names)})")
        elif not spellings:
            lines.append("label: (none)")
        elif spellings[0][0] == "header":
            label = f"label: {spellings[0][1]}"
            if len(names[0]) > 1:
                written = " and ".join(_bare_text(cell, [i]) for i in names[0])
                label += (f" (knitr reads the bare names {written} at the start of the header as one label, "
                          "commas and all)")
            lines.append(_one_line(label))
        else:
            (where, label, text), others = spellings[0], spellings[1:]
            if where == "pipe":
                # A label: (or id:) key repeated in the option lines, which knitr fails on
                pipe = _pipe_labels(block)
                key = block.entries[pipe[0][0]].key
                repeats = [block.entries[entry].text for entry, _ in pipe[1:] if block.entries[entry].key == key]
                problem = _REPEATED
            else:
                # A label= option repeated: parse_block takes the first copy ($ finds it), call_block the last
                repeats = [t for w, _, t in others if w == "option"]
                problem = "knitr takes the first for the chunk's label in some steps and the last in others"
            if repeats:
                tail = f", repeated as {' and '.join(repeats)}: {problem}"
            else:
                tail = ", which knitr reads over " + " and ".join(t for _, _, t in others) if others else ""
                copies = [s for s in others if s[0] == "option"]
                if where == "pipe" and len(copies) > 1:
                    # merge_list puts the line's label in the first label= copy; opts_chunk$merge ends with the last
                    tail += (f"; with label= repeated, knitr takes {copies[-1][1]}, its last copy, for the chunk's "
                             "label in some steps")
            lines.append(_one_line(f"label: {label} (from {text}{tail})"))
        # Every option knitr reads, from the header and the option lines, as the spelling it uses
        options = _option_spellings(cell, block)
        if not options:
            lines.append("options: (none)")
        for _, option in options:
            lines.append(_one_line(f"  {_option_line(option)}"))
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
        # The spelling knitr uses gets the value where it is written (an option line's as YAML), and the others go,
        # so one is left; a key not written yet goes at the end of the header.
        block = _option_block(cell.language, cell.source)
        spellings = next((option for name, option in _option_spellings(cell, block) if name == _option_name(key)), [])
        used = spellings[0] if spellings else None
        dropped = {s.index for s in spellings[1:] if s.where == "header"}
        removed = {s.index for s in spellings[1:] if s.where == "pipe"}
        rewritten = {}
        if used is not None and used.where == "pipe":
            rewritten[used.index] = _pipe_line(block, block.entries[used.index], _r_to_yaml(value))
        edits = _pipe_edits(cell, block, removed, rewritten) if removed or rewritten else []
        in_header = used is not None and used.where == "header"
        # The bare name first in the header, in a header knitr fails on (see _option_spellings), becomes the option
        options = [(used.key, value)] if in_header and used.index == -1 else []
        for i, (k, v) in enumerate(cell.options):
            if i not in dropped:
                options.append((k, value) if in_header and i == used.index else (k, v))
        if used is None:
            options.append((key, value))
        label = None if (in_header and used.index == -1) or -1 in dropped else cell.label
        self._set_header(cell, label, options, f"Can't set chunk option {key!r} to {value!r}")
        if edits:
            self._set_body_lines(cell, edits)
        return self._save()

    def remove_chunk_option(self, index: int, key: str) -> str:
        cell = self._require_code_cell(index)
        key = key.strip()
        if key == "label":
            # A header knitr fails on for its names without a value has no label, which _set_label says
            if len(_bare_names(cell)) < 2 and not _label_spellings(cell, _option_block(cell.language, cell.source)):
                raise RmdManagerError(f"Cell {index} has no label to remove")
            self._set_label(cell, "")
            return self._save()
        # Every spelling goes: the header's copies of the key and its option lines
        block = _option_block(cell.language, cell.source)
        spellings = next((option for name, option in _option_spellings(cell, block) if name == _option_name(key)), [])
        if not spellings:
            raise RmdManagerError(f"Cell {index} has no option {key!r}")
        dropped = {s.index for s in spellings if s.where == "header"}
        removed = {s.index for s in spellings if s.where == "pipe"}
        edits = _pipe_edits(cell, block, removed, {}) if removed else []
        options = [option for i, option in enumerate(cell.options) if i not in dropped]
        self._set_header(cell, None if -1 in dropped else cell.label, options, f"Can't remove chunk option {key!r}")
        if edits:
            self._set_body_lines(cell, edits)
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
