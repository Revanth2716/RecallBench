"""Tests for Pydantic domain models, validation, and interval invariants."""
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.domain.enums import DeletionScope, DeletionType, QueryStatus, UpdatePolicy
from app.domain.models import (
    DeletionEvent,
    Entity,
    FactRecord,
    MemoryQuery,
    QueryPrediction,
    UpdateEvent,
)


def test_entity_creation_valid():
    """Verify valid Entity creation with UTC normalization."""
    entity = Entity(
        id="user_101",
        name="Alice",
        entity_type="user",
        created_at="2026-01-01T05:30:00+05:30",  # string with offset
    )
    assert entity.id == "user_101"
    assert entity.created_at.tzinfo == timezone.utc
    assert entity.created_at.hour == 0  # 05:30 +05:30 is 00:00 UTC


def test_entity_rejects_naive_created_at():
    """Verify Entity creation fails on naive timestamp."""
    with pytest.raises(ValidationError):
        Entity(
            id="user_101",
            name="Alice",
            created_at="2026-01-01T00:00:00",  # naive
        )


def test_fact_record_valid_half_open_interval():
    """Verify valid FactRecord with valid_from < valid_to."""
    fact = FactRecord(
        id="f_01",
        entity_id="u_01",
        attribute="city",
        value="Berlin",
        valid_from="2026-01-01T00:00:00Z",
        valid_to="2026-06-01T00:00:00Z",
        asserted_at="2026-01-01T00:00:00Z",
    )
    assert fact.valid_from < fact.valid_to
    assert fact.version == 1
    assert fact.is_deleted is False


def test_fact_record_rejects_inverted_validity():
    """Verify FactRecord rejects valid_from >= valid_to."""
    with pytest.raises(ValidationError, match="must be strictly earlier than valid_to"):
        FactRecord(
            id="f_01",
            entity_id="u_01",
            attribute="city",
            value="Berlin",
            valid_from="2026-06-01T00:00:00Z",
            valid_to="2026-01-01T00:00:00Z",  # Earlier than valid_from!
            asserted_at="2026-01-01T00:00:00Z",
        )


def test_fact_record_rejects_equal_validity():
    """Verify FactRecord rejects valid_from == valid_to (zero-length interval)."""
    with pytest.raises(ValidationError, match="must be strictly earlier than valid_to"):
        FactRecord(
            id="f_01",
            entity_id="u_01",
            attribute="city",
            value="Berlin",
            valid_from="2026-06-01T00:00:00Z",
            valid_to="2026-06-01T00:00:00Z",  # Equal timestamps!
            asserted_at="2026-01-01T00:00:00Z",
        )


def test_fact_record_rejects_retracted_earlier_than_asserted():
    """Verify FactRecord rejects retracted_at earlier than asserted_at."""
    with pytest.raises(ValidationError, match="cannot be later than retracted_at"):
        FactRecord(
            id="f_01",
            entity_id="u_01",
            attribute="city",
            value="Berlin",
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            asserted_at="2026-06-01T00:00:00Z",
            retracted_at="2026-05-01T00:00:00Z",  # Earlier than asserted_at!
        )


def test_update_event_validation():
    """Verify UpdateEvent model behavior and bound validation."""
    event = UpdateEvent(
        event_id="evt_01",
        entity_id="u_01",
        attribute="city",
        new_value="Munich",
        effective_time="2026-06-01T00:00:00Z",
        valid_to=None,
        asserted_at="2026-06-01T00:00:00Z",
        policy=UpdatePolicy.TEMPORAL_SUPERSEDE,
    )
    assert event.new_value == "Munich"
    assert event.policy == UpdatePolicy.TEMPORAL_SUPERSEDE

    with pytest.raises(ValidationError, match="effective_time must be strictly earlier than valid_to"):
        UpdateEvent(
            event_id="evt_02",
            entity_id="u_01",
            attribute="city",
            new_value="Munich",
            effective_time="2026-06-01T00:00:00Z",
            valid_to="2026-05-01T00:00:00Z",
            asserted_at="2026-06-01T00:00:00Z",
        )


def test_deletion_event_validation():
    """Verify DeletionEvent attributes and defaults."""
    deletion = DeletionEvent(
        event_id="del_01",
        entity_id="u_01",
        attribute="city",
        effective_time="2026-09-01T00:00:00Z",
        asserted_at="2026-09-01T00:00:00Z",
        deletion_type=DeletionType.LOGICAL_TOMBSTONE,
        deletion_scope=DeletionScope.RETROACTIVE_PURGE,
    )
    assert deletion.deletion_type == DeletionType.LOGICAL_TOMBSTONE
    assert deletion.deletion_scope == DeletionScope.RETROACTIVE_PURGE


def test_query_prediction_provenance_fields():
    """Verify QueryPrediction carries adapter-supplied provenance evidence."""
    pred = QueryPrediction(
        query_id="q_01",
        status=QueryStatus.FOUND,
        value="Berlin",
        matched_entity_id="u_01",
        fact_id="f_01",
        latency_ms=1.45,
    )
    assert pred.matched_entity_id == "u_01"
    assert pred.fact_id == "f_01"
    assert pred.latency_ms == 1.45
