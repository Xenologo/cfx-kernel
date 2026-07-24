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
