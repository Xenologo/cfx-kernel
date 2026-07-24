from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable
from uuid import uuid4

from .model import GovernedObject, LifecycleState, validate_transition
from .provenance import GENESIS_HASH, canonical_json, digest


class RegistryError(ValueError):
    pass


class ConcurrencyError(RegistryError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return canonical_json(value)


class Registry:
    """SQLite registry with immutable versions, optimistic concurrency, and a global hash-chained event log."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Registry":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _migrate(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS objects (
              object_id TEXT PRIMARY KEY,
              current_version INTEGER NOT NULL,
              current_state TEXT NOT NULL,
              state_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS versions (
              object_id TEXT NOT NULL,
              version INTEGER NOT NULL,
              state TEXT NOT NULL,
              state_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (object_id, version),
              FOREIGN KEY (object_id) REFERENCES objects(object_id)
            );
            CREATE TABLE IF NOT EXISTS events (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id TEXT NOT NULL UNIQUE,
              object_id TEXT NOT NULL,
              action TEXT NOT NULL,
              actor TEXT NOT NULL,
              rationale TEXT NOT NULL,
              prior_version INTEGER,
              resulting_version INTEGER NOT NULL,
              evidence_refs TEXT NOT NULL,
              previous_event_hash TEXT NOT NULL,
              event_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_object_idx ON events(object_id, sequence);
            """
        )

    def register(self, obj: GovernedObject | dict[str, Any], *, actor: str = "human", rationale: str = "initial registration") -> dict[str, Any]:
        item = obj if isinstance(obj, GovernedObject) else GovernedObject.from_dict(deepcopy(obj))
        state = item.to_dict()
        if self.db.execute("SELECT 1 FROM objects WHERE object_id = ?", (item.id,)).fetchone():
            raise RegistryError(f"object already registered: {item.id}")
        now = _now()
        state_hash = digest(state)
        with self.db:
            self.db.execute("INSERT INTO objects VALUES (?, ?, ?, ?, ?)", (item.id, 1, _json(state), state_hash, now))
            self.db.execute("INSERT INTO versions VALUES (?, ?, ?, ?, ?)", (item.id, 1, _json(state), state_hash, now))
            self._append_event(item.id, "register", actor, rationale, None, 1, item.evidence_refs, now)
        return deepcopy(state)

    def get(self, object_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT current_state FROM objects WHERE object_id = ?", (object_id.upper(),)).fetchone()
        if row is None:
            raise RegistryError(f"unknown object: {object_id}")
        return json.loads(row["current_state"])

    def version(self, object_id: str) -> int:
        row = self.db.execute("SELECT current_version FROM objects WHERE object_id = ?", (object_id.upper(),)).fetchone()
        if row is None:
            raise RegistryError(f"unknown object: {object_id}")
        return int(row["current_version"])

    def list_objects(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT current_state FROM objects ORDER BY object_id").fetchall()
        return [json.loads(row["current_state"]) for row in rows]

    def history(self, object_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT version, state FROM versions WHERE object_id = ? ORDER BY version", (object_id.upper(),)).fetchall()
        if not rows:
            raise RegistryError(f"unknown object: {object_id}")
        return [{"version": int(row["version"]), "state": json.loads(row["state"])} for row in rows]

    def transition(
        self,
        object_id: str,
        new_state: LifecycleState | str,
        *,
        expected_version: int,
        actor: str = "human",
        rationale: str = "lifecycle transition",
        evidence_refs: Iterable[str] = (),
        human_approved: bool = False,
    ) -> dict[str, Any]:
        object_id = object_id.upper()
        current_version = self.version(object_id)
        if current_version != expected_version:
            raise ConcurrencyError(f"{object_id} is at version {current_version}; expected {expected_version}")
        prior = self.get(object_id)
        old = LifecycleState(prior["lifecycle_state"])
        target = LifecycleState(new_state)
        validate_transition(old, target, human_approved=human_approved)
        resulting = deepcopy(prior)
        resulting["lifecycle_state"] = target.value
        if target is LifecycleState.APPROVED:
            resulting["review_required"] = False
        now = _now()
        new_version = current_version + 1
        state_hash = digest(resulting)
        refs = sorted({str(x).strip() for x in evidence_refs if str(x).strip()})
        with self.db:
            changed = self.db.execute(
                "UPDATE objects SET current_version = ?, current_state = ?, state_hash = ? WHERE object_id = ? AND current_version = ?",
                (new_version, _json(resulting), state_hash, object_id, current_version),
            ).rowcount
            if changed != 1:
                raise ConcurrencyError(f"concurrent update detected for {object_id}")
            self.db.execute("INSERT INTO versions VALUES (?, ?, ?, ?, ?)", (object_id, new_version, _json(resulting), state_hash, now))
            self._append_event(object_id, f"transition:{old.value}->{target.value}", actor, rationale, current_version, new_version, refs, now)
        return deepcopy(resulting)

    def add_evidence(self, object_id: str, evidence_ref: str, *, expected_version: int, actor: str = "human") -> dict[str, Any]:
        object_id = object_id.upper()
        current_version = self.version(object_id)
        if current_version != expected_version:
            raise ConcurrencyError(f"{object_id} is at version {current_version}; expected {expected_version}")
        prior = self.get(object_id)
        token = str(evidence_ref).strip()
        if not token:
            raise RegistryError("evidence_ref is required")
        resulting = deepcopy(prior)
        if token not in resulting["evidence_refs"]:
            resulting["evidence_refs"].append(token)
        now = _now()
        new_version = current_version + 1
        state_hash = digest(resulting)
        with self.db:
            changed = self.db.execute(
                "UPDATE objects SET current_version = ?, current_state = ?, state_hash = ? WHERE object_id = ? AND current_version = ?",
                (new_version, _json(resulting), state_hash, object_id, current_version),
            ).rowcount
            if changed != 1:
                raise ConcurrencyError(f"concurrent update detected for {object_id}")
            self.db.execute("INSERT INTO versions VALUES (?, ?, ?, ?, ?)", (object_id, new_version, _json(resulting), state_hash, now))
            self._append_event(object_id, "add_evidence", actor, f"attach evidence {token}", current_version, new_version, [token], now)
        return resulting

    def events(self, object_id: str | None = None) -> list[dict[str, Any]]:
        if object_id:
            rows = self.db.execute("SELECT * FROM events WHERE object_id = ? ORDER BY sequence", (object_id.upper(),)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["evidence_refs"] = json.loads(item["evidence_refs"])
            out.append(item)
        return out

    def _append_event(self, object_id: str, action: str, actor: str, rationale: str, prior_version: int | None, resulting_version: int, evidence_refs: Iterable[str], created_at: str) -> None:
        prev_row = self.db.execute("SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous = prev_row["event_hash"] if prev_row else GENESIS_HASH
        payload = {
            "event_id": f"CFX.EVENT.{uuid4().hex}",
            "object_id": object_id,
            "action": action,
            "actor": actor,
            "rationale": rationale,
            "prior_version": prior_version,
            "resulting_version": resulting_version,
            "evidence_refs": sorted(set(evidence_refs)),
            "previous_event_hash": previous,
            "created_at": created_at,
        }
        event_hash = digest(payload)
        self.db.execute(
            "INSERT INTO events (event_id, object_id, action, actor, rationale, prior_version, resulting_version, evidence_refs, previous_event_hash, event_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (payload["event_id"], object_id, action, actor, rationale, prior_version, resulting_version, _json(payload["evidence_refs"]), previous, event_hash, created_at),
        )

    def verify_integrity(self) -> bool:
        previous = GENESIS_HASH
        for row in self.db.execute("SELECT * FROM events ORDER BY sequence"):
            event = dict(row)
            recorded_hash = event.pop("event_hash")
            event.pop("sequence")
            event["evidence_refs"] = json.loads(event["evidence_refs"])
            if event["previous_event_hash"] != previous or digest(event) != recorded_hash:
                return False
            previous = recorded_hash
        for row in self.db.execute("SELECT current_state, state_hash FROM objects"):
            if digest(json.loads(row["current_state"])) != row["state_hash"]:
                return False
        for row in self.db.execute("SELECT state, state_hash FROM versions"):
            if digest(json.loads(row["state"])) != row["state_hash"]:
                return False
        return True

    def export_snapshot(self) -> dict[str, Any]:
        return {
            "format": "cfx-kernel.snapshot.v1",
            "objects": self.list_objects(),
            "events": self.events(),
            "integrity_ok": self.verify_integrity(),
        }
