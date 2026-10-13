"""Integration tests for BenchmarkRunner against InMemoryMemoryStore and SQLiteTemporalMemoryStore.

Executes all 10 benchmark catalog scenarios against both stores,
validating 100% pass across all 5 benchmark categories.
"""
from pathlib import Path
import tempfile
import pytest

from app.domain.enums import BenchmarkCategory
from app.engine.reporter import generate_json_report, generate_markdown_summary
from app.engine.runner import BenchmarkRunner, load_catalog_scenarios
from app.storage.in_memory_store import InMemoryMemoryStore
from app.storage.sqlite_store import SQLiteTemporalMemoryStore

CATALOG_PATH = Path(__file__).resolve().parents[3] / "benchmarks" / "catalog.json"


@pytest.fixture
def catalog_scenarios():
    """Load all 12 catalog scenarios covering all 4 contradiction policies."""
    assert CATALOG_PATH.exists(), f"Catalog not found at {CATALOG_PATH}"
    scenarios = load_catalog_scenarios(CATALOG_PATH)
    assert len(scenarios) == 12, f"Expected 12 scenarios in catalog, got {len(scenarios)}"
    return scenarios


def test_in_memory_store_benchmark_catalog(catalog_scenarios):
    """Execute all 12 scenarios against InMemoryMemoryStore and verify 100% reliability."""
    store = InMemoryMemoryStore()
    runner = BenchmarkRunner()

    report = runner.run_scenarios(store, catalog_scenarios, store_name="InMemoryMemoryStore")

    assert report.scenarios_evaluated == 12
    assert report.total_queries > 0
    assert report.failed_queries == 0
    assert report.passed_queries == report.total_queries

    # Verify per-scenario success
    for sc_res in report.scenario_results:
        assert sc_res.all_passed is True, f"Scenario {sc_res.scenario_id} failed"
        assert sc_res.passed_count == sc_res.total_count

    # Verify all 5 benchmark category metrics
    m = report.aggregate_metrics
    assert m.overall_score == 1.0
    assert m.temporal_recall_accuracy == 1.0
    assert m.stale_fact_rate == 0.0
    assert m.contradiction_handling_score == 1.0
    assert m.entity_isolation_accuracy == 1.0
    assert m.deletion_compliance == 1.0

    # Verify latency stats
    assert m.latency.count == report.total_queries
    assert m.latency.mean_ms is not None and m.latency.mean_ms >= 0.0
    assert m.latency.p50_ms is not None and m.latency.p50_ms >= 0.0

    # Test report formatting
    md = generate_markdown_summary(report)
    assert "**Overall Reliability Score:** **100.0%**" in md
    assert "InMemoryMemoryStore" in md
    assert "TRAcc" in md and "SFR" in md and "CHS" in md and "EIA" in md and "DC" in md

    json_report = generate_json_report(report)
    assert '"overall_score": 1.0' in json_report


def test_sqlite_store_benchmark_catalog(catalog_scenarios, tmp_path):
    """Execute all 10 scenarios against SQLiteTemporalMemoryStore and verify 100% reliability."""
    db_file = tmp_path / "benchmark_test.db"
    store = SQLiteTemporalMemoryStore(db_path=str(db_file))
    runner = BenchmarkRunner()

    try:
        report = runner.run_scenarios(store, catalog_scenarios, store_name="SQLiteTemporalMemoryStore")

        assert report.scenarios_evaluated == 12
        assert report.total_queries > 0
        assert report.failed_queries == 0
        assert report.passed_queries == report.total_queries

        for sc_res in report.scenario_results:
            assert sc_res.all_passed is True, f"Scenario {sc_res.scenario_id} failed"
            assert sc_res.passed_count == sc_res.total_count

        m = report.aggregate_metrics
        assert m.overall_score == 1.0
        assert m.temporal_recall_accuracy == 1.0
        assert m.stale_fact_rate == 0.0
        assert m.contradiction_handling_score == 1.0
        assert m.entity_isolation_accuracy == 1.0
        assert m.deletion_compliance == 1.0

        assert m.latency.count == report.total_queries
        assert m.latency.mean_ms is not None and m.latency.mean_ms >= 0.0

        md = generate_markdown_summary(report)
        assert "SQLiteTemporalMemoryStore" in md
        assert "**Overall Reliability Score:** **100.0%**" in md

    finally:
        store.close()


def test_run_catalog_convenience_method():
    """Verify runner.run_catalog directly loading catalog.json."""
    store = InMemoryMemoryStore()
    runner = BenchmarkRunner()
    report = runner.run_catalog(store, CATALOG_PATH, store_name="CatalogMethodTest")
    assert report.scenarios_evaluated == 12
    assert report.passed_queries == report.total_queries
    assert report.failed_queries == 0
    assert report.aggregate_metrics.overall_score == 1.0
