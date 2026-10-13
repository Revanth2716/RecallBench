"""Integration tests for RecallBench FastAPI service routes."""
import threading
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.service import benchmark_service

client = TestClient(app)


def test_health_endpoint():
    """Verify GET /health returns service status and catalog counts."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert data["scenarios_count"] == 12


def test_list_benchmarks():
    """Verify GET /api/benchmarks returns all catalog categories and scenario summaries."""
    response = client.get("/api/benchmarks")
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    assert len(data["categories"]) == 5
    assert len(data["scenarios"]) == 12
    ids = [s["scenario_id"] for s in data["scenarios"]]
    assert "tr_01_simple_history" in ids
    assert "ct_03_confidence_weighted" in ids


def test_get_benchmark_scenario_detail():
    """Verify GET /api/benchmarks/{scenario_id} returns scenario detail."""
    response = client.get("/api/benchmarks/tr_01_simple_history")
    assert response.status_code == 200
    data = response.json()
    assert data["scenario_id"] == "tr_01_simple_history"
    assert data["category"] == "TEMPORAL_RECALL"
    assert len(data["timeline_events"]) > 0
    assert len(data["queries"]) > 0


def test_get_benchmark_scenario_not_found():
    """Verify GET /api/benchmarks/{scenario_id} returns 404 for nonexistent scenario."""
    response = client.get("/api/benchmarks/nonexistent_scenario_123")
    assert response.status_code == 404
    assert "not found in catalog" in response.json()["detail"]


def test_create_run_sqlite_success():
    """Verify POST /api/runs with sqlite adapter succeeds and returns 201."""
    response = client.post("/api/runs", json={"adapter": "sqlite"})
    assert response.status_code == 201
    data = response.json()
    assert "run_id" in data
    assert data["scenarios_evaluated"] == 12
    assert data["total_queries"] > 0
    assert data["failed_queries"] == 0
    assert data["aggregate_metrics"]["overall_score"] == 1.0


def test_create_run_in_memory_success():
    """Verify POST /api/runs with in_memory adapter succeeds and returns 201."""
    response = client.post("/api/runs", json={"adapter": "in_memory"})
    assert response.status_code == 201
    data = response.json()
    assert data["store_name"] == "In-Memory Store"
    assert data["aggregate_metrics"]["overall_score"] == 1.0


def test_create_run_unsupported_adapter():
    """Verify POST /api/runs rejects unsupported adapters with 400 Bad Request."""
    response = client.post("/api/runs", json={"adapter": "vector_db"})
    assert response.status_code == 400
    assert "Unsupported adapter" in response.json()["detail"]


def test_create_run_malformed_payload():
    """Verify POST /api/runs rejects malformed request bodies with 422."""
    response = client.post("/api/runs", json={"scenario_ids": "not-a-list"})
    assert response.status_code == 422


def test_list_runs_history():
    """Verify GET /api/runs returns historical runs."""
    response = client.get("/api/runs")
    assert response.status_code == 200
    runs = response.json()
    assert isinstance(runs, list)
    assert len(runs) >= 1
    assert "run_id" in runs[0]
    assert "overall_score" in runs[0]


def test_get_run_detail_and_missing_id():
    """Verify GET /api/runs/{run_id} returns report or 404 if missing."""
    # List runs to get a valid run ID
    list_resp = client.get("/api/runs")
    valid_id = list_resp.json()[0]["run_id"]

    # 1. Valid ID
    detail_resp = client.get(f"/api/runs/{valid_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["run_id"] == valid_id
    assert "scenario_results" in detail_resp.json()

    # 2. Missing ID
    missing_resp = client.get("/api/runs/nonexistent-run-uuid-000")
    assert missing_resp.status_code == 404
    assert "not found" in missing_resp.json()["detail"]


def test_export_run_json_and_markdown():
    """Verify GET /api/runs/{run_id}/export returns JSON or Markdown file downloads."""
    list_resp = client.get("/api/runs")
    valid_id = list_resp.json()[0]["run_id"]

    # 1. Export JSON
    json_resp = client.get(f"/api/runs/{valid_id}/export?format=json")
    assert json_resp.status_code == 200
    assert json_resp.headers["content-type"].startswith("application/json")
    assert "attachment;" in json_resp.headers["content-disposition"]
    assert f"recallbench_{valid_id}.json" in json_resp.headers["content-disposition"]
    assert '"overall_score": 1.0' in json_resp.text

    # 2. Export Markdown
    md_resp = client.get(f"/api/runs/{valid_id}/export?format=markdown")
    assert md_resp.status_code == 200
    assert md_resp.headers["content-type"].startswith("text/markdown")
    assert "attachment;" in md_resp.headers["content-disposition"]
    assert f"recallbench_{valid_id}.md" in md_resp.headers["content-disposition"]
    assert "# RecallBench Run Report" in md_resp.text


def test_export_run_unsupported_format():
    """Verify GET /api/runs/{run_id}/export rejects unsupported format with 400."""
    list_resp = client.get("/api/runs")
    valid_id = list_resp.json()[0]["run_id"]

    response = client.get(f"/api/runs/{valid_id}/export?format=pdf")
    assert response.status_code == 400
    assert "Unsupported export format" in response.json()["detail"]


def test_concurrent_run_rejection():
    """Verify overlapping run requests are rejected with 409 Conflict when a run is already active."""
    # Acquire service lock manually to simulate an active background run
    acquired = benchmark_service._lock.acquire(blocking=False)
    assert acquired, "Should acquire lock"

    try:
        # A concurrent request must be rejected with 409
        response = client.post("/api/runs", json={"adapter": "sqlite"})
        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"]
    finally:
        benchmark_service._lock.release()


def test_create_run_invalid_scenario_ids():
    """Verify POST /api/runs with non-matching scenario_ids returns 400 Bad Request."""
    response = client.post("/api/runs", json={"adapter": "in_memory", "scenario_ids": ["nonexistent_sc_999"]})
    assert response.status_code == 400
    assert "None of the requested scenario_ids matched" in response.json()["detail"]


def test_export_run_missing_run_id():
    """Verify GET /api/runs/{run_id}/export returns 404 Not Found for nonexistent run ID."""
    response = client.get("/api/runs/nonexistent-run-uuid-000/export?format=json")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
