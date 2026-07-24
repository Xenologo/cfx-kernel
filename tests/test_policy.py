from cfx_kernel.policy import GateDecision, Policy


def test_policy_is_default_safe():
    policy = Policy()
    assert policy.decide("inspect").decision is GateDecision.ALLOW
    assert policy.decide("publish").decision is GateDecision.REVIEW
    assert policy.decide("publish", approved=True).decision is GateDecision.ALLOW
    assert policy.decide("invented_action").decision is GateDecision.DENY


def test_destructive_is_a_severity_modifier_not_an_early_block():
    policy = Policy()
    assert policy.decide("inspect", destructive=True).decision is GateDecision.REVIEW
    assert (
        policy.decide("inspect", destructive=True, approved=True).decision is GateDecision.ALLOW
    )
    assert policy.decide("publish", destructive=True).decision is GateDecision.REVIEW
    assert (
        policy.decide("publish", destructive=True, approved=True).decision
        is GateDecision.ALLOW
    )
    assert policy.decide("delete", destructive=True).decision is GateDecision.REVIEW
    assert (
        policy.decide("delete", destructive=True, approved=True).decision is GateDecision.ALLOW
    )
