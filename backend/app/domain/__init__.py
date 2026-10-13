"""Domain layer of RecallBench."""
from .enums import (
    BenchmarkCategory,
    ContradictionPolicy,
    DeletionScope,
    DeletionType,
    QueryStatus,
    UpdatePolicy,
)
from .models import (
    DeletionEvent,
    Entity,
    EvaluationResult,
    FactRecord,
    GroundTruth,
    MemoryQuery,
    QueryPrediction,
    UpdateEvent,
)
from .protocols import MemoryStoreAdapter
from .semantics import (
    apply_deletion,
    apply_temporal_supersede,
    evaluate_query_against_facts,
    resolve_contradiction,
)
from .temporal import (
    interval_intersection,
    intervals_overlap,
    is_point_in_interval,
    split_interval,
)
from .timestamps import (
    OptionalUtcDateTime,
    UtcDateTime,
    utc_now,
    validate_and_normalize_optional_utc,
    validate_and_normalize_utc,
)

__all__ = [
    "BenchmarkCategory",
    "ContradictionPolicy",
    "DeletionScope",
    "DeletionType",
    "QueryStatus",
    "UpdatePolicy",
    "Entity",
    "FactRecord",
    "UpdateEvent",
    "DeletionEvent",
    "MemoryQuery",
    "QueryPrediction",
    "GroundTruth",
    "EvaluationResult",
    "MemoryStoreAdapter",
    "apply_temporal_supersede",
    "resolve_contradiction",
    "apply_deletion",
    "evaluate_query_against_facts",
    "is_point_in_interval",
    "intervals_overlap",
    "interval_intersection",
    "split_interval",
    "validate_and_normalize_utc",
    "validate_and_normalize_optional_utc",
    "utc_now",
    "UtcDateTime",
    "OptionalUtcDateTime",
]
