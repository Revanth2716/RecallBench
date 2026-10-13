"""Core Pydantic domain models for RecallBench."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from .enums import (
    BenchmarkCategory,
    ContradictionPolicy,
    DeletionScope,
    DeletionType,
    QueryStatus,
    UpdatePolicy,
)
from .timestamps import OptionalUtcDateTime, UtcDateTime


class Entity(BaseModel):
    """An entity (user, agent, system, or organization) whose memories are tracked."""
    id: str = Field(..., min_length=1, description="Unique entity identifier")
    name: str = Field(..., min_length=1)
    entity_type: str = Field(default="generic", description="e.g. user, agent, session")
    created_at: UtcDateTime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FactRecord(BaseModel):
    """A single factual statement with bitemporal coordinates and provenance."""
    id: str = Field(..., min_length=1, description="Unique fact ID")
    entity_id: str = Field(..., min_length=1, description="Associated entity ID")
    attribute: str = Field(..., min_length=1, description="Memory slot/attribute key")
    value: Any = Field(..., description="Fact payload (scalar, dict, list)")

    # Valid Time Coordinates [valid_from, valid_to) — half-open interval
    valid_from: UtcDateTime = Field(..., description="Start of world validity (inclusive)")
    valid_to: OptionalUtcDateTime = Field(None, description="End of world validity (exclusive); None = open-ended")

    # Assertion/Transaction Time Coordinates [asserted_at, retracted_at)
    asserted_at: UtcDateTime = Field(..., description="Timestamp when system learned this fact")
    retracted_at: OptionalUtcDateTime = Field(None, description="Timestamp when system retracted this assertion")

    # Provenance and Lifecycle
    version: int = Field(default=1, ge=1)
    superseded_by: Optional[str] = None
    is_deleted: bool = Field(default=False)
    deleted_at: OptionalUtcDateTime = None
    deletion_scope: Optional[DeletionScope] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_intervals(self) -> "FactRecord":
        if self.valid_to is not None and self.valid_from >= self.valid_to:
            raise ValueError(
                f"valid_from ({self.valid_from.isoformat()}) must be strictly earlier than valid_to ({self.valid_to.isoformat()})"
            )
        if self.retracted_at is not None and self.asserted_at > self.retracted_at:
            raise ValueError(
                f"asserted_at ({self.asserted_at.isoformat()}) cannot be later than retracted_at ({self.retracted_at.isoformat()})"
            )
        return self


class UpdateEvent(BaseModel):
    """Event describing a proposed modification to an entity attribute."""
    event_id: str = Field(..., min_length=1)
    entity_id: str = Field(..., min_length=1)
    attribute: str = Field(..., min_length=1)
    new_value: Any
    effective_time: UtcDateTime = Field(..., description="Start of validity for new value")
    valid_to: OptionalUtcDateTime = Field(None, description="Optional finite valid_to for the new value")
    asserted_at: UtcDateTime = Field(..., description="System transaction timestamp")
    policy: UpdatePolicy = Field(default=UpdatePolicy.TEMPORAL_SUPERSEDE)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_update_bounds(self) -> "UpdateEvent":
        if self.valid_to is not None and self.effective_time >= self.valid_to:
            raise ValueError("effective_time must be strictly earlier than valid_to")
        return self


class DeletionEvent(BaseModel):
    """Event specifying explicit deletion / forgetting of facts."""
    event_id: str = Field(..., min_length=1)
    entity_id: str = Field(..., min_length=1)
    attribute: Optional[str] = Field(None, description="Target attribute; None deletes all entity facts")
    deletion_type: DeletionType = Field(default=DeletionType.LOGICAL_TOMBSTONE)
    deletion_scope: DeletionScope = Field(default=DeletionScope.FORWARD_ONLY)
    effective_time: UtcDateTime = Field(..., description="Timestamp from which deletion is effective")
    asserted_at: UtcDateTime = Field(..., description="System transaction timestamp")
    reason: Optional[str] = None


class MemoryQuery(BaseModel):
    """Query parameterizing point-in-time memory retrieval."""
    query_id: str = Field(..., min_length=1)
    entity_id: str = Field(..., min_length=1)
    attribute: str = Field(..., min_length=1)
    as_of_valid_time: OptionalUtcDateTime = Field(None, description="Point in valid-time (None = current)")
    as_of_assertion_time: OptionalUtcDateTime = Field(None, description="Point in assertion-time (None = latest)")
    include_tombstones: bool = Field(default=False, description="Normal retrieval MUST keep False")
    contradiction_policy: Optional[ContradictionPolicy] = Field(None, description="Optional per-query contradiction resolution policy")


class QueryPrediction(BaseModel):
    """Black-box prediction returned across the Target-Store Adapter boundary."""
    query_id: str = Field(..., min_length=1)
    status: QueryStatus
    value: Any = None
    # Adapter-supplied provenance evidence (used to audit cross-entity leaks and identity):
    matched_entity_id: Optional[str] = None
    fact_id: Optional[str] = None
    valid_interval: Optional[List[Optional[datetime]]] = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    diagnostic_info: Optional[str] = None


class GroundTruth(BaseModel):
    """Independently authored ground truth expectation for a query."""
    expected_status: QueryStatus
    expected_abstention: bool = Field(default=False)
    expected_value: Any = None
    forbidden_values: List[Any] = Field(default_factory=list)
    allowed_cross_entity_values: List[Any] = Field(default_factory=list)
    valid_interval: Optional[List[Optional[str]]] = None


class EvaluationResult(BaseModel):
    """Granular result of evaluating a single QueryPrediction against GroundTruth."""
    scenario_id: str
    query_id: str
    category: BenchmarkCategory
    passed: bool
    expected_status: QueryStatus
    actual_status: QueryStatus
    expected_value: Any
    actual_value: Any
    is_stale_leak: bool = False
    is_tombstone_leak: bool = False
    is_entity_crossover: bool = False
    error_message: Optional[str] = None
    latency_ms: float = 0.0
