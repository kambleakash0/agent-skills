# agent-skills

A personal collection of Claude Code agent skills, can be used with other agents too.

## Installation

Install all skills at once or choose individual skills via [skills.sh](https://skills.sh):

```bash
npx skills add kambleakash0/agent-skills
```

## Available Skills

| Skill | Command | Description |
| ------- | ------- | ----------- |
| [git-workflow](./skills/git-workflow/SKILL.md) | `/git-workflow` | Guided Git workflow: branching, commits, PRs, and conflict resolution |
| [code-review](./skills/code-review/SKILL.md) | `/code-review` | Thorough code review covering correctness, security, performance, and style |
| [english-humanizer](./skills/english-humanizer/SKILL.md) | `/humanize` | Humanize the text |

## Skill Format

Each skill is a Markdown file with a YAML front-matter block followed by the prompt body, following the [skills.sh](https://skills.sh) spec:

```markdown
---
name: skill-name
description: >
  What the skill does and when to trigger it.
  TRIGGER when the user writes /skill-name.
triggers:
  - /skill-name
---

Skill prompt body goes here…
```

## Adding New Skills

1. Create a new folder in the root of `skills/`. The folder name must strictly match your skill's `name` in the YAML frontmatter.
2. Add a `SKILL.md` file in the root of the new folder. Ensure it contains a `name` (max 64 chars) and `description` (non-empty, max 1024 chars) inside the YAML frontmatter.
3. If needed, add a `resources/` folder in the root of the new folder and populate it with the necessary files.
4. Add a row to the **Available Skills** table in this README.
5. Test it locally by placing the folder from `skills/` in `~/.claude/skills/` or `~/.agents/skills/`.
