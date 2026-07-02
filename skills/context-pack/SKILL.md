---
name: context-pack
description: Compact the current conversation into a handoff document so a fresh agent can continue the work in the next session.
metadata:
  author: kambleakash0
  version: 1.0.0
disable-model-invocation: true
triggers:
  - /context-pack
  - /handoff
argument-hint: "What will the next session focus on?"
---

# Context Pack

Summarise the current conversation into a concise handoff document that a fresh agent can read to continue the work without losing context.

## When to Use

Use this skill when:

- The user asks you to create a context pack or handoff document.
- The user wants to continue in a new agent session and needs context carried forward cleanly.
- A task is being handed to a different agent or a different person.

Do **not** use this skill to create project documentation or permanent records — that belongs in PRDs, ADRs, or spec files. This is a transitional document, not an artifact.

## Behavior and Rules

1. **Save to the OS temp directory**, not the current workspace. Use `$TMPDIR`, `/tmp`, or the equivalent for the user's OS. Name the file descriptively: `context-pack-<dash-case-topic>-<YYYYMMDD>.md`.
2. **Don't duplicate existing artifacts.** If a PRD, ADR, plan, spec, issue, commit, or diff already captures something, reference it by file path or URL — don't re-summarise it inline.
3. **Redact sensitive information.** Strip any API keys, passwords, tokens, secrets, or personally identifiable information before writing.
4. **Tailor to the next session.** If the user passed an argument describing what the next session will focus on, use it to weight what you include — surface the most relevant context for that goal and trim what won't matter.
5. **Be concise.** The document should be scannable in under two minutes. Favour bullet points and short paragraphs over prose.

## Document Structure

```md
# Context Pack: {Topic or task}

## Context
{1–3 sentences: what this work is about and why it matters.}

## What was done this session
- {Key decision or action taken}
- {Another decision or action}

## Current state
{Where things stand right now — what is complete, what is in progress, what is blocked.}

## What to do next
- {The most important next step}
- {Other pending steps, in rough priority order}

## Key references
- {Path or URL to relevant PRD, spec, ADR, issue, commit, or diff}
- {Another reference}

## Suggested skills
- `/{skill-name}` — {one sentence on why it's relevant for the next session}
```

## Suggested Skills Section

Always include a suggested skills section. Based on what the next session will involve, recommend the most relevant skills from the workspace. Examples:

- `/incremental-tdd` — if the next session involves implementing something with tests
- `/spec-writer` — if the next session involves formalising requirements
- `/slice-the-spec` — if the next session involves breaking a spec into tasks
- `/deep-codebase-audit` — if the next session involves understanding or improving architecture
- `/teach-me` — if the next session involves learning something new
- `/grill-master` — if the next session involves stress-testing a plan or design