import type { FC } from 'react';
import {
  Info,
  Layers,
  Play,
} from 'lucide-react';
import type { BenchmarkRunReport } from '../../types';

interface OverviewViewProps {
  activeRun: BenchmarkRunReport | null;
  onNavigateToRun: () => void;
  onNavigateToFailures: () => void;
}

export const OverviewView: FC<OverviewViewProps> = ({
  activeRun,
  onNavigateToRun,
  onNavigateToFailures,
}) => {
  if (!activeRun) {
    return (
      <div style={{ textAlign: 'center', padding: '80px 20px' }}>
        <div
          style={{
            display: 'inline-flex',
            padding: '16px',
            borderRadius: '50%',
            backgroundColor: 'var(--bg-surface-2)',
            marginBottom: '16px',
          }}
        >
          <Layers size={36} color="var(--accent-indigo)" />
        </div>
        <h2 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '8px' }}>
          No Active Benchmark Report
        </h2>
        <p
          style={{
            color: 'var(--text-secondary)',
            fontSize: '14px',
            maxWidth: '520px',
            margin: '0 auto 24px',
          }}
        >
          Execute the benchmark harness against either the SQLite bitemporal store
          or the in-memory baseline store to observe memory reliability scores.
        </p>
        <button className="btn-primary" onClick={onNavigateToRun}>
          <Play size={16} />
          Start Evaluation Run
        </button>
      </div>
    );
  }

  const m = activeRun.aggregate_metrics;
  const lat = m.latency;

  const fmtPct = (val?: number) => {
    if (val === undefined || val === null) return 'N/A';
    return `${(val * 100).toFixed(1)}%`;
  };

  const macroScore = m.overall_score !== undefined ? m.overall_score : null;
  const microRate = m.micro_pass_rate !== undefined ? m.micro_pass_rate : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Banner / Disclaimer */}
      <div className="disclaimer-banner">
        <Info size={18} style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <strong>Evaluation Laboratory Benchmark Suite (v1.0.0):</strong> RecallBench measures
          memory persistence and bitemporal retrieval determinism under strict half-open interval
          semantics <code>[valid_from, valid_to)</code>, deterministic tie-breaking, and deletion
          masking. Scores reflect conformance to the current synthetic scenario suite, not general
          natural-language reasoning.
        </div>
      </div>

      {/* Hero Metrics Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
        {/* Macro Score Card */}
        <div className="ws-card" style={{ borderTop: '3px solid var(--accent-indigo)' }}>
          <div className="ws-card-header">
            <span className="ws-card-title">Macro Reliability Score</span>
            <span className="badge badge-info">Category Average</span>
          </div>
          <div className="score-hero">
            <span className="score-hero-val">{fmtPct(macroScore ?? undefined)}</span>
            <span className="score-hero-lbl">reliability</span>
          </div>
          <div className="meter-bar">
            <div
              className={`meter-fill ${macroScore === 1.0 ? 'pass' : 'fail'}`}
              style={{ width: `${(macroScore ?? 0) * 100}%` }}
            />
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
            Unweighted mean across the 5 reliability dimensions, unskewed by query volume.
          </p>
        </div>

        {/* Micro Pass Rate Card */}
        <div className="ws-card" style={{ borderTop: '3px solid var(--accent-cyan)' }}>
          <div className="ws-card-header">
            <span className="ws-card-title">Micro Query Pass Rate</span>
            <span className="badge badge-info">Query Level</span>
          </div>
          <div className="score-hero">
            <span className="score-hero-val">{fmtPct(microRate ?? undefined)}</span>
            <span className="score-hero-lbl">
              ({activeRun.passed_queries}/{activeRun.total_queries} queries)
            </span>
          </div>
          <div className="meter-bar">
            <div
              className={`meter-fill ${microRate === 1.0 ? 'pass' : 'fail'}`}
              style={{ width: `${(microRate ?? 0) * 100}%` }}
            />
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
            Fraction of total point-in-time and historical queries passing assertions.
          </p>
        </div>

        {/* Store & Execution Metadata Card */}
        <div className="ws-card">
          <div className="ws-card-header">
            <span className="ws-card-title">Run Target</span>
            <span className="badge badge-pass">{activeRun.store_name}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Scenarios Evaluated:</span>
              <strong>{activeRun.scenarios_evaluated} of 12</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Passed / Failed:</span>
              <span>
                <strong style={{ color: 'var(--status-pass-text)' }}>
                  {activeRun.passed_queries} passed
                </strong>{' '}
                /{' '}
                <strong
                  style={{
                    color:
                      activeRun.failed_queries > 0
                        ? 'var(--status-fail-text)'
                        : 'var(--text-muted)',
                  }}
                >
                  {activeRun.failed_queries} failed
                </strong>
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Median Latency (p50):</span>
              <strong>{lat.p50_ms !== undefined ? `${lat.p50_ms.toFixed(3)} ms` : 'N/A'}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Run ID:</span>
              <code style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                {activeRun.run_id.slice(0, 8)}...
              </code>
            </div>
          </div>
        </div>
      </div>

      {/* 5 Category Reliability Dimensions */}
      <div>
        <h3
          style={{
            fontSize: '15px',
            fontWeight: 600,
            color: 'var(--text-secondary)',
            marginBottom: '12px',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}
        >
          Category Reliability Dimensions
        </h3>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
            gap: '14px',
          }}
        >
          {/* 1. TRAcc */}
          <div className="ws-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                TRAcc — Temporal Recall
              </strong>
              <span className={`badge ${m.temporal_recall_accuracy === 1.0 ? 'badge-pass' : 'badge-fail'}`}>
                {fmtPct(m.temporal_recall_accuracy)}
              </span>
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Retrieves valid historical facts at arbitrary valid-time coordinates.
            </p>
            <div className="meter-bar">
              <div
                className="meter-fill pass"
                style={{ width: `${(m.temporal_recall_accuracy ?? 0) * 100}%` }}
              />
            </div>
          </div>

          {/* 2. SFR & SFAcc */}
          <div className="ws-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                SFR — Stale Fact Leak
              </strong>
              <span className={`badge ${m.stale_fact_rate === 0.0 ? 'badge-pass' : 'badge-fail'}`}>
                {fmtPct(m.stale_fact_rate)} leak
              </span>
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Accuracy: <strong>{fmtPct(m.stale_fact_accuracy)}</strong>. Penalizes returning superseded data as active.
            </p>
            <div className="meter-bar">
              <div
                className="meter-fill pass"
                style={{ width: `${(m.stale_fact_accuracy ?? 0) * 100}%` }}
              />
            </div>
          </div>

          {/* 3. CHS */}
          <div className="ws-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                CHS — Contradictions
              </strong>
              <span className={`badge ${m.contradiction_handling_score === 1.0 ? 'badge-pass' : 'badge-fail'}`}>
                {fmtPct(m.contradiction_handling_score)}
              </span>
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Resolves or abstains across all 4 policies: Abstain, LWW, Conf-Weighted, Multi-Val.
            </p>
            <div className="meter-bar">
              <div
                className="meter-fill pass"
                style={{ width: `${(m.contradiction_handling_score ?? 0) * 100}%` }}
              />
            </div>
          </div>

          {/* 4. EIA */}
          <div className="ws-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                EIA — Entity Isolation
              </strong>
              <span className={`badge ${m.entity_isolation_accuracy === 1.0 ? 'badge-pass' : 'badge-fail'}`}>
                {fmtPct(m.entity_isolation_accuracy)}
              </span>
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Zero cross-tenant provenance leakage, even under homonymous attribute values.
            </p>
            <div className="meter-bar">
              <div
                className="meter-fill pass"
                style={{ width: `${(m.entity_isolation_accuracy ?? 0) * 100}%` }}
              />
            </div>
          </div>

          {/* 5. DC */}
          <div className="ws-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                DC — Deletion Compliance
              </strong>
              <span className={`badge ${m.deletion_compliance === 1.0 ? 'badge-pass' : 'badge-fail'}`}>
                {fmtPct(m.deletion_compliance)}
              </span>
            </div>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Normal retrieval strictly masks payload on tombstones and purged records.
            </p>
            <div className="meter-bar">
              <div
                className="meter-fill pass"
                style={{ width: `${(m.deletion_compliance ?? 0) * 100}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Latency Distribution Breakdown */}
      <div className="ws-card">
        <div className="ws-card-header">
          <span className="ws-card-title">Observational Latency Distribution (ms)</span>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            N = {lat.count} queries measured
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', textAlign: 'center' }}>
          <div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Mean</div>
            <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '4px' }}>
              {lat.mean_ms !== undefined ? `${lat.mean_ms.toFixed(3)} ms` : 'N/A'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>p50 (Median)</div>
            <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '4px' }}>
              {lat.p50_ms !== undefined ? `${lat.p50_ms.toFixed(3)} ms` : 'N/A'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>p95</div>
            <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '4px' }}>
              {lat.p95_ms !== undefined ? `${lat.p95_ms.toFixed(3)} ms` : 'N/A'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>p99</div>
            <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '4px' }}>
              {lat.p99_ms !== undefined ? `${lat.p99_ms.toFixed(3)} ms` : 'N/A'}
            </div>
          </div>
        </div>
      </div>

      {/* Scenario Breakdown Table */}
      <div className="ws-card">
        <div className="ws-card-header">
          <span className="ws-card-title">Scenario Execution Breakdown</span>
          <button className="btn-secondary" onClick={onNavigateToFailures}>
            Inspect Query Evaluations
          </button>
        </div>

        <div className="ws-table-container">
          <table className="ws-table">
            <thead>
              <tr>
                <th>Scenario ID</th>
                <th>Category</th>
                <th>Passed / Total</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {activeRun.scenario_results.map((sr) => (
                <tr key={sr.scenario_id}>
                  <td>
                    <code>{sr.scenario_id}</code>
                  </td>
                  <td>
                    <span className="badge badge-info">{sr.category}</span>
                  </td>
                  <td>
                    {sr.passed_count} / {sr.total_count}
                  </td>
                  <td>
                    <span className={`badge ${sr.all_passed ? 'badge-pass' : 'badge-fail'}`}>
                      {sr.all_passed ? 'PASS' : 'FAIL'}
                    </span>
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
