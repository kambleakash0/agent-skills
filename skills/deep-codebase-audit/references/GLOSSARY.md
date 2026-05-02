# Glossary

Shared vocabulary for every suggestion this skill makes. Use these terms exactly — don't substitute "component," "service," "API," or "boundary." Consistent language is the whole point.

## Terms

**Module**
Anything with an interface and an implementation. Deliberately scale-agnostic — applies equally to a function, class, package, or tier-spanning slice.
_Avoid_: unit, component, service.

**Interface**
Everything a caller must know to use the module correctly. Includes the type signature, but also invariants, ordering constraints, error modes, required configuration, and performance characteristics.
_Avoid_: API, signature (too narrow — those refer only to the type-level surface).

**Implementation**
What's inside a module — its body of code. Distinct from **Adapter**: a thing can be a small adapter with a large implementation (a Postgres repository) or a large adapter with a small implementation (an in-memory fake). Reach for "adapter" when the seam is the topic; "implementation" otherwise.

**Depth**
Leverage at the interface — the amount of behaviour a caller (or test) can exercise per unit of interface they have to learn. A module is **deep** when a large amount of behaviour sits behind a small interface. A module is **shallow** when the interface is nearly as complex as the implementation.

**Seam** _(from Michael Feathers)_
A place where you can alter behaviour without editing in that place. The _location_ at which a module's interface lives. Choosing where to put the seam is its own design decision, distinct from what goes behind it.
_Avoid_: boundary (overloaded with DDD's bounded context).

**Adapter**
A concrete thing that satisfies an interface at a seam. Describes _role_ (what slot it fills), not substance (what's inside).
Examples: an HTTP adapter, an in-memory fake, a Postgres repository.

**Leverage**
What callers get from depth. More capability per unit of interface they have to learn. One implementation pays back across N call sites and M tests.

**Locality**
What maintainers get from depth. Change, bugs, knowledge, and verification concentrate at one place rather than spreading across callers. Fix once, fixed everywhere.

**Deepening opportunity**
A candidate refactor that would increase the depth of one or more modules — typically by merging shallow helpers, moving logic closer to the module that owns the domain concept, or hiding a cross-cutting concern behind a seam.

## Principles

- **Depth is a property of the interface, not the implementation.** A deep module can be internally composed of small, swappable parts — they just aren't part of the interface. A module can have **internal seams** (private to its implementation, used by its own tests) as well as the **external seam** at its interface.
- **The deletion test.** Imagine deleting the module. If complexity vanishes, the module wasn't hiding anything (it was a pass-through). If complexity reappears across N callers, the module was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam. If you want to test _past_ the interface, the module is probably the wrong shape.
- **One adapter means a hypothetical seam. Two adapters means a real one.** Don't introduce a seam unless something actually varies across it.
- **AI-navigability mirrors human onboarding.** An AI agent reads a codebase like a new developer: by file names, folder structure, and exports. Deep modules with stable, well-named interfaces are discovered faster and called more safely by both.

## Relationships

- A **Module** has exactly one **Interface** (the surface it presents to callers and tests).
- **Depth** is a property of a **Module**, measured against its **Interface**.
- A **Seam** is where a **Module**'s **Interface** lives.
- An **Adapter** sits at a **Seam** and satisfies the **Interface**.
- **Depth** produces **Leverage** for callers and **Locality** for maintainers.

## Rejected framings

- **Depth as ratio of implementation-lines to interface-lines**: rewards padding the implementation. We use depth-as-leverage instead.
- **"Interface" as TypeScript's `interface` keyword or a class's public methods**: too narrow — interface here includes every fact a caller must know.
- **"Boundary"**: overloaded with DDD's bounded context. Say **seam** or **interface** instead.
- **"Service"**: implies a deployment unit or a process boundary. Say **module** — it applies at every scale.
- **"Component"**: UI-framework connotation. Say **module**.
- **"API"**: refers only to the type-level surface. Say **interface** when you mean the full contract a caller must know.
