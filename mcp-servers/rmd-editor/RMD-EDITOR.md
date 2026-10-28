# RMD Editor MCP Server

When working with `.rmd` R Markdown files, do NOT use the generic `edit` or `write` tool. Use the `rmd-editor` MCP server instead. It exposes 24 tools for creating, editing, and running R Markdown documents. Pass absolute file paths. The README (https://github.com/kambleakash0/agent-skills/tree/main/mcp-servers/rmd-editor) has the full reference.

**Picking a tool — always start here:**

1. **Start with `list_cells`** for each cell's index (zero-based, `-1` is the last), type, language, label and preview. Read one cell with `get_cell(index)`, a chunk's options with `get_chunk_options(index)`, the YAML header with `get_frontmatter`; search with `find_in_rmd` (literal, case-sensitive).
2. **New document:** `create_rmd(file_path, title, author, output_format)`.
3. **Editing cells:**
   - New cell: `add_cell(index, source, cell_type)`: `"code"` (an R chunk) or `"markdown"`; `index=-1` appends.
   - Add lines: `prepend_to_cell` / `append_to_cell`. The text goes on lines of its own; `prepend_to_cell` goes below a chunk's option lines.
   - Rewrite a whole cell: `replace_cell_source` (a chunk keeps its header line; its `#|` option lines are part of the text, so keep them in the new text).
   - Restructure: `move_cell`, `split_cell(index, line_offset)` (a chunk's first `line_offset` lines stay; a markdown cell's halves merge back on save), `merge_cells(start_index, end_index)` (consecutive cells of one type and language; keeps the first chunk's header and label and every chunk's options; a blank line between chunks is a markdown cell: `delete_cell` it first), `delete_cell`.
   - Chunk text has no final newline: write `"x <- 1"`, not `"x <- 1\n"`, which leaves a blank line before the closing fence. Passing `get_cell`'s text back changes nothing.
4. **Chunk options and labels**, read and written where knitr reads them: the header (` ```{r setup, echo=FALSE} `) and the `#|` option lines at a chunk's top (`--|` for sql).
   - Read: `get_chunk_options` (each option once, as knitr uses it).
   - Set: `set_chunk_option(index, key, value)`; `key="label"` sets the label. The value is R code on one line: quote text holding a comma, `#` or `=` as an R string (`'"a, b"'`). A new dashed knitr key (`fig-width`) goes in the header as `fig.width`, or in a new `#|` line when the chunk has `#|` lines; other keys that aren't R names (`code-fold`) need `#|` lines.
   - Remove: `remove_chunk_option(index, key)` removes every spelling; `key="label"` clears the label.
5. **YAML frontmatter:** `get_frontmatter`; `set_frontmatter_key(key, value)` parses the value as YAML (`"42"` is an int, `'"42"'` a string, `"!r Sys.Date()"` stays a tag), changes only that key's lines and puts a new key last; `remove_frontmatter_key(key)` removes it with its indented lines.
6. **Running chunks:** `execute_cell(index, timeout)` and `execute_all_cells(timeout, stop_on_error)` return outputs inline, never saved to the file. `interrupt_kernel` stops a chunk, `restart_kernel` gives a fresh namespace, `get_kernel_state` checks the kernel, `shutdown_kernel` frees it.

**Anti-patterns to avoid:**

- Don't use `replace_cell_source` to add a couple of lines; use `prepend_to_cell` / `append_to_cell`.
- Don't use `add_cell` to replace a cell; use `replace_cell_source`.
- Don't guess indices: they shift after adds, deletes, splits and merges, so re-run `list_cells`.
- Don't call chunk-option tools or `execute_cell` on markdown cells.
- Don't invent a key for the label; use `key="label"`.
- Don't put option lines (`#| echo: false`) after other lines of cell text: they are refused. Use `set_chunk_option`.
- Don't hand-write `.rmd` with `Write`; use `create_rmd`.

**Safety nets:**

- Every save is read back first. An edit that would change how the cells or the YAML header read (a fence in chunk text, a chunk opening in prose, a new `---` header, code read as option lines) is refused with the reason, and the file is left unchanged.
- Adjacent markdown cells merge on save: put prose between chunks, or append to an existing markdown cell.
- Line endings (CRLF too) and a UTF-8 byte order mark are kept; pass text with `\n`.
- Chunks are the ones knitr finds; one that nothing closes runs to the end of the file.

**Kernel notes:**

- One kernel per file path, started by the first execute call in the file's folder (relative paths resolve there) and picked by that chunk's language (`r` uses IRkernel). Later chunks run there whatever their language: call `shutdown_kernel` before running a chunk in another language.
- State persists across calls. A chunk past `timeout` seconds is interrupted with the state kept; if the error says the kernel is still busy, call `restart_kernel`.

**Escape hatches:**

- No tool creates a non-R chunk or changes a chunk's language: edit that header line with your normal edit tool.
- To show chunk syntax in prose, write `` `r ''` `` before the backticks.
- To keep outputs, render the document with `rmarkdown::render()`.
