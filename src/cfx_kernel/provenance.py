from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

GENESIS_HASH = "0" * 64


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value: Any) -> str:
    payload = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seal_record(record: dict[str, Any], *, previous_hash: str = GENESIS_HASH, context: dict[str, Any] | None = None) -> dict[str, Any]:
    envelope = {
        "previous_hash": previous_hash,
        "record": deepcopy(record),
        "context": deepcopy(context) if context else {},
    }
    return {**envelope, "current_hash": digest(envelope)}


def verify_seal_chain(records: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    previous = GENESIS_HASH
    for index, sealed in enumerate(records):
        expected = seal_record(
            deepcopy(sealed.get("record") or {}),
            previous_hash=previous,
            context=sealed.get("context") or {},
        )
        if sealed.get("previous_hash") != previous:
            failures.append(f"index {index}: previous_hash mismatch")
        if sealed.get("current_hash") != expected["current_hash"]:
            failures.append(f"index {index}: current_hash mismatch")
        previous = str(sealed.get("current_hash") or "")
    return (not failures, failures)
