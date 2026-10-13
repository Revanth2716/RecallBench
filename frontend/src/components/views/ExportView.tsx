import { useEffect, useState, type FC } from 'react';
import {
  Check,
  Copy,
  FileJson,
  FileText,
} from 'lucide-react';
import { getExportDownloadUrl } from '../../services/api';
import type { BenchmarkRunReport, RunSummaryResponse } from '../../types';

interface ExportViewProps {
  activeRun: BenchmarkRunReport | null;
  historyRuns: RunSummaryResponse[];
}

export const ExportView: FC<ExportViewProps> = ({ activeRun, historyRuns }) => {
  const [selectedRunId, setSelectedRunId] = useState<string>(
    activeRun?.run_id || historyRuns[0]?.run_id || ''
  );
  const [previewContent, setPreviewContent] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    if (!selectedRunId) return;

    setLoading(true);
    fetch(`/api/runs/${encodeURIComponent(selectedRunId)}/export?format=markdown`)
      .then((res) => (res.ok ? res.text() : Promise.reject(new Error(res.statusText))))
      .then((text) => {
        setPreviewContent(text);
        setLoading(false);
      })
      .catch((err) => {
        setPreviewContent(`Failed to load report preview: ${err.message}`);
        setLoading(false);
      });
  }, [selectedRunId]);

  const handleCopy = () => {
    if (!previewContent) return;
    navigator.clipboard.writeText(previewContent).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (historyRuns.length === 0 && !activeRun) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary)' }}>
        <p>No runs available to export. Complete a benchmark run first.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <h2 style={{ fontSize: '18px', fontWeight: 600 }}>Export Benchmark Reports</h2>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          Download standalone laboratory reports in standardized JSON or GitHub-flavored Markdown.
        </p>
      </div>

      {/* Export Toolbar */}
      <div
        className="ws-card"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <label style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Select Run:</label>
          <select
            value={selectedRunId}
            onChange={(e) => setSelectedRunId(e.target.value)}
            style={{
              backgroundColor: 'var(--bg-surface-2)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '6px',
              padding: '6px 12px',
              fontSize: '13px',
              minWidth: '280px',
            }}
          >
            {historyRuns.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.store_name} ({r.run_id.slice(0, 8)}...) — {new Date(r.timestamp).toLocaleTimeString()}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          {/* Download JSON */}
          <a
            href={getExportDownloadUrl(selectedRunId, 'json')}
            download
            className="btn-secondary"
            style={{ textDecoration: 'none' }}
          >
            <FileJson size={16} />
            Download JSON
          </a>

          {/* Download Markdown */}
          <a
            href={getExportDownloadUrl(selectedRunId, 'markdown')}
            download
            className="btn-primary"
            style={{ textDecoration: 'none' }}
          >
            <FileText size={16} />
            Download Markdown (.md)
          </a>

          {/* Copy Markdown */}
          <button className="btn-secondary" onClick={handleCopy}>
            {copied ? <Check size={16} color="var(--status-pass-text)" /> : <Copy size={16} />}
            {copied ? 'Copied!' : 'Copy to Clipboard'}
          </button>
        </div>
      </div>

      {/* Preview Box */}
      <div className="ws-card">
        <div className="ws-card-header">
          <span className="ws-card-title">Markdown Report Preview</span>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Rendered from <code>/api/runs/{selectedRunId.slice(0, 8)}.../export?format=markdown</code>
          </span>
        </div>

        <pre
          style={{
            backgroundColor: 'var(--bg-surface-2)',
            padding: '16px',
            borderRadius: '6px',
            fontSize: '12px',
            color: 'var(--text-primary)',
            maxHeight: '500px',
            overflowY: 'auto',
            border: '1px solid var(--border-subtle)',
            lineHeight: 1.6,
          }}
        >
          {loading ? 'Loading report preview...' : previewContent}
        </pre>
      </div>
    </div>
  );
};
