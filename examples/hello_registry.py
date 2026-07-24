from cfx_kernel import AutonomicController, GovernedObject, Registry

with Registry(":memory:") as registry:
    registry.register(GovernedObject(id="DEMO.OBJECT.001", title="Example governed object"))
    registry.add_evidence("DEMO.OBJECT.001", "sha256:example-evidence", expected_version=1)
    registry.transition("DEMO.OBJECT.001", "sealed", expected_version=2)
    print(AutonomicController(registry).package().to_dict())
