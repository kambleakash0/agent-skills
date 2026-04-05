"""
Test suite for notebook-editor MCP server.

Uses nbformat to generate a fixture .ipynb file programmatically before each test,
so tests are idempotent and don't depend on a static file on disk.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import nbformat
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell

from notebook_editor.manager import NotebookManager, NotebookManagerError

TESTS_DIR = os.path.dirname(__file__)
FIXTURE_PATH = os.path.join(TESTS_DIR, "test_fixture.ipynb")

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
    path = os.path.join(TESTS_DIR, "test_exec.ipynb")
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
    path = os.path.join(TESTS_DIR, "test_exec_all.ipynb")
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
    path = os.path.join(TESTS_DIR, "test_exec_err.ipynb")
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
    path = os.path.join(TESTS_DIR, "test_lifecycle.ipynb")
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
# Main
# ──────────────────────────────────────────────

if __name__ == "__main__":
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

    if os.path.exists(FIXTURE_PATH):
        os.remove(FIXTURE_PATH)

    print(f"\n{'═' * 40}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL > 0:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
