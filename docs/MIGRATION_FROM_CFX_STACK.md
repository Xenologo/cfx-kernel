# Distillation map from CFX Stack

This repository is a clean, generic distillation of the most reusable CFX engineering patterns rather than a public mirror of the private monorepo.

| CFX Stack concern | CFX Kernel form |
|---|---|
| object spine / controlled lifecycle | `model.py` |
| provenance sealing | `provenance.py` |
| append-only registry / optimistic concurrency | `registry.py` |
| superagent approval gates | `policy.py` |
| autonomic observe-diagnose-plan-package loop | `autonomic.py` |
| stack proof lanes | tests + GitHub Actions |
| domain corridors / CAO-specific canonisation | intentionally omitted |
| XR/UI shells and domain applications | intentionally omitted |
| private corpus, monographs, sensitive experiments | intentionally omitted |

## Design change: canonisation -> approval

The private stack has a specific authority model built around evidence, runtime action, and CAO judgement. The public kernel generalises this into `observer -> actor -> reviewer` semantics and uses the neutral lifecycle term `approved`.

The crucial principle survives: **generated or validated output does not become authoritative merely because software produced it**.

## v0.1.1 hardening

The public kernel now enforces three boundaries that were only partially expressed in v0.1.0: registry events bind the resulting version hash, multi-statement mutations are atomic SQLite transactions, and claim levels impose evidence ceilings on lifecycle promotion. Existing v0.1.0 databases are migrated by verifying the legacy chain available to the old format, adding `resulting_state_hash`, and re-sealing the event chain against the currently stored immutable versions. Because the old format did not bind version content, that migration cannot retroactively prove that pre-migration content was never rewritten; it hardens the chain from the migration point forward.
