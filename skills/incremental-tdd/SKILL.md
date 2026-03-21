---
name: incremental-tdd
description: Test-driven development with a strict red-green-refactor loop, vertical slices, and deep modules. Use to build features or fix bugs using TDD.
metadata:
  author: kambleakash0
  version: 1.0.0
triggers:
  - /incremental-tdd
  - /tdd
---

# Test-Driven Development (Red-Green-Refactor)

This skill forces you to work in **tight TDD loops**: one failing test, one implementation, then refactor. It prefers vertical slices and **deep modules** so tests stay honest, stable, and focused on real behavior instead of implementation details.

This skill comes with extra documents you can reference for philosophy and examples:

- [deep-modules.md](references/deep-modules.md) – why deep modules make AI‑driven TDD easier and safer.
- [refactoring.md](references/refactoring.md) – patterns for safe refactors.
- [interface-design.md](assets/interface-design.md) – how to design interfaces for TDD.
- [mocking.md](assets/mocking.md) – how and when to mock without lying to yourself.
- [tests.md](assets/tests.md) – how and when to mock without lying to yourself.

When you need guidance on design or refactoring, **open and read these files** instead of guessing.

## When to Use

Use this skill when the user:

- Wants to build a feature or fix a bug **using TDD**.
- Mentions “red‑green‑refactor”, “test‑first”, or “write the tests first”.
- Wants honest integration or module‑level tests that drive design rather than brittle unit tests.
- Is running longer “Ralph” loops or autonomous agents and wants higher‑quality changes.

If the requirements are unclear, suggest using `/grill-me` and `/spec-writer` first, then come back here for execution.

## Overall Workflow

You can compress steps when context is obvious, but keep the **red → green → refactor** discipline.

1. **Clarify behavior and interfaces**

   - Confirm what behavior should exist **from the outside**: which inputs, outputs, and observable effects matter.
   - Identify or design the **interfaces** you’ll use to expose that behavior (public functions, handlers, endpoints, etc.).
   - Prefer deep modules: fewer, larger modules with thin, stable interfaces on top.
   - If needed, open [deep-modules.md](references/deep-modules.md) and adjust your interface design to match that philosophy.

2. **Choose the next vertical slice**

   - From the PRD or problem description, pick a **thin vertical slice**: a single behavior that exercises a real path through the system.
   - Avoid purely horizontal slices like “set up the DB table” or “write all the UI” in isolation.
   - Confirm with the user (or with comments) what this slice should prove when finished.

3. **Red: write one failing test**

   - Write **one** test that expresses the desired behavior of the slice using the chosen interface.
   - Keep the test as close as possible to “how a real caller would use this”, even when testing at module level.
   - Prefer real collaborators or thin fakes over heavy mocking. When in doubt, consult [mocking.md](assets/mocking.md).
   - Run the test and confirm it fails for the expected reason.

4. **Green: write the minimal implementation**

   - Open the relevant production files and write **the simplest implementation** that makes the test pass.
   - Do not over‑generalize, add unused parameters, or implement future behavior that isn’t tested yet.
   - Re‑run the tests and make sure the new test passes and the suite remains green.

5. **Refactor: improve design safely**

   - With tests green, look for duplication, awkward interfaces, or leaky abstractions.
   - Apply small refactors while **running tests frequently** to ensure behavior stays the same.
   - Use [deep-modules.md](references/deep-modules.md) and [refactoring.md](references/refactoring.md) as guides for better boundaries and deeper modules.
   - Stop once the design is “good enough” for now; you can refactor again after future slices.

6. **Repeat the loop**

   - Pick the next slice or behavior, then repeat **Red → Green → Refactor**.
   - Each cycle should be small enough that you can understand and reverse it if it goes wrong.
   - As you go, keep tests focused on behavior and avoid coupling them to incidental implementation details.

## Behavior and Rules

1. **Always respect the loop.** Never write large chunks of production code without a failing test first.
2. **One test at a time.** Do not generate dozens of tests at once. Add tests incrementally as behavior demands.
3. **Prefer higher‑level tests.** Where reasonable, prefer integration or module‑level tests that exercise real flows.
4. **Guard against dishonest tests.** Avoid tests that would pass even if the real behavior were broken; check for obvious false positives.
5. **Be willing to change your own code.** Treat previously written code as disposable if a better design emerges; rely on tests for safety.
6. **Use the attached docs.** When you’re unsure about module shape, refactoring, or mocking, open the linked markdown files instead of hallucinating patterns.

## Example Flow

**User:**
“Implement weekly admin summary emails using TDD. I already have the PRD and issues.”

**You (high level):**

1. Skim the PRD and issues, identify the first vertical slice (e.g., “compute weekly metrics for a single team”).
2. Design or confirm the module interface responsible for computing metrics; check [deep-modules.md](references/deep-modules.md) for guidance.
3. Write a single failing test for “given last week’s events, compute the summary object for team X”.
4. Implement the minimal code to make that test pass, then refactor the module while keeping tests green.
5. Repeat for additional behaviors (multiple teams, filters, performance constraints, error handling), always via red‑green‑refactor.
