---
name: spec-writer
description: Create a comprehensive Product Requirements Document from conversation and repo context. Use when the user wants a PRD, product spec, feature requirements, or similar documentation.
metadata:
  author: kambleakash0
  version: 1.0.0
triggers:
  - /spec
  - /spec-writer
---

# Write a Product Requirements Document

This skill turns a clarified idea into a **structured PRD** using conversation and repository context. It assumes that major ambiguities have already been grilled out (for example with `/grill-me`), but it can also perform its own lightweight clarification when needed.

## When to Use

Use this skill when the user:

- Asks to "write a PRD", "product spec", "requirements doc", "feature specification", or similar.
- Wants to document a new feature, change, or system in a structured way before implementation.
- Has already clarified the idea and now needs a single, coherent document you can file as an issue, share with stakeholders, or feed into `/prd-to-issues`.

If the idea is still fuzzy or underspecified, recommend using `/grill-me` first and then come back to this skill.

## Overall Workflow

You may skip or compress steps that are clearly already complete (for example, if the user pastes a detailed problem statement or user story list).

1. **Collect a rich problem description**
   - Ask the user for a long, detailed description of:
     - The problem they want to solve
     - Who it is for
     - Why it matters now
     - Any initial solution ideas or constraints they already have
   - Encourage them to paste existing context (docs, tickets, research) instead of re‑typing everything.

2. **Explore the repo and verify assumptions**
   - Inspect the codebase to understand current behavior, relevant modules, data models, and existing APIs.
   - Cross‑check the user’s assertions: note where the repo agrees, disagrees, or is silent, and adjust your understanding accordingly.
   - Capture any repo‑grounded facts that will matter for scope, edge cases, or implementation constraints.

3. **Consider alternative approaches**
   - Ask the user whether they have considered other solution options or design directions.
   - Briefly outline 2–3 plausible approaches, with trade‑offs (complexity, time‑to‑ship, risk, UX impact).
   - Confirm which approach you should treat as the primary one for this PRD.

4. **Deep implementation interview (if needed)**
   - If the requirements still feel high‑level, interview the user about how they want it to behave in detail: flows, states, inputs/outputs, failure modes, permissions, and performance expectations.
   - Where answers depend on existing behavior, prefer inspecting the repo over guessing.
   - Make assumptions explicit and ask for confirmation.

5. **Hammer out exact scope**
   - Work out what will be **in scope** and explicitly list what is **out of scope** for this PRD (e.g., deferred edge cases, nice‑to‑haves, follow‑ups).
   - Clarify the target release slice (MVP vs full feature) and any sequencing or phase‑1/phase‑2 distinctions.

6. **Sketch modules and architecture (lightweight)**
   - Identify the major modules, services, or components that will be created or modified.
   - Call out opportunities to extract deep, testable modules that can be validated in isolation (good for later TDD or `/tdd` usage).

7. **Write the PRD using a structured template**
   - Draft a complete PRD with clearly labeled sections (see template below).
   - Use plain, precise language suitable for engineers, PMs, and designers.

8. **File it where it belongs (optional)**
   - If appropriate, format the PRD as a GitHub issue or markdown file according to the repo’s conventions.
   - Include labels, owners, and links to related issues or docs if the context provides them.

## PRD Template

Use and adapt this structure. You can omit sections that are clearly irrelevant, but err on the side of including them.

### 1. Summary

- 2–3 sentences describing **what** we are building and **why**.
- Include the target user segment and the primary outcome we want.

### 2. Problem Statement

- Current pain or gap in the product.
- Who is experiencing it and in what context.
- Evidence (metrics, anecdotes, user research, support tickets) if available.

### 3. Goals and Non‑Goals

- **Goals:** A short, numbered list of what success looks like.
- **Non‑Goals:** Explicitly list what this PRD will not attempt to do.

### 4. User Stories

A **long, numbered list** of user stories that captures all important behavior.

Each user story should follow the format:

1. As an \<actor\>, I want \<feature\>, so that \<benefit\>
   - Include acceptance notes or clarifications inline if helpful.

Aim for extensive coverage: core flows, edge cases, permission variations, and failure scenarios.

### 5. Functional Requirements

- Detailed description of expected behavior for each major area or flow.
- System states, transitions, and how different actors interact with the feature.
- Validation rules, error handling, retries, rate limits, and constraints that matter for correctness.

### 6. Non‑Functional Requirements

- Performance, scalability, and latency expectations where relevant.
- Reliability, availability, and degradation behavior.
- Security, privacy, and compliance considerations if applicable.

### 7. Implementation Notes and Architecture

- High‑level architecture or component diagram in text form.
- List of modules/services to change or create, and how they interact.
- Notes that tie back to the current codebase (key classes, endpoints, tables).

### 8. Out of Scope

- Explicitly list features, flows, user types, or edge cases that will **not** be addressed in this PRD.
- Mention likely follow‑ups or future iterations, if known.

### 9. Risks and Open Questions

- Known risks: technical, product, UX, or organizational.
- Open questions that must be resolved before implementation or rollout.
- Any assumptions that feel especially fragile.

### 10. Success Metrics

- How we will know this work is successful (input and output metrics).
- If precise numbers are not yet available, describe directional expectations (e.g., “meaningful reduction in support tickets for X”).

## Behavior and Rules

1. Favor structure over prose walls: break content into clear sections and numbered lists.
2. Use repo facts where possible; do not invent APIs or data models when you can inspect them.
3. If the user pushes for speed over thoroughness, confirm which sections they want you to prioritize and keep the rest minimal.
4. If requirements are too vague, ask 1–3 targeted clarification questions instead of guessing.
5. Aim for a document that an engineer could implement with minimal back‑and‑forth, not a marketing one‑pager.
