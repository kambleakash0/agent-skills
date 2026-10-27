"""
R Markdown (.rmd) parser and serializer.

A .rmd file is markdown text that may contain:
  - An optional YAML frontmatter delimited by `---` fences at the very top.
  - Interleaved markdown prose and "executable code chunks" opened by a fence
    of the form  ```{lang [label][, opt1=val1, ...]}  and closed by ``` .
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
original raw text; modified cells regenerate from structured fields. The
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

import re
import textwrap
from collections import Counter, OrderedDict
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
    source: str                                # body only (no fences, no frontmatter markers), "\n" line breaks
    # Code-cell-only fields
    language: str = "r"                        # "r", "python", "bash", "sql", ... for code cells
    label: Optional[str] = None                # chunk label, e.g. "setup" in  ```{r setup, echo=FALSE}
    options: "OrderedDict[str, str]" = field(default_factory=OrderedDict)
    # Bookkeeping
    raw: str = ""                              # original full text (with fences and the file's own line breaks)
    dirty: bool = False                        # True after any structural edit

    def mark_dirty(self) -> None:
        self.dirty = True


# ──────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────


_CHUNK_OPEN = re.compile(r"^```\{\s*([A-Za-z][A-Za-z0-9_]*)\s*(.*?)\s*\}\s*$")
_CODE_FENCE = re.compile(r"^```")

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
    cells = _split_body(body)
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


def _split_body(body: str) -> list[Cell]:
    """
    Walk body line by line, splitting into markdown prose cells and code chunks.
    Each cell's raw text preserves its original line breaks so serialization can
    replay unchanged cells byte-for-byte; its source has "\\n" breaks. Only
    "\\n", "\\r\\n" and a lone "\\r" end a line, as for knitr (R's readLines):
    form feeds, U+2028 and the other breaks str.splitlines knows stay inside a
    line, so every cell but the last ends with a line break.
    """
    cells: list[Cell] = []
    lines = _lines(body)
    # The same lines ending in "\n": fences are matched, and sources built, on these.
    plain = [_with_newline(line, "\n") for line in lines]
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
        open_m = _CHUNK_OPEN.match(plain[i].rstrip("\n"))
        if open_m:
            flush_prose(i)
            lang = open_m.group(1)
            inside = open_m.group(2)
            label, options = _parse_label_and_options(inside)
            # Find the closing fence
            j = i + 1
            while j < n:
                # Closing ``` on its own line (no braces)
                if _CODE_FENCE.match(plain[j].rstrip("\n")) and not _CHUNK_OPEN.match(plain[j].rstrip("\n")):
                    # Only accept as a CLOSE if it's a bare ``` (or ``` followed by whitespace)
                    if re.match(r"^```[ \t]*$", plain[j].rstrip("\n")):
                        break
                j += 1
            # j now points at the closing fence line, OR == n (unterminated)
            if j >= n:
                # Unterminated chunk -- fall back: treat the whole remainder as prose
                flush_prose(n)
                return cells
            # Construct the Cell
            source = "".join(plain[i + 1:j])
            # Strip exactly one trailing newline from source so the closing fence line stays outside
            if source.endswith("\n"):
                source_no_trailing_nl = source[:-1]
            else:
                source_no_trailing_nl = source
            cells.append(Cell(
                cell_type="code",
                source=source_no_trailing_nl,
                language=lang,
                label=label,
                options=options,
                raw="".join(lines[i:j + 1]),
            ))
            i = j + 1
            prose_start = i
        else:
            i += 1
    flush_prose(n)
    return cells


# ──────────────────────────────────────────────
# Chunk header parsing
# ──────────────────────────────────────────────


def _parse_label_and_options(inside: str) -> tuple[Optional[str], "OrderedDict[str, str]"]:
    """
    Given the text between `{r ` and `}` (e.g. `label, echo=FALSE, fig.width=7`),
    return (label, options). Label is the first bare token without '='.
    Options preserve insertion order.
    """
    label: Optional[str] = None
    options: "OrderedDict[str, str]" = OrderedDict()
    parts = _split_top_level_commas(inside)
    for idx, part in enumerate(parts):
        if not part:
            continue
        if "=" not in part:
            # Bare token -- if this is the first part and we don't have a label yet, it's the label
            if idx == 0 and label is None:
                label = part.strip()
            # Otherwise it's a stray bare flag; stash as key with empty value
            else:
                options[part.strip()] = ""
        else:
            k, _, v = part.partition("=")
            options[k.strip()] = v.strip()
    return label, options


def _split_top_level_commas(s: str) -> list[str]:
    """Split on commas that aren't nested inside (), [], {}, or quotes."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    quote: Optional[str] = None
    for c in s:
        if quote is not None:
            buf.append(c)
            if c == quote:
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
    return parts


# ──────────────────────────────────────────────
# Serialization
# ──────────────────────────────────────────────


def serialize(frontmatter: Frontmatter, cells: list[Cell]) -> str:
    """
    Reconstruct the .rmd source text from the parsed model.
    The frontmatter and unmodified cells replay their original raw text. A part
    without a trailing newline (the file's last line had none) gets one only when
    another part follows it, so fences never run together and an unedited
    document still round-trips byte for byte. Edited cells and that newline use
    frontmatter.newline, the document's line break, whatever breaks the cell
    source was given with. A byte order mark that parse set aside
    (frontmatter.bom) goes back at the very start, whichever part comes first.
    """
    newline = frontmatter.newline
    parts: list[str] = [frontmatter.raw] if frontmatter.present else []
    for cell in cells:
        parts.append(_with_newline(_render_cell(cell), newline) if cell.dirty or not cell.raw else cell.raw)
    out_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if out_parts and not out_parts[-1].endswith(("\n", "\r")):
            out_parts.append(newline)
        out_parts.append(part)
    # _join keeps a lone "\r" ending a part (from a mixed-ending file) apart from a "\n" after it.
    return (_BOM if frontmatter.bom else "") + _join(out_parts, newline)


def _render_cell(cell: Cell) -> str:
    if cell.cell_type == "markdown":
        # Preserve at least one trailing newline if missing
        src = cell.source
        if src and not src.endswith("\n"):
            src = src + "\n"
        return src
    # code cell
    header = _render_chunk_header(cell.language, cell.label, cell.options)
    body = cell.source
    if body and not body.endswith("\n"):
        body = body + "\n"
    elif not body:
        body = ""
    return f"{header}\n{body}```\n"


def _render_chunk_header(language: str, label: Optional[str], options: "OrderedDict[str, str]") -> str:
    parts: list[str] = []
    if label:
        parts.append(label)
    for k, v in options.items():
        parts.append(k if v == "" else f"{k}={v}")
    if parts:
        return "```{" + language + " " + ", ".join(parts) + "}"
    return "```{" + language + "}"


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


class _TolerantLoader(yaml.SafeLoader):
    """SafeLoader that keeps nodes with unknown tags instead of raising ConstructorError."""


def _construct_unknown_tag(loader: _TolerantLoader, node: yaml.Node):
    if isinstance(node, yaml.ScalarNode):
        return TaggedScalar(node.tag, loader.construct_scalar(node))
    # Tags on collections are rare in R Markdown: keep the content, drop the tag.
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_mapping(node, deep=True)


_TolerantLoader.add_constructor(None, _construct_unknown_tag)


class _TaggedDumper(yaml.SafeDumper):
    """SafeDumper that writes TaggedScalar values back as tags and multi-line strings as | blocks."""

    def choose_scalar_style(self):
        # SafeDumper quotes every explicitly tagged scalar ("!r '1 + 1'"); keep it
        # plain ("!r 1 + 1") whenever plain style could hold an untagged value.
        style = super().choose_scalar_style()
        analysis = self.analysis
        if (
            style == "'"
            and not self.event.style
            and (self.event.tag or "").startswith("!")
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
            if yaml.safe_load(f"k: {value}") == {"k": value}:
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
            # Valid YAML holding a value PyYAML can't build, such as the date 2026-13-45.
            return {}, _yaml_problem(e, body), keys
    finally:
        loader.dispose()
    if not isinstance(data, dict):
        return {}, "it is not a mapping of key: value lines", None
    return data, None, keys


def _node_keys(root: yaml.Node, body: str) -> Optional[list[_Key]]:
    """The keys of a parsed header, or None unless it is a block mapping with one key per line at column 0."""
    if not isinstance(root, yaml.MappingNode) or root.flow_style:
        return None
    keys: list[_Key] = []
    for key_node, value_node in root.value:
        start, end = key_node.start_mark.index, key_node.end_mark.index
        colon = body.find(":", end)
        if start != body.rfind("\n", 0, start) + 1 or colon < 0 or body[end:colon].strip(" \t"):
            return None
        line = body.count("\n", 0, start)
        if keys and line <= keys[-1].line:
            return None
        name = key_node.value if isinstance(key_node, yaml.ScalarNode) else None
        keys.append(_Key(name, line, body[start:colon + 1], _value_end_line(value_node, body)))
    return keys


def _value_end_line(node: yaml.Node, body: str) -> int:
    """
    The line holding the last character of a value node. A block collection's end
    mark lies past the comments and blank lines after it, so follow its last entry;
    a block scalar's takes in trailing line breaks, which are skipped.
    """
    while isinstance(node, (yaml.MappingNode, yaml.SequenceNode)) and not node.flow_style and node.value:
        last = node.value[-1]
        node = last[1] if isinstance(node, yaml.MappingNode) else last
    end = len(body[:node.end_mark.index].rstrip())
    return body.count("\n", 0, max(end - 1, 0))


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
                name = str(yaml.safe_load(name))
            except yaml.YAMLError:
                pass
        keys.append(_Key(name, i, m.group(0)))
    return keys


def _yaml_problem(e: Exception, body: str) -> str:
    """
    A one-line description of a YAML error, with its file line number when known.
    body is the header text the error came from, with "\\n" line breaks.
    """
    problem = getattr(e, "problem", None) or str(e).split("\n")[0]
    mark = getattr(e, "problem_mark", None)
    if mark is None:
        return problem
    # Counted from the mark's index, not its line: YAML also takes NEL, U+2028 and
    # U+2029 for line breaks, which the file's lines don't. Header body line 0 is
    # file line 2, after the opening fence.
    line = body.count("\n", 0, mark.index) + 2
    return f"{problem} (line {line} of the file)"


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
        end = next(stop for stop in stops if stop > key.line)
        while end - 1 > max(key.line, key.value_end) and (not lines[end - 1].strip() or lines[end - 1].startswith("#")):
            end -= 1
        spans.append((key, key.line, end))
    return spans


def _parse_yaml_value(value: str):
    """value parsed as YAML when possible, else the string itself."""
    try:
        return load_yaml(value)
    except (yaml.YAMLError, ValueError):
        return value


def _new_key_prefix(key: str) -> str:
    """How a new top-level key is written: "key:", quoted when YAML needs it."""
    return yaml_string(key) + ":"


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
