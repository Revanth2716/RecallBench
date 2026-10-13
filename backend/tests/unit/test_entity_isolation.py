"""Tests for entity isolation, provenance verification, and homonymous attribute handling."""
import pytest

from app.domain.enums import QueryStatus
from app.domain.models import FactRecord, MemoryQuery
from app.domain.semantics import evaluate_query_against_facts


def test_homonymous_attributes_across_different_entities():
    """Verify two entities with identical attribute values maintain strict identity isolation."""
    # Alice and Bob both have theme = "dark"
    f_alice = FactRecord(
        id="fact_alice_theme",
        entity_id="entity_alice",
        attribute="theme",
        value="dark",
        valid_from="2026-01-01T00:00:00Z",
        asserted_at="2026-01-01T00:00:00Z",
    )
    f_bob = FactRecord(
        id="fact_bob_theme",
        entity_id="entity_bob",
        attribute="theme",
        value="dark",
        valid_from="2026-01-01T00:00:00Z",
        asserted_at="2026-01-01T00:00:00Z",
    )

    all_facts = [f_alice, f_bob]

    # Query for Alice
    q_alice = MemoryQuery(
        query_id="q_alice",
        entity_id="entity_alice",
        attribute="theme",
        as_of_valid_time="2026-06-01T00:00:00Z",
    )
    pred_alice = evaluate_query_against_facts(all_facts, q_alice)
    assert pred_alice.status == QueryStatus.FOUND
    assert pred_alice.value == "dark"
    assert pred_alice.matched_entity_id == "entity_alice"
    assert pred_alice.fact_id == "fact_alice_theme"

    # Query for Bob
    q_bob = MemoryQuery(
        query_id="q_bob",
        entity_id="entity_bob",
        attribute="theme",
        as_of_valid_time="2026-06-01T00:00:00Z",
    )
    pred_bob = evaluate_query_against_facts(all_facts, q_bob)
    assert pred_bob.status == QueryStatus.FOUND
    assert pred_bob.value == "dark"
    assert pred_bob.matched_entity_id == "entity_bob"
    assert pred_bob.fact_id == "fact_bob_theme"


def test_entity_query_miss_does_not_leak_other_entity_data():
    """When querying an entity that has no record, another entity's record for that attribute must NOT leak."""
    f_alice = FactRecord(
        id="fact_alice_secret",
        entity_id="entity_alice",
        attribute="api_token",
        value="sk-alice-secret-token",
        valid_from="2026-01-01T00:00:00Z",
        asserted_at="2026-01-01T00:00:00Z",
    )

    # Bob asks for api_token (Bob has none)
    q_bob = MemoryQuery(
        query_id="q_bob_token",
        entity_id="entity_bob",
        attribute="api_token",
        as_of_valid_time="2026-06-01T00:00:00Z",
    )
    pred_bob = evaluate_query_against_facts([f_alice], q_bob)
    assert pred_bob.status == QueryStatus.NOT_FOUND
    assert pred_bob.value is None
    assert pred_bob.matched_entity_id is None
