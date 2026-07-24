from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .model import ModelError, validate_claim_state
from .registry import Registry


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str
    message: str
    object_id: str | None = None
    recommendation: str | None = None


@dataclass(slots=True)
class ReviewPacket:
    mission: str
    observations: dict[str, Any]
    findings: list[Finding] = field(default_factory=list)
    proposed_actions: list[dict[str, str]] = field(default_factory=list)
    review_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission": self.mission,
            "observations": self.observations,
            "findings": [asdict(item) for item in self.findings],
            "proposed_actions": self.proposed_actions,
            "review_required": self.review_required,
        }


class AutonomicController:
    """Observe -> diagnose -> propose -> package without approval or external side effects."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def observe(self) -> dict[str, Any]:
        objects = self.registry.list_objects()
        by_state: dict[str, int] = {}
        unresolved = 0
        for obj in objects:
            state = obj["lifecycle_state"]
            by_state[state] = by_state.get(state, 0) + 1
            unresolved += len(self.registry.unresolved_dependencies(obj))
        return {
            "object_count": len(objects),
            "by_state": dict(sorted(by_state.items())),
            "review_required_count": sum(bool(obj.get("review_required")) for obj in objects),
            "evidence_ref_count": sum(len(obj.get("evidence_refs", [])) for obj in objects),
            "unresolved_dependency_count": unresolved,
            "integrity_ok": self.registry.verify_integrity(),
        }

    def diagnose(self) -> list[Finding]:
        observations = self.observe()
        findings: list[Finding] = []
        if not observations["integrity_ok"]:
            findings.append(
                Finding(
                    "integrity.failure",
                    "blocking",
                    "Registry integrity verification failed.",
                    recommendation="Freeze mutation and inspect the event/version chain.",
                )
            )
        for obj in self.registry.list_objects():
            try:
                validate_claim_state(
                    obj["claim_level"],
                    obj["lifecycle_state"],
                    evidence_count=len(obj.get("evidence_refs", [])),
                )
            except ModelError as exc:
                findings.append(
                    Finding(
                        "claim.ceiling",
                        "high",
                        str(exc),
                        object_id=obj["id"],
                        recommendation="Downgrade the claim/state or attach qualifying evidence.",
                    )
                )

            missing = self.registry.unresolved_dependencies(obj)
            if missing:
                findings.append(
                    Finding(
                        "dependency.unresolved",
                        "high",
                        f"Unresolved dependencies: {', '.join(missing)}.",
                        object_id=obj["id"],
                        recommendation="Register or remove unresolved dependencies before promotion.",
                    )
                )

            if (
                obj["lifecycle_state"] in {"evaluated", "verified", "registered"}
                and not obj.get("evidence_refs")
            ):
                findings.append(
                    Finding(
                        "evidence.missing",
                        "high",
                        "Advanced lifecycle object has no evidence references.",
                        object_id=obj["id"],
                        recommendation="Attach evidence before promotion.",
                    )
                )
            if obj["lifecycle_state"] == "registered" and obj.get("review_required"):
                findings.append(
                    Finding(
                        "review.pending",
                        "medium",
                        "Registered object awaits explicit review.",
                        object_id=obj["id"],
                        recommendation="Package for human review; do not auto-approve.",
                    )
                )
        return findings

    def package(self, mission: str = "CFX kernel health and review pass") -> ReviewPacket:
        observations = self.observe()
        findings = self.diagnose()
        actions = [
            {
                "type": "proposal",
                "target": finding.object_id or "registry",
                "action": finding.recommendation or "review finding",
            }
            for finding in findings
        ]
        return ReviewPacket(
            mission=mission,
            observations=observations,
            findings=findings,
            proposed_actions=actions,
        )
