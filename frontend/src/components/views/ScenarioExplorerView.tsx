import { useEffect, useState, type FC } from 'react';
import {
  Lock,
  ShieldCheck,
} from 'lucide-react';
import { fetchScenarioDetail } from '../../services/api';
import type { BenchmarkSummary, ScenarioDetailResponse } from '../../types';

interface ScenarioExplorerViewProps {
  scenarios: BenchmarkSummary[];
}

export const ScenarioExplorerView: FC<ScenarioExplorerViewProps> = ({ scenarios }) => {
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>(
    scenarios[0]?.scenario_id || ''
  );
  const [detail, setDetail] = useState<ScenarioDetailResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedScenarioId) return;

    let isMounted = true;
    setLoading(true);
    setError(null);

    fetchScenarioDetail(selectedScenarioId)
      .then((res) => {
        if (isMounted) {
          setDetail(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [selectedScenarioId]);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '20px' }}>
      {/* Sidebar: Scenario Catalog List */}
      <div className="ws-card" style={{ height: 'calc(100vh - 140px)', overflowY: 'auto' }}>
        <div className="ws-card-header" style={{ marginBottom: '12px' }}>
          <span className="ws-card-title">Catalog Scenarios ({scenarios.length})</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {scenarios.map((sc) => {
            const isSelected = sc.scenario_id === selectedScenarioId;
            return (
              <div
                key={sc.scenario_id}
                onClick={() => setSelectedScenarioId(sc.scenario_id)}
                style={{
                  padding: '10px 12px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  backgroundColor: isSelected ? 'var(--bg-surface-3)' : 'transparent',
                  border: '1px solid',
                  borderColor: isSelected ? 'var(--accent-indigo)' : 'transparent',
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <code style={{ fontSize: '12px', fontWeight: 600 }}>{sc.scenario_id}</code>
                  <span className="badge badge-info" style={{ fontSize: '9px' }}>
                    {sc.queries_count} Qs
                  </span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  {sc.category}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Panel: Scenario Details & Timeline */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {loading && (
          <div className="ws-card" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-secondary)' }}>
            Loading scenario manifest...
          </div>
        )}

        {error && (
          <div className="ws-card" style={{ borderColor: 'var(--status-fail-text)', color: 'var(--status-fail-text)' }}>
            Failed to load scenario: {error}
          </div>
        )}

        {detail && !loading && (
          <>
            {/* Scenario Header */}
            <div className="ws-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <h2 style={{ fontSize: '18px', fontWeight: 700 }}>
                    <code>{detail.scenario_id}</code>
                  </h2>
                  <span className="badge badge-info">{detail.category}</span>
                  <span className="badge badge-pass">v{detail.version}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>
                  <Lock size={13} />
                  <span>Immutable Static Manifest</span>
                </div>
              </div>

              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {detail.description}
              </p>

              <div
                style={{
                  display: 'flex',
                  gap: '24px',
                  marginTop: '16px',
                  paddingTop: '12px',
                  borderTop: '1px solid var(--border-subtle)',
                  fontSize: '12px',
                }}
              >
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Contradiction Policy:</span>{' '}
                  <strong>{detail.contradiction_policy}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Timeline Events:</span>{' '}
                  <strong>{detail.timeline_events.length}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Queries:</span>{' '}
                  <strong>{detail.queries.length}</strong>
                </div>
              </div>
            </div>

            {/* Timeline Events Sequence */}
            <div className="ws-card">
              <div className="ws-card-header">
                <span className="ws-card-title">Timeline Events Sequence</span>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  Ingested sequentially into memory store under bitemporal transaction coordinates
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {detail.timeline_events.map((ev, idx) => (
                  <div
                    key={ev.event_id}
                    style={{
                      display: 'flex',
                      gap: '14px',
                      padding: '12px',
                      backgroundColor: 'var(--bg-surface-2)',
                      borderRadius: '6px',
                      borderLeft: `4px solid ${
                        ev.event_type === 'INSERT'
                          ? 'var(--accent-indigo)'
                          : ev.event_type === 'UPDATE'
                          ? 'var(--accent-cyan)'
                          : 'var(--status-fail-text)'
                      }`,
                    }}
                  >
                    <div style={{ minWidth: '80px', fontSize: '11px', fontWeight: 700, color: 'var(--text-primary)' }}>
                      #{idx + 1} {ev.event_type}
                    </div>

                    <div style={{ flex: 1, fontSize: '12px' }}>
                      <div style={{ display: 'flex', gap: '16px', marginBottom: '4px' }}>
                        <span>
                          ID: <code>{ev.event_id}</code>
                        </span>
                        <span>
                          Entity: <strong>{ev.entity_id}</strong>
                        </span>
                        {ev.attribute && (
                          <span>
                            Attr: <code>{ev.attribute}</code>
                          </span>
                        )}
                        {ev.value !== undefined && (
                          <span>
                            Value: <code>{JSON.stringify(ev.value)}</code>
                          </span>
                        )}
                      </div>

                      <div style={{ display: 'flex', gap: '20px', fontSize: '11px', color: 'var(--text-muted)' }}>
                        <span>Asserted at (Tx): {ev.timestamp}</span>
                        {ev.valid_from && <span>Valid from: {ev.valid_from}</span>}
                        {ev.valid_to && <span>Valid to: {ev.valid_to}</span>}
                        {ev.confidence !== undefined && <span>Confidence: {ev.confidence}</span>}
                        {ev.policy && <span>Policy: {ev.policy}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Queries & Ground Truth */}
            <div className="ws-card">
              <div className="ws-card-header">
                <span className="ws-card-title">Queries & Static Ground Truth</span>
                <span className="badge badge-pass">
                  <ShieldCheck size={12} /> Independently Authored
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {detail.queries.map((q) => {
                  const gt = q.ground_truth;
                  return (
                    <div
                      key={q.query_id}
                      style={{
                        padding: '14px',
                        backgroundColor: 'var(--bg-surface-2)',
                        borderRadius: '6px',
                        border: '1px solid var(--border-subtle)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <div>
                          Query ID: <code>{q.query_id}</code> | Entity: <strong>{q.query.entity_id}</strong> | Attr:{' '}
                          <code>{q.query.attribute}</code>
                        </div>
                        <span className="badge badge-info">
                          Expected Status: {gt.expected_status}
                        </span>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px', fontSize: '12px' }}>
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>Query Valid Time:</span>{' '}
                          <code>{q.query.as_of_valid_time || 'Latest'}</code>
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>Expected Value:</span>{' '}
                          <code>{JSON.stringify(gt.expected_value)}</code>
                        </div>
                        {gt.forbidden_values && gt.forbidden_values.length > 0 && (
                          <div>
                            <span style={{ color: 'var(--status-fail-text)' }}>Forbidden Leaks:</span>{' '}
                            <code>{JSON.stringify(gt.forbidden_values)}</code>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
