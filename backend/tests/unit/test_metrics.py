"""Tests for benchmark metric calculations, edge cases, population denominators, and macro vs micro aggregation."""
import pytest
from app.domain.enums import BenchmarkCategory, QueryStatus
from app.domain.models import EvaluationResult
from app.engine.metrics import calculate_latency_stats, calculate_metrics


def _make_eval(
    category: BenchmarkCategory,
    query_id: str = "q1",
    passed: bool = True,
    is_stale_leak: bool = False,
    is_entity_crossover: bool = False,
    is_tombstone_leak: bool = False,
    latency_ms: float = 1.0,
) -> EvaluationResult:
    """Helper to synthesize an EvaluationResult with specific status flags."""
    return EvaluationResult(
        scenario_id="sc_test",
        query_id=query_id,
        category=category,
        passed=passed,
        expected_status=QueryStatus.FOUND,
        actual_status=QueryStatus.FOUND if passed else QueryStatus.NOT_FOUND,
        expected_value="expected",
        actual_value="expected" if passed else "wrong",
        is_stale_leak=is_stale_leak,
        is_entity_crossover=is_entity_crossover,
        is_tombstone_leak=is_tombstone_leak,
        latency_ms=latency_ms,
    )


def test_category_denominators_use_query_level_population():
    """Verify each metric category uses its exact query-level population as denominator."""
    evals = [
        # 3 Temporal Recall queries (2 pass, 1 fails) -> TRAcc = 2/3 = 0.6667
        _make_eval(BenchmarkCategory.TEMPORAL_RECALL, "tr1", passed=True),
        _make_eval(BenchmarkCategory.TEMPORAL_RECALL, "tr2", passed=True),
        _make_eval(BenchmarkCategory.TEMPORAL_RECALL, "tr3", passed=False),
        # 2 Stale Fact queries (1 stale leak) -> SFR = 1/2 = 0.5000, SFAcc = 0.5000
        _make_eval(BenchmarkCategory.STALE_FACT_DETECTION, "sf1", passed=True),
        _make_eval(BenchmarkCategory.STALE_FACT_DETECTION, "sf2", passed=False, is_stale_leak=True),
        # 1 Contradiction query (1 pass) -> CHS = 1/1 = 1.0000
        _make_eval(BenchmarkCategory.CONTRADICTION_HANDLING, "ch1", passed=True),
    ]

    metrics = calculate_metrics(evals)

    assert metrics.total_queries == 6
    assert metrics.passed_queries == 4
    assert metrics.failed_queries == 2
    assert metrics.temporal_recall_accuracy == 0.6667
    assert metrics.stale_fact_rate == 0.5000
    assert metrics.stale_fact_accuracy == 0.5000
    assert metrics.contradiction_handling_score == 1.0000
    # Categories with zero queries must produce None
    assert metrics.entity_isolation_accuracy is None
    assert metrics.deletion_compliance is None


def test_empty_denominators_produce_none():
    """Verify categories with 0 queries strictly return None to prevent deceptive 0% or 100% scores."""
    metrics = calculate_metrics([])
    assert metrics.total_queries == 0
    assert metrics.overall_score is None
    assert metrics.micro_pass_rate is None
    assert metrics.temporal_recall_accuracy is None
    assert metrics.stale_fact_rate is None
    assert metrics.stale_fact_accuracy is None
    assert metrics.contradiction_handling_score is None
    assert metrics.entity_isolation_accuracy is None
    assert metrics.deletion_compliance is None


def test_stale_fact_rate_distinct_from_accuracy():
    """Verify SFR (where 0.0 is optimal) and SFAcc (where 1.0 is optimal) are explicitly distinct."""
    evals = [
        _make_eval(BenchmarkCategory.STALE_FACT_DETECTION, "sf1", passed=True),
        _make_eval(BenchmarkCategory.STALE_FACT_DETECTION, "sf2", passed=True),
        _make_eval(BenchmarkCategory.STALE_FACT_DETECTION, "sf3", passed=True),
        _make_eval(BenchmarkCategory.STALE_FACT_DETECTION, "sf4", passed=False, is_stale_leak=True),
    ]
    metrics = calculate_metrics(evals)
    # 1 out of 4 leaked stale fact
    assert metrics.stale_fact_rate == 0.2500
    assert metrics.stale_fact_accuracy == 0.7500


def test_entity_crossover_leak_cannot_be_hidden_by_passing_queries():
    """Verify an entity crossover leak strictly degrades EIA and cannot be masked."""
    evals = [
        _make_eval(BenchmarkCategory.ENTITY_ISOLATION, f"ei_{i}", passed=True)
        for i in range(9)
    ]
    # Add 1 crossover leak
    evals.append(
        _make_eval(
            BenchmarkCategory.ENTITY_ISOLATION,
            "ei_leak",
            passed=False,
            is_entity_crossover=True,
        )
    )

    metrics = calculate_metrics(evals)
    # 9 passed cleanly out of 10
    assert metrics.entity_isolation_accuracy == 0.9000


def test_deletion_payload_leak_cannot_be_hidden_by_passing_queries():
    """Verify a tombstone payload leak strictly degrades DC and cannot be masked."""
    evals = [
        _make_eval(BenchmarkCategory.DELETION_COMPLIANCE, f"dc_{i}", passed=True)
        for i in range(9)
    ]
    # Add 1 tombstone leak
    evals.append(
        _make_eval(
            BenchmarkCategory.DELETION_COMPLIANCE,
            "dc_leak",
            passed=False,
            is_tombstone_leak=True,
        )
    )

    metrics = calculate_metrics(evals)
    # 9 passed cleanly without tombstone leak out of 10
    assert metrics.deletion_compliance == 0.9000


def test_macro_vs_micro_aggregation_with_unequal_query_counts():
    """Verify overall_score computes unweighted category macro-average while micro_pass_rate computes raw query pass rate."""
    # Category A (Temporal Recall): 9 queries, all 9 pass -> TRAcc = 1.0 (100%)
    evals_tr = [
        _make_eval(BenchmarkCategory.TEMPORAL_RECALL, f"tr_{i}", passed=True)
        for i in range(9)
    ]
    # Category B (Contradiction Handling): 1 query, fails -> CHS = 0.0 (0%)
    evals_ch = [
        _make_eval(BenchmarkCategory.CONTRADICTION_HANDLING, "ch_1", passed=False)
    ]
    all_evals = evals_tr + evals_ch

    metrics = calculate_metrics(all_evals)

    # Micro pass rate = 9 passed / 10 total = 0.9000 (90%)
    assert metrics.micro_pass_rate == 0.9000

    # Macro overall score = (TRAcc 1.0 + CHS 0.0) / 2 = 0.5000 (50%)
    # This prevents the 9 passing queries in TR from masking the 0% failure in CH!
    assert metrics.overall_score == 0.5000
