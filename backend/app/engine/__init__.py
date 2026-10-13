"""RecallBench Evaluation and Benchmark Execution Engine."""
from .evaluator import (
    BenchmarkScenario,
    CatalogEntry,
    CatalogManifest,
    EvaluatorEngine,
    ScenarioQuery,
    TimelineEvent,
    load_scenario_from_dict,
    load_scenario_from_file,
)
from .metrics import (
    AggregateMetrics,
    LatencyStats,
    calculate_latency_stats,
    calculate_metrics,
)
from .reporter import (
    generate_dict_report,
    generate_json_report,
    generate_markdown_summary,
)
from .runner import (
    BenchmarkRunner,
    BenchmarkRunReport,
    ScenarioRunResult,
    load_catalog_scenarios,
)

__all__ = [
    "BenchmarkScenario",
    "CatalogEntry",
    "CatalogManifest",
    "ScenarioQuery",
    "TimelineEvent",
    "load_scenario_from_dict",
    "load_scenario_from_file",
    "EvaluatorEngine",
    "AggregateMetrics",
    "LatencyStats",
    "calculate_latency_stats",
    "calculate_metrics",
    "BenchmarkRunner",
    "BenchmarkRunReport",
    "ScenarioRunResult",
    "load_catalog_scenarios",
    "generate_dict_report",
    "generate_json_report",
    "generate_markdown_summary",
]
