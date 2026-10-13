"""FastAPI router for RecallBench endpoints."""
import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.schemas import (
    BenchmarksListResponse,
    BenchmarkSummary,
    HealthResponse,
    RunCreateRequest,
    RunSummaryResponse,
    ScenarioDetailResponse,
)
from app.api.service import (
    SUPPORTED_ADAPTERS,
    SUPPORTED_EXPORT_FORMATS,
    benchmark_service,
)
from app.domain.enums import BenchmarkCategory
from app.engine.runner import BenchmarkRunReport

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def get_health() -> HealthResponse:
    """Return service status and catalog counts."""
    scenarios = benchmark_service.get_catalog_scenarios()
    return HealthResponse(
        status="ok",
        version="1.0.0",
        catalog_version="1.0.0",
        scenarios_count=len(scenarios),
    )


@router.get("/api/benchmarks", response_model=BenchmarksListResponse, tags=["Benchmarks"])
def list_benchmarks() -> BenchmarksListResponse:
    """List all available benchmark categories and scenarios."""
    scenarios = benchmark_service.get_catalog_scenarios()
    summaries = [
        BenchmarkSummary(
            scenario_id=s.scenario_id,
            category=s.category,
            description=s.description,
            file=f"{s.category.value.lower()}/{s.scenario_id}.json",
            queries_count=len(s.queries),
        )
        for s in scenarios
    ]
    categories = sorted(list({s.category.value for s in scenarios}))
    return BenchmarksListResponse(categories=categories, scenarios=summaries)


@router.get("/api/benchmarks/{scenario_id}", response_model=ScenarioDetailResponse, tags=["Benchmarks"])
def get_benchmark_scenario(scenario_id: str) -> ScenarioDetailResponse:
    """Retrieve detailed scenario metadata, timeline, and query expectations."""
    scenario = benchmark_service.get_scenario_by_id(scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark scenario '{scenario_id}' not found in catalog.",
        )

    # Sanitize timeline events (do not expose internal system internals)
    raw_events = [e.model_dump(mode="json", exclude_none=True) for e in scenario.timeline_events]
    raw_queries = []
    for q in scenario.queries:
        raw_queries.append({
            "query_id": q.query_id,
            "query": q.query.model_dump(mode="json", exclude_none=True),
            "ground_truth": q.ground_truth.model_dump(mode="json", exclude_none=True),
        })

    return ScenarioDetailResponse(
        scenario_id=scenario.scenario_id,
        version=scenario.version,
        category=scenario.category,
        description=scenario.description,
        contradiction_policy=scenario.contradiction_policy,
        timeline_events=raw_events,
        queries=raw_queries,
    )


@router.post(
    "/api/runs",
    response_model=BenchmarkRunReport,
    status_code=status.HTTP_201_CREATED,
    tags=["Runs"],
)
def create_run(request: RunCreateRequest) -> BenchmarkRunReport:
    """Execute a benchmark evaluation run against a selected memory adapter."""
    # 1. Validate adapter against allowlist
    norm_adapter = request.adapter.strip().lower()
    if norm_adapter not in SUPPORTED_ADAPTERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported adapter '{request.adapter}'. Supported options: {sorted(list(SUPPORTED_ADAPTERS))}",
        )

    # 2. Execute run under concurrency lock
    try:
        report = benchmark_service.execute_run(
            adapter_name=norm_adapter,
            scenario_ids=request.scenario_ids,
        )
        return report
    except RuntimeError as lock_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(lock_err),
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Benchmark execution encountered an error: {str(exc)}",
        )


@router.get("/api/runs", response_model=List[RunSummaryResponse], tags=["Runs"])
def list_runs() -> List[RunSummaryResponse]:
    """List recent benchmark execution runs."""
    runs = benchmark_service.list_runs()
    return [
        RunSummaryResponse(
            run_id=r.run_id,
            store_name=r.store_name,
            timestamp=r.timestamp,
            scenarios_evaluated=r.scenarios_evaluated,
            total_queries=r.total_queries,
            passed_queries=r.passed_queries,
            failed_queries=r.failed_queries,
            overall_score=r.aggregate_metrics.overall_score,
            micro_pass_rate=r.aggregate_metrics.micro_pass_rate,
        )
        for r in runs
    ]


@router.get("/api/runs/{run_id}", response_model=BenchmarkRunReport, tags=["Runs"])
def get_run(run_id: str) -> BenchmarkRunReport:
    """Retrieve full execution report including scenario-by-scenario results."""
    report = benchmark_service.get_run(run_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark run '{run_id}' not found.",
        )
    return report


@router.get("/api/runs/{run_id}/export", tags=["Runs"])
def export_run(
    run_id: str,
    format: str = Query(default="json", description="Export format: 'json' or 'markdown'"),
) -> Response:
    """Export a completed benchmark run report as a downloadable JSON or Markdown file."""
    norm_fmt = format.strip().lower()
    if norm_fmt not in SUPPORTED_EXPORT_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format '{format}'. Supported formats: {sorted(list(SUPPORTED_EXPORT_FORMATS))}",
        )

    try:
        content = benchmark_service.export_run(run_id, export_format=norm_fmt)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark run '{run_id}' not found.",
        )

    if norm_fmt == "json":
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="recallbench_{run_id}.json"'},
        )
    else:
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="recallbench_{run_id}.md"'},
        )
