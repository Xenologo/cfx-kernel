import pytest

from cfx_kernel import ConcurrencyError, GovernedObject, Registry


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
