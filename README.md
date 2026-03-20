# agent-skills

A personal collection of Claude Code agent skills, can be used with other agents too.

## Available Skills

| Skill | Command | Description |
| ------- | ------- | ----------- |
| [git-workflow](./skills/git-workflow/SKILL.md) | `/git-workflow` | Guided Git workflow: branching, commits, PRs, and conflict resolution |
| [code-review](./skills/code-review/SKILL.md) | `/code-review` | Thorough code review covering correctness, security, performance, and style |
| [english-humanizer](./skills/english-humanizer/SKILL.md) | `/humanize` | Humanize the text |
| [grill-master](./skills/grill-master/SKILL.md) | `/grill`, `/grill-master`, `/grill-me` | Get relentlessly interviewed about a topic, plan or design until every branch of the decision tree is resolved. |
| [spec-writer](./skills/spec-writer/SKILL.md) | `/spec`, `/spec-writer` | Create a PRD through user interview, codebase exploration, and module design, then submit as a GitHub issue. Use when user wants to write a PRD, create a product requirements document, or plan a new feature. |
| [slice-the-spec](./skills/slice-the-spec/SKILL.md) | `/slice`, `/slice-the-spec` | Break a PRD into independently-grabbable GitHub issues using vertical slices. |

## Installation via [skills.sh](https://skills.sh)

Install all skills at once:

```bash
npx skills@latest add kambleakash0/agent-skills --all
```

or, install individual skills:

```bash
npx skills@latest add kambleakash0/agent-skills/skills/git-workflow
npx skills@latest add kambleakash0/agent-skills/skills/code-review
npx skills@latest add kambleakash0/agent-skills/skills/english-humanizer
npx skills@latest add kambleakash0/agent-skills/skills/grill-master
npx skills@latest add kambleakash0/agent-skills/skills/spec-writer
npx skills@latest add kambleakash0/agent-skills/skills/slice-the-spec
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
