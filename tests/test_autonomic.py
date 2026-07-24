from cfx_kernel import AutonomicController, GovernedObject, Registry


def test_autonomic_packet_is_review_bound():
    with Registry(":memory:") as registry:
        registry.register(GovernedObject(id="DEMO.OBJECT.001", title="Demo"))
        packet = AutonomicController(registry).package()
        assert packet.review_required is True
        assert packet.observations["integrity_ok"] is True


def test_autonomic_reports_dangling_dependencies():
    with Registry(":memory:") as registry:
        registry.register(
            GovernedObject(
                id="CHILD.001",
                title="Child",
                dependencies=["GHOST.PARENT.999"],
            )
        )
        findings = AutonomicController(registry).diagnose()
        assert any(item.code == "dependency.unresolved" for item in findings)
