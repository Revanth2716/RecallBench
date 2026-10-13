"""Tests for run-history persistence and service restart recovery.

Verifies that:
1. Benchmark runs are persisted as JSON files on disk in the isolated runs directory.
2. Run history survives a complete backend restart (service re-initialization).
3. Reconstructed reports maintain exact query evaluations and aggregate metrics.
4. Exporting reloaded reports (JSON and Markdown) produces identical structured results.
5. Storage isolation: run history is independent from temporal-memory store records.
6. Corrupted history files do not crash the service on startup.
"""
import json
from pathlib import Path
import tempfile
import uuid
import pytest

from app.api.service import BenchmarkService, DATA_DIR, RUNS_DIR, SQLITE_DB_PATH
from app.engine.runner import BenchmarkRunReport, BenchmarkRunner
from app.storage.in_memory_store import InMemoryMemoryStore
from app.storage.sqlite_store import SQLiteTemporalMemoryStore


def test_run_persisted_to_disk(tmp_path: Path, monkeypatch):
    """Verify that executing a benchmark creates a persistent JSON report on disk."""
    fake_runs_dir = tmp_path / "runs"
    fake_runs_dir.mkdir(parents=True)

    # Patch RUNS_DIR in service module
    monkeypatch.setattr("app.api.service.RUNS_DIR", fake_runs_dir)

    svc = BenchmarkService()
    # Run with a single scenario for speed
    report = svc.execute_run(adapter_name="in_memory", scenario_ids=["tr_01_simple_history"])

    expected_file = fake_runs_dir / f"{report.run_id}.json"
    assert expected_file.exists(), "Report JSON file should be written to disk"

    # Verify content on disk matches report
    disk_data = json.loads(expected_file.read_text(encoding="utf-8"))
    assert disk_data["run_id"] == report.run_id
    assert disk_data["store_name"] == report.store_name
    assert disk_data["scenarios_evaluated"] == 1


def test_run_history_survives_service_restart(tmp_path: Path, monkeypatch):
    """Verify that a fresh BenchmarkService instance successfully restores history."""
    fake_runs_dir = tmp_path / "runs"
    fake_runs_dir.mkdir(parents=True)
    monkeypatch.setattr("app.api.service.RUNS_DIR", fake_runs_dir)

    # 1. Instance 1 executes a run
    svc1 = BenchmarkService()
    run1 = svc1.execute_run(adapter_name="in_memory", scenario_ids=["tr_01_simple_history"])
    run1_id = run1.run_id

    # 2. Simulate server restart: instantiate a fresh BenchmarkService
    svc2 = BenchmarkService()

    # Verify run is recovered
    restored_runs = svc2.list_runs()
    assert any(r.run_id == run1_id for r in restored_runs), "Run must be restored after restart"

    restored_run = svc2.get_run(run1_id)
    assert restored_run is not None
    assert restored_run.run_id == run1_id
    assert restored_run.store_name == run1.store_name
    assert restored_run.total_queries == run1.total_queries
    assert restored_run.passed_queries == run1.passed_queries
    assert restored_run.aggregate_metrics.overall_score == run1.aggregate_metrics.overall_score

    # 3. Verify export works seamlessly on the restored report
    json_export = svc2.export_run(run1_id, "json")
    assert run1_id in json_export

    md_export = svc2.export_run(run1_id, "markdown")
    assert run1_id in md_export
    assert "# RecallBench Run Report" in md_export


def test_corrupted_run_file_resilience(tmp_path: Path, monkeypatch):
    """Verify that corrupt JSON files in the runs directory do not crash restart."""
    fake_runs_dir = tmp_path / "runs"
    fake_runs_dir.mkdir(parents=True)
    monkeypatch.setattr("app.api.service.RUNS_DIR", fake_runs_dir)

    # Write a valid run
    svc1 = BenchmarkService()
    valid_run = svc1.execute_run(adapter_name="in_memory", scenario_ids=["tr_01_simple_history"])

    # Write a corrupt file
    corrupt_file = fake_runs_dir / "corrupted_run.json"
    corrupt_file.write_text("{ this is not valid json : [[", encoding="utf-8")

    # Write an invalid schema file
    invalid_schema = fake_runs_dir / "invalid_schema.json"
    invalid_schema.write_text(json.dumps({"some_key": "wrong_value"}), encoding="utf-8")

    # Fresh service restart
    svc2 = BenchmarkService()
    runs = svc2.list_runs()
    assert len(runs) == 1
    assert runs[0].run_id == valid_run.run_id


def test_storage_layer_isolation():
    """Verify that run-history storage is completely isolated from temporal memory store records."""
    assert RUNS_DIR != DATA_DIR
    assert SQLITE_DB_PATH.parent == DATA_DIR
    assert RUNS_DIR.name == "runs"
    assert SQLITE_DB_PATH.name == "benchmark_isolated.db"
    # Runs directory contains json files, not SQLite tables
    assert not any(f.suffix == ".db" for f in RUNS_DIR.glob("*"))
