"""
Test suite for notebook-editor MCP server.

Uses nbformat to generate a fixture .ipynb file programmatically before each test,
so tests are idempotent and don't depend on a static file on disk. Every notebook
the tests write lives in a temporary directory that __main__ creates and always
removes, so a crash can't leave files behind in tests/.
"""
import asyncio
import contextlib
import importlib.metadata
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import nbformat
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell

from notebook_editor.manager import NotebookManager, NotebookManagerError, create_notebook

# Scratch directory for every notebook the tests write; set in __main__ via tempfile.mkdtemp()
WORK_DIR = None
FIXTURE_PATH = None

PASS = 0
FAIL = 0


def check(label: str, result, expected_substring) -> None:
    global PASS, FAIL
    if isinstance(result, str) and isinstance(expected_substring, str):
        ok = expected_substring in result
    else:
        ok = result == expected_substring
    if ok:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        print(f"     Expected to find: {expected_substring!r}")
        print(f"     Got: {result!r}")
        FAIL += 1


def reset_fixture() -> str:
    """Create a fresh fixture notebook with a known structure. Returns the path."""
    nb = new_notebook()
    nb.cells = [
        new_markdown_cell("# Analysis Notebook\n\nThis is a sample notebook for testing."),
        new_code_cell("import pandas as pd\nimport numpy as np"),
        new_code_cell("def load_data(path):\n    return pd.read_csv(path)\n\ndf = load_data('data.csv')"),
        new_code_cell("class Model:\n    def __init__(self):\n        self.weights = None\n\n    def fit(self, X, y):\n        pass"),
        new_markdown_cell("## Results"),
        new_code_cell("print('done')"),
    ]
    # Attach a stream output to one code cell so we can test get_outputs/clear_outputs
    nb.cells[1].execution_count = 1
    nb.cells[5].execution_count = 2
    nb.cells[5].outputs = [
        nbformat.v4.new_output(output_type="stream", name="stdout", text="done\n")
    ]
    nbformat.write(nb, FIXTURE_PATH)
    return FIXTURE_PATH


def read_notebook(path: str):
    return nbformat.read(path, as_version=4)

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
        time.sleep(0.05)
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


# ──────────────────────────────────────────────
# Cell structure & navigation
# ──────────────────────────────────────────────

def test_list_cells():
    print("\n═══ list_cells ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    out = mgr.list_cells()
    check("list_cells: first cell is markdown", out, "[0] markdown")
    check("list_cells: second cell is code", out, "[1] code")
    check("list_cells: cell count and preview shown", out, "Analysis Notebook")
    check("list_cells: execution count shown", out, "[exec 1]")


def test_get_cell():
    print("\n═══ get_cell ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    src = mgr.get_cell(1)
    check("get_cell: returns source", src, "import pandas as pd")
    check("get_cell: full content", src, "import numpy as np")


def test_add_cell():
    print("\n═══ add_cell ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.add_cell(2, "x = 42", cell_type="code")
    nb = read_notebook(path)
    check("add_cell: new cell inserted", nb.cells[2].source, "x = 42")
    check("add_cell: default type is code", nb.cells[2].cell_type, "code")
    check("add_cell: cells shifted down", nb.cells[3].source, "def load_data(path):\n    return pd.read_csv(path)\n\ndf = load_data('data.csv')")
    check("add_cell: total count increased", len(nb.cells), 7)

    # Append at end using -1
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.add_cell(-1, "# End", cell_type="markdown")
    nb = read_notebook(path)
    check("add_cell: appended at end with index=-1", nb.cells[-1].source, "# End")
    check("add_cell: markdown type respected", nb.cells[-1].cell_type, "markdown")


def test_delete_cell():
    print("\n═══ delete_cell ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.delete_cell(4)  # delete the "## Results" markdown
    nb = read_notebook(path)
    check("delete_cell: cell removed", len(nb.cells), 5)
    check("delete_cell: subsequent cells shifted up", nb.cells[4].source, "print('done')")


def test_move_cell():
    print("\n═══ move_cell ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.move_cell(5, 0)  # move the last code cell to the top
    nb = read_notebook(path)
    check("move_cell: cell moved to new position", nb.cells[0].source, "print('done')")
    check("move_cell: original position now has what was next", nb.cells[1].source, "# Analysis Notebook\n\nThis is a sample notebook for testing.")


def test_split_cell():
    print("\n═══ split_cell ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    # Cell 3 is the Model class with multiple lines
    original_count = 6
    mgr.split_cell(3, 3)  # split after line 2 (0-indexed: 3 means lines[0:3] in first half)
    nb = read_notebook(path)
    check("split_cell: total cell count increased by 1", len(nb.cells), original_count + 1)
    # Check the first half contains `class Model` and the second half continues
    check("split_cell: first half has class header", nb.cells[3].source, "class Model:")


def test_merge_cells():
    print("\n═══ merge_cells ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    # Merge cells 1 and 2 (both code cells)
    mgr.merge_cells(1, 2)
    nb = read_notebook(path)
    check("merge_cells: total count decreased", len(nb.cells), 5)
    merged = nb.cells[1].source
    check("merge_cells: first source included", merged, "import pandas")
    check("merge_cells: second source included", merged, "def load_data")

    # Attempt to merge cells of different types -> should fail
    path = reset_fixture()
    mgr = NotebookManager(path)
    try:
        mgr.merge_cells(0, 1)  # markdown + code -> error
        check("merge_cells: mixed types rejected", "FAIL", "PASS")
    except NotebookManagerError:
        check("merge_cells: mixed types rejected", "PASS", "PASS")


# ──────────────────────────────────────────────
# Cell content editing
# ──────────────────────────────────────────────

def test_replace_cell_source():
    print("\n═══ replace_cell_source ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.replace_cell_source(5, "print('replaced')")
    nb = read_notebook(path)
    check("replace_cell_source: new content present", nb.cells[5].source, "print('replaced')")
    check("replace_cell_source: outputs cleared on code cell", len(nb.cells[5].outputs), 0)
    check("replace_cell_source: execution count cleared", nb.cells[5].execution_count, None)


def test_prepend_to_cell():
    print("\n═══ prepend_to_cell ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.prepend_to_cell(1, "# Setup imports")
    nb = read_notebook(path)
    check("prepend_to_cell: new content at top", nb.cells[1].source.startswith("# Setup imports"), True)
    check("prepend_to_cell: original content preserved", nb.cells[1].source, "import pandas as pd")


def test_append_to_cell():
    print("\n═══ append_to_cell ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.append_to_cell(1, "from scipy import stats")
    nb = read_notebook(path)
    check("append_to_cell: new content at bottom", nb.cells[1].source.endswith("from scipy import stats"), True)
    check("append_to_cell: original content preserved", nb.cells[1].source, "import pandas as pd")


# ──────────────────────────────────────────────
# Outputs & metadata
# ──────────────────────────────────────────────

def test_clear_outputs():
    print("\n═══ clear_outputs ═══")
    # Clear a specific cell
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.clear_outputs(5)
    nb = read_notebook(path)
    check("clear_outputs: specific cell outputs cleared", len(nb.cells[5].outputs), 0)
    check("clear_outputs: specific cell exec count cleared", nb.cells[5].execution_count, None)
    # Other cell's execution_count preserved
    check("clear_outputs: other cells untouched", nb.cells[1].execution_count, 1)

    # Clear all
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.clear_outputs(None)
    nb = read_notebook(path)
    check("clear_outputs (all): all exec counts cleared", nb.cells[1].execution_count, None)
    check("clear_outputs (all): all outputs cleared", len(nb.cells[5].outputs), 0)

    # Trying to clear a markdown cell should error
    path = reset_fixture()
    mgr = NotebookManager(path)
    try:
        mgr.clear_outputs(0)  # markdown
        check("clear_outputs: markdown rejected", "FAIL", "PASS")
    except NotebookManagerError:
        check("clear_outputs: markdown rejected", "PASS", "PASS")


def test_clear_execution_counts():
    print("\n═══ clear_execution_counts ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.clear_execution_counts()
    nb = read_notebook(path)
    check("clear_execution_counts: all exec counts None", nb.cells[1].execution_count, None)
    check("clear_execution_counts: outputs preserved", len(nb.cells[5].outputs), 1)


def test_get_outputs():
    print("\n═══ get_outputs ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    out = mgr.get_outputs(5)
    check("get_outputs: shows stream output", out, "[stream stdout]")
    check("get_outputs: shows text content", out, "done")

    # Cell with no outputs
    path = reset_fixture()
    mgr = NotebookManager(path)
    out = mgr.get_outputs(2)
    check("get_outputs: empty when no outputs", out, "no outputs")

    # Markdown cell
    path = reset_fixture()
    mgr = NotebookManager(path)
    out = mgr.get_outputs(0)
    check("get_outputs: markdown cell reported", out, "markdown cell")


def test_set_cell_metadata():
    print("\n═══ set_cell_metadata ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    mgr.set_cell_metadata(1, "collapsed", "true")
    nb = read_notebook(path)
    check("set_cell_metadata: JSON bool parsed", nb.cells[1].metadata.get("collapsed"), True)

    mgr = NotebookManager(path)
    mgr.set_cell_metadata(1, "tags", '["setup", "imports"]')
    nb = read_notebook(path)
    check("set_cell_metadata: JSON array parsed", nb.cells[1].metadata.get("tags"), ["setup", "imports"])


# ──────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────


# ──────────────────────────────────────────────
# Kernel execution (Phase 2)
# ──────────────────────────────────────────────

def test_execute_cell():
    print("\n═══ execute_cell ═══")
    # Create a minimal notebook that doesn't depend on pandas/numpy (those may not be installed)
    nb = new_notebook()
    nb.cells = [
        new_code_cell("x = 6 * 7"),
        new_code_cell("print(f'answer is {x}')"),
        new_code_cell("x / 0"),  # will error
        new_markdown_cell("## End"),
    ]
    path = os.path.join(WORK_DIR, "test_exec.ipynb")
    nbformat.write(nb, path)

    mgr = NotebookManager(path)
    try:
        mgr.execute_cell(0)
        loaded = read_notebook(path)
        check("execute_cell: execution_count set", loaded.cells[0].execution_count, 1)

        mgr = NotebookManager(path)
        mgr.execute_cell(1)
        loaded = read_notebook(path)
        outputs = loaded.cells[1].outputs
        check("execute_cell: stream output captured", len(outputs), 1)
        # stdout text can be a list or a string depending on nbformat version
        text = outputs[0].get("text", "")
        if isinstance(text, list):
            text = "".join(text)
        check("execute_cell: stdout contains result", text, "answer is 42")

        # Error case
        mgr = NotebookManager(path)
        mgr.execute_cell(2)
        loaded = read_notebook(path)
        err_outputs = [o for o in loaded.cells[2].outputs if o.get("output_type") == "error"]
        check("execute_cell: error captured", len(err_outputs) >= 1, True)
        check("execute_cell: ZeroDivisionError", err_outputs[0].get("ename", ""), "ZeroDivisionError")

        # Markdown cell rejected
        mgr = NotebookManager(path)
        try:
            mgr.execute_cell(3)
            check("execute_cell: markdown rejected", "FAIL", "PASS")
        except NotebookManagerError:
            check("execute_cell: markdown rejected", "PASS", "PASS")
    finally:
        from notebook_editor import kernel as _kernel
        _kernel.shutdown_kernel(path)
        if os.path.exists(path):
            os.remove(path)


def test_execute_all_cells():
    print("\n═══ execute_all_cells ═══")
    nb = new_notebook()
    nb.cells = [
        new_code_cell("a = 10"),
        new_code_cell("b = a * 2"),
        new_markdown_cell("## Midpoint"),
        new_code_cell("print(b)"),
    ]
    path = os.path.join(WORK_DIR, "test_exec_all.ipynb")
    nbformat.write(nb, path)

    try:
        mgr = NotebookManager(path)
        summary = mgr.execute_all_cells()
        check("execute_all_cells: summary includes count", summary, "Executed 3 cells")

        loaded = read_notebook(path)
        check("execute_all_cells: all exec counts set", loaded.cells[3].execution_count is not None, True)
        # Stream output from print(b) should show 20
        text = loaded.cells[3].outputs[0].get("text", "")
        if isinstance(text, list):
            text = "".join(text)
        check("execute_all_cells: result propagated", text, "20")
    finally:
        from notebook_editor import kernel as _kernel
        _kernel.shutdown_kernel(path)
        if os.path.exists(path):
            os.remove(path)


def test_execute_all_cells_stop_on_error():
    print("\n═══ execute_all_cells (stop_on_error) ═══")
    nb = new_notebook()
    nb.cells = [
        new_code_cell("x = 1"),
        new_code_cell("raise ValueError('bad')"),
        new_code_cell("y = 2"),  # should not execute
    ]
    path = os.path.join(WORK_DIR, "test_exec_err.ipynb")
    nbformat.write(nb, path)

    try:
        mgr = NotebookManager(path)
        summary = mgr.execute_all_cells(stop_on_error=True)
        check("stop_on_error: summary mentions stopped", summary, "stopped at cell 1")

        loaded = read_notebook(path)
        check("stop_on_error: first cell executed", loaded.cells[0].execution_count is not None, True)
        check("stop_on_error: third cell NOT executed", loaded.cells[2].execution_count is None, True)
    finally:
        from notebook_editor import kernel as _kernel
        _kernel.shutdown_kernel(path)
        if os.path.exists(path):
            os.remove(path)


def test_kernel_lifecycle():
    print("\n═══ kernel lifecycle ═══")
    from notebook_editor import kernel as _kernel
    nb = new_notebook()
    nb.cells = [new_code_cell("z = 100")]
    path = os.path.join(WORK_DIR, "test_lifecycle.ipynb")
    nbformat.write(nb, path)

    try:
        check("kernel: initial state is 'not started'", _kernel.kernel_state(path), "not started")

        mgr = NotebookManager(path)
        mgr.execute_cell(0)
        check("kernel: alive after execute", _kernel.kernel_state(path), "alive")

        _kernel.restart_kernel(path)
        check("kernel: still alive after restart", _kernel.kernel_state(path), "alive")

        _kernel.shutdown_kernel(path)
        check("kernel: 'not started' after shutdown", _kernel.kernel_state(path), "not started")
    finally:
        _kernel.shutdown_kernel(path)
        if os.path.exists(path):
            os.remove(path)


def test_kernel_cwd():
    print("\n═══ kernel working directory ═══")
    from notebook_editor import kernel as _kernel
    nb_dir = os.path.join(WORK_DIR, "cwd_check")
    os.makedirs(nb_dir)
    with open(os.path.join(nb_dir, "data.txt"), "w") as f:
        f.write("relative-ok")
    nb = new_notebook()
    nb.cells = [
        new_code_cell("import os\nprint(os.getcwd())"),
        new_code_cell("print(open('data.txt').read())"),
    ]
    path = os.path.join(nb_dir, "test_cwd.ipynb")
    nbformat.write(nb, path)

    def run(index: int) -> str:
        NotebookManager(path).execute_cell(index)
        outputs = read_notebook(path).cells[index].outputs
        return "".join(o.get("text", "") for o in outputs if o.get("output_type") == "stream").strip()

    try:
        # realpath on both sides: macOS temp dirs live behind the /var -> /private/var symlink
        expected = os.path.realpath(nb_dir)
        check("kernel cwd: starts in the notebook's folder", os.path.realpath(run(0)), expected)
        check("kernel cwd: relative path resolves next to the notebook", run(1), "relative-ok")
        _kernel.restart_kernel(path)
        check("kernel cwd: kept after restart_kernel", os.path.realpath(run(0)), expected)
    finally:
        _kernel.shutdown_kernel(path)


def test_kernel_start_failures():
    print("\n═══ kernel start failures ═══")
    from notebook_editor import kernel as _kernel
    from notebook_editor import server

    # Missing kernelspec
    path = os.path.join(WORK_DIR, "test_missing_kernel.ipynb")
    create_notebook(path, kernel_name="nosuchkernel-xyz")
    NotebookManager(path).add_cell(0, "x = 1")
    try:
        try:
            _kernel.get_or_start_kernel(path)
            check("missing kernelspec: KernelError raised", "FAIL", "PASS")
        except _kernel.KernelError as e:
            check("missing kernelspec: message starts with 'No such kernel named'",
                  str(e).startswith("No such kernel named nosuchkernel-xyz"), True)
        check("missing kernelspec: no session left registered", _kernel.kernel_state(path), "not started")

        try:
            NotebookManager(path).execute_cell(0)
            check("missing kernelspec: execute_cell raises NotebookManagerError", "FAIL", "PASS")
        except NotebookManagerError as e:
            check("missing kernelspec: execute_cell raises NotebookManagerError", str(e), "No such kernel named")
        try:
            NotebookManager(path).execute_all_cells()
            check("missing kernelspec: execute_all_cells raises NotebookManagerError", "FAIL", "PASS")
        except NotebookManagerError as e:
            check("missing kernelspec: execute_all_cells raises NotebookManagerError", str(e), "No such kernel named")

        # The tools return their normal error strings, not "Internal error ..."
        check("missing kernelspec: execute_cell tool error string",
              server.execute_cell(path, 0), "Cannot execute cell: No such kernel named nosuchkernel-xyz")
        check("missing kernelspec: execute_all_cells tool error string",
              server.execute_all_cells(path), "Cannot execute all cells: No such kernel named nosuchkernel-xyz")
        check("missing kernelspec: get_kernel_state reports 'not started'",
              server.get_kernel_state(path), "not started")
    finally:
        _kernel.shutdown_kernel(path)

    # Broken kernelspec: it exists, but its executable doesn't
    jupyter_dir = os.path.join(WORK_DIR, "jupyter")
    spec_dir = os.path.join(jupyter_dir, "kernels", "broken-xyz")
    os.makedirs(spec_dir)
    with open(os.path.join(spec_dir, "kernel.json"), "w") as f:
        json.dump({
            "argv": [os.path.join(WORK_DIR, "no-such-kernel-binary"), "-f", "{connection_file}"],
            "display_name": "Broken",
            "language": "python",
        }, f)
    broken_path = os.path.join(WORK_DIR, "test_broken_kernel.ipynb")
    create_notebook(broken_path, kernel_name="broken-xyz")
    NotebookManager(broken_path).add_cell(0, "x = 1")
    old_jupyter_path = os.environ.get("JUPYTER_PATH")
    os.environ["JUPYTER_PATH"] = jupyter_dir
    try:
        check("broken kernelspec: execute_cell tool reports the start failure",
              server.execute_cell(broken_path, 0), "Cannot execute cell: Kernel failed to start")
        check("broken kernelspec: no session left registered", _kernel.kernel_state(broken_path), "not started")
    finally:
        if old_jupyter_path is None:
            os.environ.pop("JUPYTER_PATH", None)
        else:
            os.environ["JUPYTER_PATH"] = old_jupyter_path
        _kernel.shutdown_kernel(broken_path)


def test_ansi_stripped_from_returned_text():
    print("\n═══ ANSI codes stripped from returned text ═══")
    from notebook_editor import kernel as _kernel
    from notebook_editor import server

    # Colored outputs already in the file: returned text is clean, the file is unchanged
    nb = new_notebook()
    nb.cells = [new_code_cell("print('x')")]
    nb.cells[0].outputs = [
        nbformat.v4.new_output(output_type="stream", name="stdout", text="\x1b[31mred text\x1b[0m\n"),
        nbformat.v4.new_output(output_type="error", ename="ValueError", evalue="bad",
                               traceback=["\x1b[0;31mValueError\x1b[0m: bad"]),
    ]
    path = os.path.join(WORK_DIR, "test_ansi.ipynb")
    nbformat.write(nb, path)
    out = NotebookManager(path).get_outputs(0)
    check("ansi: get_outputs text has no escape codes", "\x1b[" in out, False)
    check("ansi: stream text kept", out, "red text")
    check("ansi: traceback text kept", out, "ValueError: bad")
    stored = read_notebook(path).cells[0].outputs
    check("ansi: stored stream output unchanged", stored[0]["text"], "\x1b[31mred text\x1b[0m")
    check("ansi: stored traceback unchanged", stored[1]["traceback"][0], "\x1b[0;31mValueError\x1b[0m")

    # A real kernel traceback returned through the execute_cell tool
    exec_path = os.path.join(WORK_DIR, "test_ansi_exec.ipynb")
    nb = new_notebook()
    nb.cells = [new_code_cell("1 / 0")]
    nbformat.write(nb, exec_path)
    try:
        out = server.execute_cell(exec_path, 0)
        check("ansi: execute_cell tool returned the error", out, "ZeroDivisionError")
        check("ansi: execute_cell tool text has no escape codes", "\x1b[" in out, False)
        check("ansi: get_outputs after a real traceback has no escape codes",
              "\x1b[" in NotebookManager(exec_path).get_outputs(0), False)
    finally:
        _kernel.shutdown_kernel(exec_path)


def test_kernel_dies_during_execution():
    print("\n═══ kernel dies during execution ═══")
    import time
    from notebook_editor import kernel as _kernel

    nb = new_notebook()
    nb.cells = [new_code_cell("import os; os._exit(1)"), new_code_cell("print('back')")]
    path = os.path.join(WORK_DIR, "test_kernel_dies.ipynb")
    nbformat.write(nb, path)
    try:
        started = time.time()
        try:
            NotebookManager(path).execute_cell(0, timeout=30)
            check("dies: kernel death reported as an error", "no error", "Kernel died during execution")
        except NotebookManagerError as e:
            check("dies: kernel death reported as an error", str(e), "Kernel died during execution")
        check("dies: reported well before the timeout", time.time() - started < 15, True)
        # The next execute starts a fresh kernel instead of reusing the dead one
        NotebookManager(path).execute_cell(1)
        check("dies: next execute runs on a fresh kernel", NotebookManager(path).get_outputs(1), "back")
    finally:
        _kernel.shutdown_kernel(path)

def test_kernel_timeout_interrupts():
    print("\n═══ timeout interrupts the cell ═══")
    from notebook_editor import kernel as _kernel
    from notebook_editor import server

    nb = new_notebook()
    nb.cells = [
        new_code_cell("x = 41"),
        new_code_cell("import time\ntime.sleep(30)"),
        new_code_cell("print(x + 1)"),
        # Ignores the interrupt, so it is still running after the grace period
        new_code_cell("import signal, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\ntime.sleep(30)"),
        new_code_cell("print('fresh', 'x' in globals())"),
    ]
    path = os.path.join(WORK_DIR, "test_timeout.ipynb")
    nbformat.write(nb, path)
    old_grace = _kernel._INTERRUPT_GRACE
    try:
        NotebookManager(path).execute_cell(0)
        started = time.time()
        try:
            NotebookManager(path).execute_cell(1, timeout=2)
            check("timeout: error raised", "no error", "Execution timed out")
        except NotebookManagerError as e:
            check("timeout: error says the cell timed out", str(e), "Execution timed out after 2s")
            check("timeout: error says the cell was interrupted", str(e), "the cell was interrupted")
        check("timeout: returns soon after the timeout, not after the cell", time.time() - started < 6, True)
        started = time.time()
        NotebookManager(path).execute_cell(2)
        check("timeout: next cell runs promptly", time.time() - started < 5, True)
        check("timeout: earlier variables survive", NotebookManager(path).get_outputs(2), "42")
        check("timeout: kernel still alive", _kernel.kernel_state(path), "alive")
        check("timeout: execute_cell tool error string", server.execute_cell(path, 1, timeout=1),
              "Cannot execute cell: Execution failed: Execution timed out after 1s; the cell was interrupted")

        # A cell that times out before the kernel has started it is interrupted once it starts
        # (ipykernel ignores an interrupt that comes earlier)
        started = time.time()
        check("timeout: tiny timeout still interrupts the cell", server.execute_cell(path, 1, timeout=0.001),
              "Execution timed out after 0.001s; the cell was interrupted and the kernel is ready")
        check("timeout: tiny timeout doesn't wait out the grace period", time.time() - started < 4, True)
        started = time.time()
        NotebookManager(path).execute_cell(2)
        check("timeout: next cell runs promptly after a tiny timeout", time.time() - started < 3, True)
        # The same when the cell times out while queued in the kernel behind a request sent
        # directly here: the interrupt waits for the cell instead of stopping that request
        # (sent with stop_on_error=False, so an interrupt there wouldn't abort the queued cell)
        _kernel.get_kernel(path).kc.execute("import time; time.sleep(1)", stop_on_error=False)
        started = time.time()
        check("timeout: cell queued in the kernel is interrupted once it starts",
              server.execute_cell(path, 1, timeout=0.2), "the cell was interrupted and the kernel is ready")
        check("timeout: queued cell's call returns soon after it starts", time.time() - started < 4, True)

        # A timeout that isn't positive is refused before anything runs
        for bad in (0, -1):
            check(f"timeout: execute_cell refuses timeout={bad}", server.execute_cell(path, 1, timeout=bad),
                  f"Cannot execute cell: timeout must be a positive number of seconds, got {bad}")
        check("timeout: execute_all_cells refuses timeout=0", server.execute_all_cells(path, timeout=0),
              "Cannot execute all cells: timeout must be a positive number of seconds, got 0")

        _kernel._INTERRUPT_GRACE = 1.0
        try:
            NotebookManager(path).execute_cell(3, timeout=1)
            check("timeout: ignored interrupt raises", "no error", "still busy")
        except NotebookManagerError as e:
            check("timeout: ignored interrupt reported as still busy", str(e), "still busy 1s later")
            check("timeout: still-busy error suggests restart_kernel", str(e), "Use restart_kernel")
        check("timeout: restart_kernel recovers a still-busy kernel", server.restart_kernel(path), "Restarted")
        started = time.time()
        NotebookManager(path).execute_cell(4)
        check("timeout: runs promptly after the restart", time.time() - started < 5, True)
        check("timeout: restarted kernel has a fresh namespace", NotebookManager(path).get_outputs(4), "fresh False")
    finally:
        _kernel._INTERRUPT_GRACE = old_grace
        _kernel.shutdown_kernel(path)


def test_kernel_concurrency():
    print("\n═══ concurrent kernel calls ═══")
    from notebook_editor import kernel as _kernel
    from notebook_editor import server

    nb = new_notebook()
    nb.cells = [
        new_code_cell("import time\ntime.sleep(1)\nprint('first')"),
        new_code_cell("print('second')"),
        new_code_cell("import time\ntime.sleep(30)"),
        new_code_cell("y = 1"),
        # Runs long enough that a restart polling for running cells would catch it
        new_code_cell("import time\ntime.sleep(1)\nprint('queued ran')"),
    ]
    path = os.path.join(WORK_DIR, "test_concurrency.ipynb")
    nbformat.write(nb, path)

    starts = []
    real_km = _kernel.KernelManager

    class CountingKernelManager(real_km):
        def start_kernel(self, **kw):
            starts.append(kw)
            return super().start_kernel(**kw)

    _kernel.KernelManager = CountingKernelManager
    try:
        # Two tools at once on a notebook with no kernel yet
        barrier = threading.Barrier(2)

        def run(index):
            barrier.wait()
            return server.execute_cell(path, index)

        t0, r0 = in_thread(run, 0)
        t1, r1 = in_thread(run, 1)
        t0.join(60)
        t1.join(60)
        out0, out1 = r0.get("value", repr(r0)), r1.get("value", repr(r1))
        check("concurrent: first call gets its own output", out0, "Successfully executed cell 0")
        check("concurrent: first call output", "first" in out0 and "second" not in out0, True)
        check("concurrent: second call gets its own output", out1, "Successfully executed cell 1")
        check("concurrent: second call output", "second" in out1 and "first" not in out1, True)
        check("concurrent: one kernel started for both calls", len(starts), 1)
        loaded = read_notebook(path)
        stored = ["".join(o.get("text", "") for o in loaded.cells[i].outputs) for i in (0, 1)]
        check("concurrent: both outputs saved to the file", stored, ["first\n", "second\n"])

        # Many executes on one session at once: none reads another's messages
        sess = _kernel.get_kernel(path)
        runs = [in_thread(sess.execute, f"print({i})", timeout=20) for i in range(6)]
        for thread, _ in runs:
            thread.join(60)
        texts = [
            "".join(o.get("text", "") for o in result["value"][0]) if "value" in result else repr(result)
            for _, result in runs
        ]
        check("concurrent: each execute gets exactly its own output", texts, [f"{i}\n" for i in range(6)])

        # interrupt_kernel doesn't wait for the running execute
        thread, result = in_thread(server.execute_cell, path, 2, timeout=60)
        check("concurrent: cell is running", wait_until(lambda: sess._executing), True)
        time.sleep(0.5)
        started = time.time()
        check("concurrent: interrupt_kernel during a running cell", server.interrupt_kernel(path), "Interrupted")
        check("concurrent: interrupt_kernel returns at once", time.time() - started < 2, True)
        thread.join(10)
        check("concurrent: interrupted cell's call returns", thread.is_alive(), False)
        check("concurrent: interrupted cell reports KeyboardInterrupt", result.get("value", repr(result)), "KeyboardInterrupt")

        # restart_kernel kills a running cell instead of waiting for it
        thread, result = in_thread(server.execute_cell, path, 2, timeout=60)
        check("concurrent: cell is running before restart", wait_until(lambda: sess._executing), True)
        started = time.time()
        check("concurrent: restart_kernel during a running cell", server.restart_kernel(path), "Restarted")
        check("concurrent: restart_kernel doesn't wait for the cell", time.time() - started < 15, True)
        thread.join(10)
        check("concurrent: running cell fails when restarted", result.get("value", repr(result)), "Kernel died during execution")
        check("concurrent: kernel alive after restart", _kernel.kernel_state(path), "alive")

        # restart_kernel goes ahead of a call queued behind the running cell, which then
        # runs on the restarted kernel: only the running cell is lost
        starts_before = len(starts)
        thread, result = in_thread(server.execute_cell, path, 2, timeout=60)
        check("concurrent: cell is running before restart with a call queued", wait_until(lambda: sess._executing), True)
        queued, queued_result = in_thread(server.execute_cell, path, 4)
        time.sleep(0.3)  # let the second call queue up on the session lock
        check("concurrent: restart_kernel with a call queued", server.restart_kernel(path), "Restarted")
        thread.join(10)
        queued.join(30)
        check("concurrent: running cell fails when restarted with a call queued",
              result.get("value", repr(result)), "Kernel died during execution")
        check("concurrent: queued call runs on the restarted kernel",
              queued_result.get("value", repr(queued_result)), "Successfully executed cell 4")
        check("concurrent: queued call gets its output", queued_result.get("value", ""), "queued ran")
        check("concurrent: no extra kernel started for the queued call", len(starts), starts_before)
        check("concurrent: same session after the restart", _kernel.get_kernel(path) is sess, True)

        # Edits saved while a cell runs are kept when its outputs are written
        thread, result = in_thread(NotebookManager(path).execute_cell, 0)
        check("concurrent: cell is running before the edit", wait_until(lambda: sess._executing), True)
        NotebookManager(path).replace_cell_source(3, "y = 2")
        thread.join(30)
        loaded = read_notebook(path)
        check("concurrent: edit made during execution kept", loaded.cells[3].source, "y = 2")
        check("concurrent: outputs of the running cell saved",
              "".join(o.get("text", "") for o in loaded.cells[0].outputs), "first\n")

        # A running cell changed to markdown meanwhile, keeping its id (as JupyterLab does), gets no outputs
        thread, result = in_thread(NotebookManager(path).execute_cell, 0)
        check("concurrent: cell is running before its type changes", wait_until(lambda: sess._executing), True)
        changed = read_notebook(path)
        changed.cells[0] = new_markdown_cell(changed.cells[0].source, id=changed.cells[0].id)
        nbformat.write(changed, path)
        thread.join(30)
        check("concurrent: execute finishes after the type change", result.get("value", repr(result)), "Update successful")
        saved = read_notebook(path)
        check("concurrent: cell changed to markdown stays markdown", saved.cells[0].cell_type, "markdown")
        check("concurrent: no outputs written to the markdown cell",
              [k for k in ("outputs", "execution_count") if k in saved.cells[0]], [])
        try:
            nbformat.validate(saved)
            valid = True
        except nbformat.ValidationError as e:
            valid = str(e).split("\n")[0]
        check("concurrent: file still valid after the type change", valid, True)

        # shutdown_kernel kills a running cell instead of waiting for it
        thread, result = in_thread(server.execute_cell, path, 2, timeout=60)
        check("concurrent: cell is running before shutdown", wait_until(lambda: sess._executing), True)
        started = time.time()
        check("concurrent: shutdown_kernel during a running cell", server.shutdown_kernel(path), "Shut down")
        check("concurrent: shutdown_kernel doesn't wait for the cell", time.time() - started < 15, True)
        thread.join(10)
        check("concurrent: running cell fails when shut down", result.get("value", repr(result)), "Kernel died during execution")
        check("concurrent: state 'not started' after shutdown", _kernel.kernel_state(path), "not started")
        try:
            sess.execute("1")
            check("concurrent: shut-down session refuses to execute", "no error", "Kernel was shut down")
        except _kernel.KernelError as e:
            check("concurrent: shut-down session refuses to execute", str(e), "Kernel was shut down")
        check("concurrent: shut-down session started no new kernel", _kernel.kernel_state(path), "not started")
    finally:
        _kernel.KernelManager = real_km
        _kernel.shutdown_kernel(path)

    # A file without stored cell ids (nbformat 4.4) still gets its outputs
    legacy_path = os.path.join(WORK_DIR, "test_no_ids.ipynb")
    with open(legacy_path, "w", encoding="utf-8") as f:
        json.dump({
            "nbformat": 4, "nbformat_minor": 4, "metadata": {},
            "cells": [{"cell_type": "code", "source": "print('legacy')", "metadata": {},
                       "outputs": [], "execution_count": None}],
        }, f)
    try:
        NotebookManager(legacy_path).execute_cell(0)
        check("no ids: outputs saved by position",
              "".join(o.get("text", "") for o in read_notebook(legacy_path).cells[0].outputs), "legacy\n")
    finally:
        _kernel.shutdown_kernel(legacy_path)


def test_dead_kernel_cleanup():
    print("\n═══ dead kernel: interrupt and failed restarts ═══")
    from notebook_editor import kernel as _kernel
    from notebook_editor import server

    nb = new_notebook()
    nb.cells = [new_code_cell("z = 1"), new_code_cell("print('alive again')")]
    path = os.path.join(WORK_DIR, "test_dead_kernel.ipynb")
    nbformat.write(nb, path)
    try:
        NotebookManager(path).execute_cell(0)
        sess = _kernel.get_kernel(path)
        sess._kill()
        check("dead: kernel process killed", wait_until(lambda: not sess.is_alive()), True)
        check("dead: get_kernel_state reports dead", server.get_kernel_state(path), "dead")
        check("dead: interrupt_kernel reports the kernel is not running", server.interrupt_kernel(path),
              "Cannot interrupt kernel: Kernel is not running (its process has exited)")
        NotebookManager(path).execute_cell(1)
        check("dead: next execute starts a new kernel", NotebookManager(path).get_outputs(1), "alive again")

        # execute() finds its kernel dead and its own start attempt fails
        sess = _kernel.get_kernel(path)
        sess._kill()
        wait_until(lambda: not sess.is_alive())
        sess.kernel_name = "nosuchkernel-xyz"
        with captured_logs():
            try:
                sess.execute("1")
                check("dead: failed start inside execute raises", "no error", "No such kernel named")
            except _kernel.KernelError as e:
                check("dead: failed start inside execute raises", str(e), "No such kernel named nosuchkernel-xyz")
        check("dead: failed start inside execute leaves 'not started'", _kernel.kernel_state(path), "not started")
    finally:
        _kernel.shutdown_kernel(path)

    # restart_kernel when the kernel's executable has gone away
    jupyter_dir = os.path.join(WORK_DIR, "jupyter-restart")
    spec_dir = os.path.join(jupyter_dir, "kernels", "wrapped-xyz")
    os.makedirs(spec_dir)
    launcher = os.path.join(jupyter_dir, "launch-python")
    with open(launcher, "w") as f:
        f.write(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    os.chmod(launcher, 0o755)
    with open(os.path.join(spec_dir, "kernel.json"), "w") as f:
        json.dump({
            "argv": [launcher, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "Wrapped",
            "language": "python",
        }, f)
    wrapped_path = os.path.join(WORK_DIR, "test_wrapped_kernel.ipynb")
    create_notebook(wrapped_path, kernel_name="wrapped-xyz")
    NotebookManager(wrapped_path).add_cell(0, "w = 1")
    old_jupyter_path = os.environ.get("JUPYTER_PATH")
    os.environ["JUPYTER_PATH"] = jupyter_dir
    try:
        NotebookManager(wrapped_path).execute_cell(0)
        check("failed restart: kernel started through the launcher", _kernel.kernel_state(wrapped_path), "alive")
        os.remove(launcher)
        # With the tool's own logger too, as a real server logs
        with captured_logs("notebook_editor.kernel", "notebook-editor", "traitlets") as logs:
            out = server.restart_kernel(wrapped_path)
        check("failed restart: tool error string", out, "Cannot restart kernel: Kernel failed to restart: [Errno 2]")
        check("failed restart: state 'not started'", _kernel.kernel_state(wrapped_path), "not started")
        lines = logs.getvalue().strip().splitlines()
        check("failed restart: one-line warnings only, from the kernel module and the tool",
              [line.split(":")[0] for line in lines if not line.startswith("INFO ")],
              ["WARNING notebook_editor.kernel", "WARNING notebook-editor"])
        check("failed restart: the kernel module's warning", logs.getvalue(),
              "WARNING notebook_editor.kernel: Kernel failed to restart: [Errno 2]")
        check("failed restart: no traceback logged", "Traceback" in logs.getvalue(), False)
    finally:
        if old_jupyter_path is None:
            os.environ.pop("JUPYTER_PATH", None)
        else:
            os.environ["JUPYTER_PATH"] = old_jupyter_path
        _kernel.shutdown_kernel(wrapped_path)


def test_kernel_start_failure_logging():
    print("\n═══ kernel start failure logging ═══")
    from notebook_editor import kernel as _kernel

    jupyter_dir = os.path.join(WORK_DIR, "jupyter-logging")
    argvs = {
        "missing-binary-xyz": [os.path.join(WORK_DIR, "no-such-kernel-binary"), "-f", "{connection_file}"],
        # A NUL byte makes Popen raise ValueError, which is not an expected start failure
        "nul-byte-xyz": ["/bin/sh\x00", "-f", "{connection_file}"],
    }
    for name, argv in argvs.items():
        os.makedirs(os.path.join(jupyter_dir, "kernels", name))
        with open(os.path.join(jupyter_dir, "kernels", name, "kernel.json"), "w") as f:
            json.dump({"argv": argv, "display_name": name, "language": "python"}, f)
    paths = {}
    for name in ("nosuchkernel-xyz", *argvs):
        paths[name] = os.path.join(WORK_DIR, f"test_logging_{name}.ipynb")
        create_notebook(paths[name], kernel_name=name)

    def start_logs(name: str) -> str:
        with captured_logs("notebook_editor.kernel", "traitlets") as logs:
            try:
                _kernel.get_or_start_kernel(paths[name])
            except _kernel.KernelError:
                pass
        return logs.getvalue()

    old_jupyter_path = os.environ.get("JUPYTER_PATH")
    os.environ["JUPYTER_PATH"] = jupyter_dir
    try:
        missing = start_logs("nosuchkernel-xyz")
        check("logging: missing kernelspec logs one line", len(missing.strip().splitlines()), 1)
        check("logging: missing kernelspec line is the kernel module's warning", missing,
              "WARNING notebook_editor.kernel: No such kernel named nosuchkernel-xyz")
        check("logging: missing kernelspec logs no traceback", "Traceback" in missing, False)

        binary = start_logs("missing-binary-xyz")
        check("logging: missing kernel binary logs one line", len(binary.strip().splitlines()), 1)
        check("logging: missing kernel binary line is the kernel module's warning", binary,
              "WARNING notebook_editor.kernel: Kernel failed to start: [Errno 2]")
        check("logging: missing kernel binary logs no traceback", "Traceback" in binary, False)
        check("logging: missing kernel binary skips the launcher dump", "Failed to run command" in binary, False)

        unexpected = start_logs("nul-byte-xyz")
        check("logging: unexpected start error keeps jupyter_client's traceback", unexpected, "Traceback")
        check("logging: unexpected start error names the exception", unexpected, "ValueError: embedded null byte")
        check("logging: unexpected start error keeps the launcher dump", unexpected, "Failed to run command")
        check("logging: unexpected start error also gets the warning line", unexpected,
              "WARNING notebook_editor.kernel: Kernel failed to start: embedded null byte")
    finally:
        if old_jupyter_path is None:
            os.environ.pop("JUPYTER_PATH", None)
        else:
            os.environ["JUPYTER_PATH"] = old_jupyter_path
        for path in paths.values():
            _kernel.shutdown_kernel(path)

    # Only those calls were filtered: jupyter_client's logger still reports the same kinds of errors
    traitlets_log = logging.getLogger("traitlets")
    check("logging: no filter left on jupyter_client's logger",
          [f for f in traitlets_log.filters if isinstance(f, _kernel._QuietExpectedStartFailure)], [])
    with captured_logs("traitlets") as logs:
        try:
            raise FileNotFoundError("unrelated")
        except FileNotFoundError:
            traitlets_log.exception("unrelated diagnostic")
    check("logging: unrelated jupyter_client diagnostics still logged", logs.getvalue(), "unrelated diagnostic")


def test_list_notebook_symbols():
    print("\n═══ list_notebook_symbols ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    out = mgr.list_notebook_symbols()
    check("list_notebook_symbols: function in cell 2 listed", out, "function load_data")
    check("list_notebook_symbols: cell index shown", out, "cell[2]")
    check("list_notebook_symbols: class in cell 3 listed", out, "class Model")
    check("list_notebook_symbols: method listed under class", out, "method Model.__init__")
    check("list_notebook_symbols: import listed", out, "import pandas")


def test_find_in_notebook():
    print("\n═══ find_in_notebook ═══")
    path = reset_fixture()
    mgr = NotebookManager(path)
    out = mgr.find_in_notebook("load_data")
    check("find_in_notebook: matches found", out, "cell[2]")
    check("find_in_notebook: content shown", out, "load_data")

    # No match
    path = reset_fixture()
    mgr = NotebookManager(path)
    out = mgr.find_in_notebook("nonexistent_xyz")
    check("find_in_notebook: not found message", out, "not found")

    # Matches across cell types
    out = mgr.find_in_notebook("Results")
    check("find_in_notebook: markdown cell matched", out, "markdown")


# ──────────────────────────────────────────────
# create_notebook tests
# ──────────────────────────────────────────────

def test_create_notebook():
    print("\n═══ create_notebook ═══")
    new_path = os.path.join(WORK_DIR, "test_created.ipynb")
    if os.path.exists(new_path):
        os.remove(new_path)

    # Default kernel
    result = create_notebook(new_path)
    check("create_notebook: returns success message", result, "Created empty notebook")
    check("create_notebook: file exists on disk", "PASS" if os.path.isfile(new_path) else "FAIL", "PASS")

    # Read it back and verify structure
    nb = read_notebook(new_path)
    check("create_notebook: nbformat version is 4", str(nb.nbformat), "4")
    check("create_notebook: has empty cells list", "PASS" if nb.cells == [] else "FAIL", "PASS")
    check("create_notebook: has kernelspec metadata", str(nb.metadata.get("kernelspec", {}).get("name")), "python3")
    check("create_notebook: has language_info", str(nb.metadata.get("language_info", {}).get("name")), "python")

    # Refuses overwrite by default
    try:
        create_notebook(new_path)
        check("create_notebook: refuses overwrite", "FAIL", "PASS")
    except NotebookManagerError as e:
        check("create_notebook: refuses overwrite (error raised)", str(e), "already exists")

    # Overwrite=True works
    result = create_notebook(new_path, overwrite=True)
    check("create_notebook: overwrite=True succeeds", result, "Created empty notebook")

    # Custom kernel
    os.remove(new_path)
    result = create_notebook(
        new_path,
        kernel_name="fabric-venv",
        kernel_display_name="Python (fabric venv)",
        language="python",
    )
    nb = read_notebook(new_path)
    check("create_notebook: custom kernel name", str(nb.metadata["kernelspec"]["name"]), "fabric-venv")
    check("create_notebook: custom display name", str(nb.metadata["kernelspec"]["display_name"]), "Python (fabric venv)")

    # NotebookManager can open the created file
    mgr = NotebookManager(new_path)
    check("create_notebook: created file opens with NotebookManager", mgr.list_cells(), "(notebook has no cells)")

    # Cell operations work on it
    mgr.add_cell(0, cell_type="code", source="print('hello')")
    mgr2 = NotebookManager(new_path)
    check("create_notebook: supports subsequent add_cell", mgr2.list_cells(), "[0] code")

    # Rejects missing parent directory
    try:
        create_notebook("/nonexistent/dir/foo.ipynb")
        check("create_notebook: rejects missing parent dir", "FAIL", "PASS")
    except NotebookManagerError as e:
        check("create_notebook: rejects missing parent dir (error)", str(e), "Parent directory does not exist")

    if os.path.exists(new_path):
        os.remove(new_path)


def test_non_python_kernel():
    print("\n═══ non-Python kernel (R) support ═══")
    r_path = os.path.join(WORK_DIR, "test_r_notebook.ipynb")
    if os.path.exists(r_path):
        os.remove(r_path)

    # create_notebook with R kernelspec
    create_notebook(
        r_path,
        kernel_name="ir",
        kernel_display_name="R",
        language="R",
    )
    nb = read_notebook(r_path)
    check("non-python: kernelspec.name is 'ir'", str(nb.metadata["kernelspec"]["name"]), "ir")
    check("non-python: language_info.name is 'R'", str(nb.metadata["language_info"]["name"]), "R")

    # Add an R code cell and try list_notebook_symbols -- should gracefully refuse
    mgr = NotebookManager(r_path)
    mgr.add_cell(0, cell_type="code", source="x <- function(n) { n * 2 }")
    mgr2 = NotebookManager(r_path)
    symbols = mgr2.list_notebook_symbols()
    check("non-python: list_notebook_symbols refuses for R", symbols, "only supported for Python notebooks")
    check("non-python: refusal message names the language", symbols, "'r'")
    check("non-python: refusal message suggests find_in_notebook", symbols, "find_in_notebook")

    # find_in_notebook still works on R cells (substring search is language-agnostic)
    hits = mgr2.find_in_notebook("function")
    check("non-python: find_in_notebook works on R cells", hits, "function")

    # Kernel dispatch -- verify get_or_start_kernel reads the kernelspec from disk.
    # Don't actually start the kernel (IRkernel may not be installed in CI); just
    # instantiate the session via the private path to check kernel_name resolution.
    from notebook_editor import kernel as _k
    name = _k._read_notebook_kernel_name(r_path)
    check("non-python: _read_notebook_kernel_name resolves 'ir'", name, "ir")

    # _notebook_language mapping
    check("non-python: _notebook_language returns 'r'", mgr2._notebook_language(), "r")

    # Missing kernelspec -- falls back to python behavior for backward compat
    blank_path = os.path.join(WORK_DIR, "test_blank_kernel.ipynb")
    nb_blank = new_notebook()
    nb_blank.metadata = {}
    nb_blank.cells = [new_code_cell("x = 1")]
    nbformat.write(nb_blank, blank_path)
    mgr_blank = NotebookManager(blank_path)
    check("non-python: missing kernelspec defaults to python", mgr_blank._notebook_language(), "python")
    check("non-python: missing kernelspec -> list_notebook_symbols runs", mgr_blank.list_notebook_symbols(), "variable x")
    os.remove(blank_path)

    os.remove(r_path)


# ──────────────────────────────────────────────
# Server schema (tool annotations, parameter descriptions, instructions, version)
# ──────────────────────────────────────────────

def test_server_schema():
    print("\n═══ server schema ═══")
    from notebook_editor import server
    tools = asyncio.run(server.mcp.list_tools())
    check("schema: tool count", len(tools), 23)
    check("schema: every tool has annotations", [t.name for t in tools if t.annotations is None], [])
    undescribed = [
        f"{t.name}.{name}"
        for t in tools
        for name, prop in t.input_schema.get("properties", {}).items()
        if not prop.get("description")
    ]
    check("schema: every parameter has a description", undescribed, [])
    by_name = {t.name: t for t in tools}
    check("schema: timeouts must be positive",
          [by_name[n].input_schema["properties"]["timeout"].get("exclusiveMinimum") for n in ("execute_cell", "execute_all_cells")],
          [0, 0])

    # (read_only_hint, destructive_hint, open_world_hint) -> tools expected to carry it
    expected_hints = {
        (True, False, False): ["find_in_notebook", "get_cell", "get_kernel_state", "get_outputs",
                               "list_cells", "list_notebook_symbols"],
        (False, False, False): ["add_cell", "interrupt_kernel", "move_cell"],
        (False, True, False): ["append_to_cell", "clear_execution_counts", "clear_outputs",
                               "create_notebook", "delete_cell", "merge_cells", "prepend_to_cell",
                               "replace_cell_source", "restart_kernel", "set_cell_metadata",
                               "shutdown_kernel", "split_cell"],
        (False, True, True): ["execute_all_cells", "execute_cell"],
    }
    actual_hints = {
        t.name: (t.annotations.read_only_hint, t.annotations.destructive_hint, t.annotations.open_world_hint)
        for t in tools
        if t.annotations is not None
    }
    for hints, names in expected_hints.items():
        actual = sorted(n for n, h in actual_hints.items() if h == hints)
        check(f"schema: tools annotated {hints}", actual, names)

    instructions = server.mcp.instructions or ""
    check("schema: server instructions are non-empty", bool(instructions.strip()), True)
    check("schema: server version matches the installed package",
          server.mcp.version, importlib.metadata.version("notebook-editor-mcp"))


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

if __name__ == "__main__":
    # Keep the server's info/warning logs for expected errors out of the output; crashes still show
    logging.getLogger("notebook-editor").setLevel(logging.ERROR)
    # ...and the kernel module's one warning line per deliberately failed kernel start
    # (test_kernel_start_failure_logging checks those lines, and that jupyter_client adds nothing)
    logging.getLogger("notebook_editor.kernel").setLevel(logging.ERROR)

    WORK_DIR = tempfile.mkdtemp(prefix="notebook-editor-tests-")
    FIXTURE_PATH = os.path.join(WORK_DIR, "test_fixture.ipynb")
    try:
        test_list_cells()
        test_get_cell()
        test_add_cell()
        test_delete_cell()
        test_move_cell()
        test_split_cell()
        test_merge_cells()
        test_replace_cell_source()
        test_prepend_to_cell()
        test_append_to_cell()
        test_clear_outputs()
        test_clear_execution_counts()
        test_get_outputs()
        test_set_cell_metadata()
        test_list_notebook_symbols()
        test_find_in_notebook()
        test_execute_cell()
        test_execute_all_cells()
        test_execute_all_cells_stop_on_error()
        test_kernel_lifecycle()
        test_kernel_cwd()
        test_kernel_start_failures()
        test_ansi_stripped_from_returned_text()
        test_kernel_dies_during_execution()
        test_kernel_timeout_interrupts()
        test_kernel_concurrency()
        test_dead_kernel_cleanup()
        test_kernel_start_failure_logging()
        test_create_notebook()
        test_non_python_kernel()
        test_server_schema()
    finally:
        # Runs even if a test crashed: stop any kernel still registered, then drop every file
        from notebook_editor import kernel as _kernel
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
