"""Adversarial and mutation unit tests for EvaluatorEngine and metrics.

Verifies that mutated or corrupted predictions strictly fail evaluation
and accurately degrade benchmark metric dimensions.
"""
from datetime import datetime, timezone
import json
import pytest
from pydantic import ValidationError

from app.domain.enums import (
    BenchmarkCategory,
    ContradictionPolicy,
    QueryStatus,
    UpdatePolicy,
)
from app.domain.models import GroundTruth, MemoryQuery, QueryPrediction
from app.domain.timestamps import parse_utc_iso
from app.engine.evaluator import (
    BenchmarkScenario,
    EvaluatorEngine,
    ScenarioQuery,
    TimelineEvent,
    load_scenario_from_dict,
)
from app.engine.metrics import calculate_latency_stats, calculate_metrics


def _make_dummy_scenario(
    category: BenchmarkCategory,
    contradiction_policy: ContradictionPolicy = ContradictionPolicy.DETERMINISTIC_ABSTAIN,
) -> BenchmarkScenario:
    """Helper to create a minimal valid scenario for testing."""
    return BenchmarkScenario(
        scenario_id="dummy_sc",
        version="1.0.0",
        category=category,
        description="Dummy test scenario",
        contradiction_policy=contradiction_policy,
        timeline_events=[
            TimelineEvent(
                event_type="INSERT",
                event_id="e_01",
                timestamp=parse_utc_iso("2026-01-01T00:00:00Z"),
                entity_id="entity_1",
                attribute="attr",
                value="initial",
            )
        ],
        queries=[
            ScenarioQuery(
                query_id="q_01",
                query=MemoryQuery(
                    query_id="q_01",
                    entity_id="entity_1",
                    attribute="attr",
                ),
                ground_truth=GroundTruth(
                    expected_status=QueryStatus.FOUND,
                    expected_value="initial",
                ),
            )
        ],
    )


def test_stale_value_leak_fails_and_increases_sfr():
    """Mutation 1: Returning a superseded/stale value in STALE_FACT_DETECTION fails and increases SFR."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(category=BenchmarkCategory.STALE_FACT_DETECTION)
    query_spec = ScenarioQuery(
        query_id="q_sf_01",
        query=MemoryQuery(query_id="q_sf_01", entity_id="entity_1", attribute="email"),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.FOUND,
            expected_value="alice_new@corp.com",
            forbidden_values=["alice_old@corp.com"],
        ),
    )

    # Corrupted prediction: returns the old, superseded email
    stale_pred = QueryPrediction(
        query_id="q_sf_01",
        status=QueryStatus.FOUND,
        value="alice_old@corp.com",
        matched_entity_id="entity_1",
        latency_ms=1.5,
    )

    result = engine.evaluate_prediction(stale_pred, query_spec, scenario)
    assert result.passed is False
    assert result.is_stale_leak is True
    assert "Stale value leak detected" in (result.error_message or "")

    metrics = calculate_metrics([result])
    assert metrics.stale_fact_rate == 1.0
    assert metrics.failed_queries == 1


def test_incorrect_value_with_matching_status_fails():
    """Mutation 2: Status is FOUND as expected, but payload value is wrong -> strictly fails."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(category=BenchmarkCategory.TEMPORAL_RECALL)
    query_spec = ScenarioQuery(
        query_id="q_tr_val",
        query=MemoryQuery(query_id="q_tr_val", entity_id="entity_1", attribute="city"),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.FOUND,
            expected_value="Boston",
        ),
    )

    # Wrong value
    wrong_val_pred = QueryPrediction(
        query_id="q_tr_val",
        status=QueryStatus.FOUND,
        value="Seattle",
        matched_entity_id="entity_1",
    )

    result = engine.evaluate_prediction(wrong_val_pred, query_spec, scenario)
    assert result.passed is False
    assert "Value mismatch" in (result.error_message or "")


def test_arbitrary_resolution_when_abstention_required_fails():
    """Mutation 3: Under DETERMINISTIC_ABSTAIN, arbitrarily picking a winner instead of abstaining fails."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(
        category=BenchmarkCategory.CONTRADICTION_HANDLING,
        contradiction_policy=ContradictionPolicy.DETERMINISTIC_ABSTAIN,
    )
    query_spec = ScenarioQuery(
        query_id="q_ct_abstain",
        query=MemoryQuery(query_id="q_ct_abstain", entity_id="entity_1", attribute="temp"),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.CONTRADICTION,
            expected_abstention=True,
            expected_value=None,
        ),
    )

    # Store arbitrarily resolves to 72.5 with FOUND
    arbitrary_pred = QueryPrediction(
        query_id="q_ct_abstain",
        status=QueryStatus.FOUND,
        value=72.5,
        matched_entity_id="entity_1",
    )

    result = engine.evaluate_prediction(arbitrary_pred, query_spec, scenario)
    assert result.passed is False
    assert "Status mismatch" in (result.error_message or "")

    metrics = calculate_metrics([result])
    assert metrics.contradiction_handling_score == 0.0


def test_abstention_when_resolution_required_fails():
    """Mutation 4: Under LAST_ASSERTION_WINS, returning CONTRADICTION or None when a fact should be resolved fails."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(
        category=BenchmarkCategory.CONTRADICTION_HANDLING,
        contradiction_policy=ContradictionPolicy.LAST_ASSERTION_WINS,
    )
    query_spec = ScenarioQuery(
        query_id="q_ct_lww",
        query=MemoryQuery(query_id="q_ct_lww", entity_id="entity_1", attribute="token"),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.FOUND,
            expected_value="token_beta",
        ),
    )

    # Store inappropriately abstains
    abstain_pred = QueryPrediction(
        query_id="q_ct_lww",
        status=QueryStatus.CONTRADICTION,
        value=None,
        matched_entity_id="entity_1",
    )

    result = engine.evaluate_prediction(abstain_pred, query_spec, scenario)
    assert result.passed is False
    assert result.actual_status == QueryStatus.CONTRADICTION


def test_not_found_when_valid_fact_exists_fails():
    """Mutation 5: Returning NOT_FOUND when a valid record exists strictly fails."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(category=BenchmarkCategory.TEMPORAL_RECALL)
    query_spec = ScenarioQuery(
        query_id="q_tr_exist",
        query=MemoryQuery(query_id="q_tr_exist", entity_id="entity_1", attribute="city"),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.FOUND,
            expected_value="Chicago",
        ),
    )

    missed_pred = QueryPrediction(
        query_id="q_tr_exist",
        status=QueryStatus.NOT_FOUND,
        value=None,
    )

    result = engine.evaluate_prediction(missed_pred, query_spec, scenario)
    assert result.passed is False
    assert result.actual_status == QueryStatus.NOT_FOUND


def test_cross_entity_provenance_mismatch_fails_and_degrades_eia():
    """Mutation 6: Matched entity ID points to another entity -> fails and degrades EIA."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(category=BenchmarkCategory.ENTITY_ISOLATION)
    query_spec = ScenarioQuery(
        query_id="q_ei_prov",
        query=MemoryQuery(query_id="q_ei_prov", entity_id="tenant_alpha", attribute="secret"),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.FOUND,
            expected_value="secret_A",
            forbidden_values=["secret_B"],
        ),
    )

    # Returned value happens to match, BUT matched_entity_id leaked tenant_beta
    leaked_provenance_pred = QueryPrediction(
        query_id="q_ei_prov",
        status=QueryStatus.FOUND,
        value="secret_A",
        matched_entity_id="tenant_beta",
    )

    result = engine.evaluate_prediction(leaked_provenance_pred, query_spec, scenario)
    assert result.passed is False
    assert result.is_entity_crossover is True
    assert "Entity crossover leak" in (result.error_message or "")

    metrics = calculate_metrics([result])
    assert metrics.entity_isolation_accuracy == 0.0


def test_deleted_payload_leak_fails_and_degrades_dc():
    """Mutation 7: In DELETION_COMPLIANCE, exposing payload on tombstoned record fails and drops DC."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(category=BenchmarkCategory.DELETION_COMPLIANCE)
    query_spec = ScenarioQuery(
        query_id="q_dc_leak",
        query=MemoryQuery(query_id="q_dc_leak", entity_id="user_1", attribute="ssn"),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.TOMBSTONED_DELETED,
            expected_value=None,
        ),
    )

    # Returns tombstone status BUT leaks the underlying payload
    leaking_pred = QueryPrediction(
        query_id="q_dc_leak",
        status=QueryStatus.TOMBSTONED_DELETED,
        value="123-45-6789",
        matched_entity_id="user_1",
    )

    result = engine.evaluate_prediction(leaking_pred, query_spec, scenario)
    assert result.passed is False
    assert result.is_tombstone_leak is True
    assert "Tombstone payload leaked" in (result.error_message or "")

    metrics = calculate_metrics([result])
    assert metrics.deletion_compliance == 0.0


def test_exact_boundary_off_by_one_fails():
    """Mutation 8: Off-by-one at exact transition boundary fails."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(category=BenchmarkCategory.TEMPORAL_RECALL)
    query_spec = ScenarioQuery(
        query_id="q_exact_boundary",
        query=MemoryQuery(
            query_id="q_exact_boundary",
            entity_id="user_1",
            attribute="role",
            as_of_valid_time=parse_utc_iso("2026-06-01T00:00:00Z"),
        ),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.FOUND,
            expected_value="role_v2",
            forbidden_values=["role_v1"],
        ),
    )

    # Boundary was treated as <= instead of <, returning stale role_v1
    boundary_leak = QueryPrediction(
        query_id="q_exact_boundary",
        status=QueryStatus.FOUND,
        value="role_v1",
        matched_entity_id="user_1",
    )

    result = engine.evaluate_prediction(boundary_leak, query_spec, scenario)
    assert result.passed is False
    assert result.actual_value == "role_v1"


def test_malformed_scenario_manifests_raise_validation_error():
    """Mutation 9: Strict validation rejects malformed scenario manifests."""
    # 1. Duplicate event_id
    with pytest.raises(ValidationError, match="Duplicate event_id detected"):
        load_scenario_from_dict({
            "scenario_id": "malformed_dupe_events",
            "version": "1.0.0",
            "category": "TEMPORAL_RECALL",
            "description": "dup events",
            "timeline_events": [
                {
                    "event_type": "INSERT",
                    "event_id": "dupe_e",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "entity_id": "ent",
                    "attribute": "a",
                    "value": "v1",
                },
                {
                    "event_type": "INSERT",
                    "event_id": "dupe_e",
                    "timestamp": "2026-01-02T00:00:00Z",
                    "entity_id": "ent",
                    "attribute": "a",
                    "value": "v2",
                },
            ],
            "queries": [
                {
                    "query_id": "q1",
                    "query": {"entity_id": "ent", "attribute": "a"},
                    "ground_truth": {"expected_status": "FOUND", "expected_value": "v2"},
                }
            ],
        })

    # 2. Duplicate query_id
    with pytest.raises(ValidationError, match="Duplicate query_id detected"):
        load_scenario_from_dict({
            "scenario_id": "malformed_dupe_queries",
            "version": "1.0.0",
            "category": "TEMPORAL_RECALL",
            "description": "dup queries",
            "timeline_events": [
                {
                    "event_type": "INSERT",
                    "event_id": "e1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "entity_id": "ent",
                    "attribute": "a",
                    "value": "v1",
                }
            ],
            "queries": [
                {
                    "query_id": "dupe_q",
                    "query": {"entity_id": "ent", "attribute": "a"},
                    "ground_truth": {"expected_status": "FOUND", "expected_value": "v1"},
                },
                {
                    "query_id": "dupe_q",
                    "query": {"entity_id": "ent", "attribute": "a"},
                    "ground_truth": {"expected_status": "FOUND", "expected_value": "v1"},
                },
            ],
        })

    # 3. Inverted valid_from >= valid_to in event
    with pytest.raises(ValidationError, match="valid_from >= valid_to"):
        load_scenario_from_dict({
            "scenario_id": "malformed_inverted_interval",
            "version": "1.0.0",
            "category": "TEMPORAL_RECALL",
            "description": "inverted event",
            "timeline_events": [
                {
                    "event_type": "INSERT",
                    "event_id": "e1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "entity_id": "ent",
                    "attribute": "a",
                    "value": "v1",
                    "valid_from": "2026-06-01T00:00:00Z",
                    "valid_to": "2026-01-01T00:00:00Z",
                }
            ],
            "queries": [
                {
                    "query_id": "q1",
                    "query": {"entity_id": "ent", "attribute": "a"},
                    "ground_truth": {"expected_status": "FOUND", "expected_value": "v1"},
                }
            ],
        })

    # 4. Naive timestamp (no tz) in event
    with pytest.raises(ValidationError, match="timezone-aware"):
        load_scenario_from_dict({
            "scenario_id": "malformed_naive_ts",
            "version": "1.0.0",
            "category": "TEMPORAL_RECALL",
            "description": "naive ts",
            "timeline_events": [
                {
                    "event_type": "INSERT",
                    "event_id": "e1",
                    "timestamp": "2026-01-01T00:00:00",  # missing Z / offset
                    "entity_id": "ent",
                    "attribute": "a",
                    "value": "v1",
                }
            ],
            "queries": [
                {
                    "query_id": "q1",
                    "query": {"entity_id": "ent", "attribute": "a"},
                    "ground_truth": {"expected_status": "FOUND", "expected_value": "v1"},
                }
            ],
        })

    # 5. Abstention expected but non-None value provided
    with pytest.raises(ValidationError, match="expects abstention but specifies non-None expected_value"):
        load_scenario_from_dict({
            "scenario_id": "malformed_abstain_with_value",
            "version": "1.0.0",
            "category": "CONTRADICTION_HANDLING",
            "description": "abstain conflict",
            "timeline_events": [
                {
                    "event_type": "INSERT",
                    "event_id": "e1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "entity_id": "ent",
                    "attribute": "a",
                    "value": "v1",
                }
            ],
            "queries": [
                {
                    "query_id": "q1",
                    "query": {"entity_id": "ent", "attribute": "a"},
                    "ground_truth": {
                        "expected_status": "CONTRADICTION",
                        "expected_abstention": True,
                        "expected_value": "should_not_be_here",
                    },
                }
            ],
        })


def test_metrics_empty_denominators_and_latency_percentiles():
    """Verify empty denominator behavior (returns None) and observational latency calculations."""
    empty_metrics = calculate_metrics([])
    assert empty_metrics.total_queries == 0
    assert empty_metrics.overall_score is None
    assert empty_metrics.temporal_recall_accuracy is None
    assert empty_metrics.stale_fact_rate is None
    assert empty_metrics.contradiction_handling_score is None
    assert empty_metrics.entity_isolation_accuracy is None
    assert empty_metrics.deletion_compliance is None
    assert empty_metrics.latency.count == 0

    latencies = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    stats = calculate_latency_stats(latencies)
    assert stats.count == 10
    assert stats.mean_ms == 5.5
    assert stats.p50_ms == 5.5
    assert stats.p95_ms == 10.0
    assert stats.p99_ms == 10.0


def test_confidence_weighted_evaluation_and_mutations():
    """Verify CONFIDENCE_WEIGHTED evaluation correctly handles valid winner and fails corrupted predictions."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(
        category=BenchmarkCategory.CONTRADICTION_HANDLING,
        contradiction_policy=ContradictionPolicy.CONFIDENCE_WEIGHTED,
    )
    query_spec = ScenarioQuery(
        query_id="q_cw_test",
        query=MemoryQuery(query_id="q_cw_test", entity_id="sensor_01", attribute="temp"),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.FOUND,
            expected_value=72.5,
            forbidden_values=[45.0],
        ),
    )

    # 1. Valid prediction with highest-confidence fact passes
    valid_pred = QueryPrediction(
        query_id="q_cw_test",
        status=QueryStatus.FOUND,
        value=72.5,
        matched_entity_id="sensor_01",
    )
    res_valid = engine.evaluate_prediction(valid_pred, query_spec, scenario)
    assert res_valid.passed is True

    # 2. Corrupted prediction returning lower-confidence value (45.0) fails
    corrupt_pred = QueryPrediction(
        query_id="q_cw_test",
        status=QueryStatus.FOUND,
        value=45.0,
        matched_entity_id="sensor_01",
    )
    res_corrupt = engine.evaluate_prediction(corrupt_pred, query_spec, scenario)
    assert res_corrupt.passed is False
    assert "Value mismatch" in (res_corrupt.error_message or "")
    assert "Forbidden value returned" in (res_corrupt.error_message or "")

    # 3. Corrupted prediction abstaining when resolution is required fails
    abstain_pred = QueryPrediction(
        query_id="q_cw_test",
        status=QueryStatus.CONTRADICTION,
        value=None,
        matched_entity_id="sensor_01",
    )
    res_abstain = engine.evaluate_prediction(abstain_pred, query_spec, scenario)
    assert res_abstain.passed is False


def test_multivalued_collection_evaluation_and_mutations():
    """Verify MULTIVALUED_COLLECTION evaluation requires exact sorted unique collection and fails corruptions."""
    engine = EvaluatorEngine()
    scenario = _make_dummy_scenario(
        category=BenchmarkCategory.CONTRADICTION_HANDLING,
        contradiction_policy=ContradictionPolicy.MULTIVALUED_COLLECTION,
    )
    query_spec = ScenarioQuery(
        query_id="q_mc_test",
        query=MemoryQuery(query_id="q_mc_test", entity_id="user_bob", attribute="roles"),
        ground_truth=GroundTruth(
            expected_status=QueryStatus.FOUND,
            expected_value=["admin", "editor"],
        ),
    )

    # 1. Valid merged collection passes
    valid_pred = QueryPrediction(
        query_id="q_mc_test",
        status=QueryStatus.FOUND,
        value=["admin", "editor"],
        matched_entity_id="user_bob",
    )
    res_valid = engine.evaluate_prediction(valid_pred, query_spec, scenario)
    assert res_valid.passed is True

    # 2. Corrupted prediction returning single scalar fails
    scalar_pred = QueryPrediction(
        query_id="q_mc_test",
        status=QueryStatus.FOUND,
        value="admin",
        matched_entity_id="user_bob",
    )
    res_scalar = engine.evaluate_prediction(scalar_pred, query_spec, scenario)
    assert res_scalar.passed is False
    assert "Value mismatch" in (res_scalar.error_message or "")

    # 3. Corrupted prediction returning unsorted list fails
    unsorted_pred = QueryPrediction(
        query_id="q_mc_test",
        status=QueryStatus.FOUND,
        value=["editor", "admin"],
        matched_entity_id="user_bob",
    )
    res_unsorted = engine.evaluate_prediction(unsorted_pred, query_spec, scenario)
    assert res_unsorted.passed is False

    # 4. Inappropriate abstention fails
    abstain_pred = QueryPrediction(
        query_id="q_mc_test",
        status=QueryStatus.CONTRADICTION,
        value=None,
        matched_entity_id="user_bob",
    )
    res_abstain = engine.evaluate_prediction(abstain_pred, query_spec, scenario)
    assert res_abstain.passed is False


def test_ground_truth_independence_from_target_store():
    """Confirm expected outcomes are strictly static data fixtures and cannot be altered by store predictions."""
    from pathlib import Path
    from app.engine.evaluator import load_scenario_from_file

    catalog_path = Path(__file__).resolve().parents[3] / "benchmarks" / "catalog.json"
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog_data = json.load(f)

    base_dir = catalog_path.parent
    for entry in catalog_data["scenarios"]:
        sc = load_scenario_from_file(base_dir / entry["file"])
        for q in sc.queries:
            gt = q.ground_truth
            # Verify ground truth is pure Pydantic model with immutable data
            assert isinstance(gt, GroundTruth)
            assert gt.expected_status in list(QueryStatus)
            # Verify ground truth cannot be mutated by evaluating predictions
            dummy_pred = QueryPrediction(
                query_id=q.query_id,
                status=QueryStatus.SUPERSEDED_STALE,
                value="arbitrary_fabricated_payload",
            )
            engine = EvaluatorEngine()
            engine.evaluate_prediction(dummy_pred, q, sc)
            # Ground truth remains completely unaffected
            assert dummy_pred.value != gt.expected_value
