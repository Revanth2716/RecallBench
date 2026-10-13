"""Benchmark Runner for RecallBench.

Orchestrates scenario loading, store event ingestion, query execution,
and evaluation across the MemoryStoreAdapter boundary.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from app.domain.enums import (
    BenchmarkCategory,
    ContradictionPolicy,
    DeletionScope,
    DeletionType,
    UpdatePolicy,
)
from app.domain.models import (
    DeletionEvent,
    EvaluationResult,
    FactRecord,
    MemoryQuery,
    UpdateEvent,
)
from app.domain.protocols import MemoryStoreAdapter
from app.domain.timestamps import UtcDateTime, now_utc
from app.engine.evaluator import (
    BenchmarkScenario,
    EvaluatorEngine,
    ScenarioQuery,
    TimelineEvent,
    load_scenario_from_file,
)
from app.engine.metrics import AggregateMetrics, calculate_metrics


class ScenarioRunResult(BaseModel):
    """Result of running a single benchmark scenario against a store."""
    scenario_id: str
    category: BenchmarkCategory
    evaluations: List[EvaluationResult] = Field(default_factory=list)
    passed_count: int = 0
    total_count: int = 0
    all_passed: bool = False


class BenchmarkRunReport(BaseModel):
    """Comprehensive benchmark execution report."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_name: str
    timestamp: UtcDateTime = Field(default_factory=now_utc)
    scenarios_evaluated: int = 0
    total_queries: int = 0
    passed_queries: int = 0
    failed_queries: int = 0
    scenario_results: List[ScenarioRunResult] = Field(default_factory=list)
    aggregate_metrics: AggregateMetrics = Field(default_factory=AggregateMetrics)


def load_catalog_scenarios(catalog_or_dir_path: Path) -> List[BenchmarkScenario]:
    """Load benchmark scenarios from a catalog.json file or directory with strict integrity checks."""
    catalog_or_dir_path = Path(catalog_or_dir_path)

    if catalog_or_dir_path.is_file():
        # Either a single scenario JSON or catalog index
        with open(catalog_or_dir_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "scenarios" in data and isinstance(data["scenarios"], list):
            # Strict catalog manifest validation
            from app.engine.evaluator import CatalogManifest

            catalog_manifest = CatalogManifest(**data)
            base_dir = catalog_or_dir_path.parent
            scenarios: List[BenchmarkScenario] = []

            for entry in catalog_manifest.scenarios:
                scenario_file = base_dir / entry.file
                if not scenario_file.exists():
                    raise FileNotFoundError(
                        f"Scenario file '{entry.file}' declared for scenario '{entry.scenario_id}' "
                        f"in catalog does not exist at '{scenario_file}'"
                    )
                sc = load_scenario_from_file(scenario_file)
                if sc.scenario_id != entry.scenario_id:
                    raise ValueError(
                        f"Catalog scenario ID '{entry.scenario_id}' does not match manifest "
                        f"scenario ID '{sc.scenario_id}' in '{entry.file}'"
                    )
                if sc.category != entry.category:
                    raise ValueError(
                        f"Catalog category '{entry.category.value}' does not match manifest "
                        f"category '{sc.category.value}' in '{entry.file}'"
                    )
                scenarios.append(sc)

            # Global uniqueness check across loaded scenarios
            sc_ids = [s.scenario_id for s in scenarios]
            if len(sc_ids) != len(set(sc_ids)):
                duplicates = [x for x in sc_ids if sc_ids.count(x) > 1]
                raise ValueError(f"Duplicate scenario_id detected across catalog entries: {duplicates}")

            return scenarios
        else:
            # Single scenario file
            return [load_scenario_from_file(catalog_or_dir_path)]

    elif catalog_or_dir_path.is_dir():
        # Check if catalog.json exists in directory
        cat_file = catalog_or_dir_path / "catalog.json"
        if cat_file.exists():
            return load_catalog_scenarios(cat_file)

        # Otherwise find all json files except catalog.json
        scenarios = []
        for p in sorted(catalog_or_dir_path.glob("**/*.json")):
            if p.name == "catalog.json":
                continue
            scenarios.append(load_scenario_from_file(p))

        sc_ids = [s.scenario_id for s in scenarios]
        if len(sc_ids) != len(set(sc_ids)):
            duplicates = [x for x in sc_ids if sc_ids.count(x) > 1]
            raise ValueError(f"Duplicate scenario_id detected across directory manifests: {duplicates}")

        return scenarios

    else:
        raise FileNotFoundError(f"Path not found: {catalog_or_dir_path}")


class BenchmarkRunner:
    """Executes benchmark scenarios against any MemoryStoreAdapter."""

    def __init__(self, evaluator: Optional[EvaluatorEngine] = None):
        self.evaluator = evaluator or EvaluatorEngine()

    def run_scenario(
        self,
        store: MemoryStoreAdapter,
        scenario: BenchmarkScenario,
        reset_store: bool = True,
    ) -> ScenarioRunResult:
        """Execute a single scenario against a store and evaluate all queries."""
        if reset_store:
            store.reset()

        # Set contradiction policy if store supports it
        if hasattr(store, "default_contradiction_policy"):
            setattr(store, "default_contradiction_policy", scenario.contradiction_policy)
        if hasattr(store, "contradiction_policy"):
            setattr(store, "contradiction_policy", scenario.contradiction_policy)

        # 1. Ingest timeline events in order
        for event in scenario.timeline_events:
            # Pass dictionary representation to adapter's ingest_event
            store.ingest_event(event.model_dump(mode="json", exclude_none=True))

        # 2. Execute and evaluate all scenario queries
        evaluations: List[EvaluationResult] = []
        for sq in scenario.queries:
            # If query does not specify a contradiction policy, pass scenario's policy
            query = sq.query
            if query.contradiction_policy is None:
                query = query.model_copy(
                    update={"contradiction_policy": scenario.contradiction_policy}
                )

            prediction = store.retrieve(query)
            ev_result = self.evaluator.evaluate_prediction(prediction, sq, scenario)
            evaluations.append(ev_result)

        passed_count = sum(1 for e in evaluations if e.passed)
        total_count = len(evaluations)
        all_passed = (passed_count == total_count and total_count > 0)

        return ScenarioRunResult(
            scenario_id=scenario.scenario_id,
            category=scenario.category,
            evaluations=evaluations,
            passed_count=passed_count,
            total_count=total_count,
            all_passed=all_passed,
        )

    def run_scenarios(
        self,
        store: MemoryStoreAdapter,
        scenarios: List[BenchmarkScenario],
        store_name: str = "UnknownStore",
    ) -> BenchmarkRunReport:
        """Execute multiple scenarios against a store and aggregate results."""
        scenario_results: List[ScenarioRunResult] = []
        all_evaluations: List[EvaluationResult] = []

        for scenario in scenarios:
            res = self.run_scenario(store, scenario, reset_store=True)
            scenario_results.append(res)
            all_evaluations.extend(res.evaluations)

        agg_metrics = calculate_metrics(all_evaluations)

        return BenchmarkRunReport(
            store_name=store_name,
            timestamp=now_utc(),
            scenarios_evaluated=len(scenarios),
            total_queries=len(all_evaluations),
            passed_queries=sum(1 for e in all_evaluations if e.passed),
            failed_queries=sum(1 for e in all_evaluations if not e.passed),
            scenario_results=scenario_results,
            aggregate_metrics=agg_metrics,
        )

    def run_catalog(
        self,
        store: MemoryStoreAdapter,
        catalog_path: Path,
        store_name: str = "UnknownStore",
    ) -> BenchmarkRunReport:
        """Load and run all scenarios in a catalog."""
        scenarios = load_catalog_scenarios(catalog_path)
        return self.run_scenarios(store, scenarios, store_name=store_name)
