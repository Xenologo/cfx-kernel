from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


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

    SAFE: ClassVar[frozenset[Action]] = frozenset(
        {
            Action.INSPECT,
            Action.VALIDATE,
            Action.SIMULATE,
            Action.PROPOSE,
            Action.PACKAGE_REVIEW,
            Action.EXPORT_DRAFT,
        }
    )
    REVIEW: ClassVar[frozenset[Action]] = frozenset(
        {
            Action.APPROVE,
            Action.PUBLISH,
            Action.MERGE,
            Action.DELETE,
            Action.EXTERNAL_COMMUNICATION,
            Action.SPEND,
        }
    )

    def decide(
        self,
        action: Action | str,
        *,
        approved: bool = False,
        destructive: bool = False,
    ) -> PolicyResult:
        try:
            normalized = Action(action)
        except ValueError:
            return PolicyResult(GateDecision.DENY, "unknown actions are denied by default")

        if normalized in self.SAFE:
            if destructive and not approved:
                return PolicyResult(
                    GateDecision.REVIEW,
                    "destructive side effects require explicit approval",
                )
            if destructive:
                return PolicyResult(
                    GateDecision.ALLOW,
                    "bounded local action with explicit destructive approval",
                )
            return PolicyResult(GateDecision.ALLOW, "bounded local action")

        if normalized in self.REVIEW:
            if approved:
                qualifier = "destructive " if destructive else ""
                return PolicyResult(
                    GateDecision.ALLOW,
                    f"explicit approval supplied for {qualifier}authority-bearing action",
                )
            return PolicyResult(
                GateDecision.REVIEW,
                "external, destructive, or authority-bearing action requires explicit approval",
            )

        return PolicyResult(GateDecision.DENY, "action not covered by policy")
