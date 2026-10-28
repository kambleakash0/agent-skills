"""
R Markdown (.rmd) parser and serializer.

A .rmd file is markdown text that may contain:
  - An optional YAML frontmatter delimited by `---` fences at the very top.
  - Interleaved markdown prose and "executable code chunks" opened by a fence
    of the form  ```{lang [label][, opt1=val1, ...]}  and closed by ``` ,
    found where knitr finds them (see _chunk_stop): a fence may be indented
    or in a blockquote, and have more backticks, as long as the closing one
    matches it.
  - Regular markdown code blocks (```python, ``` , etc. — no braces) stay as
    part of the surrounding prose and are NOT treated as cells.

The parser produces:
  - frontmatter: a Frontmatter struct holding the header's raw text plus its
    parsed YAML (unknown tags such as R Markdown's !r kept as TaggedScalar)
  - cells: an ordered list of Cell objects with either cell_type="markdown"
    (prose) or cell_type="code" (chunks). Code cells carry language, optional
    label, and option key-value pairs (order-preserving).

Round-trip goal: reading a file and serializing without any edits should
yield byte-identical output. Cells that haven't been edited replay their
original raw text; a chunk whose label or options alone changed gets a new
header line before its raw body; other modified cells regenerate from
structured fields, a chunk's body from its source (see _chunk_source). The
frontmatter is always replayed from its raw text: key edits rewrite only the
lines of that key.

Line endings: "\\n", "\\r\\n" and a lone "\\r" each end a line, so CRLF and
mixed-ending documents parse like LF ones, and cell sources and the YAML that
callers see use "\\n". Raw text keeps the file's own line breaks; everything
the serializer writes anew (edited cells, edited header lines, the break
between parts) uses the document's line break, the one most of its lines end
with. Nothing else ends a line (not a form feed, NEL or U+2028), and the
manager counts, splits and numbers lines by the same rule (_lines).

A byte order mark (U+FEFF) at the very start is not part of the text the
document is parsed from: parse sets it aside in Frontmatter.bom and serialize
writes it back first, so a BOM file's header is still found and the file
round-trips byte for byte.
"""
from __future__ import annotations

import bisect
import re
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from typing import NamedTuple, Optional

import yaml


# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────


class FrontmatterError(ValueError):
    """A frontmatter edit that can't be made; the header is left as it was."""


@dataclass
class Frontmatter:
    """
    YAML frontmatter at the top of the document, if any. raw is the source of
    truth and is always replayed as is: set_key and remove_key rewrite only the
    lines of the key they change, so comments, blank lines, quoting, tags (!r,
    !expr), key order and line breaks elsewhere in the header stay byte for
    byte (but a lone "\\r" they leave just before a "\\n" is written as newline,
    see _join). The lines they write end with newline, the document's line break.
    """
    data: dict = field(default_factory=dict)   # parsed YAML, unknown tags as TaggedScalar; {} if unreadable
    raw: str = ""                              # original text between the --- fences (inclusive)
    present: bool = False
    error: Optional[str] = None                # why the header couldn't be read as a YAML mapping, else None
    newline: str = "\n"                        # the document's line break, set by parse: lines written anew use it
    bom: bool = False                          # the text began with a byte order mark (U+FEFF), set by parse: serialize writes it back

    def text(self) -> str:
        """The YAML between the --- fences, with "\\n" line breaks."""
        return _with_newline("".join(self._split()[1]), "\n") if self.present else ""

    def set_key(self, key: str, value: str) -> None:
        """
        Set one top-level key, rewriting only its lines; with no header, create
        one. value is parsed as YAML when possible, else kept as a string. If the
        value means the same written as given (on the key's line, or as an
        indented block below it), it is written that way, keeping its quoting,
        comments and tags; otherwise the parsed value is written as YAML. A new
        key goes just before the closing fence. Raises FrontmatterError, leaving
        the header unchanged, if the header can't be edited key by key.
        """
        # YAML reads "\r\n" and "\r" as "\n" too, so this keeps the value's meaning.
        value = _with_newline(value, "\n")
        parsed = _parse_yaml_value(value)
        if not self.present:
            header = "---\n" + _render_entry(_new_key_prefix(key), value, parsed) + "---\n"
            self._commit(key, _with_newline(header, self.newline), [key])
            return
        head, body, tail = self._split()
        keys = _editable_keys(body)
        names = [k.name for k in keys]
        spans = [span for span in _key_spans(body, keys) if span[0].name == key]
        lines = list(body)
        if not spans:
            # Before a document end marker ("..."), if the header has one.
            at = next((i for i, line in enumerate(lines) if _DOC_END.match(line)), len(lines))
            lines.insert(at, self._entry(_new_key_prefix(key), value, parsed))
            self._commit(key, _join([head, *lines, tail], self.newline), names + [key])
            return
        (first, start, end), repeats = spans[0], spans[1:]
        # Leave one copy holding the new value: YAML readers either keep the last copy or reject repeats.
        for _, repeat_start, repeat_end in reversed(repeats):
            del lines[repeat_start:repeat_end]
        lines[start:end] = [self._entry(first.prefix, value, parsed)]
        kept = keys.index(first)
        self._commit(key, _join([head, *lines, tail], self.newline), [n for i, n in enumerate(names) if n != key or i == kept])

    def remove_key(self, key: str) -> None:
        """
        Remove one top-level key with its indented lines (every copy, if it is
        repeated). Raises FrontmatterError, leaving the header unchanged, if there
        is no such key or the header can't be edited key by key.
        """
        if not self.present:
            raise FrontmatterError(f"Frontmatter has no key {key!r}")
        head, body, tail = self._split()
        keys = _editable_keys(body)
        spans = [span for span in _key_spans(body, keys) if span[0].name == key]
        if not spans:
            raise FrontmatterError(f"Frontmatter has no key {key!r}")
        lines = list(body)
        for _, start, end in reversed(spans):
            del lines[start:end]
        self._commit(key, _join([head, *lines, tail], self.newline), [k.name for k in keys if k.name != key])

    def _split(self) -> tuple[str, list[str], str]:
        """raw as (opening fence line, header body lines, closing fence line plus anything after it)."""
        lines = _lines(self.raw)
        close = next(i for i in range(1, len(lines)) if _FENCE_LINE.match(lines[i]))
        return lines[0], lines[1:close], "".join(lines[close:])

    def _entry(self, prefix: str, value: str, parsed) -> str:
        """The header lines for one key, as _render_entry writes them, with the document's line break."""
        return _with_newline(_render_entry(prefix, value, parsed), self.newline)

    def _commit(self, key: str, raw: str, names: list) -> None:
        """
        Adopt raw as the header. If the current header reads as a YAML mapping,
        the new one must too, with exactly the keys in names; otherwise raise
        FrontmatterError and keep the current header.
        """
        data, error, keys = _read_header(Frontmatter(raw=raw, present=True).text())
        if self.error is None and (error is not None or keys is None or [k.name for k in keys] != names):
            raise FrontmatterError(
                f"Changing frontmatter key {key!r} would break the rest of the header (for example an "
                "anchor that other keys refer to), so the file was left unchanged"
            )
        self.raw, self.data, self.error, self.present = raw, data, error, True


@dataclass
class Cell:
    cell_type: str                             # "markdown" or "code"
    source: str                                # body only (no fences, no frontmatter markers), "\n" line breaks; a chunk's as _chunk_source gives it
    # Code-cell-only fields
    language: str = "r"                        # "r", "python", "bash", "sql", ... for code cells
    label: Optional[str] = None                # the bare name first in the header, e.g. "setup" in  ```{r setup, echo=FALSE}
    # The header's other parts in the order written, as (key, value) pairs: a key written twice is there twice, and a
    # bare name (one after a leading comma or an option too) has the value "". knitr's own reading of the label and
    # options, #| lines included, is the manager's to work out.
    options: list = field(default_factory=list)
    # The header line before its {: indentation or > marks, backticks and any spaces, as "```" or "  ````". The
    # closing fence repeats it up to its last backtick, and the source is the code without the indentation.
    fence: str = "```"
    closed: bool = True                        # raw ends with the closing fence; False if knitr ends the chunk at the next chunk's header or the end
    # Bookkeeping
    raw: str = ""                              # original full text (with fences and the file's own line breaks)
    dirty: bool = False                        # True after any structural edit
    header_dirty: bool = False                 # True after a label or option edit: only the header line is written anew

    def mark_dirty(self) -> None:
        self.dirty = True

    def mark_header_dirty(self) -> None:
        self.header_dirty = True


# ──────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────


# A chunk's header line, as knitr reads it (the chunk.begin pattern of its R Markdown patterns, R/pattern.R):
# three or more backticks after nothing but spaces, tabs or >, maybe spaces, then {engine} or {engine options},
# the engine being letters, digits and underscores. The groups are the fence (the indentation or > marks and the
# backticks), the spaces after it, the engine, and what follows the engine inside the braces. knitr writes that last
# part ( *[ ,].*)?, which takes the same text as ([ ,].*)? but backtracks over a long run of spaces in time that
# grows with its length squared.
_KNITR_CHUNK_BEGIN = re.compile(r"([\t >]*```+)(\s*)\{([a-zA-Z0-9_]+)((?:[ ,].*)?)\}\s*\Z")
# A line knitr reads as a closing fence (its chunk.end pattern): three or more backticks alone, after nothing but
# spaces, tabs or >. Which of these closes a chunk is _chunk_stop's to say.
_KNITR_CHUNK_END = re.compile(r"[\t >]*```+\s*\Z")

# A UTF-8 byte order mark as decoded text; editors on Windows may write one before the --- fence.
_BOM = "\ufeff"


def parse(text: str) -> tuple[Frontmatter, list[Cell]]:
    """
    Parse the text of an .rmd document into a Frontmatter and an ordered list
    of Cells. Byte-level round-trip is preserved on unmodified parse-then-
    serialize cycles. The document's line break goes in frontmatter.newline,
    which serialize writes edited parts with. A byte order mark (U+FEFF) at the
    very start is set aside in frontmatter.bom, so a header or chunk fence on the
    first line is still found and no cell source starts with it.
    """
    bom = text.startswith(_BOM)
    if bom:
        text = text[len(_BOM):]
    frontmatter, body_start_idx = _extract_frontmatter(text)
    frontmatter.newline = _detect_newline(text)
    frontmatter.bom = bom
    body = text[body_start_idx:]
    cells = _split_body(body, at_start=body_start_idx == 0)
    return frontmatter, cells


def _extract_frontmatter(text: str) -> tuple[Frontmatter, int]:
    """Return (Frontmatter, index into text where body begins)."""
    fm = Frontmatter()
    lines = _LINE.finditer(text)
    # Must start with `---` on its own line (optionally with trailing whitespace), ended by a line break
    first = next(lines, None)
    if first is None or not _FENCE_LINE.match(first.group()) or not first.group().endswith(("\n", "\r")):
        return fm, 0
    # Find the closing `---` on its own line
    close = next((line for line in lines if _FENCE_LINE.match(line.group())), None)
    if close is None:
        return fm, 0  # Unterminated frontmatter -- treat whole thing as body
    fm.data, fm.error, _ = _read_header(_with_newline(text[first.end():close.start()], "\n"))
    fm.raw = text[:close.end()]
    fm.present = True
    return fm, close.end()


def _split_body(body: str, at_start: bool = False) -> list[Cell]:
    """
    Walk body line by line, splitting into markdown prose cells and code chunks,
    where knitr's split_file finds chunks (see _chunk_stop); at_start says body
    begins on the file's first line, which knitr reads a chunk on differently.
    Each cell's raw text preserves its original line breaks so serialization can
    replay unchanged cells byte-for-byte; its source has "\\n" breaks, a chunk's
    being its code as knitr reads it, without the indentation or > marks of its
    fence (see _strip_indent). Only "\\n", "\\r\\n" and a lone "\\r" end a line,
    as for knitr (R's readLines): form feeds, U+2028 and the other breaks
    str.splitlines knows stay inside a line, so every cell but the last ends
    with a line break.
    """
    cells: list[Cell] = []
    lines = _lines(body)
    # The same lines ending in "\n": fences are matched, and sources built, on these.
    plain = [_with_newline(line, "\n") for line in lines]
    texts = [line.rstrip("\n") for line in plain]
    i = 0
    n = len(lines)
    # First line of the prose not yet in a cell
    prose_start = 0

    def flush_prose(end: int) -> None:
        nonlocal prose_start
        if end > prose_start:
            cells.append(Cell(
                cell_type="markdown",
                source="".join(plain[prose_start:end]),
                raw="".join(lines[prose_start:end]),
            ))
        prose_start = end

    while i < n:
        opening = _read_chunk_opening(texts[i])
        if opening is None:
            i += 1
            continue
        stop, closed = _chunk_stop(texts, i, exact=not (at_start and i == 0))
        indent = _fence_indent(opening.fence)
        code = "".join(_strip_indent(texts[j], indent) + plain[j][len(texts[j]):] for j in range(i + 1, stop - closed))
        flush_prose(i)
        cells.append(Cell(
            cell_type="code",
            source=_chunk_source(code),
            language=opening.language,
            label=opening.label,
            options=opening.options,
            fence=opening.fence,
            closed=closed,
            raw="".join(lines[i:stop]),
        ))
        i = prose_start = stop
    flush_prose(n)
    return cells


def _chunk_stop(lines: list[str], start: int, exact: bool = True) -> tuple[int, bool]:
    """
    Where the chunk whose header is lines[start] ends, as knitr's
    group_indices finds it (R/parser.R): (stop, closed), the chunk being
    lines [start, stop) and closed saying whether its last line is its closing
    fence. lines are without line breaks. The closing fence is the first line
    that _KNITR_CHUNK_END takes and that is the header's fence (its indentation
    or > marks and backticks) and nothing but spaces: in ```{r}, "```" closes
    the chunk, while "````" and "  ```" are code. On the file's first line
    (exact false) knitr has no fence to match yet, and any such line closes it.
    A header line whose fence is followed right away by its {, as ```{python} in
    ```{r}, starts a new chunk, the one before it having no closing fence;
    other header lines are code, and a chunk nothing closes runs to the end.
    knitr refuses some chunks outright (one on the first line that holds a
    header line, or one with a closing fence of another fence and no fence of
    its own after it); their lines are read here as in any other chunk.
    """
    fence = _KNITR_CHUNK_BEGIN.match(lines[start]).group(1)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if _KNITR_CHUNK_BEGIN.match(line):
            if line.startswith(fence + "{"):
                return j, False
        elif _KNITR_CHUNK_END.match(line) and (not exact or line[:len(fence)] == fence and not line[len(fence):].strip()):
            return j + 1, True
    return len(lines), False


def _fence_indent(fence: str) -> str:
    """The indentation or > marks a chunk's fence (see Cell.fence) starts with."""
    return fence[:len(fence) - len(fence.lstrip("\t >"))]


def _fence_close(fence: str) -> str:
    """The closing fence of a chunk whose header starts with fence: its indentation or > marks and its backticks."""
    return fence[:fence.rindex("`") + 1]


def _strip_indent(line: str, indent: str) -> str:
    """
    A line of a chunk's body, without its line break, as knitr's parse_block
    reads it in a chunk whose fence starts with indent: without indent at its
    start, then without indent's text before its trailing spaces and tabs (so a
    blank line of a blockquote, written ">", is blank too).
    """
    if line.startswith(indent):
        line = line[len(indent):]
    bare = indent.rstrip(" \t")
    return line[len(bare):] if bare and line.startswith(bare) else line


def _indented(code: str, indent: str) -> str:
    """
    code, lines with "\\n" breaks, as the body of a chunk whose fence starts
    with indent writes it, which _strip_indent reads back: each line after
    indent, a blank one after indent without its trailing spaces and tabs.
    """
    if not indent:
        return code
    return "".join(indent.rstrip(" \t") + line if not line.strip("\n") else indent + line for line in _lines(code))


def _chunk_source(body: str) -> str:
    """
    A chunk's source from its body, the lines between its fences with "\\n"
    breaks: the body without the line break that ends its last line, since the
    closing fence goes on a line of its own anyway. So a source ending in "\\n"
    has a blank line before the fence. A body of blank lines only is kept whole,
    so one blank line ("\\n") stays apart from an empty chunk (""). _chunk_body
    undoes it: every body has exactly one source.
    """
    return body[:-1] if body.endswith("\n") and body.strip("\n") else body


def _chunk_body(source: str) -> str:
    """The body a chunk's source stands for (see _chunk_source), each line ending with a line break."""
    return source + "\n" if source.strip("\n") else source


# ──────────────────────────────────────────────
# Chunk header parsing
# ──────────────────────────────────────────────


class _ChunkOpening(NamedTuple):
    fence: str                       # the line before its {, as Cell.fence
    language: str
    label: Optional[str]             # as Cell.label and Cell.options
    options: list[tuple[str, str]]


def _read_chunk_opening(line: str) -> Optional[_ChunkOpening]:
    """A chunk header line, without its line break, as knitr reads one (see _KNITR_CHUNK_BEGIN); None if it isn't one."""
    m = _KNITR_CHUNK_BEGIN.match(line)
    if not m:
        return None
    label, options = _parse_label_and_options(m.group(4).strip())
    return _ChunkOpening(m.group(1) + m.group(2), m.group(3), label, options)


def _parse_label_and_options(inside: str) -> tuple[Optional[str], list[tuple[str, str]]]:
    """
    Given the text between `{r ` and `}` (e.g. `label, echo=FALSE, fig.width=7`),
    return (label, options). Label is the first part when it is a bare token
    without '='. Options are the other parts as (key, value) pairs in the order
    written, a key written twice included twice; a bare token has the value "".
    """
    label: Optional[str] = None
    options: list[tuple[str, str]] = []
    parts = _split_top_level_commas(inside)
    for idx, part in enumerate(parts):
        if not part:
            continue
        if "=" not in part:
            # Bare token -- if this is the first part, it's the label
            if idx == 0:
                label = part.strip()
            # Otherwise it's a bare name after a comma or an option; stash as key with empty value
            else:
                options.append((part.strip(), ""))
        else:
            k, _, v = part.partition("=")
            options.append((k.strip(), v.strip()))
    return label, options


def _split_top_level_commas(s: str) -> list[str]:
    """
    Split on commas that aren't nested inside (), [], {}, or quotes. Inside a
    quoted string a backslash escapes the next character, as in R, so
    "a\\", b" stays one part.
    """
    return _scan_commas(s)[0]


def _closed(s: str) -> bool:
    """Whether s ends outside every bracket and quote, so a comma written after it still splits."""
    return _scan_commas(s)[1]


def _scan_commas(s: str) -> tuple[list[str], bool]:
    """The parts of s for _split_top_level_commas, and whether s ends outside every bracket and quote."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    quote: Optional[str] = None
    escaped = False
    for c in s:
        if quote is not None:
            buf.append(c)
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == quote:
                quote = None
            continue
        if c in ("'", '"'):
            quote = c
            buf.append(c)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(c)
    if buf:
        parts.append("".join(buf).strip())
    return parts, depth == 0 and quote is None

def _r_trouble(s: str) -> Optional[str]:
    """
    What in s, read as R code the way knitr reads a chunk's options (as the
    arguments of alist(...)), would break the rest of the header: "`" for a
    backtick-quoted name left open, "#" for a comment (it runs to the end of
    the line), "=" for an = outside quotes and brackets that isn't part of ==,
    !=, <= or >= (a second = in key=value), or None. Quotes and brackets left
    open are _closed's to find.
    """
    quote: Optional[str] = None
    escaped = False
    depth = 0
    i = 0
    while i < len(s):
        c = s[i]
        if quote is not None:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
        elif c == "#":
            return "#"
        elif c == "%":
            # An operator such as %in% or %=%: skip to its closing %
            i = max(i, s.find("%", i + 1))
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "=":
            if s.startswith("==", i):
                i += 1
            elif depth == 0 and not (i and s[i - 1] in "<>!"):
                return "="
        i += 1
    return "`" if quote == "`" else None


# A quoted R string, as a whole: its quote, then its text with backslash escapes.
_R_STRING = re.compile(r"""(["'])((?:\\.|(?!\1)[^\\])*)\1""", re.S)
# A quoted R string whose only escapes are \\, \", \', \n and \t, which _r_string_value undoes as R does.
_SIMPLE_R_STRING = re.compile(r"""(["'])(?:\\[\\"'nt]|(?!\1)[^\\])*\1""", re.S)
# An R number that YAML reads as the same number: decimal digits without leading zeros, a minus sign and a fraction.
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
# Plain text that R's yaml package, which knitr reads option lines with, reads as something other than a string where
# PyYAML reads a string (its implicit.re): y and n as booleans, .na as NA, numbers with commas among their digits,
# floats without a digit (., -., .e+1, which it reads as NA) and base-60 numbers such as 0:30. Anything that looks like
# a number is taken, to be safe.
_R_YAML_NOT_TEXT = re.compile(
    r"[yYnN]|\.na(?:\.integer|\.real|\.character)?|[-+]?[0-9.,]*[0-9][0-9.,eE+-]*|[-+]?0x[0-9a-fA-F,]+"
    r"|[-+]?(?:[0-9][0-9,]*)?\.[0-9,]*|[-+]?(?:[0-9][0-9,]*)?\.[0-9.]*[eE][-+][0-9]+"
    r"|[-+]?[0-9][0-9,]*(?::[0-5]?[0-9])+(?:\.[0-9,]*)?"
)
# The first of a chunk's option lines, without the characters it starts with, when knitr reads them as YAML:
# "key:" then a space or nothing.
_YAML_OPTIONS = re.compile(r"[^ :]+:(?:\s|$)")
# The comment characters an engine's option lines start with, before "| ", and those they end with ("" for none):
# xfun's comment_chars table, which knitr's divide_chunk reads them by. Engine names match exactly, as in knitr;
# one not listed here, such as r, python or bash, uses "#".
_OPTION_COMMENTS = {
    **dict.fromkeys(("asy", "cc", "csharp", "d3", "dot", "fsharp", "go", "groovy", "java", "js", "node", "ojs", "Rcpp",
                     "rust", "sass", "scss", "scala"), ("//", "")),
    "mermaid": ("%%", ""),
    **dict.fromkeys(("matlab", "tikz"), ("%", "")),
    **dict.fromkeys(("c", "css"), ("/*", "*/")),
    "sas": ("*", ";"),
    **dict.fromkeys(("haskell", "lua", "mysql", "psql", "sql"), ("--", "")),
    **dict.fromkeys(("fortran", "fortran95"), ("!", "")),
    "stata": ("*", ""),
    "apl": (chr(0x235D), ""),
}
# The characters R's trimws() takes as space, which divide_chunk trims before it looks for the closing characters.
_R_SPACE = " \t\r\n"


def _r_string_value(text: str) -> Optional[str]:
    """The text of text read as one quoted R string, such as "a\\"b" or 'a', with its escapes undone; None if it isn't one."""
    m = _R_STRING.fullmatch(text)
    if m is None:
        return None
    return re.sub(r"\\(.)", lambda e: {"n": "\n", "t": "\t"}.get(e.group(1), e.group(1)), m.group(2), flags=re.S)


def _option_text(text: str) -> str:
    """
    text as a one-line YAML string for an option line that R's yaml package reads
    back as that string too: yaml_string's, quoted also where that package reads
    plain text as something else (see _R_YAML_NOT_TEXT).
    """
    return yaml_string(text, quote=bool(_R_YAML_NOT_TEXT.fullmatch(text)))


def _r_to_yaml(value: str) -> str:
    """
    value, R code as a chunk header holds it, as the YAML scalar an option
    line ("#| key: value") holds for it, which knitr reads as the same value:
    TRUE, FALSE and NULL as true, false and null, a decimal number as written,
    a quoted R string with no escapes but \\\\, \\", \\', \\n and \\t as a YAML
    string (see _option_text), and any other code tagged !expr, which knitr
    evaluates as R (as a quoted YAML string when it wouldn't read back plain).
    """
    if value in ("TRUE", "FALSE", "NULL"):
        return value.lower()
    if _DECIMAL.fullmatch(value):
        return value
    if _SIMPLE_R_STRING.fullmatch(value):
        return _option_text(_r_string_value(value))
    try:
        loaded = load_yaml(f"k: !expr {value}")
        plain = isinstance(loaded, dict) and isinstance(loaded.get("k"), TaggedScalar) and loaded["k"].value == value
    except (yaml.YAMLError, ValueError):
        plain = False
    return "!expr " + (value if plain else yaml_string(value, quote=True))


class _OptionEntry(NamedTuple):
    key: Optional[str]   # the key as YAML reads it; None for a key that isn't a scalar
    prefix: str          # its first line, without the block's start, up to and including the ":"
    start: int           # lines [start, end) of the chunk's source hold the key and its value
    end: int
    text: str            # those lines as written, without the last line break
    value: object        # the value as YAML reads it on its own; as written if it doesn't read
    written: str         # the value as written after the ":", without surrounding whitespace


class _OptionBlock(NamedTuple):
    start: str                  # what its lines start with: comment characters and "| ", as "#| " or "--| "
    end: str                    # what they end with, as "*/" for c; "" for most engines
    lines: list[str]            # the source lines it is, from the first, each ending with "\n"
    meta: list[str]             # those lines as YAML reads them: without start and end, each ending with "\n"
    entries: list[_OptionEntry]


def _option_extent(language: str, lines: list[str]) -> Optional[tuple[str, str, int]]:
    """
    Which of lines, a chunk's source lines, are its option lines, found as
    knitr's xfun::divide_chunk finds them: (start, end, count), the first count
    lines starting with start, the engine's comment characters and "| " (see
    _OPTION_COMMENTS), or else "#| ", and ending with end ("" for most
    engines). Where those characters open a comment that a line closes
    ("/*| x */" for c), the lines run while they end with end, or else to the
    first that does. None if the first line doesn't start with either.
    """
    if not lines:
        return None
    char, end = _OPTION_COMMENTS.get(language, ("#", ""))
    start = char + "| "
    if not lines[0].startswith(start):
        start, end = "#| ", ""
        if not lines[0].startswith(start):
            return None
    if not end:
        return start, end, next((i for i, line in enumerate(lines) if not line.startswith(start)), len(lines))
    # As divide_chunk counts them with R's which.min() and which.max()
    closed = [line.rstrip(_R_SPACE).endswith(end) for line in lines]
    if closed[0]:
        # Up to the first line not closed; when every line is, its 1:0 is the first line alone
        return start, end, next((i for i, c in enumerate(closed) if not c), 0) or 1
    # Up to the first closed line, or the first line alone if none is
    return start, end, next((i + 1 for i, c in enumerate(closed) if c), 1)


def _option_block(language: str, source: str) -> Optional[_OptionBlock]:
    """
    The option lines a chunk's source starts with (see _option_extent). Their
    text without the comment characters is one YAML document, as knitr and
    Quarto read it when its first line is "key:" (otherwise the lines are R
    key=value text, not read here, and this is None, as it is when the keys
    aren't one per line at the start of a line). Each top-level key is an
    entry, holding its lines up to the next key but for trailing blank and
    comment lines.
    """
    lines = [line.rstrip("\n") + "\n" for line in _lines(source)]
    extent = _option_extent(language, lines)
    if extent is None:
        return None
    start, end, count = extent
    lines = lines[:count]
    meta = []
    for line in lines:
        text = line[:-1]
        text = text[len(start):] if text.startswith(start) else text
        if end and text.rstrip(_R_SPACE).endswith(end):
            # divide_chunk takes as many characters off the end as the closing characters have, spaces after them or not
            text = text[:-len(end)]
        meta.append(text + "\n")
    if not _YAML_OPTIONS.match(meta[0]):
        return None
    _, _, keys = _read_header("".join(meta))
    if keys is None:
        return None
    entries = []
    for key, first, last in _key_spans(meta, keys):
        entry = "".join(meta[first:last])
        written = entry[len(key.prefix):].strip()
        try:
            loaded = load_yaml(entry)
            value = loaded.get(key.name) if isinstance(loaded, dict) else written
        except (yaml.YAMLError, ValueError):
            value = written
        text = "".join(lines[first:last]).rstrip("\n")
        entries.append(_OptionEntry(key.name, key.prefix, first, last, text, value, written))
    return _OptionBlock(start, end, lines, meta, entries)


def _pipe_labels(block: Optional[_OptionBlock]) -> list[tuple[int, str]]:
    """
    Where a chunk's option lines (see _option_block) give its label, as
    (entry, label): block.entries[entry] holds the key "label" or "id" with a
    value. knitr takes label: and else id:, so label: keys come first; one
    with no value gives no label. A value that isn't a string is given as
    written.
    """
    labels: list[tuple[int, str]] = []
    for index, entry in enumerate(block.entries if block else []):
        if entry.key in ("label", "id") and entry.value is not None:
            labels.append((index, entry.value if isinstance(entry.value, str) else entry.written))
    return sorted(labels, key=lambda label: block.entries[label[0]].key != "label")


# ──────────────────────────────────────────────
# Serialization
# ──────────────────────────────────────────────


def serialize(frontmatter: Frontmatter, cells: list[Cell]) -> str:
    """
    Reconstruct the .rmd source text from the parsed model.
    The frontmatter and unmodified cells replay their original raw text; a chunk
    whose label or options alone changed gets a new header line before its raw
    body and closing fence. A part without a trailing newline (the file's last
    line had none) gets one only when another part follows it, so fences never
    run together and an unedited document still round-trips byte for byte.
    A chunk written without a closing fence (see Cell.closed) gets one when
    another part follows it, unless that is a chunk as written in the file
    whose header line ends it, as it did when it was read. Edited cells, header
    lines, that newline and that fence use frontmatter.newline, the document's
    line break, whatever breaks the cell source was given with. A byte order
    mark that parse set aside (frontmatter.bom) goes back at the very start,
    whichever part comes first.
    """
    newline = frontmatter.newline
    texts = [_cell_text(cell, newline) for cell in cells]
    parts: list[str] = [frontmatter.raw] if frontmatter.present else []
    for index, (cell, text) in enumerate(zip(cells, texts)):
        after = next((i for i in range(index + 1, len(cells)) if texts[i]), None)
        if text and after is not None and _needs_closing(cell, cells[after], texts[after]):
            if not text.endswith(("\n", "\r")):
                text += newline
            text = _join([text, _fence_close(cell.fence) + newline], newline)
        parts.append(text)
    out_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if out_parts and not out_parts[-1].endswith(("\n", "\r")):
            out_parts.append(newline)
        out_parts.append(part)
    # _join keeps a lone "\r" ending a part (from a mixed-ending file) apart from a "\n" after it.
    return (_BOM if frontmatter.bom else "") + _join(out_parts, newline)


def _needs_closing(cell: Cell, following: Cell, text: str) -> bool:
    """
    Whether cell, a chunk replayed without a closing fence, needs one before
    following, the next cell written (as text): unless following is a chunk
    replayed from the file whose header line has cell's fence right before its
    {, which knitr ends cell at.
    """
    if cell.cell_type != "code" or cell.dirty or not cell.raw or cell.closed:
        return False
    first = _LINE.match(text).group().rstrip("\r\n")
    ends = following.cell_type == "code" and following.raw and not following.dirty and _KNITR_CHUNK_BEGIN.match(first)
    return not (ends and first.startswith(_fence_close(cell.fence) + "{"))


def _cell_text(cell: Cell, newline: str) -> str:
    """
    A cell as serialize writes it: its raw text if unedited; after label or option
    edits only, a new header line ending in newline, then the raw text's other
    lines; otherwise the cell rendered anew with newline for its line breaks.
    """
    if cell.dirty or not cell.raw:
        return _with_newline(_render_cell(cell), newline)
    if cell.header_dirty:
        header = _render_chunk_header(cell.language, cell.label, cell.options, cell.fence) + newline
        return _join([header, cell.raw[_LINE.match(cell.raw).end():]], newline)
    return cell.raw


def _render_cell(cell: Cell) -> str:
    if cell.cell_type == "markdown":
        # Preserve at least one trailing newline if missing
        src = cell.source
        if src and not src.endswith("\n"):
            src = src + "\n"
        return src
    # code cell: the body its source stands for, so a source ending in "\n" keeps its blank line, under its fence
    header = _render_chunk_header(cell.language, cell.label, cell.options, cell.fence)
    return f"{header}\n{_indented(_chunk_body(cell.source), _fence_indent(cell.fence))}{_fence_close(cell.fence)}\n"


def _render_chunk_header(language: str, label: Optional[str], options: list[tuple[str, str]], fence: str = "```") -> str:
    # An option without a value is a bare name; one with neither name nor value (a lone "=") stays "=".
    parts = [f"{k}={v}" if v or not k else k for k, v in options]
    if label:
        parts.insert(0, label)
    if not parts:
        return fence + "{" + language + "}"
    # A bare name first among the options came after a leading comma, as in ```{r, echo}: the comma is written back,
    # so it reads back as it was (knitr reads it as the label either way).
    lead = " " if label or "=" in parts[0] else ", "
    return fence + "{" + language + lead + ", ".join(parts) + "}"


def _layout(frontmatter: Frontmatter, cells: list[Cell]) -> tuple[Optional[str], list[tuple[int, tuple]]]:
    """
    The document as parse reads back what serialize writes for it: the YAML
    header's text (None without a header), and the cells as (index, shape) pairs,
    index being that of the first cell the shape stands for. A chunk's shape is
    ("code", language, label, options, fence, source). A markdown cell's is ("markdown",
    text), each text ending in a line break, with adjacent markdown cells (and
    text kept after the header's closing fence) joined, as nothing marks where
    one ends, and empty ones left out.
    """
    header = frontmatter.text() if frontmatter.present else None
    entries: list[tuple[int, tuple]] = []
    if frontmatter.present:
        after = "".join(_lines(frontmatter._split()[2])[1:])
        entries.append((0, ("markdown", _with_newline(after, "\n"))))
    for index, cell in enumerate(cells):
        if cell.cell_type == "markdown":
            entries.append((index, ("markdown", cell.source)))
        else:
            entries.append((index, ("code", cell.language, cell.label, tuple(cell.options), cell.fence, cell.source)))
    layout: list[tuple[int, tuple]] = []
    for index, shape in entries:
        if shape[0] == "markdown":
            text = shape[1]
            if not text:
                continue
            text = text if text.endswith("\n") else text + "\n"
            if layout and layout[-1][1][0] == "markdown":
                layout[-1] = (layout[-1][0], ("markdown", layout[-1][1][1] + text))
                continue
            shape = ("markdown", text)
        layout.append((index, shape))
    return header, layout


# ──────────────────────────────────────────────
# Frontmatter YAML: tolerant reading, line-level editing
# ──────────────────────────────────────────────


class TaggedScalar(str):
    """
    A scalar whose tag PyYAML has no constructor for, such as R Markdown's !r and
    !expr. Compares and prints as the tag plus the value, e.g. "!r 1 + 1"; .tag
    and .value hold the two parts, and dump_yaml writes it back as a tag.
    """

    def __new__(cls, tag: str, value: str):
        obj = super().__new__(cls, f"{tag} {value}")
        obj.tag = tag
        obj.value = value
        return obj

    def __getnewargs__(self):
        return (self.tag, self.value)

    def __repr__(self) -> str:
        return f"TaggedScalar({self.tag!r}, {self.value!r})"


# How deep the YAML read here may nest collections, the header mapping itself being one level. PyYAML
# builds and writes nested values recursively, so a few hundred levels exhaust Python's stack; real
# headers nest a few.
_MAX_YAML_DEPTH = 100


class _SafeLoader(yaml.SafeLoader):
    """
    SafeLoader that raises YAMLError, with the value's position, for every value
    it can't build: collections nested more than max_depth levels deep, counting
    the values aliases stand for (see _too_deep), explicitly tagged scalars
    PyYAML's constructors fail on with another exception, such as !!bool maybe
    or !!int "" (see _checked_scalar), and an escape past the last Unicode
    character, such as "\\U00110000".
    """

    max_depth = _MAX_YAML_DEPTH

    def __init__(self, stream):
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent, index):
        if not self.check_event(yaml.events.CollectionStartEvent):
            return super().compose_node(parent, index)
        if self._depth == self.max_depth:
            raise yaml.composer.ComposerError(
                None, None, f"values are nested more than {self.max_depth} levels deep, deeper than this tool reads",
                self.peek_event().start_mark,
            )
        self._depth += 1
        try:
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1

    def construct_document(self, node):
        # Composed nesting is checked above; aliases can nest a value deeper than its text does.
        deep = _too_deep(node, self.max_depth)
        if deep is not None:
            raise yaml.constructor.ConstructorError(
                None, None, f"values are nested more than {self.max_depth} levels deep (counting the values aliases "
                "stand for), deeper than this tool reads", deep.start_mark,
            )
        return super().construct_document(node)

    def scan_flow_scalar_non_spaces(self, double, start_mark):
        try:
            return super().scan_flow_scalar_non_spaces(double, start_mark)
        except ValueError:
            # chr() of a \U escape past U+10FFFF; the mark is at its hex digits.
            raise yaml.scanner.ScannerError(
                "while scanning a double-quoted scalar", start_mark,
                "found an escape past U+10FFFF, the last Unicode character", self.get_mark(),
            ) from None


def _too_deep(root: yaml.Node, limit: int) -> Optional[yaml.Node]:
    """
    The first collection more than limit levels deep in root, the deepest way
    down, or None. An alias is the node it names, so a value an alias stands for
    nests as deep as the alias is, and a merge key's (<<) mapping is a level:
    PyYAML merges, builds and writes values recursively, following aliases.
    Measured without recursion, each node once; a value holding itself
    (&a [*a]) is not followed back into.
    """
    def children(node: yaml.Node):
        return (n for pair in node.value for n in pair) if isinstance(node, yaml.MappingNode) else iter(node.value)

    if not isinstance(root, yaml.nodes.CollectionNode):
        return None
    # How many levels deep each finished collection goes; best is the deepest child so far of those still open.
    heights: dict = {}
    best = {root: 0}
    stack = [(root, children(root))]
    while stack:
        node, rest = stack[-1]
        child = next(rest, None)
        if child is None:
            stack.pop()
            heights[node] = best.pop(node) + 1
            if stack:
                best[stack[-1][0]] = max(best[stack[-1][0]], heights[node])
        elif child in heights:
            best[node] = max(best[node], heights[child])
        elif isinstance(child, yaml.nodes.CollectionNode) and child not in best:
            best[child] = 0
            stack.append((child, children(child)))
    if heights[root] <= limit:
        return None
    # Down the deepest way to the first level past the limit.
    node = root
    for _ in range(limit):
        node = next(c for c in children(node) if heights.get(c, 0) == heights[node] - 1)
    return node


def _checked_scalar(tag: str):
    """
    PyYAML's constructor for the scalar tag !!tag, raising ConstructorError where
    it raises KeyError, IndexError, AttributeError or OverflowError for a value it
    can't read: !!bool maybe, !!int "", !!timestamp hello, a 60-based float too
    big for a float. Its other errors, such as the ValueError of the date
    2026-13-45, pass through, and an int too long to print (from hex, binary or
    60-based digits) raises the ValueError int() raises for a decimal one.
    """
    construct = yaml.SafeLoader.yaml_constructors[f"tag:yaml.org,2002:{tag}"]

    def construct_checked(loader: yaml.SafeLoader, node: yaml.Node):
        try:
            value = construct(loader, node)
        except (KeyError, IndexError, AttributeError, OverflowError):
            shown = node.value if len(node.value) <= 40 else node.value[:37] + "..."
            raise yaml.constructor.ConstructorError(None, None, f"can't read {shown!r} as !!{tag}", node.start_mark) from None
        if type(value) is int:
            # Here, not when the header is shown or compared: str() refuses an int of more than 4300 digits.
            str(value)
        return value

    return construct_checked


for _tag in ("bool", "int", "float", "timestamp"):
    _SafeLoader.add_constructor(f"tag:yaml.org,2002:{_tag}", _checked_scalar(_tag))


class _TolerantLoader(_SafeLoader):
    """_SafeLoader that keeps nodes with unknown tags instead of raising ConstructorError."""


def _construct_unknown_tag(loader: _TolerantLoader, node: yaml.Node):
    if isinstance(node, yaml.ScalarNode):
        return TaggedScalar(node.tag, loader.construct_scalar(node))
    # Tags on collections are rare in R Markdown: keep the content, drop the tag.
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_mapping(node, deep=True)


_TolerantLoader.add_constructor(None, _construct_unknown_tag)


class _ValueLoader(_TolerantLoader):
    """_TolerantLoader for a value to set under a top-level key: one level less deep, as the header mapping is one."""

    max_depth = _MAX_YAML_DEPTH - 1


class _TaggedDumper(yaml.SafeDumper):
    """SafeDumper that writes TaggedScalar values back as tags and multi-line strings as | blocks."""

    def choose_scalar_style(self):
        # SafeDumper quotes every explicitly tagged scalar ("!r '1 + 1'", "!!merge 'x'"); keep it plain
        # ("!r 1 + 1") whenever plain style could hold an untagged value. A scalar whose tag is written
        # whatever its style (neither implicit flag set) is a TaggedScalar, a tag under "!" or under YAML's
        # own tag:yaml.org,2002: prefix (!!merge); a string that plain style would read as something else
        # ('true') has its quoted flag set, and stays quoted.
        style = super().choose_scalar_style()
        analysis = self.analysis
        if (
            style == "'"
            and not self.event.style
            and not any(self.event.implicit)
            and not (self.simple_key_context and (analysis.empty or analysis.multiline))
            and (analysis.allow_flow_plain if self.flow_level else analysis.allow_block_plain)
        ):
            return ""
        return style


_TaggedDumper.add_representer(TaggedScalar, lambda dumper, data: dumper.represent_scalar(data.tag, data.value))
_TaggedDumper.add_representer(
    str, lambda dumper, data: dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|" if "\n" in data else None)
)


def load_yaml(text: str):
    """yaml.safe_load, except that values with unknown tags load as TaggedScalar instead of failing."""
    return yaml.load(text, Loader=_TolerantLoader)


def dump_yaml(data, **kwargs) -> str:
    """Block-style YAML for data in key order; TaggedScalar values are written as tags."""
    return yaml.dump(data, Dumper=_TaggedDumper, sort_keys=False, default_flow_style=False, allow_unicode=True, **kwargs)


def yaml_string(value: str, *, quote: bool = False) -> str:
    """
    value as a one-line YAML scalar that loads back as exactly that string: plain
    when that is safe and quote is false, otherwise double-quoted with escapes.
    """
    if not quote and value:
        try:
            if yaml.load(f"k: {value}", Loader=_SafeLoader) == {"k": value}:
                return value
        except (yaml.YAMLError, ValueError):
            pass
    return yaml.dump(value, Dumper=yaml.SafeDumper, default_style='"', allow_unicode=True, width=float("inf")).rstrip("\n")


# A line break, as knitr (R's readLines) reads them; nothing else ends a line.
_LINE_BREAK = re.compile(r"\r\n?|\n")
# One line with its line break, or a last line without one.
_LINE = re.compile(r"[^\r\n]*(?:\r\n?|\n)|[^\r\n]+")
# A --- fence line, as _extract_frontmatter finds it.
_FENCE_LINE = re.compile(r"---[ \t]*(?:\r\n?|\n)?\Z")
# A column-0 "key:" line, used only for headers that don't parse: a plain or
# quoted key, then ":" followed by a space or the end of the line.
_KEY_LINE = re.compile(r"""("(?:[^"\\\n]|\\.)*"|'(?:[^'\n]|'')*'|[^\s#'"?:,\[\]{}&*!|>%@`-][^:#\n]*?)[ \t]*:(?=[ \t\n]|$)""")
# A YAML document end marker; it also ends the last key's lines.
_DOC_END = re.compile(r"\.\.\.(?:[ \t\r\n]|\Z)")
# Characters YAML treats as line breaks but line-level editing doesn't.
_OTHER_BREAKS = re.compile(r"[\x85\u2028\u2029]")
# The most characters YAML reads a key in before its ":" on a key: value line (an implicit key).
_MAX_IMPLICIT_KEY = 1024


class _Key(NamedTuple):
    name: Optional[str]   # the key's text, unquoted; None for a non-scalar key
    line: int             # index into the header body's lines
    prefix: str           # the key line up to and including its ":"
    value_end: int = -1   # line holding the last character of its value; -1 if unknown (header doesn't parse)


def _lines(text: str) -> list[str]:
    """
    Split text into lines that keep their line break. Only "\\n", "\\r\\n" and a
    lone "\\r" end a line (unlike str.splitlines).
    """
    return _LINE.findall(text)


def _with_newline(text: str, newline: str) -> str:
    """text with every line break ("\\n", "\\r\\n" or a lone "\\r") written as newline."""
    if newline == "\n" and "\r" not in text:
        return text
    return _LINE_BREAK.sub(newline, text)

def _join(parts: list[str], newline: str) -> str:
    """
    parts joined into one text. A part ending in a lone "\\r" (from a mixed-ending
    file), then one starting with "\\n", would read back as one "\\r\\n" line
    break: that "\\r" is written as newline instead, so they stay two line breaks.
    """
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        if out and out[-1].endswith("\r") and part.startswith("\n"):
            out[-1] = out[-1][:-1] + ("\r\n" if newline == "\r" else newline)
        out.append(part)
    return "".join(out)


def _detect_newline(text: str) -> str:
    """
    The line break most lines of text end with: "\\n", "\\r\\n" or "\\r". A tie
    goes to the one used first; text without a line break gets "\\n".
    """
    counts = Counter(_LINE_BREAK.findall(text))
    return counts.most_common(1)[0][0] if counts else "\n"


def _read_header(body: str) -> tuple[dict, Optional[str], Optional[list[_Key]]]:
    """
    Read the YAML between the fences. Returns (data, error, keys):
      data   the parsed mapping, or {} when the header is empty or unreadable
      error  why the header couldn't be read as a YAML mapping, else None
      keys   the top-level keys in order; None when they can't be edited line by
             line (the header isn't a mapping, or not one key per line at
             column 0). For a header that doesn't parse, the lines that look
             like keys.
    Unknown tags such as !r are not errors: they load as TaggedScalar.
    """
    try:
        loader = _TolerantLoader(body)
    except yaml.YAMLError as e:
        # The reader rejects control characters such as a form feed before parsing starts.
        return {}, _yaml_problem(e, body), _guess_keys(_lines(body))
    try:
        try:
            root = loader.get_single_node()
        except yaml.YAMLError as e:
            return {}, _yaml_problem(e, body), _guess_keys(_lines(body))
        if root is None:
            return {}, None, []
        # Before construction, which rewrites merge keys (<<) in place.
        keys = _node_keys(root, body)
        try:
            data = loader.construct_document(root)
        except (yaml.YAMLError, ValueError) as e:
            # Valid YAML holding a value PyYAML can't build, such as the date 2026-13-45. A
            # ValueError has no mark, so the node it came from gives the position.
            index = None if isinstance(e, yaml.YAMLError) else _failed_node_index(loader)
            return {}, _yaml_problem(e, body, index), keys
    finally:
        loader.dispose()
    if not isinstance(data, dict):
        return {}, "it is not a mapping of key: value lines", None
    return data, None, keys


def _failed_node_index(loader: _TolerantLoader) -> Optional[int]:
    """
    The index into the header text where the node loader failed to build (such
    as the date 2026-13-45) starts, or None. PyYAML's construct_object records
    each node it starts building in recursive_objects and drops it once built,
    so after a failure the last node there is the one that failed, whatever
    order PyYAML built the others in.
    """
    node = next(reversed(loader.recursive_objects), None)
    return None if node is None else node.start_mark.index


def _node_keys(root: yaml.Node, body: str) -> Optional[list[_Key]]:
    """The keys of a parsed header, or None unless it is a block mapping with one key per line at column 0."""
    if not isinstance(root, yaml.MappingNode) or root.flow_style:
        return None
    # Where the line breaks are, so finding a position's line is a binary search, not a count from the top
    breaks = [m.start() for m in re.finditer("\n", body)]
    keys: list[_Key] = []
    for key_node, value_node in root.value:
        start, end = key_node.start_mark.index, key_node.end_mark.index
        colon = body.find(":", end)
        if start != body.rfind("\n", 0, start) + 1 or colon < 0 or body[end:colon].strip(" \t"):
            return None
        line = bisect.bisect_left(breaks, start)
        if keys and line <= keys[-1].line:
            return None
        name = key_node.value if isinstance(key_node, yaml.ScalarNode) else None
        keys.append(_Key(name, line, body[start:colon + 1], _value_end_line(value_node, body, breaks)))
    return keys


def _value_end_line(node: yaml.Node, body: str, breaks: list[int]) -> int:
    """
    The line holding the last character of a value node, breaks being the
    positions of body's line breaks. A block collection's end mark lies past the
    comments and blank lines after it, so follow its last entry; a block scalar's
    takes in trailing line breaks, which are skipped. An entry that starts no
    later than its collection is an alias, the node of an anchor written before
    it (or the collection itself): it isn't followed, and the collection's first
    line is given, no later than the alias's own. Each step goes to a node that
    starts later, so the walk stays within the value's text and doesn't loop.
    """
    while isinstance(node, (yaml.MappingNode, yaml.SequenceNode)) and not node.flow_style and node.value:
        last = node.value[-1]
        child = last[1] if isinstance(node, yaml.MappingNode) else last
        if child.start_mark.index <= node.start_mark.index:
            return bisect.bisect_left(breaks, node.start_mark.index)
        node = child
    # The last character that isn't whitespace, as rstrip() finds it, without copying the text before it
    end = node.end_mark.index
    while end > 0 and body[end - 1].isspace():
        end -= 1
    return bisect.bisect_left(breaks, max(end - 1, 0))


def _guess_keys(lines: list[str]) -> list[_Key]:
    """The lines of a header that doesn't parse that look like top-level keys."""
    keys: list[_Key] = []
    for i, line in enumerate(lines):
        m = _KEY_LINE.match(line)
        if not m:
            continue
        name = m.group(1)
        if name[0] in "\"'":
            try:
                name = str(yaml.load(name, Loader=_SafeLoader))
            except (yaml.YAMLError, ValueError):
                pass
        keys.append(_Key(name, i, m.group(0)))
    return keys


def _yaml_problem(e: Exception, body: str, index: Optional[int] = None) -> str:
    """
    A one-line description of a YAML error, with its file line and column when
    known: from the error's mark, else the position of a character the reader
    rejected, else index. body is the header text the error came from, with
    "\\n" line breaks; positions are indexes into it.
    """
    problem = getattr(e, "problem", None) or str(e).split("\n")[0]
    mark = getattr(e, "problem_mark", None)
    if mark is not None:
        index = mark.index
    elif isinstance(e, yaml.reader.ReaderError):
        # The reader rejects a control character before parsing starts: it gives a position, not a mark.
        index = e.position
    if index is None:
        return problem
    # Counted from the index, not the mark's line and column: YAML also takes NEL,
    # U+2028 and U+2029 for line breaks, which the file's lines don't. Header body
    # line 0 is file line 2, after the opening fence (a byte order mark is on line 1).
    line = body.count("\n", 0, index) + 2
    column = index - body.rfind("\n", 0, index)
    return f"{problem} (line {line}, column {column} of the file)"


def _editable_keys(body: list[str]) -> list[_Key]:
    # Line breaks as "\n" for YAML and line counting; each line is still one line.
    _, error, keys = _read_header(_with_newline("".join(body), "\n"))
    if keys is None:
        raise FrontmatterError(
            "Frontmatter can't be edited key by key: "
            + (error or "its keys are not one per line at column 0 (for example a {...} flow mapping)")
        )
    return keys


def _key_spans(lines: list[str], keys: list[_Key]) -> list[tuple[_Key, int, int]]:
    """
    Pair each key with the header lines [start, end) it owns: its own line and
    everything up to the next key or document end marker, minus trailing blank
    lines and column-0 comments, which stay where they are. Lines up to the end
    of the key's value are always kept, such as a quoted string's continuation
    line that starts with "#".
    """
    stops = sorted({k.line for k in keys} | {i for i, line in enumerate(lines) if _DOC_END.match(line)} | {len(lines)})
    spans = []
    for key in keys:
        end = stops[bisect.bisect_right(stops, key.line)]
        while end - 1 > max(key.line, key.value_end) and (not lines[end - 1].strip() or lines[end - 1].startswith("#")):
            end -= 1
        spans.append((key, key.line, end))
    return spans


def _parse_yaml_value(value: str):
    """
    value parsed as YAML when possible, else the string itself. It is to go under
    a top-level key, so it may nest one level less than a header.
    """
    try:
        return yaml.load(value, Loader=_ValueLoader)
    except (yaml.YAMLError, ValueError):
        return value


def _new_key_prefix(key: str) -> str:
    """
    How a new top-level key is written: "key:", quoted when YAML needs it.
    Raises FrontmatterError for a key longer as written than the 1024
    characters YAML reads before the ":" of a key: value line (an implicit key:
    PyYAML and the libyaml in R's yaml package both stop there).
    """
    written = yaml_string(key)
    if len(written) > _MAX_IMPLICIT_KEY:
        shown = key if len(key) <= 40 else key[:37] + "..."
        raise FrontmatterError(
            f"Frontmatter key {shown!r} is {len(written)} characters long as written, and YAML reads a key: value line "
            f"only for a key of up to {_MAX_IMPLICIT_KEY} characters, so the file was left unchanged"
        )
    return written + ":"


def _render_entry(prefix: str, value: str, parsed) -> str:
    """
    The header lines for one key. value is written as given, after the key or as
    an indented block below it, when it means parsed there; otherwise parsed is
    dumped as YAML.
    """
    text = value.strip("\n")
    if text.strip() and not _OTHER_BREAKS.search(text):
        if "\n" in text:
            candidate = f"{prefix}\n{textwrap.indent(textwrap.dedent(text), '  ')}\n"
        else:
            candidate = f"{prefix} {text.strip()}\n"
        if _means(candidate, parsed):
            return candidate
    return prefix + dump_yaml({"k": parsed}, width=float("inf"))[len("k:"):]


def _means(entry: str, parsed) -> bool:
    """Whether entry, a single "key: value" mapping, loads with parsed as its value."""
    try:
        loaded = load_yaml(entry)
    except (yaml.YAMLError, ValueError):
        return False
    if not (isinstance(loaded, dict) and len(loaded) == 1):
        return False
    # Compare dumps, not reprs: a dump writes each shared (anchored) value once, so
    # the cost follows the text's size even when aliases nest. Dumps still tell a
    # TaggedScalar or a date from a str and 1 from 1.0, and match NaN with NaN.
    return dump_yaml(next(iter(loaded.values()))) == dump_yaml(parsed)
