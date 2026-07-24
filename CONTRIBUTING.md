# Contributing

Changes should preserve the kernel's small trusted computing base.

- Prefer the Python standard library over new runtime dependencies.
- Keep state transitions explicit and testable.
- Treat external/destructive actions as review-gated by default.
- Add integrity and concurrency tests for persistent state changes.
- Do not add autonomous publication, spending, deletion, or external messaging without an explicit policy boundary.
