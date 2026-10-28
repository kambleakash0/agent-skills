"""
MCP server exposing rmd-editor tools via the MCP SDK's MCPServer (mcp>=2.0.0).
"""
from __future__ import annotations

import logging
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

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

# Condensed RMD-EDITOR.md, sent to clients as MCP server instructions.
_INSTRUCTIONS = (
    "Tools for R Markdown (.rmd): use them, not generic edit or write tools; pass absolute paths. Create "
    "files with create_rmd. "
    "Start with list_cells; indices shift after adds, deletes, splits and merges (adjacent markdown cells "
    "merge on save), so re-run it. "
    "Pick the narrowest edit: prepend_to_cell or append_to_cell to add lines, replace_cell_source to rewrite "
    "a cell, add_cell for a new one. Chunk text has no final newline; one leaves a blank line before the "
    "fence. "
    "set_chunk_option and remove_chunk_option edit chunk options and labels where knitr reads them: the "
    "header or the #| lines at the top. set_frontmatter_key changes only that key's lines. Edits that would "
    "read back other than meant are refused, the file unchanged. "
    "execute_cell and execute_all_cells return outputs inline, not saved. One Jupyter kernel per file, "
    "picked by the first chunk run (r uses ir), runs in the file's folder; state persists: interrupt_kernel "
    "stops a chunk, restart_kernel clears it, shutdown_kernel ends it."
)


def _server_version() -> str:
    try:
        return _pkg_version("rmd-editor-mcp")
    except PackageNotFoundError:
        return "0.0.0"


mcp = MCPServer("rmd-editor", instructions=_INSTRUCTIONS, version=_server_version())


# Tool behavior hints. The .rmd file is the tool's environment; execution tools
# also run arbitrary chunk code in a local kernel.
_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
_ADDITIVE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
_DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
_RUNS_CODE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True)

# Shared parameter types. The Field descriptions end up in each tool's inputSchema.
FilePath = Annotated[str, Field(description="Absolute path to an existing .rmd file.")]
KernelFilePath = Annotated[str, Field(description="Absolute path of the .rmd file, as passed to execute_cell.")]
CellIndex = Annotated[int, Field(description="Zero-based cell index from list_cells; -1 is the last cell.")]
ChunkIndex = Annotated[
    int,
    Field(description="Zero-based index of a code chunk from list_cells; -1 is the last cell; markdown cells are refused."),
]


def _err(e: Exception) -> str:
    return f"Error: {e}"


# ──────────────────────────────────────────────
# Notebook creation
# ──────────────────────────────────────────────


@mcp.tool(annotations=_DESTRUCTIVE)
def create_rmd(
    file_path: Annotated[str, Field(description="Absolute path for the new .rmd file; its folder must exist.")],
    title: Annotated[str, Field(description="Title, as a quoted YAML string; '' (default) omits it.")] = "",
    author: Annotated[str, Field(description="Author, as a quoted YAML string; '' (default) omits it.")] = "",
    output_format: Annotated[
        str,
        Field(description="Output format such as html_document (default), pdf_document or word_document; '' omits it."),
    ] = "html_document",
    overwrite: Annotated[bool, Field(description="Replace an existing file; false (default) refuses it.")] = False,
) -> str:
    """Create a new .rmd file holding only a YAML header with title, author and output keys.

    Example: file_path="/abs/report.rmd", title="Sales report"
    """
    try:
        logger.info("create_rmd: path=%s", file_path)
        return _create_rmd(file_path, title=title, author=author, output_format=output_format, overwrite=overwrite)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Cell structure & navigation
# ──────────────────────────────────────────────


@mcp.tool(annotations=_READ_ONLY)
def list_cells(file_path: FilePath) -> str:
    """List every cell: index, type, a chunk's language, label and option count as knitr reads them, line count and a preview. Chunks are found where knitr finds them.

    Example output line: [2] code (r label=setup opts=1) 3L  library(dplyr)
    """
    try:
        return RmdManager(file_path).list_cells()
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_READ_ONLY)
def get_cell(file_path: FilePath, index: CellIndex) -> str:
    """Return one cell's text: a chunk's lines below its header, option lines included, or prose.

    Don't use this when: you need the document's layout -> use `list_cells`.

    Example: index=0
    """
    try:
        return RmdManager(file_path).get_cell(index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_ADDITIVE)
def add_cell(
    file_path: FilePath,
    index: Annotated[int, Field(description="Zero-based position of the new cell; -1 or the cell count appends.")],
    source: Annotated[
        str,
        Field(description="Text of the new cell, without a final newline for a chunk; empty by default."),
    ] = "",
    cell_type: Annotated[str, Field(description='"code" (default, a new r chunk) or "markdown".')] = "code",
) -> str:
    """Insert a new cell at index: an r chunk or markdown prose.

    Refused, with the line's number in the text: in a chunk, a line knitr reads as a closing fence or chunk header, or an option line (#|) after other lines; in markdown, a line that would open a chunk.

    Don't use this when: you add lines to a cell -> use `append_to_cell` or `prepend_to_cell`.

    Example: index=-1, source="summary(df)"
    """
    try:
        return RmdManager(file_path).add_cell(index, source=source, cell_type=cell_type)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def delete_cell(file_path: FilePath, index: CellIndex) -> str:
    """Delete the cell at index; later cells shift up.

    Example: index=3
    """
    try:
        return RmdManager(file_path).delete_cell(index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_ADDITIVE)
def move_cell(
    file_path: FilePath,
    from_index: Annotated[int, Field(description="Zero-based index of the cell to move; -1 is the last cell.")],
    to_index: Annotated[int, Field(description="Zero-based index it ends up at; -1 is the last position.")],
) -> str:
    """Move a cell to another index; the cells in between shift.

    Example: from_index=4, to_index=0
    """
    try:
        return RmdManager(file_path).move_cell(from_index, to_index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_ADDITIVE)
def split_cell(
    file_path: FilePath,
    index: CellIndex,
    line_offset: Annotated[
        int,
        Field(description="Lines that stay in the cell, from 1 to its line count minus 1; the rest move to a new cell after it."),
    ],
) -> str:
    """Split a chunk in two after line_offset lines; the new half keeps its language but not its label or options. A markdown cell's halves merge back on save, so only chunks split.

    Refused: a split inside the option lines (#|), or one that would start the new chunk with a line that reads as an option line.

    Example: index=2, line_offset=3
    """
    try:
        return RmdManager(file_path).split_cell(index, line_offset)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def merge_cells(
    file_path: FilePath,
    start_index: Annotated[int, Field(description="Zero-based index of the first cell to merge; its header and label are kept.")],
    end_index: Annotated[
        int,
        Field(description="Zero-based index of the last cell to merge, inclusive, after start_index; -1 is the last cell."),
    ],
) -> str:
    """Merge cells start_index to end_index into the first; all must be markdown, or chunks of one language. A blank line between chunks is a markdown cell: delete_cell it first.

    The merged chunk keeps the first chunk's header and label (the others' labels go) and every chunk's options: the other headers' options join the first, and all option lines go in one block at the top, in the first block's comment style. An option set to one value in several chunks is written once. Refused, naming the cells: an option set to different values, option lines that aren't YAML key: value lines, a header knitr fails on, and lines that would read differently in the merged chunk (as option lines, a fence or a chunk header).

    Example: start_index=2, end_index=4
    """
    try:
        return RmdManager(file_path).merge_cells(start_index, end_index)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Cell content editing
# ──────────────────────────────────────────────


@mcp.tool(annotations=_DESTRUCTIVE)
def replace_cell_source(
    file_path: FilePath,
    index: CellIndex,
    new_source: Annotated[
        str,
        Field(description="New text of the cell, as get_cell returns it; for a chunk, a final newline leaves a blank line before the fence."),
    ],
) -> str:
    """Replace a cell's whole text; a chunk keeps its header line, but its #| option lines are part of the text.

    get_cell's text given back leaves the file byte for byte as it was. Refused, with the line's number in the text: in a chunk, a line knitr reads as a closing fence or chunk header, or an option line after other lines; in markdown, a line that would open a chunk.

    Don't use this when: you add lines -> use `prepend_to_cell` or `append_to_cell`; you change one option -> use `set_chunk_option`.

    Example: index=3, new_source="x <- 1\\nplot(x)"
    """
    try:
        return RmdManager(file_path).replace_cell_source(index, new_source)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_ADDITIVE)
def prepend_to_cell(
    file_path: FilePath,
    index: CellIndex,
    source: Annotated[
        str,
        Field(description="Text to add above the cell's text, on lines of its own; in a chunk, below its option lines."),
    ],
) -> str:
    """Add text at the top of a cell; in a chunk with option lines (#|), below them and the blank line after them.

    One line break separates the text from the cell's, added unless the text ends with one. In a chunk with option lines, text starting with an option line is refused (use set_chunk_option); in one without, the text's leading option lines become the chunk's. Refused too: an option line after other lines of the text, or text that changes which lines knitr reads as option lines.

    Example: index=2, source="library(dplyr)"
    """
    try:
        return RmdManager(file_path).prepend_to_cell(index, source)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_ADDITIVE)
def append_to_cell(
    file_path: FilePath,
    index: CellIndex,
    source: Annotated[
        str,
        Field(description="Text to add below the cell's text, on lines of its own; a final newline leaves a blank line before a chunk's fence."),
    ],
) -> str:
    """Add text at the bottom of a cell.

    One line break separates it from the cell's text (in a chunk, added unless the text starts with one), and the cell's own blank lines stay. Refused: an option line (#|) after other lines (use set_chunk_option; option lines may go into an empty chunk or below option lines alone), and text that would change which lines knitr reads as option lines.

    Example: index=2, source="summary(fit)"
    """
    try:
        return RmdManager(file_path).append_to_cell(index, source)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Chunk options
# ──────────────────────────────────────────────


@mcp.tool(annotations=_READ_ONLY)
def get_chunk_options(file_path: FilePath, index: ChunkIndex) -> str:
    """Return a chunk's language, the label knitr uses and every option knitr reads, from its header and its option lines (#| for r).

    Each option is listed once, in the spelling knitr uses: key=value in the header, or the option line as written. Spellings knitr overrides (a header copy by a #| line, fig.width by fig-width) are noted, and so is a header or a repeated #| key knitr fails on.

    Example: index=1
    """
    try:
        return RmdManager(file_path).get_chunk_options(index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def set_chunk_option(
    file_path: FilePath,
    index: ChunkIndex,
    key: Annotated[
        str,
        Field(description='Option name such as echo or fig.width, or "label"; a new dashed knitr option (fig-width) goes in the header dotted, or in a new #| line of a chunk with #| lines.'),
    ],
    value: Annotated[
        str,
        Field(description='Value as R code on one line, e.g. FALSE, 7 or "My caption"; "" clears the label and is refused for other keys.'),
    ],
) -> str:
    """Set or overwrite one chunk option where knitr reads it; key "label" sets the label.

    A #| line holding the key gets the value as YAML (FALSE as false, other R code as !expr), else the header copy knitr uses; the key's other spellings go. A new key goes at the end of the header, but one that isn't a syntactic R name (code-fold) goes in a new #| line, and is refused in a chunk without #| lines. Refused, file unchanged: a line break, an unmatched bracket, quote or backtick, or a comma, # or = outside quotes and brackets (x == 1 is fine).

    Don't use this when: the key belongs in the YAML header -> use `set_frontmatter_key`.

    Example: index=2, key="fig.width", value="7"
    """
    try:
        return RmdManager(file_path).set_chunk_option(index, key, value)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_chunk_option(
    file_path: FilePath,
    index: ChunkIndex,
    key: Annotated[str, Field(description='Option to remove; "label" clears the label.')],
) -> str:
    """Remove one chunk option in every spelling knitr reads: its header copies, its #| line and its dashed or dotted twin (fig-width for fig.width). key "label" clears the label wherever it is written. Refused when the chunk has no such option.

    Don't use this when: the key is in the YAML header -> use `remove_frontmatter_key`.

    Example: index=2, key="echo"
    """
    try:
        return RmdManager(file_path).remove_chunk_option(index, key)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# YAML frontmatter
# ──────────────────────────────────────────────


@mcp.tool(annotations=_READ_ONLY)
def get_frontmatter(file_path: FilePath) -> str:
    """Return the YAML header as YAML text, R tags such as !r and !expr shown as tags.

    A header that isn't valid YAML, or holds a value that can't be built, comes back as its raw text after a note saying why; the other tools still work on the file.
    """
    try:
        return RmdManager(file_path).get_frontmatter()
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def set_frontmatter_key(
    file_path: FilePath,
    key: Annotated[str, Field(description="Top-level key such as title, author, date or output; a new key goes last in the header.")],
    value: Annotated[
        str,
        Field(description='Value read as YAML ("true" is a bool, "42" an int; quote it to keep a string), kept as written when that means the same; may span several lines.'),
    ],
) -> str:
    """Set or overwrite one top-level key of the YAML header; comments, quoting, tags and the other keys' lines are kept.

    A document without a header gets one. A key holding a line break is refused. A value that isn't YAML is written as a quoted string.

    Don't use this when: the option belongs to one chunk -> use `set_chunk_option`.

    Example: key="output", value="pdf_document"
    """
    try:
        return RmdManager(file_path).set_frontmatter_key(key, value)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_frontmatter_key(
    file_path: FilePath,
    key: Annotated[str, Field(description="Top-level key to remove; it must exist.")],
) -> str:
    """Remove one top-level key of the YAML header with its indented lines; the rest of the header keeps its bytes.

    Don't use this when: it is a chunk option -> use `remove_chunk_option`.

    Example: key="author"
    """
    try:
        return RmdManager(file_path).remove_frontmatter_key(key)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────


@mcp.tool(annotations=_READ_ONLY)
def find_in_rmd(
    file_path: FilePath,
    pattern: Annotated[str, Field(description="Case-sensitive literal substring, not a regex.")],
) -> str:
    """Search every cell's text for a substring; returns `cell[i] line N: <text>` per matching line, with lines numbered as list_cells counts them and split_cell takes offsets.

    Example: pattern="read.csv"
    """
    try:
        return RmdManager(file_path).find_in_rmd(pattern)
    except RmdManagerError as e:
        return _err(e)


# ──────────────────────────────────────────────
# Kernel execution (outputs returned inline, never persisted)
# ──────────────────────────────────────────────


@mcp.tool(annotations=_RUNS_CODE)
def execute_cell(
    file_path: FilePath,
    index: ChunkIndex,
    timeout: Annotated[
        float,
        Field(gt=0, description="Seconds the chunk may run, more than 0 (default 60); then it is interrupted, the state kept."),
    ] = 60.0,
) -> str:
    """Run one code chunk in the file's kernel and return its outputs, an error's traceback included; nothing is written to the file.

    The first chunk run picks the kernel (r uses ir); later chunks run in it whatever their language: shutdown_kernel before switching. If a timeout error says the kernel is still busy, use restart_kernel. Calls on one file run one at a time.

    Example: index=2, timeout=120
    """
    try:
        return RmdManager(file_path).execute_cell(index, timeout=timeout)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_RUNS_CODE)
def execute_all_cells(
    file_path: FilePath,
    timeout: Annotated[
        float,
        Field(gt=0, description="Seconds each chunk may run, more than 0 (default 60); then it is interrupted and the run stops."),
    ] = 60.0,
    stop_on_error: Annotated[
        bool,
        Field(description="Stop after the first chunk with an error output (default true); false runs every chunk."),
    ] = True,
) -> str:
    """Run every non-empty code chunk in order and return a transcript of their outputs; nothing is written to the file.

    Don't use this when: you run one chunk -> use `execute_cell`.

    Example: stop_on_error=false
    """
    try:
        return RmdManager(file_path).execute_all_cells(timeout=timeout, stop_on_error=stop_on_error)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_READ_ONLY)
def get_kernel_state(file_path: KernelFilePath) -> str:
    """Return the state of the file's kernel: 'not started', 'alive' or 'dead'."""
    return _kernel.kernel_state(file_path)


@mcp.tool(annotations=_DESTRUCTIVE)
def restart_kernel(file_path: KernelFilePath) -> str:
    """Restart the file's kernel; its in-memory state is lost. A kernel not running gives an error.

    A running chunk is killed and its call fails; calls waiting behind it run on the new kernel.

    Don't use this when: you only stop a running chunk -> use `interrupt_kernel`.
    """
    try:
        _kernel.restart_kernel(file_path)
        return "Restarted"
    except _kernel.KernelError as e:
        return _err(e)


@mcp.tool(annotations=_ADDITIVE)
def interrupt_kernel(file_path: KernelFilePath) -> str:
    """Interrupt the chunk the file's kernel is running, at once, even while an execute call waits on it; the state is kept. A kernel not running gives an error, and the next execute_cell starts a new one."""
    try:
        _kernel.interrupt_kernel(file_path)
        return "Interrupted"
    except _kernel.KernelError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def shutdown_kernel(file_path: KernelFilePath) -> str:
    """Shut down the file's kernel and free its resources. A running chunk is killed, and execute calls waiting behind it fail.

    Don't use this when: you want a clean namespace -> use `restart_kernel`.
    """
    _kernel.shutdown_kernel(file_path)
    return "Shutdown"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
