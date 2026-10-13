"""Pytest fixtures for RecallBench domain tests."""
from datetime import datetime, timezone
import pytest

from app.domain.models import Entity, FactRecord


@pytest.fixture
def sample_utc_time() -> datetime:
    return datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_entity(sample_utc_time: datetime) -> Entity:
    return Entity(
        id="user_test_01",
        name="Test User",
        entity_type="user",
        created_at=sample_utc_time,
        metadata={"tier": "premium"},
    )


@pytest.fixture
def sample_fact(sample_utc_time: datetime) -> FactRecord:
    return FactRecord(
        id="fact_001",
        entity_id="user_test_01",
        attribute="preferred_language",
        value="Python",
        valid_from=sample_utc_time,
        valid_to=None,
        asserted_at=sample_utc_time,
        version=1,
    )
