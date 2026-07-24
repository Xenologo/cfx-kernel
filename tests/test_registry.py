import json

import pytest

from cfx_kernel import ConcurrencyError, GovernedObject, ModelError, Registry, RegistryError
from cfx_kernel.provenance import digest


def test_registry_versions_and_integrity(tmp_path):
    db = tmp_path / "cfx.db"
    with Registry(db) as registry:
        registry.register(GovernedObject(id="DEMO.OBJECT.001", title="Demo"))
        registry.add_evidence("DEMO.OBJECT.001", "evidence:1", expected_version=1)
        registry.transition("DEMO.OBJECT.001", "sealed", expected_version=2)
        assert registry.version("DEMO.OBJECT.001") == 3
        assert len(registry.history("DEMO.OBJECT.001")) == 3
        assert registry.verify_integrity()


def test_stale_write_fails():
    with Registry(":memory:") as registry:
        registry.register(GovernedObject(id="DEMO.OBJECT.001", title="Demo"))
        registry.add_evidence("DEMO.OBJECT.001", "evidence:1", expected_version=1)
        with pytest.raises(ConcurrencyError):
            registry.transition("DEMO.OBJECT.001", "sealed", expected_version=1)


def test_event_chain_binds_resulting_object_content():
    with Registry(":memory:") as registry:
        registry.register(
            GovernedObject(
                id="DEMO.OBJECT.001",
                title="Demo",
                claim_level="evidentiary",
            )
        )
        registry.add_evidence("DEMO.OBJECT.001", "evidence:1", expected_version=1)
        assert registry.verify_integrity()

        forged = registry.history("DEMO.OBJECT.001")[0]["state"]
        forged["title"] = "FORGED title"
        forged["claim_level"] = "formal"
        forged_json = json.dumps(
            forged,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        registry.db.execute(
            "UPDATE versions SET state = ?, state_hash = ? WHERE object_id = ? AND version = 1",
            (forged_json, digest(forged), "DEMO.OBJECT.001"),
        )
        assert registry.verify_integrity() is False


def test_write_is_atomic_when_event_append_fails(monkeypatch):
    with Registry(":memory:") as registry:
        registry.register(GovernedObject(id="DEMO.OBJECT.001", title="Demo"))

        def fail_event(*_args, **_kwargs):
            raise RuntimeError("synthetic event failure")

        monkeypatch.setattr(registry, "_append_event", fail_event)
        with pytest.raises(RuntimeError, match="synthetic event failure"):
            registry.add_evidence("DEMO.OBJECT.001", "evidence:1", expected_version=1)

        assert registry.version("DEMO.OBJECT.001") == 1
        assert len(registry.history("DEMO.OBJECT.001")) == 1
        assert registry.get("DEMO.OBJECT.001")["evidence_refs"] == []


def test_claim_minima_block_evidence_free_promotion():
    with Registry(":memory:") as registry:
        registry.register(
            GovernedObject(
                id="EVIDENCE.CLAIM.001",
                title="Evidence claim",
                claim_level="evidentiary",
            )
        )
        registry.transition("EVIDENCE.CLAIM.001", "sealed", expected_version=1)
        with pytest.raises(ModelError, match="at least 1 evidence"):
            registry.transition("EVIDENCE.CLAIM.001", "evaluated", expected_version=2)

        promoted = registry.transition(
            "EVIDENCE.CLAIM.001",
            "evaluated",
            expected_version=2,
            evidence_refs=["evidence:measurement-1"],
        )
        assert promoted["evidence_refs"] == ["evidence:measurement-1"]


def test_unresolved_dependency_blocks_advanced_promotion():
    with Registry(":memory:") as registry:
        registry.register(
            GovernedObject(
                id="CHILD.001",
                title="Child",
                dependencies=["GHOST.PARENT.999"],
            )
        )
        registry.transition("CHILD.001", "sealed", expected_version=1)
        with pytest.raises(RegistryError, match="unresolved dependencies"):
            registry.transition("CHILD.001", "evaluated", expected_version=2)


def test_lookup_validates_object_id():
    with Registry(":memory:") as registry:
        with pytest.raises(ModelError, match="invalid object id"):
            registry.get("not valid!")
