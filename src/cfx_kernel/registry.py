from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Self
from uuid import uuid4

from .model import (
    PROMOTION_RANK,
    GovernedObject,
    LifecycleState,
    ModelError,
    normalize_id,
    validate_claim_state,
    validate_transition,
)
from .provenance import GENESIS_HASH, canonical_json, digest


class RegistryError(ValueError):
    pass


class ConcurrencyError(RegistryError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return canonical_json(value)


class Registry:
    """SQLite registry with immutable versions, atomic writes, and content-bound events."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        # Autocommit is deliberate: every mutation opens its own BEGIN IMMEDIATE transaction.
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self.db.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @contextmanager
    def _write_transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.db.rollback()
            raise
        else:
            self.db.commit()

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
              resulting_state_hash TEXT,
              evidence_refs TEXT NOT NULL,
              previous_event_hash TEXT NOT NULL,
              event_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_object_idx ON events(object_id, sequence);
            """
        )
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(events)")}
        if "resulting_state_hash" not in columns:
            self._migrate_content_binding()

    def _migrate_content_binding(self) -> None:
        """Upgrade v0.1.0 event rows so the event chain binds the resulting version hash.

        The old format cannot retroactively prove that pre-migration state was never rewritten; this
        migration verifies the legacy self-consistency that is available, then re-seals the chain
        against the currently stored immutable versions.
        """
        with self._write_transaction():
            if not self._verify_legacy_integrity():
                raise RegistryError(
                    "legacy registry integrity check failed; refusing content-binding migration"
                )
            self.db.execute("ALTER TABLE events ADD COLUMN resulting_state_hash TEXT")
            previous = GENESIS_HASH
            rows = self.db.execute("SELECT * FROM events ORDER BY sequence").fetchall()
            for row in rows:
                version = self.db.execute(
                    "SELECT state_hash FROM versions WHERE object_id = ? AND version = ?",
                    (row["object_id"], row["resulting_version"]),
                ).fetchone()
                if version is None:
                    raise RegistryError(
                        f"event {row['event_id']} references missing version "
                        f"{row['object_id']}@{row['resulting_version']}"
                    )
                state_hash = str(version["state_hash"])
                payload = {
                    "event_id": row["event_id"],
                    "object_id": row["object_id"],
                    "action": row["action"],
                    "actor": row["actor"],
                    "rationale": row["rationale"],
                    "prior_version": row["prior_version"],
                    "resulting_version": row["resulting_version"],
                    "resulting_state_hash": state_hash,
                    "evidence_refs": json.loads(row["evidence_refs"]),
                    "previous_event_hash": previous,
                    "created_at": row["created_at"],
                }
                event_hash = digest(payload)
                self.db.execute(
                    "UPDATE events SET resulting_state_hash = ?, previous_event_hash = ?, "
                    "event_hash = ? WHERE sequence = ?",
                    (state_hash, previous, event_hash, row["sequence"]),
                )
                previous = event_hash

    def _verify_legacy_integrity(self) -> bool:
        previous = GENESIS_HASH
        for row in self.db.execute("SELECT * FROM events ORDER BY sequence"):
            event = dict(row)
            recorded_hash = event.pop("event_hash")
            event.pop("sequence")
            event.pop("resulting_state_hash", None)
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

    def _load_current(self, object_id: str) -> tuple[str, int, dict[str, Any]]:
        normalized = normalize_id(object_id)
        row = self.db.execute(
            "SELECT current_version, current_state FROM objects WHERE object_id = ?",
            (normalized,),
        ).fetchone()
        if row is None:
            raise RegistryError(f"unknown object: {normalized}")
        return normalized, int(row["current_version"]), json.loads(row["current_state"])

    def register(
        self,
        obj: GovernedObject | dict[str, Any],
        *,
        actor: str = "human",
        rationale: str = "initial registration",
    ) -> dict[str, Any]:
        item = obj if isinstance(obj, GovernedObject) else GovernedObject.from_dict(deepcopy(obj))
        state = item.to_dict()
        now = _now()
        state_hash = digest(state)

        with self._write_transaction():
            if self.db.execute(
                "SELECT 1 FROM objects WHERE object_id = ?", (item.id,)
            ).fetchone():
                raise RegistryError(f"object already registered: {item.id}")
            self._require_dependencies_for_state(state, item.lifecycle_state)
            self.db.execute(
                "INSERT INTO objects VALUES (?, ?, ?, ?, ?)",
                (item.id, 1, _json(state), state_hash, now),
            )
            self.db.execute(
                "INSERT INTO versions VALUES (?, ?, ?, ?, ?)",
                (item.id, 1, _json(state), state_hash, now),
            )
            self._append_event(
                item.id,
                "register",
                actor,
                rationale,
                None,
                1,
                state_hash,
                item.evidence_refs,
                now,
            )
        return deepcopy(state)

    def get(self, object_id: str) -> dict[str, Any]:
        return deepcopy(self._load_current(object_id)[2])

    def version(self, object_id: str) -> int:
        return self._load_current(object_id)[1]

    def list_objects(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT current_state FROM objects ORDER BY object_id").fetchall()
        return [json.loads(row["current_state"]) for row in rows]

    def history(self, object_id: str) -> list[dict[str, Any]]:
        normalized = normalize_id(object_id)
        rows = self.db.execute(
            "SELECT version, state FROM versions WHERE object_id = ? ORDER BY version",
            (normalized,),
        ).fetchall()
        if not rows:
            raise RegistryError(f"unknown object: {normalized}")
        return [
            {"version": int(row["version"]), "state": json.loads(row["state"])} for row in rows
        ]

    def unresolved_dependencies(self, obj: GovernedObject | dict[str, Any]) -> list[str]:
        payload = obj.to_dict() if isinstance(obj, GovernedObject) else obj
        dependencies = [normalize_id(value) for value in payload.get("dependencies", [])]
        if not dependencies:
            return []
        found = {
            row["object_id"]
            for row in self.db.execute(
                f"SELECT object_id FROM objects WHERE object_id IN ({','.join('?' for _ in dependencies)})",
                dependencies,
            )
        }
        return sorted(set(dependencies) - found)

    def _require_dependencies_for_state(
        self, obj: GovernedObject | dict[str, Any], target: LifecycleState
    ) -> None:
        if PROMOTION_RANK.get(target, -1) < PROMOTION_RANK[LifecycleState.EVALUATED]:
            return
        missing = self.unresolved_dependencies(obj)
        if missing:
            raise RegistryError(
                "unresolved dependencies block promotion: " + ", ".join(missing)
            )

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
        target = LifecycleState(new_state)
        refs = sorted({str(value).strip() for value in evidence_refs if str(value).strip()})

        with self._write_transaction():
            normalized, current_version, prior = self._load_current(object_id)
            if current_version != expected_version:
                raise ConcurrencyError(
                    f"{normalized} is at version {current_version}; expected {expected_version}"
                )
            old = LifecycleState(prior["lifecycle_state"])
            resulting = deepcopy(prior)
            for ref in refs:
                if ref not in resulting["evidence_refs"]:
                    resulting["evidence_refs"].append(ref)

            validate_transition(
                old,
                target,
                human_approved=human_approved,
                claim_level=resulting["claim_level"],
                evidence_count=len(resulting["evidence_refs"]),
            )
            self._require_dependencies_for_state(resulting, target)
            resulting["lifecycle_state"] = target.value
            if target is LifecycleState.APPROVED:
                resulting["review_required"] = False

            now = _now()
            new_version = current_version + 1
            state_hash = digest(resulting)
            changed = self.db.execute(
                "UPDATE objects SET current_version = ?, current_state = ?, state_hash = ? "
                "WHERE object_id = ? AND current_version = ?",
                (new_version, _json(resulting), state_hash, normalized, current_version),
            ).rowcount
            if changed != 1:
                raise ConcurrencyError(f"concurrent update detected for {normalized}")
            self.db.execute(
                "INSERT INTO versions VALUES (?, ?, ?, ?, ?)",
                (normalized, new_version, _json(resulting), state_hash, now),
            )
            self._append_event(
                normalized,
                f"transition:{old.value}->{target.value}",
                actor,
                rationale,
                current_version,
                new_version,
                state_hash,
                refs,
                now,
            )
        return deepcopy(resulting)

    def add_evidence(
        self,
        object_id: str,
        evidence_ref: str,
        *,
        expected_version: int,
        actor: str = "human",
    ) -> dict[str, Any]:
        token = str(evidence_ref).strip()
        if not token:
            raise RegistryError("evidence_ref is required")

        with self._write_transaction():
            normalized, current_version, prior = self._load_current(object_id)
            if current_version != expected_version:
                raise ConcurrencyError(
                    f"{normalized} is at version {current_version}; expected {expected_version}"
                )
            resulting = deepcopy(prior)
            if token not in resulting["evidence_refs"]:
                resulting["evidence_refs"].append(token)
            validate_claim_state(
                resulting["claim_level"],
                resulting["lifecycle_state"],
                evidence_count=len(resulting["evidence_refs"]),
            )
            now = _now()
            new_version = current_version + 1
            state_hash = digest(resulting)
            changed = self.db.execute(
                "UPDATE objects SET current_version = ?, current_state = ?, state_hash = ? "
                "WHERE object_id = ? AND current_version = ?",
                (new_version, _json(resulting), state_hash, normalized, current_version),
            ).rowcount
            if changed != 1:
                raise ConcurrencyError(f"concurrent update detected for {normalized}")
            self.db.execute(
                "INSERT INTO versions VALUES (?, ?, ?, ?, ?)",
                (normalized, new_version, _json(resulting), state_hash, now),
            )
            self._append_event(
                normalized,
                "add_evidence",
                actor,
                f"attach evidence {token}",
                current_version,
                new_version,
                state_hash,
                [token],
                now,
            )
        return deepcopy(resulting)

    def events(self, object_id: str | None = None) -> list[dict[str, Any]]:
        if object_id:
            normalized = normalize_id(object_id)
            rows = self.db.execute(
                "SELECT * FROM events WHERE object_id = ? ORDER BY sequence", (normalized,)
            ).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["evidence_refs"] = json.loads(item["evidence_refs"])
            out.append(item)
        return out

    def _append_event(
        self,
        object_id: str,
        action: str,
        actor: str,
        rationale: str,
        prior_version: int | None,
        resulting_version: int,
        resulting_state_hash: str,
        evidence_refs: Iterable[str],
        created_at: str,
    ) -> None:
        prev_row = self.db.execute(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = prev_row["event_hash"] if prev_row else GENESIS_HASH
        payload = {
            "event_id": f"CFX.EVENT.{uuid4().hex}",
            "object_id": object_id,
            "action": action,
            "actor": actor,
            "rationale": rationale,
            "prior_version": prior_version,
            "resulting_version": resulting_version,
            "resulting_state_hash": resulting_state_hash,
            "evidence_refs": sorted(set(evidence_refs)),
            "previous_event_hash": previous,
            "created_at": created_at,
        }
        event_hash = digest(payload)
        self.db.execute(
            "INSERT INTO events (event_id, object_id, action, actor, rationale, prior_version, "
            "resulting_version, resulting_state_hash, evidence_refs, previous_event_hash, "
            "event_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payload["event_id"],
                object_id,
                action,
                actor,
                rationale,
                prior_version,
                resulting_version,
                resulting_state_hash,
                _json(payload["evidence_refs"]),
                previous,
                event_hash,
                created_at,
            ),
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

            version = self.db.execute(
                "SELECT state_hash FROM versions WHERE object_id = ? AND version = ?",
                (event["object_id"], event["resulting_version"]),
            ).fetchone()
            if version is None or event["resulting_state_hash"] != version["state_hash"]:
                return False
            previous = recorded_hash

        for row in self.db.execute(
            "SELECT object_id, current_version, current_state, state_hash FROM objects"
        ):
            current_state = json.loads(row["current_state"])
            if digest(current_state) != row["state_hash"]:
                return False
            version = self.db.execute(
                "SELECT state, state_hash FROM versions WHERE object_id = ? AND version = ?",
                (row["object_id"], row["current_version"]),
            ).fetchone()
            if version is None:
                return False
            if version["state_hash"] != row["state_hash"] or version["state"] != row["current_state"]:
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
