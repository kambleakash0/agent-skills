---
name: deep-codebase-audit
description: Explore a codebase like an AI would, surface architectural friction, and propose deep-module changes that improve testability and agent-friendliness.
metadata:
  author: kambleakash0
  version: 1.0.0
triggers:
  - /deep-codebase-audit
  - /deep-audit
  - /codebase-audit
---

# Improve Codebase Architecture

This skill explores a codebase the way an AI agent experiences it: by reading files, following references, and trying to understand how to make safe changes. It surfaces architectural friction (shallow modules, tangled dependencies, missing seams) and suggests **deep-module** improvements that make the codebase easier to test, reason about, and modify with AI.

References for this skill are kept in [references.md](references/references.md)

## When to Use

Use this skill when:

- The user says the codebase feels messy, hard to change, or “not ready for AI”.
- You want to improve testability and make future TDD or autonomous agents more effective.
- You’re about to invest heavily in AI‑driven changes and want to reduce risk first.

If the user just wants to ship a small feature, consider using `/tdd` or similar execution skills instead.

## Overall Approach

The goal is **not** to apply a rigid checklist, but to explore organically and report back what hurts and where to deepen modules.

1. **Clarify goals and constraints**

   - Ask what “better architecture” means in this context: easier AI changes, better tests, less cognitive load, fewer regressions, etc.
   - Ask about constraints: tech stack, team experience, time horizon (quick wins vs deeper re‑architecture).

2. **Map the codebase like an AI**

   - Start from natural entry points: main app, top‑level routes, CLI commands, or “hot” areas the user mentions.
   - Follow imports and references to build a mental map of major modules and how they relate.
   - Notice where behavior is spread across many shallow modules versus encapsulated in a few deep ones.

3. **Identify architectural friction**

   Look for and note:

   - **Shallow modules:** Lots of tiny helpers that do very little each, forcing callers (and AI) to stitch behavior together.
   - **Cross‑cutting concerns** scattered everywhere (logging, auth, validation) instead of grouped behind boundaries.
   - **Hidden contracts:** Implicit assumptions encoded in call order, parameter combinations, or shared mutable state.
   - **Hard‑to‑test areas:** Code that touches many systems at once, with no obvious narrow seam to test.

4. **Spot opportunities for deep modules**

   - From the friction you find, propose **deep module seams**: places where you could introduce or strengthen modules with simple APIs and rich internals.
   - Think in terms of “lumps of responsibility” an AI could own: “billing calculator”, “metrics aggregator”, “notification scheduler”, etc.
   - For each candidate module, sketch what a clean, stable interface might look like and what behavior it would hide.

5. **Evaluate AI‑friendliness**

   For each key area:

   - How easy would it be for an AI (or new human) to find the right module and call it safely?
   - Is there a clear public interface and a matching set of tests?
   - Does the current shape encourage **progressive disclosure of complexity**: simple on the outside, complex only when you dive in?

6. **Propose practical refactors**

   - Turn your findings into **concrete, incremental refactors**: deepen a module, extract a seam, consolidate duplicated logic, wrap a messy call pattern in a single function.
   - Prioritize changes that will unlock better tests, clearer interfaces, or safer AI modifications.
   - Suggest a small number of vertical slices (e.g., “make the metrics subsystem deep‑module‑friendly”) instead of a total rewrite.

7. **Summarize and hand off**

   - Write a short architecture report: current pain points, candidate deep modules, suggested refactors, and expected benefits for AI and humans.
   - Recommend follow‑up skills: `/tdd` for test‑driven refactors, `/spec-writer` and `/slice-the-spec` for larger architectural initiatives.

## Behavior and Rules

1. **Stay descriptive before prescriptive.** Spend time describing what the codebase feels like to work with before jumping to solutions.
2. **Prioritize leverage.** Focus on changes that will make many future changes easier, not micro‑tweaks.
3. **Think in deep modules.** Whenever you see scattered logic, ask “what deep module could own this?”.
4. **Respect constraints.** If the user says they only have time for quick wins, adjust recommendations accordingly.
5. **Avoid framework dogma.** Use the existing language and framework idioms; don’t reinvent the project around a new architecture trend.
6. **Write for humans and agents.** Explanations and recommendations should be understandable both to human engineers and future AI agents reading the report.

## Example

**User:**
“This Typescript backend feels impossible to navigate and test. Make it more AI‑friendly.”

**You (high level):**

1. Ask what “AI‑friendly” means to them (e.g., safer autonomous changes, fewer regressions).
2. Explore the codebase from the main entrypoints, mapping major modules and noting shallow, scattered logic.
3. Identify friction: cross‑cutting concerns tangled through routes, no clear deep modules for billing, notifications, or metrics.
4. Propose 3–5 deep module candidates with sketched interfaces and concrete refactors to get there.
5. Summarize in a short report and suggest follow‑up TDD work to implement the refactors safely.
