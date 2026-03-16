# agent-skills

A personal collection of Claude Code agent skills, built to be submitted to the [skills.sh](https://skills.sh) catalogue.

## Installation

Install all skills at once via [skills.sh](https://skills.sh):

```bash
npx skills.sh install kambleakash0/agent-skills
```

Or clone manually into your Claude skills directory:

```bash
git clone https://github.com/kambleakash0/agent-skills .claude/skills/agent-skills
```

## Available Skills

| Skill | Command | Description |
|-------|---------|-------------|
| [git-workflow](./git-workflow.md) | `/git-workflow` | Guided Git workflow: branching, commits, PRs, and conflict resolution |
| [code-review](./code-review.md) | `/code-review` | Thorough code review covering correctness, security, performance, and style |

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

1. Create a new `.md` file in the root of this repo using the format above.
2. Add a row to the **Available Skills** table in this README.
3. Test it locally by placing the file in `.claude/skills/agent-skills/`.
