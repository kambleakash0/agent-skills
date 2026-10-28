# RMD Editor MCP Server

A Model Context Protocol (MCP) server for editing R Markdown (`.rmd`) documents with **chunk- and prose-level primitives** and **R kernel execution**. Provides 24 native tools for working with R Markdown the way data scientists actually use it: code chunks as first-class citizens, YAML frontmatter as structured data, and a real R kernel for running chunks and capturing results.

## Why a chunk-native server?

R Markdown files are `.rmd` text documents with YAML frontmatter, interleaved markdown prose, and executable ` ```{r} ` code chunks — not a flat source file and not a JSON notebook. A chunk-specific server can model this correctly:

- **Chunks are the unit of analysis.** Add, delete, reorder, split, merge — all operations that a line-based editor would corrupt.
- **Chunk options are structured.** Labels (`setup`, `analysis`), `echo=FALSE`, `fig.width=7`, `message=FALSE` — these live in the chunk header or in `#|` lines at the top of the chunk, and need first-class read/write tools that read them as knitr does.
- **YAML frontmatter is structured too.** `title`, `author`, `output`, `date` belong in the YAML header, not scattered in prose. Dedicated tools keep edits clean.
- **Kernel execution is part of the workflow.** Running a chunk and inspecting output is how analysts iterate. Outputs are returned **inline** to the caller and are **never** written to the `.rmd` file — R Markdown regenerates outputs on render (`rmarkdown::render()`), so persisting them would drift from the canonical format.

This server complements `notebook-editor` (for `.ipynb` Jupyter notebooks): different file format, same mental model. If you already use `notebook-editor`, the API here is deliberately parallel.

## Tools Exposed

All tools require `file_path` to be an **absolute path**. Every tool except `create_rmd` additionally requires the `.rmd` file to already exist. A cell `index` is zero-based, as `list_cells` shows it, and `-1` means the last cell; indices shift after adds, deletes, splits and merges, so run `list_cells` again rather than guessing. The chunk tools (`get_chunk_options`, `set_chunk_option`, `remove_chunk_option`, `execute_cell`) reject a markdown cell's index.

### Document creation

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `create_rmd` | `file_path`, `title` (default `""`), `author` (default `""`), `output_format` (default `"html_document"`), `overwrite` (default `False`) | Create a new empty `.rmd` with a minimal YAML frontmatter; the parent directory must already exist. `output_format` is the rmarkdown format for the `output` key (`html_document`, `pdf_document`, `word_document`, `github_document`, ...). Title and author are written as escaped, double-quoted YAML strings, so quotes, backslashes and newlines are safe; an empty `title`, `author` or `output_format` leaves that key out. Refuses to overwrite unless `overwrite=True`. |

### Cell structure & navigation

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `list_cells` | `file_path` | Outline of all cells with index, type (code/markdown), language/label/option-count for chunks, line count, and a one-line preview. Chunks are the ones knitr finds (see [Format notes](#format-notes)). The label and the option count are knitr's, from the chunk header and its `#|` lines; see [Chunk labels](#chunk-labels) and [Chunk options](#chunk-options-as-knitr-reads-them). |
| `get_cell` | `file_path`, `index` | Return the source text of a specific cell. A chunk's text leaves off the line break before its closing fence, and an indented or blockquoted chunk's leaves off the indentation or `>` marks; see [Chunk text](#chunk-text). |
| `add_cell` | `file_path`, `index`, `source` (default `""`), `cell_type` (`"code"` or `"markdown"`, default `"code"`) | Insert a new cell at the given index. Pass `index=-1` (or the current cell count) to append. A code cell is an R chunk (` ```{r} `). Chunk text with a line knitr reads as a closing fence or a chunk header, or with an option line after other lines, is refused, with the line's number in the text (see [Chunk text](#chunk-text)), and so is markdown text with a line that would open a chunk (see [Prose](#prose)). |
| `delete_cell` | `file_path`, `index` | Remove a cell by index. |
| `move_cell` | `file_path`, `from_index`, `to_index` | Reorder: move a cell from one position to another. `to_index` is the index the cell has after the move; `-1` is the last position. |
| `split_cell` | `file_path`, `index`, `line_offset` | Split one cell into two at a line boundary: the first `line_offset` lines (1 to the cell's line count, as `list_cells` counts it, minus 1) stay, and the rest go to a new cell right after it, which keeps a chunk's language but not its label or options. Every line, blank lines included, ends up in one of the two. A markdown cell's halves merge back on save, so only chunks split. A split inside a chunk's `#|` option lines, or one that would start the new chunk with an option line, is refused; see [Chunk text](#chunk-text). |
| `merge_cells` | `file_path`, `start_index`, `end_index` | Merge consecutive cells of the same type into one; `end_index` (inclusive) must be greater than `start_index`. Code chunks must share a language. A blank line between chunks is a markdown cell: `delete_cell` it first. The merged chunk has the first chunk's header, fence and label, every chunk's options (the option lines in one block at the top), then each chunk's code in order; an empty chunk adds no line. Options set to different values, and a line that would read as a closing fence or chunk header under that fence, are refused; see [Chunk options](#chunk-options-as-knitr-reads-them) and [Chunk text](#chunk-text). |

### Cell content editing

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `replace_cell_source` | `file_path`, `index`, `new_source` | Replace a cell's entire body. A chunk keeps its header line (language, and the label and options written there); its `#|` option lines are part of the text and go unless the new text keeps them. For a chunk, text ending in `\n` leaves a blank line before the closing fence, and a line knitr would read as a closing fence or a chunk header is refused, as is an option line (`#| ...`) after other lines; see [Chunk text](#chunk-text). The text `get_cell` returned leaves the file byte for byte as it was. |
| `prepend_to_cell` | `file_path`, `index`, `source` | Add lines to the top of a cell, one line break above the cell's text (unless the new text ends with one); in a chunk that starts with `#|` option lines, below them. The cell's own blank lines stay; see [Chunk text](#chunk-text). |
| `append_to_cell` | `file_path`, `index`, `source` | Add lines to the bottom of a cell, one line break below the cell's text (in a chunk, unless the new text starts with one). The cell's own blank lines stay. In a chunk, an option line after other lines is refused (option lines can go only into an empty chunk or one holding option lines alone), and so is text that would change which lines knitr reads as option lines; see [Chunk text](#chunk-text). |

### Chunk options (labels and `key=value` pairs on code chunks)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `get_chunk_options` | `file_path`, `index` | Return the chunk's language, label, and every option knitr reads, from the header and the `#|` lines, each once as the spelling knitr uses, with the spellings it reads that one over. A label written as `label=` or as a `#| label:` line is shown as the label, with where it is written. Raises on markdown cells. See [Chunk options](#chunk-options-as-knitr-reads-them). |
| `set_chunk_option` | `file_path`, `index`, `key`, `value` | Set or overwrite one option. Use `key="label"` to set the chunk label (e.g. `setup`), where it is written; see [Chunk labels](#chunk-labels). The option is written where knitr reads it: the `#|` line that holds the key (as YAML), else the header, whose line alone is rewritten; other spellings of the key go. A new dashed knitr key (`fig-width`) goes in the header as `fig.width`, or in a new `#|` line when the chunk has `#|` lines; other keys that aren't R names (`code-fold`) need `#|` lines and are refused in a chunk without them. A key, value or label the header can't hold as written is refused; see [Chunk headers](#chunk-headers). |
| `remove_chunk_option` | `file_path`, `index`, `key` | Remove one option, wherever it is written: every copy in the header and its `#|` line. Use `key="label"` to clear the chunk label, wherever it is written. |

### YAML frontmatter

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `get_frontmatter` | `file_path` | Return the YAML frontmatter as a formatted YAML string. Tags such as R Markdown's `!r` and `!expr`, and YAML's own `!!` tags without a meaning PyYAML builds (`!!merge x`), are shown as tags, on values left unquoted where YAML allows it. A header that isn't valid YAML comes back as its raw text, after a note saying why it couldn't be parsed and, when known, where (line and column of the file). |
| `set_frontmatter_key` | `file_path`, `key`, `value` | Set or overwrite one top-level YAML key. Value is parsed as YAML where possible (so `"true"` → bool, `"42"` → int). Only that key's lines change; see [Frontmatter edits](#frontmatter-edits). A new key goes at the end of the header, and a document without a header gets one. A new key holding a line break, or longer than 1024 characters as written, is refused, and so is a value that YAML reads with a lone surrogate. |
| `remove_frontmatter_key` | `file_path`, `key` | Remove one top-level YAML key along with its indented lines. The rest of the header is left as it is. A key the header doesn't have is an error. |

### Discovery (read-only)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `find_in_rmd` | `file_path`, `pattern` | Case-sensitive literal substring search (not a regex) across all cell sources. Returns `cell[i] line N: <text>` per hit. |

### Kernel execution

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `execute_cell` | `file_path`, `index`, `timeout` (default `60.0`) | Execute one code chunk via a Jupyter kernel. Captured outputs are returned **inline** — never written to the `.rmd` file. An error output includes the kernel's traceback. A chunk still running at `timeout` is interrupted and an error is returned. |
| `execute_all_cells` | `file_path`, `timeout` (default `60.0`), `stop_on_error` (default `True`) | Execute all code chunks in order. Returns a cell-by-cell transcript. With `stop_on_error`, the run stops after the first chunk that produces an error output; with `False`, every chunk runs. A chunk still running at `timeout` is interrupted and the run stops with an error. |
| `get_kernel_state` | `file_path` | Report whether this document's kernel is `not started`, `alive`, or `dead`. |
| `restart_kernel` | `file_path` | Restart the kernel. All in-memory state is lost. |
| `interrupt_kernel` | `file_path` | Send a signal to stop a long-running chunk. Returns an error saying the kernel is not running if its process has died. |
| `shutdown_kernel` | `file_path` | Shut down the kernel and release resources. |

### Kernel lifecycle notes

- The kernel is **started lazily** on the first `execute_cell` / `execute_all_cells` call.
- **One kernel per `.rmd` file path**, cached in memory for the server's lifetime. The kernel tools look it up by the exact path string `execute_cell` was given; `restart_kernel` and `interrupt_kernel` return an error when no kernel runs for it.
- **Runs in the document's folder.** As in Jupyter, the kernel's working directory is the folder that contains the `.rmd` file, so relative paths in chunks (for example `read.csv("data/input.csv")`) resolve against that folder, not the server's install directory. `restart_kernel` keeps the same folder.
- **Kernel chosen by the first chunk run.** The language of the first executed chunk picks the kernelspec: `r` launches IRkernel (`ir`), `python` launches `python3`, and other languages pass through lowercased as the kernelspec name. `julia` launches the installed IJulia kernelspec: `julia` or `julia-1` if one exists, otherwise the highest-versioned `julia-X.Y` (IJulia names its kernelspecs after the Julia version, for example `julia-1.11`). With no Julia kernel installed, the error names `julia-1`. Later chunks run in that same kernel whatever their language, so in a mixed-language document call `shutdown_kernel` before running chunks in another language (this discards the kernel's state). The matching Jupyter kernel must be installed on the host.
- **Install IRkernel** (R): in R, run `install.packages("IRkernel"); IRkernel::installspec()`.
- **Outputs are never persisted.** R Markdown regenerates outputs on render (`rmarkdown::render()`), so the server returns outputs inline to the caller only.
- Kernels survive across tool calls: state accumulates across `execute_cell` invocations. Use `restart_kernel` to reset or `shutdown_kernel` to free resources.
- **A timeout interrupts the chunk.** When a chunk is still running after `timeout` seconds, the server interrupts it (as `interrupt_kernel` does) and waits up to 5 seconds for the kernel to stop. The error then says the chunk was interrupted; the kernel keeps its state and is ready for the next call. If the chunk ignores the interrupt, the error says the kernel is still busy: call `restart_kernel`. `timeout` must be positive. If the kernel hadn't started the chunk yet when the timeout passed, the chunk is interrupted as soon as it starts.
- **Calls on one document take turns.** Concurrent `execute_cell` / `execute_all_cells` calls on the same file never run two chunks at once, and each gets its own outputs; another call's chunk can run between two chunks of an `execute_all_cells` run. `interrupt_kernel` acts at once. `restart_kernel` and `shutdown_kernel` don't wait for a running chunk: they kill the kernel, and that execute call fails with "Kernel died during execution". Calls waiting behind it run afterwards on the restarted kernel, or fail with "Kernel was shut down" after `shutdown_kernel`.

### Format notes

- `.rmd` has no cell-boundary markers between adjacent prose blocks (unlike `.ipynb`). Two adjacent `markdown` cells in the model **auto-merge** on save + re-parse. This is expected; prefer inserting prose between code chunks or appending to an existing markdown cell.
- **Every save reads back as intended.** Before writing, each tool reads its new text back and compares the YAML header and the cells (type, text, and a chunk's language, label, options and fence) with what the edit meant, adjacent markdown cells counting as one. If they differ, the tool returns an error saying which cell would read back as what, and the file is left unchanged. See [Prose](#prose) for the edits this stops.
- Polyglot chunks (`{python}`, `{bash}`, `{sql}`) parse and round-trip correctly. For execution, the matching Jupyter kernel must be installed. No tool creates a non-R chunk or changes a chunk's language yet: `add_cell` writes ` ```{r} `, `replace_cell_source` keeps the language, and `set_chunk_option(key="language")` only adds a `language=` option to the header.
- **Chunks are found where knitr finds them** (its R Markdown `chunk.begin` and `chunk.end` patterns and the fence matching of its `group_indices`, checked in knitr 1.52.5's source). A chunk opens at a header line: three or more backticks after nothing but spaces, tabs or `>`, maybe spaces, then `{engine}` or `{engine options}`, the engine being letters, digits and underscores (` ```{r} `, `  ```{r} `, `> ```{r} `, ` ````{r} `, ` ``` {r} `). It closes only at a line with the header's fence, its indentation or `>` marks and its backticks, then nothing but spaces: in a ` ```{r} ` chunk ` ``` ` closes it, while ` ```` ` and `  ``` ` are code. The one exception is knitr's too: a chunk on the first line of a file without a YAML header closes at the first line of backticks alone, whatever its indentation or length. A header with the chunk's own fence right before its `{` (` ```{python} ` inside a ` ```{r} ` chunk) starts a new chunk there, the one before it having no closing fence; a header with another fence (`  ```{r} `, ` ````{r} `, ` ``` {r} ` in a ` ```{r} ` chunk) is code. A chunk that nothing closes runs to the end of the file. The text of an indented or blockquoted chunk is its code as knitr runs it, without the indentation or `>` marks (so its `#|` lines are read too), and edits write them back, its header line and closing fence keeping them. Regular markdown code fences (` ```python ` without braces, ` ```{.r} `, and ` ```{ r} ` or ` ```{r-x} `, which knitr doesn't read as headers) stay prose.
- **This changed how some files split into cells.** Before, only ` ```{lang} ` at the start of a line opened a chunk, only ` ``` ` closed it, other header lines in a chunk were code, and a header nothing closed was prose. Files that use other fences, hold a chunk header inside a chunk, leave a chunk open, or have header lines knitr doesn't read as headers (` ```{ r} `, ` ```{r-x} `, which opened chunks before and are prose now) read as knitr reads them, so `list_cells` can show other cells for them than before; files where every chunk opens with ` ```{engine ...} ` at the start of a line and closes with ` ``` ` read as they did. knitr refuses a few layouts outright (a chunk holding a closing fence of another fence that none of its own follows, or a chunk on the first line holding a header line); their lines read as code here, as in any other chunk.
- **A chunk without a closing fence** (ended by the next chunk's header, or by the end of the file) is written back as it was, and gets its closing fence when anything but a chunk header with its fence, as written in the file, comes after it: a new cell, prose moved there, or the text after the chunk that ended it, once that chunk is deleted.
- A document whose last line has no trailing newline keeps it that way while its last cell's text is left alone: re-saving that text, or changing a chunk's label or options, keeps the end of the file as it was. A newline is added when a cell is added after the last one or moved past it, so chunk fences never end up on the same line as other text. Rewriting the last cell's text also ends the file with a newline: new text from `replace_cell_source`, `prepend_to_cell` or `append_to_cell`, or a `split_cell` or `merge_cells` that takes in the last cell. For example, `replace_cell_source(1, "z")` on `` ```{r}\nx\n```\nlast `` writes `` ```{r}\nx\n```\nz\n ``.
- Only a line break ends a line, as in knitr: `\n`, `\r\n`, or a lone `\r`. A form feed or a Unicode line separator (U+2028) stays part of its line, so a chunk fence that follows one on the same line doesn't start a chunk. Every tool counts lines this way: the line count in `list_cells`, the `line_offset` of `split_cell`, the line numbers `find_in_rmd` gives, and the line and column `get_frontmatter`'s YAML errors give.
- **Line endings are kept.** A CRLF document, or one that mixes line endings, parses like an LF one: the YAML header, chunk fences and chunk headers are found the same way, and `get_cell`, `get_frontmatter` and `find_in_rmd` return text with `\n` line breaks. On save, cells you don't edit and header lines outside the edited key keep their bytes, and so do the body and closing fence of a chunk whose label or options you change (only its header line, or the `#|` lines of the option, is rewritten). Any other edited cell is rewritten whole, and everything an edit writes (a cell, a chunk header line, a frontmatter key's lines, a new header) uses the document's line ending, the one most of its lines end with. The one exception: a lone `\r` that an edit leaves just before a `\n` is rewritten in the document's line ending, so the two don't read back as one `\r\n` line break. Write the text you pass with `\n`; `\r\n` works too, and both are converted. An untouched CRLF file saves back byte for byte. `create_rmd` always writes LF.
- **A byte order mark is kept.** A file that starts with a UTF-8 byte order mark (as some Windows editors save it) reads as if it had none: the YAML header or a chunk fence on its first line is found, and no cell's text starts with the mark. Every save writes the mark back at the start of the file, so an untouched file still saves back byte for byte. `create_rmd` never writes one.
- **Lone surrogates are refused.** JSON lets a client send half of a surrogate pair (`\ud800`), which isn't a character and has no UTF-8 form. Every tool that takes text (cell sources, chunk option keys and values, labels, frontmatter keys and values, search text, `create_rmd`'s `title`, `author` and `output_format`) and every tool that opens the file refuses one in its arguments or path before doing anything: `Refused: the text holds a lone surrogate, U+D800, which is not a character and can't be written as UTF-8. <path> was not modified.`, with a surrogate in the path shown escaped (`\ud800`). One that the file's YAML gives (`#| label: "a\ud800b"`, written with a real backslash) is shown in the reply or error as its escape, a backslash then `ud800`; before, `list_cells` and `get_chunk_options` returned a reply that couldn't be sent, and over stdio the server process died.

### Chunk text

- **A chunk's text leaves off the line break before its closing fence.** `get_cell` returns `x <- 1` for a one-line chunk, and `replace_cell_source`, `add_cell`, `prepend_to_cell` and `append_to_cell` take text the same way. The closing fence always starts a new line, so text that ends with `\n` leaves a blank line before it: `replace_cell_source(i, "x <- 1\n")` writes `x <- 1`, then a blank line, then the fence. Pass `"x <- 1"` for no blank line.
- **Blank lines only.** A chunk that holds nothing but blank lines comes back as one `\n` per blank line, so an empty chunk (`""`, the fence right after the header) and a chunk with one blank line (`"\n"`) stay apart.
- **Every line is kept.** Saving a cell's own text back (the text `get_cell` returned) or adding empty text leaves the file byte for byte as it was, whatever its line endings. `split_cell` keeps every line of the chunk it splits, blank lines included, and `merge_cells` every line of the chunks it merges but the later chunks' labels, the options they set again, and the blank line after their option lines (see [Chunk options](#chunk-options-as-knitr-reads-them)). An option or label edit doesn't touch the body, apart from the `#|` lines of an option or label written there. `list_cells` counts the lines of a chunk's text, so for `x <- 1\n` it counts one line: the blank line before the fence isn't counted, and `split_cell` can't split it off.
- **Adding lines keeps blank lines.** `prepend_to_cell` and `append_to_cell` put the new text on lines of its own, one line break from the cell's text. The new text may supply that line break itself, by ending with one (`prepend_to_cell`) or starting with one (`append_to_cell`); none of the cell's own line breaks is taken for it, so its blank lines all stay. `prepend_to_cell(i, "Top")` on prose `\nMore\n` writes `Top\n\nMore\n`, and `append_to_cell(i, "y")` on a chunk whose text is `x\n` (`x`, then a blank line before the fence) writes `x\n\ny`. In prose, the line break that ends the cell's last line is the one before appended text. Text appended to a chunk keeps the rule above: `"y\n"` leaves a blank line before the fence.
- **Option lines stay at the top.** knitr reads a chunk's option lines (`#|` for `r`, `--|` for `sql`, `/*| ... */` for `c`, each engine's comment; see [Chunk options](#chunk-options-as-knitr-reads-them)) only at the very top of its body, so a line above them would make them code, silently. `prepend_to_cell` puts the text below them, and below the blank line after them that knitr takes with them: `prepend_to_cell(i, "library(x)")` on `#| echo: false\nx` writes `#| echo: false\nlibrary(x)\nx`. There, text that starts with an option line is refused (`Line 1 of the new text, '#| warning: false', is a chunk option line, but the chunk starts with option lines already ...`): set options with `set_chunk_option`, or rewrite the option lines with `replace_cell_source`. In a chunk without option lines the text goes on top, so its own option lines become the chunk's. `add_cell`, `replace_cell_source`, `prepend_to_cell` and `append_to_cell` refuse an option line after other lines of the text (`library(x)\n#| echo: false\nx`), which knitr would read as code, giving its line number in the text (`Line 2 of the new text, '#| echo: false', is a chunk option line after other lines, ...: move it up with the option lines at the top, or set the option with set_chunk_option`); for `replace_cell_source` and `prepend_to_cell`, a line the chunk already had there is fine. `append_to_cell` adds option lines only to an empty chunk or one holding option lines alone, and checks only the lines of the new text, so text that starts with its own line break can go below a last line that starts as an option line does. `prepend_to_cell` and `append_to_cell` also refuse text that would change which lines knitr reads as option lines: prepending `int y; */`, which ends with `*/`, under the `/*| echo: false */` line of a c chunk, or appending a line ending in `*/` under an open `/*|` line. `split_cell` refuses a split inside the option lines, which would give some of them to the new chunk, and one that would start the new chunk with a line that starts as an option line does, which is code where it is now. In a c, css or sas chunk whose every line ends with the comment's closing characters (`*/`, or `;` for sas), knitr reads only the first line as an option line, so `split_cell` also refuses a split that would leave the first chunk its option lines alone, and the errors for text say so (`... knitr reads only the first line of a chunk whose every line ends with '*/' as an option line ...`).
- **No fence lines inside.** knitr ends a chunk at a closing fence, a line of three or more backticks with nothing after them but spaces or tabs, and nothing before them but spaces, tabs or `>` (` ``` `, ` ```` `, `  ``` `, `> ``` `), and at a chunk header (such backticks, then `{engine}` or `{engine options}`: ` ```{r} `, `  ```{python} `), where it starts another chunk. Which of these lines ends a chunk depends on the chunk's fence and on where it is (see [Format notes](#format-notes)), so `add_cell`, `replace_cell_source`, `prepend_to_cell` and `append_to_cell` refuse new chunk text that holds any of them, as in `` Line 2 of the new text, '```{r}', is a chunk header for knitr (...), which would end the chunk there and start another ``; the error gives its line number in the text you passed. `merge_cells` puts the chunks' lines under the first chunk's fence, so it refuses a merge that would make one of them end the merged chunk (a ` ``` ` or ` ```{r} ` line from a ` ````{r} ` chunk, or any closing fence under a chunk on the first line of the file), naming its cell and line. Other lines that start with backticks are fine (` ```{ r} `, ` ```r `), and only the text you pass is checked, so a chunk that already holds such a line can still be appended to.

### Prose

Markdown text can't add or remove chunks, so the cells you see stay the cells you get:

- **No chunk openings.** `add_cell` (markdown), and `replace_cell_source`, `prepend_to_cell` and `append_to_cell` on a markdown cell, refuse new text that holds a line that would open a chunk: a chunk header for knitr, which this server reads the same way (three or more backticks after nothing but spaces, tabs or `>`, then `{engine}` or `{engine options}`, as in ` ```{r} `, ` ```{r setup, echo=FALSE} `, `  ```{r} `, `> ```{r} `, ` ````{r} ` or ` ``` {r} `). The error gives the line number in the text you passed. Add a chunk with `add_cell(cell_type="code")` instead, and to show chunk syntax as text, put `` `r ''` `` before the backticks (`` `r ''````{r} ``), as the R Markdown Cookbook does. Plain code blocks (` ```r `, ` ```` `, ` ```{.r} `), lines knitr doesn't read as headers (` ```{ r} `, ` ```{r-x} `), `~~~` fences and inline `` `r x` `` are fine. Only the text you pass is checked.
- **No new YAML header.** In a document without a header, text that would put a `---` line on the first line of the file, with another `---` line further down, would read back as the YAML header. Every tool refuses that, whether the text is new (`add_cell` at index 0, or a new first line for cell 0) or the cell becomes the first one (`delete_cell`, `move_cell`); the error gives the lines that would become the header. Start the first cell with other text, and use `set_frontmatter_key` to add a header.
- **A chunk left open stays a chunk.** A chunk header that nothing closes opens a chunk that runs to the end of the file, as for knitr (before, such a line was read as prose). A cell added after it gets the chunk's closing fence first, so it doesn't become chunk code: `add_cell(-1, "More", "markdown")` on `` Intro\n```{r}\nx\n `` writes `` Intro\n```{r}\nx\n```\nMore\n ``.
- **Chunks that change where they end.** An edit that would make knitr end a chunk elsewhere is refused by the read-back check: for example deleting the prose before a chunk that holds an `  ``` ` line, which would put the chunk on the first line of the file, where knitr closes it at that line. The other way round, a chunk on the first line that a closing fence of another fence closed (`> ``` ` after ` ```{r} `) is written anew with its own closing fence once a cell or a YAML header goes before it: `add_cell(0, "Intro", "markdown")` on `` ```{r}\nx\n> ```\nMore\n `` writes `` Intro\n```{r}\nx\n```\nMore\n ``.

### Chunk headers

`set_chunk_option` and `remove_chunk_option` rewrite only the chunk's header line (` ```{r label, key=value} `); the body and closing fence keep their bytes (an option or label written in a `#|` line is edited there instead; see [Chunk options](#chunk-options-as-knitr-reads-them)). The new header must read back with exactly the label and options asked for, and knitr, which reads keys and values as R code, must be able to read it. If not, the tool returns an error saying why (for text that would read back as other options, the header it would write and how that reads back), and the file is left unchanged:

- **Keys R can read.** knitr's `csv_options` reads the header as the arguments of `alist(...)`, where a key must be a syntactic R name: letters, digits, dots and underscores, starting with a letter or a dot not followed by a digit, and not a reserved word (`if`, `TRUE`, `...`). A dashed name of one of knitr's options, as Quarto writes them, goes in the header as the dotted name knitr reads it as (its `dot_names`): `set_chunk_option(key="fig-width", value="5")` writes ` ```{r fig.width=5} `, and a header copy written `fig-width=3` becomes `fig.width=5`. In a chunk that starts with YAML `#|` lines, a new dashed name goes there as written instead (`#| fig-width: 5`, after the other keys), and so does any other key that isn't a syntactic name (`#| code-fold: true`, `#| my key: 1`, quoted when R's yaml package would read it as something else); without `#|` lines such a key is refused (`Option key 'code-fold' isn't a syntactic R name ...`). When the `#|` lines can't take a new line (one c comment over several lines, or sas lines that would all end with `;`), a dashed name of knitr's goes in the header as the dotted name after all. A header key written in backticks or quotes, which R reads too (`` `my key`=1 ``, `"fig-width"=3`), is found by the name it stands for, and a dashed one of knitr's is written dotted when set. A header copy R can't read at all (`code-fold=TRUE`) counts as none: setting the key writes it as a new one and drops that copy, or is refused.
- **One line.** A key, value or label holding a line break (`\n`, `\r\n` or `\r`) is refused. For a line break inside an R string, write the escape `\n`, as in `fig.cap="Line one\nLine two"`.
- **Quote text.** A comma outside a quoted string would split the header into other options, so `fig.cap=a, b` is refused: pass the value `"a, b"`. In a key or value, a `#` outside a quoted string starts an R comment that runs to the end of the header, and an `=` outside quotes and brackets is a second `=` that knitr can't read (`fig.cap=a=1`), so both are refused; `x == 1`, `x <= 1` and `list(a = 1)` are fine. A key can't hold `=` at all, and a label holding one goes first in the header as an R string (` ```{r "x == 1"} `), as `quote_label` quotes no bare name with an `=` in it (see [Chunk labels](#chunk-labels)). Reading a header, a part is `key=value` at its first `=` outside quotes, backticks and brackets that isn't part of `==`, `!=`, `<=` or `>=`, as R reads it, so `"a=b"` and `list(a=1)` are names without a value, and `"fig.cap"="x"` is the key `"fig.cap"`.
- **Close what you open.** A key, value or bare-name label must close every bracket and quote it opens, and a key or value every backtick, or it would swallow the options after it: `"a`, `c(1, 2`, `` `x `` and `x}` are refused. Inside a quoted string a backslash escapes the next character, as in R, so `"say \"hi\", then go"` is one value, and `}` or backticks inside a quoted string are fine.
- **Give a value.** An empty value is refused for any key but `label`, where it clears the label: knitr reads a bare name in a chunk header as the chunk's label. Surrounding whitespace is dropped from keys, values and labels.
- **Headers written by hand.** If a header in the file already ends in an unmatched quote or bracket, a new option can't go after it: set that option to a balanced value first. A bare name stays where it is written when the header is rewritten: ` ```{r, foo} ` keeps its comma, and knitr reads `foo` as the label either way.

### Chunk labels

knitr finds a chunk's label in three places, and the tools follow it:

- **Where it can be written.** As a name without a value in the header (` ```{r setup} `, and also after other options or a comma: ` ```{r echo=FALSE, setup} ` and ` ```{r, setup} `), as a `label=` option (` ```{r label="setup"} `), or as a `#| label: setup` line among the option lines a chunk's body starts with (knitr 1.35 and later, and Quarto; knitr takes `#| id:` when there is no `label:`). When more than one is written, knitr takes the `#| label:` line over the header (warning about it), and `label=` over the bare name: its `csv_options` makes the bare name the label only when no `label=` is given.
- **Names without a value.** knitr's `csv_options` quotes the names written before the first `key=value` as one string, so ` ```{r ab, cd, echo=TRUE} ` and ` ```{r ab, cd} ` have the one label `ab, cd`, commas and all; `get_chunk_options` says so. A first name of one character is quoted alone (by its `quote_label`), so in ` ```{r a, b} ` the names are two. `quote_label` quotes no text with an `=` in it, even inside quotes or brackets, so a name holding one ends the names before it and is R code of its own: ` ```{r "a=b"} ` and ` ```{r echo=FALSE, "a=b"} ` are labelled `a=b`, ` ```{r list(a = 1)} ` is labelled `list(a=1)`, and ` ```{r foo, "a=b"} ` has two names, which knitr fails on. It quotes the text before the header's first `=` up to the last comma there, so a name with a comma before an `=` inside it (` ```{r cd(x, y=1)} `) is cut in two, which R can't parse: `get_chunk_options` says knitr fails on the header and lists the name among the options. A name after other options is R code: knitr takes a string's text, and writes other code without its spaces (` ```{r echo=FALSE, f(x, y)} ` is labelled `f(x,y)`). A header with any other name without a value (` ```{r echo=TRUE, a, b} `, ` ```{r a, echo=TRUE, b} `, ` ```{r a, b} `) is one knitr stops at ("All options must be of the form 'tag=value' except for the chunk label"): `get_chunk_options` shows `label: (none: knitr fails on this chunk header, ...)` naming them, lists them among the options, and `set_chunk_option(key="label")` and `remove_chunk_option(key="label")` are refused until you give them values (`set_chunk_option(key="b", value="TRUE")`) or remove them (`remove_chunk_option(key="b")`).
- **Reading.** `list_cells` and `get_chunk_options` show the label knitr uses. `get_chunk_options` says where it is written when it isn't a bare name, and which other spellings knitr reads it over, as in `label: setup (from label="setup")`; it doesn't list `label=` among the options, and `list_cells` doesn't count it. A line break in a label is shown as `\n`. A `label:` key the `#|` lines repeat is shown with the copies, as R's yaml package rejects a repeated key and knitr fails on the chunk; so is a repeated `label=` option, which knitr takes the first copy of in some steps and the last in others. With a `#| label:` line too, knitr puts the line's label in the first copy, so it still takes the last `label=` copy in some steps, which is noted.
- **Setting.** `set_chunk_option(key="label")` rewrites the label where knitr reads it: the `#| label:` (or `id:`) key, as one line holding its value as YAML, quoted when needed (also for text R's yaml package reads as something else, such as `y`, `n`, `1,000`, `.` or `0:30`; the body's other lines, the closing fence and their line endings stay as they are), the `label=` option (as an R string in the quotes it had, with `\` and quotes escaped), or else the bare name or names, in their place: first in the header, or after other options as an R name or, for other text, a quoted R string (` ```{r echo=FALSE, "my label"} `). A chunk without a label gets one first in the header, as a quoted R string if it holds an `=` (` ```{r "x == 1"} `), which R would otherwise read as code there. The spellings knitr reads it over are removed, so one is left: ` ```{r setup, label="other"} ` becomes ` ```{r label="L"} `, and repeated `#| label:` keys or `label=` options leave one.
- **Removing.** `remove_chunk_option(key="label")`, or `set_chunk_option(key="label", value="")`, removes every spelling, so no other one becomes the label: ` ```{r ab, cd, echo=TRUE} ` becomes ` ```{r echo=TRUE} `.
- Option lines count only at the very top of the body, in YAML form (the first one is `#| key: value`); see [Chunk options](#chunk-options-as-knitr-reads-them) for how they are found. They are read as one YAML document, as knitr reads them, so a value can go on over several lines, and a `label:` with no value gives no label. A `#| label:` line after other code, or R-style `#| label="x"` lines, are left alone.

### Chunk options as knitr reads them

knitr reads a chunk's options from its header and from the option lines at the top of its body, and merges them. `get_chunk_options`, `list_cells`, `set_chunk_option` and `remove_chunk_option` follow it:

- **Option lines.** knitr's `divide_chunk` finds them by the engine's comment characters followed by `| ` (xfun's `comment_chars` table): `#| ` for `r`, `python`, `bash` and any engine not in the table, `--| ` for `sql`, `mysql`, `psql`, `lua` and `haskell`, `//| ` for `Rcpp`, `cc`, `js`, `go`, `java`, `rust` and the other `//` languages, `%| ` for `matlab` and `tikz`, and a comment closed on each line for `c` and `css` (`/*| echo: false */`) and `sas` (`*| echo: false;`). Engine names match exactly, as in knitr (`{SQL}` uses `#| `), and when the first line doesn't start with the engine's characters, `#| ` lines are read instead. Where each line closes its comment, the lines run while they end with the closing characters, and knitr takes as many characters off each line as those have, spaces after them or not, so `/*| label: q */  ` is labelled `q */`; when every line of the chunk ends with them, the option lines are the first alone. Such lines are edited line by line. Lines that form one comment over several lines (`/*| a: 1`, then `/*| b: 2 */`) are read, but edits to them are refused.
- **Merging.** Each option knitr reads is listed once, as the spelling it uses: a `#|` line over the header (knitr warns about such a pair), a dashed name such as `#| fig-width: 5` over the dotted `fig.width=7` (knitr's `dot_names`, for the options knitr knows, so `#| code-fold: true` stays as it is), and the last copy of a key the header repeats (` ```{r echo=TRUE, echo=FALSE} ` is `echo=FALSE`), which also wins over a `#|` line for that key, as knitr puts the `#|` value in the first copy. The spellings it reads that one over are noted, as in `  #| echo: false (knitr reads it over echo=TRUE)`. A key the `#|` lines repeat is noted too: R's yaml package rejects it, so knitr fails on the chunk. `list_cells` counts each option once.
- **Setting.** `set_chunk_option` writes the value where knitr reads it: in the `#|` line that holds the key (its other lines and the body stay as they are; a value over several lines becomes one line), else in the header copy knitr uses, the last if the key is repeated there. The other spellings are removed, so one is left: ` ```{r echo=TRUE, fig.width=5, echo=FALSE} ` with `echo=TRUE` becomes ` ```{r fig.width=5, echo=TRUE} `, and a header copy that a `#|` line overrides goes. A key written nowhere yet goes at the end of the header, a dashed name of one of knitr's options as its dotted name; in a chunk with YAML `#|` lines, a dashed name or another key that isn't a syntactic R name goes in a new `#|` line after the other keys (see [Chunk headers](#chunk-headers)). In a `#|` line the R value is written as YAML that knitr reads back as the same value: `TRUE`, `FALSE` and `NULL` as `true`, `false` and `null`, a decimal number as written, a quoted R string as a YAML string (quoted when needed, as for labels), and any other R code tagged `!expr` (`c(6, 4)` becomes `!expr c(6, 4)`), which knitr evaluates.
- **Removing.** `remove_chunk_option` removes every spelling: each header copy, the `#|` line, and the dashed or dotted name knitr reads as the same option.
- **Keeping the lines YAML.** knitr reads the option lines as YAML only when the first one holds a key. So when an edit removes the first key, the comment and blank `#|` lines below it (`#| # note`) move to just after the next key; with no key left, they go too. An edit that would make the other lines read differently, such as removing an anchor (`&w`) that another key's alias (`*w`) needs, or make code below them option lines (a line ending in `*/` under the last `/*| ... */` line of a c chunk), is refused.
- **Repeated header keys are kept.** Rewriting a header for another option, or rewriting a chunk's text, keeps every copy of a repeated key as written; only an edit of that key leaves one.
- **Merging chunks.** `merge_cells` keeps every chunk's options where knitr reads them. The first chunk's label stays and the others' labels (a bare name, `label=`, `#| label:` or `#| id:`) go; the others' header options join the first chunk's header. All option lines (`#|` for r, `--|` for sql, `//|` for js, `/*| ... */` for c) go in one block at the top, written with the first block's comment characters, and the blank line after a later chunk's option lines, which knitr takes with them, goes. Rewritten lines keep their values: where the usual `text */` form would change one (the lines of a block scalar such as `fig-cap: |`), they are written as knitr reads them, `/*| fig-cap: |*/` and `/*|   a*/` with no space before `*/`, or as `#|` lines that keep their trailing spaces.
- **One value per option.** An option several merged chunks set to one value is written once, as the first of them writes it. Values are compared as knitr reads them: header `echo=FALSE` matches `#| echo: false`, `fig-width` matches `fig.width`, and a header string and a `#|` string with the same text, plain and quoted strings, `FALSE` and `false` (or `yes` and `true`), a value with a comment after it, flow and block lists, and `!expr` code with other spaces around it (not inside: `c(6,4)` against `c(6, 4)` is refused) are one value. Numbers, dates, and unquoted text that R's yaml reads as something else (`y`, `n`, number-like text) must be written alike: `7` against `7.0`, or `y` against `"y"`, is refused. An option set to different values (a header option against a `#|` line too) is refused, naming the option and both cells: give them one value with `set_chunk_option`, or remove one, first.
- **Merges that are refused.** The file is left unchanged when a chunk's option lines aren't YAML `key: value` lines, when a chunk's header is one knitr fails on, when a later chunk's option lines can't lose its label or an option set again (an alias to an anchor that goes, or one `/*| ... */` comment over several lines; the error starts `Can't merge cells i to j`, names the cell and the keys, and suggests rewriting those lines with `replace_cell_source` first), and when knitr would read other option lines at the top of the merged chunk, also when no later chunk has options: an open `/*|` comment in the first c chunk closed by a later chunk's code, c chunks holding only option lines, or a c, css or sas chunk whose every line ends with the closing characters merged with code that doesn't.

### Frontmatter edits

`set_frontmatter_key` and `remove_frontmatter_key` edit the YAML header line by line. They change only the target key's lines (the `key:` line at the start of the line plus the indented lines below it) and leave every other byte of the header as it is: comments, blank lines, quoting, tags such as `!r` and `!expr`, and key order.

- **Values.** The value is parsed as YAML. If it means the same when written as given, it's written that way: on the key's line for a one-line value, or indented below the key for a multi-line one. So `"!r Sys.Date()"` stays an R expression, `'"2026-04-20"'` stays a quoted string, and comments in a multi-line value are kept. Any other value is written as YAML for the parsed value. Quote a value to keep it a string (`'"42"'`, not `42`, which is an int).
- **No lone surrogates.** A value whose YAML reading holds a lone UTF-16 surrogate is refused, the file unchanged: an escape of a lone surrogate (`"\ud800"`), or of either half of a surrogate pair (so the pair of escapes for U+1F600 is refused too), anywhere in the value, keys and tagged values included (`The value for frontmatter key 'k' holds U+D800 as YAML reads it, a lone UTF-16 surrogate, which YAML can only write as an escape that the libyaml in R's yaml package rejects, ...`). Write a character beyond U+FFFF as itself, or as an escape of eight hex digits (`"\U0001F600"`).
- **New keys** go just before the closing `---`. A document without a header gets a new one at the top. A new key longer than 1024 characters as written, its quotes and escapes included, is refused with an error that says so: YAML reads a key on a `key: value` line only up to 1024 characters (the limit the YAML spec sets for an implicit key, which PyYAML and the libyaml in R's yaml package keep). The spaces and other whitespace around a key are dropped, but not a line break (`\n`, `\r`, or NEL, U+2028 and U+2029, which YAML reads as line breaks too): a new key holding one is refused (`Frontmatter key 'short\n' contains a line break, ...`), so `"title\n"` doesn't set `title`, and `remove_frontmatter_key("title\n")` finds no such key. A key holding a lone surrogate gets the refusal every tool gives (see [Format notes](#format-notes)).
- **Repeated keys.** If a key appears more than once, `set_frontmatter_key` replaces the first copy and removes the others, leaving one copy with the new value. `remove_frontmatter_key` removes every copy.
- **Headers that aren't valid YAML** (for example, a tab used for indentation) can still be edited: lines that start with `key:` at column 0 count as keys. `get_frontmatter` returns such a header as raw text, after a note saying what is wrong and where, as a line and column of the file (counted past a byte order mark, and with only a line break ending a line). That holds for syntax errors, for a control character such as a form feed, for an impossible date such as `2026-13-45` (the one PyYAML rejected, if there are several), for an explicit tag on a value it can't hold (`!!bool maybe` gives `can't read 'maybe' as !!bool`, likewise `!!int ""` or `!!timestamp hello`), for an int too long to print (more than 4300 digits, as hex digits can make it), for an escape past the last Unicode character (`"\U00110000"`), and for values nested more than 100 levels deep, deeper than this server reads. That depth counts the values aliases stand for, and each merge key (`<<`), since PyYAML builds and writes them recursively. Every other tool still works on such a file.
- **Values that can't be built.** A value passed to `set_frontmatter_key` (or a key, or `create_rmd`'s `output_format`) that would be such a value, such as `!!bool maybe`, is not YAML this server can read, so it is written as a quoted string, like any text that isn't valid YAML. A value sits one level down, under its key, so one nested 100 levels deep is written as a string too.
- **What can't be edited key by key:** a header that is a YAML list or a single value rather than `key: value` lines, a flow-style header such as `{title: x, author: y}`, and a header whose keys are indented rather than starting at column 0. For these, both tools return an error and the file is left unchanged.
- **Safety check.** If the header was valid YAML before an edit, it must still be valid afterwards, with the same other keys. Otherwise the tool returns an error and doesn't write the file. This can happen when the edit removes an anchor that another key refers to.

## Which tool should I use?

### Discovering what's in a document (do this first)

- **Don't know what's in the document?** → `list_cells`
- **Need to see a chunk's language/label/options?** → `get_chunk_options`
- **Need to see the YAML header?** → `get_frontmatter`
- **Searching for a name or string?** → `find_in_rmd`
- **Need to read a specific cell?** → `get_cell`

### Creating documents

- **Need a new empty `.rmd`?** → `create_rmd` (do NOT hand-write `.rmd` with a generic `Write` tool — `create_rmd` guarantees a valid YAML frontmatter)

### Editing

| Intent | Tool |
| :--- | :--- |
| Add a new cell at a specific position | `add_cell` |
| Remove a cell | `delete_cell` |
| Reorder cells | `move_cell` |
| Break a large cell into two | `split_cell` |
| Combine consecutive same-type cells | `merge_cells` |
| Rewrite a cell's whole body | `replace_cell_source` |
| Add lines to the top of a cell | `prepend_to_cell` |
| Add lines to the bottom of a cell | `append_to_cell` |
| Set a chunk label or option | `set_chunk_option` |
| Remove a chunk label or option | `remove_chunk_option` |
| Set a frontmatter key | `set_frontmatter_key` |
| Remove a frontmatter key | `remove_frontmatter_key` |

### Running chunks

| Intent | Tool |
| :--- | :--- |
| Run one specific chunk | `execute_cell` |
| Re-run the whole document | `execute_all_cells` |
| Stop a stuck chunk | `interrupt_kernel` |
| Reset kernel state | `restart_kernel` |
| Check if the kernel is alive | `get_kernel_state` |
| Release kernel resources | `shutdown_kernel` |

### Avoid

- `replace_cell_source` to add a few lines: use `prepend_to_cell` or `append_to_cell`.
- `add_cell` to replace a cell: use `replace_cell_source`.
- A key of your own naming for the label: set it with `set_chunk_option(key="label")`.

## Prerequisites

This MCP server uses [`uv`](https://docs.astral.sh/uv/) to manage its Python environment and dependencies automatically. Install `uv` if you don't have it already:

**macOS / Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Homebrew (macOS):**

```bash
brew install uv
```

**pip (any platform):**

```bash
pip install uv
```

Verify the installation:

```bash
uv --version
```

> For more options (Docker, Cargo, WinGet, etc.), see the [official uv installation docs](https://docs.astral.sh/uv/getting-started/installation/).

**uv 0.9.17 or newer is required.** This server's `pyproject.toml` sets a 7-day dependency cooldown (`[tool.uv] exclude-newer = "7 days"`). Older uv versions can't parse that relative duration. They print a warning and ignore the setting. A plain `uv sync` or `uv run`, including the `uv --directory … run` launch commands below, then discards the committed `uv.lock`, re-resolves to the newest compatible versions (even ones published in the last 7 days), and rewrites the file. Upgrade with `uv self update`, `brew upgrade uv`, or `pip install -U uv`, depending on how you installed it. Upgrading doesn't undo an earlier rewrite: restore the original `uv.lock` with `git checkout HEAD -- uv.lock` in this folder, or copy it again from the archive you downloaded.

For kernel execution, install the matching Jupyter kernel:

- **R:** in R, run `install.packages("IRkernel"); IRkernel::installspec()`. Docs: <https://irkernel.github.io/>
- **Python:** `pip install ipykernel`, then `python -m ipykernel install --user` with the same Python. The second step registers the kernel in your user Jupyter folder, which the server always searches. Without it, the kernelspec stays under that Python's own prefix (for example a Homebrew, pyenv or conda Python), where the server may not find it.
- **Julia:** in Julia, `using Pkg; Pkg.add("IJulia")`. IJulia names its kernelspec after the Julia version (for example `julia-1.11`); the server finds it under that name.

The server itself depends on `mcp`, `pyyaml`, and `jupyter-client`. `uv` handles all of these automatically on first run.

## Installation

> **Note:** Replace `/absolute/path/to/rmd-editor` below with the absolute path to the `rmd-editor` folder on your machine (the folder that contains its `pyproject.toml`).

### Method 1: CLI Configuration (Claude Code, Codex, Gemini)

If your agent supports adding servers via CLI, run the following:

`--scope user` installs the server globally so it's available in every project on your machine. Drop it if you only want the server active in the current project.

```bash
# Claude Code / Codex
[claude|codex] mcp add rmd-editor --scope user -- uv --directory /absolute/path/to/rmd-editor run rmd-editor-mcp

# Gemini CLI
gemini mcp add --transport stdio --scope user rmd-editor -- uv --directory /absolute/path/to/rmd-editor run rmd-editor-mcp
```

### Method 2: JSON Configuration

For tools that use a `mcp_config.json` or `settings.json` file, add the following block.

> **Important:** Use the **absolute path** to `uv` for `"command"`, not just `"uv"`. GUI-based MCP clients (Claude Desktop, Cursor) don't always inherit your shell `PATH`, so a bare `"uv"` will fail with a "command not found" error. Get your absolute path with:
>
> ```bash
> which uv
> # e.g. /Users/you/.local/bin/uv  or  /opt/homebrew/bin/uv
> ```

```json
{
  "mcpServers": {
    "rmd-editor": {
      "command": "/absolute/path/to/uv",
      "args": [
        "--directory",
        "/absolute/path/to/rmd-editor",
        "run",
        "rmd-editor-mcp"
      ]
    }
  }
}
```

| Agent | Configuration File Path |
| :--- | :--- |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS); `%APPDATA%\Claude\claude_desktop_config.json` (Windows) |
| **Cursor** | `.cursor/mcp.json` (Project) or `~/.cursor/mcp.json` (Global) |
| **Windsurf** | Agent Panel → "..." → MCP Servers → View raw config |
| **Antigravity** | `~/.gemini/config/mcp_config.json` — see [Antigravity IDE](#antigravity-ide) (uses `uvx --from`) |
| **Gemini CLI** | `~/.gemini/settings.json` (Global) or `.gemini/settings.json` (Project) |

### Antigravity IDE

The Antigravity IDE uses its own MCP config file and a `uvx`-based command — **not** the `uv --directory … run` form shown above. Add the server to `~/.gemini/config/mcp_config.json`:

> **Important:** Use the **absolute path** to `uvx` for `"command"`, not a bare `"uvx"` — Antigravity doesn't inherit your shell `PATH`. Find it with `which uvx` (e.g. `/opt/homebrew/bin/uvx`).

> **Note:** `uvx` ignores both this server's `uv.lock` and the `[tool.uv]` settings in its `pyproject.toml`. It re-resolves dependencies on each launch instead of using the locked versions, and the 7-day cooldown is passed explicitly as `--exclude-newer "7 days"` in `args`, so you get the newest compatible releases that are at least 7 days old. This requires uv 0.9.17 or newer: older versions reject the value (`invalid value '7 days' for '--exclude-newer <EXCLUDE_NEWER>'`) and the server fails to start.

```json
{
  "mcpServers": {
    "rmd-editor": {
      "command": "/absolute/path/to/uvx",
      "args": [
        "--exclude-newer",
        "7 days",
        "--from",
        "/absolute/path/to/rmd-editor",
        "rmd-editor-mcp"
      ]
    }
  }
}
```

### Using Standard Python (Fallback)

If you prefer not to use `uv`, run the following from the `rmd-editor` folder (the one that contains its `pyproject.toml`), then point to the `.venv` executable it creates. `python3` must be Python 3.10 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install .
```

This path doesn't use uv, so the `[tool.uv]` 7-day dependency cooldown doesn't apply. With pip 26.1 or newer, add `--uploaded-prior-to P7D` to the `pip install` command to apply the same cooldown.

```json
{
  "mcpServers": {
    "rmd-editor": {
      "command": "/absolute/path/to/rmd-editor/.venv/bin/python",
      "args": ["-m", "rmd_editor.server"]
    }
  }
}
```

## Agent Configuration (Important)

Coding agents are heavily biased toward their default tools. You **must** explicitly instruct them to use `rmd-editor` when working with R Markdown documents. The agent prompt lives in [`RMD-EDITOR.md`](./RMD-EDITOR.md) — a standalone file you wire into your agent's system instructions. The server also sends a condensed version of this guidance as MCP server `instructions`, which some clients pass to the model automatically. Wiring in the full prompt file is still recommended.

### Claude Code / Claude Desktop (via `@`-include)

Claude Code supports `@filename` includes in `CLAUDE.md`. Copy the prompt file into your global config directory and add one include line:

```bash
cp /absolute/path/to/rmd-editor/RMD-EDITOR.md ~/.claude/
echo '@RMD-EDITOR.md' >> ~/.claude/CLAUDE.md
```

Or for a single project, place it next to the project's `CLAUDE.md` and add `@RMD-EDITOR.md` there.

### Other agents (Cursor, Codex CLI, Windsurf, Antigravity, Aider, Gemini CLI, etc.)

Copy the **contents** of [`RMD-EDITOR.md`](./RMD-EDITOR.md) into your agent's instruction file (`AGENTS.md`, `.cursor/rules/*.mdc`, `.windsurfrules`, `.github/copilot-instructions.md`, system prompt, etc.). Most non-Claude agents don't support `@`-include — paste the prompt body directly.

| Agent | Instruction file |
| :--- | :--- |
| **Any agent that reads `AGENTS.md`** (Codex CLI, Windsurf, Zed, Cursor secondary) | `AGENTS.md` at repo root |
| **Cursor** | `.cursor/rules/*.mdc` (current) — legacy: `.cursorrules` |
| **GitHub Copilot** | `.github/copilot-instructions.md` |
| **Windsurf** | `.windsurfrules` or `AGENTS.md` |
| **Antigravity** | `_agents/rules/` |
| **Aider / Gemini CLI / generic** | Rules file or system prompt |

## Logging & Debugging

The server logs all tool invocations and errors to **stderr** (safe for stdio transport — does not interfere with JSON-RPC). Logs include timestamps and severity levels.

To inspect logs when running under Claude Desktop, check:

- **macOS:** `~/Library/Logs/Claude/mcp*.log`
- **Windows:** `%APPDATA%\Claude\logs\mcp*.log`

For interactive testing, use the [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector), which provides a UI for exercising each tool with custom parameters and inspecting responses.

### Common issues

- **`No such kernel named <name>`** — the Jupyter kernel for the chunk's language isn't installed (`ir` for R chunks, `python3` for Python chunks, `julia-1` for Julia chunks when no IJulia kernelspec is found). To see the kernels the server can find, run `uv --directory /absolute/path/to/rmd-editor run jupyter kernelspec list`. Install the missing one per the Prerequisites section, then run the chunk again; `get_kernel_state` stays `not started` after this error, so the server doesn't need a restart.
- **"Kernel failed to start"** — the kernelspec exists but the kernel couldn't be launched (for example, its command points to an R installation that has moved), or it started but died or didn't become ready within 30 seconds. The message includes the underlying error. Check that the kernel's own runtime works (for example, that R starts and loads IRkernel), then retry. `restart_kernel` reports the same kinds of problems as **"Kernel failed to restart"**. After any of these errors nothing is left running (`get_kernel_state` reports `not started`), and the server log gets one warning line, not a traceback.
- **"Execution timed out after Ns; the cell was interrupted"** — the chunk ran longer than `timeout` and was stopped; the kernel keeps its state. For long-running code, pass a larger `timeout` (in seconds).
- **"... the kernel was interrupted but is still busy"** — the chunk ignored the interrupt (for example, native code that doesn't check for interrupts). Call `restart_kernel`; in-memory state is lost.
- **"Kernel is not running (its process has exited)"** from `interrupt_kernel` — the kernel crashed or was killed (`get_kernel_state` reports `dead`). The next `execute_cell` starts a fresh kernel.
- **"File is not a .rmd document"** — every tool checks that the path ends in `.rmd`. The check ignores case, so `.Rmd` (the usual RStudio extension) and `.RMD` work as they are. Any other extension, such as `.qmd`, `.md` or `.txt`, is rejected; rename the file to `.Rmd`. For a Jupyter notebook, use `notebook-editor`, or convert between `.Rmd` and `.ipynb` with [`jupytext`](https://jupytext.readthedocs.io/).
- **Outputs aren't appearing in the file** — by design. Outputs are returned inline to the caller. To persist, render with `rmarkdown::render("file.rmd")`.
- **Adjacent markdown cells merged after a save** — by design. `.rmd` has no cell-boundary markers for prose; the model collapses consecutive markdown cells on re-parse.

## Tool count

**24 tools** total:

- 1 document creation (`create_rmd`)
- 7 cell structure & navigation (`list_cells`, `get_cell`, `add_cell`, `delete_cell`, `move_cell`, `split_cell`, `merge_cells`)
- 3 cell content editing (`replace_cell_source`, `prepend_to_cell`, `append_to_cell`)
- 3 chunk options (`get_chunk_options`, `set_chunk_option`, `remove_chunk_option`)
- 3 YAML frontmatter (`get_frontmatter`, `set_frontmatter_key`, `remove_frontmatter_key`)
- 1 discovery (`find_in_rmd`)
- 2 execution (`execute_cell`, `execute_all_cells`)
- 4 kernel lifecycle (`get_kernel_state`, `restart_kernel`, `interrupt_kernel`, `shutdown_kernel`)
