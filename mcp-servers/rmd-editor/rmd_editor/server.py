"""
MCP server exposing rmd-editor tools via FastMCP.
"""
from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from rmd_editor import kernel as _kernel
from rmd_editor.manager import (
    RmdManager,
    RmdManagerError,
    create_rmd as _create_rmd,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("rmd-editor")

mcp = FastMCP("rmd-editor")


def _err(e: Exception) -> str:
    return f"Error: {e}"


# ──────────────────────────────────────────────
# Notebook creation
# ──────────────────────────────────────────────


@mcp.tool()
def create_rmd(
    file_path: str,
    title: str = "",
    author: str = "",
    output_format: str = "html_document",
    overwrite: bool = False,
) -> str:
    """Create a new empty .rmd file with a minimal YAML frontmatter.

    Args:
        file_path: Absolute path for the new .rmd file.
        title: Optional document title for the YAML frontmatter.
        author: Optional author string for the YAML frontmatter.
        output_format: Pandoc/rmarkdown output format. Defaults to html_document.
            Other common values: pdf_document, word_document, github_document.
        overwrite: If True, overwrite an existing file. Defaults to False.

    Refuses to overwrite unless overwrite=True. Fails if the parent directory
    does not exist.
    """
    try:
        logger.info("create_rmd: path=%s", file_path)
        return _create_rmd(file_path, title=title, author=author, output_format=output_format, overwrite=overwrite)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Cell structure & navigation
# ──────────────────────────────────────────────


@mcp.tool()
def list_cells(file_path: str) -> str:
    """List all cells in the .rmd with index, type (code/markdown), language/label/option-count for code chunks, line count, and a one-line preview.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    try:
        return RmdManager(file_path).list_cells()
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def get_cell(file_path: str, index: int) -> str:
    """Return the source text of one cell (chunk body or prose).

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index. -1 means the last cell.
    """
    try:
        return RmdManager(file_path).get_cell(index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def add_cell(file_path: str, index: int, source: str = "", cell_type: str = "code") -> str:
    """Insert a new cell at the given index.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based insertion position. Pass -1 to append at the end.
        source: Initial cell body. For code cells this is the R/Python/etc. source;
            for markdown cells it is the prose text.
        cell_type: Either "code" (an R chunk by default) or "markdown" (prose).
    """
    try:
        return RmdManager(file_path).add_cell(index, source=source, cell_type=cell_type)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def delete_cell(file_path: str, index: int) -> str:
    """Delete the cell at the given index.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index.
    """
    try:
        return RmdManager(file_path).delete_cell(index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def move_cell(file_path: str, from_index: int, to_index: int) -> str:
    """Move a cell from one index to another.

    Args:
        file_path: Absolute path to a .rmd file.
        from_index: Source cell index.
        to_index: Destination cell index.
    """
    try:
        return RmdManager(file_path).move_cell(from_index, to_index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def split_cell(file_path: str, index: int, line_offset: int) -> str:
    """Split a cell into two at the given line offset (1-indexed, exclusive upper).

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index.
        line_offset: 1-indexed line number where the split happens; the first
            line_offset lines stay in the original cell, the rest move to the
            new cell.
    """
    try:
        return RmdManager(file_path).split_cell(index, line_offset)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def merge_cells(file_path: str, start_index: int, end_index: int) -> str:
    """Merge consecutive cells [start_index..end_index] inclusive. All cells must share the same cell_type (and language for code chunks).

    Args:
        file_path: Absolute path to a .rmd file.
        start_index: Zero-based index of the first cell to merge.
        end_index: Zero-based index of the last cell to merge (inclusive).
    """
    try:
        return RmdManager(file_path).merge_cells(start_index, end_index)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Cell content editing
# ──────────────────────────────────────────────


@mcp.tool()
def replace_cell_source(file_path: str, index: int, new_source: str) -> str:
    """Replace a cell's entire source text. Preserves chunk language, label, and options for code cells.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index.
        new_source: Replacement source text for the cell body.
    """
    try:
        return RmdManager(file_path).replace_cell_source(index, new_source)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def prepend_to_cell(file_path: str, index: int, source: str) -> str:
    """Prepend text to an existing cell's source.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index.
        source: Text to prepend to the cell body.
    """
    try:
        return RmdManager(file_path).prepend_to_cell(index, source)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def append_to_cell(file_path: str, index: int, source: str) -> str:
    """Append text to an existing cell's source.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index.
        source: Text to append to the cell body.
    """
    try:
        return RmdManager(file_path).append_to_cell(index, source)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Chunk options
# ──────────────────────────────────────────────


@mcp.tool()
def get_chunk_options(file_path: str, index: int) -> str:
    """Return the chunk's language, label, and all key=value options.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based index of a CODE cell (chunk). Markdown cells raise.
    """
    try:
        return RmdManager(file_path).get_chunk_options(index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def set_chunk_option(file_path: str, index: int, key: str, value: str) -> str:
    """Set or overwrite one chunk option. Special key "label" sets the chunk label.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based index of a CODE cell (chunk).
        key: Option name (e.g. echo, warning, fig.width, or the special "label").
        value: Option value as a string (e.g. "FALSE", "7", '"My caption"').
    """
    try:
        return RmdManager(file_path).set_chunk_option(index, key, value)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def remove_chunk_option(file_path: str, index: int, key: str) -> str:
    """Remove one chunk option. Use key="label" to clear the chunk label.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based index of a CODE cell (chunk).
        key: Option name to remove (or "label" to clear the chunk label).
    """
    try:
        return RmdManager(file_path).remove_chunk_option(index, key)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# YAML frontmatter
# ──────────────────────────────────────────────


@mcp.tool()
def get_frontmatter(file_path: str) -> str:
    """Return the YAML frontmatter as a formatted YAML string.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    try:
        return RmdManager(file_path).get_frontmatter()
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def set_frontmatter_key(file_path: str, key: str, value: str) -> str:
    """Set or overwrite one top-level YAML frontmatter key. Value is parsed as YAML when possible.

    Args:
        file_path: Absolute path to a .rmd file.
        key: Top-level YAML key (e.g. title, author, output).
        value: Value as a string; parsed as YAML where possible (so "true" becomes
            bool, "42" becomes int). Quote strings that look like numbers to keep
            them as strings.
    """
    try:
        return RmdManager(file_path).set_frontmatter_key(key, value)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def remove_frontmatter_key(file_path: str, key: str) -> str:
    """Remove one top-level YAML frontmatter key.

    Args:
        file_path: Absolute path to a .rmd file.
        key: Top-level YAML key to remove.
    """
    try:
        return RmdManager(file_path).remove_frontmatter_key(key)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────


@mcp.tool()
def find_in_rmd(file_path: str, pattern: str) -> str:
    """Case-sensitive substring search across all cell sources.

    Args:
        file_path: Absolute path to a .rmd file.
        pattern: Substring to find; returns `cell[i] line N: <text>` per hit.
    """
    try:
        return RmdManager(file_path).find_in_rmd(pattern)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Kernel execution (outputs returned inline, never persisted)
# ──────────────────────────────────────────────


@mcp.tool()
def execute_cell(file_path: str, index: int, timeout: float = 60.0) -> str:
    """Execute one code chunk via a Jupyter kernel and return the captured outputs INLINE. Outputs are NOT written to the .rmd file.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based index of a CODE cell.
        timeout: Seconds to wait for execution; default 60.
    """
    try:
        return RmdManager(file_path).execute_cell(index, timeout=timeout)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def execute_all_cells(file_path: str, timeout: float = 60.0, stop_on_error: bool = True) -> str:
    """Execute all code chunks in order and return a transcript of captured outputs. Outputs are NOT written to the .rmd file.

    Args:
        file_path: Absolute path to a .rmd file.
        timeout: Per-cell timeout in seconds; default 60.
        stop_on_error: If True, stop at the first cell that errors. Default True.
    """
    try:
        return RmdManager(file_path).execute_all_cells(timeout=timeout, stop_on_error=stop_on_error)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool()
def get_kernel_state(file_path: str) -> str:
    """Return whether the kernel for this .rmd is 'not started', 'alive', or 'dead'.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    return _kernel.kernel_state(file_path)


@mcp.tool()
def restart_kernel(file_path: str) -> str:
    """Restart the kernel; in-memory state is lost.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    try:
        _kernel.restart_kernel(file_path)
        return "Restarted"
    except _kernel.KernelError as e:
        return _err(e)


@mcp.tool()
def interrupt_kernel(file_path: str) -> str:
    """Send an interrupt signal to stop a long-running cell.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    try:
        _kernel.interrupt_kernel(file_path)
        return "Interrupted"
    except _kernel.KernelError as e:
        return _err(e)


@mcp.tool()
def shutdown_kernel(file_path: str) -> str:
    """Shut down the kernel and release its resources.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    _kernel.shutdown_kernel(file_path)
    return "Shutdown"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
