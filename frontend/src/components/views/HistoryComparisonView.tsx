import { useEffect, useState, type FC } from 'react';
import { GitCompare } from 'lucide-react';
import { fetchRunReport } from '../../services/api';
import type { BenchmarkRunReport, RunSummaryResponse } from '../../types';

interface HistoryComparisonViewProps {
  historyRuns: RunSummaryResponse[];
  onSelectRunAsActive: (report: BenchmarkRunReport) => void;
}

export const HistoryComparisonView: FC<HistoryComparisonViewProps> = ({
  historyRuns,
  onSelectRunAsActive,
}) => {
  const [runAId, setRunAId] = useState<string>(historyRuns[0]?.run_id || '');
  const [runBId, setRunBId] = useState<string>(historyRuns[1]?.run_id || historyRuns[0]?.run_id || '');
  const [reportA, setReportA] = useState<BenchmarkRunReport | null>(null);
  const [reportB, setReportB] = useState<BenchmarkRunReport | null>(null);

  useEffect(() => {
    if (!runAId) return;
    fetchRunReport(runAId).then((r) => setReportA(r)).catch(() => {});
  }, [runAId]);

  useEffect(() => {
    if (!runBId) return;
    fetchRunReport(runBId).then((r) => setReportB(r)).catch(() => {});
  }, [runBId]);

  const fmtPct = (val?: number) => {
    if (val === undefined || val === null) return 'N/A';
    return `${(val * 100).toFixed(1)}%`;
  };

  const renderDelta = (valA?: number, valB?: number) => {
    if (valA === undefined || valB === undefined) return null;
    const diff = (valB - valA) * 100;
    if (Math.abs(diff) < 0.001) return <span style={{ color: 'var(--text-muted)' }}>0.0%</span>;
    if (diff > 0) {
      return <span style={{ color: 'var(--status-pass-text)' }}>+{diff.toFixed(1)}%</span>;
    }
    return <span style={{ color: 'var(--status-fail-text)' }}>{diff.toFixed(1)}%</span>;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div>
        <h2 style={{ fontSize: '18px', fontWeight: 600 }}>Run History & Comparison Laboratory</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          Inspect previous test executions and compare regression deltas across adapters or runs.
        </p>
      </div>

      {/* Side-by-Side Run Comparison Selection */}
      <div className="ws-card">
        <div className="ws-card-header">
          <span className="ws-card-title">Side-by-Side Diff Inspector</span>
          {reportA && reportB && reportA.store_name !== reportB.store_name && (
            <span className="badge badge-warn">
              Cross-Adapter Comparison: {reportA.store_name} vs {reportB.store_name}
            </span>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 60px 1fr', gap: '16px', alignItems: 'center' }}>
          {/* Run A Selector */}
          <div>
            <label style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>
              Baseline Run (A):
            </label>
            <select
              value={runAId}
              onChange={(e) => setRunAId(e.target.value)}
              style={{
                width: '100%',
                backgroundColor: 'var(--bg-surface-2)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '6px',
                padding: '8px 12px',
                fontSize: '13px',
              }}
            >
              {historyRuns.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.store_name} ({fmtPct(r.overall_score)}) — {new Date(r.timestamp).toLocaleTimeString()}
                </option>
              ))}
            </select>
          </div>

          <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
            <GitCompare size={22} />
          </div>

          {/* Run B Selector */}
          <div>
            <label style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>
              Comparison Run (B):
            </label>
            <select
              value={runBId}
              onChange={(e) => setRunBId(e.target.value)}
              style={{
                width: '100%',
                backgroundColor: 'var(--bg-surface-2)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '6px',
                padding: '8px 12px',
                fontSize: '13px',
              }}
            >
              {historyRuns.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.store_name} ({fmtPct(r.overall_score)}) — {new Date(r.timestamp).toLocaleTimeString()}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Comparison Metrics Diff Table */}
        {reportA && reportB && (
          <div style={{ marginTop: '20px' }}>
            <div className="ws-table-container">
              <table className="ws-table">
                <thead>
                  <tr>
                    <th>Dimension</th>
                    <th>Run A ({reportA.store_name})</th>
                    <th>Run B ({reportB.store_name})</th>
                    <th>Delta (B - A)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Macro Overall Reliability</strong></td>
                    <td>{fmtPct(reportA.aggregate_metrics.overall_score)}</td>
                    <td>{fmtPct(reportB.aggregate_metrics.overall_score)}</td>
                    <td>{renderDelta(reportA.aggregate_metrics.overall_score, reportB.aggregate_metrics.overall_score)}</td>
                  </tr>
                  <tr>
                    <td><strong>Micro Query Pass Rate</strong></td>
                    <td>{fmtPct(reportA.aggregate_metrics.micro_pass_rate)}</td>
                    <td>{fmtPct(reportB.aggregate_metrics.micro_pass_rate)}</td>
                    <td>{renderDelta(reportA.aggregate_metrics.micro_pass_rate, reportB.aggregate_metrics.micro_pass_rate)}</td>
                  </tr>
                  <tr>
                    <td>TRAcc (Temporal Recall)</td>
                    <td>{fmtPct(reportA.aggregate_metrics.temporal_recall_accuracy)}</td>
                    <td>{fmtPct(reportB.aggregate_metrics.temporal_recall_accuracy)}</td>
                    <td>{renderDelta(reportA.aggregate_metrics.temporal_recall_accuracy, reportB.aggregate_metrics.temporal_recall_accuracy)}</td>
                  </tr>
                  <tr>
                    <td>SFR (Stale Fact Rate)</td>
                    <td>{fmtPct(reportA.aggregate_metrics.stale_fact_rate)}</td>
                    <td>{fmtPct(reportB.aggregate_metrics.stale_fact_rate)}</td>
                    <td>{renderDelta(reportA.aggregate_metrics.stale_fact_rate, reportB.aggregate_metrics.stale_fact_rate)}</td>
                  </tr>
                  <tr>
                    <td>CHS (Contradictions)</td>
                    <td>{fmtPct(reportA.aggregate_metrics.contradiction_handling_score)}</td>
                    <td>{fmtPct(reportB.aggregate_metrics.contradiction_handling_score)}</td>
                    <td>{renderDelta(reportA.aggregate_metrics.contradiction_handling_score, reportB.aggregate_metrics.contradiction_handling_score)}</td>
                  </tr>
                  <tr>
                    <td>EIA (Entity Isolation)</td>
                    <td>{fmtPct(reportA.aggregate_metrics.entity_isolation_accuracy)}</td>
                    <td>{fmtPct(reportB.aggregate_metrics.entity_isolation_accuracy)}</td>
                    <td>{renderDelta(reportA.aggregate_metrics.entity_isolation_accuracy, reportB.aggregate_metrics.entity_isolation_accuracy)}</td>
                  </tr>
                  <tr>
                    <td>DC (Deletion Compliance)</td>
                    <td>{fmtPct(reportA.aggregate_metrics.deletion_compliance)}</td>
                    <td>{fmtPct(reportB.aggregate_metrics.deletion_compliance)}</td>
                    <td>{renderDelta(reportA.aggregate_metrics.deletion_compliance, reportB.aggregate_metrics.deletion_compliance)}</td>
                  </tr>
                  <tr>
                    <td>Median Latency (p50)</td>
                    <td>{reportA.aggregate_metrics.latency.p50_ms?.toFixed(3) ?? 'N/A'} ms</td>
                    <td>{reportB.aggregate_metrics.latency.p50_ms?.toFixed(3) ?? 'N/A'} ms</td>
                    <td>
                      {reportA.aggregate_metrics.latency.p50_ms !== undefined &&
                      reportB.aggregate_metrics.latency.p50_ms !== undefined ? (
                        <span>
                          {(reportB.aggregate_metrics.latency.p50_ms - reportA.aggregate_metrics.latency.p50_ms).toFixed(3)} ms
                        </span>
                      ) : (
                        'N/A'
                      )}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* History Log Table */}
      <div className="ws-card">
        <div className="ws-card-header">
          <span className="ws-card-title">Run History Log ({historyRuns.length})</span>
        </div>

        <div className="ws-table-container">
          <table className="ws-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Adapter</th>
                <th>Timestamp</th>
                <th>Macro Score</th>
                <th>Micro Rate</th>
                <th>Queries</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {historyRuns.map((r) => (
                <tr key={r.run_id}>
                  <td>
                    <code>{r.run_id.slice(0, 8)}...</code>
                  </td>
                  <td>
                    <span className="badge badge-info">{r.store_name}</span>
                  </td>
                  <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {new Date(r.timestamp).toLocaleString()}
                  </td>
                  <td>
                    <strong style={{ color: r.overall_score === 1.0 ? 'var(--status-pass-text)' : 'inherit' }}>
                      {fmtPct(r.overall_score)}
                    </strong>
                  </td>
                  <td>{fmtPct(r.micro_pass_rate)}</td>
                  <td>
                    {r.passed_queries} / {r.total_queries}
                  </td>
                  <td>
                    <button
                      className="btn-secondary"
                      style={{ fontSize: '11px', padding: '3px 8px' }}
                      onClick={() => fetchRunReport(r.run_id).then(onSelectRunAsActive)}
                    >
                      Inspect in Overview
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
