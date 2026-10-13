"""SQLite-backed temporal memory store implementing MemoryStoreAdapter.

Persists facts in SQLite tables using standard-library sqlite3,
parameterized queries, transaction safety, and WAL mode.
"""
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from app.domain.enums import (
    ContradictionPolicy,
    DeletionScope,
    DeletionType,
    QueryStatus,
    UpdatePolicy,
)
from app.domain.models import DeletionEvent, FactRecord, MemoryQuery, QueryPrediction, UpdateEvent
from app.domain.protocols import MemoryStoreAdapter
from app.domain.semantics import (
    apply_deletion,
    apply_temporal_supersede,
    evaluate_query_against_facts,
)
from app.domain.timestamps import (
    utc_now,
    validate_and_normalize_optional_utc,
    validate_and_normalize_utc,
)
from app.storage.sqlite_db import get_connection


UPSERT_FACT_SQL = """
INSERT INTO facts (
    id, entity_id, attribute, value_json, valid_from, valid_to,
    asserted_at, retracted_at, version, superseded_by, is_deleted,
    deleted_at, deletion_scope, confidence, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    entity_id = excluded.entity_id,
    attribute = excluded.attribute,
    value_json = excluded.value_json,
    valid_from = excluded.valid_from,
    valid_to = excluded.valid_to,
    asserted_at = excluded.asserted_at,
    retracted_at = excluded.retracted_at,
    version = excluded.version,
    superseded_by = excluded.superseded_by,
    is_deleted = excluded.is_deleted,
    deleted_at = excluded.deleted_at,
    deletion_scope = excluded.deletion_scope,
    confidence = excluded.confidence;
"""


def _row_to_fact(row: sqlite3.Row) -> FactRecord:
    """Deserialize an SQLite row into a domain FactRecord."""
    return FactRecord(
        id=row["id"],
        entity_id=row["entity_id"],
        attribute=row["attribute"],
        value=json.loads(row["value_json"]),
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        asserted_at=row["asserted_at"],
        retracted_at=row["retracted_at"],
        version=row["version"],
        superseded_by=row["superseded_by"],
        is_deleted=bool(row["is_deleted"]),
        deleted_at=row["deleted_at"],
        deletion_scope=DeletionScope(row["deletion_scope"]) if row["deletion_scope"] else None,
        confidence=float(row["confidence"]),
    )


class SQLiteTemporalMemoryStore:
    """SQLite implementation of MemoryStoreAdapter with ACID persistence."""

    def __init__(
        self,
        db_path: str = ":memory:",
        default_contradiction_policy: ContradictionPolicy = ContradictionPolicy.DETERMINISTIC_ABSTAIN,
    ) -> None:
        self.db_path = db_path
        self.default_contradiction_policy = default_contradiction_policy
        self.conn = get_connection(db_path)

    def close(self) -> None:
        """Close the SQLite connection."""
        self.conn.close()

    def reset(self) -> None:
        """Clear all facts from storage."""
        with self.conn:
            self.conn.execute("DELETE FROM facts;")

    def get_all_facts(self) -> List[FactRecord]:
        """Query all facts from the SQLite database."""
        cursor = self.conn.execute("SELECT * FROM facts;")
        return [_row_to_fact(row) for row in cursor.fetchall()]

    def _upsert_fact(self, fact: FactRecord) -> None:
        """Execute a single upsert statement for a FactRecord."""
        self.conn.execute(
            UPSERT_FACT_SQL,
            (
                fact.id,
                fact.entity_id,
                fact.attribute,
                json.dumps(fact.value, ensure_ascii=False),
                fact.valid_from.isoformat(),
                fact.valid_to.isoformat() if fact.valid_to else None,
                fact.asserted_at.isoformat(),
                fact.retracted_at.isoformat() if fact.retracted_at else None,
                fact.version,
                fact.superseded_by,
                1 if fact.is_deleted else 0,
                fact.deleted_at.isoformat() if fact.deleted_at else None,
                fact.deletion_scope.value if fact.deletion_scope else None,
                fact.confidence,
                utc_now().isoformat(),
            ),
        )

    def _get_entity_attribute_facts(self, entity_id: str, attribute: str) -> List[FactRecord]:
        cursor = self.conn.execute(
            "SELECT * FROM facts WHERE entity_id = ? AND attribute = ?;",
            (entity_id, attribute),
        )
        return [_row_to_fact(row) for row in cursor.fetchall()]

    def _get_entity_facts(self, entity_id: str, attribute: Optional[str] = None) -> List[FactRecord]:
        if attribute is not None:
            return self._get_entity_attribute_facts(entity_id, attribute)
        cursor = self.conn.execute(
            "SELECT * FROM facts WHERE entity_id = ?;",
            (entity_id,),
        )
        return [_row_to_fact(row) for row in cursor.fetchall()]

    def ingest_event(self, event: Dict[str, Any]) -> None:
        """Ingest a timeline event with transaction isolation."""
        event_type = event.get("event_type", "INSERT").upper()
        entity_id = event["entity_id"]
        attribute = event.get("attribute")

        raw_ts = event.get("timestamp") or event.get("asserted_at")
        if raw_ts is None:
            raise ValueError(f"Event {event.get('event_id')} missing timestamp / asserted_at")
        asserted_at = validate_and_normalize_utc(raw_ts)

        with self.conn:
            if event_type == "INSERT":
                policy_val = event.get("policy")
                if policy_val in (UpdatePolicy.TEMPORAL_SUPERSEDE, "TEMPORAL_SUPERSEDE"):
                    self._handle_update_in_tx(event, asserted_at)
                    return

                raw_valid_from = event.get("valid_from")
                valid_from = (
                    validate_and_normalize_utc(raw_valid_from)
                    if raw_valid_from is not None
                    else asserted_at
                )
                valid_to = validate_and_normalize_optional_utc(event.get("valid_to"))

                fact_id = event.get("fact_id") or f"fact_{event['event_id']}"
                new_fact = FactRecord(
                    id=fact_id,
                    entity_id=entity_id,
                    attribute=attribute,  # type: ignore[arg-type]
                    value=event["value"],
                    valid_from=valid_from,
                    valid_to=valid_to,
                    asserted_at=asserted_at,
                    retracted_at=None,
                    version=event.get("version", 1),
                    superseded_by=None,
                    is_deleted=False,
                    confidence=float(event.get("confidence", 1.0)),
                )
                self._upsert_fact(new_fact)

            elif event_type == "UPDATE":
                self._handle_update_in_tx(event, asserted_at)

            elif event_type == "DELETE":
                self._handle_deletion_in_tx(event, asserted_at)

            else:
                raise ValueError(f"Unknown event_type: {event_type}")

    def _handle_update_in_tx(self, event: Dict[str, Any], asserted_at: Any) -> None:
        raw_eff = event.get("effective_time") or event.get("timestamp") or asserted_at
        effective_time = validate_and_normalize_utc(raw_eff)
        valid_to = validate_and_normalize_optional_utc(event.get("valid_to"))

        val = event.get("new_value") if "new_value" in event else event.get("value")
        policy = UpdatePolicy(event.get("policy", UpdatePolicy.TEMPORAL_SUPERSEDE))

        update = UpdateEvent(
            event_id=event["event_id"],
            entity_id=event["entity_id"],
            attribute=event["attribute"],
            new_value=val,
            effective_time=effective_time,
            valid_to=valid_to,
            asserted_at=asserted_at,
            policy=policy,
            confidence=float(event.get("confidence", 1.0)),
        )

        relevant_facts = self._get_entity_attribute_facts(update.entity_id, update.attribute)
        modified_existing, new_fact = apply_temporal_supersede(relevant_facts, update)

        for f in modified_existing:
            self._upsert_fact(f)
        self._upsert_fact(new_fact)

    def _handle_deletion_in_tx(self, event: Dict[str, Any], asserted_at: Any) -> None:
        raw_eff = event.get("effective_time") or event.get("timestamp") or asserted_at
        effective_time = validate_and_normalize_utc(raw_eff)

        del_type = DeletionType(event.get("deletion_type", DeletionType.LOGICAL_TOMBSTONE))
        del_scope = DeletionScope(event.get("deletion_scope", DeletionScope.FORWARD_ONLY))

        deletion = DeletionEvent(
            event_id=event["event_id"],
            entity_id=event["entity_id"],
            attribute=event.get("attribute"),
            deletion_type=del_type,
            deletion_scope=del_scope,
            effective_time=effective_time,
            asserted_at=asserted_at,
            reason=event.get("reason"),
        )

        relevant_facts = self._get_entity_facts(deletion.entity_id, deletion.attribute)
        prior_ids = {f.id for f in relevant_facts}

        modified = apply_deletion(relevant_facts, deletion)
        modified_ids = {f.id for f in modified}

        # Any facts missing from modified were physically purged
        purged_ids = prior_ids - modified_ids
        for pid in purged_ids:
            self.conn.execute("DELETE FROM facts WHERE id = ?;", (pid,))

        for f in modified:
            self._upsert_fact(f)

    def retrieve(
        self,
        query: MemoryQuery,
        contradiction_policy: Optional[ContradictionPolicy] = None,
    ) -> QueryPrediction:
        """Execute a black-box retrieval query against SQLite-backed facts."""
        start_time = time.perf_counter()

        policy = (
            contradiction_policy
            or query.contradiction_policy
            or self.default_contradiction_policy
        )

        # Retrieve candidates by entity and attribute
        candidates = self._get_entity_attribute_facts(query.entity_id, query.attribute)

        prediction = evaluate_query_against_facts(candidates, query, policy)
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        pred_data = prediction.model_dump()
        pred_data["latency_ms"] = round(latency_ms, 3)
        return QueryPrediction(**pred_data)
