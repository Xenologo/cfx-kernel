# CFX Kernel

**A small, local-first governance kernel for agentic software and evidence-bearing workflows.**

CFX Kernel distils the most practical engineering ideas from the larger private CFX Stack into a compact Python package that can be embedded in automation, QA systems, research tooling, agent runtimes, and local-first applications.

It gives you:

- governed objects with explicit claim and lifecycle state;
- a deterministic lifecycle with invalid-transition rejection;
- evidence references and SHA-256 provenance seals that bind each event to the resulting object version;
- an append-only SQLite registry with immutable versions;
- optimistic concurrency plus explicit SQLite write transactions so stale or interrupted writers cannot leave torn mutations;
- a tamper-evident global event chain;
- default-safe policy gates for publishing, merging, deletion, external messaging, approval, and spending;
- a bounded autonomic controller that may observe, diagnose, propose, and package work for review—but does not silently approve its own output;
- a dependency-free runtime on Python 3.11+.

## Why this exists

Many agent frameworks optimize for *doing more*. CFX Kernel optimizes for **knowing what was done, why, from which evidence, under whose authority, and whether it is allowed to become authoritative**.

The core architectural rule is intentionally simple:

> **Observe separately. Act explicitly. Judge independently.**

That separation is useful anywhere software-generated output must remain distinguishable from reviewed or approved output.

## Install

```bash
python -m pip install -e .
```

For development:

```bash
python -m pip install -e '.[dev]'
pytest -q
```

## 60-second demo

```bash
cfx --db demo.db register examples/example_object.json
cfx --db demo.db evidence DEMO.OBJECT.001 evidence://measurement-0001 --expected-version 1
cfx --db demo.db transition DEMO.OBJECT.001 sealed --expected-version 2
cfx --db demo.db transition DEMO.OBJECT.001 evaluated --expected-version 3
cfx --db demo.db verify
cfx --db demo.db observe
cfx --db demo.db package-review --mission "Prepare current objects for review"
```

Authority-bearing actions are gated:

```bash
cfx gate publish
# -> review

cfx gate publish --approved
# -> allow
```

An object may not transition from `registered` to `approved` unless the operator supplies the explicit approval gate.

## Lifecycle

```text
draft -> sealed -> evaluated -> verified -> registered -> approved
  |         |          |           |
  +------> quarantined / rejected --+--> archived
                                   \--> superseded
```

The lifecycle exists in executable code, not only documentation.

## Claim ceilings

`claim_level` is executable policy, not decorative metadata. Evidentiary claims need evidence before `evaluated`; runtime and simulation claims need evidence before `verified`; experimental claims need one reference before `evaluated` and two before `verified`; speculative claims are capped at `sealed`. Dependencies must resolve before promotion to `evaluated` or beyond.

## Package map

```text
src/cfx_kernel/
  model.py       governed objects + lifecycle invariants
  provenance.py  canonical hashing + seal-chain verification
  registry.py    SQLite history + optimistic concurrency + event chain
  policy.py      allow/review/deny action gates
  autonomic.py   observe/diagnose/propose/review-package loop
  cli.py         dependency-free operator CLI
```

## What was intentionally left out

This is not a dump of the private CFX monorepo. It excludes domain-specific research, private corpus material, CAO canonisation machinery, UI/XR shells, monograph content, specialised simulators, and project-specific nomenclature.

The result is deliberately smaller: a reusable trusted spine that other systems can import rather than a framework they must inhabit.

See [Architecture](docs/ARCHITECTURE.md) and [Distillation map](docs/MIGRATION_FROM_CFX_STACK.md).

## Status

`0.1.1` — integrity-hardening release. The target is a small, auditable trusted computing base rather than feature proliferation.

## License

Publicly viewable source, all rights reserved for the initial release. Relicensing can be done explicitly later without conflating public visibility with an open-source grant.
