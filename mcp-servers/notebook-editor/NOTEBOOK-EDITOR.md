# Notebook Editor MCP Server

When working with `.ipynb` Jupyter notebook files, do NOT use the generic `edit` or `write` tool. Use the `notebook-editor` MCP server instead. It exposes 23 cell-level tools for creating, editing, and executing notebooks. Use `create_notebook` to create a new `.ipynb` (never hand-write notebook JSON).

**Picking a tool — always start here:**

1. **Start by calling `list_cells`** to see the notebook's structure (cell types, line counts, previews). Call `list_notebook_symbols` if you need to find Python symbols (functions, classes) across cells. Call `find_in_notebook` for text search. Call `get_cell(index)` to read one cell's full source.
2. **Creating a new notebook:** `create_notebook` (do NOT hand-write `.ipynb` JSON with a generic `Write` tool — `create_notebook` guarantees valid nbformat structure and kernelspec).
3. **Editing cells:**
   - New cell at a position: `add_cell` (default type is `code`; pass `index=-1` to append)
   - Rewrite a cell: `replace_cell_source`
   - Add lines to an existing cell: `prepend_to_cell` / `append_to_cell`
   - Reorder: `move_cell`
   - Split a large cell: `split_cell`
   - Merge consecutive same-type cells: `merge_cells`
   - Delete: `delete_cell`
4. **Outputs & metadata:**
   - Read outputs: `get_outputs`
   - Clear stale outputs: `clear_outputs`
   - Clear numbering: `clear_execution_counts`
   - Tag with metadata: `set_cell_metadata`
5. **Running cells:**
   - One cell: `execute_cell`
   - Whole notebook: `execute_all_cells`
   - Stop a runaway cell: `interrupt_kernel`
   - Fresh namespace: `restart_kernel`
   - Check if kernel is alive: `get_kernel_state`
   - Release resources: `shutdown_kernel`

**Anti-patterns to avoid:**

- Don't use `replace_cell_source` to add a couple of lines — use `prepend_to_cell` / `append_to_cell`.
- Don't use `add_cell` to replace an existing cell — use `replace_cell_source`.
- Don't skip `list_cells` and guess indices — they're zero-based and shift when you add/delete cells.
- Don't call `execute_cell` on a markdown cell (it will error).
- Don't hand-write notebook JSON with `Write` — use `create_notebook` for new files.

**Kernel lifecycle notes:**

- Kernel starts lazily on first `execute_cell` / `execute_all_cells`. One kernel per notebook file path, cached for the server's lifetime.
- State accumulates across calls: variables from an earlier `execute_cell` are visible to later ones. Use `restart_kernel` for a clean namespace or `shutdown_kernel` to release resources.
- **Kernel-agnostic.** The kernel language follows `metadata.kernelspec.name` in the notebook (python3, ir for R, julia-1.x, etc.) — works with any Jupyter kernel installed on the host. Set it at creation: `create_notebook(path, kernel_name="ir", language="R")`.
- **Symbol discovery is Python-only.** `list_notebook_symbols` returns a clear refusal message for non-Python notebooks. Use `find_in_notebook` instead.
