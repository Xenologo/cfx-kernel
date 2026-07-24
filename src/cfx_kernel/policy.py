from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    INSPECT = "inspect"
    VALIDATE = "validate"
    SIMULATE = "simulate"
    PROPOSE = "propose"
    PACKAGE_REVIEW = "package_review"
    EXPORT_DRAFT = "export_draft"
    APPROVE = "approve"
    PUBLISH = "publish"
    MERGE = "merge"
    DELETE = "delete"
    EXTERNAL_COMMUNICATION = "external_communication"
    SPEND = "spend"


class GateDecision(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PolicyResult:
    decision: GateDecision
    reason: str


class Policy:
    """Small default-safe policy gate for autonomous or agentic callers."""

    SAFE = {
        Action.INSPECT,
        Action.VALIDATE,
        Action.SIMULATE,
        Action.PROPOSE,
        Action.PACKAGE_REVIEW,
        Action.EXPORT_DRAFT,
    }
    REVIEW = {
        Action.APPROVE,
        Action.PUBLISH,
        Action.MERGE,
        Action.DELETE,
        Action.EXTERNAL_COMMUNICATION,
        Action.SPEND,
    }

    def decide(self, action: Action | str, *, approved: bool = False, destructive: bool = False) -> PolicyResult:
        try:
            action = Action(action)
        except ValueError:
            return PolicyResult(GateDecision.DENY, "unknown actions are denied by default")

        if destructive and action not in {Action.DELETE}:
            return PolicyResult(GateDecision.REVIEW, "destructive side effects require explicit review")
        if action in self.SAFE:
            return PolicyResult(GateDecision.ALLOW, "bounded local action")
        if action in self.REVIEW:
            if approved:
                return PolicyResult(GateDecision.ALLOW, "explicit approval supplied")
            return PolicyResult(GateDecision.REVIEW, "external, destructive, or authority-bearing action")
        return PolicyResult(GateDecision.DENY, "action not covered by policy")
