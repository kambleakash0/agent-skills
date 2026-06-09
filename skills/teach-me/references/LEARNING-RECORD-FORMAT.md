# LEARNING-RECORD-FORMAT.md

Defines the format for files in `./learning-records/`.

## Purpose

Learning records are the teaching equivalent of Architecture Decision Records in software. They capture decision-grade insights about what the user now knows — not session summaries, not coverage logs. They are read at the start of every session to calculate the zone of proximal development and decide what to teach next.

## File naming

`0001-<dash-case-title>.md`, incrementing with each new record. Scan `./learning-records/` for the highest existing number and add one. Create the directory lazily — only when the first record is written.

## Template

```md
# {Short title of what was learned or established}

{1–3 sentences: what was understood (or what prior knowledge was disclosed), and why it matters for future sessions.}
```

That is the complete format. A learning record can be a single paragraph. The value is in recording *that* this is now known and *why* it changes what to teach next — not in filling out sections.

## Optional fields

Include these only when they add genuine signal. Most records won't need them.

- **Status**: `active` or `superseded by LR-NNNN` — use when an earlier understanding is replaced by a later, more accurate one.
- **Evidence**: how the user demonstrated the understanding (a question answered correctly, an exercise completed, prior experience cited). Useful when the claim is likely to be revisited.
- **Implications**: what this unlocks or rules out for future sessions. Worth recording when non-obvious.

## When to write a learning record

Write one when any of these is true:

1. **The user demonstrated genuine understanding of something non-trivial.** Not just exposure — evidence they can use the concept correctly. This sets a new floor for what to teach next.
2. **The user disclosed prior knowledge.** "I already know X." Record it so future sessions don't re-teach it. Also note the depth they claimed.
3. **A misconception was corrected.** The user previously believed something wrong and now sees why. High-value records: they predict future stumbling blocks on related topics.
4. **The mission shifted.** The user discovered they cared about something different. Cross-link to `MISSION.md` and update it.

## What does NOT qualify

- Material that was merely covered. Coverage is not learning — wait for evidence.
- Anything already captured as a term in `GLOSSARY.md`. Don't duplicate.
- Session-by-session activity logs. These are not a journal.

## Supersession

When a later record contradicts an earlier one, mark the older record `Status: superseded by LR-NNNN` rather than deleting it. The history of how understanding evolved is itself useful signal for future teaching.
