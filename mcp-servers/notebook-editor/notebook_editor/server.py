"""
Notebook Editor MCP Server -- cell-level operations for Jupyter .ipynb files.
"""
import logging
import os

from mcp.server.fastmcp import FastMCP

from notebook_editor.manager import NotebookManager, NotebookManagerError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("notebook-editor")

mcp = FastMCP("Notebook-Editor")


def _validate_file(file_path: str) -> str | None:
    """Return an error string if file_path is invalid, else None."""
    if not os.path.isabs(file_path):
        return f"file_path must be an absolute path, got: {file_path}"
    if not os.path.isfile(file_path):
        return f"File not found: {file_path}"
    if not file_path.endswith(".ipynb"):
        return f"File is not a .ipynb notebook: {file_path}"
    return None


# ──────────────────────────────────────────────
# Cell structure & navigation
# ──────────────────────────────────────────────

@mcp.tool()
def list_cells(file_path: str) -> str:
    """
    Return a formatted outline of all cells in a Jupyter notebook: index, type
    (code/markdown/raw), line count, execution count (if any), and a preview of
    the first line.

    Use this when: You're starting work on an unfamiliar notebook and want to see
    its structure at a glance. Always a good first call.
    Don't use this when: You need actual code symbols (functions/classes) -- use
    `list_notebook_symbols` instead.

    Example:
        file_path="/abs/path/to/notebook.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("list_cells: file='%s'", file_path)
        return NotebookManager(file_path).list_cells()
    except NotebookManagerError as e:
        logger.warning("list_cells: %s", e)
        return f"Cannot list cells: {e}"
    except Exception as e:
        logger.exception("list_cells crashed")
        return f"Internal error in list_cells: {type(e).__name__}: {e}"


@mcp.tool()
def get_cell(file_path: str, index: int) -> str:
    """
    Return the source text of a specific cell.

    Use this when: You need to read the exact contents of a cell (to reason about
    it before editing, or to display it to the user).
    Don't use this when: You need the whole notebook's structure -- use `list_cells`.

    Example:
        file_path="/abs/path/to/notebook.ipynb"
        index=3
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("get_cell: file='%s' index=%d", file_path, index)
        return NotebookManager(file_path).get_cell(index)
    except NotebookManagerError as e:
        logger.warning("get_cell: %s", e)
        return f"Cannot get cell: {e}"
    except Exception as e:
        logger.exception("get_cell crashed")
        return f"Internal error in get_cell: {type(e).__name__}: {e}"


@mcp.tool()
def add_cell(file_path: str, index: int, source: str = "", cell_type: str = "code") -> str:
    """
    Insert a new cell at the given index, shifting existing cells down. Default
    cell_type is 'code'. Pass -1 for index to append at the end of the notebook.

    Use this when: You need to add a new code cell, markdown explanation, or raw
    cell at a specific position.
    Don't use this when: You want to replace an existing cell's source -> use
    `replace_cell_source`. You want to merge content into an existing cell -> use
    `prepend_to_cell`/`append_to_cell`.

    Example:
        index=2
        source="import pandas as pd\\ndf = pd.read_csv('data.csv')"
        cell_type="code"    # default; other options: "markdown", "raw"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("add_cell: file='%s' index=%d type=%s", file_path, index, cell_type)
        mgr = NotebookManager(file_path)
        mgr.add_cell(index, source, cell_type)
        return f"Successfully added {cell_type} cell at index {index} in {file_path}."
    except NotebookManagerError as e:
        logger.warning("add_cell: %s", e)
        return f"Cannot add cell: {e}"
    except Exception as e:
        logger.exception("add_cell crashed")
        return f"Internal error in add_cell: {type(e).__name__}: {e}"


@mcp.tool()
def delete_cell(file_path: str, index: int) -> str:
    """
    Remove the cell at the given index, shifting subsequent cells up.

    Use this when: You want to remove an entire cell (obsolete code, outdated
    markdown).
    Don't use this when: You want to clear a cell's outputs but keep the code ->
    use `clear_outputs`.

    Example:
        index=5
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("delete_cell: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.delete_cell(index)
        return f"Successfully deleted cell at index {index} in {file_path}."
    except NotebookManagerError as e:
        logger.warning("delete_cell: %s", e)
        return f"Cannot delete cell: {e}"
    except Exception as e:
        logger.exception("delete_cell crashed")
        return f"Internal error in delete_cell: {type(e).__name__}: {e}"


@mcp.tool()
def move_cell(file_path: str, from_index: int, to_index: int) -> str:
    """
    Move a cell from one index to another. Other cells shift to accommodate.

    Use this when: You want to reorder cells (e.g., move imports to the top, move
    a helper function above its caller).

    Example:
        from_index=4
        to_index=1
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("move_cell: file='%s' from=%d to=%d", file_path, from_index, to_index)
        mgr = NotebookManager(file_path)
        mgr.move_cell(from_index, to_index)
        return f"Successfully moved cell from index {from_index} to {to_index}."
    except NotebookManagerError as e:
        logger.warning("move_cell: %s", e)
        return f"Cannot move cell: {e}"
    except Exception as e:
        logger.exception("move_cell crashed")
        return f"Internal error in move_cell: {type(e).__name__}: {e}"


@mcp.tool()
def split_cell(file_path: str, index: int, line_offset: int) -> str:
    """
    Split one cell into two at a line boundary. The first cell keeps lines
    [0:line_offset], and a new cell of the same type is inserted after with the
    rest. Outputs are cleared on both halves since the code has changed.

    Use this when: A cell has grown too large and should be broken into logical
    sections, or you want to insert a markdown cell in the middle of existing code.

    Example:
        index=3
        line_offset=10    # first cell keeps lines 0-9, new cell gets line 10 onwards
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("split_cell: file='%s' index=%d line_offset=%d", file_path, index, line_offset)
        mgr = NotebookManager(file_path)
        mgr.split_cell(index, line_offset)
        return f"Successfully split cell {index} at line {line_offset}."
    except NotebookManagerError as e:
        logger.warning("split_cell: %s", e)
        return f"Cannot split cell: {e}"
    except Exception as e:
        logger.exception("split_cell crashed")
        return f"Internal error in split_cell: {type(e).__name__}: {e}"


@mcp.tool()
def merge_cells(file_path: str, start_index: int, end_index: int) -> str:
    """
    Merge consecutive cells [start_index..end_index] (inclusive) into one. All
    cells in the range must be the same type (can't mix code and markdown).
    Outputs are cleared on the merged result.

    Use this when: Multiple small cells logically belong together.
    Don't use this when: The cells have different types -> move them or split them
    into a common type first.

    Example:
        start_index=2
        end_index=4    # merges cells 2, 3, and 4 into a single cell at index 2
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("merge_cells: file='%s' start=%d end=%d", file_path, start_index, end_index)
        mgr = NotebookManager(file_path)
        mgr.merge_cells(start_index, end_index)
        return f"Successfully merged cells {start_index}..{end_index}."
    except NotebookManagerError as e:
        logger.warning("merge_cells: %s", e)
        return f"Cannot merge cells: {e}"
    except Exception as e:
        logger.exception("merge_cells crashed")
        return f"Internal error in merge_cells: {type(e).__name__}: {e}"


# ──────────────────────────────────────────────
# Cell content editing
# ──────────────────────────────────────────────

@mcp.tool()
def replace_cell_source(file_path: str, index: int, new_source: str) -> str:
    """
    Replace the entire source text of a cell. Clears outputs and execution_count
    if the cell is a code cell.

    Use this when: You're rewriting a cell's content top-to-bottom.
    Don't use this when: You only need to add lines -> use `prepend_to_cell` or
    `append_to_cell`. You need AST-level Python edits within a cell -> convert
    to a .py file via jupytext, edit with ast-editor, convert back.

    Example:
        index=2
        new_source="import pandas as pd\\ndf = pd.read_parquet('data.parquet')"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_cell_source: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.replace_cell_source(index, new_source)
        return f"Successfully replaced source of cell {index} in {file_path}."
    except NotebookManagerError as e:
        logger.warning("replace_cell_source: %s", e)
        return f"Cannot replace cell source: {e}"
    except Exception as e:
        logger.exception("replace_cell_source crashed")
        return f"Internal error in replace_cell_source: {type(e).__name__}: {e}"


@mcp.tool()
def prepend_to_cell(file_path: str, index: int, source: str) -> str:
    """
    Prepend source text to the top of a cell. Clears outputs if it's a code cell.

    Use this when: You need to add setup code, imports, or preamble lines to the
    beginning of an existing cell.
    Don't use this when: You're replacing the whole cell -> use `replace_cell_source`.

    Example:
        index=3
        source="import numpy as np"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("prepend_to_cell: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.prepend_to_cell(index, source)
        return f"Successfully prepended to cell {index} in {file_path}."
    except NotebookManagerError as e:
        logger.warning("prepend_to_cell: %s", e)
        return f"Cannot prepend to cell: {e}"
    except Exception as e:
        logger.exception("prepend_to_cell crashed")
        return f"Internal error in prepend_to_cell: {type(e).__name__}: {e}"


@mcp.tool()
def append_to_cell(file_path: str, index: int, source: str) -> str:
    """
    Append source text to the bottom of a cell. Clears outputs if it's a code cell.

    Use this when: You need to add follow-up code, assertions, or logging to the
    end of an existing cell.
    Don't use this when: You're replacing the whole cell -> use `replace_cell_source`.

    Example:
        index=3
        source="print(df.shape)"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("append_to_cell: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.append_to_cell(index, source)
        return f"Successfully appended to cell {index} in {file_path}."
    except NotebookManagerError as e:
        logger.warning("append_to_cell: %s", e)
        return f"Cannot append to cell: {e}"
    except Exception as e:
        logger.exception("append_to_cell crashed")
        return f"Internal error in append_to_cell: {type(e).__name__}: {e}"


# ──────────────────────────────────────────────
# Outputs & metadata
# ──────────────────────────────────────────────

@mcp.tool()
def clear_outputs(file_path: str, index: int = -1) -> str:
    """
    Clear outputs and execution_count of a specific code cell, or of ALL code
    cells if index is -1 (default). Markdown/raw cells are untouched.

    Use this when: You want to clean up stale outputs before committing the
    notebook, or reset outputs before re-running cells.

    Example:
        index=-1    # clear all code cells (default)
        index=3     # clear only cell 3
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("clear_outputs: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.clear_outputs(None if index == -1 else index)
        scope = "all code cells" if index == -1 else f"cell {index}"
        return f"Successfully cleared outputs of {scope} in {file_path}."
    except NotebookManagerError as e:
        logger.warning("clear_outputs: %s", e)
        return f"Cannot clear outputs: {e}"
    except Exception as e:
        logger.exception("clear_outputs crashed")
        return f"Internal error in clear_outputs: {type(e).__name__}: {e}"


@mcp.tool()
def clear_execution_counts(file_path: str) -> str:
    """
    Reset execution_count to None on all code cells across the notebook. Outputs
    are preserved -- only the execution numbering is reset.

    Use this when: You want to remove the `In [3]:` / `Out [7]:` numbering noise
    (e.g., before committing to git) without losing the actual output data.

    Example:
        file_path="/abs/path/to/notebook.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("clear_execution_counts: file='%s'", file_path)
        mgr = NotebookManager(file_path)
        mgr.clear_execution_counts()
        return f"Successfully cleared execution counts in {file_path}."
    except NotebookManagerError as e:
        logger.warning("clear_execution_counts: %s", e)
        return f"Cannot clear execution counts: {e}"
    except Exception as e:
        logger.exception("clear_execution_counts crashed")
        return f"Internal error in clear_execution_counts: {type(e).__name__}: {e}"


@mcp.tool()
def get_outputs(file_path: str, index: int) -> str:
    """
    Return a formatted text representation of a code cell's outputs. Handles
    stream (stdout/stderr), execute_result, display_data, and error output types.

    Use this when: You need to see what a cell produced (e.g., to interpret an
    error or verify a result).
    Don't use this when: The cell isn't a code cell -> the tool will tell you so.

    Example:
        index=3
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("get_outputs: file='%s' index=%d", file_path, index)
        return NotebookManager(file_path).get_outputs(index)
    except NotebookManagerError as e:
        logger.warning("get_outputs: %s", e)
        return f"Cannot get outputs: {e}"
    except Exception as e:
        logger.exception("get_outputs crashed")
        return f"Internal error in get_outputs: {type(e).__name__}: {e}"


@mcp.tool()
def set_cell_metadata(file_path: str, index: int, key: str, value: str) -> str:
    """
    Set a metadata key on a specific cell. The value is parsed as JSON (so you
    can pass booleans, numbers, nested objects). Falls back to string if parsing
    fails.

    Use this when: You need to tag a cell with Jupyter metadata (e.g., `collapsed`,
    `tags`, `scrolled`, papermill parameters).

    Example:
        index=0
        key="tags"
        value='["parameters"]'    # JSON array
        # or
        key="collapsed"
        value="true"               # JSON boolean
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("set_cell_metadata: file='%s' index=%d key='%s'", file_path, index, key)
        mgr = NotebookManager(file_path)
        mgr.set_cell_metadata(index, key, value)
        return f"Successfully set metadata '{key}' on cell {index}."
    except NotebookManagerError as e:
        logger.warning("set_cell_metadata: %s", e)
        return f"Cannot set metadata: {e}"
    except Exception as e:
        logger.exception("set_cell_metadata crashed")
        return f"Internal error in set_cell_metadata: {type(e).__name__}: {e}"


# ──────────────────────────────────────────────
# Discovery (read-only)
# ──────────────────────────────────────────────

@mcp.tool()
def list_notebook_symbols(file_path: str) -> str:
    """
    Walk all code cells and list Python symbols (functions, classes, methods,
    top-level assignments, imports) with their cell index and line number. Uses
    Python's stdlib `ast` module so it works only for Python code cells.

    Use this when: You want a notebook-wide view of defined functions and classes
    (e.g., "where is `train_model` defined?"). Complements `list_cells` which
    shows only cell-level structure.

    Example:
        file_path="/abs/path/to/notebook.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("list_notebook_symbols: file='%s'", file_path)
        return NotebookManager(file_path).list_notebook_symbols()
    except NotebookManagerError as e:
        logger.warning("list_notebook_symbols: %s", e)
        return f"Cannot list notebook symbols: {e}"
    except Exception as e:
        logger.exception("list_notebook_symbols crashed")
        return f"Internal error in list_notebook_symbols: {type(e).__name__}: {e}"


@mcp.tool()
def find_in_notebook(file_path: str, pattern: str) -> str:
    """
    Search for a text pattern across all cell sources. Returns each match as
    `cell[i] line N (cell_type): <text>`. Case-sensitive substring match -- no
    regex. Searches code, markdown, and raw cells.

    Use this when: You need a quick text search across the whole notebook (e.g.,
    to find a variable name or a TODO marker).
    Don't use this when: You need scoped symbol search -> use `list_notebook_symbols`.

    Example:
        pattern="train_model"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("find_in_notebook: file='%s' pattern='%s'", file_path, pattern)
        return NotebookManager(file_path).find_in_notebook(pattern)
    except NotebookManagerError as e:
        logger.warning("find_in_notebook: %s", e)
        return f"Cannot search notebook: {e}"
    except Exception as e:
        logger.exception("find_in_notebook crashed")
        return f"Internal error in find_in_notebook: {type(e).__name__}: {e}"


# ──────────────────────────────────────────────
# Kernel execution (Phase 2)
# ──────────────────────────────────────────────

@mcp.tool()
def execute_cell(file_path: str, index: int, timeout: float = 60.0) -> str:
    """
    Execute a single code cell using the notebook's Python kernel. Captures
    outputs (stdout, results, errors, display data) and writes them back to the
    notebook file along with the execution_count. The kernel is started lazily
    on first execute and kept alive for the server's lifetime.

    Use this when: You want to run a specific cell and capture its output.
    Don't use this when: The cell isn't a code cell (markdown/raw cannot execute).
    You want to run the whole notebook -> use `execute_all_cells`.

    Example:
        index=3
        timeout=60.0    # seconds; default is 60
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("execute_cell: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.execute_cell(index, timeout=timeout)
        # Report the outputs captured
        return f"Successfully executed cell {index}.\n\n" + mgr.get_outputs(index)
    except NotebookManagerError as e:
        logger.warning("execute_cell: %s", e)
        return f"Cannot execute cell: {e}"
    except Exception as e:
        logger.exception("execute_cell crashed")
        return f"Internal error in execute_cell: {type(e).__name__}: {e}"


@mcp.tool()
def execute_all_cells(file_path: str, timeout: float = 60.0, stop_on_error: bool = True) -> str:
    """
    Execute all code cells in the notebook in order, updating outputs and
    execution_count on each. Markdown/raw cells and empty code cells are skipped.
    By default, execution stops at the first cell that raises an error.

    Use this when: You're running a full notebook top-to-bottom (e.g., for
    regeneration, CI, or batch re-execution).
    Don't use this when: You only need one cell -> use `execute_cell`.

    Example:
        timeout=60.0
        stop_on_error=true    # default; set to false to continue past errors
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("execute_all_cells: file='%s'", file_path)
        mgr = NotebookManager(file_path)
        return mgr.execute_all_cells(timeout=timeout, stop_on_error=stop_on_error)
    except NotebookManagerError as e:
        logger.warning("execute_all_cells: %s", e)
        return f"Cannot execute all cells: {e}"
    except Exception as e:
        logger.exception("execute_all_cells crashed")
        return f"Internal error in execute_all_cells: {type(e).__name__}: {e}"


@mcp.tool()
def get_kernel_state(file_path: str) -> str:
    """
    Return the current state of the Python kernel associated with this notebook:
    'not started', 'alive', or 'dead'. Does not start a kernel if none exists.

    Use this when: You want to check whether the notebook has an active kernel
    before executing anything.

    Example:
        file_path="/abs/path/to/notebook.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    try:
        from notebook_editor import kernel as _kernel
        state = _kernel.kernel_state(file_path)
        logger.info("get_kernel_state: file='%s' state=%s", file_path, state)
        return f"Kernel state for {file_path}: {state}"
    except Exception as e:
        logger.exception("get_kernel_state crashed")
        return f"Internal error in get_kernel_state: {type(e).__name__}: {e}"


@mcp.tool()
def restart_kernel(file_path: str) -> str:
    """
    Restart the Python kernel associated with this notebook. All in-memory state
    (imports, variables, defined functions) is lost. Outputs in the notebook file
    are preserved -- they are only cleared if you subsequently re-execute.

    Use this when: The kernel is in a bad state, or you want to start from a
    clean namespace without re-running all cells.

    Example:
        file_path="/abs/path/to/notebook.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    try:
        from notebook_editor import kernel as _kernel
        logger.info("restart_kernel: file='%s'", file_path)
        if _kernel.get_kernel(file_path) is None:
            return f"No kernel running for {file_path} -- nothing to restart."
        _kernel.restart_kernel(file_path)
        return f"Kernel restarted for {file_path}."
    except Exception as e:
        logger.exception("restart_kernel crashed")
        return f"Internal error in restart_kernel: {type(e).__name__}: {e}"


@mcp.tool()
def interrupt_kernel(file_path: str) -> str:
    """
    Send an interrupt signal (KeyboardInterrupt / SIGINT) to the Python kernel.
    Use this to stop a long-running or stuck cell without restarting the kernel.
    Variable state in the kernel is preserved.

    Use this when: A cell is taking too long, appears stuck in an infinite loop,
    or you want to abort the current execution.

    Example:
        file_path="/abs/path/to/notebook.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    try:
        from notebook_editor import kernel as _kernel
        logger.info("interrupt_kernel: file='%s'", file_path)
        if _kernel.get_kernel(file_path) is None:
            return f"No kernel running for {file_path} -- nothing to interrupt."
        _kernel.interrupt_kernel(file_path)
        return f"Interrupt signal sent to kernel for {file_path}."
    except Exception as e:
        logger.exception("interrupt_kernel crashed")
        return f"Internal error in interrupt_kernel: {type(e).__name__}: {e}"


@mcp.tool()
def shutdown_kernel(file_path: str) -> str:
    """
    Shut down the Python kernel associated with this notebook. Frees the process
    and releases resources. A new kernel will be started automatically if you
    call `execute_cell` again.

    Use this when: You're done with a notebook and want to release kernel
    resources, or you want a completely fresh start next time you execute.

    Example:
        file_path="/abs/path/to/notebook.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    try:
        from notebook_editor import kernel as _kernel
        logger.info("shutdown_kernel: file='%s'", file_path)
        if _kernel.get_kernel(file_path) is None:
            return f"No kernel running for {file_path} -- nothing to shut down."
        _kernel.shutdown_kernel(file_path)
        return f"Kernel shut down for {file_path}."
    except Exception as e:
        logger.exception("shutdown_kernel crashed")
        return f"Internal error in shutdown_kernel: {type(e).__name__}: {e}"


def main():
    logger.info("Starting Notebook Editor MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
