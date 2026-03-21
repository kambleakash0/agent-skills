# Reference: Improving Codebase Architecture for AI

This skill is inspired by long‑standing software design ideas (especially **deep modules**) applied to AI‑driven development. The goal is to make codebases easier to navigate, test, and change for both humans and AI agents.

## Key Ideas

### Deep Modules

A deep module has:

- A **simple, stable interface** at the top.
- A **rich, complex implementation** hidden inside.
- A clear, domain‑meaningful responsibility (“payments engine”, “metrics aggregator”).

Deep modules make AI’s job easier because:

- The agent only needs to understand a small set of well‑named entrypoints.
- Most changes happen inside one place, protected by tests.
- You can reason about the system in a few “lumps” instead of many tiny functions.

Shallow modules, by contrast, expose many small pieces that barely do anything. They force callers (including AI) to mentally assemble behavior from low‑level steps, which is harder to test and easier to break.

### Progressive Disclosure of Complexity

Good architecture lets you understand the system in layers:

1. At the top: **interfaces** that describe what each module does.
2. Below that: enough detail to tweak or debug behavior.
3. Deep inside: implementation details that almost nobody needs to think about day‑to‑day.

AI benefits from this because it can:

- Discover the right module by reading clear interfaces.
- Make localized changes without understanding the entire codebase.
- Rely on tests to validate behavior while safely refactoring internals.

### AI as a New Starter

An AI agent experiences your codebase like a new developer:

- It has to build a mental map from file names, folder structure, and exports.
- It struggles when behavior is spread across many shallow modules with implicit contracts.
- It performs better when there are obvious seams, clear interfaces, and good tests.

Designing for AI quality is very similar to designing for onboarding new humans quickly.

## What This Skill Looks For

When exploring a codebase, the skill pays special attention to:

- Areas where **multiple concerns are tangled together** (e.g., business logic, I/O, and formatting in one function).
- Long chains of calls that must be made in a specific order for things to work.
- Places where it’s hard to introduce tests without hitting a huge surface area at once.
- Repeated patterns that suggest a missing deep module (e.g., copy‑pasted query‑and‑transform logic).

It then suggests refactors that:

- Introduce or deepen modules with clearer boundaries.
- Move logic towards the modules that “own” the corresponding domain concepts.
- Create test seams where AI and humans can safely experiment.

## How to Use the Output

You can use the architecture report to:

- Plan a **short refactor phase** before large AI‑driven changes.
- Identify **modules worth protecting with TDD** and strong tests.
- Decide where to direct autonomous agents (give them deep modules to own, not entire subsystems).
- Educate your team on how to design for AI and new starters at the same time.
