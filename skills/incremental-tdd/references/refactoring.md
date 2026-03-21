# Refactoring with Tests

Refactoring means changing code structure **without changing behavior**. With a solid test suite, you can do this aggressively and safely.

Basic loop:

1. Get tests **green**.
2. Make a **small structural change** (rename, extract, inline, move code).
3. Run tests again.
4. Repeat.

Guidelines:

- Refactor in **tiny steps**, especially when using an AI agent.
- Let tests tell you if you went too far; if they fail in surprising ways, undo or adjust.
- Use refactoring to **clarify deep module boundaries**: move logic towards the modules that own the concept.

If a refactor requires updating many tests, it’s a signal that tests are **too coupled to implementation**. Consider pushing more behavior behind stable interfaces so future refactors are cheaper.
