# Deep vs Shallow Modules

Deep modules hide a lot of useful behavior behind **simple, stable interfaces**. Shallow modules expose a lot of surface area but do very little, forcing callers to do all the hard work.

**Deep module** = small interface + lots of implementation

```txt
┌─────────────────────┐
│   Small Interface   │  ← Few methods, simple params
├─────────────────────┤
│                     │
│                     │
│ Deep Implementation │  ← Complex logic hidden
│                     │
│                     │
└─────────────────────┘
```

**Shallow module** = large interface + little implementation (avoid)

```txt
┌─────────────────────────────────┐
│         Large Interface         │  ← Many methods, complex params
├─────────────────────────────────┤
│       Thin Implementation       │  ← Just passes through
└─────────────────────────────────┘
```

In AI‑driven TDD, deep modules are your friend:

- They give you fewer, more meaningful places to write tests.
- They let you change internals freely as long as behavior at the boundary stays the same.
- They reduce how often you have to touch tests when you refactor.

When designing a module, ask:

- Can I **push more behavior inside** this module while keeping the interface simple?
- Can callers ask for “what they want” instead of assembling it step by step themselves?
- Does this module feel like a **useful concept in the domain**, not just a grab‑bag of helpers?

If the answer is “no”, your module is probably too shallow. Try to combine related behavior into deeper, more coherent modules with clear boundaries.
