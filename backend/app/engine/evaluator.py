"""Independent Evaluation Engine for RecallBench.

Strictly decoupled from target memory stores:
- Ground truth is loaded from independent static scenario manifests.
- Evaluates QueryPrediction DTOs across the adapter boundary.
- Never inspects database tables or internal data structures.
- Never reuses store resolution logic to determine what answers should be.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from app.domain.enums import (
    BenchmarkCategory,
    ContradictionPolicy,
    DeletionScope,
    DeletionType,
    QueryStatus,
    UpdatePolicy,
)
from app.domain.models import EvaluationResult, GroundTruth, MemoryQuery, QueryPrediction
from app.domain.timestamps import OptionalUtcDateTime, UtcDateTime


class TimelineEvent(BaseModel):
    """An event defined in a benchmark scenario timeline."""
    event_type: str = Field(..., description="INSERT, UPDATE, or DELETE")
    event_id: str = Field(..., min_length=1)
    timestamp: UtcDateTime
    entity_id: str = Field(..., min_length=1)
    attribute: Optional[str] = None
    value: Optional[Any] = None
    valid_from: OptionalUtcDateTime = None
    valid_to: OptionalUtcDateTime = None
    effective_time: OptionalUtcDateTime = None
    policy: Optional[UpdatePolicy] = None
    deletion_type: Optional[DeletionType] = None
    deletion_scope: Optional[DeletionScope] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_bounds(self) -> "TimelineEvent":
        if self.valid_from is not None and self.valid_to is not None:
            if self.valid_from >= self.valid_to:
                raise ValueError(
                    f"Event '{self.event_id}' has valid_from >= valid_to ({self.valid_from} >= {self.valid_to})"
                )
        return self


class ScenarioQuery(BaseModel):
    """A query specification within a benchmark scenario."""
    query_id: str = Field(..., min_length=1)
    query: MemoryQuery
    ground_truth: GroundTruth

    @model_validator(mode="before")
    @classmethod
    def populate_query_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            qid = data.get("query_id")
            q = data.get("query")
            if qid and isinstance(q, dict) and "query_id" not in q:
                q["query_id"] = qid
        return data



class BenchmarkScenario(BaseModel):
    """A versioned, self-contained synthetic benchmark scenario manifest."""
    scenario_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    category: BenchmarkCategory
    description: str = Field(..., min_length=1)
    contradiction_policy: ContradictionPolicy = Field(
        default=ContradictionPolicy.DETERMINISTIC_ABSTAIN
    )
    timeline_events: List[TimelineEvent] = Field(..., min_length=1)
    queries: List[ScenarioQuery] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_manifest_integrity(self) -> "BenchmarkScenario":
        # Check unique event IDs
        event_ids = [e.event_id for e in self.timeline_events]
        if len(event_ids) != len(set(event_ids)):
            duplicates = [x for x in event_ids if event_ids.count(x) > 1]
            raise ValueError(f"Duplicate event_id detected in scenario '{self.scenario_id}': {duplicates}")

        # Check unique query IDs
        query_ids = [q.query_id for q in self.queries]
        if len(query_ids) != len(set(query_ids)):
            duplicates = [x for x in query_ids if query_ids.count(x) > 1]
            raise ValueError(f"Duplicate query_id detected in scenario '{self.scenario_id}': {duplicates}")

        # Validate ground truth consistency
        for sq in self.queries:
            gt = sq.ground_truth
            if gt.expected_abstention and gt.expected_value is not None:
                raise ValueError(
                    f"Query '{sq.query_id}' expects abstention but specifies non-None expected_value: {gt.expected_value}"
                )
            if not gt.expected_abstention and gt.expected_status == QueryStatus.FOUND and gt.expected_value is None:
                raise ValueError(
                    f"Query '{sq.query_id}' expects FOUND status but specifies None expected_value without abstention flag"
                )

        return self


class CatalogEntry(BaseModel):
    """An entry declared in the benchmark catalog index."""
    scenario_id: str = Field(..., min_length=1)
    category: BenchmarkCategory
    file: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class CatalogManifest(BaseModel):
    """The root catalog manifest structure (benchmarks/catalog.json)."""
    version: str = Field(..., min_length=1)
    scenarios: List[CatalogEntry] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_catalog_integrity(self) -> "CatalogManifest":
        ids = [s.scenario_id for s in self.scenarios]
        if len(ids) != len(set(ids)):
            duplicates = [x for x in ids if ids.count(x) > 1]
            raise ValueError(f"Duplicate scenario_id declared in catalog: {duplicates}")
        files = [s.file for s in self.scenarios]
        if len(files) != len(set(files)):
            duplicates = [x for x in files if files.count(x) > 1]
            raise ValueError(f"Duplicate scenario file path declared in catalog: {duplicates}")
        return self


def load_scenario_from_dict(data: Dict[str, Any]) -> BenchmarkScenario:
    """Parse and strictly validate a scenario manifest dictionary."""
    return BenchmarkScenario(**data)


def load_scenario_from_file(file_path: Path) -> BenchmarkScenario:
    """Load and validate a scenario manifest from a JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return load_scenario_from_dict(data)


class EvaluatorEngine:
    """Evaluates QueryPrediction DTOs against independent ground truth."""

    def evaluate_prediction(
        self,
        prediction: QueryPrediction,
        query_spec: ScenarioQuery,
        scenario: BenchmarkScenario,
    ) -> EvaluationResult:
        """Compare actual prediction against static ground truth expectations."""
        gt = query_spec.ground_truth
        target_entity = query_spec.query.entity_id

        # 1. Status Match
        status_matches = (prediction.status == gt.expected_status)

        # 2. Value Match
        if gt.expected_abstention:
            value_matches = (prediction.value is None)
        else:
            value_matches = (prediction.value == gt.expected_value)

        # 3. Forbidden Value Leak Check
        is_forbidden_leak = False
        if prediction.value is not None and gt.forbidden_values:
            if prediction.value in gt.forbidden_values:
                is_forbidden_leak = True

        # Classify as stale leak if category is stale fact detection
        is_stale_leak = (
            is_forbidden_leak and scenario.category == BenchmarkCategory.STALE_FACT_DETECTION
        )

        # 4. Entity Provenance & Crossover Check
        is_entity_crossover = False
        # If prediction provides matched_entity_id, it must match target_entity
        if prediction.matched_entity_id is not None and prediction.matched_entity_id != target_entity:
            is_entity_crossover = True
        # If query expected NOT_FOUND but store returned a value, or returned a forbidden cross-entity value
        if is_forbidden_leak and scenario.category == BenchmarkCategory.ENTITY_ISOLATION:
            is_entity_crossover = True

        # 5. Tombstone Leak Check
        is_tombstone_leak = False
        if gt.expected_status in (QueryStatus.TOMBSTONED_DELETED, QueryStatus.NOT_FOUND):
            if prediction.value is not None:
                is_tombstone_leak = True

        # 6. Contradiction Strictness: Mutual exclusion
        # If policy is DETERMINISTIC_ABSTAIN: resolving to any value is an explicit failure
        if scenario.contradiction_policy == ContradictionPolicy.DETERMINISTIC_ABSTAIN:
            if gt.expected_status == QueryStatus.CONTRADICTION:
                if prediction.status != QueryStatus.CONTRADICTION or prediction.value is not None:
                    status_matches = False
                    value_matches = False

        # If policy is LAST_ASSERTION_WINS, CONFIDENCE_WEIGHTED, or MULTIVALUED_COLLECTION:
        # abstaining or failing to resolve the expected value/collection is an explicit failure
        elif scenario.contradiction_policy in (
            ContradictionPolicy.LAST_ASSERTION_WINS,
            ContradictionPolicy.CONFIDENCE_WEIGHTED,
            ContradictionPolicy.MULTIVALUED_COLLECTION,
        ):
            if gt.expected_status == QueryStatus.FOUND:
                if prediction.status != QueryStatus.FOUND or prediction.value != gt.expected_value:
                    status_matches = False
                    value_matches = False

        # Query Passes if ALL conditions hold
        passed = (
            status_matches
            and value_matches
            and not is_forbidden_leak
            and not is_entity_crossover
            and not is_tombstone_leak
        )

        error_msg: Optional[str] = None
        if not passed:
            reasons = []
            if not status_matches:
                reasons.append(f"Status mismatch (expected={gt.expected_status.value}, actual={prediction.status.value})")
            if not value_matches:
                reasons.append(f"Value mismatch (expected={gt.expected_value!r}, actual={prediction.value!r})")
            if is_stale_leak:
                reasons.append(f"Stale value leak detected: {prediction.value!r}")
            if is_forbidden_leak and not is_stale_leak:
                reasons.append(f"Forbidden value returned: {prediction.value!r}")
            if is_entity_crossover:
                reasons.append(
                    f"Entity crossover leak (target={target_entity}, matched={prediction.matched_entity_id})"
                )
            if is_tombstone_leak:
                reasons.append(f"Tombstone payload leaked: {prediction.value!r}")
            error_msg = "; ".join(reasons)

        return EvaluationResult(
            scenario_id=scenario.scenario_id,
            query_id=query_spec.query_id,
            category=scenario.category,
            passed=passed,
            expected_status=gt.expected_status,
            actual_status=prediction.status,
            expected_value=gt.expected_value,
            actual_value=prediction.value,
            is_stale_leak=is_stale_leak,
            is_tombstone_leak=is_tombstone_leak,
            is_entity_crossover=is_entity_crossover,
            error_message=error_msg,
            latency_ms=prediction.latency_ms,
        )
