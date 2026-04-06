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

### ast-editor

```bash
cd mcp-servers/ast-editor
uv sync
uv run python tests/run_all_tests.py   # 218 tests
```

### notebook-editor

```bash
cd mcp-servers/notebook-editor
uv sync
uv run python tests/run_all_tests.py   # 68 tests
```

Always run the test suite before submitting changes. If you're adding a new language or tool, add corresponding test cases.

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
