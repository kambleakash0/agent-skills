# Notebook Editor MCP Server

For `.ipynb` Jupyter notebook files, do NOT use the generic `edit` or `write` tool. Use the `notebook-editor` MCP server: 23 cell-level tools for creating, editing, and executing notebooks.

**Picking a tool — always start here:**

1. **Start with `list_cells`** for the structure (cell types, line counts, previews). `get_cell(index)` reads one cell's source, `find_in_notebook` searches text, `list_notebook_symbols` finds Python functions and classes across cells.
2. **New notebook:** `create_notebook` (it guarantees a valid nbformat structure and kernelspec; never hand-write `.ipynb` JSON with `Write`).
3. **Editing cells:**
   - New cell at a position: `add_cell` (default type `code`; `index=-1` appends)
   - Rewrite a cell: `replace_cell_source`
   - Add lines to a cell: `prepend_to_cell` / `append_to_cell`
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

**Kernel lifecycle notes:**

- One kernel per notebook, started lazily on the first `execute_cell` / `execute_all_cells` and kept for the server's lifetime. It runs in the notebook's folder, so relative paths resolve there.
- State accumulates across calls. `restart_kernel` gives a clean namespace, `shutdown_kernel` frees resources.
- A cell still running at `timeout` (seconds, positive) is interrupted and the kernel keeps its state; if the error says the kernel is still busy, call `restart_kernel`. Cells on one notebook run one at a time; `restart_kernel` and `shutdown_kernel` kill a running cell instead of waiting.
- **Kernel-agnostic.** The kernel follows `metadata.kernelspec.name` (python3, ir for R, julia-1.x, ...): any Jupyter kernel installed on the host. Set it at creation: `create_notebook(path, kernel_name="ir", language="R")`.
- The built-in `python3` kernel runs in the server's environment and can't import the user's packages. For a project environment: install `ipykernel` there, run `python -m ipykernel install --user --name <name>` with its Python, then call `create_notebook(path, kernel_name="<name>")` or set the notebook's kernelspec to `<name>`. Naming it `python3` doesn't override the built-in kernel.
- **`list_notebook_symbols` is Python-only;** in other languages use `find_in_notebook`.
