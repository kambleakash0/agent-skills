# RMD Editor MCP Server

When working with `.rmd` R Markdown files, do NOT use the generic `edit` or `write` tool. Use the `rmd-editor` MCP server instead. It exposes 24 chunk- and prose-level tools for creating, editing, and executing R Markdown documents. Use `create_rmd` to create a new `.rmd` (never hand-write YAML frontmatter + chunk syntax).

**Picking a tool — always start here:**

1. **Start by calling `list_cells`** to see the document's structure (code chunks vs. markdown prose, language, chunk labels, line counts, previews). Call `find_in_rmd` for text search. Call `get_cell(index)` to read one cell's full source. Call `get_chunk_options(index)` to see a chunk's language/label/options. Call `get_frontmatter` to see the YAML header.
2. **Creating a new document:** `create_rmd` (do NOT hand-write `.rmd` with a generic `Write` tool — `create_rmd` guarantees a valid YAML frontmatter header).
3. **Editing cells:**
   - New cell at a position: `add_cell(index, source, cell_type)` — `cell_type` is `"code"` (an R chunk by default) or `"markdown"` (prose). Pass `index=-1` to append.
   - Rewrite a cell's body: `replace_cell_source` (chunk language, label, and options are preserved)
   - Add lines to an existing cell: `prepend_to_cell` / `append_to_cell` (the text goes on lines of its own, one line break from the cell's text, which it may supply itself; the cell's blank lines stay)
   - Reorder: `move_cell`
   - Split a large cell: `split_cell`
   - Merge consecutive same-type cells: `merge_cells`
   - Delete: `delete_cell`
4. **Chunk options (labels and `key=value` settings on code chunks):**
   - Read all options: `get_chunk_options`
   - Set/overwrite one option: `set_chunk_option(index, key, value)` — use `key="label"` to set the chunk label (e.g. `setup`, `analysis`).
   - Remove one option: `remove_chunk_option(index, key)` — use `key="label"` to clear the chunk label.
   - A label can be written as a name without a value in the header (first, or after other options: ` ```{r echo=FALSE, setup} `), as `label="setup"`, or as a `#| label: setup` (or `#| id: setup`) line at the top of the chunk. The tools show and edit the one knitr uses (`#| label:` over `label=` over the bare name): it is rewritten where it is written (`label=` stays an R string; a `#| ` label changes only its own lines), the spellings it overrides are dropped, and removing a label removes every spelling. knitr reads the bare names before the first `key=value` as one label (` ```{r ab, cd} ` is `ab, cd`, but a first name of one character stands alone, so ` ```{r a, b} ` has two names) and fails on a header with any other name without a value; `get_chunk_options` says so, and label edits are refused until those names get values or go.
   - Options are read as knitr merges them, from the header and the `#|` lines at the top of the chunk (`--| ` for sql, `//| ` for Rcpp and js, `/*| ... */` for c: each engine's comment characters): a `#|` line over the header, `#| fig-width:` over `fig.width=`, and the last copy of a key the header repeats. `get_chunk_options` lists each option once, as the spelling knitr uses, with the ones it reads it over, and flags a key the `#|` lines repeat (knitr fails on it). `set_chunk_option` writes where knitr reads (the `#|` line if one holds the key, as YAML: `true`, `7`, a string, or `!expr` for other R code; else the header copy knitr uses) and removes the other spellings; a new key goes in the header. `remove_chunk_option` removes every spelling. Comment lines left at the top of the `#|` lines move after the next key, so they still read as YAML; an edit that would change how the other option lines read, or turn code below them into option lines, is refused, and so is one to a c, css or sas comment written over several lines.
   - Values are R code and must read back as written, or the edit is refused and the file left unchanged: no line breaks (inside an R string write `\n`), every bracket, quote and backtick closed, a comma or second `=` only inside brackets or a quoted string, and a `#` only inside a quoted string (pass `'"a, b"'`, not `'a, b'`; `c(6, 4)`, `x == 1` and `list(a = 1)` are fine). Every key but `label` needs a non-empty value. Only the header line, or the option's `#|` lines, change.
5. **YAML frontmatter:**
   - Read: `get_frontmatter` (shows tags such as `!r` or `!!merge` as tags, on values left unquoted where YAML allows it; a header that isn't valid YAML, or holds a value that can't be built, such as `!!bool maybe` or values nested more than 100 levels deep, comes back as raw text with a note saying what is wrong and, when known, at which line and column of the file; every other tool still works)
   - Set/overwrite one key: `set_frontmatter_key(key, value)` — value is parsed as YAML when possible. Only that key's lines change, so comments, quoting and tags elsewhere in the header are kept. A value that means the same written as given is written that way (`"!r Sys.Date()"` stays an R tag). A new key goes at the end of the header; one longer than 1024 characters as written is refused, as YAML reads no longer key on a `key: value` line.
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
- Chunks are the ones knitr finds: a header line may be indented, after `>`, or have more backticks (`  ```{r} `, `> ```{r} `, ` ````{r} `), and only a closing fence with the same indentation and backticks closes the chunk (on the first line of a file without a header, any closing fence does; once something goes before such a chunk, it gets its own closing fence). A header with the chunk's own fence inside it starts a new chunk, and a chunk nothing closes runs to the end of the file; a cell added after such a chunk gets its closing fence first. An indented or blockquoted chunk's text comes without that indentation, as knitr runs it. This changed how files with such fences, or with a chunk left open, split into cells: they used to read as prose or as one longer chunk.
- Prose can't hold a line that opens a chunk (` ```{r} `, `  ```{r} `, `> ```{r} `, ` ````{r} `): new markdown text with one is refused, with its line number. Add chunks with `add_cell(cell_type="code")`; to show chunk syntax as text, write `` `r ''` `` before the backticks. Plain fences (` ```r `, ` ```` `) and inline `` `r x` `` are fine.
- Every save is read back first: if the cells or the YAML header would read back differently (for example a `---` line landing on line 1 of a document without a header, with another `---` further down, which would become the header), the tool returns an error and leaves the file unchanged.
- CRLF and mixed-ending files work like LF ones. Cell text comes back with `\n` line breaks, and you pass text with `\n`: on save, an edited cell (rewritten whole, or only its header line for an option edit) and an edited header key's lines get the file's own line ending; everything else keeps its bytes. A UTF-8 byte order mark at the start of the file is kept on save and never shows up in cell text.
- Only `\n`, `\r\n` or a lone `\r` ends a line (a form feed or U+2028 doesn't), and every tool counts lines this way: `list_cells` line counts, `split_cell` offsets and `find_in_rmd` line numbers agree.
- A chunk's text, as `get_cell` returns it and `replace_cell_source`, `add_cell`, `prepend_to_cell` and `append_to_cell` take it, leaves off the line break before the closing fence: write `"x <- 1"`, not `"x <- 1\n"`, which leaves a blank line before the fence. A chunk of blank lines only comes back as its line breaks (`""` is an empty chunk, `"\n"` one blank line). Passing a cell's own text back changes nothing in the file, and `split_cell`, `merge_cells` and option edits keep every line. New chunk text with a line knitr reads as a closing fence (backticks alone, after nothing but spaces, tabs or `>`) or a chunk header (such backticks, then `{engine}`) is refused, since it would end the chunk; the error gives the line number in the text you passed. `merge_cells` refuses a merge that would turn a line into one of these under the first chunk's fence.
- A file without a final newline keeps it that way until the last cell's text changes or a cell goes after it (an option edit or re-saving the same text doesn't count); then the file ends with a newline.
- Code chunks default to R (`cell_type="code"` creates an ` ```{r} ` chunk). Polyglot chunks (`{python}`, `{bash}`, `{sql}`) already in the file are preserved on round-trip, but no tool can create a non-R chunk or change a chunk's language yet: `replace_cell_source` keeps the language, and `set_chunk_option(key="language")` only adds a `language=` option to the header.

**Kernel lifecycle notes:**

- Kernel starts lazily on first `execute_cell` / `execute_all_cells`. One kernel per `.rmd` file path, cached for the server's lifetime.
- The kernel runs in the `.rmd` file's folder, so relative paths in chunks resolve against that folder, not the server's directory.
- State accumulates across calls: variables from an earlier `execute_cell` are visible to later ones. Use `restart_kernel` for a clean namespace or `shutdown_kernel` to release resources.
- A chunk still running at `timeout` (seconds, must be positive) is interrupted and its kernel keeps its state; if the error says the kernel is still busy, call `restart_kernel`. Chunks on one file run one at a time (another call's chunk can run between two chunks of `execute_all_cells`); `restart_kernel` and `shutdown_kernel` kill a running chunk instead of waiting for it.
- The kernel is chosen from the language of the first chunk you run (`r` → `ir`, `python` → `python3`, `julia` → the installed IJulia kernelspec: `julia`, `julia-1`, or the newest `julia-X.Y`; others passed through lowercased). Later chunks go to that same kernel whatever their language, so in a mixed-language document call `shutdown_kernel` before running chunks in another language (this discards the kernel's state). The matching Jupyter kernel must be installed on the host: install IRkernel for R via `install.packages("IRkernel"); IRkernel::installspec()`.
- Outputs are **never** written to the `.rmd` file. They're returned inline to the caller only; an error includes the kernel's traceback. Render the document with `rmarkdown::render()` if you want persisted HTML/PDF/Word output.
