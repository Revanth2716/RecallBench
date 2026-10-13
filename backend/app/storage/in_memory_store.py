"""In-memory baseline memory store implementing MemoryStoreAdapter.

Maintains deterministic in-memory fact collections and evaluates queries
using domain semantics with zero network or disk overhead.
"""
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
    validate_and_normalize_optional_utc,
    validate_and_normalize_utc,
)


class InMemoryMemoryStore:
    """Deterministic in-memory implementation of MemoryStoreAdapter."""

    def __init__(
        self,
        default_contradiction_policy: ContradictionPolicy = ContradictionPolicy.DETERMINISTIC_ABSTAIN,
    ) -> None:
        self.default_contradiction_policy = default_contradiction_policy
        self._facts: Dict[str, FactRecord] = {}

    def reset(self) -> None:
        """Reset internal memory to clean empty state."""
        self._facts.clear()

    def get_all_facts(self) -> List[FactRecord]:
        """Return a copy of all current fact records for inspection/tests."""
        return list(self._facts.values())

    def ingest_event(self, event: Dict[str, Any]) -> None:
        """Ingest a timeline event (INSERT, UPDATE, DELETE)."""
        event_type = event.get("event_type", "INSERT").upper()
        entity_id = event["entity_id"]
        attribute = event.get("attribute")

        # Validate mandatory assertion timestamp
        raw_ts = event.get("timestamp") or event.get("asserted_at")
        if raw_ts is None:
            raise ValueError(f"Event {event.get('event_id')} missing timestamp / asserted_at")
        asserted_at = validate_and_normalize_utc(raw_ts)

        if event_type == "INSERT":
            policy_val = event.get("policy")
            if policy_val in (UpdatePolicy.TEMPORAL_SUPERSEDE, "TEMPORAL_SUPERSEDE"):
                # Delegated to temporal supersede if explicit supersede policy on insert
                self._handle_update(event, asserted_at)
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
            self._facts[new_fact.id] = new_fact

        elif event_type == "UPDATE":
            self._handle_update(event, asserted_at)

        elif event_type == "DELETE":
            self._handle_deletion(event, asserted_at)

        else:
            raise ValueError(f"Unknown event_type: {event_type}")

    def _handle_update(self, event: Dict[str, Any], asserted_at: Any) -> None:
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

        relevant_facts = [
            f for f in self._facts.values()
            if f.entity_id == update.entity_id and f.attribute == update.attribute
        ]
        modified_existing, new_fact = apply_temporal_supersede(relevant_facts, update)

        for f in modified_existing:
            self._facts[f.id] = f
        self._facts[new_fact.id] = new_fact

    def _handle_deletion(self, event: Dict[str, Any], asserted_at: Any) -> None:
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

        target_entity_id = deletion.entity_id
        target_attr = deletion.attribute

        relevant_facts = [
            f for f in self._facts.values()
            if f.entity_id == target_entity_id and (target_attr is None or f.attribute == target_attr)
        ]
        other_facts = [
            f for f in self._facts.values()
            if not (f.entity_id == target_entity_id and (target_attr is None or f.attribute == target_attr))
        ]

        modified = apply_deletion(relevant_facts, deletion)

        # Clear and reconstruct dictionary
        self._facts.clear()
        for f in other_facts:
            self._facts[f.id] = f
        for f in modified:
            self._facts[f.id] = f

    def retrieve(
        self,
        query: MemoryQuery,
        contradiction_policy: Optional[ContradictionPolicy] = None,
    ) -> QueryPrediction:
        """Execute a black-box retrieval query against in-memory facts."""
        start_time = time.perf_counter()

        policy = (
            contradiction_policy
            or query.contradiction_policy
            or self.default_contradiction_policy
        )

        prediction = evaluate_query_against_facts(
            list(self._facts.values()), query, policy
        )
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        pred_data = prediction.model_dump()
        pred_data["latency_ms"] = round(latency_ms, 3)
        return QueryPrediction(**pred_data)
