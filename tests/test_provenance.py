from cfx_kernel.provenance import GENESIS_HASH, seal_record, verify_seal_chain


def test_hash_chain_detects_tampering():
    one = seal_record({"x": 1})
    two = seal_record({"x": 2}, previous_hash=one["current_hash"])
    ok, failures = verify_seal_chain([one, two])
    assert ok and not failures
    two["record"]["x"] = 3
    ok, failures = verify_seal_chain([one, two])
    assert not ok
    assert failures
