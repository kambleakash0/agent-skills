# RMD Editor MCP Server

When working with `.rmd` R Markdown files, do NOT use the generic `edit` or `write` tool. Use the `rmd-editor` MCP server instead. It exposes 24 chunk- and prose-level tools for creating, editing, and executing R Markdown documents. Use `create_rmd` to create a new `.rmd` (never hand-write YAML frontmatter + chunk syntax).

**Picking a tool — always start here:**

1. **Start by calling `list_cells`** to see the document's structure (code chunks vs. markdown prose, language, chunk labels, line counts, previews). Call `find_in_rmd` for text search. Call `get_cell(index)` to read one cell's full source. Call `get_chunk_options(index)` to see a chunk's language/label/options. Call `get_frontmatter` to see the YAML header.
2. **Creating a new document:** `create_rmd` (do NOT hand-write `.rmd` with a generic `Write` tool — `create_rmd` guarantees a valid YAML frontmatter header).
3. **Editing cells:**
   - New cell at a position: `add_cell(index, source, cell_type)` — `cell_type` is `"code"` (an R chunk by default) or `"markdown"` (prose). Pass `index=-1` to append.
   - Rewrite a cell's body: `replace_cell_source` (chunk language, label, and options are preserved)
   - Add lines to an existing cell: `prepend_to_cell` / `append_to_cell`
   - Reorder: `move_cell`
   - Split a large cell: `split_cell`
   - Merge consecutive same-type cells: `merge_cells`
   - Delete: `delete_cell`
4. **Chunk options (labels and `key=value` settings on code chunks):**
   - Read all options: `get_chunk_options`
   - Set/overwrite one option: `set_chunk_option(index, key, value)` — use `key="label"` to set the chunk label (e.g. `setup`, `analysis`).
   - Remove one option: `remove_chunk_option(index, key)` — use `key="label"` to clear the chunk label.
5. **YAML frontmatter:**
   - Read: `get_frontmatter` (shows R tags such as `!r`; a header that isn't valid YAML comes back as raw text with a note)
   - Set/overwrite one key: `set_frontmatter_key(key, value)` — value is parsed as YAML when possible. Only that key's lines change, so comments, quoting and tags elsewhere in the header are kept. A value that means the same written as given is written that way (`"!r Sys.Date()"` stays an R tag). A new key goes at the end of the header.
   - Remove one key: `remove_frontmatter_key(key)` (removes its indented lines too)
6. **Running chunks (R kernel via IRkernel by default):**
   - One chunk: `execute_cell` — captured outputs are returned **INLINE** to the caller and are NOT written to the `.rmd` file (R Markdown regenerates outputs on render).
   - All chunks: `execute_all_cells`
   - Stop a runaway chunk: `interrupt_kernel`
   - Fresh namespace: `restart_kernel`
   - Check if kernel is alive: `get_kernel_state`
   - Release resources: `shutdown_kernel`

**Anti-patterns to avoid:**

- Don't use `replace_cell_source` to add a couple of lines — use `prepend_to_cell` / `append_to_cell`.
- Don't use `add_cell` to replace an existing cell — use `replace_cell_source`.
- Don't skip `list_cells` and guess indices — they're zero-based and shift when you add/delete cells.
- Don't call chunk-option tools on markdown cells (they raise).
- Don't use `set_chunk_option` for the chunk label naming convention you just invented — use `key="label"` explicitly.
- Don't hand-write `.rmd` with `Write` — use `create_rmd` for new files.

**Format notes:**

- `.rmd` has no cell-boundary markers between adjacent prose blocks (unlike `.ipynb`). Two adjacent `markdown` cells in the model will **auto-merge** on save and re-parse. Prefer inserting prose between code chunks, or append to an existing markdown cell.
- Code chunks default to R (`cell_type="code"` creates an ` ```{r} ` chunk). Polyglot chunks (`{python}`, `{bash}`, `{sql}`) already in the file are preserved on round-trip, but no tool can create a non-R chunk or change a chunk's language yet: `replace_cell_source` keeps the language, and `set_chunk_option(key="language")` only adds a `language=` option to the header.

**Kernel lifecycle notes:**

- Kernel starts lazily on first `execute_cell` / `execute_all_cells`. One kernel per `.rmd` file path, cached for the server's lifetime.
- The kernel runs in the `.rmd` file's folder, so relative paths in chunks resolve against that folder, not the server's directory.
- State accumulates across calls: variables from an earlier `execute_cell` are visible to later ones. Use `restart_kernel` for a clean namespace or `shutdown_kernel` to release resources.
- A chunk still running at `timeout` (seconds, must be positive) is interrupted and its kernel keeps its state; if the error says the kernel is still busy, call `restart_kernel`. Chunks on one file run one at a time (another call's chunk can run between two chunks of `execute_all_cells`); `restart_kernel` and `shutdown_kernel` kill a running chunk instead of waiting for it.
- The kernel is chosen from the language of the first chunk you run (`r` → `ir`, `python` → `python3`, `julia` → the installed IJulia kernelspec: `julia`, `julia-1`, or the newest `julia-X.Y`; others passed through lowercased). Later chunks go to that same kernel whatever their language, so in a mixed-language document call `shutdown_kernel` before running chunks in another language (this discards the kernel's state). The matching Jupyter kernel must be installed on the host: install IRkernel for R via `install.packages("IRkernel"); IRkernel::installspec()`.
- Outputs are **never** written to the `.rmd` file. They're returned inline to the caller only; an error includes the kernel's traceback. Render the document with `rmarkdown::render()` if you want persisted HTML/PDF/Word output.
