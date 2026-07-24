from cfx_kernel.policy import GateDecision, Policy


def test_policy_is_default_safe():
    policy = Policy()
    assert policy.decide("inspect").decision is GateDecision.ALLOW
    assert policy.decide("publish").decision is GateDecision.REVIEW
    assert policy.decide("publish", approved=True).decision is GateDecision.ALLOW
    assert policy.decide("invented_action").decision is GateDecision.DENY
