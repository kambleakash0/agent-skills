# RESOURCES-FORMAT.md

Defines the format for `RESOURCES.md` — the curated source library for this teaching workspace.

## Purpose

`RESOURCES.md` is the list of trusted, annotated sources the agent draws on when building lessons. Knowledge in lessons must come from here, not from parametric memory. Communities listed here are where the user can acquire wisdom through real-world practice.

## When to create

Start building `RESOURCES.md` before writing the first lesson. If no good sources exist yet, create a `## Gaps` section and note what's missing — this drives the next round of research.

## Template

```md
# {Topic} Resources

## Knowledge

- [{Source type}: _{Title}_ — {Author or publisher}]({url})
  {One sentence: what it covers. One sentence: when to reach for it.}

## Wisdom (Communities)

- [{Community name}]({url})
  {One sentence: what kind of practitioner is here. One sentence: when to send the user here.}

## Gaps

- {An area the mission requires but no good source has been found yet}
```

## Example entries

```md
## Knowledge

- [Book: _The Science and Practice of Strength Training_ — Zatsiorsky & Kraemer](https://example.com)
  Foundational text on training adaptation and programming. Use for: anything related to periodisation, recovery, and intensity zones.

- [Article: "How Much Should I Train?" — Greg Nuckols (Stronger By Science)](https://example.com)
  Evidence-based review of weekly volume landmarks per muscle group. Use for: deciding how many sets per muscle per week.

## Wisdom (Communities)

- [r/weightroom](https://reddit.com/r/weightroom)
  High-signal subreddit with strong moderation against unsourced claims. Use for: programme critique and plateau troubleshooting.
```

## Rules

- **High-trust only.** Prefer primary sources, recognised practitioners, peer-reviewed work, and communities with real moderation. If a resource is marketing dressed as education, leave it out.
- **Annotate every entry.** A bare link is useless in two months. Add what it covers and when to reach for it — two sentences maximum.
- **Group as Knowledge or Wisdom.** Mirrors the philosophy in [SKILL.md](../SKILL.md). A resource can appear in only one group.
- **Surface gaps explicitly.** If the mission requires coverage of an area and no good source exists yet, write it in `## Gaps`. Don't pretend the gap isn't there.
- **Prune when sources prove wrong or shallow.** Remove them outright rather than leaving a buried warning. Five sharp sources beat thirty mediocre ones.
- **Record community opt-outs.** If the user has said they don't want to join communities, note it here so future sessions don't keep proposing them.
