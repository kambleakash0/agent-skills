# Contributing to agent-skills

Thanks for your interest in contributing! This repo contains agent skills and MCP servers for AI coding assistants. Contributions of all kinds are welcome — new skills, MCP server improvements, bug fixes, documentation, and ideas.

## Getting started

1. Fork the repo and clone your fork.
2. Create a branch for your work: `git checkout -b my-feature`.
3. Make your changes (see guidelines below).
4. Run any relevant tests before submitting.
5. Open a pull request against `main`.

## Adding a new skill

1. Create a folder under `skills/` — the folder name must match the `name` field in YAML frontmatter.
2. Add a `SKILL.md` with the required frontmatter (`name`, `description`, `triggers`, `metadata`).
3. If the skill needs reference material, add a `resources/` subfolder.
4. Add a row to the **Available Skills** table in the root `README.md`.
5. Test locally by placing the folder in `~/.claude/skills/` or `~/.agents/skills/`.

See the [Skill Format](README.md#skill-format) section for the full schema.

## Working on MCP servers

Running a server or its tests needs uv 0.9.17 or newer (check with `uv --version`). Each server's `pyproject.toml` sets a relative `exclude-newer = "7 days"` cooldown. Older uv only warns about it, then re-resolves without the cooldown and rewrites `uv.lock`. Don't commit that rewrite. Upgrading uv doesn't undo it, so restore the lock from the server folder with `git checkout HEAD -- uv.lock`.

A passing test run ends with `Results: N passed, 0 failed` and `ALL TESTS PASSED`. Any failure makes the runner exit non-zero. Always run the test suite before submitting changes. If you're adding a new language or tool, add corresponding test cases.

### ast-editor

```bash
cd mcp-servers/ast-editor
uv sync
uv run python tests/run_all_tests.py
```

### notebook-editor

```bash
cd mcp-servers/notebook-editor
uv sync
uv run python tests/run_all_tests.py
```

### rmd-editor

```bash
cd mcp-servers/rmd-editor
uv sync
uv run python tests/run_all_tests.py
```

The rmd-editor suite doesn't execute R code, so you don't need R or IRkernel to run it.

### Changing dependencies, versions, or the lockfile

Use uv 0.12.22 or newer (ideally the latest) for anything that rewrites `uv.lock`: `uv add`, `uv remove`, `uv lock --upgrade`, `uv lock --upgrade-package <name>`, and any `uv lock`, `uv sync`, or `uv run` after you edit `pyproject.toml` (for example a `version` bump). uv before 0.12.22 writes an older lock format, which adds unrelated lines to the diff: `revision = 3`, plus extra `marker = ...` clauses before 0.11.25, plus a dated `exclude-newer` timestamp before 0.11.8.

Before committing a changed `uv.lock`, check that the diff only touches the packages you meant to change, that `revision` hasn't gone down (it's `5` today), and that the `[options]` block still reads:

```toml
[options]
exclude-newer = "0001-01-01T00:00:00Z" # This has no effect and is included for backwards compatibility when using relative exclude-newer values.
exclude-newer-span = "P7D"
```

If any of these checks fails, upgrade uv and restore the committed lock from the server folder with `git checkout HEAD -- uv.lock` (keep your `pyproject.toml` changes). Then run `uv lock`, or re-run your `uv lock --upgrade` or `uv lock --upgrade-package <name>` command. Running `uv add`, `uv lock`, or `uv sync` on top of an old-format lock doesn't convert it, so restore the lock first.

## Code style

- Python code follows standard PEP 8 conventions.
- Keep diffs focused — avoid unrelated formatting changes.
- Prefer small, reviewable pull requests over large ones.

## Reporting bugs

Open an [issue](https://github.com/kambleakash0/agent-skills/issues) with:

- What you expected to happen.
- What actually happened (include error messages or output).
- Steps to reproduce.
- Which skill or MCP server is affected.

## Suggesting features

Open an issue with the **enhancement** label. Describe the use case and why it would be valuable.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
