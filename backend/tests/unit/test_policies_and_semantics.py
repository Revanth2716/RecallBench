"""Tests for domain semantics: updates, contradictions, deletions, and point-in-time queries."""
from datetime import datetime, timezone
import pytest

from app.domain.enums import (
    ContradictionPolicy,
    DeletionScope,
    DeletionType,
    QueryStatus,
    UpdatePolicy,
)
from app.domain.models import DeletionEvent, FactRecord, MemoryQuery, UpdateEvent
from app.domain.semantics import (
    apply_deletion,
    apply_temporal_supersede,
    evaluate_query_against_facts,
    resolve_contradiction,
)


@pytest.fixture
def base_fact() -> FactRecord:
    return FactRecord(
        id="fact_01",
        entity_id="user_alice",
        attribute="city",
        value="Paris",
        valid_from="2026-01-01T00:00:00Z",
        valid_to=None,
        asserted_at="2026-01-01T00:00:00Z",
        version=1,
    )


# --- 1. Update Semantics (TEMPORAL_SUPERSEDE) ---

def test_apply_temporal_supersede_forward(base_fact):
    """Verify standard forward update truncates existing fact and opens new version."""
    update = UpdateEvent(
        event_id="up_01",
        entity_id="user_alice",
        attribute="city",
        new_value="Lyon",
        effective_time="2026-06-01T00:00:00Z",
        asserted_at="2026-06-01T00:00:00Z",
        policy=UpdatePolicy.TEMPORAL_SUPERSEDE,
    )

    modified, new_fact = apply_temporal_supersede([base_fact], update)
    assert new_fact.value == "Lyon"
    assert new_fact.version == 2
    assert new_fact.valid_from == datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert new_fact.valid_to is None

    # Original fact should be retracted and its fragments created
    retracted_original = [f for f in modified if f.id == "fact_01"][0]
    assert retracted_original.retracted_at == datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert retracted_original.superseded_by == new_fact.id

    # The split fragment covering [2026-01-01, 2026-06-01)
    split_frags = [f for f in modified if "split" in f.id]
    assert len(split_frags) == 1
    assert split_frags[0].valid_to == datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert split_frags[0].value == "Paris"


def test_apply_temporal_supersede_retroactive_split(base_fact):
    """Verify back-dated update with finite validity splits existing fact into prefix and suffix."""
    update = UpdateEvent(
        event_id="up_retro",
        entity_id="user_alice",
        attribute="city",
        new_value="Marseille",
        effective_time="2026-03-01T00:00:00Z",
        valid_to="2026-05-01T00:00:00Z",
        asserted_at="2026-07-01T00:00:00Z",
        policy=UpdatePolicy.TEMPORAL_SUPERSEDE,
    )

    modified, new_fact = apply_temporal_supersede([base_fact], update)
    assert new_fact.value == "Marseille"
    assert new_fact.valid_from == datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert new_fact.valid_to == datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)

    # We should have prefix [2026-01-01, 2026-03-01) and suffix [2026-05-01, None)
    split_frags = [f for f in modified if "split" in f.id]
    assert len(split_frags) == 2
    prefix = split_frags[0]
    suffix = split_frags[1]
    assert prefix.valid_from == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert prefix.valid_to == datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert suffix.valid_from == datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert suffix.valid_to is None


# --- 2. Contradiction Resolution Semantics ---

def test_resolve_contradiction_abstain():
    """DETERMINISTIC_ABSTAIN policy returns CONTRADICTION status with None value."""
    f1 = FactRecord(
        id="f1", entity_id="u1", attribute="dept", value="Engineering",
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-01T00:00:00Z"
    )
    f2 = FactRecord(
        id="f2", entity_id="u1", attribute="dept", value="Research",
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-02T00:00:00Z"
    )

    status, matched_fact, value = resolve_contradiction(
        [f1, f2], ContradictionPolicy.DETERMINISTIC_ABSTAIN
    )
    assert status == QueryStatus.CONTRADICTION
    assert matched_fact is None
    assert value is None


def test_resolve_contradiction_last_assertion_wins():
    """LAST_ASSERTION_WINS selects fact with latest asserted_at timestamp."""
    f1 = FactRecord(
        id="f1", entity_id="u1", attribute="dept", value="Engineering",
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-01T00:00:00Z"
    )
    f2 = FactRecord(
        id="f2", entity_id="u1", attribute="dept", value="Research",
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-02T00:00:00Z"
    )

    status, winner, value = resolve_contradiction(
        [f1, f2], ContradictionPolicy.LAST_ASSERTION_WINS
    )
    assert status == QueryStatus.FOUND
    assert winner.id == "f2"
    assert value == "Research"


def test_resolve_contradiction_lww_tie_break():
    """Identical asserted_at timestamps break tie deterministically by min(fact.id)."""
    f_b = FactRecord(
        id="fact_b", entity_id="u1", attribute="dept", value="Sales",
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-01T00:00:00Z"
    )
    f_a = FactRecord(
        id="fact_a", entity_id="u1", attribute="dept", value="Marketing",
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-01T00:00:00Z"
    )

    status, winner, value = resolve_contradiction(
        [f_b, f_a], ContradictionPolicy.LAST_ASSERTION_WINS
    )
    assert status == QueryStatus.FOUND
    assert winner.id == "fact_a"
    assert value == "Marketing"


def test_resolve_contradiction_confidence_weighted():
    """CONFIDENCE_WEIGHTED selects higher confidence fact."""
    f_low = FactRecord(
        id="f_low", entity_id="u1", attribute="status", value="Inactive",
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-02T00:00:00Z",
        confidence=0.4,
    )
    f_high = FactRecord(
        id="f_high", entity_id="u1", attribute="status", value="Active",
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-01T00:00:00Z",
        confidence=0.9,
    )

    status, winner, value = resolve_contradiction(
        [f_low, f_high], ContradictionPolicy.CONFIDENCE_WEIGHTED
    )
    assert status == QueryStatus.FOUND
    assert winner.id == "f_high"
    assert value == "Active"


def test_resolve_contradiction_multivalued():
    """MULTIVALUED_COLLECTION merges values into a deterministic sorted unique list."""
    f1 = FactRecord(
        id="f1", entity_id="u1", attribute="roles", value=["editor"],
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-01T00:00:00Z"
    )
    f2 = FactRecord(
        id="f2", entity_id="u1", attribute="roles", value=["admin", "contributor"],
        valid_from="2026-01-01T00:00:00Z", asserted_at="2026-01-02T00:00:00Z"
    )

    status, _, value = resolve_contradiction(
        [f1, f2], ContradictionPolicy.MULTIVALUED_COLLECTION
    )
    assert status == QueryStatus.FOUND
    assert value == ["admin", "contributor", "editor"]


# --- 3. Deletion Semantics ---

def test_apply_deletion_forward_only_preserves_history():
    """FORWARD_ONLY deletion truncates active fact and preserves past validity."""
    f_past = FactRecord(
        id="f_past", entity_id="u1", attribute="plan", value="basic",
        valid_from="2026-01-01T00:00:00Z", valid_to="2026-04-01T00:00:00Z",
        asserted_at="2026-01-01T00:00:00Z"
    )
    f_active = FactRecord(
        id="f_active", entity_id="u1", attribute="plan", value="pro",
        valid_from="2026-04-01T00:00:00Z", valid_to=None,
        asserted_at="2026-04-01T00:00:00Z"
    )

    del_event = DeletionEvent(
        event_id="del_01", entity_id="u1", attribute="plan",
        effective_time="2026-08-01T00:00:00Z", asserted_at="2026-08-01T00:00:00Z",
        deletion_type=DeletionType.LOGICAL_TOMBSTONE,
        deletion_scope=DeletionScope.FORWARD_ONLY,
    )

    modified = apply_deletion([f_past, f_active], del_event)
    # Past fact remains intact
    assert any(f.id == "f_past" and f.valid_to == datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc) for f in modified)

    # Active fact was truncated to 2026-08-01
    truncated = [f for f in modified if f.id == "f_active"][0]
    assert truncated.valid_to == datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert truncated.is_deleted is False


def test_apply_deletion_retroactive_purge_tombstones_all():
    """RETROACTIVE_PURGE marks all facts as tombstoned."""
    f_past = FactRecord(
        id="f_past", entity_id="u1", attribute="email", value="old@test.com",
        valid_from="2026-01-01T00:00:00Z", valid_to="2026-04-01T00:00:00Z",
        asserted_at="2026-01-01T00:00:00Z"
    )
    del_event = DeletionEvent(
        event_id="del_purge", entity_id="u1", attribute="email",
        effective_time="2026-08-01T00:00:00Z", asserted_at="2026-08-01T00:00:00Z",
        deletion_type=DeletionType.LOGICAL_TOMBSTONE,
        deletion_scope=DeletionScope.RETROACTIVE_PURGE,
    )

    modified = apply_deletion([f_past], del_event)
    assert len(modified) == 1
    assert modified[0].is_deleted is True
    assert modified[0].deletion_scope == DeletionScope.RETROACTIVE_PURGE


# --- 4. Query Evaluation Against Facts ---

def test_evaluate_query_historical_point_in_time():
    """Evaluate point-in-time retrieval returns the historically valid fact."""
    f1 = FactRecord(
        id="f1", entity_id="u1", attribute="loc", value="NYC",
        valid_from="2026-01-01T00:00:00Z", valid_to="2026-06-01T00:00:00Z",
        asserted_at="2026-01-01T00:00:00Z"
    )
    f2 = FactRecord(
        id="f2", entity_id="u1", attribute="loc", value="London",
        valid_from="2026-06-01T00:00:00Z", valid_to=None,
        asserted_at="2026-06-01T00:00:00Z"
    )

    # Query historically at March 2026
    query = MemoryQuery(
        query_id="q1", entity_id="u1", attribute="loc",
        as_of_valid_time="2026-03-01T00:00:00Z"
    )
    pred = evaluate_query_against_facts([f1, f2], query)
    assert pred.status == QueryStatus.FOUND
    assert pred.value == "NYC"
    assert pred.matched_entity_id == "u1"
    assert pred.fact_id == "f1"

    # Query currently at July 2026
    query_now = MemoryQuery(
        query_id="q2", entity_id="u1", attribute="loc",
        as_of_valid_time="2026-07-01T00:00:00Z"
    )
    pred_now = evaluate_query_against_facts([f1, f2], query_now)
    assert pred_now.status == QueryStatus.FOUND
    assert pred_now.value == "London"
    assert pred_now.fact_id == "f2"


def test_evaluate_query_exact_boundary():
    """Query exactly at the transition boundary returns the new fact."""
    f1 = FactRecord(
        id="f1", entity_id="u1", attribute="loc", value="NYC",
        valid_from="2026-01-01T00:00:00Z", valid_to="2026-06-01T00:00:00Z",
        asserted_at="2026-01-01T00:00:00Z"
    )
    f2 = FactRecord(
        id="f2", entity_id="u1", attribute="loc", value="London",
        valid_from="2026-06-01T00:00:00Z", valid_to=None,
        asserted_at="2026-06-01T00:00:00Z"
    )

    # Exactly at boundary 2026-06-01T00:00:00Z -> f1 expired, f2 begins
    query = MemoryQuery(
        query_id="q_bound", entity_id="u1", attribute="loc",
        as_of_valid_time="2026-06-01T00:00:00Z"
    )
    pred = evaluate_query_against_facts([f1, f2], query)
    assert pred.status == QueryStatus.FOUND
    assert pred.value == "London"
    assert pred.fact_id == "f2"


def test_evaluate_query_masks_tombstone():
    """Normal retrieval masks tombstoned record and returns TOMBSTONED_DELETED with None value."""
    f_tomb = FactRecord(
        id="f_tomb", entity_id="u1", attribute="phone", value="555-1234",
        valid_from="2026-01-01T00:00:00Z", valid_to=None,
        asserted_at="2026-01-01T00:00:00Z", is_deleted=True,
        deleted_at="2026-05-01T00:00:00Z", deletion_scope=DeletionScope.RETROACTIVE_PURGE
    )

    query = MemoryQuery(
        query_id="q_tomb", entity_id="u1", attribute="phone",
        as_of_valid_time="2026-02-01T00:00:00Z", include_tombstones=False
    )
    pred = evaluate_query_against_facts([f_tomb], query)
    assert pred.status == QueryStatus.TOMBSTONED_DELETED
    assert pred.value is None  # Payload is NEVER leaked in normal retrieval!
