"""
Notebook Editor MCP Server -- cell-level operations for Jupyter .ipynb files.
"""
import logging
import os
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from notebook_editor.manager import NotebookManager, NotebookManagerError, create_notebook as _create_notebook

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("notebook-editor")

# Condensed version of NOTEBOOK-EDITOR.md, sent to clients as MCP server instructions
_INSTRUCTIONS = (
    "Cell-level tools for Jupyter .ipynb files: use them, not generic edit or write "
    "tools, and pass absolute paths. "
    "Start with list_cells; get_cell reads a cell, find_in_notebook searches text, "
    "list_notebook_symbols lists Python symbols. "
    "Create notebooks with create_notebook, never hand-written JSON. "
    "Pick the narrowest edit: prepend_to_cell or append_to_cell to add lines, "
    "replace_cell_source only to rewrite a whole cell, add_cell for a new one "
    "(index -1 appends). "
    "Indices are zero-based and shift after adds, deletes, splits and merges: re-run "
    "list_cells. "
    "One kernel per notebook starts lazily on the first execute_cell or "
    "execute_all_cells, from metadata.kernelspec.name, in the notebook's folder, and "
    "keeps its state across calls: interrupt_kernel stops a stuck cell, "
    "restart_kernel clears the state, shutdown_kernel frees the kernel. "
    "A cell past its timeout is interrupted and the kernel keeps its state; if the "
    "error says the kernel is still busy, call restart_kernel."
)


def _server_version() -> str:
    try:
        return _pkg_version("notebook-editor-mcp")
    except PackageNotFoundError:
        return "0.0.0"


mcp = MCPServer("Notebook-Editor", instructions=_INSTRUCTIONS, version=_server_version())

# Tool behavior hints. Destructive covers anything that can discard cell content,
# outputs, metadata, an existing file, or in-memory kernel state.
_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
_ADDITIVE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
_DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
_RUNS_CODE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)

# Shared parameter types; the descriptions end up in each tool's inputSchema
FilePath = Annotated[str, Field(description="Absolute path to an existing .ipynb file.")]
CellIndex = Annotated[int, Field(description="Zero-based cell index, as list_cells shows it.")]


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

@mcp.tool(annotations=_READ_ONLY)
def list_cells(file_path: FilePath) -> str:
    """
    List every cell: index, type (code/markdown/raw), line count, execution
    count and a preview of its first line.

    Use this when: You start on a notebook; always a good first call.
    Don't use this when: You need functions or classes -> use `list_notebook_symbols`.

    Example: file_path="/abs/path/nb.ipynb"
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


@mcp.tool(annotations=_READ_ONLY)
def get_cell(file_path: FilePath, index: CellIndex) -> str:
    """
    Return one cell's full source text.

    Use this when: You need a cell's exact contents, e.g. before editing it.
    Don't use this when: You need the notebook's structure -> use `list_cells`.

    Example: index=3
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


@mcp.tool(annotations=_ADDITIVE)
def add_cell(
    file_path: FilePath,
    index: Annotated[int, Field(description="Zero-based position of the new cell; -1 or the cell count appends.")],
    source: Annotated[str, Field(description="Source of the new cell; empty by default.")] = "",
    cell_type: Annotated[str, Field(description="'code' (default), 'markdown' or 'raw'.")] = "code",
) -> str:
    """
    Insert a new cell at index, shifting later cells down.

    Use this when: You add a code, markdown or raw cell.
    Don't use this when: You rewrite a cell -> use `replace_cell_source`; you add
    lines to one -> use `prepend_to_cell` or `append_to_cell`.

    Example: index=-1, source="import pandas as pd"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("add_cell: file='%s' index=%d type=%s", file_path, index, cell_type)
        mgr = NotebookManager(file_path)
        mgr.add_cell(index, source, cell_type)
        return "Added"
    except NotebookManagerError as e:
        logger.warning("add_cell: %s", e)
        return f"Cannot add cell: {e}"
    except Exception as e:
        logger.exception("add_cell crashed")
        return f"Internal error in add_cell: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def delete_cell(file_path: FilePath, index: CellIndex) -> str:
    """
    Remove the cell at index; later cells shift up.

    Use this when: A whole cell is obsolete.
    Don't use this when: Only its outputs should go -> use `clear_outputs`.

    Example: index=5
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("delete_cell: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.delete_cell(index)
        return "Deleted"
    except NotebookManagerError as e:
        logger.warning("delete_cell: %s", e)
        return f"Cannot delete cell: {e}"
    except Exception as e:
        logger.exception("delete_cell crashed")
        return f"Internal error in delete_cell: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def move_cell(
    file_path: FilePath,
    from_index: Annotated[int, Field(description="Zero-based index of the cell to move.")],
    to_index: Annotated[int, Field(description="Zero-based index it ends up at; must be an existing index.")],
) -> str:
    """
    Move a cell to another index; the cells in between shift.

    Use this when: You reorder cells, e.g. move imports to the top.
    Don't use this when: You combine cells -> use `merge_cells`.

    Example: from_index=4, to_index=1
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("move_cell: file='%s' from=%d to=%d", file_path, from_index, to_index)
        mgr = NotebookManager(file_path)
        mgr.move_cell(from_index, to_index)
        return "Moved"
    except NotebookManagerError as e:
        logger.warning("move_cell: %s", e)
        return f"Cannot move cell: {e}"
    except Exception as e:
        logger.exception("move_cell crashed")
        return f"Internal error in move_cell: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def split_cell(
    file_path: FilePath,
    index: CellIndex,
    line_offset: Annotated[int, Field(description="Zero-based line where the new cell starts (find_in_notebook's line N is N-1), from 0 to the cell's line count.")],
) -> str:
    """
    Split a cell in two: it keeps the lines before line_offset, and a new cell of
    the same type right after it gets the rest. Outputs are cleared.

    Use this when: A cell is too large, or you want a markdown cell between its
    lines (split, then `add_cell` at index+1 with cell_type='markdown').
    Don't use this when: You need a new cell -> use `add_cell`.

    Example: index=3, line_offset=10 (the cell keeps its first 10 lines)
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("split_cell: file='%s' index=%d line_offset=%d", file_path, index, line_offset)
        mgr = NotebookManager(file_path)
        mgr.split_cell(index, line_offset)
        return "Split"
    except NotebookManagerError as e:
        logger.warning("split_cell: %s", e)
        return f"Cannot split cell: {e}"
    except Exception as e:
        logger.exception("split_cell crashed")
        return f"Internal error in split_cell: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def merge_cells(
    file_path: FilePath,
    start_index: Annotated[int, Field(description="Zero-based index of the first cell to merge.")],
    end_index: Annotated[int, Field(description="Zero-based index of the last cell to merge; must be greater than start_index.")],
) -> str:
    """
    Merge cells start_index..end_index (inclusive) into one, their sources joined
    by newlines. All must have the same type; outputs are cleared.

    Use this when: Several small cells belong together.
    Don't use this when: Their types differ (refused) -> regroup with `move_cell`.

    Example: start_index=2, end_index=4 (cells 2-4 become cell 2)
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("merge_cells: file='%s' start=%d end=%d", file_path, start_index, end_index)
        mgr = NotebookManager(file_path)
        mgr.merge_cells(start_index, end_index)
        return "Merged"
    except NotebookManagerError as e:
        logger.warning("merge_cells: %s", e)
        return f"Cannot merge cells: {e}"
    except Exception as e:
        logger.exception("merge_cells crashed")
        return f"Internal error in merge_cells: {type(e).__name__}: {e}"


# ──────────────────────────────────────────────
# Cell content editing
# ──────────────────────────────────────────────

@mcp.tool(annotations=_DESTRUCTIVE)
def replace_cell_source(
    file_path: FilePath,
    index: CellIndex,
    new_source: Annotated[str, Field(description="New source for the whole cell.")],
) -> str:
    """
    Replace a cell's whole source. A code cell's outputs and execution count
    are cleared.

    Use this when: You rewrite a cell top to bottom.
    Don't use this when: You add lines -> use `prepend_to_cell` or `append_to_cell`.

    Example: index=2, new_source="df = pd.read_parquet('data.parquet')"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("replace_cell_source: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.replace_cell_source(index, new_source)
        return "Updated"
    except NotebookManagerError as e:
        logger.warning("replace_cell_source: %s", e)
        return f"Cannot replace cell source: {e}"
    except Exception as e:
        logger.exception("replace_cell_source crashed")
        return f"Internal error in replace_cell_source: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def prepend_to_cell(
    file_path: FilePath,
    index: CellIndex,
    source: Annotated[str, Field(description="Text to add at the top; a newline is put between it and the old source if needed.")],
) -> str:
    """
    Add text at the top of a cell. A code cell's outputs are cleared.

    Use this when: You add imports or setup lines to an existing cell.
    Don't use this when: You rewrite the whole cell -> use `replace_cell_source`.

    Example: index=3, source="import numpy as np"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("prepend_to_cell: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.prepend_to_cell(index, source)
        return "Added"
    except NotebookManagerError as e:
        logger.warning("prepend_to_cell: %s", e)
        return f"Cannot prepend to cell: {e}"
    except Exception as e:
        logger.exception("prepend_to_cell crashed")
        return f"Internal error in prepend_to_cell: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def append_to_cell(
    file_path: FilePath,
    index: CellIndex,
    source: Annotated[str, Field(description="Text to add at the bottom; a newline is put between the old source and it if needed.")],
) -> str:
    """
    Add text at the bottom of a cell. A code cell's outputs are cleared.

    Use this when: You add follow-up code, checks or logging to an existing cell.
    Don't use this when: You rewrite the whole cell -> use `replace_cell_source`.

    Example: index=3, source="print(df.shape)"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("append_to_cell: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.append_to_cell(index, source)
        return "Added"
    except NotebookManagerError as e:
        logger.warning("append_to_cell: %s", e)
        return f"Cannot append to cell: {e}"
    except Exception as e:
        logger.exception("append_to_cell crashed")
        return f"Internal error in append_to_cell: {type(e).__name__}: {e}"


# ──────────────────────────────────────────────
# Outputs & metadata
# ──────────────────────────────────────────────

@mcp.tool(annotations=_DESTRUCTIVE)
def clear_outputs(
    file_path: FilePath,
    index: Annotated[int, Field(description="Zero-based index of the code cell to clear; -1 (default) clears all code cells.")] = -1,
) -> str:
    """
    Clear the outputs and execution count of one code cell, or of all of them.
    A markdown or raw cell's index is refused.

    Use this when: You drop stale outputs before a commit or a re-run.
    Don't use this when: Only the numbering should go -> use `clear_execution_counts`.

    Example: index=3
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("clear_outputs: file='%s' index=%d", file_path, index)
        mgr = NotebookManager(file_path)
        mgr.clear_outputs(None if index == -1 else index)
        return "Cleared"
    except NotebookManagerError as e:
        logger.warning("clear_outputs: %s", e)
        return f"Cannot clear outputs: {e}"
    except Exception as e:
        logger.exception("clear_outputs crashed")
        return f"Internal error in clear_outputs: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def clear_execution_counts(file_path: FilePath) -> str:
    """
    Reset every code cell's execution count (the In [3] numbering); outputs stay.

    Use this when: You remove numbering noise, e.g. before a commit.
    Don't use this when: Outputs should go too -> use `clear_outputs`.

    Example: file_path="/abs/path/nb.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("clear_execution_counts: file='%s'", file_path)
        mgr = NotebookManager(file_path)
        mgr.clear_execution_counts()
        return "Cleared"
    except NotebookManagerError as e:
        logger.warning("clear_execution_counts: %s", e)
        return f"Cannot clear execution counts: {e}"
    except Exception as e:
        logger.exception("clear_execution_counts crashed")
        return f"Internal error in clear_execution_counts: {type(e).__name__}: {e}"


@mcp.tool(annotations=_READ_ONLY)
def get_outputs(file_path: FilePath, index: CellIndex) -> str:
    """
    Return a code cell's stored outputs as text (streams, results, display data,
    errors), ANSI color codes removed; the file keeps them. A markdown or raw
    cell gets a note saying it has none.

    Use this when: You check what a cell produced, e.g. to read an error.
    Don't use this when: You want to run it -> `execute_cell` returns its outputs.

    Example: index=3
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


@mcp.tool(annotations=_DESTRUCTIVE)
def set_cell_metadata(
    file_path: FilePath,
    index: CellIndex,
    key: Annotated[str, Field(description="Cell metadata key; an existing value is overwritten.")],
    value: Annotated[str, Field(description="Value as JSON text (e.g. 'true', '42', '[\"parameters\"]'); stored as a plain string if not valid JSON.")],
) -> str:
    """
    Set one metadata key on a cell to a JSON value.

    Use this when: You tag a cell, e.g. `tags`, `collapsed` or papermill parameters.
    Don't use this when: You clear outputs or numbering -> use `clear_outputs` or
    `clear_execution_counts`.

    Example: index=0, key="tags", value='["parameters"]'
    """
    if err := _validate_file(file_path):
        return err
    try:
        logger.info("set_cell_metadata: file='%s' index=%d key='%s'", file_path, index, key)
        mgr = NotebookManager(file_path)
        mgr.set_cell_metadata(index, key, value)
        return "Updated"
    except NotebookManagerError as e:
        logger.warning("set_cell_metadata: %s", e)
        return f"Cannot set metadata: {e}"
    except Exception as e:
        logger.exception("set_cell_metadata crashed")
        return f"Internal error in set_cell_metadata: {type(e).__name__}: {e}"


# ──────────────────────────────────────────────
# Discovery (read-only)
# ──────────────────────────────────────────────

@mcp.tool(annotations=_READ_ONLY)
def list_notebook_symbols(file_path: FilePath) -> str:
    """
    List the Python functions, classes, methods, top-level assignments and
    imports in all code cells, with cell index and line (counting from 1).
    Python notebooks only; others get a message saying so.

    Use this when: You look for where something is defined, e.g. `train_model`.
    Don't use this when: You need the cell layout -> use `list_cells`; text in
    any language -> use `find_in_notebook`.

    Example: file_path="/abs/path/nb.ipynb"
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


@mcp.tool(annotations=_READ_ONLY)
def find_in_notebook(
    file_path: FilePath,
    pattern: Annotated[str, Field(description="Case-sensitive substring to find, not a regex.")],
) -> str:
    """
    Search every cell's source (code, markdown, raw) for a substring; each match
    comes back as `cell[i] line N (type): <text>`, N counting from 1.

    Use this when: You look for a name or a TODO across the notebook.
    Don't use this when: You need Python definitions -> use `list_notebook_symbols`.

    Example: pattern="train_model"
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

@mcp.tool(annotations=_RUNS_CODE)
def execute_cell(
    file_path: FilePath,
    index: Annotated[int, Field(description="Zero-based index of the code cell to run; markdown and raw cells are refused.")],
    timeout: Annotated[float, Field(gt=0, description="Seconds the cell may run; past that it is interrupted and an error returned, the kernel's state kept.")] = 60.0,
) -> str:
    """
    Run one code cell on the notebook's kernel, write its outputs and execution
    count into the file, and return the outputs. Calls on one notebook take
    turns, and edits saved while a cell runs are kept.

    Use this when: You run a cell and want its output.
    Don't use this when: You run the whole notebook -> use `execute_all_cells`.

    Example: index=3, timeout=120
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


@mcp.tool(annotations=_RUNS_CODE)
def execute_all_cells(
    file_path: FilePath,
    timeout: Annotated[float, Field(gt=0, description="Seconds each cell may run; past that it is interrupted and the run stops with an error.")] = 60.0,
    stop_on_error: Annotated[bool, Field(description="True (default) stops at the first cell that raises an error; false runs the rest too.")] = True,
) -> str:
    """
    Run every non-empty code cell in order, writing outputs and execution
    counts, and return a summary of executed and errored cells. If a cell times
    out or the kernel dies, the run stops with an error and saves no outputs.

    Use this when: You re-run a notebook top to bottom.
    Don't use this when: You need one cell -> use `execute_cell`.

    Example: stop_on_error=false
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


@mcp.tool(annotations=_READ_ONLY)
def get_kernel_state(file_path: FilePath) -> str:
    """
    Report the notebook's kernel state: 'not started', 'alive' or 'dead'. Never
    starts a kernel.

    Use this when: You check for a live kernel before running code.
    Don't use this when: A cell is stuck -> use `interrupt_kernel`.

    Example: file_path="/abs/path/nb.ipynb"
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


@mcp.tool(annotations=_DESTRUCTIVE)
def restart_kernel(file_path: FilePath) -> str:
    """
    Restart the notebook's kernel in the same folder: in-memory state is lost,
    outputs in the file stay. A running cell is not waited for; it fails with
    "Kernel died during execution", and calls queued behind it run afterwards.

    Use this when: The kernel is in a bad state, or you want a clean namespace.
    Don't use this when: You only need to stop a cell -> use `interrupt_kernel`.

    Example: file_path="/abs/path/nb.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    from notebook_editor import kernel as _kernel
    try:
        logger.info("restart_kernel: file='%s'", file_path)
        if _kernel.get_kernel(file_path) is None:
            return "Skipped (no kernel running)"
        _kernel.restart_kernel(file_path)
        return "Restarted"
    except _kernel.KernelError as e:
        logger.warning("restart_kernel: %s", e)
        return f"Cannot restart kernel: {e}"
    except Exception as e:
        logger.exception("restart_kernel crashed")
        return f"Internal error in restart_kernel: {type(e).__name__}: {e}"


@mcp.tool(annotations=_ADDITIVE)
def interrupt_kernel(file_path: FilePath) -> str:
    """
    Interrupt the running cell (a KeyboardInterrupt in Python) at once, even
    while an execute call waits on it; the kernel keeps its state. A dead kernel
    gives an error, and the next execute call starts a new one.

    Use this when: A cell is too slow or stuck.
    Don't use this when: The kernel itself is broken -> use `restart_kernel`.

    Example: file_path="/abs/path/nb.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    from notebook_editor import kernel as _kernel
    try:
        logger.info("interrupt_kernel: file='%s'", file_path)
        if _kernel.get_kernel(file_path) is None:
            return "Skipped (no kernel running)"
        _kernel.interrupt_kernel(file_path)
        return "Interrupted"
    except _kernel.KernelError as e:
        logger.warning("interrupt_kernel: %s", e)
        return f"Cannot interrupt kernel: {e}"
    except Exception as e:
        logger.exception("interrupt_kernel crashed")
        return f"Internal error in interrupt_kernel: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def shutdown_kernel(file_path: FilePath) -> str:
    """
    Shut down the notebook's kernel and free its process; the next execute call
    starts a new one. A running cell fails with "Kernel died during execution",
    and calls queued behind it with "Kernel was shut down".

    Use this when: You are done with a notebook, or want a fresh kernel next run.
    Don't use this when: You want a clean namespace now -> use `restart_kernel`.

    Example: file_path="/abs/path/nb.ipynb"
    """
    if err := _validate_file(file_path):
        return err
    try:
        from notebook_editor import kernel as _kernel
        logger.info("shutdown_kernel: file='%s'", file_path)
        if _kernel.get_kernel(file_path) is None:
            return "Skipped (no kernel running)"
        _kernel.shutdown_kernel(file_path)
        return "Shut down"
    except Exception as e:
        logger.exception("shutdown_kernel crashed")
        return f"Internal error in shutdown_kernel: {type(e).__name__}: {e}"


@mcp.tool(annotations=_DESTRUCTIVE)
def create_notebook(
    file_path: Annotated[str, Field(description="Absolute path for the new .ipynb file; its folder must exist.")],
    kernel_name: Annotated[str, Field(description="Kernelspec name for metadata.kernelspec.name (e.g. 'python3', 'ir'); must be an installed kernel to execute.")] = "python3",
    kernel_display_name: Annotated[str, Field(description="Kernel name shown in Jupyter; '' (default) uses kernel_name.")] = "",
    language: Annotated[str, Field(description="Kernel language for kernelspec.language and language_info.name (e.g. 'python', 'R').")] = "python",
    overwrite: Annotated[bool, Field(description="Replace an existing file; false (default) refuses.")] = False,
) -> str:
    """
    Create an empty notebook with valid nbformat metadata and a kernelspec,
    instead of writing notebook JSON by hand.

    Use this when: You need a new notebook.
    Don't use this when: It exists -> edit it with `add_cell` and the other tools;
    pass overwrite=true only to replace it on purpose.

    Example: file_path="/abs/path/new.ipynb", kernel_name="ir", language="R"
    """
    if not os.path.isabs(file_path):
        return f"file_path must be an absolute path, got: {file_path}"
    if not file_path.endswith(".ipynb"):
        return f"File is not a .ipynb notebook: {file_path}"
    try:
        logger.info("create_notebook: file='%s' kernel='%s'", file_path, kernel_name)
        _create_notebook(
            file_path,
            kernel_name=kernel_name,
            kernel_display_name=kernel_display_name or None,
            language=language,
            overwrite=overwrite,
        )
        return "Created"
    except NotebookManagerError as e:
        logger.warning("create_notebook: %s", e)
        return f"Cannot create notebook: {e}"
    except Exception as e:
        logger.exception("create_notebook crashed")
        return f"Internal error in create_notebook: {type(e).__name__}: {e}"


def main():
    logger.info("Starting Notebook Editor MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
