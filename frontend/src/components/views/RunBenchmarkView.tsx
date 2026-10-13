import { useState, type FC } from 'react';
import {
  AlertCircle,
  HardDrive,
  Loader2,
  Play,
  Zap,
} from 'lucide-react';
import type { BenchmarkSummary, BenchmarkRunReport } from '../../types';

interface RunBenchmarkViewProps {
  scenarios: BenchmarkSummary[];
  isRunning: boolean;
  onExecuteRun: (adapter: 'sqlite' | 'in_memory', selectedIds?: string[]) => Promise<void>;
  lastRunReport: BenchmarkRunReport | null;
  error: string | null;
}

export const RunBenchmarkView: FC<RunBenchmarkViewProps> = ({
  scenarios,
  isRunning,
  onExecuteRun,
  lastRunReport,
  error,
}) => {
  const [selectedAdapter, setSelectedAdapter] = useState<'sqlite' | 'in_memory'>('sqlite');
  const [selectedIds, setSelectedIds] = useState<string[]>(scenarios.map((s) => s.scenario_id));

  const toggleScenario = (id: string) => {
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter((item) => item !== id));
    } else {
      setSelectedIds([...selectedIds, id]);
    }
  };

  const selectAll = () => {
    setSelectedIds(scenarios.map((s) => s.scenario_id));
  };

  const deselectAll = () => {
    setSelectedIds([]);
  };

  const handleStart = () => {
    if (selectedIds.length === 0) return;
    onExecuteRun(selectedAdapter, selectedIds);
  };

  // Group scenarios by category
  const grouped: Record<string, BenchmarkSummary[]> = {};
  for (const sc of scenarios) {
    if (!grouped[sc.category]) grouped[sc.category] = [];
    grouped[sc.category].push(sc);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Configuration Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Run Benchmark Laboratory
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Select the target memory store adapter and scenario suite to evaluate.
          </p>
        </div>
        {lastRunReport && (
          <span className="badge badge-info" style={{ fontSize: '12px' }}>
            Last Run: {lastRunReport.store_name} ({lastRunReport.passed_queries}/{lastRunReport.total_queries} passed)
          </span>
        )}
      </div>

      {/* Error alert if any */}
      {error && (
        <div
          style={{
            backgroundColor: 'var(--status-fail-bg)',
            border: '1px solid rgba(248, 81, 73, 0.4)',
            color: 'var(--status-fail-text)',
            padding: '12px 16px',
            borderRadius: '6px',
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* Adapter Selection Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
        {/* SQLite Card */}
        <div
          className="ws-card"
          onClick={() => !isRunning && setSelectedAdapter('sqlite')}
          style={{
            cursor: isRunning ? 'not-allowed' : 'pointer',
            borderColor: selectedAdapter === 'sqlite' ? 'var(--accent-indigo)' : 'var(--border-subtle)',
            backgroundColor: selectedAdapter === 'sqlite' ? 'var(--bg-surface-2)' : 'var(--bg-surface-1)',
            transition: 'all 0.15s ease',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <HardDrive size={18} color="var(--accent-indigo)" />
              <strong style={{ fontSize: '14px' }}>SQLite Temporal Store</strong>
            </div>
            {selectedAdapter === 'sqlite' && <span className="badge badge-info">Selected Target</span>}
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Production-grade disk storage with WAL journaling, transaction isolation, bitemporal
            half-open valid intervals <code>[valid_from, valid_to)</code>, and physical purge capabilities.
          </p>
          <div style={{ marginTop: '10px', fontSize: '11px', color: 'var(--text-muted)' }}>
            Database: <code>backend/data/benchmark_isolated.db</code>
          </div>
        </div>

        {/* In-Memory Card */}
        <div
          className="ws-card"
          onClick={() => !isRunning && setSelectedAdapter('in_memory')}
          style={{
            cursor: isRunning ? 'not-allowed' : 'pointer',
            borderColor: selectedAdapter === 'in_memory' ? 'var(--accent-cyan)' : 'var(--border-subtle)',
            backgroundColor: selectedAdapter === 'in_memory' ? 'var(--bg-surface-2)' : 'var(--bg-surface-1)',
            transition: 'all 0.15s ease',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={18} color="var(--accent-cyan)" />
              <strong style={{ fontSize: '14px' }}>In-Memory Store (Baseline)</strong>
            </div>
            {selectedAdapter === 'in_memory' && <span className="badge badge-info">Selected Target</span>}
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Pure Python domain baseline without disk I/O. Used to compare memory indexing
            overhead and verify zero-deviation behavioral equivalence across storage tiers.
          </p>
          <div style={{ marginTop: '10px', fontSize: '11px', color: 'var(--text-muted)' }}>
            Volatile RAM fact records (zero disk dependency)
          </div>
        </div>
      </div>

      {/* Scenario Suite Checklist */}
      <div className="ws-card">
        <div className="ws-card-header">
          <div>
            <span className="ws-card-title">Scenario Catalog Suite</span>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: '8px' }}>
              ({selectedIds.length} of {scenarios.length} selected)
            </span>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn-secondary" onClick={selectAll} disabled={isRunning} style={{ fontSize: '11px', padding: '4px 10px' }}>
              Select All
            </button>
            <button className="btn-secondary" onClick={deselectAll} disabled={isRunning} style={{ fontSize: '11px', padding: '4px 10px' }}>
              Deselect All
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {Object.entries(grouped).map(([category, items]) => (
            <div key={category} style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--accent-indigo)', marginBottom: '8px', textTransform: 'uppercase' }}>
                {category} ({items.length})
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '8px' }}>
                {items.map((sc) => {
                  const isChecked = selectedIds.includes(sc.scenario_id);
                  return (
                    <div
                      key={sc.scenario_id}
                      onClick={() => !isRunning && toggleScenario(sc.scenario_id)}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '8px',
                        padding: '8px 10px',
                        borderRadius: '4px',
                        backgroundColor: isChecked ? 'rgba(99, 102, 241, 0.06)' : 'transparent',
                        border: '1px solid',
                        borderColor: isChecked ? 'rgba(99, 102, 241, 0.3)' : 'var(--border-subtle)',
                        cursor: isRunning ? 'not-allowed' : 'pointer',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}}
                        disabled={isRunning}
                        style={{ marginTop: '3px', cursor: 'pointer' }}
                      />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '12px', fontWeight: 600 }}>
                          <code>{sc.scenario_id}</code>
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          {sc.description}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '20px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Target: <strong>{selectedAdapter.toUpperCase()}</strong> | Scenarios: <strong>{selectedIds.length}</strong>
          </div>
          <button
            className="btn-primary"
            onClick={handleStart}
            disabled={isRunning || selectedIds.length === 0}
            style={{ padding: '10px 24px', fontSize: '14px' }}
          >
            {isRunning ? (
              <>
                <Loader2 size={16} className="spin" style={{ animation: 'spin 1s linear infinite' }} />
                Running Benchmark Laboratory...
              </>
            ) : (
              <>
                <Play size={16} />
                Execute Benchmark Run
              </>
            )}
          </button>
        </div>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};
