"""Benchmark service managing catalog inspection, execution, locking, and report persistence."""
import asyncio
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

from app.domain.enums import BenchmarkCategory
from app.domain.protocols import MemoryStoreAdapter
from app.engine.evaluator import BenchmarkScenario, load_scenario_from_file
from app.engine.reporter import generate_json_report, generate_markdown_summary
from app.engine.runner import BenchmarkRunner, BenchmarkRunReport, load_catalog_scenarios
from app.storage.in_memory_store import InMemoryMemoryStore
from app.storage.sqlite_store import SQLiteTemporalMemoryStore

# Base directory paths
BASE_DIR = Path(__file__).resolve().parents[3]
CATALOG_PATH = BASE_DIR / "benchmarks" / "catalog.json"
DATA_DIR = BASE_DIR / "backend" / "data"
RUNS_DIR = DATA_DIR / "runs"
SQLITE_DB_PATH = DATA_DIR / "benchmark_isolated.db"

# Supported adapter allowlist
SUPPORTED_ADAPTERS = {"sqlite", "in_memory"}
SUPPORTED_EXPORT_FORMATS = {"json", "markdown"}


class BenchmarkService:
    """Manages catalog caching, execution runs, mutual exclusion, and reporting."""

    def __init__(self):
        self._lock = threading.Lock()
        self._runs: Dict[str, BenchmarkRunReport] = {}
        self._runner = BenchmarkRunner()
        self._ensure_storage()
        self._load_cached_runs()

    def _ensure_storage(self) -> None:
        """Ensure isolated data directories exist."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_cached_runs(self) -> None:
        """Load any previously saved runs from local storage on startup."""
        if not RUNS_DIR.exists():
            return
        for run_file in RUNS_DIR.glob("*.json"):
            try:
                with open(run_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                report = BenchmarkRunReport(**data)
                self._runs[report.run_id] = report
            except Exception:
                # Corrupted run file ignored
                pass

    def get_catalog_scenarios(self) -> List[BenchmarkScenario]:
        """Load and return all validated catalog scenarios."""
        return load_catalog_scenarios(CATALOG_PATH)

    def get_scenario_by_id(self, scenario_id: str) -> Optional[BenchmarkScenario]:
        """Retrieve a specific scenario manifest by ID."""
        scenarios = self.get_catalog_scenarios()
        for sc in scenarios:
            if sc.scenario_id == scenario_id:
                return sc
        return None

    def create_adapter(self, adapter_name: str) -> MemoryStoreAdapter:
        """Create a target store adapter from the strict allowlist."""
        norm_name = adapter_name.strip().lower()
        if norm_name not in SUPPORTED_ADAPTERS:
            raise ValueError(
                f"Unsupported adapter '{adapter_name}'. Allowed adapters are: {sorted(list(SUPPORTED_ADAPTERS))}"
            )

        if norm_name == "sqlite":
            return SQLiteTemporalMemoryStore(db_path=str(SQLITE_DB_PATH))
        elif norm_name == "in_memory":
            return InMemoryMemoryStore()
        else:
            raise ValueError(f"Unknown adapter: {norm_name}")

    def execute_run(
        self,
        adapter_name: str = "sqlite",
        scenario_ids: Optional[List[str]] = None,
    ) -> BenchmarkRunReport:
        """Execute a benchmark run under mutual exclusion to prevent race conditions."""
        # Validate adapter
        norm_name = adapter_name.strip().lower()
        if norm_name not in SUPPORTED_ADAPTERS:
            raise ValueError(
                f"Unsupported adapter '{adapter_name}'. Allowed adapters are: {sorted(list(SUPPORTED_ADAPTERS))}"
            )

        # Acquire lock non-blockingly; if busy, raise conflict
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            raise RuntimeError("A benchmark run is already in progress. Please wait for it to complete.")

        store: Optional[MemoryStoreAdapter] = None
        try:
            all_scenarios = self.get_catalog_scenarios()
            if scenario_ids:
                id_set = set(scenario_ids)
                selected_scenarios = [s for s in all_scenarios if s.scenario_id in id_set]
                if not selected_scenarios:
                    raise ValueError(f"None of the requested scenario_ids matched available catalog scenarios.")
            else:
                selected_scenarios = all_scenarios

            store = self.create_adapter(norm_name)
            display_name = f"SQLite Store (isolated)" if norm_name == "sqlite" else "In-Memory Store"

            report = self._runner.run_scenarios(
                store=store,
                scenarios=selected_scenarios,
                store_name=display_name,
            )

            # Store in session memory
            self._runs[report.run_id] = report

            # Persist to local JSON file
            try:
                run_file = RUNS_DIR / f"{report.run_id}.json"
                run_file.write_text(generate_json_report(report), encoding="utf-8")
            except Exception:
                pass

            return report

        finally:
            if store and hasattr(store, "close"):
                try:
                    store.close()
                except Exception:
                    pass
            self._lock.release()

    def list_runs(self) -> List[BenchmarkRunReport]:
        """Return list of all recorded runs, sorted by timestamp descending."""
        return sorted(self._runs.values(), key=lambda r: r.timestamp, reverse=True)

    def get_run(self, run_id: str) -> Optional[BenchmarkRunReport]:
        """Retrieve a specific run report by ID."""
        return self._runs.get(run_id)

    def export_run(self, run_id: str, export_format: str = "json") -> str:
        """Export a completed report as JSON or Markdown."""
        report = self.get_run(run_id)
        if not report:
            raise KeyError(f"Run ID '{run_id}' not found.")

        fmt = export_format.strip().lower()
        if fmt not in SUPPORTED_EXPORT_FORMATS:
            raise ValueError(
                f"Unsupported export format '{export_format}'. Allowed formats are: {sorted(list(SUPPORTED_EXPORT_FORMATS))}"
            )

        if fmt == "json":
            return generate_json_report(report)
        else:
            return generate_markdown_summary(report)


# Global singleton service instance
benchmark_service = BenchmarkService()
