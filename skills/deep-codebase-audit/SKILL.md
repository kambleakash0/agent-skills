---
name: deep-codebase-audit
description: Find deepening opportunities in a codebase, surfacing architectural friction and proposing refactors that turn shallow modules into deep ones. Use when the user wants to improve architecture, make a codebase more testable, consolidate tightly-coupled modules, or make it safer for AI agents to navigate and change.
metadata:
  author: kambleakash0
  version: 2.0.0
triggers:
  - /deep-codebase-audit
  - /deep-audit
  - /codebase-audit
---

# Deep Codebase Audit

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability, AI-navigability, and leverage.

References for this skill are in the `references/` folder:

- [GLOSSARY.md](references/GLOSSARY.md) — vocabulary to use in every suggestion
- [DEPTH-GUIDE.md](references/DEPTH-GUIDE.md) — how to classify dependencies and test across seams
- [INTERFACES.md](references/INTERFACES.md) — how to explore alternative interfaces

## When to Use

Use this skill when:

- The user says the codebase feels messy, hard to change, or "not ready for AI".
- You want to improve testability and make future TDD or autonomous agent work more effective.
- You're about to invest heavily in AI-driven changes and want to reduce risk first.

Do **not** use this skill when the user just wants to ship a small feature — use `/incremental-tdd` instead.

## Glossary

Use these terms exactly in every suggestion. Consistent language is the point — don't drift into "component," "service," "API," or "boundary." Full definitions in [GLOSSARY.md](references/GLOSSARY.md).

- **Module** — anything with an interface and an implementation (function, class, package, slice).
- **Interface** — everything a caller must know to use the module: types, invariants, error modes, ordering, config. Not just the type signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. (Use this, not "boundary.")
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** — what callers get from depth.
- **Locality** — what maintainers get from depth: change, bugs, knowledge concentrated in one place.

Key principles (see [GLOSSARY.md](references/GLOSSARY.md) for the full list):

- **Deletion test**: imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.**
- **One adapter = hypothetical seam. Two adapters = real seam.**

## Process

### 0. Read context first

Before exploring anything, check whether the project has:

- A domain glossary (`CONTEXT.md`, `docs/glossary.md`, or similar) — read it and use its vocabulary when naming modules and seams.
- Architecture Decision Records (`docs/adr/` or similar) — note any decisions that constrain or inform the areas you'll explore.

If neither exists, proceed without them. Do not create them yet.

### 1. Explore

Use the Agent tool with `subagent_type=Explore` to walk the codebase organically. Don't follow a rigid checklist — explore from natural entry points (main app, top-level routes, CLI commands, or areas the user flags) and note where you experience friction:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity in callers, or just eliminate it? A "yes, concentrates" is the signal you want.

Ask the user upfront what "better architecture" means in this context — easier AI changes, better tests, less cognitive load, fewer regressions — and what constraints apply (time horizon, tech stack, team experience). Let that shape what you look for.

### 2. Present candidates

Present a numbered list of deepening opportunities. For each candidate:

- **Files** — which files/modules are involved
- **Problem** — why the current architecture is causing friction
- **Solution** — plain-English description of what would change
- **Benefits** — explained in terms of locality and leverage, and how tests would improve

Use the project's domain vocabulary for names (e.g. "the Order intake module" if `CONTEXT.md` defines "Order"), and use [GLOSSARY.md](references/GLOSSARY.md) vocabulary for the architecture itself (module, seam, depth, leverage — not "service", "boundary", "API").

**ADR conflicts**: if a candidate contradicts an existing ADR, only surface it when the friction is real enough to warrant revisiting. Mark it clearly (e.g. _"contradicts ADR-0007 — but worth reopening because…"_). Don't list every theoretical refactor an ADR forbids.

Do **not** propose interfaces yet. Ask the user: "Which of these would you like to explore?"

### 3. Grilling loop

Once the user picks a candidate, drop into a grilling conversation. Walk the design tree with them — constraints, dependencies, the shape of the deepened module, what sits behind the seam, what tests survive.

Side effects happen inline as decisions crystallize:

- **Naming a deepened module after a concept not in the domain glossary?** Add the term to `CONTEXT.md` (create it lazily if it doesn't exist).
- **Sharpening a fuzzy term mid-conversation?** Update `CONTEXT.md` right there.
- **User rejects a candidate with a load-bearing reason?** Offer to record it as an ADR: _"Want me to record this so future architecture reviews don't re-suggest it?"_ Only offer when the reason is durable — skip "not worth it right now" or self-evident reasons.
- **Want to explore alternative interfaces for the deepened module?** See [INTERFACES.md](references/INTERFACES.md).

For dependency classification and testing strategy across the seam, see [DEPTH-GUIDE.md](references/DEPTH-GUIDE.md).

## Behavior and Rules

1. **Stay descriptive before prescriptive.** Spend time describing what the codebase feels like to work with before jumping to solutions.
2. **Prioritize leverage.** Focus on changes that will make many future changes easier, not micro-tweaks.
3. **Think in deep modules.** Whenever you see scattered logic, ask "what deep module could own this?".
4. **Respect constraints.** If the user says they only have time for quick wins, adjust recommendations accordingly.
5. **Avoid framework dogma.** Use the existing language and framework idioms; don't reinvent the project around a new architecture trend.
6. **Write for humans and agents.** Explanations and recommendations should be understandable both to human engineers and future AI agents reading the report.
7. **Use locked vocabulary.** Every suggestion uses terms from [GLOSSARY.md](references/GLOSSARY.md). Never substitute "component," "service," "API," or "boundary."

## Example

**User:**
"This TypeScript backend feels impossible to navigate and test. Make it more AI-friendly."

**You (high level):**

1. Check for `CONTEXT.md` and any ADRs. Read them if present.
2. Ask what "AI-friendly" means to them (e.g., safer autonomous changes, fewer regressions) and what constraints exist.
3. Explore from main entrypoints, mapping major modules and noting shallow, scattered logic. Apply the deletion test to suspects.
4. Present 3–5 numbered deepening candidates with files, problem, solution, benefits.
5. Ask which one to explore. Drop into grilling on that candidate.
6. Once design crystallizes, see [INTERFACES.md](references/INTERFACES.md) for parallel interface exploration.
7. Recommend follow-up skills: `/incremental-tdd` for test-driven refactors, `/spec-writer` and `/slice-the-spec` for larger architectural initiatives.
