---
name: slice-the-spec
description: Turn a PRD into a Kanban-ready backlog of vertically sliced issues, with clear dependencies and HITL/AFK flags.
metadata:
  author: kambleakash0
  version: 1.0.0
triggers:
  - /slice-the-spec
  - /slice-spec
---

# Turn a PRD into Issues

This skill takes a clarified PRD and turns it into a **small, sharp backlog** of vertically sliced GitHub issues. Each issue should be an independently grabbable “tracer bullet” that cuts through all relevant layers end‑to‑end, flushing out unknown unknowns as early as possible.

## When to Use

Use this skill when the user:

- Has a PRD or similar spec (possibly created via `/spec-writer`) and now wants concrete issues.
- Wants to turn “destination” docs into a Kanban board of tasks.
- Needs to break work down so multiple engineers or agents can work in parallel without stepping on each other.

If there is no PRD yet or the requirements are fuzzy, suggest using `/grill-me` and `/spec-writer` first.

## Concepts

- **Vertical slice / tracer bullet:** A thin, end‑to‑end piece of functionality that goes through all necessary layers (data, domain, API, UI, etc.), not just one layer in isolation.
- **HITL issue:** Requires Human‑In‑The‑Loop decisions (design review, stakeholder sign‑off, risky refactor, etc.).
- **AFK issue:** “Away‑From‑Keyboard” for the human; safe enough for an autonomous agent to implement and merge without human intervention.

Prefer AFK slices where possible, but mark HITL clearly where human judgment is essential.

## Workflow

You may compress or skip steps if the context already provides the answer (e.g., the PRD is already loaded and clearly scoped).

1. **Locate and understand the PRD**
   - Find the PRD from the conversation or repository (issue, doc, file).
   - Skim to understand: goals, user stories, functional requirements, and explicit non‑goals.
   - If multiple PRDs are present, confirm with the user which one to use.

2. **Explore the codebase**
   - Inspect relevant parts of the repo to understand current architecture, major modules, and likely integration points.
   - Note any existing patterns you should respect (e.g., existing feature flags, background jobs, notification systems).

3. **Draft vertical slices (tracer bullets)**
   - Break the PRD into a **small set** of vertical slices, each of which delivers end‑to‑end value and exercises multiple layers of the system.
   - Avoid horizontal slices like “set up database tables” or “build all UI components” unless truly necessary; fold those into end‑to‑end slices instead.
   - For each slice, decide whether it is HITL or AFK, preferring AFK when risk is low.

4. **Define issue structure and dependencies**
   For each slice, define:

   - **Title:** Short, descriptive, directly tied to user value.
   - **Type:** HITL or AFK.
   - **Description:** What this issue will deliver, referencing specific user stories and PRD sections.
   - **Acceptance criteria:** Clear, testable criteria including edge cases.
   - **Blocked by:** Which other slices must be completed first (if any).

   Identify at least one **unblocked** issue that can be started immediately.

5. **Quiz the user and iterate**
   Present the proposed breakdown as a numbered list of slices with:

   - Title
   - Type (HITL/AFK)
   - Blocked by
   - User stories covered

   Ask the user:

   - Does the **granularity** feel right (too coarse, too fine)?
   - Are **dependencies** correct?
   - Should any slices be **merged or split**?
   - Are the right slices marked as HITL vs AFK?

   Refine until the user approves the breakdown.

6. **Generate GitHub‑ready issues**
   - For each approved slice, generate a GitHub‑ready issue body (Markdown) including:
     - Context summary
     - Detailed task description
     - Acceptance criteria
     - Links to the PRD and related issues
     - HITL/AFK flag and any notes for human reviewers
   - Optionally group them into epics or labels if the repo conventions are clear.

## Behavior and Rules

1. Optimize for **few, high‑leverage slices**, not dozens of micro‑issues.
2. Every issue should be implementable by someone who has the PRD and the repo, with **minimal additional clarification**.
3. Prefer vertical slices that “light up” a narrow but real path through the system over broad foundational work that shows no user‑visible change.
4. Always expose and annotate HITL work; do not hide human decisions inside AFK issues.
5. If the PRD is missing critical details, ask a small number of targeted clarification questions instead of guessing, or suggest returning to `/spec-writer`.

## Example

**Input:**
A PRD describing a new weekly summary email feature for team admins, with detailed user stories and requirements.

**You:**

1. Locate the PRD file or issue, skim goals, user stories, and non‑goals.
2. Explore the repo to find existing notification and email infrastructure.
3. Propose 3–5 vertical slices such as:
   - “Engine for computing weekly admin metrics (AFK)”
   - “Admin‑configurable summary email template (HITL)”
   - “Schedule and send weekly summary emails (AFK)”
   - “Admin UI to preview and enable weekly summaries (HITL)”
4. Present these with types, dependencies, and mapped user stories; refine based on the user’s feedback.
5. Emit final GitHub issue bodies for each slice, ready to paste or create via API.
