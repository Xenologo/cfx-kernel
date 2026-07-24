"""CFX Kernel: governed, local-first runtime primitives."""

from .autonomic import AutonomicController, Finding, ReviewPacket
from .model import (
    CLAIM_EVIDENCE_MINIMA,
    CLAIM_MAX_STATE,
    ClaimLevel,
    GovernedObject,
    LifecycleState,
    ModelError,
    normalize_id,
    validate_claim_state,
    validate_transition,
)
from .policy import Action, GateDecision, Policy, PolicyResult
from .provenance import canonical_json, digest, seal_record, verify_seal_chain
from .registry import ConcurrencyError, Registry, RegistryError

__all__ = [
    "CLAIM_EVIDENCE_MINIMA",
    "CLAIM_MAX_STATE",
    "Action",
    "AutonomicController",
    "ClaimLevel",
    "ConcurrencyError",
    "Finding",
    "GateDecision",
    "GovernedObject",
    "LifecycleState",
    "ModelError",
    "Policy",
    "PolicyResult",
    "Registry",
    "RegistryError",
    "ReviewPacket",
    "canonical_json",
    "digest",
    "normalize_id",
    "seal_record",
    "validate_claim_state",
    "validate_transition",
    "verify_seal_chain",
]
