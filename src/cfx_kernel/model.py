from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from enum import StrEnum
from typing import Any

ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,126}[A-Z0-9]$")


class ModelError(ValueError):
    pass


class LifecycleState(StrEnum):
    DRAFT = "draft"
    SEALED = "sealed"
    EVALUATED = "evaluated"
    VERIFIED = "verified"
    REGISTERED = "registered"
    APPROVED = "approved"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ClaimLevel(StrEnum):
    ARCHITECTURAL = "architectural"
    FORMAL = "formal"
    EVIDENTIARY = "evidentiary"
    RUNTIME = "runtime"
    SIMULATION = "simulation"
    EXPERIMENTAL = "experimental"
    SPECULATIVE = "speculative"


NORMAL_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.DRAFT: {
        LifecycleState.SEALED,
        LifecycleState.QUARANTINED,
        LifecycleState.REJECTED,
    },
    LifecycleState.SEALED: {
        LifecycleState.EVALUATED,
        LifecycleState.QUARANTINED,
        LifecycleState.REJECTED,
    },
    LifecycleState.EVALUATED: {
        LifecycleState.VERIFIED,
        LifecycleState.QUARANTINED,
        LifecycleState.REJECTED,
    },
    LifecycleState.VERIFIED: {
        LifecycleState.REGISTERED,
        LifecycleState.QUARANTINED,
        LifecycleState.REJECTED,
    },
    LifecycleState.REGISTERED: {
        LifecycleState.APPROVED,
        LifecycleState.SUPERSEDED,
        LifecycleState.ARCHIVED,
    },
    LifecycleState.APPROVED: {LifecycleState.SUPERSEDED, LifecycleState.ARCHIVED},
    LifecycleState.QUARANTINED: {
        LifecycleState.DRAFT,
        LifecycleState.REJECTED,
        LifecycleState.ARCHIVED,
    },
    LifecycleState.REJECTED: {LifecycleState.ARCHIVED},
    LifecycleState.SUPERSEDED: {LifecycleState.ARCHIVED},
    LifecycleState.ARCHIVED: set(),
}

PROMOTION_RANK: dict[LifecycleState, int] = {
    LifecycleState.DRAFT: 0,
    LifecycleState.SEALED: 1,
    LifecycleState.EVALUATED: 2,
    LifecycleState.VERIFIED: 3,
    LifecycleState.REGISTERED: 4,
    LifecycleState.APPROVED: 5,
}

# Claim ceilings are deliberately small and inspectable. Structural/formal claims can advance
# without external evidence; claims that imply observation, runtime behaviour, simulation, or
# experiment require evidence before stronger lifecycle states are reachable.
CLAIM_EVIDENCE_MINIMA: dict[ClaimLevel, tuple[tuple[LifecycleState, int], ...]] = {
    ClaimLevel.ARCHITECTURAL: (),
    ClaimLevel.FORMAL: (),
    ClaimLevel.EVIDENTIARY: ((LifecycleState.EVALUATED, 1),),
    ClaimLevel.RUNTIME: ((LifecycleState.VERIFIED, 1),),
    ClaimLevel.SIMULATION: ((LifecycleState.VERIFIED, 1),),
    ClaimLevel.EXPERIMENTAL: (
        (LifecycleState.EVALUATED, 1),
        (LifecycleState.VERIFIED, 2),
    ),
    ClaimLevel.SPECULATIVE: (),
}

CLAIM_MAX_STATE: dict[ClaimLevel, LifecycleState] = {
    ClaimLevel.SPECULATIVE: LifecycleState.SEALED,
}


def normalize_id(value: str) -> str:
    token = str(value or "").strip().upper()
    if not ID_RE.fullmatch(token):
        raise ModelError(f"invalid object id: {value!r}")
    return token


def validate_claim_state(
    claim_level: ClaimLevel | str,
    state: LifecycleState | str,
    *,
    evidence_count: int,
) -> None:
    claim = ClaimLevel(claim_level)
    target = LifecycleState(state)
    target_rank = PROMOTION_RANK.get(target)
    if target_rank is None:
        return

    maximum = CLAIM_MAX_STATE.get(claim)
    if maximum is not None and target_rank > PROMOTION_RANK[maximum]:
        raise ModelError(f"{claim.value} claims are capped at lifecycle state {maximum.value}")

    required = 0
    for threshold, minimum in CLAIM_EVIDENCE_MINIMA[claim]:
        if target_rank >= PROMOTION_RANK[threshold]:
            required = max(required, minimum)
    if evidence_count < required:
        raise ModelError(
            f"{claim.value} claim requires at least {required} evidence reference(s) "
            f"before lifecycle state {target.value}"
        )


def validate_transition(
    old: LifecycleState | str,
    new: LifecycleState | str,
    *,
    human_approved: bool = False,
    claim_level: ClaimLevel | str = ClaimLevel.ARCHITECTURAL,
    evidence_count: int = 0,
) -> None:
    old_state = LifecycleState(old)
    new_state = LifecycleState(new)
    if new_state not in NORMAL_TRANSITIONS[old_state]:
        raise ModelError(f"invalid lifecycle transition: {old_state} -> {new_state}")
    validate_claim_state(claim_level, new_state, evidence_count=evidence_count)
    if new_state is LifecycleState.APPROVED and not human_approved:
        raise ModelError("transition to approved requires explicit human approval")


@dataclass(slots=True)
class GovernedObject:
    id: str
    title: str
    kind: str = "object"
    lifecycle_state: LifecycleState = LifecycleState.DRAFT
    claim_level: ClaimLevel = ClaimLevel.ARCHITECTURAL
    source: str = "local"
    review_required: bool = True
    evidence_refs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = normalize_id(self.id)
        self.title = self.title.strip()
        self.kind = self.kind.strip() or "object"
        self.source = self.source.strip() or "local"
        self.lifecycle_state = LifecycleState(self.lifecycle_state)
        self.claim_level = ClaimLevel(self.claim_level)
        self.evidence_refs = _unique_strings(self.evidence_refs)
        self.dependencies = [normalize_id(value) for value in _unique_strings(self.dependencies)]
        self.tags = _unique_strings(self.tags)
        if not self.title:
            raise ModelError("title is required")
        validate_claim_state(
            self.claim_level,
            self.lifecycle_state,
            evidence_count=len(self.evidence_refs),
        )
        if self.lifecycle_state is LifecycleState.APPROVED and self.review_required:
            raise ModelError("approved objects cannot remain review_required=True")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lifecycle_state"] = self.lifecycle_state.value
        payload["claim_level"] = self.claim_level.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GovernedObject:
        if not isinstance(payload, dict):
            raise ModelError("governed object must be a mapping")
        allowed = {item.name for item in fields(cls)}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ModelError(f"unknown object field(s): {', '.join(unknown)}")
        try:
            return cls(**payload)
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ModelError):
                raise
            raise ModelError(str(exc)) from exc


def _unique_strings(values: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = str(raw).strip()
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
