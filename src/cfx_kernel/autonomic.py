from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

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
    """Observe -> diagnose -> propose -> package. It deliberately performs no approval or external side effect."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def observe(self) -> dict[str, Any]:
        objects = self.registry.list_objects()
        by_state: dict[str, int] = {}
        for obj in objects:
            state = obj["lifecycle_state"]
            by_state[state] = by_state.get(state, 0) + 1
        return {
            "object_count": len(objects),
            "by_state": dict(sorted(by_state.items())),
            "review_required_count": sum(bool(obj.get("review_required")) for obj in objects),
            "evidence_ref_count": sum(len(obj.get("evidence_refs", [])) for obj in objects),
            "integrity_ok": self.registry.verify_integrity(),
        }

    def diagnose(self) -> list[Finding]:
        observations = self.observe()
        findings: list[Finding] = []
        if not observations["integrity_ok"]:
            findings.append(Finding("integrity.failure", "blocking", "Registry integrity verification failed.", recommendation="Freeze mutation and inspect the event/version chain."))
        for obj in self.registry.list_objects():
            if obj["lifecycle_state"] in {"evaluated", "verified", "registered"} and not obj.get("evidence_refs"):
                findings.append(Finding("evidence.missing", "high", "Advanced lifecycle object has no evidence references.", object_id=obj["id"], recommendation="Attach evidence before promotion."))
            if obj["lifecycle_state"] == "registered" and obj.get("review_required"):
                findings.append(Finding("review.pending", "medium", "Registered object awaits explicit review.", object_id=obj["id"], recommendation="Package for human review; do not auto-approve."))
        return findings

    def package(self, mission: str = "CFX kernel health and review pass") -> ReviewPacket:
        observations = self.observe()
        findings = self.diagnose()
        actions: list[dict[str, str]] = []
        for finding in findings:
            actions.append({
                "type": "proposal",
                "target": finding.object_id or "registry",
                "action": finding.recommendation or "review finding",
            })
        return ReviewPacket(mission=mission, observations=observations, findings=findings, proposed_actions=actions)
