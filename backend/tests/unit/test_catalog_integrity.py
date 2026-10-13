"""Tests for catalog manifest integrity, duplicate rejection, and file reference validation."""
import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.domain.enums import BenchmarkCategory
from app.engine.evaluator import CatalogEntry, CatalogManifest, load_scenario_from_file
from app.engine.runner import load_catalog_scenarios

CATALOG_PATH = Path(__file__).resolve().parents[3] / "benchmarks" / "catalog.json"


def test_valid_catalog_loads_all_scenarios():
    """Verify official catalog.json loads all 12 declared scenarios with zero errors."""
    scenarios = load_catalog_scenarios(CATALOG_PATH)
    assert len(scenarios) == 12
    scenario_ids = [s.scenario_id for s in scenarios]
    assert len(scenario_ids) == len(set(scenario_ids)), "Scenario IDs must be unique"
    # Verify all 4 contradiction policies are represented
    policies = {s.contradiction_policy for s in scenarios}
    assert len(policies) >= 4


def test_catalog_rejects_duplicate_scenario_ids_in_manifest():
    """Verify CatalogManifest rejects duplicate scenario_id entries."""
    with pytest.raises(ValidationError, match="Duplicate scenario_id declared in catalog"):
        CatalogManifest(
            version="1.0.0",
            scenarios=[
                CatalogEntry(
                    scenario_id="dupe_sc",
                    category=BenchmarkCategory.TEMPORAL_RECALL,
                    file="v1/temporal_recall/tr_01_simple_history.json",
                    description="first",
                ),
                CatalogEntry(
                    scenario_id="dupe_sc",
                    category=BenchmarkCategory.TEMPORAL_RECALL,
                    file="v1/temporal_recall/tr_02_exact_boundary.json",
                    description="second",
                ),
            ],
        )


def test_catalog_rejects_duplicate_file_paths_in_manifest():
    """Verify CatalogManifest rejects duplicate scenario file paths."""
    with pytest.raises(ValidationError, match="Duplicate scenario file path declared in catalog"):
        CatalogManifest(
            version="1.0.0",
            scenarios=[
                CatalogEntry(
                    scenario_id="sc_01",
                    category=BenchmarkCategory.TEMPORAL_RECALL,
                    file="v1/temporal_recall/tr_01_simple_history.json",
                    description="first",
                ),
                CatalogEntry(
                    scenario_id="sc_02",
                    category=BenchmarkCategory.TEMPORAL_RECALL,
                    file="v1/temporal_recall/tr_01_simple_history.json",
                    description="second with same file",
                ),
            ],
        )


def test_catalog_rejects_missing_scenario_file(tmp_path):
    """Verify load_catalog_scenarios raises FileNotFoundError with actionable error when referenced file is missing."""
    bogus_catalog = tmp_path / "catalog.json"
    bogus_catalog.write_text(
        json.dumps({
            "version": "1.0.0",
            "scenarios": [
                {
                    "scenario_id": "missing_sc",
                    "category": "TEMPORAL_RECALL",
                    "file": "nonexistent_dir/missing_scenario.json",
                    "description": "points to non-existent file",
                }
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="declared for scenario 'missing_sc' in catalog does not exist"):
        load_catalog_scenarios(bogus_catalog)


def test_catalog_rejects_mismatched_scenario_id(tmp_path):
    """Verify load_catalog_scenarios rejects mismatch between catalog ID and file's internal scenario_id."""
    # Write a scenario file with internal ID 'actual_id'
    sc_file = tmp_path / "scenario_mismatch.json"
    sc_file.write_text(
        json.dumps({
            "scenario_id": "actual_id",
            "version": "1.0.0",
            "category": "TEMPORAL_RECALL",
            "description": "test",
            "timeline_events": [
                {
                    "event_type": "INSERT",
                    "event_id": "e1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "entity_id": "u1",
                    "attribute": "a",
                    "value": "v",
                }
            ],
            "queries": [
                {
                    "query_id": "q1",
                    "query": {"entity_id": "u1", "attribute": "a"},
                    "ground_truth": {"expected_status": "FOUND", "expected_value": "v"},
                }
            ],
        }),
        encoding="utf-8",
    )

    # Write a catalog declaring it as 'declared_id'
    cat_file = tmp_path / "catalog.json"
    cat_file.write_text(
        json.dumps({
            "version": "1.0.0",
            "scenarios": [
                {
                    "scenario_id": "declared_id",
                    "category": "TEMPORAL_RECALL",
                    "file": "scenario_mismatch.json",
                    "description": "id mismatch",
                }
            ],
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Catalog scenario ID 'declared_id' does not match manifest scenario ID 'actual_id'"):
        load_catalog_scenarios(cat_file)


def test_directory_loading_rejects_duplicate_scenario_ids(tmp_path):
    """Verify directory loading detects duplicate scenario_ids across distinct files."""
    sc_content = {
        "scenario_id": "shared_dupe_id",
        "version": "1.0.0",
        "category": "TEMPORAL_RECALL",
        "description": "test",
        "timeline_events": [
            {
                "event_type": "INSERT",
                "event_id": "e1",
                "timestamp": "2026-01-01T00:00:00Z",
                "entity_id": "u1",
                "attribute": "a",
                "value": "v",
            }
        ],
        "queries": [
            {
                "query_id": "q1",
                "query": {"entity_id": "u1", "attribute": "a"},
                "ground_truth": {"expected_status": "FOUND", "expected_value": "v"},
            }
        ],
    }

    file1 = tmp_path / "file1.json"
    file2 = tmp_path / "file2.json"
    file1.write_text(json.dumps(sc_content), encoding="utf-8")
    file2.write_text(json.dumps(sc_content), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate scenario_id detected across directory manifests"):
        load_catalog_scenarios(tmp_path)
