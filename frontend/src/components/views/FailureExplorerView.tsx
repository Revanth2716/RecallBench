import { useState, type FC } from 'react';
import {
  CheckCircle2,
  Filter,
  Search,
  XCircle,
} from 'lucide-react';
import type { BenchmarkRunReport, EvaluationResult } from '../../types';

interface FailureExplorerViewProps {
  activeRun: BenchmarkRunReport | null;
}

export const FailureExplorerView: FC<FailureExplorerViewProps> = ({ activeRun }) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');

  if (!activeRun) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary)' }}>
        <p>No benchmark run available. Execute a run to inspect evaluations and failure diagnostics.</p>
      </div>
    );
  }

  // Collect all query evaluations
  const allEvaluations: EvaluationResult[] = [];
  for (const sr of activeRun.scenario_results) {
    allEvaluations.push(...sr.evaluations);
  }

  // Filter evaluations
  const filtered = allEvaluations.filter((ev) => {
    if (selectedCategory !== 'ALL' && ev.category !== selectedCategory) return false;

    if (selectedStatusFilter === 'FAILURES' && ev.passed) return false;
    if (selectedStatusFilter === 'PASSES' && !ev.passed) return false;
    if (selectedStatusFilter === 'STALE_LEAKS' && !ev.is_stale_leak) return false;
    if (selectedStatusFilter === 'CROSSOVER_LEAKS' && !ev.is_entity_crossover) return false;
    if (selectedStatusFilter === 'TOMBSTONE_LEAKS' && !ev.is_tombstone_leak) return false;

    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const matchQuery = ev.query_id.toLowerCase().includes(term);
      const matchScenario = ev.scenario_id.toLowerCase().includes(term);
      const matchErr = (ev.error_message || '').toLowerCase().includes(term);
      if (!matchQuery && !matchScenario && !matchErr) return false;
    }

    return true;
  });

  const failureCount = allEvaluations.filter((ev) => !ev.passed).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header and Summary Status */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 600 }}>Failure Explorer & Query Inspector</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Detailed assertion results across every individual query in the benchmark suite.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <span className={`badge ${failureCount === 0 ? 'badge-pass' : 'badge-fail'}`}>
            {failureCount === 0 ? 'Zero Failure State' : `${failureCount} Failed Queries`}
          </span>
          <span className="badge badge-info">{allEvaluations.length} Total Queries</span>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div
        className="ws-card"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '12px',
          alignItems: 'center',
          padding: '14px 16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Filter size={15} color="var(--text-muted)" />
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>Filters:</span>
        </div>

        {/* Category filter */}
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          style={{
            backgroundColor: 'var(--bg-surface-2)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '6px',
            padding: '6px 10px',
            fontSize: '12px',
          }}
        >
          <option value="ALL">All Categories</option>
          <option value="TEMPORAL_RECALL">Temporal Recall</option>
          <option value="STALE_FACT_DETECTION">Stale-Fact Detection</option>
          <option value="CONTRADICTION_HANDLING">Contradiction Handling</option>
          <option value="ENTITY_ISOLATION">Entity Isolation</option>
          <option value="DELETION_COMPLIANCE">Deletion Compliance</option>
        </select>

        {/* Status / Leak filter */}
        <select
          value={selectedStatusFilter}
          onChange={(e) => setSelectedStatusFilter(e.target.value)}
          style={{
            backgroundColor: 'var(--bg-surface-2)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '6px',
            padding: '6px 10px',
            fontSize: '12px',
          }}
        >
          <option value="ALL">All Statuses ({allEvaluations.length})</option>
          <option value="FAILURES">Only Failures ({failureCount})</option>
          <option value="PASSES">Only Passed ({allEvaluations.length - failureCount})</option>
          <option value="STALE_LEAKS">Stale Fact Leaks</option>
          <option value="CROSSOVER_LEAKS">Entity Crossovers</option>
          <option value="TOMBSTONE_LEAKS">Tombstone Payload Leaks</option>
        </select>

        {/* Search input */}
        <div style={{ position: 'relative', flex: 1, minWidth: '200px' }}>
          <Search
            size={14}
            color="var(--text-muted)"
            style={{ position: 'absolute', left: '10px', top: '9px' }}
          />
          <input
            type="text"
            placeholder="Search by query ID, scenario ID, or reason..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              backgroundColor: 'var(--bg-surface-2)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '6px',
              padding: '6px 10px 6px 30px',
              fontSize: '12px',
            }}
          />
        </div>
      </div>

      {/* Query Evaluations Table */}
      <div className="ws-table-container">
        <table className="ws-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Query ID</th>
              <th>Scenario</th>
              <th>Category</th>
              <th>Expected</th>
              <th>Actual</th>
              <th>Adversarial Checks</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                  No queries match the active filter criteria.
                </td>
              </tr>
            ) : (
              filtered.map((ev) => (
                <tr key={`${ev.scenario_id}-${ev.query_id}`}>
                  <td>
                    {ev.passed ? (
                      <span className="badge badge-pass">
                        <CheckCircle2 size={12} /> PASS
                      </span>
                    ) : (
                      <span className="badge badge-fail">
                        <XCircle size={12} /> FAIL
                      </span>
                    )}
                  </td>
                  <td>
                    <code>{ev.query_id}</code>
                  </td>
                  <td>
                    <code style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      {ev.scenario_id}
                    </code>
                  </td>
                  <td>
                    <span className="badge badge-info">{ev.category}</span>
                  </td>
                  <td>
                    <div style={{ fontSize: '12px' }}>
                      <span style={{ color: 'var(--text-muted)' }}>status:</span>{' '}
                      <strong>{ev.expected_status}</strong>
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      val: <code>{JSON.stringify(ev.expected_value)}</code>
                    </div>
                  </td>
                  <td>
                    <div style={{ fontSize: '12px' }}>
                      <span style={{ color: 'var(--text-muted)' }}>status:</span>{' '}
                      <strong>{ev.actual_status}</strong>
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                      val: <code>{JSON.stringify(ev.actual_value)}</code>
                    </div>
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                      {ev.is_stale_leak && <span className="badge badge-fail">STALE LEAK</span>}
                      {ev.is_entity_crossover && <span className="badge badge-fail">CROSSOVER</span>}
                      {ev.is_tombstone_leak && <span className="badge badge-fail">TOMBSTONE LEAK</span>}
                      {!ev.is_stale_leak && !ev.is_entity_crossover && !ev.is_tombstone_leak && (
                        <span style={{ fontSize: '11px', color: 'var(--status-pass-text)' }}>
                          ✓ Clean Invariants
                        </span>
                      )}
                      {ev.error_message && (
                        <span style={{ fontSize: '10px', color: 'var(--status-fail-text)' }}>
                          {ev.error_message}
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {ev.latency_ms.toFixed(3)} ms
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
