# Architecture

CFX Kernel keeps six things separate:

1. **Object model** — what an artifact is, what it claims, and where it sits in a lifecycle.
2. **Evidence/provenance** — what supports it and whether history has been tampered with.
3. **Registry** — immutable versions plus a current pointer, stored in SQLite.
4. **Policy** — what an automated caller may do locally, what needs review, and what is denied.
5. **Autonomic control** — observation, diagnosis, proposals, and review packaging without implicit approval.
6. **Operator boundary** — humans remain the authority for approval, publication, destructive operations, and external effects.

## Lifecycle

`draft -> sealed -> evaluated -> verified -> registered -> approved`

Side states are explicit: `quarantined`, `rejected`, `superseded`, `archived`.

The lifecycle is not merely documentation. Invalid transitions raise errors, and approval cannot occur without an explicit `human_approved=True` gate.

## Integrity model

Each object version is hashed. Each registry event is hashed over its normalized payload and includes the previous event hash. The result is a small tamper-evident ledger without requiring a blockchain or external service.

## Concurrency model

Every mutation requires `expected_version`. Stale writers fail. This makes agent swarms and concurrent operator sessions easier to reason about because silent last-write-wins behavior is forbidden.

## Autonomy boundary

The autonomic controller may inspect, diagnose, propose, and package. It does not publish, merge, approve, delete, spend, or communicate externally. Those effects are represented through policy gates rather than hidden in agent behavior.
