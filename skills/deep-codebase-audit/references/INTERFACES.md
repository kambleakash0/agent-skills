# Interfaces

How to explore alternative interfaces for a chosen deepening candidate using a parallel sub-agent pattern. Based on "Design It Twice" (Ousterhout) — your first idea is unlikely to be the best one.

Uses the vocabulary in [GLOSSARY.md](GLOSSARY.md) — **module**, **interface**, **seam**, **adapter**, **leverage**, **locality**.

## When to use this

After the grilling loop (Step 3 of the skill) has produced a clear candidate, and before committing to an implementation. Trigger it when:

- The interface shape is genuinely uncertain.
- The user wants to compare options rather than accept the first reasonable idea.
- The dependency category (see [DEPTH-GUIDE.md](DEPTH-GUIDE.md)) makes the seam placement non-obvious.

Skip it for simple in-process deepenings where the interface is obvious — save it for candidates with real design decisions at the seam.

## Process

### 1. Frame the problem space

Before spawning sub-agents, write a user-facing explanation of the problem space for the chosen candidate:

- The constraints any new interface would need to satisfy.
- The dependencies it would rely on, and which category they fall into (see [DEPTH-GUIDE.md](DEPTH-GUIDE.md)).
- A rough illustrative code sketch to ground the constraints — not a proposal, just a way to make the constraints concrete.

Show this to the user, then immediately proceed to Step 2. The user reads and thinks while the sub-agents work in parallel.

### 2. Spawn sub-agents

Spawn 3 or more sub-agents in parallel using the Agent tool. Each must produce a **radically different** interface for the deepened module.

Prompt each sub-agent with a separate technical brief that includes:

- The relevant file paths and coupling details.
- The dependency category from [DEPTH-GUIDE.md](DEPTH-GUIDE.md) and what sits behind the seam.
- The domain vocabulary from `CONTEXT.md` (if it exists) — so the agent names things consistently with the project's language.
- The architecture vocabulary from [GLOSSARY.md](GLOSSARY.md) — so the agent uses module, seam, adapter, leverage, locality consistently.

Give each sub-agent a different design constraint:

- **Sub-agent 1:** "Minimize the interface — aim for 1–3 entry points max. Maximise leverage per entry point."
- **Sub-agent 2:** "Maximise flexibility — support many use cases and future extension points."
- **Sub-agent 3:** "Optimise for the most common caller — make the default case trivial, edge cases possible."
- **Sub-agent 4 (if applicable):** "Design around ports & adapters for the cross-seam dependencies — make the production and test adapters as thin as possible."

Each sub-agent outputs:

1. **Interface** — types, methods, parameters, plus invariants, ordering constraints, and error modes.
2. **Usage example** — how a typical caller uses it; shows whether the interface is actually easy.
3. **What the implementation hides** — the behaviour that moves behind the seam.
4. **Dependency strategy and adapters** — which adapter type (from [DEPTH-GUIDE.md](DEPTH-GUIDE.md)) and what those adapters look like.
5. **Trade-offs** — where leverage is high, where it is thin; what this design makes hard.

### 3. Present and compare

Present designs sequentially so the user can absorb each one. Then compare them in prose by:

- **Depth** — how much leverage does each interface give callers per unit of interface they must learn?
- **Locality** — where does change concentrate? Is the hot path in the module or leaking into callers?
- **Seam placement** — does the seam sit at the right level? Does it match the domain concept or is it too technical?

After comparing, give your own recommendation: which design you think is strongest and why. If elements from different designs would combine well, propose a hybrid. **Be opinionated** — the user wants a strong read, not a menu.

## What makes a good interface

A strong interface:

- Is named after a domain concept (from `CONTEXT.md` or a term you're about to add to it), not an implementation detail.
- Makes the common case simple and the uncommon case possible, not the reverse.
- Hides as much as possible — callers should not need to know about the dependency category, the adapter type, or the internal structure.
- Has a test surface that survives internal refactors — tests describe observable behaviour through the interface, not internal state.

A weak interface:

- Exposes internal seams as part of the external interface.
- Forces callers to assemble multiple methods in a specific order (hidden contract).
- Has too many parameters with non-obvious interactions (shallow by another name).
- Is named after an implementation technology rather than a domain concept ("PostgresHandler", "HttpClientWrapper").
