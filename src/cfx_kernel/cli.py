from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .autonomic import AutonomicController
from .model import GovernedObject
from .policy import Policy
from .registry import Registry


def _dump(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cfx", description="CFX Kernel local-first governance CLI")
    p.add_argument("--db", default="cfx.db", help="SQLite registry path")
    sub = p.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register", help="register a JSON object")
    reg.add_argument("file")
    reg.add_argument("--actor", default="human")

    show = sub.add_parser("show", help="show an object")
    show.add_argument("object_id")

    sub.add_parser("list", help="list current objects")

    tr = sub.add_parser("transition", help="move an object through the lifecycle")
    tr.add_argument("object_id")
    tr.add_argument("state")
    tr.add_argument("--expected-version", type=int, required=True)
    tr.add_argument("--actor", default="human")
    tr.add_argument("--approve", action="store_true", help="explicitly approve authority-bearing transition")
    tr.add_argument("--evidence", action="append", default=[])

    ev = sub.add_parser("evidence", help="attach an evidence reference")
    ev.add_argument("object_id")
    ev.add_argument("reference")
    ev.add_argument("--expected-version", type=int, required=True)
    ev.add_argument("--actor", default="human")

    sub.add_parser("verify", help="verify registry and history integrity")
    sub.add_parser("snapshot", help="export a current snapshot")
    sub.add_parser("observe", help="bounded autonomic observation")
    package = sub.add_parser("package-review", help="produce a review-bound maintenance packet")
    package.add_argument("--mission", default="CFX kernel health and review pass")

    gate = sub.add_parser("gate", help="evaluate an action against default policy")
    gate.add_argument("action")
    gate.add_argument("--approved", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "gate":
        _dump(asdict(Policy().decide(args.action, approved=args.approved)))
        return 0

    with Registry(args.db) as registry:
        if args.command == "register":
            _dump(registry.register(GovernedObject.from_dict(_load(args.file)), actor=args.actor))
        elif args.command == "show":
            _dump({"version": registry.version(args.object_id), "object": registry.get(args.object_id)})
        elif args.command == "list":
            _dump(registry.list_objects())
        elif args.command == "transition":
            _dump(registry.transition(args.object_id, args.state, expected_version=args.expected_version, actor=args.actor, evidence_refs=args.evidence, human_approved=args.approve))
        elif args.command == "evidence":
            _dump(registry.add_evidence(args.object_id, args.reference, expected_version=args.expected_version, actor=args.actor))
        elif args.command == "verify":
            _dump({"integrity_ok": registry.verify_integrity()})
        elif args.command == "snapshot":
            _dump(registry.export_snapshot())
        elif args.command == "observe":
            _dump(AutonomicController(registry).observe())
        elif args.command == "package-review":
            _dump(AutonomicController(registry).package(args.mission).to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
