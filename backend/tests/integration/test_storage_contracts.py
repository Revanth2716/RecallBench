"""Contract test suite running identically against InMemoryMemoryStore and SQLiteTemporalMemoryStore.

Enforces behavioral parity, temporal correctness, entity isolation,
bitemporal coordinates, and deletion compliance.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Generator
import pytest

from app.domain.enums import (
    ContradictionPolicy,
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
        db_file = str(tmp_path / "test_contract.sqlite3")
        sql_store = SQLiteTemporalMemoryStore(db_path=db_file)
        yield sql_store
        sql_store.close()


# --- 1. Basic Ingestion & Historical vs Current Recall ---

def test_insert_update_historical_and_current_recall(store: MemoryStoreAdapter):
    """Verify insert -> update -> historical point-in-time and current query parity."""
    # 1. Insert original fact
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "evt_01",
        "entity_id": "user_42",
        "attribute": "location",
        "value": "New York",
        "timestamp": "2026-01-01T00:00:00Z",
    })

    # 2. Update with temporal supersede at June 2026
    store.ingest_event({
        "event_type": "UPDATE",
        "event_id": "evt_02",
        "entity_id": "user_42",
        "attribute": "location",
        "new_value": "London",
        "timestamp": "2026-06-01T00:00:00Z",
        "policy": "TEMPORAL_SUPERSEDE",
    })

    # Historical query in March 2026 must return New York
    q_hist = MemoryQuery(
        query_id="q_hist",
        entity_id="user_42",
        attribute="location",
        as_of_valid_time="2026-03-01T00:00:00Z",
    )
    res_hist = store.retrieve(q_hist)
    assert res_hist.status == QueryStatus.FOUND
    assert res_hist.value == "New York"
    assert res_hist.matched_entity_id == "user_42"

    # Current query in August 2026 must return London
    q_curr = MemoryQuery(
        query_id="q_curr",
        entity_id="user_42",
        attribute="location",
        as_of_valid_time="2026-08-01T00:00:00Z",
    )
    res_curr = store.retrieve(q_curr)
    assert res_curr.status == QueryStatus.FOUND
    assert res_curr.value == "London"
    assert res_curr.matched_entity_id == "user_42"


# --- 2. Retroactive Interval Splitting ---

def test_retroactive_interval_splitting(store: MemoryStoreAdapter):
    """Verify back-dated finite update carves an interval in two (prefix and suffix)."""
    # Base fact valid from Jan 2026 open-ended
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_base",
        "entity_id": "user_emp",
        "attribute": "status",
        "value": "active",
        "timestamp": "2026-01-01T00:00:00Z",
    })

    # Retroactive update recorded in July saying employee was on sabbatical in March-May
    store.ingest_event({
        "event_type": "UPDATE",
        "event_id": "e_retro",
        "entity_id": "user_emp",
        "attribute": "status",
        "new_value": "sabbatical",
        "effective_time": "2026-03-01T00:00:00Z",
        "valid_to": "2026-05-01T00:00:00Z",
        "timestamp": "2026-07-01T00:00:00Z",
    })

    # February (prefix) -> active
    q_feb = MemoryQuery(query_id="q_feb", entity_id="user_emp", attribute="status", as_of_valid_time="2026-02-01T00:00:00Z")
    assert store.retrieve(q_feb).value == "active"

    # April (carved interval) -> sabbatical
    q_apr = MemoryQuery(query_id="q_apr", entity_id="user_emp", attribute="status", as_of_valid_time="2026-04-01T00:00:00Z")
    assert store.retrieve(q_apr).value == "sabbatical"

    # June (suffix) -> active
    q_jun = MemoryQuery(query_id="q_jun", entity_id="user_emp", attribute="status", as_of_valid_time="2026-06-01T00:00:00Z")
    assert store.retrieve(q_jun).value == "active"


# --- 3. Exact Half-Open Interval Boundaries ---

def test_exact_interval_boundary_behavior(store: MemoryStoreAdapter):
    """Verify half-open boundary: point at valid_to returns new fact, not expired fact."""
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_v1",
        "entity_id": "user_tier",
        "attribute": "tier",
        "value": "free",
        "timestamp": "2026-01-01T00:00:00Z",
    })

    store.ingest_event({
        "event_type": "UPDATE",
        "event_id": "e_v2",
        "entity_id": "user_tier",
        "attribute": "tier",
        "new_value": "pro",
        "effective_time": "2026-06-01T00:00:00Z",
        "timestamp": "2026-06-01T00:00:00Z",
    })

    # Exactly at boundary 2026-06-01T00:00:00Z -> must return 'pro'
    q_exact = MemoryQuery(
        query_id="q_exact",
        entity_id="user_tier",
        attribute="tier",
        as_of_valid_time="2026-06-01T00:00:00Z",
    )
    res_exact = store.retrieve(q_exact)
    assert res_exact.value == "pro"

    # One microsecond before boundary -> must return 'free'
    q_prev = MemoryQuery(
        query_id="q_prev",
        entity_id="user_tier",
        attribute="tier",
        as_of_valid_time="2026-05-31T23:59:59.999999Z",
    )
    res_prev = store.retrieve(q_prev)
    assert res_prev.value == "free"


# --- 4. Simultaneous and Out-of-Order Ingestion ---

def test_simultaneous_events_tie_break(store: MemoryStoreAdapter):
    """Verify simultaneous assertions break ties deterministically by min(fact_id)."""
    # Insert two conflicting facts with identical timestamps
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "evt_z",
        "fact_id": "fact_z",
        "entity_id": "u_sim",
        "attribute": "role",
        "value": "viewer",
        "timestamp": "2026-01-01T00:00:00Z",
        "confidence": 1.0,
    })
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "evt_a",
        "fact_id": "fact_a",
        "entity_id": "u_sim",
        "attribute": "role",
        "value": "editor",
        "timestamp": "2026-01-01T00:00:00Z",
        "confidence": 1.0,
    })

    # Under LAST_ASSERTION_WINS, tied timestamp falls back to min(fact_id) -> 'fact_a'
    q = MemoryQuery(
        query_id="q_sim",
        entity_id="u_sim",
        attribute="role",
        as_of_valid_time="2026-01-01T00:00:00Z",
        contradiction_policy=ContradictionPolicy.LAST_ASSERTION_WINS,
    )
    res = store.retrieve(q)
    assert res.status == QueryStatus.FOUND
    assert res.value == "editor"
    assert res.fact_id == "fact_a"


# --- 5. All Contradiction Policies ---

def test_all_contradiction_policies(store: MemoryStoreAdapter):
    """Verify DETERMINISTIC_ABSTAIN, LWW, CONFIDENCE, and MULTIVALUED across stores."""
    # Seed two conflicting facts
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "f_low",
        "fact_id": "f_low",
        "entity_id": "u_cp",
        "attribute": "title",
        "value": "Staff Engineer",
        "timestamp": "2026-01-01T00:00:00Z",
        "confidence": 0.5,
    })
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "f_high",
        "fact_id": "f_high",
        "entity_id": "u_cp",
        "attribute": "title",
        "value": "Principal Engineer",
        "timestamp": "2026-01-02T00:00:00Z",
        "confidence": 0.95,
    })

    # 1. DETERMINISTIC_ABSTAIN
    q_abs = MemoryQuery(
        query_id="q_abs", entity_id="u_cp", attribute="title",
        as_of_valid_time="2026-01-03T00:00:00Z",
        contradiction_policy=ContradictionPolicy.DETERMINISTIC_ABSTAIN,
    )
    res_abs = store.retrieve(q_abs)
    assert res_abs.status == QueryStatus.CONTRADICTION
    assert res_abs.value is None

    # 2. LAST_ASSERTION_WINS (f_high asserted on Jan 2)
    q_lww = MemoryQuery(
        query_id="q_lww", entity_id="u_cp", attribute="title",
        as_of_valid_time="2026-01-03T00:00:00Z",
        contradiction_policy=ContradictionPolicy.LAST_ASSERTION_WINS,
    )
    res_lww = store.retrieve(q_lww)
    assert res_lww.status == QueryStatus.FOUND
    assert res_lww.value == "Principal Engineer"

    # 3. CONFIDENCE_WEIGHTED (f_high has 0.95 vs 0.5)
    q_conf = MemoryQuery(
        query_id="q_conf", entity_id="u_cp", attribute="title",
        as_of_valid_time="2026-01-03T00:00:00Z",
        contradiction_policy=ContradictionPolicy.CONFIDENCE_WEIGHTED,
    )
    res_conf = store.retrieve(q_conf)
    assert res_conf.status == QueryStatus.FOUND
    assert res_conf.value == "Principal Engineer"

    # 4. MULTIVALUED_COLLECTION
    q_multi = MemoryQuery(
        query_id="q_multi", entity_id="u_cp", attribute="title",
        as_of_valid_time="2026-01-03T00:00:00Z",
        contradiction_policy=ContradictionPolicy.MULTIVALUED_COLLECTION,
    )
    res_multi = store.retrieve(q_multi)
    assert res_multi.status == QueryStatus.FOUND
    assert res_multi.value == ["Principal Engineer", "Staff Engineer"]


# --- 6. Entity Isolation & Homonymous Attributes ---

def test_entity_isolation_with_identical_values(store: MemoryStoreAdapter):
    """Verify distinct entities with identical values maintain strict provenance isolation."""
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_alice",
        "fact_id": "f_alice_country",
        "entity_id": "entity_alice",
        "attribute": "country",
        "value": "IN",
        "timestamp": "2026-01-01T00:00:00Z",
    })
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_bob",
        "fact_id": "f_bob_country",
        "entity_id": "entity_bob",
        "attribute": "country",
        "value": "IN",
        "timestamp": "2026-01-01T00:00:00Z",
    })

    # Query Alice
    q_alice = MemoryQuery(query_id="qa", entity_id="entity_alice", attribute="country", as_of_valid_time="2026-03-01T00:00:00Z")
    res_alice = store.retrieve(q_alice)
    assert res_alice.value == "IN"
    assert res_alice.matched_entity_id == "entity_alice"
    assert res_alice.fact_id == "f_alice_country"

    # Query Bob
    q_bob = MemoryQuery(query_id="qb", entity_id="entity_bob", attribute="country", as_of_valid_time="2026-03-01T00:00:00Z")
    res_bob = store.retrieve(q_bob)
    assert res_bob.value == "IN"
    assert res_bob.matched_entity_id == "entity_bob"
    assert res_bob.fact_id == "f_bob_country"

    # Query non-existent Charlie
    q_charlie = MemoryQuery(query_id="qc", entity_id="entity_charlie", attribute="country", as_of_valid_time="2026-03-01T00:00:00Z")
    res_charlie = store.retrieve(q_charlie)
    assert res_charlie.status == QueryStatus.NOT_FOUND
    assert res_charlie.value is None


# --- 7. Forward-Only Logical Deletion ---

def test_forward_only_logical_deletion(store: MemoryStoreAdapter):
    """FORWARD_ONLY deletion preserves historical validity and masks future retrieval."""
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_sub",
        "entity_id": "u_sub",
        "attribute": "plan",
        "value": "premium",
        "timestamp": "2026-01-01T00:00:00Z",
    })

    store.ingest_event({
        "event_type": "DELETE",
        "event_id": "del_sub",
        "entity_id": "u_sub",
        "attribute": "plan",
        "effective_time": "2026-06-01T00:00:00Z",
        "timestamp": "2026-06-01T00:00:00Z",
        "deletion_type": "LOGICAL_TOMBSTONE",
        "deletion_scope": "FORWARD_ONLY",
    })

    # Historical query before deletion -> valid
    q_hist = MemoryQuery(query_id="q_h", entity_id="u_sub", attribute="plan", as_of_valid_time="2026-03-01T00:00:00Z")
    res_hist = store.retrieve(q_hist)
    assert res_hist.status == QueryStatus.FOUND
    assert res_hist.value == "premium"

    # Query after deletion -> masked
    q_del = MemoryQuery(query_id="q_d", entity_id="u_sub", attribute="plan", as_of_valid_time="2026-08-01T00:00:00Z")
    res_del = store.retrieve(q_del)
    assert res_del.status in (QueryStatus.NOT_FOUND, QueryStatus.TOMBSTONED_DELETED)
    assert res_del.value is None


# --- 8. Retroactive Logical Deletion ---

def test_retroactive_logical_deletion(store: MemoryStoreAdapter):
    """RETROACTIVE_PURGE completely masks past, present, and future fact payloads."""
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_pii",
        "entity_id": "u_pii",
        "attribute": "ssn",
        "value": "000-12-3456",
        "timestamp": "2026-01-01T00:00:00Z",
    })

    store.ingest_event({
        "event_type": "DELETE",
        "event_id": "del_gdpr",
        "entity_id": "u_pii",
        "attribute": "ssn",
        "effective_time": "2026-06-01T00:00:00Z",
        "timestamp": "2026-06-01T00:00:00Z",
        "deletion_type": "LOGICAL_TOMBSTONE",
        "deletion_scope": "RETROACTIVE_PURGE",
    })

    # Query in the past (before deletion occurred) -> payload MUST be masked!
    q_past = MemoryQuery(query_id="qp", entity_id="u_pii", attribute="ssn", as_of_valid_time="2026-03-01T00:00:00Z")
    res_past = store.retrieve(q_past)
    assert res_past.status == QueryStatus.TOMBSTONED_DELETED
    assert res_past.value is None

    # Query in the future -> masked
    q_fut = MemoryQuery(query_id="qf", entity_id="u_pii", attribute="ssn", as_of_valid_time="2026-09-01T00:00:00Z")
    res_fut = store.retrieve(q_fut)
    assert res_fut.status == QueryStatus.TOMBSTONED_DELETED
    assert res_fut.value is None


# --- 9. Physical Row Removal ---

def test_physical_record_removal(store: MemoryStoreAdapter):
    """PHYSICAL_PURGE removes records from storage tables."""
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_phys",
        "entity_id": "u_phys",
        "attribute": "temp_code",
        "value": "XYZ-999",
        "timestamp": "2026-01-01T00:00:00Z",
    })

    # Execute physical purge
    store.ingest_event({
        "event_type": "DELETE",
        "event_id": "del_phys",
        "entity_id": "u_phys",
        "attribute": "temp_code",
        "effective_time": "2026-01-01T00:00:00Z",
        "timestamp": "2026-01-02T00:00:00Z",
        "deletion_type": "PHYSICAL_PURGE",
        "deletion_scope": "RETROACTIVE_PURGE",
    })

    q = MemoryQuery(query_id="qp", entity_id="u_phys", attribute="temp_code", as_of_valid_time="2026-01-01T12:00:00Z")
    res = store.retrieve(q)
    assert res.status == QueryStatus.NOT_FOUND
    assert res.value is None


# --- 10. SQLite Persistence Across Reinitialization ---

def test_sqlite_persistence_across_reinitialization(tmp_path):
    """Verify facts and tombstones persist across closing and re-opening SQLite store."""
    db_file = str(tmp_path / "persist_test.sqlite3")

    # Instance 1: write data
    store1 = SQLiteTemporalMemoryStore(db_path=db_file)
    store1.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_persist",
        "entity_id": "u_pers",
        "attribute": "setting",
        "value": "dark_mode",
        "timestamp": "2026-01-01T00:00:00Z",
    })
    store1.close()

    # Instance 2: reopen same file
    store2 = SQLiteTemporalMemoryStore(db_path=db_file)
    q = MemoryQuery(query_id="qp", entity_id="u_pers", attribute="setting", as_of_valid_time="2026-02-01T00:00:00Z")
    res = store2.retrieve(q)
    assert res.status == QueryStatus.FOUND
    assert res.value == "dark_mode"
    assert res.matched_entity_id == "u_pers"

    # Verify physical row in SQLite table
    cursor = store2.conn.execute("SELECT COUNT(*) FROM facts WHERE entity_id = 'u_pers';")
    assert cursor.fetchone()[0] == 1
    store2.close()


# --- 11. Rejection of Naive Timestamps ---

def test_store_rejects_naive_timestamp(store: MemoryStoreAdapter):
    """Verify ingest_event rejects naive ISO string without timezone offset."""
    with pytest.raises(ValueError, match="Naive timestamp rejected"):
        store.ingest_event({
            "event_type": "INSERT",
            "event_id": "e_err",
            "entity_id": "u_err",
            "attribute": "val",
            "value": 123,
            "timestamp": "2026-01-01T00:00:00",  # naive
        })


# --- 12. Store Reset ---

def test_store_reset(store: MemoryStoreAdapter):
    """Verify reset() empties all stored records."""
    store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_reset",
        "entity_id": "u_rst",
        "attribute": "val",
        "value": "hello",
        "timestamp": "2026-01-01T00:00:00Z",
    })
    store.reset()
    q = MemoryQuery(query_id="qr", entity_id="u_rst", attribute="val", as_of_valid_time="2026-02-01T00:00:00Z")
    assert store.retrieve(q).status == QueryStatus.NOT_FOUND


# --- 13. Rejection of Inverted Intervals ---

def test_store_rejects_inverted_valid_interval(store: MemoryStoreAdapter):
    """Verify ingest_event rejects an inverted valid interval (valid_from >= valid_to)."""
    with pytest.raises(ValueError, match="strictly earlier than valid_to"):
        store.ingest_event({
            "event_type": "INSERT",
            "event_id": "e_inv",
            "entity_id": "u_inv",
            "attribute": "status",
            "value": "error",
            "timestamp": "2026-01-01T00:00:00Z",
            "valid_from": "2026-06-01T00:00:00Z",
            "valid_to": "2026-01-01T00:00:00Z",
        })


# --- 14. Transaction Safety and Rollback on Failure ---

def test_sqlite_transaction_rollback_on_failure(tmp_path):
    """Verify that if an error occurs during ingestion in SQLite, changes are rolled back cleanly."""
    db_file = str(tmp_path / "rollback_test.sqlite3")
    sql_store = SQLiteTemporalMemoryStore(db_path=db_file)

    # Initial valid insert
    sql_store.ingest_event({
        "event_type": "INSERT",
        "event_id": "e_init",
        "entity_id": "u_tx",
        "attribute": "balance",
        "value": 100,
        "timestamp": "2026-01-01T00:00:00Z",
    })

    # Ingesting an event with invalid event type must raise error and leave initial state intact
    with pytest.raises(ValueError):
        sql_store.ingest_event({
            "event_type": "INVALID_TYPE",
            "event_id": "e_fail",
            "entity_id": "u_tx",
            "attribute": "balance",
            "value": 999,
            "timestamp": "2026-02-01T00:00:00Z",
        })

    # Balance should still be 100
    q = MemoryQuery(query_id="q_tx", entity_id="u_tx", attribute="balance", as_of_valid_time="2026-01-15T00:00:00Z")
    res = sql_store.retrieve(q)
    assert res.status == QueryStatus.FOUND
    assert res.value == 100
    sql_store.close()
