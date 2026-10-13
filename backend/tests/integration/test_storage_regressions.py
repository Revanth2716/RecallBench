"""Targeted regression tests for out-of-order event ingestion and assertion-time reconstruction.

Exercises bitemporal invariants and behavioral parity across InMemoryMemoryStore
and SQLiteTemporalMemoryStore.
"""
from typing import Generator
import pytest

from app.domain.enums import (
    DeletionScope,
    DeletionType,
    QueryStatus,
    UpdatePolicy,
)
from app.domain.models import MemoryQuery
from app.domain.protocols import MemoryStoreAdapter
from app.storage.in_memory_store import InMemoryMemoryStore
from app.storage.sqlite_store import SQLiteTemporalMemoryStore


@pytest.fixture(params=["in_memory", "sqlite"])
def store(request, tmp_path) -> Generator[MemoryStoreAdapter, None, None]:
    """Parametrized fixture providing both in-memory and SQLite-backed memory stores."""
    if request.param == "in_memory":
        mem_store = InMemoryMemoryStore()
        yield mem_store
        mem_store.reset()
    elif request.param == "sqlite":
        db_file = str(tmp_path / "test_regressions.sqlite3")
        sql_store = SQLiteTemporalMemoryStore(db_path=db_file)
        yield sql_store
        sql_store.close()


# ==============================================================================
# 1. OUT-OF-ORDER EVENT INGESTION
# ==============================================================================

def test_out_of_order_event_ingestion_valid_times(store: MemoryStoreAdapter):
    """Ingest facts whose valid times arrive out of chronological order.

    Scenario:
    - Step 1 (ingested first at transaction time Ta1):
      Fact for future valid time [2026-06-01, None) -> firmware = 'v2.0'
    - Step 2 (ingested second at transaction time Ta2 > Ta1):
      Fact for past valid time [2026-01-01, 2026-06-01) -> firmware = 'v1.0'

    Verify:
    - Historical query in March 2026 returns 'v1.0'
    - Current/future query in August 2026 returns 'v2.0'
    - Exact boundary at 2026-06-01T00:00:00Z returns 'v2.0'
    - Just before boundary at 2026-05-31T23:59:59.999999Z returns 'v1.0'
    - Before Jan 2026 returns NOT_FOUND
    """
    # 1. Ingest future fact first
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "evt_future",
        "fact_id": "fact_v2",
        "entity_id": "device_01",
        "attribute": "firmware",
        "value": "v2.0",
        "timestamp": "2026-06-01T10:00:00Z",  # transaction time Ta1
        "valid_from": "2026-06-01T00:00:00Z",
        "valid_to": None,
    })

    # 2. Ingest past fact later (out of order relative to valid time)
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "evt_past",
        "fact_id": "fact_v1",
        "entity_id": "device_01",
        "attribute": "firmware",
        "value": "v1.0",
        "timestamp": "2026-06-02T10:00:00Z",  # transaction time Ta2 > Ta1
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": "2026-06-01T00:00:00Z",
    })

    # Historical query in March 2026 -> v1.0
    q_march = MemoryQuery(
        query_id="q_march",
        entity_id="device_01",
        attribute="firmware",
        as_of_valid_time="2026-03-01T00:00:00Z",
    )
    res_march = store.retrieve(q_march)
    assert res_march.status == QueryStatus.FOUND
    assert res_march.value == "v1.0"
    assert res_march.matched_entity_id == "device_01"
    assert res_march.fact_id == "fact_v1"

    # Future query in August 2026 -> v2.0
    q_aug = MemoryQuery(
        query_id="q_aug",
        entity_id="device_01",
        attribute="firmware",
        as_of_valid_time="2026-08-01T00:00:00Z",
    )
    res_aug = store.retrieve(q_aug)
    assert res_aug.status == QueryStatus.FOUND
    assert res_aug.value == "v2.0"
    assert res_aug.matched_entity_id == "device_01"
    assert res_aug.fact_id == "fact_v2"

    # Exact boundary query at 2026-06-01T00:00:00Z -> v2.0 (half-open: v1 expired, v2 started)
    q_exact = MemoryQuery(
        query_id="q_exact",
        entity_id="device_01",
        attribute="firmware",
        as_of_valid_time="2026-06-01T00:00:00Z",
    )
    res_exact = store.retrieve(q_exact)
    assert res_exact.status == QueryStatus.FOUND
    assert res_exact.value == "v2.0"

    # Just before boundary -> v1.0
    q_prev = MemoryQuery(
        query_id="q_prev",
        entity_id="device_01",
        attribute="firmware",
        as_of_valid_time="2026-05-31T23:59:59.999999Z",
    )
    res_prev = store.retrieve(q_prev)
    assert res_prev.status == QueryStatus.FOUND
    assert res_prev.value == "v1.0"

    # Before Jan 2026 -> NOT_FOUND
    q_early = MemoryQuery(
        query_id="q_early",
        entity_id="device_01",
        attribute="firmware",
        as_of_valid_time="2025-12-31T23:59:59Z",
    )
    assert store.retrieve(q_early).status == QueryStatus.NOT_FOUND


def test_out_of_order_retroactive_update_splitting(store: MemoryStoreAdapter):
    """Verify that back-dated updates ingested out of chronological order carve intervals cleanly.

    Timeline sequence:
    1. At Ta1 (Jan 2026): Record base fact valid on [2026-01-01, None) -> salary = 100k
    2. At Ta2 (Aug 2026): Record forward update valid on [2026-08-01, None) -> salary = 120k
    3. At Ta3 (Sep 2026): Ingest out-of-order retro-update valid on [2026-04-01, 2026-06-01) -> salary = 110k (interim bonus)

    The resulting timeline should have:
    - [2026-01-01, 2026-04-01): 100k
    - [2026-04-01, 2026-06-01): 110k
    - [2026-06-01, 2026-08-01): 100k
    - [2026-08-01, None): 120k
    """
    # 1. Base fact
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_base",
        "entity_id": "emp_01",
        "attribute": "salary",
        "value": 100000,
        "timestamp": "2026-01-01T00:00:00Z",
    })

    # 2. Forward update in August
    store.ingest_event({
        "event_type": "UPDATE",
        "event_id": "e_promo",
        "entity_id": "emp_01",
        "attribute": "salary",
        "new_value": 120000,
        "effective_time": "2026-08-01T00:00:00Z",
        "timestamp": "2026-08-01T00:00:00Z",
        "policy": "TEMPORAL_SUPERSEDE",
    })

    # 3. Out-of-order retro update ingested in September for April-June
    store.ingest_event({
        "event_type": "UPDATE",
        "event_id": "e_bonus",
        "entity_id": "emp_01",
        "attribute": "salary",
        "new_value": 110000,
        "effective_time": "2026-04-01T00:00:00Z",
        "valid_to": "2026-06-01T00:00:00Z",
        "timestamp": "2026-09-01T00:00:00Z",
        "policy": "TEMPORAL_SUPERSEDE",
    })

    # Check Feb 2026 -> 100k
    q_feb = MemoryQuery(query_id="q_feb", entity_id="emp_01", attribute="salary", as_of_valid_time="2026-02-01T00:00:00Z")
    assert store.retrieve(q_feb).value == 100000

    # Check May 2026 -> 110k
    q_may = MemoryQuery(query_id="q_may", entity_id="emp_01", attribute="salary", as_of_valid_time="2026-05-01T00:00:00Z")
    assert store.retrieve(q_may).value == 110000

    # Check July 2026 -> 100k
    q_jul = MemoryQuery(query_id="q_jul", entity_id="emp_01", attribute="salary", as_of_valid_time="2026-07-01T00:00:00Z")
    assert store.retrieve(q_jul).value == 100000

    # Check October 2026 -> 120k
    q_oct = MemoryQuery(query_id="q_oct", entity_id="emp_01", attribute="salary", as_of_valid_time="2026-10-01T00:00:00Z")
    assert store.retrieve(q_oct).value == 120000

    # Boundary check at 2026-04-01T00:00:00Z -> 110k
    q_b1 = MemoryQuery(query_id="q_b1", entity_id="emp_01", attribute="salary", as_of_valid_time="2026-04-01T00:00:00Z")
    assert store.retrieve(q_b1).value == 110000

    # Boundary check at 2026-06-01T00:00:00Z -> 100k
    q_b2 = MemoryQuery(query_id="q_b2", entity_id="emp_01", attribute="salary", as_of_valid_time="2026-06-01T00:00:00Z")
    assert store.retrieve(q_b2).value == 100000

    # Boundary check at 2026-08-01T00:00:00Z -> 120k
    q_b3 = MemoryQuery(query_id="q_b3", entity_id="emp_01", attribute="salary", as_of_valid_time="2026-08-01T00:00:00Z")
    assert store.retrieve(q_b3).value == 120000


# ==============================================================================
# 2. ASSERTION-TIME HISTORICAL RECONSTRUCTION
# ==============================================================================

def test_assertion_time_historical_reconstruction_supersede(store: MemoryStoreAdapter):
    """Verify that querying with an as_of_assertion_time coordinate reconstructs
    historical system beliefs prior to subsequent updates/retractions.

    Timeline:
    - At transaction time Ta1 (2026-01-01T12:00:00Z):
      System records that user_investor risk is 'conservative' starting 2026-01-01 open-ended.
    - At transaction time Ta2 (2026-06-01T12:00:00Z):
      System updates risk to 'aggressive' starting 2026-06-01 open-ended.

    Verification questions:
    1. What did the system believe on 2026-03-01 (Ta < Ta2) about the user's risk on 2026-07-01?
       -> At that assertion time, the system had NOT received the update, and believed risk was 'conservative'.
    2. What did the system believe on 2026-07-01 (Ta > Ta2) about the user's risk on 2026-07-01?
       -> At that assertion time, the system had received the update, and knew risk was 'aggressive'.
    3. What did the system believe on 2025-12-01 (Ta < Ta1)?
       -> Nothing had been asserted into the system yet -> NOT_FOUND.
    """
    # 1. Initial assertion at Ta1 = Jan 1, 2026
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "evt_risk_1",
        "fact_id": "fact_risk_1",
        "entity_id": "user_investor",
        "attribute": "risk_tolerance",
        "value": "conservative",
        "timestamp": "2026-01-01T12:00:00Z",  # Ta1
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": None,
    })

    # 2. Superseding assertion at Ta2 = June 1, 2026
    store.ingest_event({
        "event_type": "UPDATE",
        "event_id": "evt_risk_2",
        "entity_id": "user_investor",
        "attribute": "risk_tolerance",
        "new_value": "aggressive",
        "effective_time": "2026-06-01T00:00:00Z",
        "timestamp": "2026-06-01T12:00:00Z",  # Ta2
        "policy": "TEMPORAL_SUPERSEDE",
    })

    # Query 1: Audit query as of system knowledge on March 1, 2026 (Ta < Ta2)
    # Asking about valid time July 1, 2026:
    q_audit_past = MemoryQuery(
        query_id="q_audit_past",
        entity_id="user_investor",
        attribute="risk_tolerance",
        as_of_valid_time="2026-07-01T00:00:00Z",
        as_of_assertion_time="2026-03-01T00:00:00Z",  # Prior to retraction!
    )
    res_past = store.retrieve(q_audit_past)
    assert res_past.status == QueryStatus.FOUND
    assert res_past.value == "conservative"
    assert res_past.fact_id == "fact_risk_1"

    # Query 2: Query as of system knowledge on July 1, 2026 (Ta > Ta2)
    # Asking about valid time July 1, 2026:
    q_audit_present = MemoryQuery(
        query_id="q_audit_present",
        entity_id="user_investor",
        attribute="risk_tolerance",
        as_of_valid_time="2026-07-01T00:00:00Z",
        as_of_assertion_time="2026-07-01T00:00:00Z",  # After retraction!
    )
    res_present = store.retrieve(q_audit_present)
    assert res_present.status == QueryStatus.FOUND
    assert res_present.value == "aggressive"

    # Query 3: Query as of system knowledge before initial assertion (Ta < Ta1)
    q_before_assert = MemoryQuery(
        query_id="q_before_assert",
        entity_id="user_investor",
        attribute="risk_tolerance",
        as_of_valid_time="2026-07-01T00:00:00Z",
        as_of_assertion_time="2025-12-01T00:00:00Z",  # Before system knew anything
    )
    res_before = store.retrieve(q_before_assert)
    assert res_before.status == QueryStatus.NOT_FOUND
    assert res_before.value is None


def test_assertion_time_historical_reconstruction_deletion(store: MemoryStoreAdapter):
    """Verify that retroactive deletion respects assertion time:
    prior to the deletion assertion, the system was aware of the fact.
    After the deletion assertion, the fact is tombstoned/masked.

    Timeline:
    - At Ta1 (2026-01-01T12:00:00Z): Record secret API key.
    - At Ta2 (2026-09-01T12:00:00Z): Assert retroactive deletion purge (GDPR forgotten).

    Verify:
    1. Query as of Ta = 2026-05-01 (before deletion asserted):
       System knew secret API key was valid on 2026-03-01.
    2. Query as of Ta = 2026-10-01 (after deletion asserted):
       Retroactive purge masks secret API key on 2026-03-01 (returns TOMBSTONED_DELETED).
    """
    # 1. Initial assertion
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_key",
        "fact_id": "fact_key",
        "entity_id": "user_sec",
        "attribute": "api_key",
        "value": "secret_abc_123",
        "timestamp": "2026-01-01T12:00:00Z",
        "valid_from": "2026-01-01T00:00:00Z",
    })

    # 2. Retroactive deletion asserted later in September
    store.ingest_event({
        "event_type": "DELETE",
        "event_id": "del_gdpr",
        "entity_id": "user_sec",
        "attribute": "api_key",
        "timestamp": "2026-09-01T12:00:00Z",
        "effective_time": "2026-01-01T00:00:00Z",
        "deletion_type": "LOGICAL_TOMBSTONE",
        "deletion_scope": "RETROACTIVE_PURGE",
    })

    # As of May 2026 assertion time (before deletion was asserted into system):
    q_may = MemoryQuery(
        query_id="q_may",
        entity_id="user_sec",
        attribute="api_key",
        as_of_valid_time="2026-03-01T00:00:00Z",
        as_of_assertion_time="2026-05-01T00:00:00Z",
    )
    res_may = store.retrieve(q_may)
    assert res_may.status == QueryStatus.FOUND
    assert res_may.value == "secret_abc_123"

    # As of October 2026 assertion time (after deletion was asserted):
    q_oct = MemoryQuery(
        query_id="q_oct",
        entity_id="user_sec",
        attribute="api_key",
        as_of_valid_time="2026-03-01T00:00:00Z",
        as_of_assertion_time="2026-10-01T00:00:00Z",
    )
    res_oct = store.retrieve(q_oct)
    assert res_oct.status == QueryStatus.TOMBSTONED_DELETED
    assert res_oct.value is None
