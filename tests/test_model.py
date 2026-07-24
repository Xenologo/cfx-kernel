import pytest

from cfx_kernel.model import GovernedObject, ModelError, validate_transition


def test_normalizes_id_and_deduplicates_refs():
    obj = GovernedObject(id="demo.object.001", title="Demo", evidence_refs=["A", "A"])
    assert obj.id == "DEMO.OBJECT.001"
    assert obj.evidence_refs == ["A"]


def test_approval_requires_explicit_human_gate():
    with pytest.raises(ModelError):
        validate_transition("registered", "approved")
    validate_transition("registered", "approved", human_approved=True)


def test_claim_evidence_minima_and_speculative_ceiling():
    with pytest.raises(ModelError, match="at least 1 evidence"):
        validate_transition(
            "sealed",
            "evaluated",
            claim_level="evidentiary",
            evidence_count=0,
        )
    validate_transition(
        "sealed",
        "evaluated",
        claim_level="evidentiary",
        evidence_count=1,
    )

    with pytest.raises(ModelError, match="at least 2 evidence"):
        validate_transition(
            "evaluated",
            "verified",
            claim_level="experimental",
            evidence_count=1,
        )

    with pytest.raises(ModelError, match="capped"):
        validate_transition(
            "sealed",
            "evaluated",
            claim_level="speculative",
            evidence_count=99,
        )


def test_unknown_fields_raise_model_error():
    with pytest.raises(ModelError, match="unknown object field"):
        GovernedObject.from_dict({"id": "DEMO.OBJECT.001", "title": "Demo", "mystery": 1})
