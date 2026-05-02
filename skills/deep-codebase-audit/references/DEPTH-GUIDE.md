# Depth Guide

How to deepen a cluster of shallow modules safely, given its dependencies. Assumes the vocabulary in [GLOSSARY.md](GLOSSARY.md) — **module**, **interface**, **seam**, **adapter**.

## Dependency categories

When assessing a candidate for deepening, classify its dependencies. The category determines how the deepened module is tested across its seam.

### 1. In-process

Pure computation or in-memory state — no I/O, no network, no filesystem.

**Always deepenable.** Merge the shallow modules and test through the new interface directly. No adapter needed. This is the lowest-risk deepening.

_Signal_: all calls stay within the process boundary; the only inputs are function arguments or in-memory objects.

### 2. Local-substitutable

Dependencies that have realistic local test stand-ins: PGLite for Postgres, an in-memory filesystem, a local SQLite for a remote DB, etc.

**Deepenable if the stand-in exists.** The deepened module is tested with the stand-in running inside the test suite. The seam is internal to the module — no port needs to be exposed at the module's external interface. The stand-in is an implementation detail of the test setup, not a design decision for callers.

_Signal_: a fast, low-fidelity local replacement for the dependency already exists or is easy to create.

### 3. Remote but owned (Ports & Adapters)

Your own services across a network boundary — microservices, internal APIs, internal queues.

**Deepenable via a port.** Define a **port** (interface) at the seam. The deep module owns the logic; the transport is injected as an **adapter**. Tests use an in-memory adapter. Production uses an HTTP/gRPC/queue adapter.

Recommendation shape: _"Define a port at the seam, implement an HTTP adapter for production and an in-memory adapter for testing, so the logic sits in one deep module even though it's deployed across a network."_

_Signal_: you own the service on the other side of the call, so you can control the interface and add a test adapter.

### 4. True external (Mock)

Third-party services you don't control — Stripe, Twilio, AWS SDKs, external SaaS APIs.

**Deepenable via an injected port + mock adapter.** The deepened module takes the external dependency as an injected port; tests provide a mock adapter that records calls or returns canned responses.

_Signal_: you cannot run the real service in tests. The module wraps the external SDK and hides its details behind your own interface — callers never import the SDK directly.

## Seam discipline

- **One adapter means a hypothetical seam. Two adapters means a real one.** Don't introduce a port unless at least two adapters are justified (typically production + test). A single-adapter seam is just indirection with no payoff.
- **Internal seams vs external seams.** A deep module can have internal seams (private to its implementation, used by its own tests) as well as the external seam at its interface. Do not expose internal seams through the external interface just because tests use them.
- **Seam placement is a design decision.** Where you put the seam determines what callers must know. A seam placed too deep forces callers to assemble behavior themselves. A seam placed too shallow hides too little.

## Testing strategy: replace, don't layer

- Old unit tests on the shallow modules that were merged become waste once tests at the deepened module's interface exist — **delete them**.
- Write new tests at the deepened module's interface. **The interface is the test surface.**
- Tests assert on observable outcomes through the interface, not on internal state.
- Tests should survive internal refactors — they describe behaviour, not implementation. If a test has to change when the implementation changes but not the interface, it is testing past the interface.

## What to include in a deepening proposal

When you propose a deepening candidate, include:

1. **Dependency category** (from the four above) — this determines the testing strategy.
2. **What the seam looks like** — a sketch of the interface the deepened module would expose.
3. **What moves behind the seam** — the behaviour that callers currently have to manage themselves.
4. **Test approach** — which adapter type the test suite would use, and what the old unit tests become.

This keeps recommendations actionable rather than abstract.
