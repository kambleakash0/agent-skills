"""
Test suite for rmd-editor MCP server.

Uses programmatic fixtures — no static files. Actual R kernel execution is not
exercised (IRkernel isn't guaranteed to be installed), but kernel_name mapping
is verified. Every file the tests write lives in a temporary directory that
__main__ creates and always removes, so a crash can't leave files behind in tests/.
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import queue
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rmd_editor.manager import RmdManager, RmdManagerError, create_rmd, _language_to_kernel_name
from rmd_editor.parser import parse, serialize

# Scratch directory for every file the tests write; set in __main__ via tempfile.mkdtemp()
WORK_DIR = None
FIXTURE_PATH = None

PASS = 0
FAIL = 0


def check(label: str, result, expected) -> None:
    global PASS, FAIL
    if isinstance(result, str) and isinstance(expected, str):
        ok = expected in result
    else:
        ok = result == expected
    if ok:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        print(f"     Expected: {expected!r}")
        print(f"     Got:      {result!r}")
        FAIL += 1

@contextlib.contextmanager
def captured_logs(*names: str):
    """
    Send every log record to a buffer instead of stderr while the block runs, with
    the named loggers (some are quieted in __main__) at their default level.
    Yields the buffer; each record is formatted as "LEVEL logger: message".
    """
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    loggers = [logging.getLogger(name) for name in names]
    saved_levels = [lg.level for lg in loggers]
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for lg in loggers:
        lg.setLevel(logging.NOTSET)
    try:
        yield buf
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        for lg, level in zip(loggers, saved_levels):
            lg.setLevel(level)


def wait_until(predicate, timeout: float = 10.0) -> bool:
    """Poll predicate() until it is true or timeout seconds pass; returns its last value."""
    deadline = time.time() + timeout
    while not predicate():
        if time.time() > deadline:
            return False
        time.sleep(0.02)
    return True


def in_thread(fn, *args, **kwargs):
    """Run fn in a new thread; returns (thread, result) where result gets 'value' or 'error'."""
    result: dict = {}

    def target():
        try:
            result["value"] = fn(*args, **kwargs)
        except Exception as e:
            result["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, result

def check_same(label: str, got: str, want: str) -> None:
    """Exact text comparison (check() only tests substrings); prints a line diff when they differ."""
    check(label, got == want, True)
    if got != want:
        import difflib
        for line in difflib.unified_diff(want.splitlines(True), got.splitlines(True), "expected", "got"):
            print(f"     {line.rstrip(chr(10))}")


def write_doc(name: str, text: str) -> str:
    """Write text to WORK_DIR/name and return the path."""
    path = os.path.join(WORK_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def read_doc(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()

def write_raw(name: str, text: str) -> str:
    """Write text to WORK_DIR/name with its line breaks exactly as given and return the path."""
    path = os.path.join(WORK_DIR, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def read_raw(path: str) -> str:
    """The file's text with its line breaks as written (read_doc reads "\\r\\n" as "\\n")."""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()

def read_bytes(path: str) -> bytes:
    """The file's bytes, byte order mark included."""
    with open(path, "rb") as f:
        return f.read()


def lone_newlines(text: str) -> int:
    """How many "\\n" in text are not part of a "\\r\\n"."""
    return text.replace("\r\n", "").count("\n")


@contextlib.contextmanager
def env_vars(**values):
    """Set environment variables for the block (None unsets one), then restore them."""
    saved = {name: os.environ.get(name) for name in values}

    def apply(settings):
        for name, value in settings.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    apply(values)
    try:
        yield
    finally:
        apply(saved)


SAMPLE = """---
title: "Sample"
author: "Akash"
output: html_document
---

# Introduction

Some prose here.

```{r setup, include=FALSE}
knitr::opts_chunk$set(echo = TRUE)
```

More prose.

```{r analysis, echo=FALSE, fig.width=7}
x <- 1:10
plot(x)
```

```{python}
import numpy as np
```

Final prose.
"""


def reset_fixture() -> str:
    with open(FIXTURE_PATH, "w", encoding="utf-8") as f:
        f.write(SAMPLE)
    return FIXTURE_PATH


# ──────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────


def test_parser_round_trip():
    print("\n═══ parser round-trip ═══")
    fm, cells = parse(SAMPLE)
    check("frontmatter present", fm.present, True)
    check("frontmatter title", str(fm.data.get("title")), "Sample")
    check("cell count", len(cells), 7)
    check("cell 0 is markdown", cells[0].cell_type, "markdown")
    check("cell 1 is r chunk", cells[1].cell_type, "code")
    check("cell 1 language is r", cells[1].language, "r")
    check("cell 1 label is setup", cells[1].label, "setup")
    check("cell 1 include=FALSE", cells[1].options.get("include"), "FALSE")
    check("cell 3 echo=FALSE", cells[3].options.get("echo"), "FALSE")
    check("cell 3 fig.width=7", cells[3].options.get("fig.width"), "7")
    check("cell 5 is python", cells[5].language, "python")
    check("cell 5 has no label", cells[5].label, None)
    out = serialize(fm, cells)
    check("serialize round-trips byte-identical", out, SAMPLE)


def test_parser_edge_cases():
    print("\n═══ parser edge cases ═══")
    # Empty file
    fm, cells = parse("")
    check("empty file: no frontmatter", fm.present, False)
    check("empty file: no cells", len(cells), 0)
    # Prose only
    fm, cells = parse("Just prose.\n")
    check("prose only: 1 cell", len(cells), 1)
    check("prose only: markdown type", cells[0].cell_type, "markdown")
    # Single chunk, no label or options
    fm, cells = parse("```{r}\nx <- 1\n```\n")
    check("bare chunk: 1 cell", len(cells), 1)
    check("bare chunk: no label", cells[0].label, None)
    check("bare chunk: no options", len(cells[0].options), 0)
    check("bare chunk: source", cells[0].source, "x <- 1")
    # Chunk with label only
    fm, cells = parse("```{r mylabel}\ny <- 2\n```\n")
    check("label only: label=mylabel", cells[0].label, "mylabel")
    check("label only: no options", len(cells[0].options), 0)
    # Chunk with options, no label
    fm, cells = parse("```{r echo=FALSE}\nz <- 3\n```\n")
    check("no label: label is None", cells[0].label, None)
    check("no label: echo=FALSE option", cells[0].options.get("echo"), "FALSE")
    # Regular markdown code fence (NOT an rmarkdown chunk) stays in prose
    fm, cells = parse("```python\nprint('hi')\n```\n")
    check("markdown fence stays prose: 1 cell", len(cells), 1)
    check("markdown fence stays prose: markdown type", cells[0].cell_type, "markdown")


def test_parser_complex_options():
    print("\n═══ parser complex options ═══")
    src = '```{r foo, fig.cap="A, B", eval=(x > 0)}\ncode()\n```\n'
    fm, cells = parse(src)
    check("complex: label=foo", cells[0].label, "foo")
    check("complex: fig.cap preserves quoted comma", cells[0].options.get("fig.cap"), '"A, B"')
    check("complex: eval preserves parens", cells[0].options.get("eval"), "(x > 0)")
    out = serialize(fm, cells)
    check("complex: round-trip", out, src)

def test_no_trailing_newline():
    print("\n═══ documents without a trailing newline ═══")

    def cells_of(path):
        return [(c.cell_type, c.source) for c in RmdManager(path).cells]

    # Untouched documents still round-trip byte for byte
    for text in ("# Intro\n\n```{r}\nx <- 1\n```", "```{r}\nx\n```\n\nlast prose", "---\ntitle: x\n---", "---\ntitle: x\n---\nprose"):
        fm, cells = parse(text)
        check(f"no newline: untouched {text!r} round-trips", serialize(fm, cells) == text, True)

    # move_cell: the newline-less last chunk moves to the front
    path = write_doc("no_newline.rmd", "# Intro\n\n```{r}\nx <- 1\n```")
    RmdManager(path).move_cell(1, 0)
    check_same("no newline: move last to first keeps the fence on its own line", read_doc(path), "```{r}\nx <- 1\n```\n# Intro\n\n")
    check("no newline: move last to first reparses", cells_of(path), [("code", "x <- 1"), ("markdown", "# Intro\n\n")])
    # move_cell: another cell moves past newline-less prose
    path = write_doc("no_newline.rmd", "```{r}\na\n```\n\ntail")
    RmdManager(path).move_cell(0, -1)
    check("no newline: move first to last reparses", cells_of(path), [("markdown", "\ntail\n"), ("code", "a")])

    # add_cell(-1) after a newline-less chunk, prose, or header
    path = write_doc("no_newline.rmd", "```{r}\nx\n```")
    RmdManager(path).add_cell(-1, "y")
    check_same("no newline: add after last chunk", read_doc(path), "```{r}\nx\n```\n```{r}\ny\n```\n")
    check("no newline: add after last chunk reparses", cells_of(path), [("code", "x"), ("code", "y")])
    path = write_doc("no_newline.rmd", "```{r}\nx\n```\n\nlast prose")
    RmdManager(path).add_cell(-1, "y")
    check("no newline: add after last prose reparses", cells_of(path), [("code", "x"), ("markdown", "\nlast prose\n"), ("code", "y")])
    path = write_doc("no_newline.rmd", "```{r}\nx\n```")
    RmdManager(path).add_cell(-1, "More prose", cell_type="markdown")
    check("no newline: markdown added after last chunk reparses", cells_of(path), [("code", "x"), ("markdown", "More prose\n")])
    path = write_doc("no_newline.rmd", "---\ntitle: x\n---")
    RmdManager(path).add_cell(-1, "y")
    check_same("no newline: add after a header at end of file", read_doc(path), "---\ntitle: x\n---\n```{r}\ny\n```\n")
    mgr = RmdManager(path)
    check("no newline: header kept after add", (mgr.frontmatter.data, cells_of(path)), ({"title": "x"}, [("code", "y")]))

    # split_cell / merge_cells next to a newline-less last cell
    path = write_doc("no_newline.rmd", "```{r}\na\nb\n```\n```{r}\nc\n```")
    RmdManager(path).split_cell(0, 1)
    check("no newline: split before the last cell reparses", cells_of(path), [("code", "a"), ("code", "b"), ("code", "c")])
    check("no newline: untouched last cell keeps its missing newline", read_doc(path).endswith("```{r}\nc\n```"), True)
    path = write_doc("no_newline.rmd", "```{r}\na\nb\n```")
    RmdManager(path).split_cell(0, 1)
    check("no newline: split of the last cell reparses", cells_of(path), [("code", "a"), ("code", "b")])
    path = write_doc("no_newline.rmd", "```{r}\na\n```\n```{r}\nb\n```")
    RmdManager(path).merge_cells(0, 1)
    check("no newline: merge into the last cell reparses", cells_of(path), [("code", "a\nb")])
    path = write_doc("no_newline.rmd", "```{r}\na\n```\n```{r}\nb\n```\ntail")
    RmdManager(path).merge_cells(0, 1)
    check_same("no newline: merge before newline-less prose", read_doc(path), "```{r}\na\nb\n```\ntail")

    # Rewriting the last cell's text ends the file with a newline; re-saving the same text or an option edit doesn't
    path = write_doc("no_newline.rmd", "```{r}\nx\n```\nlast")
    RmdManager(path).replace_cell_source(1, "last")
    check_same("no newline: re-saving the last cell's own text keeps it", read_doc(path), "```{r}\nx\n```\nlast")
    RmdManager(path).replace_cell_source(1, "z")
    check_same("no newline: new text in the last cell adds a final newline", read_doc(path), "```{r}\nx\n```\nz\n")
    path = write_doc("no_newline.rmd", "```{r}\nx\n```")
    RmdManager(path).set_chunk_option(0, "echo", "FALSE")
    check_same("no newline: an option edit on the last chunk keeps it", read_doc(path), "```{r echo=FALSE}\nx\n```")
    RmdManager(path).append_to_cell(0, "y")
    check_same("no newline: appending to the last chunk adds a final newline", read_doc(path), "```{r echo=FALSE}\nx\ny\n```\n")


def test_line_breaks():
    print("\n═══ only a newline ends a line ═══")
    # As for knitr: the other breaks str.splitlines knows (vertical tab, form feed, U+001C, NEL,
    # U+2028, U+2029) stay inside the line, so a fence after one is not a chunk
    for code in (0x0B, 0x0C, 0x1C, 0x85, 0x2028, 0x2029):
        text = "---\ntitle: x\n---\n\nIntro" + chr(code) + "```{r}\nx\n```\n"
        fm, cells = parse(text)
        check(f"line breaks: U+{code:04X} doesn't end a line", [c.cell_type for c in cells], ["markdown"])
        check(f"line breaks: untouched document with U+{code:04X} round-trips", serialize(fm, cells) == text, True)
    # Editing a chunk leaves such prose byte for byte
    text = "Intro" + chr(0x0C) + "```{r}\n1\n```\n\nPage" + chr(0x2028) + "\n```{r}\n2\n```\n"
    path = write_doc("line_breaks.rmd", text)
    mgr = RmdManager(path)
    check("line breaks: one chunk, after the real line break", [c.cell_type for c in mgr.cells], ["markdown", "code"])
    mgr.set_chunk_option(1, "echo", "FALSE")
    check_same("line breaks: editing the chunk leaves the prose alone", read_doc(path),
               text.replace("```{r}\n2", "```{r echo=FALSE}\n2"))

def _cell_shape(cells):
    return [(c.cell_type, c.source, c.language, c.label, dict(c.options)) for c in cells]


def test_crlf_documents():
    print("\n═══ CRLF documents ═══")
    crlf = SAMPLE.replace("\n", "\r\n")
    # Parsed like the LF document: header found, chunk fences and headers recognised, "\n" sources
    fm, cells = parse(crlf)
    lf_fm, lf_cells = parse(SAMPLE)
    check("crlf parse: frontmatter found", (fm.present, fm.error, fm.data), (True, None, lf_fm.data))
    check("crlf parse: line break detected", (fm.newline, lf_fm.newline), ("\r\n", "\n"))
    check("crlf parse: same cells as the LF document", _cell_shape(cells), _cell_shape(lf_cells))
    check_same("crlf parse: frontmatter text has \\n line breaks", fm.text(), lf_fm.text())
    check("crlf parse: untouched document round-trips byte for byte", serialize(fm, cells) == crlf, True)

    # Read tools see the same document as for the LF file
    path = write_raw("crlf.rmd", crlf)
    mgr = RmdManager(path)
    lf_mgr = RmdManager(reset_fixture())
    check_same("crlf: list_cells", mgr.list_cells(), lf_mgr.list_cells())
    check_same("crlf: get_cell has \\n line breaks", mgr.get_cell(3), "x <- 1:10\nplot(x)")
    check_same("crlf: get_frontmatter", mgr.get_frontmatter(), lf_mgr.get_frontmatter())
    check_same("crlf: get_chunk_options", mgr.get_chunk_options(3), lf_mgr.get_chunk_options(3))
    check_same("crlf: find_in_rmd", mgr.find_in_rmd("x"), lf_mgr.find_in_rmd("x"))
    mgr._save()
    check("crlf: untouched file saves back byte for byte", read_raw(path) == crlf, True)

    def same_as_lf(label, lf_text, edit, name="crlf.rmd"):
        """Apply edit to lf_text and to its CRLF copy: the CRLF result must be the LF one in CRLF."""
        lf_path, crlf_path = write_raw("lf_" + name, lf_text), write_raw(name, lf_text.replace("\n", "\r\n"))
        edit(RmdManager(lf_path))
        edit(RmdManager(crlf_path))
        out, lf_out = read_raw(crlf_path), read_raw(lf_path)
        check_same(f"crlf {label}: same edit as on the LF file, with CRLF", out, lf_out.replace("\n", "\r\n"))
        check(f"crlf {label}: no lone \\n written", lone_newlines(out), 0)
        check(f"crlf {label}: reparses like the LF result",
              (_cell_shape(RmdManager(crlf_path).cells), RmdManager(crlf_path).frontmatter.data),
              (_cell_shape(RmdManager(lf_path).cells), RmdManager(lf_path).frontmatter.data))
        return out

    # Every tool that writes, with caller text in "\n"
    edits = {
        "add_cell code": lambda m: m.add_cell(2, "y <- 2\nz <- 3", "code"),
        "add_cell markdown at the end": lambda m: m.add_cell(-1, "More\nprose\n", "markdown"),
        "delete_cell": lambda m: m.delete_cell(2),
        "move_cell": lambda m: m.move_cell(1, 5),
        "move_cell to the end": lambda m: m.move_cell(0, -1),
        "split_cell code": lambda m: m.split_cell(3, 1),
        "split_cell markdown": lambda m: m.split_cell(0, 2),
        "merge_cells": lambda m: (m.delete_cell(2), m.merge_cells(1, 2)),
        "replace_cell_source": lambda m: m.replace_cell_source(1, "a <- 1\nb <- 2\n"),
        "prepend_to_cell": lambda m: m.prepend_to_cell(0, "Top line"),
        "append_to_cell": lambda m: m.append_to_cell(3, "lines(x)\nabline(h = 0)"),
        "set_chunk_option": lambda m: m.set_chunk_option(1, "echo", "FALSE"),
        "set_chunk_option label": lambda m: m.set_chunk_option(5, "label", "py"),
        "remove_chunk_option": lambda m: m.remove_chunk_option(3, "fig.width"),
        "remove_chunk_option label": lambda m: m.remove_chunk_option(1, "label"),
        "set_frontmatter_key new key": lambda m: m.set_frontmatter_key("date", "2026-10-27"),
        "set_frontmatter_key existing key": lambda m: m.set_frontmatter_key("title", '"New: title"'),
        "set_frontmatter_key multi-line value": lambda m: m.set_frontmatter_key("params", "n: 1\nregion: EU  # default"),
        "remove_frontmatter_key": lambda m: m.remove_frontmatter_key("author"),
    }
    for label, edit in edits.items():
        same_as_lf(label, SAMPLE, edit)

    # A header with comments, blank lines, tags and nested keys: the lines that stay keep their CRLF
    header_edits = {
        "header: set a nested key": lambda m: m.set_frontmatter_key("output", "word_document: default"),
        "header: set a block scalar": lambda m: m.set_frontmatter_key("abstract", "|\n  One.\n\n  Two."),
        "header: set a tagged value": lambda m: m.set_frontmatter_key("date", "!r Sys.time()"),
        "header: add a key": lambda m: m.set_frontmatter_key("lang", "en"),
        "header: remove a list": lambda m: m.remove_frontmatter_key("tags"),
        "header: remove a nested key": lambda m: m.remove_frontmatter_key("params"),
    }
    for label, edit in header_edits.items():
        same_as_lf(label, RICH_HEADER, edit, name="rich.rmd")
    out = same_as_lf("header: set keeps the other lines", RICH_HEADER, lambda m: m.set_frontmatter_key("author", "B"))
    check_same("crlf header: only the key's line changed", out,
               RICH_HEADER.replace("author: 'A. Person'", "author: B").replace("\n", "\r\n"))

    # Headers created, edited next to a document end marker, unreadable, or at the end of the file
    out = same_as_lf("no header: created", "# Title\n\nText.\n", lambda m: m.set_frontmatter_key("title", "T"))
    check_same("crlf no header: created in CRLF", out, "---\r\ntitle: T\r\n---\r\n\r\n# Title\r\n\r\nText.\r\n")
    out = same_as_lf("no header: body starts with a blank line", "\n# Title\n", lambda m: m.set_frontmatter_key("title", "X"))
    check_same("crlf no header: no second blank line", out, "---\r\ntitle: X\r\n---\r\n\r\n# Title\r\n")
    out = same_as_lf("doc end marker", "---\ntitle: x\n...\n---\n", lambda m: m.set_frontmatter_key("z", "1"))
    check_same("crlf doc end marker: new key goes before it", out, "---\r\ntitle: x\r\nz: 1\r\n...\r\n---\r\n")
    unreadable = "---\ntitle: x\n\tbad: 1\n---\nBody\n"
    path = write_raw("crlf.rmd", unreadable.replace("\n", "\r\n"))
    check_same("crlf unreadable header: raw text with \\n line breaks",
               RmdManager(path).get_frontmatter(), RmdManager(write_raw("lf.rmd", unreadable)).get_frontmatter())
    same_as_lf("unreadable header: set a key", unreadable, lambda m: m.set_frontmatter_key("title", "y"))
    out = same_as_lf("header at the end of the file", "---\ntitle: x\n---", lambda m: m.add_cell(-1, "y"))
    check_same("crlf header at the end of the file: cell added in CRLF", out, "---\r\ntitle: x\r\n---\r\n```{r}\r\ny\r\n```\r\n")

    # Caller text with "\r\n" or "\r" is written in the document's line break, like "\n" text
    path = write_raw("crlf.rmd", crlf)
    RmdManager(path).replace_cell_source(1, "a <- 1\r\nb <- 2\rc <- 3")
    RmdManager(path).set_frontmatter_key("params", "n: 1\r\nregion: EU")
    lf_path = reset_fixture()
    RmdManager(lf_path).replace_cell_source(1, "a <- 1\nb <- 2\nc <- 3")
    RmdManager(lf_path).set_frontmatter_key("params", "n: 1\nregion: EU")
    check_same("crlf: caller \\r\\n and \\r text written as CRLF", read_raw(path), read_raw(lf_path).replace("\n", "\r\n"))
    path = reset_fixture()
    RmdManager(path).replace_cell_source(1, "a <- 1\r\nb <- 2\rc <- 3")
    RmdManager(path).set_frontmatter_key("params", "n: 1\r\nregion: EU")
    check_same("lf: caller \\r\\n and \\r text written as LF", read_raw(path), read_raw(lf_path))
    mgr = RmdManager(write_raw("crlf.rmd", crlf))
    mgr.replace_cell_source(1, "a <- 1\r\nb <- 2")
    mgr.add_cell(-1, "c <- 3\rd <- 4", "code")
    check("crlf: caller \\r\\n and \\r text read back with \\n",
          (mgr.get_cell(1), mgr.get_cell(len(mgr.cells) - 1)), ("a <- 1\nb <- 2", "c <- 3\nd <- 4"))
    # append_to_cell and prepend_to_cell add the same separator for "\r\n" and "\r" text as for "\n" text
    separator_edits = {
        "append_to_cell text starting with \\r\\n": ("\r\nb <- 2", "\nb <- 2", lambda m, s: m.append_to_cell(1, s)),
        "append_to_cell text starting with \\r": ("\rb <- 2", "\nb <- 2", lambda m, s: m.append_to_cell(1, s)),
        "prepend_to_cell text ending with \\r": ("Top\r", "Top\n", lambda m, s: m.prepend_to_cell(2, s)),
    }
    for doc, text in (("lf", SAMPLE), ("crlf", crlf)):
        for label, (given, plain, edit) in separator_edits.items():
            path, plain_path = write_raw(doc + ".rmd", text), write_raw(doc + "_plain.rmd", text)
            edit(RmdManager(path), given)
            edit(RmdManager(plain_path), plain)
            check_same(f"{doc}: {label}, same as with \\n", read_raw(path), read_raw(plain_path))

    # create_rmd always writes LF
    new_path = os.path.join(WORK_DIR, "created_lf.rmd")
    create_rmd(new_path, title="T", author="A")
    check("create_rmd: LF line breaks only", "\r" in read_raw(new_path), False)


def test_mixed_line_endings():
    print("\n═══ mixed line endings ═══")
    # Mostly CRLF, with some LF lines: parsed like LF, edits written in CRLF, other lines kept
    text = ("---\r\ntitle: x\n# note\r\n---\r\n\r\nIntro\n\n"
            "```{r one}\r\nx <- 1\n```\r\n\r\n```{r two}\nb\r\n```\nTail\r\n")
    fm, cells = parse(text)
    check("mixed: frontmatter found", (fm.present, fm.data), (True, {"title": "x"}))
    check("mixed: the most common line break is the document's", fm.newline, "\r\n")
    check("mixed: cells", [(c.cell_type, c.source, c.label) for c in cells],
          [("markdown", "\nIntro\n\n", None), ("code", "x <- 1", "one"), ("markdown", "\n", None),
           ("code", "b", "two"), ("markdown", "Tail\n", None)])
    check("mixed: untouched document round-trips byte for byte", serialize(fm, cells) == text, True)
    path = write_raw("mixed.rmd", text)
    RmdManager(path)._save()
    check("mixed: untouched file saves back byte for byte", read_raw(path) == text, True)
    RmdManager(path).set_chunk_option(3, "echo", "FALSE")
    check_same("mixed: an option edit writes the header line in CRLF, the rest is kept", read_raw(path),
               text.replace("```{r two}\nb\r\n```\n", "```{r two, echo=FALSE}\r\nb\r\n```\n"))
    path = write_raw("mixed.rmd", text)
    RmdManager(path).set_frontmatter_key("date", "2026")
    check_same("mixed: a new header key uses CRLF, the other header lines are kept", read_raw(path),
               text.replace("# note\r\n", "# note\r\ndate: 2026\r\n"))
    path = write_raw("mixed.rmd", text)
    RmdManager(path).set_frontmatter_key("title", "y")
    check_same("mixed: a rewritten header key uses CRLF", read_raw(path), text.replace("title: x\n", "title: y\r\n"))
    path = write_raw("mixed.rmd", text)
    RmdManager(path).remove_frontmatter_key("title")
    check_same("mixed: removing a key keeps the other header lines", read_raw(path), text.replace("title: x\n", ""))

    # Mostly LF, with a CRLF line: edits are written in LF
    text = "a\nb\r\n```{r}\nx\n```\n"
    path = write_raw("mixed.rmd", text)
    check("mixed LF: the document's line break", RmdManager(path).frontmatter.newline == "\n", True)
    RmdManager(path).replace_cell_source(1, "y\nz")
    check_same("mixed LF: edited chunk in LF, prose kept", read_raw(path), "a\nb\r\n```{r}\ny\nz\n```\n")
    # A tie goes to the line break used first
    check("mixed: tie goes to the first line break", (parse("a\r\nb\nc")[0].newline, parse("a\nb\r\nc")[0].newline), ("\r\n", "\n"))

    # A lone "\r" ends a line too (old Mac files), as for knitr
    text = "---\rtitle: x\r---\r\rIntro\r```{r}\rx <- 1\r```\r"
    fm, cells = parse(text)
    check("cr: frontmatter found", (fm.present, fm.data, fm.newline), (True, {"title": "x"}, "\r"))
    check("cr: cells with \\n line breaks", [(c.cell_type, c.source) for c in cells], [("markdown", "\nIntro\n"), ("code", "x <- 1")])
    check("cr: untouched document round-trips byte for byte", serialize(fm, cells) == text, True)
    path = write_raw("cr.rmd", text)
    RmdManager(path).set_chunk_option(1, "echo", "FALSE")
    RmdManager(path).set_frontmatter_key("date", "2026")
    check_same("cr: edits written with \\r", read_raw(path),
               "---\rtitle: x\rdate: 2026\r---\r\rIntro\r```{r echo=FALSE}\rx <- 1\r```\r")

    # A part ending in a lone "\r" moved before one starting with "\n": the two breaks stay two
    text = "```{r}\na\n```\r# P\n```{r}\nb\n```\n\nEnd\n"
    path = write_raw("mixed.rmd", text)
    RmdManager(path).move_cell(0, 2)
    check_same("mixed: lone \\r before \\n written as one LF", read_raw(path), "# P\n```{r}\nb\n```\n```{r}\na\n```\n\nEnd\n")
    check("mixed: blank line kept after the move", [(c.cell_type, c.source) for c in RmdManager(path).cells],
          [("markdown", "# P\n"), ("code", "b"), ("code", "a"), ("markdown", "\nEnd\n")])
    # The same for header edits: a key line ending in a lone "\r" next to a "\n" blank line
    path = write_raw("mixed.rmd", "---\r\na: 1\rb: 2\r\n\nc: 3\r\n---\r\nx\r\ny\r\n")
    RmdManager(path).remove_frontmatter_key("b")
    check_same("mixed header: remove keeps the blank line after a lone \\r", read_raw(path),
               "---\r\na: 1\r\n\nc: 3\r\n---\r\nx\r\ny\r\n")
    check_same("mixed header: blank line still read after the remove", RmdManager(path).frontmatter.text(), "a: 1\n\nc: 3\n")
    path = write_raw("mixed.rmd", "---\rtitle: x\n\nz: 1\r---\rA\rB\rC\r")
    RmdManager(path).set_frontmatter_key("title", "y")
    check_same("cr header: set keeps the blank line after the rewritten key", read_raw(path),
               "---\rtitle: y\r\n\nz: 1\r---\rA\rB\rC\r")
    check_same("cr header: blank line still read after the set", RmdManager(path).frontmatter.text(), "title: y\n\nz: 1\n")

def test_line_numbers_agree():
    print("\n═══ line counts, split offsets and line numbers agree ═══")
    # A form feed doesn't end a line (see test_line_breaks): list_cells, find_in_rmd and split_cell all see 2 lines
    ff = chr(0x0C)
    text = f"```{{r}}\na <- 1{ff}b <- 2\nc <- 3\n```\n"
    path = write_raw("line_numbers.rmd", text)
    mgr = RmdManager(path)
    check("line numbers: list_cells counts 2 lines", mgr.list_cells(), f"[0] code (r) 2L  a <- 1{ff}b <- 2")
    check_same("line numbers: find_in_rmd numbers the last line 2", mgr.find_in_rmd("c <- 3"), "cell[0] line 2: c <- 3")
    check_same("line numbers: find_in_rmd shows the whole first line", mgr.find_in_rmd("b <- 2"), f"cell[0] line 1: a <- 1{ff}b <- 2")
    try:
        mgr.split_cell(0, 2)
        check("line numbers: split_cell takes offsets up to the line count minus 1", "no error", "out of range")
    except RmdManagerError as e:
        check("line numbers: split_cell takes offsets up to the line count minus 1", str(e), "(1..1) for cell with 2 line(s)")
    mgr.split_cell(0, 1)
    check_same("line numbers: split_cell splits at the line break, not the form feed", read_raw(path),
               f"```{{r}}\na <- 1{ff}b <- 2\n```\n```{{r}}\nc <- 3\n```\n")
    # The same for every break str.splitlines knows but knitr doesn't, in prose and in chunks
    for code in (0x0B, 0x0C, 0x1C, 0x85, 0x2028, 0x2029):
        ch = chr(code)
        text = f"Intro{ch}more\nlast\n\n```{{r}}\nx <- 1{ch}y <- 2\nz <- 3\n```\n"
        path = write_raw("line_numbers.rmd", text)
        mgr = RmdManager(path)
        listing = mgr.list_cells()
        check(f"line numbers: U+{code:04X} prose has 3 lines", listing, f"[0] markdown 3L  Intro{ch}more")
        check(f"line numbers: U+{code:04X} chunk has 2 lines", listing, f"[1] code (r) 2L  x <- 1{ch}y <- 2")
        check_same(f"line numbers: U+{code:04X} prose line numbers", mgr.find_in_rmd("last"), "cell[0] line 2: last")
        check_same(f"line numbers: U+{code:04X} chunk line numbers", mgr.find_in_rmd("z <- 3"), "cell[1] line 2: z <- 3")
        check_same(f"line numbers: U+{code:04X} stays inside the line find_in_rmd shows", mgr.find_in_rmd("more"),
                   f"cell[0] line 1: Intro{ch}more")
        mgr.split_cell(1, 1)
        mgr.split_cell(0, 1)
        check(f"line numbers: U+{code:04X} split prose at its line break",
              [c.source for c in mgr.cells[:2]], [f"Intro{ch}more\n", "last\n\n"])
        check_same(f"line numbers: U+{code:04X} split chunk at its line break", read_raw(path),
                   text.replace(f"y <- 2\nz", f"y <- 2\n```\n```{{r}}\nz"))
    # YAML also takes NEL, U+2028 and U+2029 for line breaks; the error's line number counts the file's lines
    for code in (0x85, 0x2028, 0x2029):
        path = write_raw("line_numbers.rmd", f'---\ntitle: "a{chr(code)}b"\nkey: value\n\tbad: x\n---\n')
        check(f"line numbers: U+{code:04X} in the header leaves YAML error lines as the file's",
              RmdManager(path).get_frontmatter(), "(line 4, column 1 of the file)")


def test_byte_order_mark():
    print("\n═══ UTF-8 byte order mark ═══")
    bom = chr(0xFEFF)
    body = "---\ntitle: x\n---\n\n# H\n\n```{r}\nx <- 1\n```\n"
    text = bom + body
    fm, cells = parse(text)
    check("bom: parser finds the header after the mark", (fm.present, fm.data), (True, {"title": "x"}))
    check("bom: parser round-trips", serialize(fm, cells) == text, True)
    fm, cells = parse(bom + "```{r}\nx\n```\n")
    check("bom: parser finds a chunk fence after the mark", [(c.cell_type, c.source) for c in cells], [("code", "x")])
    path = write_raw("bom.rmd", text)
    mgr = RmdManager(path)
    check_same("bom: get_frontmatter reads the header", mgr.get_frontmatter(), "title: x")
    check("bom: cells hold no mark", [(c.cell_type, c.source) for c in mgr.cells], [("markdown", "\n# H\n\n"), ("code", "x <- 1")])
    check("bom: list_cells shows the prose", mgr.list_cells(), "[0] markdown 3L  # H")
    mgr._save()
    check("bom: untouched file saves back byte for byte", read_bytes(path), text.encode("utf-8"))
    RmdManager(path).set_frontmatter_key("author", "y")
    check_same("bom: set_frontmatter_key keeps the mark", read_raw(path), bom + body.replace("title: x\n", "title: x\nauthor: y\n"))
    RmdManager(path).remove_frontmatter_key("title")
    check_same("bom: remove_frontmatter_key keeps the mark", read_raw(path), bom + body.replace("title: x\n", "author: y\n"))
    RmdManager(path).replace_cell_source(1, "y <- 2")
    check_same("bom: cell edits keep the mark", read_raw(path), bom + "---\nauthor: y\n---\n\n# H\n\n```{r}\ny <- 2\n```\n")
    check("bom: the mark is written as UTF-8 bytes", read_bytes(path).startswith(b"\xef\xbb\xbf---\n"), True)
    # Without a header the mark stays at the start of the file, whichever cell comes first
    path = write_raw("bom.rmd", bom + "```{r}\nx\n```\nprose\n")
    mgr = RmdManager(path)
    check("bom: a first-line chunk is a chunk", mgr.list_cells(), "[0] code (r) 1L  x")
    check_same("bom: no frontmatter", mgr.get_frontmatter(), "(no frontmatter)")
    mgr.delete_cell(0)
    check_same("bom: deleting the first cell keeps the mark", read_raw(path), bom + "prose\n")
    RmdManager(path).add_cell(0, "a <- 1")
    check_same("bom: a new first cell goes after the mark", read_raw(path), bom + "```{r}\na <- 1\n```\nprose\n")
    RmdManager(path).move_cell(0, 1)
    check_same("bom: moving the first cell keeps the mark", read_raw(path), bom + "prose\n```{r}\na <- 1\n```\n")
    RmdManager(path).set_frontmatter_key("title", "t")
    check_same("bom: a new header goes after the mark", read_raw(path), bom + "---\ntitle: t\n---\n\nprose\n```{r}\na <- 1\n```\n")
    # CRLF documents keep both the mark and their line breaks
    crlf = bom + body.replace("\n", "\r\n")
    path = write_raw("bom.rmd", crlf)
    RmdManager(path)._save()
    check("bom: untouched CRLF file saves back byte for byte", read_bytes(path), crlf.encode("utf-8"))
    RmdManager(path).set_frontmatter_key("author", "y")
    check_same("bom: CRLF header edit keeps the mark", read_raw(path), crlf.replace("title: x\r\n", "title: x\r\nauthor: y\r\n"))
    # Only one mark is set aside: a second U+FEFF is text, so the header isn't on the first line
    twice = bom + bom + body
    path = write_raw("bom.rmd", twice)
    mgr = RmdManager(path)
    check_same("bom: a second mark is text", mgr.get_frontmatter(), "(no frontmatter)")
    mgr._save()
    check("bom: a second mark round-trips", read_bytes(path), twice.encode("utf-8"))
    # A file that is only the mark
    path = write_raw("bom.rmd", bom)
    mgr = RmdManager(path)
    check_same("bom: mark-only file has no cells", mgr.list_cells(), "(document has no cells)")
    mgr.add_cell(-1, "x")
    check_same("bom: mark-only file gets its first cell after the mark", read_raw(path), bom + "```{r}\nx\n```\n")
    # create_rmd writes no mark, even over a file that has one
    path = os.path.join(WORK_DIR, "bom_created.rmd")
    create_rmd(path, title="t")
    check("bom: create_rmd writes no mark", read_bytes(path).startswith(b"---\n"), True)
    write_raw("bom.rmd", text)
    create_rmd(os.path.join(WORK_DIR, "bom.rmd"), title="t", overwrite=True)
    check("bom: create_rmd overwrite drops the mark", read_bytes(os.path.join(WORK_DIR, "bom.rmd")).startswith(b"---\n"), True)


# ──────────────────────────────────────────────
# create_rmd
# ──────────────────────────────────────────────


def test_create_rmd():
    print("\n═══ create_rmd ═══")
    new_path = os.path.join(WORK_DIR, "test_created.rmd")
    if os.path.exists(new_path):
        os.remove(new_path)
    result = create_rmd(new_path, title="Hello", author="Akash")
    check("create: returns Created", result, "Created")
    check("create: file exists", os.path.isfile(new_path), True)
    with open(new_path) as f:
        body = f.read()
    check("create: has title", body, 'title: "Hello"')
    check("create: has author", body, 'author: "Akash"')
    check("create: default output is html_document", body, "html_document")
    # Refuses overwrite
    try:
        create_rmd(new_path)
        check("create: refuses overwrite", "FAIL", "PASS")
    except RmdManagerError as e:
        check("create: refuses overwrite", str(e), "already exists")
    # Overwrite=True works
    result = create_rmd(new_path, overwrite=True, output_format="pdf_document")
    check("create: overwrite=True", result, "Created")
    # Rejects non-abs path
    try:
        create_rmd("relative.rmd")
        check("create: rejects relative path", "FAIL", "PASS")
    except RmdManagerError as e:
        check("create: rejects relative path", str(e), "absolute")
    # Rejects wrong extension
    try:
        create_rmd(os.path.join(WORK_DIR, "wrong.txt"))
        check("create: rejects non-rmd extension", "FAIL", "PASS")
    except RmdManagerError as e:
        check("create: rejects non-rmd extension", str(e), ".rmd")
    os.remove(new_path)

def test_create_rmd_quoting():
    print("\n═══ create_rmd: title and author quoting ═══")
    import yaml
    path = os.path.join(WORK_DIR, "quoted.rmd")
    values = {
        "double quote": 'He said "hi"',
        "backslash": "C:\\Users\\akash\\",
        "newline": "Line one\nLine two\n",
        "colon and hash": "Results: 95% # of runs",
        "yaml-looking": "true",
        "leading space, unicode and line separators": "  Caf" + chr(0xE9) + chr(0x2028) + "end" + chr(0x85) + "\r",
    }
    for label, value in values.items():
        create_rmd(path, title=value, author=value, overwrite=True)
        fm = RmdManager(path).frontmatter
        check(f"quoting {label}: header is valid YAML", fm.error, None)
        check(f"quoting {label}: title and author load back exactly", (fm.data.get("title"), fm.data.get("author")), (value, value))
        check(f"quoting {label}: safe_load agrees", yaml.safe_load(fm.text()).get("title"), value)
        check(f"quoting {label}: one line per key", fm.text().count("\n"), 3)
    create_rmd(path, title="Hello", overwrite=True)
    check("quoting: plain title still double-quoted", read_doc(path), 'title: "Hello"\noutput: html_document\n')
    # output_format: plain when that is safe, quoted otherwise, left out when empty
    create_rmd(path, output_format="rmarkdown::html_vignette", overwrite=True)
    check("output_format: plain when safe", read_doc(path), "output: rmarkdown::html_vignette\n")
    create_rmd(path, output_format="html_document: default", overwrite=True)
    check("output_format: quoted when plain would change it", RmdManager(path).frontmatter.data, {"output": "html_document: default"})
    create_rmd(path, title="T", output_format="", overwrite=True)
    check_same("output_format: empty leaves the key out", read_doc(path), '---\ntitle: "T"\n---\n\n')


def test_extension_case():
    print("\n═══ .rmd extension check ignores case ═══")
    for name in ("Report.Rmd", "REPORT.RMD"):
        path = os.path.join(WORK_DIR, name)
        check(f"extension: create_rmd accepts {name}", create_rmd(path, title="x", overwrite=True), "Created")
        check(f"extension: tools open {name}", RmdManager(path).get_frontmatter(), "title: x")
    for name in ("report.qmd", "report.md"):
        try:
            create_rmd(os.path.join(WORK_DIR, name))
            check(f"extension: {name} rejected", "no error", "File is not a .rmd document")
        except RmdManagerError as e:
            check(f"extension: {name} rejected", str(e), "File is not a .rmd document")


# ──────────────────────────────────────────────
# Cell structure
# ──────────────────────────────────────────────


def test_list_cells():
    print("\n═══ list_cells ═══")
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    out = mgr.list_cells()
    check("list: shows cell 0 markdown", out, "[0] markdown")
    check("list: shows code chunk with language", out, "code (r")
    check("list: shows label", out, "label=setup")
    check("list: shows python chunk", out, "code (python)")


def test_get_cell():
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    check("get_cell: setup chunk source", mgr.get_cell(1), "knitr::opts_chunk$set")
    check("get_cell: python chunk source", mgr.get_cell(5), "import numpy")


def test_add_cell():
    print("\n═══ add_cell ═══")
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    before = len(mgr.cells)
    # Insert a code chunk between two prose blocks — cell count grows cleanly
    mgr.add_cell(1, source="k <- 1", cell_type="code")
    mgr2 = RmdManager(FIXTURE_PATH)
    check("add: count increased", len(mgr2.cells), before + 1)
    check("add: inserted chunk at 1", mgr2.cells[1].source, "k <- 1")
    # Append code at the end
    mgr2.add_cell(-1, source="final <- TRUE", cell_type="code")
    mgr3 = RmdManager(FIXTURE_PATH)
    check("add: appended code chunk", mgr3.cells[-1].source, "final <- TRUE")
    # Adjacent markdown cells auto-merge on round-trip (.rmd format has no prose
    # boundary markers, unlike .ipynb). Document this as expected behavior.
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    md_count_before = sum(1 for c in mgr.cells if c.cell_type == "markdown")
    mgr.add_cell(0, source="# New heading\n", cell_type="markdown")
    mgr_after = RmdManager(FIXTURE_PATH)
    md_count_after = sum(1 for c in mgr_after.cells if c.cell_type == "markdown")
    check("add: adjacent markdown cells merge on reparse", md_count_after, md_count_before)
    check("add: merged cell contains new heading", mgr_after.cells[0].source, "# New heading")


def test_delete_cell():
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    before = len(mgr.cells)
    mgr.delete_cell(0)
    mgr2 = RmdManager(FIXTURE_PATH)
    check("delete: count decreased", len(mgr2.cells), before - 1)


def test_move_cell():
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    first_before = mgr.cells[0].source
    mgr.move_cell(0, 1)
    mgr2 = RmdManager(FIXTURE_PATH)
    check("move: source cell shifted", mgr2.cells[1].source, first_before)


def test_split_cell():
    print("\n═══ split_cell ═══")
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    # cell 3 has two lines: x <- 1:10 / plot(x)
    mgr.split_cell(3, 1)
    mgr2 = RmdManager(FIXTURE_PATH)
    check("split: cell 3 first half", mgr2.cells[3].source, "x <- 1:10")
    check("split: cell 4 second half", mgr2.cells[4].source, "plot(x)")


def test_merge_cells():
    print("\n═══ merge_cells ═══")
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    # Split cell 3 first, then merge back
    mgr.split_cell(3, 1)
    mgr2 = RmdManager(FIXTURE_PATH)
    mgr2.merge_cells(3, 4)
    mgr3 = RmdManager(FIXTURE_PATH)
    check("merge: first line", mgr3.cells[3].source, "x <- 1:10")
    check("merge: second line", mgr3.cells[3].source, "plot(x)")
    # Rejects cross-type merge
    try:
        mgr3.merge_cells(0, 1)  # markdown + code
        check("merge: rejects cross-type", "FAIL", "PASS")
    except RmdManagerError as e:
        check("merge: rejects cross-type", str(e), "different types")

def test_empty_document_indexes():
    print("\n═══ index -1 on a document with no cells ═══")
    from rmd_editor import kernel as _k
    from rmd_editor import server
    for label, text in (("empty file", ""), ("header only", "---\ntitle: x\n---\n")):
        path = write_doc("no_cells.rmd", text)
        calls = {
            "get_cell": lambda: server.get_cell(path, -1),
            "delete_cell": lambda: server.delete_cell(path, -1),
            "move_cell": lambda: server.move_cell(path, -1, 0),
            "split_cell": lambda: server.split_cell(path, -1, 1),
            "merge_cells": lambda: server.merge_cells(path, -1, -1),
            "replace_cell_source": lambda: server.replace_cell_source(path, -1, "x"),
            "prepend_to_cell": lambda: server.prepend_to_cell(path, -1, "x"),
            "append_to_cell": lambda: server.append_to_cell(path, -1, "x"),
            "get_chunk_options": lambda: server.get_chunk_options(path, -1),
            "set_chunk_option": lambda: server.set_chunk_option(path, -1, "echo", "FALSE"),
            "remove_chunk_option": lambda: server.remove_chunk_option(path, -1, "echo"),
            "execute_cell": lambda: server.execute_cell(path, -1),
        }
        for name, call in calls.items():
            try:
                out = call()
            except Exception as e:
                out = f"raised {type(e).__name__}: {e}"
            check(f"{label}: {name}(-1) returns the manager's error", out,
                  "Error: Cell index -1 out of range: the document has no cells")
        check(f"{label}: index 0 gets the same error", server.get_cell(path, 0), "Error: Cell index 0 out of range: the document has no cells")
        check(f"{label}: failed calls leave the file unchanged", read_doc(path) == text, True)
        check(f"{label}: execute_cell(-1) started no kernel", _k.kernel_state(path), "not started")
        check(f"{label}: add_cell(-1) still appends", server.add_cell(path, -1, "x <- 1"), "Saved")
        check(f"{label}: appended chunk is the only cell", [c.source for c in RmdManager(path).cells], ["x <- 1"])
    # -1 still means the last cell when there are cells
    reset_fixture()
    check("non-empty: get_cell(-1) is the last cell", RmdManager(FIXTURE_PATH).get_cell(-1), "Final prose.")


# ──────────────────────────────────────────────
# Cell content editing
# ──────────────────────────────────────────────


def test_replace_cell_source():
    print("\n═══ replace_cell_source ═══")
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    mgr.replace_cell_source(1, "new <- 42")
    mgr2 = RmdManager(FIXTURE_PATH)
    check("replace: new source", mgr2.cells[1].source, "new <- 42")
    check("replace: label preserved", mgr2.cells[1].label, "setup")
    check("replace: options preserved", mgr2.cells[1].options.get("include"), "FALSE")


def test_prepend_append_to_cell():
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    mgr.prepend_to_cell(1, "# prepended\n")
    mgr2 = RmdManager(FIXTURE_PATH)
    check("prepend: new line at top", mgr2.cells[1].source, "# prepended")
    mgr2.append_to_cell(1, "# appended")
    mgr3 = RmdManager(FIXTURE_PATH)
    check("append: new line at bottom", mgr3.cells[1].source.rstrip().split("\n")[-1], "# appended")


# ──────────────────────────────────────────────
# Chunk options
# ──────────────────────────────────────────────


def test_chunk_options():
    print("\n═══ chunk options ═══")
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    # Get
    opts = mgr.get_chunk_options(1)
    check("get_chunk_options: shows language", opts, "language: r")
    check("get_chunk_options: shows label", opts, "label: setup")
    check("get_chunk_options: shows include", opts, "include=FALSE")
    # Set new option
    mgr.set_chunk_option(1, "warning", "FALSE")
    mgr2 = RmdManager(FIXTURE_PATH)
    check("set_chunk_option: added warning", mgr2.cells[1].options.get("warning"), "FALSE")
    # Overwrite existing
    mgr2.set_chunk_option(1, "include", "TRUE")
    mgr3 = RmdManager(FIXTURE_PATH)
    check("set_chunk_option: overwrote include", mgr3.cells[1].options.get("include"), "TRUE")
    # Set label via special key
    mgr3.set_chunk_option(1, "label", "new-label")
    mgr4 = RmdManager(FIXTURE_PATH)
    check("set_chunk_option: label=new-label", mgr4.cells[1].label, "new-label")
    # Remove option
    mgr4.remove_chunk_option(1, "warning")
    mgr5 = RmdManager(FIXTURE_PATH)
    check("remove_chunk_option: warning gone", "warning" not in mgr5.cells[1].options, True)
    # Remove nonexistent option raises
    try:
        mgr5.remove_chunk_option(1, "nonexistent")
        check("remove: raises on missing", "FAIL", "PASS")
    except RmdManagerError as e:
        check("remove: raises on missing", str(e), "no option")
    # Chunk ops on markdown cell raise
    try:
        mgr5.get_chunk_options(0)
        check("chunk ops: reject markdown", "FAIL", "PASS")
    except RmdManagerError as e:
        check("chunk ops: reject markdown", str(e), "markdown cell")


def test_chunk_header_values():
    print("\n═══ chunk options: what a header can hold ═══")
    from rmd_editor import server
    text = "```{r}\nx <- 1\n```\n\nText\n"

    def refused(label, call, error, doc=text):
        """call(path) on a fresh copy of doc returns an error holding error, and leaves the file alone."""
        path = write_doc("header.rmd", doc)
        check(f"header {label}: refused", call(path), error)
        check(f"header {label}: file unchanged", read_doc(path) == doc, True)

    # A chunk header is one line: a line break in a value, label or key would split it
    refused("line break in a value", lambda p: server.set_chunk_option(p, 0, "fig.cap", '"a\nb"'),
            "Chunk option value '\"a\\nb\"' contains a line break")
    refused("CRLF in a value", lambda p: server.set_chunk_option(p, 0, "fig.cap", '"a\r\nb"'), "contains a line break")
    refused("lone CR in a value", lambda p: server.set_chunk_option(p, 0, "fig.cap", '"a\rb"'), "contains a line break")
    refused("line break in a label", lambda p: server.set_chunk_option(p, 0, "label", "a b\nc"),
            "Chunk label 'a b\\nc' contains a line break")
    refused("line break in a key", lambda p: server.set_chunk_option(p, 0, "fig\ncap", "1"),
            "Option key 'fig\\ncap' contains a line break")
    # Text that would read back as other options, or swallow the options after it
    refused("comma outside a string", lambda p: server.set_chunk_option(p, 0, "fig.cap", "a, b"),
            "the chunk header ```{r fig.cap=a, b} would read back as label None and options {'fig.cap': 'a', 'b': ''}")
    refused("comma in a label", lambda p: server.set_chunk_option(p, 0, "label", "a, b"), "would read back as label 'a'")
    refused("= in a label", lambda p: server.set_chunk_option(p, 0, "label", "a=b"), "would read back as label None")
    refused("= in a key", lambda p: server.set_chunk_option(p, 0, "a=b", "1"), "would read back as")
    refused("unmatched quote", lambda p: server.set_chunk_option(p, 0, "fig.cap", '"a'),
            "Chunk option value '\"a' has an unmatched bracket or quote")
    refused("unmatched bracket", lambda p: server.set_chunk_option(p, 0, "eval", "c(1, 2"), "has an unmatched bracket or quote")
    refused("stray closing brace", lambda p: server.set_chunk_option(p, 0, "fig.cap", "x}"), "has an unmatched bracket or quote")
    refused("closing brace in a label", lambda p: server.set_chunk_option(p, 0, "label", "x}"),
            "Chunk label 'x}' has an unmatched bracket or quote")
    # knitr reads keys and values as R code: a backtick-quoted name left open, a # outside a string
    # (a comment to the end of the line) or a second = would break the whole header
    refused("backtick left open in a value", lambda p: server.set_chunk_option(p, 0, "fig.cap", "`x"),
            "Chunk option value '`x' has an unmatched bracket or quote")
    refused("# outside a string in a value", lambda p: server.set_chunk_option(p, 0, "fig.cap", "TRUE # note"),
            "Chunk option value 'TRUE # note' has a # outside a quoted string")
    refused("# in a key", lambda p: server.set_chunk_option(p, 0, "a#b", "1"), "Option key 'a#b' has a # outside a quoted string")
    refused("second = in a value", lambda p: server.set_chunk_option(p, 0, "fig.cap", "a=1"),
            "Chunk option value 'a=1' has an = outside a quoted string or brackets")
    # A bare name in a header is the chunk label to knitr, so an option needs a value
    refused("empty value", lambda p: server.set_chunk_option(p, 0, "echo", ""), "Option value must not be empty")
    refused("blank value", lambda p: server.set_chunk_option(p, 0, "echo", "  "), "Option value must not be empty")
    # An option written after an unmatched quote already in the file would be swallowed by it
    refused("option after an unmatched quote in the file", lambda p: server.set_chunk_option(p, 0, "echo", "FALSE"),
            "would read back as", doc='```{r fig.cap="a}\nx\n```\n')

    # Accepted text reads back as written, and an option set after it still reads back too
    accepted = [
        ("fig.cap", '"a}b"'), ("fig.cap", '"a```b"'), ("fig.cap", '"A, B = C"'), ("fig.cap", "'it, \"is\"'"),
        ("fig.cap", '"say \\"hi\\", then go"'), ("fig.cap", '"a' + chr(0x2028) + "b" + chr(0x0C) + 'c"'),
        ("eval", "c(1, 2)"), ("fig.align", "`center`"), ("label", "my-label"), ("label", "a b"),
        ("eval", "x == 1"), ("eval", "x != 1 && y <= 2"), ("eval", "a %in% b"), ("fig.cap", '"Figure #1"'),
        ("fig.cap", "list(a = 1)"), ("fig.cap", "`a#b`"), ("label", "`a"), ("label", "fig#1"),
    ]
    for key, value in accepted:
        path = write_doc("header.rmd", text)
        mgr = RmdManager(path)
        mgr.set_chunk_option(0, key, value)
        mgr.set_chunk_option(0, "echo", "FALSE")
        cells = RmdManager(path).cells
        want = (value, {"echo": "FALSE"}) if key == "label" else (None, {key: value, "echo": "FALSE"})
        check(f"header {key}={value!r}: reads back", (cells[0].label, dict(cells[0].options)), want)
        check(f"header {key}={value!r}: same cells", [(c.cell_type, c.source) for c in cells], [("code", "x <- 1"), ("markdown", "\nText\n")])
        written = f"```{{r {value}, echo=FALSE}}" if key == "label" else f"```{{r {key}={value}, echo=FALSE}}"
        check_same(f"header {key}={value!r}: header line written", read_doc(path).split("\n")[0], written)
    # Surrounding whitespace is dropped, as reading the header drops it
    path = write_doc("header.rmd", text)
    RmdManager(path).set_chunk_option(0, "echo", "  FALSE \n")
    check_same("header: value stripped", read_doc(path), text.replace("{r}", "{r echo=FALSE}"))

    # A bare option first in the header stays an option, not the label, when the header is rewritten
    path = write_doc("header.rmd", "```{r, foo}\nx\n```\n")
    RmdManager(path).set_chunk_option(0, "echo", "FALSE")
    check_same("bare first option: kept after an edit", read_doc(path), "```{r, foo, echo=FALSE}\nx\n```\n")
    check("bare first option: still not the label", (RmdManager(path).cells[0].label, dict(RmdManager(path).cells[0].options)),
          (None, {"foo": "", "echo": "FALSE"}))
    path = write_doc("header.rmd", "```{r setup, foo}\nx\n```\n")
    RmdManager(path).remove_chunk_option(0, "label")
    check_same("bare first option: removing the label before it", read_doc(path), "```{r, foo}\nx\n```\n")
    # A backslash escapes a quote inside an R string
    fm, cells = parse('```{r fig.cap="a\\", b", echo=FALSE}\nx\n```\n')
    check("escaped quote: one option", dict(cells[0].options), {"fig.cap": '"a\\", b"', "echo": "FALSE"})
    # Tools that rewrite a whole chunk write its header from the parsed label and options: it reads back the same,
    # and is written as the line given here
    headers = {
        "{r}": "{r}", "{r setup}": "{r setup}", "{r, echo=FALSE}": "{r echo=FALSE}",
        "{r setup, include=FALSE}": "{r setup, include=FALSE}", "{r, foo}": "{r, foo}", "{r a, foo, b=1}": "{r a, foo, b=1}",
        '{r fig.cap="a, b", eval=(x > 0)}': '{r fig.cap="a, b", eval=(x > 0)}', '{r fig.cap="x}"}': '{r fig.cap="x}"}',
        '{python name, fig.cap="a\\", b"}': '{python name, fig.cap="a\\", b"}',
        "{r out.width='50%', fig.align=c('a', 'b')}": "{r out.width='50%', fig.align=c('a', 'b')}",
        '{r fig.cap="a}': '{r fig.cap="a}', "{r a=(, b=1}": "{r a=(, b=1}", "{r  lbl ,  echo = TRUE }": "{r lbl, echo=TRUE}",
    }
    for header, written in headers.items():
        path = write_doc("header.rmd", f"```{header}\nx\n```\n")
        before = [shape[2:] for shape in _cell_shape(RmdManager(path).cells)]
        RmdManager(path).replace_cell_source(0, "y")
        check(f"rewritten {header}: same language, label and options", [shape[2:] for shape in _cell_shape(RmdManager(path).cells)], before)
        check_same(f"rewritten {header}: header line written", read_doc(path), f"```{written}\ny\n```\n")

    # A line knitr reads as a closing fence in a chunk's new text would close the chunk early; the
    # error gives its line in the text passed
    refused("closing fence in a chunk's new text", lambda p: server.replace_cell_source(p, 0, "a\n```\nb"),
            "Line 2 of the new text, '```', is a closing fence for knitr")
    refused("closing fence with trailing spaces", lambda p: server.replace_cell_source(p, 0, "a\n```  "), "Line 2 of the new text")
    refused("closing fence in a new chunk", lambda p: server.add_cell(p, -1, "```"), "Line 1 of the new text")
    refused("closing fence appended", lambda p: server.append_to_cell(p, 0, "```\ny"), "Line 1 of the new text")
    refused("closing fence appended after a line", lambda p: server.append_to_cell(p, 0, "e\n```"), "Line 2 of the new text",
            doc="```{r}\na\nb\nc\nd\n```\n")
    refused("closing fence prepended", lambda p: server.prepend_to_cell(p, 0, "```"), "Line 1 of the new text")
    for fence in ["````", "  ```", "\t```\t", "> ```", " > > ````  "]:
        refused(f"closing fence {fence!r}", lambda p: server.replace_cell_source(p, 0, f"x\n{fence}\ny"),
                f"Line 2 of the new text, {fence!r}, is a closing fence for knitr")
    # Other backtick lines stay in the chunk, and prose may hold a plain code fence
    path = write_doc("header.rmd", text)
    check("backtick lines in a chunk: saved", server.replace_cell_source(path, 0, "``` x\n````r\n`a` <- 1"), "Saved")
    check("backtick lines in a chunk: read back", server.get_cell(path, 0) == "``` x\n````r\n`a` <- 1", True)
    check("code fence in prose: saved", server.replace_cell_source(path, 1, "```\ncode\n```\n"), "Saved")
    check("code fence in prose: read back", [(c.cell_type, c.source) for c in RmdManager(path).cells],
          [("code", "``` x\n````r\n`a` <- 1"), ("markdown", "```\ncode\n```\n")])
    # A fence line already in a chunk that this tool reads as body: the chunk's own text saves back, and
    # text added to it is checked on its own
    doc = "```{r}\na\n  ```\n```\n"
    path = write_doc("header.rmd", doc)
    check("fence already in a chunk: own text saves back", server.replace_cell_source(path, 0, server.get_cell(path, 0)), "Saved")
    check("fence already in a chunk: file unchanged", read_doc(path) == doc, True)
    check("fence already in a chunk: append works", server.append_to_cell(path, 0, "b"), "Saved")
    check_same("fence already in a chunk: appended", read_doc(path), "```{r}\na\n  ```\nb\n```\n")


def test_chunk_body_lines():
    print("\n═══ chunk bodies: every line kept ═══")
    from rmd_editor import server
    # A chunk's text is its body without the line break before the closing fence, so "x <- 1\n"
    # ends with a blank line; a body of blank lines only is its line breaks, so "" is an empty chunk
    bodies = {
        "empty": ("", ""), "one blank line": ("\n", "\n"), "two blank lines": ("\n\n", "\n\n"),
        "one line": ("x <- 1\n", "x <- 1"), "trailing blank line": ("x <- 1\n\n", "x <- 1\n"),
        "leading blank line": ("\nx <- 1\n", "\nx <- 1"), "inner blank line": ("a\n\nb\n", "a\n\nb"),
    }
    for name, (body, source) in bodies.items():
        doc = "```{r}\n" + body + "```\n\nText\n"
        path = write_doc("body.rmd", doc)
        check_same(f"body {name}: get_cell", server.get_cell(path, 0), source)
        # An option or label edit rewrites only the header line
        server.set_chunk_option(path, 0, "echo", "FALSE")
        check_same(f"body {name}: set_chunk_option keeps the body", read_doc(path), doc.replace("{r}", "{r echo=FALSE}"))
        server.set_chunk_option(path, 0, "label", "lbl")
        server.remove_chunk_option(path, 0, "echo")
        check_same(f"body {name}: label and remove keep the body", read_doc(path), doc.replace("{r}", "{r lbl}"))
        # Saving the text get_cell returned leaves the file as it was
        path = write_doc("body.rmd", doc)
        server.replace_cell_source(path, 0, server.get_cell(path, 0))
        check_same(f"body {name}: replace with its own text is a no-op", read_doc(path), doc)
        # Writing that text anew gives the same body
        server.replace_cell_source(path, 0, "tmp")
        server.replace_cell_source(path, 0, source)
        check_same(f"body {name}: replace_cell_source writes that body", read_doc(path), doc)
    # So text from an agent that ends with a newline leaves a blank line before the fence
    path = write_doc("body.rmd", "```{r}\ny\n```\n")
    server.replace_cell_source(path, 0, "x <- 1\n")
    check_same("body: text ending in \\n leaves a blank line", read_doc(path), "```{r}\nx <- 1\n\n```\n")
    server.replace_cell_source(path, 0, "x <- 1")
    check_same("body: text without a final \\n leaves none", read_doc(path), "```{r}\nx <- 1\n```\n")
    server.append_to_cell(path, 0, "")
    check_same("body: appending nothing changes nothing", read_doc(path), "```{r}\nx <- 1\n```\n")
    # Text added to an empty chunk needs no separator, and a one-blank-line chunk keeps its blank line
    for name, (op, body, want) in {
        "prepend to an empty chunk": (server.prepend_to_cell, "", "y\n"),
        "append to an empty chunk": (server.append_to_cell, "", "y\n"),
        "prepend to a blank line": (server.prepend_to_cell, "\n", "y\n\n"),
        "append to a blank line": (server.append_to_cell, "\n", "\ny\n"),
    }.items():
        path = write_doc("body.rmd", "```{r}\n" + body + "```\n")
        op(path, 0, "y")
        check_same(f"body: {name}", read_doc(path), "```{r}\n" + want + "```\n")

    # split_cell keeps every body line, at every offset
    body_lines = ["\n", "a\n", "\n", "b\n", "\n"]
    doc = "```{r}\n" + "".join(body_lines) + "```\n"
    for offset in range(1, 4):
        path = write_doc("body.rmd", doc)
        server.split_cell(path, 0, offset)
        check_same(f"split at {offset}: every line kept", read_doc(path),
                   "```{r}\n" + "".join(body_lines[:offset]) + "```\n```{r}\n" + "".join(body_lines[offset:]) + "```\n")
    # A markdown cell split anywhere saves back as it was (the halves merge again on reparse)
    doc = "```{r}\nx\n```\n\na\n\n\nb\n\n"
    for offset in range(1, 6):
        path = write_doc("body.rmd", doc)
        server.split_cell(path, 1, offset)
        check_same(f"split prose at {offset}: every line kept", read_doc(path), doc)
    # merge_cells joins the bodies as they are: an empty chunk adds no line
    path = write_doc("body.rmd", "```{r}\na\n\n```\n```{r}\n```\n```{r}\n\nb\n```\n")
    server.merge_cells(path, 0, 2)
    check_same("merge: every line kept", read_doc(path), "```{r}\na\n\n\nb\n```\n")

    # CRLF, mixed and BOM documents: an option edit writes the header line in the document's line
    # break and keeps the body's bytes
    path = write_raw("body.rmd", "```{r}\r\nx <- 1\r\n\r\n```\r\nT\r\n")
    server.set_chunk_option(path, 0, "echo", "FALSE")
    check_same("crlf body: option edit keeps the blank line", read_raw(path), "```{r echo=FALSE}\r\nx <- 1\r\n\r\n```\r\nT\r\n")
    path = write_raw("body.rmd", "```{r}\r\na\nb\r\n\n```\r\nT\r\n")
    server.set_chunk_option(path, 0, "echo", "FALSE")
    check_same("mixed body: option edit keeps every byte of the body", read_raw(path), "```{r echo=FALSE}\r\na\nb\r\n\n```\r\nT\r\n")
    bom = chr(0xFEFF)
    path = write_raw("body.rmd", bom + "```{r}\nx\n\n```\n")
    server.set_chunk_option(path, 0, "echo", "FALSE")
    check("bom body: option edit keeps the mark and the blank line", read_bytes(path), (bom + "```{r echo=FALSE}\nx\n\n```\n").encode("utf-8"))

    # Re-saving every cell's own text is byte for byte a no-op, whatever the document
    docs = {
        "sample": SAMPLE, "crlf": SAMPLE.replace("\n", "\r\n"),
        "mixed": "---\r\ntitle: x\n---\r\n\r\nIntro\n\n```{r one}\r\nx <- 1\n\n```\r\n\r\n```{r two}\nb\r\n```\nTail\r\n",
        "cr": "---\rtitle: x\r---\r\rIntro\r```{r}\rx <- 1\r\r```\r",
        "bom": bom + "---\ntitle: x\n---\n\n```{r}\n\n```\n```{r}\n```\n",
        "no final newline after prose": "```{r}\nx\n\n```\nlast",
        "no final newline after a chunk": "# T\n```{r}\ny\n\n```",
    }
    for name, doc in docs.items():
        path = write_raw("noop.rmd", doc)
        for i in range(len(RmdManager(path).cells)):
            mgr = RmdManager(path)
            mgr.replace_cell_source(i, mgr.get_cell(i))
        check(f"no-op {name}: re-saving every cell's text keeps the file byte for byte", read_bytes(path), doc.encode("utf-8"))

    # Front matter: blank lines before the closing fence stay through key edits
    path = write_doc("body.rmd", "---\ntitle: x\n\n---\nB\n")
    server.set_frontmatter_key(path, "title", "y")
    server.set_frontmatter_key(path, "a", "1")
    server.remove_frontmatter_key(path, "a")
    check_same("front matter: blank line before the fence kept", read_doc(path), "---\ntitle: y\n\n---\nB\n")


# ──────────────────────────────────────────────
# Frontmatter
# ──────────────────────────────────────────────


def test_frontmatter():
    print("\n═══ frontmatter ═══")
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    fm_txt = mgr.get_frontmatter()
    check("get_frontmatter: title", fm_txt, "title: Sample")
    check("get_frontmatter: author", fm_txt, "author: Akash")
    # Set a new key
    mgr.set_frontmatter_key("date", "2026-04-20")
    mgr2 = RmdManager(FIXTURE_PATH)
    check("set_frontmatter_key: date added", str(mgr2.frontmatter.data.get("date")), "2026-04-20")
    # Set overwrites
    mgr2.set_frontmatter_key("author", "Someone Else")
    mgr3 = RmdManager(FIXTURE_PATH)
    check("set_frontmatter_key: overwrote author", mgr3.frontmatter.data.get("author"), "Someone Else")
    # Remove
    mgr3.remove_frontmatter_key("date")
    mgr4 = RmdManager(FIXTURE_PATH)
    check("remove_frontmatter_key: date gone", "date" not in mgr4.frontmatter.data, True)
    # Remove missing raises
    try:
        mgr4.remove_frontmatter_key("nonexistent")
        check("remove_fm: raises on missing", "FAIL", "PASS")
    except RmdManagerError as e:
        check("remove_fm: raises on missing", str(e), "no key")

RICH_HEADER = """---
# Report settings
title: "Quarterly: report"   # quoted, with a comment
author: 'A. Person'
date: !r Sys.Date()
params:
  n: !r 1 + 1
  region: "EU"   # default region
output:
  html_document:
    toc: true

    toc_depth: 2
  pdf_document: default
abstract: |
  First line.

  Third line.
tags:
- a
- b
# trailing comment
---

Body text.
"""


def test_frontmatter_line_level():
    print("\n═══ frontmatter: line-level edits ═══")
    from rmd_editor.parser import TaggedScalar, load_yaml
    # The reported case: R tags made the header unreadable, and a set rewrote it with only the new key
    path = write_doc("tagged.rmd", '---\ntitle: "T"\nparams:\n  n: !r 1 + 1\noutput: html_document\n---\n\nbody\n')
    check("tags: get_frontmatter shows the content", RmdManager(path).get_frontmatter(),
          "title: T\nparams:\n  n: !r 1 + 1\noutput: html_document")
    RmdManager(path).set_frontmatter_key("author", "A")
    check_same("tags: set keeps every other key and line", read_doc(path),
               '---\ntitle: "T"\nparams:\n  n: !r 1 + 1\noutput: html_document\nauthor: A\n---\n\nbody\n')

    path = write_doc("header.rmd", RICH_HEADER)
    original = RmdManager(path).frontmatter
    check("read: header with comments, tags and blocks parses", original.error, None)
    n = original.data["params"]["n"]
    check("read: !r value kept as a tagged string", (isinstance(n, TaggedScalar), n, n.tag, n.value), (True, "!r 1 + 1", "!r", "1 + 1"))
    shown = RmdManager(path).get_frontmatter()
    check("read: get_frontmatter shows quoted values", shown, "title: 'Quarterly: report'")
    check("read: get_frontmatter shows tags as tags", shown, "date: !r Sys.Date()\nparams:\n  n: !r 1 + 1\n")
    check("read: get_frontmatter shows a block scalar as a | block", shown, "abstract: |\n  First line.\n\n  Third line.\n")

    cases = [
        ("set existing key", "set_frontmatter_key", ("author", "B. Person"),
         "author: 'A. Person'\n", "author: B. Person\n"),
        ("set tagged value", "set_frontmatter_key", ("date", "!r format(Sys.Date())"),
         "date: !r Sys.Date()\n", "date: !r format(Sys.Date())\n"),
        ("set quoted value", "set_frontmatter_key", ("title", '"2026: final"'),
         'title: "Quarterly: report"   # quoted, with a comment\n', 'title: "2026: final"\n'),
        ("set nested-block key", "set_frontmatter_key", ("output", "html_document:\n  toc: false"),
         "output:\n  html_document:\n    toc: true\n\n    toc_depth: 2\n  pdf_document: default\n",
         "output:\n  html_document:\n    toc: false\n"),
        ("set block with tags and a comment", "set_frontmatter_key", ("params", 'n: !r 2 * 3\nregion: "US"  # changed'),
         'params:\n  n: !r 1 + 1\n  region: "EU"   # default region\n', 'params:\n  n: !r 2 * 3\n  region: "US"  # changed\n'),
        ("set block scalar to one line", "set_frontmatter_key", ("abstract", "Short."),
         "abstract: |\n  First line.\n\n  Third line.\n", "abstract: Short.\n"),
        ("add new key", "set_frontmatter_key", ("subtitle", "Draft"),
         "# trailing comment\n---\n", "# trailing comment\nsubtitle: Draft\n---\n"),
        ("remove key with a block", "remove_frontmatter_key", ("output",),
         "output:\n  html_document:\n    toc: true\n\n    toc_depth: 2\n  pdf_document: default\n", ""),
        ("remove block scalar key", "remove_frontmatter_key", ("abstract",),
         "abstract: |\n  First line.\n\n  Third line.\n", ""),
        ("remove column-0 sequence key", "remove_frontmatter_key", ("tags",), "tags:\n- a\n- b\n", ""),
    ]
    for label, op, args, old, new in cases:
        write_doc("header.rmd", RICH_HEADER)
        getattr(RmdManager(path), op)(*args)
        after = read_doc(path)
        check_same(f"{label}: only that key's lines change", after, RICH_HEADER.replace(old, new, 1))
        fm = RmdManager(path).frontmatter
        check(f"{label}: result parses with the tolerant loader", (fm.error, isinstance(load_yaml(fm.text()), dict)), (None, True))
        key = args[0]
        others = {k: v for k, v in original.data.items() if k != key}
        check(f"{label}: other keys' values unchanged", repr({k: v for k, v in fm.data.items() if k != key}), repr(others))
        if op == "set_frontmatter_key":
            check(f"{label}: key holds the parsed value", repr(fm.data.get(key)), repr(load_yaml(args[1])))
        else:
            check(f"{label}: key gone", key in fm.data, False)


def test_frontmatter_edge_cases():
    print("\n═══ frontmatter: edge cases ═══")
    from rmd_editor import server

    def after_set(text, key, value, name="edge.rmd"):
        path = write_doc(name, text)
        RmdManager(path).set_frontmatter_key(key, value)
        return read_doc(path)

    # No header: one is created, with a blank line before the body
    check_same("no header: created above prose", after_set("# Title\n\nText.\n", "title", "My Report"),
               "---\ntitle: My Report\n---\n\n# Title\n\nText.\n")
    check_same("no header: no second blank line", after_set("\n# Title\n", "title", "X"), "---\ntitle: X\n---\n\n# Title\n")
    check_same("no header: empty document", after_set("", "title", "X"), "---\ntitle: X\n---\n")
    check("no header: created above a chunk",
          [c.cell_type for c in parse(after_set("```{r}\nx\n```\n", "title", "X"))[1]], ["markdown", "code"])
    # Header closing at the end of the file
    check_same("end of file: new key before the fence", after_set("---\ntitle: x\n---", "author", "A"), "---\ntitle: x\nauthor: A\n---")
    # Repeated key: the first copy is replaced, later copies removed
    check_same("repeated key: one copy left", after_set("---\ntitle: a\nauthor: b\ntitle: c\n---\n", "title", "d"),
               "---\ntitle: d\nauthor: b\n---\n")
    # Keys keep their spelling, so a numeric key stays numeric
    text = after_set("---\n2020: old\n---\n", "2020", "new")
    check_same("key spelling: numeric key kept", text, "---\n2020: new\n---\n")
    check("key spelling: still an int key", parse(text)[0].data, {2020: "new"})
    check_same("key spelling: quoted key kept", after_set('---\n"my key" : 1\n---\n', "my key", "2"), '---\n"my key" : 2\n---\n')
    check_same("new key: quoted when YAML needs it", after_set("---\na: 1\n---\n", "fig: cap", "x"), '---\na: 1\n"fig: cap": x\n---\n')
    # Values
    text = after_set("---\ntitle: x\n---\n", "title", "a: b: c")
    check_same("value: invalid YAML is written as a quoted string", text, "---\ntitle: 'a: b: c'\n---\n")
    check("value: invalid YAML loads back as that string", parse(text)[0].data["title"], "a: b: c")
    check_same("value: empty is null", after_set("---\ntitle: x\n---\n", "draft", ""), "---\ntitle: x\ndraft: null\n---\n")
    check_same("value: impossible date kept as a string", after_set("---\ntitle: x\n---\n", "date", "2026-13-45"),
               "---\ntitle: x\ndate: '2026-13-45'\n---\n")
    # A document end marker stays last
    check_same("doc end marker: new key goes before it", after_set("---\ntitle: x\n...\n---\n", "z", "1"),
               "---\ntitle: x\nz: 1\n...\n---\n")
    # Comments-only header
    check_same("comments-only header: key added after them", after_set("---\n# notes\n---\n", "title", "x"),
               "---\n# notes\ntitle: x\n---\n")
    # Removing a missing key, or with no header
    path = write_doc("edge.rmd", "---\ntitle: x\n---\n")
    check("remove: missing key", server.remove_frontmatter_key(path, "nope"), "Error: Frontmatter has no key 'nope'")
    path = write_doc("edge.rmd", "Just prose.\n")
    check("remove: no header", server.remove_frontmatter_key(path, "title"), "Error: Frontmatter has no key 'title'")
    # An edit that would break another key is refused and the file left alone
    text = "---\nbase: &b\n  a: 1\nother: *b\n---\n"
    path = write_doc("edge.rmd", text)
    check("guard: breaking an alias is refused", server.set_frontmatter_key(path, "base", "a: 5"), "would break the rest of the header")
    check("guard: file unchanged", read_doc(path) == text, True)
    check("guard: removing the alias user is fine", server.remove_frontmatter_key(path, "other"), "Saved")
    check_same("guard: anchor kept after removing the alias user", read_doc(path), "---\nbase: &b\n  a: 1\n---\n")
    # A quoted value's continuation line starting with "#" belongs to the value; real comments stay put
    text = '---\ntitle: "foo\n# not a comment"\ndate: x\n# a real comment\n---\n'
    check("quoted continuation: it is part of the value", parse(text)[0].data["title"], "foo # not a comment")
    check_same("quoted continuation: set replaces the whole value", after_set(text, "title", "bar"),
               "---\ntitle: bar\ndate: x\n# a real comment\n---\n")
    path = write_doc("edge.rmd", text)
    RmdManager(path).remove_frontmatter_key("title")
    check_same("quoted continuation: remove takes the whole value", read_doc(path), "---\ndate: x\n# a real comment\n---\n")
    text = "---\nparams:\n  a: 1\n# about params\n\nabstract: |\n  x\n\n# after abstract\ndate: x\n---\n"
    check_same("block then comment: set keeps the comment", after_set(text, "params", "a: 2"), text.replace("  a: 1\n", "  a: 2\n"))
    path = write_doc("edge.rmd", text)
    RmdManager(path).remove_frontmatter_key("abstract")
    check_same("block scalar then comment: remove keeps the blank line and comment", read_doc(path),
               text.replace("abstract: |\n  x\n", ""))
    # A short value whose aliases nest is cheap to set: 7 levels stand for 10^7 leaves
    value = "&l0 [" + ", ".join(["x"] * 10) + "]"
    for level in range(1, 7):
        value = f"&l{level} [{value}" + f", *l{level - 1}" * 9 + "]"
    started = time.time()
    text = after_set("---\ntitle: x\n---\n", "nested", value)
    check("nested aliases: set returns at once", time.time() - started < 0.4, True)
    check_same("nested aliases: value written as given", text, f"---\ntitle: x\nnested: {value}\n---\n")


def test_frontmatter_unreadable():
    print("\n═══ frontmatter: headers that don't parse ═══")
    from rmd_editor import server
    # A tab used for indentation: invalid YAML, but the keys are still editable line by line
    text = "---\ntitle: Report\nparams:\n\tn: 1\noutput: html_document\n---\n\nBody\n"
    path = write_doc("broken.rmd", text)
    shown = server.get_frontmatter(path)
    check("broken: get_frontmatter says why", shown, "(the YAML header could not be parsed: found character '\\t'")
    check("broken: get_frontmatter gives the line and column", shown, "(line 4, column 1 of the file)")
    check("broken: get_frontmatter returns the raw text", shown, "title: Report\nparams:\n\tn: 1\noutput: html_document")
    check("broken: set works", server.set_frontmatter_key(path, "title", "New"), "Saved")
    check_same("broken: set changes only that line", read_doc(path), text.replace("title: Report", "title: New"))
    check("broken: remove works", server.remove_frontmatter_key(path, "output"), "Saved")
    check_same("broken: remove takes only that line", read_doc(path), text.replace("title: Report", "title: New").replace("output: html_document\n", ""))
    check("broken: set the broken key", server.set_frontmatter_key(path, "params", "n: 2"), "Saved")
    fm = RmdManager(path).frontmatter
    check("broken: header parses once fixed", (fm.error, fm.data), (None, {"title": "New", "params": {"n": 2}}))
    # Well-formed YAML holding an impossible date: no crash, and still editable
    path = write_doc("broken.rmd", "---\ndate: 2026-13-45\ntitle: x\n---\n\n```{r}\n1\n```\n")
    check("bad date: other tools still work", server.list_cells(path), "[1] code (r)")
    check("bad date: get_frontmatter says why and where", server.get_frontmatter(path), "month must be in 1..12 (line 2, column 7 of the file)")
    check("bad date: set works", server.set_frontmatter_key(path, "title", "y"), "Saved")
    check_same("bad date: set changes only that line", read_doc(path), "---\ndate: 2026-13-45\ntitle: y\n---\n\n```{r}\n1\n```\n")
    # A control character such as a form feed: the YAML reader refuses the header before parsing
    text = '---\ntitle: "a\fb"\n---\n\n```{r}\nx\n```\n'
    path = write_doc("broken.rmd", text)
    check("form feed: other tools still work", server.list_cells(path), "[1] code (r)")
    shown = server.get_frontmatter(path)
    check("form feed: get_frontmatter says why", shown, "(the YAML header could not be parsed: unacceptable character #x000c")
    check("form feed: get_frontmatter gives the line and column", shown,
          "special characters are not allowed (line 2, column 10 of the file); its raw text follows")
    check("form feed: get_frontmatter returns the raw text", shown, 'its raw text follows)\ntitle: "a\fb"')
    check("form feed: set works", server.set_frontmatter_key(path, "author", "B"), "Saved")
    check_same("form feed: set adds only that line", read_doc(path), text.replace('"\n---', '"\nauthor: B\n---'))
    # Line and column count the file's own lines: past a byte order mark, CRLF breaks and a NEL inside a line
    where = {
        "control character after a mark, in CRLF": (chr(0xFEFF) + '---\r\ntitle: x\r\nz: "a\x01b"\r\n---\r\n',
                                                     "unacceptable character #x0001: special characters are not allowed (line 3, column 6 of the file)"),
        "control character after a NEL": ('---\ntitle: "a\x85b"\nkey: "\x0c"\n---\n', "(line 3, column 7 of the file)"),
        "tab after a mark, in CRLF": (chr(0xFEFF) + "---\r\ntitle: x\r\n\tbad: 1\r\n---\r\n", "(line 3, column 1 of the file)"),
        "impossible date in a nested list": ("---\ntitle: x\nparams:\n  d: [1, 2026-02-30]\n---\n",
                                             "day is out of range for month (line 4, column 10 of the file)"),
        "the impossible date that was read first": ("---\nparams:\n  d: 2026-02-30\ndate: 2026-13-45\n---\n",
                                                    "month must be in 1..12 (line 4, column 7 of the file)"),
        "the one of two dates with one message that was read first": ("---\na: [2026-13-45]\nb: 2026-14-01\n---\n",
                                                                       "month must be in 1..12 (line 3, column 4 of the file)"),
    }
    for label, (text, error) in where.items():
        check(f"where: {label}", server.get_frontmatter(write_raw("broken.rmd", text)), error)
    path = write_doc("broken.rmd", "---\n{title: x, date: 2026-13-45}\n---\n")
    check("where: refused set gives the line too", server.set_frontmatter_key(path, "title", "y"),
          "Error: Frontmatter can't be edited key by key: month must be in 1..12 (line 2, column 18 of the file)")
    # Not a mapping: shown raw, and edits are refused without touching the file
    text = "---\n- a\n- b\n---\n\nBody\n"
    path = write_doc("broken.rmd", text)
    check("list header: get_frontmatter shows the raw text", server.get_frontmatter(path),
          "(the YAML header could not be parsed: it is not a mapping of key: value lines; its raw text follows)\n- a\n- b")
    check("list header: set refused", server.set_frontmatter_key(path, "title", "x"), "Error: Frontmatter can't be edited key by key")
    check("list header: remove refused", server.remove_frontmatter_key(path, "a"), "Error: Frontmatter can't be edited key by key")
    check("list header: file unchanged", read_doc(path) == text, True)
    # Flow-style mapping: readable, but not line-editable
    text = "---\n{title: x, author: y}\n---\n"
    path = write_doc("broken.rmd", text)
    check("flow header: get_frontmatter shows the keys", server.get_frontmatter(path), "title: x\nauthor: y")
    check("flow header: set refused", server.set_frontmatter_key(path, "title", "z"), "flow mapping")
    check("flow header: file unchanged", read_doc(path) == text, True)
    # Indented keys: valid YAML and readable, but not line-editable (as the README says)
    text = "---\n  title: x\n  author: y\n---\nB\n"
    path = write_doc("broken.rmd", text)
    check("indented header: get_frontmatter shows the keys", server.get_frontmatter(path), "title: x\nauthor: y")
    check("indented header: set refused", server.set_frontmatter_key(path, "title", "z"), "not one per line at column 0")
    check("indented header: remove refused", server.remove_frontmatter_key(path, "title"), "not one per line at column 0")
    check("indented header: file unchanged", read_doc(path) == text, True)


# ──────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────


def test_find_in_rmd():
    print("\n═══ find_in_rmd ═══")
    reset_fixture()
    mgr = RmdManager(FIXTURE_PATH)
    hits = mgr.find_in_rmd("plot")
    check("find: matches plot(x)", hits, "plot(x)")
    hits = mgr.find_in_rmd("# Introduction")
    check("find: matches heading", hits, "# Introduction")
    hits = mgr.find_in_rmd("___no_such_thing___")
    check("find: empty result", hits, "no matches")
    hits = mgr.find_in_rmd("")
    check("find: empty pattern", hits, "empty pattern")


# ──────────────────────────────────────────────
# Kernel dispatch (no IRkernel required)
# ──────────────────────────────────────────────


def test_kernel_name_mapping():
    print("\n═══ kernel name mapping ═══")
    check("r → ir", _language_to_kernel_name("r"), "ir")
    check("R → ir", _language_to_kernel_name("R"), "ir")
    check("python → python3", _language_to_kernel_name("python"), "python3")
    check("unknown → lowercase passthrough", _language_to_kernel_name("Foo"), "foo")


def test_kernel_state_not_started():
    print("\n═══ kernel_state (not started) ═══")
    from rmd_editor import kernel as _k
    reset_fixture()
    # Shut down if a previous test left one running
    _k.shutdown_kernel(FIXTURE_PATH)
    check("state: not started", _k.kernel_state(FIXTURE_PATH), "not started")


# ──────────────────────────────────────────────
# Kernel lifecycle (fake KernelManager; no IRkernel required)
# ──────────────────────────────────────────────


class _FakeKernelClient:
    """Answers every execute() with one ANSI-colored stream message, then idle."""

    def __init__(self):
        self._iopub: list[dict] = []

    def start_channels(self):
        pass

    def stop_channels(self):
        pass

    def wait_for_ready(self, timeout=None):
        pass

    def execute(self, code):
        msg_id = "fake-msg"
        parent = {"msg_id": msg_id}
        self._iopub = [
            {"parent_header": parent, "msg_type": "stream",
             "content": {"name": "stdout", "text": "\x1b[31mred\x1b[0m\n"}},
            {"parent_header": parent, "msg_type": "status", "content": {"execution_state": "idle"}},
        ]
        return msg_id

    def get_iopub_msg(self, timeout=None):
        if not self._iopub:
            raise queue.Empty
        return self._iopub.pop(0)


class _FakeKernelManager:
    """Stands in for jupyter_client.KernelManager and records the launch kwargs."""

    instances: list = []
    # Make start_kernel() / restart_kernel() fail like a missing kernel binary.
    fail_start = False
    fail_restart = False
    # Client type handed out by client(); None means _FakeKernelClient.
    client_class = None
    # Real managers have a log trait; the kernel module filters it during starts.
    log = logging.getLogger("tests.fake_kernel_manager")

    def __init__(self, kernel_name=""):
        self.kernel_name = kernel_name
        self.start_kwargs = None
        self.restart_kwargs = None
        self.alive = False
        self.cleaned_up = False
        self.interrupts = 0
        self.signals: list = []
        # Called by interrupt_kernel(); _ScriptedKernelClient uses it to end a "sleep" request.
        self.on_interrupt = None
        _FakeKernelManager.instances.append(self)

    def start_kernel(self, **kw):
        self.start_kwargs = kw
        if _FakeKernelManager.fail_start:
            raise FileNotFoundError(2, "No such file or directory", "fake-kernel-binary")
        self.alive = True

    def restart_kernel(self, **kw):
        self.restart_kwargs = kw
        if _FakeKernelManager.fail_restart:
            self.alive = False
            raise FileNotFoundError(2, "No such file or directory", "fake-kernel-binary")
        self.alive = True

    def is_alive(self):
        return self.alive

    def client(self):
        if _FakeKernelManager.client_class is not None:
            return _FakeKernelManager.client_class(self)
        return _FakeKernelClient()

    def interrupt_kernel(self):
        self.interrupts += 1
        if self.on_interrupt is not None:
            self.on_interrupt()

    def signal_kernel(self, signum):
        # The kernel module only signals to kill the process.
        self.signals.append(signum)
        self.alive = False

    def shutdown_kernel(self, **kw):
        self.alive = False

    def cleanup_resources(self):
        self.cleaned_up = True


class _DyingKernelClient(_FakeKernelClient):
    """Kills its kernel as soon as code is sent, so no idle message ever arrives."""

    def __init__(self, km):
        super().__init__()
        self._km = km

    def execute(self, code):
        self._km.alive = False
        return "fake-msg"

class _ErrorKernelClient(_FakeKernelClient):
    """Answers every execute() with an error output that has a traceback, then idle."""

    def __init__(self, km):
        super().__init__()

    def execute(self, code):
        parent = {"msg_id": "fake-msg"}
        error = {"ename": "simpleError", "evalue": "boom", "traceback": ["\x1b[31mError in f(): boom\x1b[0m", "Traceback:", "1. f()"]}
        self._iopub = [
            {"parent_header": parent, "msg_type": "error", "content": error},
            {"parent_header": parent, "msg_type": "status", "content": {"execution_state": "idle"}},
        ]
        return "fake-msg"

class _ScriptedKernelClient:
    """
    Thread-safe fake client with one shared iopub queue, like the real one. Each
    execute() gets its own msg_id, an execute_input at once, and its code echoed
    as stdout shortly after; code "sleep" only finishes once the kernel is
    interrupted, "stubborn" never does, and "late" starts (execute_input) only
    after 0.3s, ignoring interrupts until then, and then acts like "sleep".
    Records the most requests ever in flight at once.
    """

    def __init__(self, km):
        self._km = km
        self._iopub: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._count = 0
        self._in_flight = 0
        self.max_in_flight = 0

    def start_channels(self):
        pass

    def stop_channels(self):
        pass

    def wait_for_ready(self, timeout=None):
        pass

    def execute(self, code):
        with self._lock:
            self._count += 1
            msg_id = f"msg-{self._count}"
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        if code == "late":
            # Ignores interrupts until it starts, as ipykernel does
            self._km.on_interrupt = None
            threading.Timer(0.3, self._start, (msg_id, lambda: self._reply(msg_id, "interrupted"))).start()
        elif code == "sleep":
            self._start(msg_id, lambda: self._reply(msg_id, "interrupted"))
        else:
            self._start(msg_id, None)
            if code != "stubborn":
                threading.Timer(0.05, self._reply, (msg_id, code)).start()
        return msg_id

    def _start(self, msg_id, on_interrupt):
        """Begin running a request: install its interrupt handler, if it has one, then send execute_input."""
        if on_interrupt is not None:
            self._km.on_interrupt = on_interrupt
        self._iopub.put({"parent_header": {"msg_id": msg_id}, "msg_type": "execute_input", "content": {"code": ""}})

    def _reply(self, msg_id, text):
        parent = {"msg_id": msg_id}
        self._iopub.put({"parent_header": parent, "msg_type": "stream", "content": {"name": "stdout", "text": text}})
        self._iopub.put({"parent_header": parent, "msg_type": "status", "content": {"execution_state": "idle"}})

    def get_iopub_msg(self, timeout=None):
        msg = self._iopub.get(timeout=timeout)
        if msg["msg_type"] == "status":
            with self._lock:
                self._in_flight -= 1
        return msg


@contextlib.contextmanager
def _fake_kernels(client_class=None):
    """Run the block with _FakeKernelManager (handing out client_class clients) in place of KernelManager."""
    from rmd_editor import kernel as _k
    real_km = _k.KernelManager
    _FakeKernelManager.instances.clear()
    _FakeKernelManager.client_class = client_class
    _k.KernelManager = _FakeKernelManager
    try:
        yield
    finally:
        for path in list(_k._kernels):
            _k.shutdown_kernel(path)
        _k.KernelManager = real_km
        _FakeKernelManager.client_class = None
        _FakeKernelManager.fail_start = False
        _FakeKernelManager.fail_restart = False


def test_kernel_cwd():
    print("\n═══ kernel cwd (fake KernelManager) ═══")
    from rmd_editor import kernel as _k
    from rmd_editor import server
    reset_fixture()
    _k.shutdown_kernel(FIXTURE_PATH)
    real_km = _k.KernelManager
    _FakeKernelManager.instances.clear()
    _k.KernelManager = _FakeKernelManager
    try:
        out = RmdManager(FIXTURE_PATH).execute_cell(3)
        check("cwd: execute_cell returns the kernel output", out, "[stream:stdout] red")
        check("cwd: returned text has no ANSI codes", "\x1b[" in out, False)
        km = _FakeKernelManager.instances[-1]
        check("cwd: kernel name from chunk language", km.kernel_name, "ir")
        cwd = (km.start_kwargs or {}).get("cwd") or ""
        check("cwd: kernel starts in the .rmd folder", os.path.realpath(cwd) == os.path.realpath(WORK_DIR), True)
        check("cwd: restart_kernel returns Restarted", server.restart_kernel(FIXTURE_PATH), "Restarted")
        check("cwd: restart keeps the same KernelManager", _k.get_kernel(FIXTURE_PATH).km is km, True)
        # jupyter_client relaunches with the original start_kernel() kwargs unless
        # restart_kernel() overrides them (see test_jupyter_restart_keeps_cwd).
        check("cwd: restart does not override launch args", km.restart_kwargs, {"now": True})
    finally:
        _k.shutdown_kernel(FIXTURE_PATH)
        _k.KernelManager = real_km


def test_kernel_dead_session():
    print("\n═══ dead kernel (fake KernelManager) ═══")
    import time
    from rmd_editor import kernel as _k
    from rmd_editor import server
    reset_fixture()
    _k.shutdown_kernel(FIXTURE_PATH)
    real_km = _k.KernelManager
    _FakeKernelManager.instances.clear()
    _k.KernelManager = _FakeKernelManager
    try:
        sess = _k.get_or_start_kernel(FIXTURE_PATH)
        old_km = sess.km
        old_km.alive = False
        check("dead: kernel_state reports dead", _k.kernel_state(FIXTURE_PATH), "dead")
        _k.get_or_start_kernel(FIXTURE_PATH)
        check("dead: a new KernelManager replaces the dead one", sess.km is not old_km, True)
        check("dead: dead kernel's resources released", old_km.cleaned_up, True)
        sess.kc = _DyingKernelClient(sess.km)
        started = time.time()
        out = server.execute_cell(FIXTURE_PATH, 3, timeout=30)
        check("dead: death during execution is reported", out, "Kernel died during execution")
        check("dead: reported without waiting for the timeout", time.time() - started < 5, True)
    finally:
        _k.shutdown_kernel(FIXTURE_PATH)
        _k.KernelManager = real_km

def _scripted_doc(root: str) -> tuple[str, list[int]]:
    """Write an .rmd whose chunks are the _ScriptedKernelClient commands; returns (path, code cell indices)."""
    path = os.path.join(root, "scripted.rmd")
    with open(path, "w", encoding="utf-8") as f:
        f.write("```{r}\nsleep\n```\n\n```{r}\nafter\n```\n\n```{r}\nstubborn\n```\n\n```{r}\nlate\n```\n")
    return path, [i for i, c in enumerate(RmdManager(path).cells) if c.cell_type == "code"]


def test_kernel_timeout_interrupts():
    print("\n═══ timeout interrupts the chunk (fake KernelManager) ═══")
    from rmd_editor import kernel as _k
    from rmd_editor import server
    root = tempfile.mkdtemp(dir=WORK_DIR)
    path, code = _scripted_doc(root)
    old_grace = _k._INTERRUPT_GRACE
    _k._INTERRUPT_GRACE = 0.5
    try:
        with _fake_kernels(_ScriptedKernelClient):
            started = time.time()
            out = server.execute_cell(path, code[0], timeout=0.3)
            check("timeout: error says the chunk timed out", out, "Error: Execution failed: Execution timed out after 0.3s")
            check("timeout: error says it was interrupted", out, "the cell was interrupted and the kernel is ready")
            check("timeout: kernel interrupted once", _FakeKernelManager.instances[-1].interrupts, 1)
            check("timeout: returns right after the interrupt", time.time() - started < 2, True)
            started = time.time()
            check("timeout: next chunk runs", server.execute_cell(path, code[1]), "[stream:stdout] after")
            check("timeout: next chunk runs promptly", time.time() - started < 2, True)
            check("timeout: same kernel kept", len(_FakeKernelManager.instances), 1)
            started = time.time()
            out = server.execute_cell(path, code[2], timeout=0.3)
            check("timeout: ignored interrupt reported as still busy", out, "still busy 0.5s later")
            check("timeout: still-busy error suggests restart_kernel", out, "Use restart_kernel")
            check("timeout: still-busy error comes after the grace period", time.time() - started < 3, True)
            # A chunk that times out before the kernel has started it is interrupted once it starts
            # (an interrupt that comes earlier is ignored)
            started = time.time()
            out = server.execute_cell(path, code[3], timeout=0.05)
            check("timeout: chunk that starts late is still interrupted", out, "the cell was interrupted and the kernel is ready")
            # It starts after 0.3s; waiting out the 0.5s grace period instead would take longer
            check("timeout: late chunk interrupted as soon as it starts", time.time() - started < 0.5, True)
            # A timeout that isn't positive is refused before anything runs
            interrupts = _FakeKernelManager.instances[-1].interrupts
            for bad in (0, -1):
                check(f"timeout: execute_cell refuses timeout={bad}", server.execute_cell(path, code[1], timeout=bad),
                      f"Error: timeout must be a positive number of seconds, got {bad}")
            check("timeout: execute_all_cells refuses timeout=0", server.execute_all_cells(path, timeout=0),
                  "Error: timeout must be a positive number of seconds, got 0")
            check("timeout: refused timeouts interrupt nothing", _FakeKernelManager.instances[-1].interrupts, interrupts)
            out = server.execute_all_cells(path, timeout=0.3)
            check("timeout: execute_all_cells names the interrupted chunk", out,
                  f"Execution failed at cell {code[0]}: Execution timed out after 0.3s; the cell was interrupted")
    finally:
        _k._INTERRUPT_GRACE = old_grace
        shutil.rmtree(root, ignore_errors=True)


def test_kernel_concurrency():
    print("\n═══ concurrent kernel calls (fake KernelManager) ═══")
    from rmd_editor import kernel as _k
    from rmd_editor import server
    root = tempfile.mkdtemp(dir=WORK_DIR)
    path, _ = _scripted_doc(root)
    try:
        with _fake_kernels(_ScriptedKernelClient):
            # Concurrent first calls start one kernel
            barrier = threading.Barrier(4)

            def first_call():
                barrier.wait()
                return _k.get_or_start_kernel(path)

            starts = [in_thread(first_call) for _ in range(4)]
            for thread, _ in starts:
                thread.join(10)
            sessions = {id(result.get("value")) for _, result in starts}
            check("concurrent: one session for concurrent first calls", len(sessions), 1)
            check("concurrent: one kernel started", len(_FakeKernelManager.instances), 1)

            # Many executes at once: one request in flight at a time, each gets its own output
            sess = _k.get_kernel(path)
            barrier = threading.Barrier(6)

            def run(i):
                barrier.wait()
                return sess.execute(f"out-{i}", timeout=3)

            runs = [in_thread(run, i) for i in range(6)]
            for thread, _ in runs:
                thread.join(30)
            texts = [result["value"][0]["text"] if "value" in result else repr(result) for _, result in runs]
            check("concurrent: each execute gets exactly its own output", texts, [f"out-{i}" for i in range(6)])
            check("concurrent: requests never overlap on the client", sess.kc.max_in_flight, 1)

            # interrupt_kernel doesn't wait for the running execute
            thread, result = in_thread(sess.execute, "sleep", timeout=30)
            check("concurrent: chunk is running", wait_until(lambda: sess._executing), True)
            started = time.time()
            check("concurrent: interrupt_kernel during a running chunk", server.interrupt_kernel(path), "Interrupted")
            check("concurrent: interrupt_kernel returns at once", time.time() - started < 1, True)
            thread.join(5)
            check("concurrent: interrupted chunk's call returns its output",
                  result.get("value", [{}])[0].get("text"), "interrupted")

            # restart_kernel kills a running execute instead of waiting for it
            km = sess.km
            thread, result = in_thread(sess.execute, "stubborn", timeout=30)
            check("concurrent: chunk is running before restart", wait_until(lambda: sess._executing), True)
            started = time.time()
            check("concurrent: restart_kernel during a running chunk", server.restart_kernel(path), "Restarted")
            check("concurrent: restart_kernel doesn't wait for the chunk", time.time() - started < 5, True)
            thread.join(5)
            check("concurrent: running chunk fails when restarted", str(result.get("error")), "Kernel died during execution")
            check("concurrent: restart killed the kernel process", len(km.signals) >= 1, True)
            check("concurrent: kernel alive after restart", _k.kernel_state(path), "alive")

            # restart_kernel goes ahead of a call queued behind the running chunk, which then
            # runs on the restarted kernel: only the running chunk is lost
            kernels_before = len(_FakeKernelManager.instances)
            thread, result = in_thread(sess.execute, "stubborn", timeout=30)
            check("concurrent: chunk is running before restart with a call queued", wait_until(lambda: sess._executing), True)
            queued, queued_result = in_thread(sess.execute, "queued", timeout=30)
            time.sleep(0.3)  # let the second call queue up on the session lock
            check("concurrent: restart_kernel with a call queued", server.restart_kernel(path), "Restarted")
            thread.join(5)
            queued.join(5)
            check("concurrent: running chunk fails when restarted with a call queued",
                  str(result.get("error")), "Kernel died during execution")
            check("concurrent: queued call runs on the restarted kernel",
                  queued_result["value"][0]["text"] if "value" in queued_result else repr(queued_result), "queued")
            check("concurrent: no extra kernel started for the queued call", len(_FakeKernelManager.instances), kernels_before)
            check("concurrent: the restart reused the kernel", sess.km is km, True)

            # shutdown_kernel kills a running execute instead of waiting for it
            thread, result = in_thread(sess.execute, "stubborn", timeout=30)
            check("concurrent: chunk is running before shutdown", wait_until(lambda: sess._executing), True)
            started = time.time()
            check("concurrent: shutdown_kernel during a running chunk", server.shutdown_kernel(path), "Shutdown")
            check("concurrent: shutdown_kernel doesn't wait for the chunk", time.time() - started < 5, True)
            thread.join(5)
            check("concurrent: running chunk fails when shut down", str(result.get("error")), "Kernel died during execution")
            check("concurrent: state 'not started' after shutdown", _k.kernel_state(path), "not started")
            kernels_before = len(_FakeKernelManager.instances)
            try:
                sess.execute("late")
                check("concurrent: shut-down session refuses to execute", "no error", "Kernel was shut down")
            except _k.KernelError as e:
                check("concurrent: shut-down session refuses to execute", str(e), "Kernel was shut down")
            check("concurrent: shut-down session started no new kernel", len(_FakeKernelManager.instances), kernels_before)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_dead_kernel_cleanup():
    print("\n═══ dead kernel: interrupt and failed restarts (fake KernelManager) ═══")
    from rmd_editor import kernel as _k
    from rmd_editor import server
    reset_fixture()
    _k.shutdown_kernel(FIXTURE_PATH)
    with _fake_kernels():
        sess = _k.get_or_start_kernel(FIXTURE_PATH)
        sess.km.alive = False
        check("dead: state is dead", _k.kernel_state(FIXTURE_PATH), "dead")
        check("dead: interrupt_kernel reports the kernel is not running", server.interrupt_kernel(FIXTURE_PATH),
              "Error: Kernel is not running (its process has exited)")
        check("dead: no interrupt sent to the dead kernel", sess.km.interrupts, 0)

        # execute() finds its kernel dead and its own start attempt fails
        _FakeKernelManager.fail_start = True
        try:
            sess.execute("1 + 1")
            check("dead: failed start inside execute raises", "no error", "Kernel failed to start")
        except _k.KernelError as e:
            check("dead: failed start inside execute raises", str(e), "Kernel failed to start: [Errno 2]")
        check("dead: failed start inside execute leaves 'not started'", _k.kernel_state(FIXTURE_PATH), "not started")
        _FakeKernelManager.fail_start = False

        # A failed restart_kernel drops the session too
        _k.get_or_start_kernel(FIXTURE_PATH)
        _FakeKernelManager.fail_restart = True
        check("dead: failed restart error string", server.restart_kernel(FIXTURE_PATH),
              "Error: Kernel failed to restart: [Errno 2]")
        check("dead: failed restart leaves 'not started'", _k.kernel_state(FIXTURE_PATH), "not started")


def _wait_for_lines(path: str, n: int, timeout: float = 10.0) -> list:
    import time
    deadline = time.time() + timeout
    lines: list = []
    while time.time() < deadline:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
            if len(lines) >= n:
                break
        time.sleep(0.05)
    return lines


def test_jupyter_restart_keeps_cwd():
    print("\n═══ jupyter_client restart keeps cwd ═══")
    # No Jupyter kernel needed: this stand-in kernelspec only logs its working
    # directory, which shows the launch args that restart_kernel() reuses.
    import json
    import shutil
    import tempfile
    from jupyter_client import KernelManager
    from jupyter_client.kernelspec import KernelSpecManager
    root = tempfile.mkdtemp(dir=WORK_DIR)
    km = None
    try:
        kernels_dir = os.path.join(root, "kernels")
        work_dir = os.path.join(root, "work")
        os.makedirs(os.path.join(kernels_dir, "cwdprobe"))
        os.makedirs(work_dir)
        code = "import os, time; open('cwd.log', 'a').write(os.getcwd() + '\\n'); time.sleep(30)"
        spec = {"argv": [sys.executable, "-c", code, "{connection_file}"], "display_name": "cwd probe", "language": "python"}
        with open(os.path.join(kernels_dir, "cwdprobe", "kernel.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f)
        km = KernelManager(kernel_name="cwdprobe", kernel_spec_manager=KernelSpecManager(kernel_dirs=[kernels_dir]))
        km.start_kernel(cwd=work_dir)
        log_path = os.path.join(work_dir, "cwd.log")
        first = _wait_for_lines(log_path, 1)
        km.restart_kernel(now=True)
        both = _wait_for_lines(log_path, 2)
        want = os.path.realpath(work_dir)
        check("restart: first launch ran in cwd", [os.path.realpath(p) for p in first], [want])
        check("restart: relaunch ran in the same cwd", [os.path.realpath(p) for p in both], [want, want])
    finally:
        if km is not None:
            try:
                km.shutdown_kernel(now=True)
            except Exception:
                pass
        shutil.rmtree(root, ignore_errors=True)


def test_kernel_start_failures():
    print("\n═══ kernel start failures ═══")
    import json
    import shutil
    import tempfile
    from rmd_editor import kernel as _k
    from rmd_editor import server
    reset_fixture()
    _k.shutdown_kernel(FIXTURE_PATH)
    # Missing kernelspec, straight from the kernel module
    try:
        _k.get_or_start_kernel(FIXTURE_PATH, kernel_name="nosuchkernel-xyz")
        check("missing kernelspec: raises KernelError", "FAIL", "PASS")
    except _k.KernelError as e:
        check("missing kernelspec: message starts with 'No such kernel named'",
              str(e).startswith("No such kernel named nosuchkernel-xyz"), True)
    check("missing kernelspec: state is not started", _k.kernel_state(FIXTURE_PATH), "not started")
    # Missing kernelspec through the manager and the server tools
    with open(FIXTURE_PATH, "w", encoding="utf-8") as f:
        f.write("```{nosuchkernelxyz}\n1 + 1\n```\n")
    try:
        RmdManager(FIXTURE_PATH).execute_cell(0)
        check("execute_cell: raises RmdManagerError", "FAIL", "PASS")
    except RmdManagerError as e:
        check("execute_cell: raises RmdManagerError", str(e), "No such kernel named nosuchkernelxyz")
    check("execute_cell: state is not started", _k.kernel_state(FIXTURE_PATH), "not started")
    check("server execute_cell: error string", server.execute_cell(FIXTURE_PATH, 0), "Error: No such kernel named nosuchkernelxyz")
    check("server execute_all_cells: error string", server.execute_all_cells(FIXTURE_PATH), "Error: No such kernel named nosuchkernelxyz")
    check("server restart_kernel: error string", server.restart_kernel(FIXTURE_PATH), "Error: No kernel running")
    check("server interrupt_kernel: error string", server.interrupt_kernel(FIXTURE_PATH), "Error: No kernel running")
    # Broken kernelspec (argv points at a missing binary)
    root = tempfile.mkdtemp(dir=WORK_DIR)
    doc = os.path.join(root, "broken.rmd")
    old_jupyter_path = os.environ.get("JUPYTER_PATH")
    try:
        os.makedirs(os.path.join(root, "kernels", "brokenkernelxyz"))
        spec = {"argv": [os.path.join(root, "missing-binary"), "{connection_file}"], "display_name": "broken", "language": "r"}
        with open(os.path.join(root, "kernels", "brokenkernelxyz", "kernel.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f)
        os.environ["JUPYTER_PATH"] = root
        try:
            _k.get_or_start_kernel(doc, kernel_name="brokenkernelxyz")
            check("broken kernelspec: raises KernelError", "FAIL", "PASS")
        except _k.KernelError as e:
            check("broken kernelspec: raises KernelError", str(e), "Kernel failed to start")
        check("broken kernelspec: state is not started", _k.kernel_state(doc), "not started")
    finally:
        _k.shutdown_kernel(doc)
        if old_jupyter_path is None:
            os.environ.pop("JUPYTER_PATH", None)
        else:
            os.environ["JUPYTER_PATH"] = old_jupyter_path
        shutil.rmtree(root, ignore_errors=True)

def test_kernel_start_failure_logging():
    print("\n═══ kernel start failure logging ═══")
    # Real jupyter_client with stand-in kernelspecs; no kernel ever runs.
    from rmd_editor import kernel as _k
    root = tempfile.mkdtemp(dir=WORK_DIR)
    argvs = {
        "missingbinaryxyz": [os.path.join(root, "missing-binary"), "{connection_file}"],
        # A NUL byte makes Popen raise ValueError, which is not an expected start failure.
        "nulbytexyz": ["/bin/sh\x00", "{connection_file}"],
    }
    for name, argv in argvs.items():
        os.makedirs(os.path.join(root, "kernels", name))
        with open(os.path.join(root, "kernels", name, "kernel.json"), "w", encoding="utf-8") as f:
            json.dump({"argv": argv, "display_name": name, "language": "r"}, f)
    docs = {name: os.path.join(root, f"{name}.rmd") for name in ("nosuchkernelxyz", *argvs)}

    def start_logs(name: str) -> str:
        with captured_logs("rmd_editor.kernel", "traitlets") as logs:
            try:
                _k.get_or_start_kernel(docs[name], kernel_name=name)
            except _k.KernelError:
                pass
        return logs.getvalue()

    old_jupyter_path = os.environ.get("JUPYTER_PATH")
    os.environ["JUPYTER_PATH"] = root
    try:
        missing = start_logs("nosuchkernelxyz")
        check("logging: missing kernelspec logs one line", len(missing.strip().splitlines()), 1)
        check("logging: missing kernelspec line is the kernel module's warning", missing,
              "WARNING rmd_editor.kernel: No such kernel named nosuchkernelxyz")
        check("logging: missing kernelspec logs no traceback", "Traceback" in missing, False)

        binary = start_logs("missingbinaryxyz")
        check("logging: missing kernel binary logs one line", len(binary.strip().splitlines()), 1)
        check("logging: missing kernel binary line is the kernel module's warning", binary,
              "WARNING rmd_editor.kernel: Kernel failed to start: [Errno 2]")
        check("logging: missing kernel binary logs no traceback", "Traceback" in binary, False)
        check("logging: missing kernel binary skips the launcher dump", "Failed to run command" in binary, False)

        unexpected = start_logs("nulbytexyz")
        check("logging: unexpected start error keeps jupyter_client's traceback", unexpected, "Traceback")
        check("logging: unexpected start error names the exception", unexpected, "ValueError: embedded null byte")
        check("logging: unexpected start error keeps the launcher dump", unexpected, "Failed to run command")
        check("logging: unexpected start error also gets the warning line", unexpected,
              "WARNING rmd_editor.kernel: Kernel failed to start: embedded null byte")
        check("logging: states are 'not started'", [_k.kernel_state(d) for d in docs.values()], ["not started"] * 3)
    finally:
        if old_jupyter_path is None:
            os.environ.pop("JUPYTER_PATH", None)
        else:
            os.environ["JUPYTER_PATH"] = old_jupyter_path
        for doc in docs.values():
            _k.shutdown_kernel(doc)
        shutil.rmtree(root, ignore_errors=True)

    # Only those calls were filtered: jupyter_client's logger still reports the same kinds of errors.
    traitlets_log = logging.getLogger("traitlets")
    check("logging: no filter left on jupyter_client's logger",
          [f for f in traitlets_log.filters if isinstance(f, _k._QuietExpectedStartFailure)], [])
    with captured_logs("traitlets") as logs:
        try:
            raise FileNotFoundError("unrelated")
        except FileNotFoundError:
            traitlets_log.exception("unrelated diagnostic")
    check("logging: unrelated jupyter_client diagnostics still logged", logs.getvalue(), "unrelated diagnostic")

def _fake_kernelspec(root: str, name: str) -> None:
    """Write a stand-in kernelspec (never launched) to root/kernels/name."""
    os.makedirs(os.path.join(root, "kernels", name))
    with open(os.path.join(root, "kernels", name, "kernel.json"), "w", encoding="utf-8") as f:
        json.dump({"argv": ["false", "{connection_file}"], "display_name": name, "language": "julia"}, f)


def test_julia_kernel_resolution():
    print("\n═══ julia kernelspec resolution ═══")
    from jupyter_client.kernelspec import KernelSpecManager
    from rmd_editor import kernel as _k
    from rmd_editor import server
    root = tempfile.mkdtemp(dir=WORK_DIR)
    empty = os.path.join(root, "empty")
    specs = os.path.join(root, "specs")
    os.makedirs(empty)
    for name in ("julia-1.9", "julia-1.10", "julia-1.11", "julia-dev"):
        _fake_kernelspec(specs, name)
    doc = os.path.join(root, "julia.rmd")
    with open(doc, "w", encoding="utf-8") as f:
        f.write("```{julia}\n1 + 1\n```\n")
    # JUPYTER_DATA_DIR hides the user's own kernelspecs; JUPYTER_PATH adds the fakes.
    with env_vars(JUPYTER_PATH=empty, JUPYTER_DATA_DIR=empty):
        elsewhere = sorted(n for n in KernelSpecManager(ensure_native_kernel=False).find_kernel_specs() if n.startswith("julia"))
    if elsewhere:
        print(f"  [SKIP] julia resolution: system-wide Julia kernelspecs {elsewhere} would change the answers")
        return
    with env_vars(JUPYTER_PATH=empty, JUPYTER_DATA_DIR=empty):
        check("julia: none installed falls back to julia-1", _language_to_kernel_name("julia"), "julia-1")
        check("julia: the error names julia-1", server.execute_cell(doc, 0), "Error: No such kernel named julia-1")
        check("julia: nothing left running", _k.kernel_state(doc), "not started")
    with env_vars(JUPYTER_PATH=specs, JUPYTER_DATA_DIR=empty):
        with captured_logs("traitlets") as logs:
            check("julia: highest version wins, compared as numbers", _k.julia_kernel_name(), "julia-1.11")
        check("julia: the lookup logs nothing", logs.getvalue() == "", True)
        check("julia: chunk language is case-insensitive", _language_to_kernel_name("Julia"), "julia-1.11")
        with _fake_kernels():
            RmdManager(doc).execute_cell(0)
            check("julia: execute_cell starts the resolved kernelspec", _FakeKernelManager.instances[-1].kernel_name, "julia-1.11")
        _fake_kernelspec(specs, "julia-1")
        check("julia: julia-1 preferred over versioned names", _k.julia_kernel_name(), "julia-1")
        _fake_kernelspec(specs, "julia")
        check("julia: julia preferred over julia-1", _k.julia_kernel_name(), "julia")


def test_format_outputs_strips_ansi():
    print("\n═══ format_outputs strips ANSI ═══")
    import copy
    from rmd_editor import kernel as _k
    outputs = [
        {"output_type": "stream", "name": "stderr", "text": "\x1b[33mWarning:\x1b[0m slow\n"},
        {"output_type": "execute_result", "data": {"text/plain": "\x1b[1m[1] 42\x1b[22m"}},
        {"output_type": "display_data", "data": {"text/plain": "\x1b[32mok\x1b[39m"}},
        {"output_type": "error", "ename": "\x1b[31mError\x1b[0m", "evalue": "\x1b[1;31mboom\x1b[0m",
         "traceback": ["\x1b[31mtraceback\x1b[0m"]},
    ]
    before = copy.deepcopy(outputs)
    text = _k.format_outputs(outputs)
    check("ansi: no escape codes in returned text", "\x1b[" in text, False)
    check("ansi: stream text kept", text, "[stream:stderr] Warning: slow")
    check("ansi: result text kept", text, "[result] [1] 42")
    check("ansi: display text kept", text, "[display] ok")
    check("ansi: error text kept", text, "[error] Error: boom")
    check("ansi: error traceback kept, without codes", text, "[error] Error: boom\ntraceback")
    check("ansi: captured outputs left untouched", outputs == before, True)
    stream_only = _k.format_outputs([{"output_type": "stream", "name": "stdout", "text": "\x1b[2K\x1b[1Gdone\n"}])
    check("ansi: cursor codes stripped from stream-only output", stream_only, "[stream:stdout] done\n")

def test_format_outputs_traceback():
    print("\n═══ format_outputs: error tracebacks ═══")
    from rmd_editor import kernel as _k
    from rmd_editor import server
    python_error = {
        "output_type": "error", "ename": "ZeroDivisionError", "evalue": "division by zero",
        "traceback": [
            "\x1b[0;31m" + "-" * 20 + "\x1b[0m",
            "\x1b[0;31mZeroDivisionError\x1b[0m  Traceback (most recent call last)\nCell In[1], line 1\n----> 1 1/0",
            "\x1b[0;31mZeroDivisionError\x1b[0m: division by zero",
        ],
    }
    check_same("traceback: error line, then every traceback line without ANSI codes", _k.format_outputs([python_error]),
               "[error] ZeroDivisionError: division by zero\n" + "-" * 20
               + "\nZeroDivisionError  Traceback (most recent call last)\nCell In[1], line 1\n----> 1 1/0"
               + "\nZeroDivisionError: division by zero")
    check_same("traceback: none means just the error line",
               _k.format_outputs([{"output_type": "error", "ename": "E", "evalue": "v"}]), "[error] E: v")
    check_same("traceback: empty list means just the error line",
               _k.format_outputs([{"output_type": "error", "ename": "E", "evalue": "v", "traceback": []}]), "[error] E: v")
    check_same("traceback: a string traceback is kept",
               _k.format_outputs([{"output_type": "error", "ename": "E", "evalue": "v", "traceback": "line 1\nline 2"}]),
               "[error] E: v\nline 1\nline 2")
    mixed = [{"output_type": "stream", "name": "stdout", "text": "partial\n"},
             {"output_type": "error", "ename": "E", "evalue": "v", "traceback": ["tb"]}]
    check_same("traceback: after other outputs", _k.format_outputs(mixed), "[stream:stdout] partial\n\n[error] E: v\ntb")
    # Through the tools, with a fake kernel that answers with an R-style error
    reset_fixture()
    _k.shutdown_kernel(FIXTURE_PATH)
    with _fake_kernels(_ErrorKernelClient):
        check("traceback: execute_cell returns it", server.execute_cell(FIXTURE_PATH, 3),
              "[error] simpleError: boom\nError in f(): boom\nTraceback:\n1. f()")
        out = server.execute_all_cells(FIXTURE_PATH)
        check("traceback: execute_all_cells returns it", out, "── cell[1] ──\n[error] simpleError: boom\nError in f(): boom\nTraceback:\n1. f()")
        check("traceback: execute_all_cells still stops at the error", out, "Executed 1 cell(s), 1 error(s), stopped at cell 1")


# ──────────────────────────────────────────────
# Server schema
# ──────────────────────────────────────────────


def test_server_schema():
    print("\n═══ server schema ═══")
    import asyncio
    from importlib.metadata import version as pkg_version
    from rmd_editor import server
    tools = asyncio.run(server.mcp.list_tools())
    check("schema: tool count", len(tools), 24)
    check("schema: every tool has annotations", [t.name for t in tools if t.annotations is None], [])
    undescribed = [
        f"{t.name}.{name}"
        for t in tools
        for name, prop in t.input_schema.get("properties", {}).items()
        if not prop.get("description")
    ]
    check("schema: every parameter has a description", undescribed, [])
    read_only = sorted(t.name for t in tools if t.annotations and t.annotations.read_only_hint)
    check("schema: read-only tools", read_only, sorted([
        "list_cells", "get_cell", "get_chunk_options", "get_frontmatter", "find_in_rmd", "get_kernel_state",
    ]))
    destructive = sorted(t.name for t in tools if t.annotations and t.annotations.destructive_hint)
    check("schema: destructive tools", destructive, sorted([
        "create_rmd", "delete_cell", "merge_cells", "replace_cell_source", "set_chunk_option",
        "remove_chunk_option", "set_frontmatter_key", "remove_frontmatter_key", "restart_kernel",
        "shutdown_kernel", "execute_cell", "execute_all_cells",
    ]))
    open_world = sorted(t.name for t in tools if t.annotations and t.annotations.open_world_hint)
    check("schema: only execution tools are open-world", open_world, ["execute_all_cells", "execute_cell"])
    by_name = {t.name: t for t in tools}
    check("schema: defaults kept", by_name["create_rmd"].input_schema["properties"]["output_format"].get("default"), "html_document")
    check("schema: timeouts must be positive",
          [by_name[n].input_schema["properties"]["timeout"].get("exclusiveMinimum") for n in ("execute_cell", "execute_all_cells")],
          [0, 0])
    check("schema: instructions non-empty", bool((server.mcp.instructions or "").strip()), True)
    check("schema: version matches package metadata", server.mcp.version == pkg_version("rmd-editor-mcp"), True)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────


if __name__ == "__main__":
    # The kernel module logs one warning line per deliberately failed kernel start
    # (test_kernel_start_failure_logging checks those lines, and that jupyter_client adds nothing).
    logging.getLogger("rmd_editor.kernel").setLevel(logging.ERROR)

    WORK_DIR = tempfile.mkdtemp(prefix="rmd-editor-tests-")
    FIXTURE_PATH = os.path.join(WORK_DIR, "test_fixture.rmd")
    try:
        test_parser_round_trip()
        test_parser_edge_cases()
        test_parser_complex_options()
        test_no_trailing_newline()
        test_line_breaks()
        test_crlf_documents()
        test_mixed_line_endings()
        test_line_numbers_agree()
        test_byte_order_mark()
        test_create_rmd()
        test_create_rmd_quoting()
        test_extension_case()
        test_list_cells()
        test_get_cell()
        test_add_cell()
        test_delete_cell()
        test_move_cell()
        test_split_cell()
        test_merge_cells()
        test_empty_document_indexes()
        test_replace_cell_source()
        test_prepend_append_to_cell()
        test_chunk_options()
        test_chunk_header_values()
        test_chunk_body_lines()
        test_frontmatter()
        test_frontmatter_line_level()
        test_frontmatter_edge_cases()
        test_frontmatter_unreadable()
        test_find_in_rmd()
        test_kernel_name_mapping()
        test_kernel_state_not_started()
        test_kernel_cwd()
        test_kernel_dead_session()
        test_kernel_timeout_interrupts()
        test_kernel_concurrency()
        test_dead_kernel_cleanup()
        test_jupyter_restart_keeps_cwd()
        test_kernel_start_failures()
        test_kernel_start_failure_logging()
        test_julia_kernel_resolution()
        test_format_outputs_strips_ansi()
        test_format_outputs_traceback()
        test_server_schema()
    finally:
        # Runs even if a test crashed: stop any kernel still registered, then drop every file
        from rmd_editor import kernel as _kernel
        for kernel_path in list(_kernel._kernels):
            _kernel.shutdown_kernel(kernel_path)
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    print(f"\n{'═' * 40}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
