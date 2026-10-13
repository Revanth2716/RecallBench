"""Metric calculations for RecallBench.

All rates are bounded in [0.0, 1.0]. Empty denominators return None (null),
preventing deceptive 100% or 0% ratings when a category has zero queries.
Latency is reported observationally as distribution statistics (mean, p50, p95, p99).
"""
import statistics
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.domain.enums import BenchmarkCategory
from app.domain.models import EvaluationResult


class LatencyStats(BaseModel):
    """Observational latency statistics in milliseconds."""
    count: int = 0
    mean_ms: Optional[float] = None
    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    p99_ms: Optional[float] = None


class AggregateMetrics(BaseModel):
    """Summary metrics across a benchmark run.

    Aggregation semantics:
    - TRAcc (Temporal Recall Accuracy): Fraction of temporal recall queries passing.
    - SFR (Stale Fact Rate): Fraction of stale-fact detection queries leaking superseded facts [0.0 is optimal].
    - SFAcc (Stale Fact Accuracy): Derived accuracy dimension = (1.0 - SFR) [1.0 is optimal].
    - CHS (Contradiction Handling Score): Fraction of contradiction queries resolving or abstaining as specified.
    - EIA (Entity Isolation Accuracy): Fraction of entity queries passing with zero cross-entity crossover.
    - DC (Deletion Compliance): Fraction of deletion queries passing with zero tombstone payload leaks.
    - overall_score (Macro Reliability Score): Unweighted arithmetic mean across active category reliability dimensions.
    - micro_pass_rate (Raw Query Pass Rate): Fraction of total individual queries passing across all scenarios.
    """
    total_queries: int = 0
    passed_queries: int = 0
    failed_queries: int = 0
    overall_score: Optional[float] = None
    micro_pass_rate: Optional[float] = None

    temporal_recall_accuracy: Optional[float] = None
    stale_fact_rate: Optional[float] = None
    stale_fact_accuracy: Optional[float] = None
    contradiction_handling_score: Optional[float] = None
    entity_isolation_accuracy: Optional[float] = None
    deletion_compliance: Optional[float] = None

    latency: LatencyStats = Field(default_factory=LatencyStats)


def calculate_latency_stats(latencies_ms: List[float]) -> LatencyStats:
    """Calculate observational latency distribution percentiles."""
    if not latencies_ms:
        return LatencyStats()

    sorted_lat = sorted(latencies_ms)
    n = len(sorted_lat)

    def percentile(p: float) -> float:
        idx = int(round(p * (n - 1)))
        return round(sorted_lat[min(max(idx, 0), n - 1)], 3)

    return LatencyStats(
        count=n,
        mean_ms=round(statistics.mean(sorted_lat), 3),
        p50_ms=round(statistics.median(sorted_lat), 3),
        p95_ms=percentile(0.95),
        p99_ms=percentile(0.99),
    )


def calculate_metrics(evaluations: List[EvaluationResult]) -> AggregateMetrics:
    """Aggregate individual EvaluationResults into rigorous benchmark metrics."""
    if not evaluations:
        return AggregateMetrics()

    by_category: Dict[BenchmarkCategory, List[EvaluationResult]] = {
        cat: [] for cat in BenchmarkCategory
    }
    for ev in evaluations:
        by_category[ev.category].append(ev)

    # 1. Temporal Recall Accuracy (TRAcc)
    tr_list = by_category[BenchmarkCategory.TEMPORAL_RECALL]
    tr_acc: Optional[float] = (
        round(sum(1 for ev in tr_list if ev.passed) / len(tr_list), 4)
        if tr_list else None
    )

    # 2. Stale Fact Rate (SFR) — fraction of queries where a stale/superseded fact was leaked
    # Derived Stale Fact Accuracy (SFAcc) = 1.0 - SFR
    sf_list = by_category[BenchmarkCategory.STALE_FACT_DETECTION]
    sf_rate: Optional[float] = (
        round(sum(1 for ev in sf_list if ev.is_stale_leak) / len(sf_list), 4)
        if sf_list else None
    )
    sf_acc: Optional[float] = (
        round(1.0 - sf_rate, 4) if sf_rate is not None else None
    )

    # 3. Contradiction Handling Score (CHS)
    ch_list = by_category[BenchmarkCategory.CONTRADICTION_HANDLING]
    ch_score: Optional[float] = (
        round(sum(1 for ev in ch_list if ev.passed) / len(ch_list), 4)
        if ch_list else None
    )

    # 4. Entity Isolation Accuracy (EIA) — strict requirement: query passed AND zero crossover
    ei_list = by_category[BenchmarkCategory.ENTITY_ISOLATION]
    ei_acc: Optional[float] = (
        round(sum(1 for ev in ei_list if ev.passed and not ev.is_entity_crossover) / len(ei_list), 4)
        if ei_list else None
    )

    # 5. Deletion Compliance (DC) — strict requirement: query passed AND zero tombstone leaks
    dc_list = by_category[BenchmarkCategory.DELETION_COMPLIANCE]
    dc_comp: Optional[float] = (
        round(sum(1 for ev in dc_list if ev.passed and not ev.is_tombstone_leak) / len(dc_list), 4)
        if dc_list else None
    )

    # Composite Overall Score: Macro-average across active category reliability dimensions
    # For SFR, the positive accuracy dimension (sf_acc = 1.0 - SFR) is included.
    active_scores: List[float] = []
    if tr_acc is not None:
        active_scores.append(tr_acc)
    if sf_acc is not None:
        active_scores.append(sf_acc)
    if ch_score is not None:
        active_scores.append(ch_score)
    if ei_acc is not None:
        active_scores.append(ei_acc)
    if dc_comp is not None:
        active_scores.append(dc_comp)

    overall: Optional[float] = (
        round(sum(active_scores) / len(active_scores), 4)
        if active_scores else None
    )

    total_n = len(evaluations)
    passed_n = sum(1 for ev in evaluations if ev.passed)
    micro_rate: Optional[float] = round(passed_n / total_n, 4) if total_n > 0 else None

    latencies = [ev.latency_ms for ev in evaluations if ev.latency_ms is not None]

    return AggregateMetrics(
        total_queries=total_n,
        passed_queries=passed_n,
        failed_queries=total_n - passed_n,
        overall_score=overall,
        micro_pass_rate=micro_rate,
        temporal_recall_accuracy=tr_acc,
        stale_fact_rate=sf_rate,
        stale_fact_accuracy=sf_acc,
        contradiction_handling_score=ch_score,
        entity_isolation_accuracy=ei_acc,
        deletion_compliance=dc_comp,
        latency=calculate_latency_stats(latencies),
    )
