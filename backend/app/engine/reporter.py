"""Diagnostic reporting and summary generator for RecallBench benchmark runs."""
import json
from typing import Any, Dict
from app.engine.runner import BenchmarkRunReport


def generate_dict_report(report: BenchmarkRunReport) -> Dict[str, Any]:
    """Convert a BenchmarkRunReport into a clean dictionary representation."""
    return report.model_dump(mode="json")


def generate_json_report(report: BenchmarkRunReport, indent: int = 2) -> str:
    """Format a BenchmarkRunReport as a JSON string."""
    return json.dumps(generate_dict_report(report), indent=indent)


def generate_markdown_summary(report: BenchmarkRunReport) -> str:
    """Generate a GitHub-flavored markdown report summarizing benchmark results."""
    m = report.aggregate_metrics
    lat = m.latency

    def fmt_pct(val: Any) -> str:
        if val is None:
            return "N/A"
        return f"{val * 100:.1f}%"

    def fmt_num(val: Any) -> str:
        if val is None:
            return "N/A"
        return f"{val:.3f}"

    overall_str = fmt_pct(m.overall_score)
    tr_str = fmt_pct(m.temporal_recall_accuracy)
    sf_str = fmt_pct(m.stale_fact_rate)
    ch_str = fmt_pct(m.contradiction_handling_score)
    ei_str = fmt_pct(m.entity_isolation_accuracy)
    dc_str = fmt_pct(m.deletion_compliance)

    lines = [
        f"# RecallBench Run Report: `{report.store_name}`",
        "",
        f"- **Run ID:** `{report.run_id}`",
        f"- **Timestamp:** `{report.timestamp.isoformat()}`",
        f"- **Scenarios Evaluated:** {report.scenarios_evaluated}",
        f"- **Total Queries:** {report.total_queries} ({report.passed_queries} passed, {report.failed_queries} failed)",
        f"- **Query Pass Rate (Micro):** {fmt_pct(m.micro_pass_rate)}",
        f"- **Overall Reliability Score:** **{overall_str}**",
        "",
        "## Category Reliability Metrics",
        "",
        "| Metric | Dimension | Value | Target | Status |",
        "| :--- | :--- | :--- | :--- | :--- |",
        f"| **TRAcc** | Temporal Recall Accuracy | {tr_str} | 100.0% | {'PASS' if m.temporal_recall_accuracy == 1.0 else 'FAIL'} |",
        f"| **SFR** | Stale Fact Rate | {sf_str} | 0.0% | {'PASS' if m.stale_fact_rate == 0.0 else 'FAIL'} |",
        f"| **CHS** | Contradiction Handling Score | {ch_str} | 100.0% | {'PASS' if m.contradiction_handling_score == 1.0 else 'FAIL'} |",
        f"| **EIA** | Entity Isolation Accuracy | {ei_str} | 100.0% | {'PASS' if m.entity_isolation_accuracy == 1.0 else 'FAIL'} |",
        f"| **DC** | Deletion Compliance | {dc_str} | 100.0% | {'PASS' if m.deletion_compliance == 1.0 else 'FAIL'} |",

        "",
        "## Latency Distribution (ms)",
        "",
        f"- **Mean Latency:** {fmt_num(lat.mean_ms)} ms",
        f"- **p50 (Median):** {fmt_num(lat.p50_ms)} ms",
        f"- **p95:** {fmt_num(lat.p95_ms)} ms",
        f"- **p99:** {fmt_num(lat.p99_ms)} ms",
        "",
        "## Scenario Breakdown",
        "",
        "| Scenario ID | Category | Passed / Total | Status |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for sr in report.scenario_results:
        status_badge = "PASS" if sr.all_passed else "FAIL"
        lines.append(
            f"| `{sr.scenario_id}` | `{sr.category.value}` | {sr.passed_count}/{sr.total_count} | **{status_badge}** |"
        )

    # Detailed failures section if any failed
    failed_evals = []
    for sr in report.scenario_results:
        for ev in sr.evaluations:
            if not ev.passed:
                failed_evals.append((sr.scenario_id, ev))

    if failed_evals:
        lines.extend([
            "",
            "## Failed Query Diagnostics",
            "",
            "| Scenario | Query ID | Expected Status | Actual Status | Expected Value | Actual Value | Reason |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])
        for sc_id, ev in failed_evals:
            lines.append(
                f"| `{sc_id}` | `{ev.query_id}` | `{ev.expected_status.value}` | `{ev.actual_status.value}` | "
                f"`{ev.expected_value}` | `{ev.actual_value}` | {ev.error_message or 'Unknown'} |"
            )

    lines.append("")
    return "\n".join(lines)
