# agent-skills

A personal collection of Claude Code agent skills and MCP servers, can be used with other agents too.

## Available Skills

| Skill | Command | Description |
| ------- | ------- | ----------- |
| [git-workflow](./skills/git-workflow/SKILL.md) | `/git-workflow` | Guided Git workflow: branching, commits, PRs, and conflict resolution |
| [code-review](./skills/code-review/SKILL.md) | `/code-review` | Thorough code review covering correctness, security, performance, and style |
| [english-humanizer](./skills/english-humanizer/SKILL.md) | `/humanize` | Humanize the text |
| [grill-master](./skills/grill-master/SKILL.md) | `/grill`, `/grill-master`, `/grill-me` | Get relentlessly interviewed about a topic, plan or design until every branch of the decision tree is resolved. |
| [spec-writer](./skills/spec-writer/SKILL.md) | `/spec`, `/spec-writer` | Create a PRD through user interview, codebase exploration, and module design, then submit as a GitHub issue. Use when user wants to write a PRD, create a product requirements document, or plan a new feature. |
| [slice-the-spec](./skills/slice-the-spec/SKILL.md) | `/slice`, `/slice-the-spec` | Break a PRD into independently-grabbable GitHub issues using vertical slices. |
| [incremental-tdd](./skills/incremental-tdd/SKILL.md) | `/tdd`, `/incremental-tdd` | Test-driven development with a red-green-refactor loop. Builds features or fixes bugs one vertical slice at a time. |
| [deep-codebase-audit](./skills/deep-codebase-audit/SKILL.md) | `/deep-codebase-audit`, `/deep-audit`, `/codebase-audit` | Explore a codebase the way an AI agent experiences it: by reading files, following references, and trying to understand how to make safe changes. It surfaces architectural friction (shallow modules, tangled dependencies, missing seams) and suggests **deep-module** improvements that make the codebase easier to test, reason about, and modify with AI. |
| [spec-to-plan](./skills/spec-to-plan/SKILL.md) | `/spec-plan`, `/spec-to-plan` | Turn a PRD into a multi-phase implementation plan using tracer-bullet vertical slices. |
| [domain-glossary](./skills/domain-glossary/SKILL.md) | `/domain-glossary`, `/glossary` | Turn an ongoing conversation into a **DDD-style ubiquitous language** document. It scans for domain terms, resolves ambiguities, proposes canonical names, and writes a living glossary to `DOMAIN_GLOSSARY.md` in the working directory. |
| [script-writer](./skills/script-writer/SKILL.md) | `/script-writer`, `/write-a-script` | Script-writer that drafts presentations, essays, emails, and slides using only the cognitive and persuasive heuristics from Patrick Winston's "How to Speak" lecture. |

## MCP Servers

| Server | Description |
| ------ | ----------- |
| [ast-editor](./mcp-servers/ast-editor/README.md) | AST-targeted code editing MCP server with **28 surgical tools**: functions, classes, methods, fields, parameters, imports, parametrized tools for leading comments (`edit_leading_comment(op=...)`), sibling inserts (`insert_sibling`), body inserts (`insert_in_body(at/after/before)`), and tiered reads (`read_symbol(depth=full/interface/signature)`). In-body snippet editing (`replace_in_body`, `delete_in_body`), dict/list editing across JSON/YAML/TOML and Python/JS/TS literals. Dotted targets descend into closures (Go `stdioCmd.RunE`, TS `app.handler`). Built on tree-sitter. Supports **11 languages**: Python, JavaScript, TypeScript, C, C++, Ruby, Go, Java, JSON, YAML, and TOML. |
| [notebook-editor](./mcp-servers/notebook-editor/README.md) | Jupyter notebook editing MCP server with **23 cell-level tools**: notebook creation (`create_notebook` with valid nbformat schema), cell structure (add/delete/move/split/merge), content editing (replace/prepend/append), outputs & metadata management, notebook-wide symbol discovery, and **kernel execution** (execute_cell, execute_all_cells, restart/interrupt/shutdown kernel). Complements `ast-editor` — use this for `.ipynb` files, `ast-editor` for everything else. |

## Skills installation via [skills.sh](https://skills.sh)

Install multiple skills at once:

```bash
npx skills@latest add kambleakash0/agent-skills
```

or, install individual skills:

```bash
npx skills@latest add kambleakash0/agent-skills/skills/git-workflow
npx skills@latest add kambleakash0/agent-skills/skills/code-review
npx skills@latest add kambleakash0/agent-skills/skills/english-humanizer
npx skills@latest add kambleakash0/agent-skills/skills/grill-master
npx skills@latest add kambleakash0/agent-skills/skills/spec-writer
npx skills@latest add kambleakash0/agent-skills/skills/slice-the-spec
npx skills@latest add kambleakash0/agent-skills/skills/incremental-tdd
npx skills@latest add kambleakash0/agent-skills/skills/deep-codebase-audit
npx skills@latest add kambleakash0/agent-skills/skills/spec-to-plan
npx skills@latest add kambleakash0/agent-skills/skills/domain-glossary
npx skills@latest add kambleakash0/agent-skills/skills/script-writer
```

## Skill Format

Each skill is a Markdown file with a YAML front-matter block followed by the prompt body, following the [skills.sh](https://skills.sh) spec:

```markdown
---
name: skill-name
description: >
  What the skill does and when to trigger it.
  TRIGGER when the user writes /skill-name.
metadata:
  author: kambleakash0
  version: x.y.z
triggers:
  - /trigger-1
  - /trigger-2
  - ...
---

Skill prompt body goes here…
```

## Adding New Skills

1. Create a new folder in the root of `skills/`. The folder name must strictly match your skill's `name` in the YAML frontmatter.
2. Add a `SKILL.md` file in the root of the new folder. Ensure it contains a `name` (max 64 chars) and `description` (non-empty, max 1024 chars) inside the YAML frontmatter.
3. If needed, add a `resources/` folder in the root of the new folder and populate it with the necessary files.
4. Add a row to the **Available Skills** table in this README.
5. Test it locally by placing the folder from `skills/` in `~/.claude/skills/` or `~/.agents/skills/`.

## MCP Servers' installation

Refer to their respective READMEs for installation instructions.
