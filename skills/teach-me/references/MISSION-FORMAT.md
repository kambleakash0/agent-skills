# MISSION-FORMAT.md

Defines the format for `MISSION.md` — the root document of the teaching workspace.

## Purpose

`MISSION.md` captures the concrete reason the user is learning this topic. Every teaching decision — what to teach next, which resources to surface, which exercises to design — should trace back to it. A workspace without a mission produces technically correct lessons that feel irrelevant to the user.

## When to create

Create `MISSION.md` before writing any lesson. If the user is vague about why they want to learn, interview them until you have a concrete, real-world goal. Do not start teaching until this file exists.

## Template

```md
# Mission: {Topic}

## Why
{1–3 sentences. The concrete real-world outcome the user is chasing. What changes in their life or work when they have this skill? Avoid abstract framings like "to understand X" — push for the underlying goal.}

## Success looks like
- {A specific, observable thing the user will be able to do}
- {Another specific outcome}

## Constraints
- {Time, budget, prior commitments, learning style preferences, anything that bounds the approach}

## Out of scope
- {Adjacent topics the user has explicitly set aside for now}
```

## Rules

- **One mission per workspace.** If the user wants to learn two unrelated things, that is two separate workspaces.
- **Concrete over abstract.** "Ship a Rust CLI tool to my team by end of quarter" beats "learn Rust." "Run a half marathon in October" beats "get fitter." The concrete goal tells you what to teach and what to skip.
- **Push back on vagueness.** If the user can't articulate why they want to learn this, interview them before writing anything. A mission built on a vague goal is worse than no mission — it gives false direction.
- **Revise when reality shifts.** Goals change. When the user's reason for learning moves, update this file immediately. Don't let a stale mission quietly steer the workspace in the wrong direction.
- **Keep it short.** If `MISSION.md` runs longer than a screen, it has stopped being a compass and started being a project plan. Cut it back.
