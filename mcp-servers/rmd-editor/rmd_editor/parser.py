"""
R Markdown (.rmd) parser and serializer.

A .rmd file is markdown text that may contain:
  - An optional YAML frontmatter delimited by `---` fences at the very top.
  - Interleaved markdown prose and "executable code chunks" opened by a fence
    of the form  ```{lang [label][, opt1=val1, ...]}  and closed by ``` .
  - Regular markdown code blocks (```python, ``` , etc. — no braces) stay as
    part of the surrounding prose and are NOT treated as cells.

The parser produces:
  - frontmatter: a Frontmatter struct (either parsed YAML dict or raw text)
  - cells: an ordered list of Cell objects with either cell_type="markdown"
    (prose) or cell_type="code" (chunks). Code cells carry language, optional
    label, and option key-value pairs (order-preserving).

Round-trip goal: reading a file and serializing without any edits should
yield byte-identical output. Cells that haven't been edited replay their
original raw text; modified cells regenerate from structured fields.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

import yaml


# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────


@dataclass
class Frontmatter:
    """YAML frontmatter at the top of the document, if any."""
    data: dict = field(default_factory=dict)   # parsed YAML
    raw: str = ""                              # original text between the --- fences (inclusive)
    present: bool = False
    dirty: bool = False                        # True after any structural edit

    def mark_dirty(self) -> None:
        self.dirty = True


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
    yaml_body = text[search_from:close_match.start()]
    try:
        parsed = yaml.safe_load(yaml_body) or {}
        if not isinstance(parsed, dict):
            parsed = {}
    except yaml.YAMLError:
        parsed = {}
    fm.data = parsed
    fm.raw = text[0:close_match.end()]
    fm.present = True
    return fm, close_match.end()


def _split_body(body: str) -> list[Cell]:
    """
    Walk body line by line, splitting into markdown prose cells and code chunks.
    Each cell's raw text preserves its original newlines so serialization can
    replay unchanged cells byte-for-byte.
    """
    cells: list[Cell] = []
    lines = body.splitlines(keepends=True)
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
    Unmodified frontmatter/cells replay their original raw text.
    """
    out_parts: list[str] = []
    if frontmatter.present:
        if frontmatter.dirty or not frontmatter.raw:
            out_parts.append(_render_frontmatter(frontmatter.data))
        else:
            out_parts.append(frontmatter.raw)
    for cell in cells:
        if cell.dirty or not cell.raw:
            out_parts.append(_render_cell(cell))
        else:
            out_parts.append(cell.raw)
    return "".join(out_parts)


def _render_frontmatter(data: dict) -> str:
    if not data:
        return "---\n---\n\n"
    yaml_body = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return f"---\n{yaml_body}---\n\n"


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
