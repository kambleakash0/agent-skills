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
    "Chunk- and prose-level tools for creating, editing and running R Markdown (.rmd) documents. "
    "Use them instead of generic edit or write tools for .rmd files, pass absolute file paths, and "
    "create files with create_rmd. "
    "Start with list_cells for cell indices, types, labels and previews; indices are zero-based and "
    "shift after adds, deletes, splits and merges, so re-run it. "
    "Pick the narrowest edit: prepend_to_cell or append_to_cell to add lines, replace_cell_source "
    "only to rewrite a cell (a chunk keeps its language, label and options), add_cell for a new "
    "cell (index -1 appends). Chunk text has no final newline: one at the end leaves a blank line "
    "before the closing fence. Adjacent markdown cells merge on save. "
    "Edit chunk options with set_chunk_option and remove_chunk_option (key=\"label\" for the label), "
    "which work where knitr reads them: the chunk header or the #| lines at its top. "
    "set_frontmatter_key and remove_frontmatter_key parse values as YAML and change only that "
    "key's lines. Edits that would change how the file reads back are refused. "
    "execute_cell and execute_all_cells start one Jupyter kernel per file, picked by the first "
    "chunk's language (r uses ir), in the file's folder; outputs come back inline, never written "
    "to the file. State persists: interrupt_kernel stops a chunk, restart_kernel resets the "
    "namespace, shutdown_kernel frees the kernel. A chunk past its timeout is interrupted with the "
    "state kept; if the error says the kernel is still busy, use restart_kernel."
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
KernelFilePath = Annotated[
    str,
    Field(description="Absolute path of the .rmd file whose kernel to use; must be the same path string passed to execute_cell."),
]
CellIndex = Annotated[int, Field(description="Zero-based cell index as shown by list_cells; -1 means the last cell.")]
ChunkIndex = Annotated[
    int,
    Field(description="Zero-based index of a code chunk as shown by list_cells; -1 means the last cell; markdown cells are rejected."),
]


def _err(e: Exception) -> str:
    return f"Error: {e}"


# ──────────────────────────────────────────────
# Notebook creation
# ──────────────────────────────────────────────


@mcp.tool(annotations=_DESTRUCTIVE)
def create_rmd(
    file_path: Annotated[str, Field(description="Absolute path for the new .rmd file; its parent directory must already exist.")],
    title: Annotated[
        str,
        Field(description="Document title for the YAML frontmatter, written as a quoted YAML string so any characters are safe; an empty string omits the title key."),
    ] = "",
    author: Annotated[
        str,
        Field(description="Author for the YAML frontmatter, written as a quoted YAML string so any characters are safe; an empty string omits the author key."),
    ] = "",
    output_format: Annotated[
        str,
        Field(description="rmarkdown output format for the output key, e.g. html_document, pdf_document, word_document, or github_document; an empty string omits the output key."),
    ] = "html_document",
    overwrite: Annotated[bool, Field(description="Replace an existing file at file_path; when false, an existing file is an error.")] = False,
) -> str:
    """Create a new empty .rmd file with a minimal YAML frontmatter.

    Args:
        file_path: Absolute path for the new .rmd file.
        title: Optional document title for the YAML frontmatter.
        author: Optional author string for the YAML frontmatter.
        output_format: Pandoc/rmarkdown output format. Defaults to html_document.
            Other common values: pdf_document, word_document, github_document.
        overwrite: If True, overwrite an existing file. Defaults to False.

    Title and author are written as escaped, double-quoted YAML strings, so
    quotes, backslashes, and newlines in them are safe. An empty title, author,
    or output_format leaves that key out. Refuses to overwrite unless
    overwrite=True. Fails if the parent directory does not exist.
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
    """List all cells in the .rmd with index, type (code/markdown), language/label/option-count for code chunks, line count, and a one-line preview.

    Chunks are found where knitr finds them: a header line (```{r}, also
    indented, after >, with more backticks or a space before the {) opens one,
    and only a closing fence with the header's indentation and backticks
    closes it, but for a chunk on the first line of the file, which any
    closing fence closes (once a cell or a YAML header goes before it, it is
    written with its own). A header with the chunk's own fence inside it starts
    a new chunk, and a chunk nothing closes runs to the end of the file.

    A chunk's label and option count are those knitr reads, from its header and
    its #| lines, as get_chunk_options shows them.

    Only a line break (\\n, \\r\\n or a lone \\r) ends a line, as in knitr: a form
    feed or U+2028 stays inside its line. split_cell and find_in_rmd count lines
    the same way.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    try:
        return RmdManager(file_path).list_cells()
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_READ_ONLY)
def get_cell(file_path: FilePath, index: CellIndex) -> str:
    """Return the source text of one cell (chunk body or prose).

    A chunk's text leaves off the line break before its closing fence, so text
    ending in \\n means a blank line there. A chunk of blank lines only comes back
    as those line breaks: "" is an empty chunk, "\\n" one blank line. A chunk
    whose fence is indented or in a blockquote comes back as knitr runs it,
    without that indentation or those > marks, and edits write them back.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index. -1 means the last cell.
    """
    try:
        return RmdManager(file_path).get_cell(index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_ADDITIVE)
def add_cell(
    file_path: FilePath,
    index: Annotated[int, Field(description="Zero-based position the new cell takes; -1 (or the current cell count) appends at the end.")],
    source: Annotated[
        str,
        Field(description="Initial cell body: chunk code for a code cell (without a final newline, which would leave a blank line before the closing fence) or prose for a markdown cell; empty by default."),
    ] = "",
    cell_type: Annotated[str, Field(description='Either "code" (a new R chunk) or "markdown" (prose).')] = "code",
) -> str:
    """Insert a new cell at the given index.

    Chunk code with a line knitr reads as a closing fence (backticks alone,
    after nothing but spaces, tabs or >) or a chunk header (```{r}, or with
    such indentation, more backticks or a space before the {) is refused, since
    knitr would end the chunk there. Markdown text with a line that would open
    a chunk is refused, since the prose after it would become chunk code; each
    error gives its line in the text passed. So is markdown that would put a
    --- line at the top of a document without a header, with another --- line
    further down, which would read back as the YAML header. A chunk before the
    new cell that has no closing fence (knitr ends it at the next chunk's
    header or the end of the file) gets one first.

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


@mcp.tool(annotations=_DESTRUCTIVE)
def delete_cell(file_path: FilePath, index: CellIndex) -> str:
    """Delete the cell at the given index.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index.
    """
    try:
        return RmdManager(file_path).delete_cell(index)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_ADDITIVE)
def move_cell(
    file_path: FilePath,
    from_index: Annotated[int, Field(description="Zero-based index of the cell to move; -1 means the last cell.")],
    to_index: Annotated[int, Field(description="Zero-based index the cell ends up at after the move; -1 means the last position.")],
) -> str:
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


@mcp.tool(annotations=_ADDITIVE)
def split_cell(
    file_path: FilePath,
    index: CellIndex,
    line_offset: Annotated[
        int,
        Field(description="Number of lines that stay in the original cell, from 1 to its line count (as list_cells shows it) minus 1; the rest move to a new cell inserted right after it, which keeps a chunk's language but not its label or options."),
    ],
) -> str:
    """Split a cell into two at the given line offset (1-indexed, exclusive upper).

    knitr reads a chunk's option lines (#| for r, --| for sql) only at its
    top, so a split inside them, which would give some of them to the new
    chunk, is refused, and so is one that would start the new chunk with a
    line that starts as an option line does, which knitr reads as code where
    it is now. In a c, css or sas chunk whose every line ends with the
    comment's closing characters (*/, or ; for sas), knitr reads the first
    line alone as an option line, so a split that would leave the first chunk
    its option lines alone is refused too.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index.
        line_offset: 1-indexed line number where the split happens; the first
            line_offset lines stay in the original cell, the rest move to the
            new cell. Lines are counted as list_cells and find_in_rmd count
            them: only a line break ends one, not a form feed or U+2028.
    """
    try:
        return RmdManager(file_path).split_cell(index, line_offset)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def merge_cells(
    file_path: FilePath,
    start_index: Annotated[int, Field(description="Zero-based index of the first cell to merge; its chunk header is the one kept.")],
    end_index: Annotated[
        int,
        Field(description="Zero-based index of the last cell to merge (inclusive); must be greater than start_index; -1 means the last cell."),
    ],
) -> str:
    """Merge consecutive cells [start_index..end_index] inclusive. All cells must share the same cell_type (and language for code chunks).

    Merged chunks take the first one's header and fence. A line knitr read as
    code in its own chunk but would read as a closing fence or a chunk header
    under that fence (```, or ```{r}, from a chunk opened with ````) is
    refused, with its cell and line.

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


@mcp.tool(annotations=_DESTRUCTIVE)
def replace_cell_source(
    file_path: FilePath,
    index: CellIndex,
    new_source: Annotated[
        str,
        Field(description="Replacement body text for the cell; a code chunk keeps its language, label, and options. For a chunk, leave off the final newline: text ending in a newline leaves a blank line before the closing fence."),
    ],
) -> str:
    """Replace a cell's entire source text. Preserves chunk language, label, and options for code cells.

    The text is read as get_cell returns it: for a chunk, text ending in \\n
    leaves a blank line before the closing fence, so write "x <- 1", not
    "x <- 1\\n". Passing the text get_cell returned leaves the file byte for byte
    as it was. In a chunk's text, a line knitr reads as a closing fence
    (backticks alone on a line, after nothing but spaces, tabs or >) or as a
    chunk header (such backticks, then {engine} or {engine options}) would end
    the chunk there, so it is refused; the error gives its line in the text
    passed. So is an option line (#| for r, --| for sql) after other lines,
    as when a line is put above the chunk's option lines: knitr reads them
    only at the top of a chunk, so it would be code there; one the chunk
    already had there is fine. That holds for one right below them that
    knitr reads as code too: in a c, css or sas chunk whose every line ends
    with */ (or ; for sas), it reads the first line alone as an option line.
    In a markdown cell's text, a line that would
    open a chunk is refused the same way (prepend_to_cell and append_to_cell
    check the text they add).

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index.
        new_source: Replacement source text for the cell body.
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
        Field(description="Text to insert at the top of the cell body; in a chunk that starts with #| option lines, at the top of its code, below them. One line break separates it from the cell's text, added unless the text ends with one; the cell's own blank lines stay."),
    ],
) -> str:
    """Prepend text to an existing cell's source.

    The text goes on lines of its own above the cell's text: one line break
    separates them, added unless the text ends with one, and a blank line the
    cell starts with stays. On prose "\\nMore\\n", "Top" gives "Top\\n\\nMore\\n".

    knitr reads a chunk's option lines (#| for r, --| for sql, /*| ... */ for
    c) only at its top, so in a chunk that starts with them the text goes
    below them, and below the blank line after them: "library(x)" on
    "#| echo: false\\nx" gives "#| echo: false\\nlibrary(x)\\nx". Text that
    starts with an option line is refused there (set options with
    set_chunk_option), and so is an option line after other lines of the
    text, which knitr would read as code; in a chunk without option lines,
    the text's own option lines at its top become the chunk's.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based cell index.
        source: Text to prepend to the cell body.
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
        Field(description="Text to add at the bottom of the cell body, after one line break: in prose, the one that ends the cell's last line; else one added unless the text starts with one. The cell's own blank lines stay, a chunk's blank line before its fence too."),
    ],
) -> str:
    """Append text to an existing cell's source.

    The text goes on lines of its own below the cell's text, after one line
    break: in prose, the one that ends its last line; in a chunk, one added
    unless the text starts with one. A blank line the cell ends with stays: on
    a chunk whose text is "x\\n" (a blank line before the fence), "y" gives
    "x\\n\\ny", and text ending in \\n leaves a blank line before the fence.

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


@mcp.tool(annotations=_READ_ONLY)
def get_chunk_options(file_path: FilePath, index: ChunkIndex) -> str:
    """Return the chunk's language, label, and every option knitr reads, from its header and its #| lines.

    The label is the one knitr uses: a #| label: (else #| id:) line at the top
    of the chunk, else a label= option, else the one name in the header written
    without a value, wherever it is (```{r echo=FALSE, foo} is labelled foo).
    The names written before the first key=value are one label to knitr,
    commas and all, which is noted, unless the first is one character, which
    knitr quotes alone. A part of the header is key=value at its first =
    outside quotes and brackets, as R reads it, so "a=b" and list(a=1) are
    names without a value; knitr quotes none with an = in it, so such a name
    ends the ones before it and is R code (```{r "a=b"} is labelled a=b). A
    header with any other name without a value, which knitr fails on, shows
    label: (none: ...) saying so, and so does one whose first = has a comma
    before it in the same name (```{r cd(x, y=1)}), which knitr's quote_label
    cuts in two. A name after other options is R code, which knitr writes
    without its spaces. A label not written as a bare name is shown with where
    it is written, and label= is not listed among the options. A line break in a label shows as \\n.

    Each option knitr reads is listed once, as the spelling it uses: key=value
    in the header (a key in backticks or quotes, `my key`=1, under the name it
    stands for), or the option line as written (#| for r and python, --| for
    sql, //| for Rcpp and js, /*| ... */ for c, as knitr reads each engine's
    comment). knitr reads a #| line over the header, a dashed name such as
    fig-width over the dotted fig.width, and the last copy of a key the header
    repeats; the spellings it reads one over are noted, and so is a key the #|
    lines repeat, which R's yaml package rejects, so knitr fails on the chunk.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based index of a CODE cell (chunk). Markdown cells raise.
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
        Field(description='Chunk option name such as echo, warning, or fig.width; the special key "label" sets the chunk label. A dashed name such as fig-width (as Quarto writes them) goes in the header as fig.width; a key that is not a syntactic R name (code-fold, my key) goes only in the #| lines of a chunk that has them.'),
    ],
    value: Annotated[
        str,
        Field(description='Option value as R code, e.g. FALSE, 7, or a quoted string, without its surrounding whitespace: written into the chunk header, or as YAML into the #| line that holds the key. It must fit on one line, close every bracket, quote and backtick it opens, and read back as this one option, so quote text holding a comma, "#" or "=" as an R string (x == 1 is fine). For key "label" an empty value clears the label; any other key needs a value.'),
    ],
) -> str:
    """Set or overwrite one chunk option. Special key "label" sets the chunk label.

    The option is set where knitr reads it from: the #| line that holds the key,
    written as YAML (TRUE, FALSE and NULL as true, false and null, a number as
    written, an R string as a YAML string, other R code tagged !expr), else the
    copy in the chunk header knitr uses, the last if the key is repeated there.
    The other spellings of the key (other copies, a header copy a #| line
    overrides, fig.width beside a #| fig-width line) are removed, so one is
    left. A key not written yet goes at the end of the header. Only those lines
    are rewritten: the body's other lines and the closing fence keep their bytes.

    knitr reads the header as R code (the arguments of alist()), where a key
    must be a syntactic R name: letters, digits, dots and underscores, starting
    with a letter or a dot not followed by a digit, and not a reserved word. A
    dashed name of one of knitr's options, as Quarto writes them (fig-width,
    out-width), goes in the header as the dotted name knitr reads it as
    (fig.width), or as written in a new #| line after the others when the
    chunk has YAML #| lines (or in the header after all, when those lines
    can't take a new one); a header copy written dashed is rewritten dotted.
    Another key that isn't a syntactic name (code-fold, my key) goes in a new
    #| line too, and is refused in a chunk without #| lines. A header key in
    backticks or quotes (`my key`=1), which R reads too, is found by the name
    it stands for, and a header copy R can't read (code-fold=TRUE) counts as
    none.

    knitr reads keys and values as R code, and the header must read back with
    exactly the new label and options, so the edit is refused, leaving the file
    unchanged, for a line break, an unmatched bracket or quote, a comma outside
    a quoted string, an "=" in a key, or, in a key or value, a
    backtick left open or a # or "=" outside quotes and brackets (x == 1 is
    fine). So is an empty value for any key but "label".

    The label is set where knitr reads it from: a #| label: (or #| id:) line at
    the top of the chunk, whose lines alone are rewritten, else a label= option
    (kept as an R string, any text allowed but a line break), else the bare name
    or names in the header, in their place (after other options as an R name or
    a quoted string); a chunk without a label gets it first in the header, as
    a quoted R string if it holds an = (```{r "x == 1"}), as knitr quotes no
    bare name with an = in it.
    Spellings knitr reads it over are removed, so one is left. A header with
    more than one name without a value, which knitr fails on, is refused: give
    those names values, or remove them, first. When the first #| key goes, the
    comment and blank #| lines under it move to after the next key. An edit to
    the #| lines that would change how the others read (an alias losing its
    anchor) or make code below them option lines is refused, and so is one to
    c, css or sas option lines written as one comment over several lines.

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


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_chunk_option(
    file_path: FilePath,
    index: ChunkIndex,
    key: Annotated[str, Field(description='Name of the option to remove; the special key "label" clears the chunk label.')],
) -> str:
    """Remove one chunk option. Use key="label" to clear the chunk label.

    Every spelling of the option goes: each copy in the header, its #| line,
    and a dashed or dotted name knitr reads as the same option (fig-width for
    fig.width). Clearing the label removes it wherever it is written (the bare
    name or names in the header, a label= option, #| label: and #| id: lines at
    the top of the chunk), so no other spelling becomes the label. knitr reads
    the #| lines as YAML only when the first holds a key, so when the first key
    goes, the comment and blank #| lines under it move to after the next key,
    or go too when no key is left.

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


@mcp.tool(annotations=_READ_ONLY)
def get_frontmatter(file_path: FilePath) -> str:
    """Return the YAML frontmatter as a formatted YAML string.

    R Markdown tags such as !r and !expr are shown as tags. A header that is not
    valid YAML is returned as its raw text, after a note saying why it could not
    be parsed and, when known, at which line and column of the file. So is one
    holding a value that can't be built, such as !!bool maybe ("can't read
    'maybe' as !!bool"), an impossible date, an escape past U+10FFFF, or values
    nested more than 100 levels deep (counting the values aliases stand for);
    the other tools still work on such a file.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    try:
        return RmdManager(file_path).get_frontmatter()
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def set_frontmatter_key(
    file_path: FilePath,
    key: Annotated[
        str,
        Field(description="Top-level YAML frontmatter key such as title, author, date, or output; a new key is added at the end of the header."),
    ],
    value: Annotated[
        str,
        Field(description='Value parsed as YAML when possible ("true" becomes a bool, "42" an int); quote it to keep it a string. A one-line value is written as given when that means the same, keeping its quotes and tags such as !r; nested values may span several lines.'),
    ],
) -> str:
    """Set or overwrite one top-level YAML frontmatter key. Value is parsed as YAML when possible.

    Only that key's lines change (the key line and its indented lines): comments,
    quoting, tags such as !r, and key order elsewhere in the header are kept. A
    new key goes just before the closing ---; a document without a header gets
    one. The whitespace around the key is dropped, but not a line break: a new
    key holding one ("short\\n", or NEL or U+2028) is refused, as is one with a
    lone UTF-16 surrogate, which R's yaml package can't read, and one longer
    than 1024 characters as written (quotes included), as YAML reads no longer
    key on a key: value line. A header that is not valid YAML is still edited
    line by line. A value that can't be built (such as !!bool maybe, or nested
    too deep to sit under a key) is written as a quoted string, like other text
    that isn't YAML.

    Args:
        file_path: Absolute path to a .rmd file.
        key: Top-level YAML key (e.g. title, author, output).
        value: Value as a string; parsed as YAML where possible (so "true" becomes
            bool, "42" becomes int). Quote strings that look like numbers to keep
            them as strings. When the value means the same written as given, it
            is written that way, so "!r Sys.Date()" stays an R tag.
    """
    try:
        return RmdManager(file_path).set_frontmatter_key(key, value)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def remove_frontmatter_key(
    file_path: FilePath,
    key: Annotated[str, Field(description="Top-level YAML frontmatter key to remove; it must exist.")],
) -> str:
    """Remove one top-level YAML frontmatter key.

    Removes the key line and its indented lines; the rest of the header is kept
    byte for byte.

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


@mcp.tool(annotations=_READ_ONLY)
def find_in_rmd(
    file_path: FilePath,
    pattern: Annotated[str, Field(description="Case-sensitive literal substring (not a regex) to look for in every cell's source.")],
) -> str:
    """Case-sensitive substring search across all cell sources.

    Args:
        file_path: Absolute path to a .rmd file.
        pattern: Substring to find; returns `cell[i] line N: <text>` per hit,
            with lines numbered as list_cells counts them and split_cell takes
            offsets.
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
        Field(gt=0, description="Seconds the chunk may run (must be positive); a chunk still running then is interrupted and a timeout error is returned, with the kernel's state kept."),
    ] = 60.0,
) -> str:
    """Execute one code chunk via a Jupyter kernel and return the captured outputs INLINE. Outputs are NOT written to the .rmd file.

    A chunk that runs past `timeout` is interrupted (as interrupt_kernel does) so
    the kernel is free for the next call. Concurrent executions on one file run
    one at a time. An error output includes the kernel's traceback.

    Args:
        file_path: Absolute path to a .rmd file.
        index: Zero-based index of a CODE cell.
        timeout: Seconds the chunk may run before it is interrupted; default 60.
    """
    try:
        return RmdManager(file_path).execute_cell(index, timeout=timeout)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_RUNS_CODE)
def execute_all_cells(
    file_path: FilePath,
    timeout: Annotated[float, Field(gt=0, description="Seconds each chunk may run (must be positive); a chunk still running then is interrupted and the run stops with an error.")] = 60.0,
    stop_on_error: Annotated[
        bool,
        Field(description="Stop after the first chunk that produces an error output; when false, every chunk runs."),
    ] = True,
) -> str:
    """Execute all code chunks in order and return a transcript of captured outputs. Outputs are NOT written to the .rmd file.

    Args:
        file_path: Absolute path to a .rmd file.
        timeout: Per-cell timeout in seconds, after which the cell is interrupted; default 60.
        stop_on_error: If True, stop at the first cell that errors. Default True.
    """
    try:
        return RmdManager(file_path).execute_all_cells(timeout=timeout, stop_on_error=stop_on_error)
    except RmdManagerError as e:
        return _err(e)


@mcp.tool(annotations=_READ_ONLY)
def get_kernel_state(file_path: KernelFilePath) -> str:
    """Return whether the kernel for this .rmd is 'not started', 'alive', or 'dead'.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    return _kernel.kernel_state(file_path)


@mcp.tool(annotations=_DESTRUCTIVE)
def restart_kernel(file_path: KernelFilePath) -> str:
    """Restart the kernel; in-memory state is lost.

    A chunk that is running is not waited for: the kernel is killed, and that
    execute call fails with "Kernel died during execution". Execute calls waiting
    behind it run afterwards, on the restarted kernel.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    try:
        _kernel.restart_kernel(file_path)
        return "Restarted"
    except _kernel.KernelError as e:
        return _err(e)


@mcp.tool(annotations=_ADDITIVE)
def interrupt_kernel(file_path: KernelFilePath) -> str:
    """Send an interrupt signal to stop a long-running cell.

    Acts at once, even while an execute call is waiting on that cell. If the
    kernel process has died (get_kernel_state reports 'dead'), returns an error
    saying the kernel is not running; the next execute_cell starts a new one.

    Args:
        file_path: Absolute path to a .rmd file.
    """
    try:
        _kernel.interrupt_kernel(file_path)
        return "Interrupted"
    except _kernel.KernelError as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def shutdown_kernel(file_path: KernelFilePath) -> str:
    """Shut down the kernel and release its resources.

    A chunk that is running is not waited for: the kernel is killed, and that
    execute call fails with "Kernel died during execution"; execute calls waiting
    behind it fail with "Kernel was shut down".

    Args:
        file_path: Absolute path to a .rmd file.
    """
    _kernel.shutdown_kernel(file_path)
    return "Shutdown"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
