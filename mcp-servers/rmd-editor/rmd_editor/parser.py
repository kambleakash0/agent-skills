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
"""
from __future__ import annotations

import re
import textwrap
from collections import OrderedDict
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
    !expr) and key order elsewhere in the header stay byte for byte.
    """
    data: dict = field(default_factory=dict)   # parsed YAML, unknown tags as TaggedScalar; {} if unreadable
    raw: str = ""                              # original text between the --- fences (inclusive)
    present: bool = False
    error: Optional[str] = None                # why the header couldn't be read as a YAML mapping, else None

    def text(self) -> str:
        """The YAML between the --- fences."""
        return "".join(self._split()[1]) if self.present else ""

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
        parsed = _parse_yaml_value(value)
        if not self.present:
            self._commit(key, "---\n" + _render_entry(_new_key_prefix(key), value, parsed) + "---\n", [key])
            return
        head, body, tail = self._split()
        keys = _editable_keys(body)
        names = [k.name for k in keys]
        spans = [span for span in _key_spans(body, keys) if span[0].name == key]
        lines = list(body)
        if not spans:
            # Before a document end marker ("..."), if the header has one.
            at = next((i for i, line in enumerate(lines) if _DOC_END.match(line)), len(lines))
            lines.insert(at, _render_entry(_new_key_prefix(key), value, parsed))
            self._commit(key, head + "".join(lines) + tail, names + [key])
            return
        (first, start, end), repeats = spans[0], spans[1:]
        # Leave one copy holding the new value: YAML readers either keep the last copy or reject repeats.
        for _, repeat_start, repeat_end in reversed(repeats):
            del lines[repeat_start:repeat_end]
        lines[start:end] = [_render_entry(first.prefix, value, parsed)]
        kept = keys.index(first)
        self._commit(key, head + "".join(lines) + tail, [n for i, n in enumerate(names) if n != key or i == kept])

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
        self._commit(key, head + "".join(lines) + tail, [k.name for k in keys if k.name != key])

    def _split(self) -> tuple[str, list[str], str]:
        """raw as (opening fence line, header body lines, closing fence line plus anything after it)."""
        lines = _lines(self.raw)
        close = next(i for i in range(1, len(lines)) if _FENCE_LINE.match(lines[i]))
        return lines[0], lines[1:close], "".join(lines[close:])

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
    source: str                                # body only (no fences, no frontmatter markers)
    # Code-cell-only fields
    language: str = "r"                        # "r", "python", "bash", "sql", ... for code cells
    label: Optional[str] = None                # chunk label, e.g. "setup" in  ```{r setup, echo=FALSE}
    options: "OrderedDict[str, str]" = field(default_factory=OrderedDict)
    # Bookkeeping
    raw: str = ""                              # original full text (with fences / prose newlines)
    dirty: bool = False                        # True after any structural edit

    def mark_dirty(self) -> None:
        self.dirty = True


# ──────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────


_CHUNK_OPEN = re.compile(r"^```\{\s*([A-Za-z][A-Za-z0-9_]*)\s*(.*?)\s*\}\s*$")
_CODE_FENCE = re.compile(r"^```")


def parse(text: str) -> tuple[Frontmatter, list[Cell]]:
    """
    Parse the text of an .rmd document into a Frontmatter and an ordered list
    of Cells. Byte-level round-trip is preserved on unmodified parse-then-
    serialize cycles.
    """
    frontmatter, body_start_idx = _extract_frontmatter(text)
    body = text[body_start_idx:]
    cells = _split_body(body)
    return frontmatter, cells


def _extract_frontmatter(text: str) -> tuple[Frontmatter, int]:
    """Return (Frontmatter, index into text where body begins)."""
    fm = Frontmatter()
    # Must start with `---` on its own line (optionally with trailing whitespace and a newline)
    m = re.match(r"^---[ \t]*\n", text)
    if not m:
        return fm, 0
    # Find the closing `---` on its own line
    # Search starting after the opening fence
    search_from = m.end()
    close_pat = re.compile(r"^---[ \t]*(?:\n|$)", re.MULTILINE)
    close_match = close_pat.search(text, search_from)
    if close_match is None:
        return fm, 0  # Unterminated frontmatter -- treat whole thing as body
    fm.data, fm.error, _ = _read_header(text[search_from:close_match.start()])
    fm.raw = text[0:close_match.end()]
    fm.present = True
    return fm, close_match.end()


def _split_body(body: str) -> list[Cell]:
    """
    Walk body line by line, splitting into markdown prose cells and code chunks.
    Each cell's raw text preserves its original newlines so serialization can
    replay unchanged cells byte-for-byte. Only "\\n" ends a line, as for knitr:
    form feeds, U+2028 and the other breaks str.splitlines knows stay inside a
    line, so every cell but the last ends with "\\n". (Files are read with
    universal newlines, so "\\r\\n" and "\\r" arrive as "\\n".)
    """
    cells: list[Cell] = []
    lines = _lines(body)
    i = 0
    n = len(lines)
    # Buffer for accumulating prose lines
    prose_buf: list[str] = []

    def flush_prose():
        if prose_buf:
            raw = "".join(prose_buf)
            cells.append(Cell(cell_type="markdown", source=raw, raw=raw))
            prose_buf.clear()

    while i < n:
        line = lines[i]
        open_m = _CHUNK_OPEN.match(line.rstrip("\n"))
        if open_m:
            flush_prose()
            lang = open_m.group(1)
            inside = open_m.group(2)
            label, options = _parse_label_and_options(inside)
            # Find the closing fence
            j = i + 1
            chunk_body_lines: list[str] = []
            while j < n:
                # Closing ``` on its own line (no braces)
                if _CODE_FENCE.match(lines[j].rstrip("\n")) and not _CHUNK_OPEN.match(lines[j].rstrip("\n")):
                    # Only accept as a CLOSE if it's a bare ``` (or ``` followed by whitespace)
                    if re.match(r"^```[ \t]*$", lines[j].rstrip("\n")):
                        break
                chunk_body_lines.append(lines[j])
                j += 1
            # j now points at the closing fence line, OR == n (unterminated)
            if j >= n:
                # Unterminated chunk -- fall back: treat the whole remainder as prose
                prose_buf.append(lines[i])
                for k in range(i + 1, n):
                    prose_buf.append(lines[k])
                flush_prose()
                return cells
            # Construct the Cell
            source = "".join(chunk_body_lines)
            # Strip exactly one trailing newline from source so the closing fence line stays outside
            if source.endswith("\n"):
                source_no_trailing_nl = source[:-1]
            else:
                source_no_trailing_nl = source
            raw = lines[i] + source + lines[j]
            cells.append(Cell(
                cell_type="code",
                source=source_no_trailing_nl,
                language=lang,
                label=label,
                options=options,
                raw=raw,
            ))
            i = j + 1
        else:
            prose_buf.append(line)
            i += 1
    flush_prose()
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
    document still round-trips byte for byte.
    """
    parts: list[str] = [frontmatter.raw] if frontmatter.present else []
    for cell in cells:
        parts.append(_render_cell(cell) if cell.dirty or not cell.raw else cell.raw)
    out_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if out_parts and not out_parts[-1].endswith("\n"):
            out_parts.append("\n")
        out_parts.append(part)
    return "".join(out_parts)


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


# A closing --- fence line, as _extract_frontmatter finds it.
_FENCE_LINE = re.compile(r"---[ \t]*\n?\Z")
# A column-0 "key:" line, used only for headers that don't parse: a plain or
# quoted key, then ":" followed by a space or the end of the line.
_KEY_LINE = re.compile(r"""("(?:[^"\\\n]|\\.)*"|'(?:[^'\n]|'')*'|[^\s#'"?:,\[\]{}&*!|>%@`-][^:#\n]*?)[ \t]*:(?=[ \t\n]|$)""")
# A YAML document end marker; it also ends the last key's lines.
_DOC_END = re.compile(r"\.\.\.(?:[ \t]|$)")
# Characters YAML treats as line breaks but line-level editing doesn't.
_OTHER_BREAKS = re.compile(r"[\r\x85\u2028\u2029]")


class _Key(NamedTuple):
    name: Optional[str]   # the key's text, unquoted; None for a non-scalar key
    line: int             # index into the header body's lines
    prefix: str           # the key line up to and including its ":"
    value_end: int = -1   # line holding the last character of its value; -1 if unknown (header doesn't parse)


def _lines(text: str) -> list[str]:
    """Split text into lines that keep their newline. Only "\\n" ends a line (unlike str.splitlines)."""
    lines = text.split("\n")
    return [line + "\n" for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])


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
    loader = _TolerantLoader(body)
    try:
        try:
            root = loader.get_single_node()
        except yaml.YAMLError as e:
            return {}, _yaml_problem(e), _guess_keys(_lines(body))
        if root is None:
            return {}, None, []
        # Before construction, which rewrites merge keys (<<) in place.
        keys = _node_keys(root, body)
        try:
            data = loader.construct_document(root)
        except (yaml.YAMLError, ValueError) as e:
            # Valid YAML holding a value PyYAML can't build, such as the date 2026-13-45.
            return {}, _yaml_problem(e), keys
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


def _yaml_problem(e: Exception) -> str:
    """A one-line description of a YAML error, with its file line number when known."""
    problem = getattr(e, "problem", None) or str(e).split("\n")[0]
    mark = getattr(e, "problem_mark", None)
    # Header body line 0 is file line 2, after the opening fence.
    return f"{problem} (line {mark.line + 2} of the file)" if mark is not None else problem


def _editable_keys(body: list[str]) -> list[_Key]:
    _, error, keys = _read_header("".join(body))
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
