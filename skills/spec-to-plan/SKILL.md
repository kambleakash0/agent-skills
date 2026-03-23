---
name: spec-to-plan
description: Turn a PRD into a multi-phase implementation plan using tracer-bullet vertical slices.
metadata:
  author: kambleakash0
  version: 1.0.0
triggers:
  - /spec-to-plan
  - /spec-plan
---

# Turn a PRD into an Implementation Plan

This skill translates **what** needs to be built (the PRD) into **how** it will be built (a phased implementation plan). It breaks the PRD into tracer-bullet vertical slices, orders them into phases, and writes the result as a Markdown plan file in `./plans/`.

## When to Use

Use this skill when:

- You already have a PRD or equivalent spec and now need a concrete implementation plan.
- You want to think in **phases**, not just issues: what gets built first, what can be deferred, and how slices build on each other.
- You intend to drive downstream work (e.g. `/slice-the-spec`, `/incremental-tdd`) from a single, durable planning document.

If the requirements are still fuzzy, use `/grill-me` and `/spec-writer` first.

## Workflow

You can compress steps if the context is already clear, but keep the core structure: PRD → slices → phases → plan file.

1. **Confirm the PRD is in context**

   - Ensure the PRD is available in the conversation or repo.
   - If not, ask the user to paste it or point you to the file path or issue.
   - Skim for: goals, user stories, functional requirements, non-goals, and constraints.

2. **Explore the codebase (light)**

   - If you have not already explored the codebase for this feature, do a quick pass to understand major modules, integration layers, and architectural patterns.
   - Note any constraints that will affect slicing (e.g. existing routing, data models, auth, third-party boundaries).

3. **Identify durable architectural decisions**

   Before slicing, identify decisions that are unlikely to change across phases and are worth calling out up front:

   - Route structures / URL patterns.
   - Database schema shape and key tables.
   - Core data models and domain concepts.
   - Authentication / authorization approach.
   - Third‑party service boundaries and integration points.

   These go into the **Architectural decisions** section of the plan so every phase can reference them.

4. **Draft vertical slices (tracer bullets)**

   - Break the PRD into **tracer-bullet** slices: thin, end‑to‑end pieces that cut through all relevant layers (schema, domain, API, UI, tests).
   - Apply the vertical-slice rules:
     - Each slice delivers a narrow but **complete** path through every necessary layer.
     - Each slice is demoable or verifiable on its own.
     - Prefer **many thin slices** over a few thick ones.
     - Do **not** include brittle implementation details (file names, specific function signatures) that are likely to change.
     - Do include durable decisions like route paths, schema shapes, and model names.

5. **Group slices into phases**

   - Order slices into 2–5 phases that make sense from a risk and value perspective.
   - Earlier phases should:
     - Validate the riskiest assumptions.
     - Deliver something demoable quickly.
     - Set up patterns that later phases can follow.
   - Later phases can expand coverage, add polish, or handle edge cases and scale.

6. **Quiz the user**

   - Present the proposed phases as a numbered list.
     For each phase, show:
     - **Title**: short, descriptive name.
     - **User stories covered**: which PRD stories this phase delivers.
   - Ask:
     - Does the **granularity** feel right (too coarse / too fine)?
     - Are phases in the right **order**?
     - Should any phases be merged or split?
   - Refine until the user approves the breakdown.

7. **Write the plan file**

   - Ensure `./plans/` exists; if not, create it.
   - Name the plan file after the feature (e.g. `./plans/weekly-admin-summary-email.md`).
   - Use and adapt the template below, filling in architectural decisions and one section per phase.

## Plan Template

Use this as the default Markdown structure.

```markdown
# Plan: <Feature Name>
> Source PRD: <brief identifier or link>

## Architectural decisions

Durable decisions that apply across all phases:

- **Routes:** ...
- **Schema:** ...
- **Key models:** ...
- **Auth:** ...
- **Third-party services:** ...
- (add/remove items as appropriate)

## Phases

### Phase 1: <Title>

#### What to build

A concise description of this vertical slice. Describe the **end-to-end behavior**, not layer-by-layer implementation.[1]

- Which user stories this phase covers.
- Which layers it will touch (data, domain, API, UI, background jobs, etc.).[1]

#### Acceptance criteria

- Criterion 1
- Criterion 2
- Criterion 3

***

### Phase 2: <Title>

#### What to build

...

#### Acceptance criteria

- ...

<!-- Repeat for each phase -->
```

## Behavior and Rules

1. Stay at the plan level. Do not drop into detailed implementation plans or specific file edits; that is work for execution skills like /tdd.
2. Think in risk and value. Earlier phases should de-risk core architecture and ship something demoable quickly.
3. Keep slices vertical. Avoid phases that are purely “set up database” or “build UI” without delivering end-to-end value.
4. Make decisions explicit. Put durable architectural decisions in the plan header so downstream skills and humans can reuse them.
5. Write for future you and agents. Plans should be readable, skimmable, and easy to hand to another engineer or AI agent as a starting point.
