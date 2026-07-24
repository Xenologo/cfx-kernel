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
