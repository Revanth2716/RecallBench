"""Pydantic API request and response schemas for RecallBench."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.domain.enums import BenchmarkCategory, ContradictionPolicy
from app.engine.metrics import AggregateMetrics
from app.engine.runner import BenchmarkRunReport, ScenarioRunResult


class HealthResponse(BaseModel):
    """Health and service status schema."""
    status: str = "ok"
    version: str = "1.0.0"
    catalog_version: str = "1.0.0"
    scenarios_count: int


class BenchmarkSummary(BaseModel):
    """Brief metadata for a catalog scenario."""
    scenario_id: str
    category: BenchmarkCategory
    description: str
    file: str
    queries_count: int


class BenchmarksListResponse(BaseModel):
    """List of all benchmark categories and scenarios."""
    categories: List[str]
    scenarios: List[BenchmarkSummary]


class ScenarioDetailResponse(BaseModel):
    """Full detail of a benchmark scenario for inspection."""
    scenario_id: str
    version: str
    category: BenchmarkCategory
    description: str
    contradiction_policy: ContradictionPolicy
    timeline_events: List[Dict[str, Any]]
    queries: List[Dict[str, Any]]


class RunCreateRequest(BaseModel):
    """Request payload to initiate a benchmark run."""
    adapter: str = Field(
        default="sqlite",
        description="Target store adapter allowlist: 'sqlite' or 'in_memory'",
    )
    scenario_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional subset of scenario IDs to run. Defaults to entire catalog.",
    )


class RunSummaryResponse(BaseModel):
    """Compact summary of a benchmark run for history listing."""
    run_id: str
    store_name: str
    timestamp: datetime
    scenarios_evaluated: int
    total_queries: int
    passed_queries: int
    failed_queries: int
    overall_score: Optional[float] = None
    micro_pass_rate: Optional[float] = None
