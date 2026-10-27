"""
Test suite for rmd-editor MCP server.

Uses programmatic fixtures — no static files. Actual R kernel execution is not
exercised (IRkernel isn't guaranteed to be installed), but kernel_name mapping
is verified.
"""
from __future__ import annotations

import os
import queue
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rmd_editor.manager import RmdManager, RmdManagerError, create_rmd, _language_to_kernel_name
from rmd_editor.parser import parse, serialize

TESTS_DIR = os.path.dirname(__file__)
FIXTURE_PATH = os.path.join(TESTS_DIR, "test_fixture.rmd")

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


# ──────────────────────────────────────────────
# create_rmd
# ──────────────────────────────────────────────


def test_create_rmd():
    print("\n═══ create_rmd ═══")
    new_path = os.path.join(TESTS_DIR, "test_created.rmd")
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
        create_rmd(os.path.join(TESTS_DIR, "wrong.txt"))
        check("create: rejects non-rmd extension", "FAIL", "PASS")
    except RmdManagerError as e:
        check("create: rejects non-rmd extension", str(e), ".rmd")
    os.remove(new_path)


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
    check("julia → julia-1", _language_to_kernel_name("julia"), "julia-1")
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

    def __init__(self, kernel_name=""):
        self.kernel_name = kernel_name
        self.start_kwargs = None
        self.restart_kwargs = None
        self.alive = False
        self.cleaned_up = False
        _FakeKernelManager.instances.append(self)

    def start_kernel(self, **kw):
        self.start_kwargs = kw
        self.alive = True

    def restart_kernel(self, **kw):
        self.restart_kwargs = kw

    def is_alive(self):
        return self.alive

    def client(self):
        return _FakeKernelClient()

    def interrupt_kernel(self):
        pass

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
        check("cwd: kernel starts in the .rmd folder", os.path.realpath(cwd) == os.path.realpath(TESTS_DIR), True)
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
    root = tempfile.mkdtemp()
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
    import logging
    import shutil
    import tempfile
    from rmd_editor import kernel as _k
    from rmd_editor import server
    reset_fixture()
    _k.shutdown_kernel(FIXTURE_PATH)
    # jupyter_client logs every failed start with a full traceback; keep the output readable.
    jc_log = logging.getLogger("traitlets")
    jc_log_level = jc_log.level
    jc_log.setLevel(logging.CRITICAL)
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
    root = tempfile.mkdtemp()
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
        jc_log.setLevel(jc_log_level)


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
    check("ansi: captured outputs left untouched", outputs == before, True)
    stream_only = _k.format_outputs([{"output_type": "stream", "name": "stdout", "text": "\x1b[2K\x1b[1Gdone\n"}])
    check("ansi: cursor codes stripped from stream-only output", stream_only, "[stream:stdout] done\n")


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
    check("schema: instructions non-empty", bool((server.mcp.instructions or "").strip()), True)
    check("schema: version matches package metadata", server.mcp.version == pkg_version("rmd-editor-mcp"), True)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────


if __name__ == "__main__":
    test_parser_round_trip()
    test_parser_edge_cases()
    test_parser_complex_options()
    test_create_rmd()
    test_list_cells()
    test_get_cell()
    test_add_cell()
    test_delete_cell()
    test_move_cell()
    test_split_cell()
    test_merge_cells()
    test_replace_cell_source()
    test_prepend_append_to_cell()
    test_chunk_options()
    test_frontmatter()
    test_find_in_rmd()
    test_kernel_name_mapping()
    test_kernel_state_not_started()
    test_kernel_cwd()
    test_kernel_dead_session()
    test_jupyter_restart_keeps_cwd()
    test_kernel_start_failures()
    test_format_outputs_strips_ansi()
    test_server_schema()

    if os.path.exists(FIXTURE_PATH):
        os.remove(FIXTURE_PATH)

    print(f"\n{'═' * 40}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
