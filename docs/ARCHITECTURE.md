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

Each object version is hashed. Each registry event includes the resulting version hash and the previous event hash, so the ledger binds both the mutation record and the object state produced by that mutation. Integrity verification cross-checks events, immutable versions, and each current object pointer. The result is a small tamper-evident ledger without requiring a blockchain or external service.

## Concurrency model

Every mutation requires `expected_version`. Stale writers fail. Mutations run inside `BEGIN IMMEDIATE` transactions, so the current pointer, immutable version, and event append commit or roll back together. This forbids silent last-write-wins behavior and torn multi-statement writes.

## Claim and dependency gates

Lifecycle promotion is constrained by claim level. Evidentiary, runtime, simulation, and experimental claims acquire minimum evidence burdens as they advance; speculative claims cannot advance beyond `sealed`. Dependencies may be declared early, but all dependencies must resolve before promotion to `evaluated` or beyond.

The JSON Schema is a portable reference contract. The dependency-free runtime enforces the equivalent object boundary in Python rather than importing a JSON Schema validator. Unknown object keys therefore raise `ModelError` at construction time.

## Autonomy boundary

The autonomic controller may inspect, diagnose, propose, and package. It does not publish, merge, approve, delete, spend, or communicate externally. Those effects are represented through policy gates rather than hidden in agent behavior.
