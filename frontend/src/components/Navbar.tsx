import type { FC } from 'react';
import {
  AlertTriangle,
  BarChart2,
  BookOpen,
  Download,
  GitCompare,
  Play,
} from 'lucide-react';
import type { HealthResponse } from '../types';

export type ActiveTab =
  | 'overview'
  | 'run'
  | 'failures'
  | 'scenarios'
  | 'history'
  | 'export';

interface NavbarProps {
  currentTab: ActiveTab;
  onSelectTab: (tab: ActiveTab) => void;
  health: HealthResponse | null;
  isRunning: boolean;
  activeAdapterName?: string;
}

export const Navbar: FC<NavbarProps> = ({
  currentTab,
  onSelectTab,
  health,
  isRunning,
  activeAdapterName,
}) => {
  return (
    <header className="workstation-nav">
      <div className="nav-brand">
        <span className="brand-badge">LAB</span>
        <div>
          <span className="brand-title">RecallBench</span>
          <span className="brand-subtitle">Agent Memory Reliability</span>
        </div>
      </div>

      <nav className="nav-tabs">
        <button
          className={`nav-tab-btn ${currentTab === 'overview' ? 'active' : ''}`}
          onClick={() => onSelectTab('overview')}
        >
          <BarChart2 size={15} />
          Overview
        </button>
        <button
          className={`nav-tab-btn ${currentTab === 'run' ? 'active' : ''}`}
          onClick={() => onSelectTab('run')}
        >
          <Play size={15} />
          Run Benchmark
        </button>
        <button
          className={`nav-tab-btn ${currentTab === 'failures' ? 'active' : ''}`}
          onClick={() => onSelectTab('failures')}
        >
          <AlertTriangle size={15} />
          Failure Explorer
        </button>
        <button
          className={`nav-tab-btn ${currentTab === 'scenarios' ? 'active' : ''}`}
          onClick={() => onSelectTab('scenarios')}
        >
          <BookOpen size={15} />
          Scenario Explorer
        </button>
        <button
          className={`nav-tab-btn ${currentTab === 'history' ? 'active' : ''}`}
          onClick={() => onSelectTab('history')}
        >
          <GitCompare size={15} />
          History & Compare
        </button>
        <button
          className={`nav-tab-btn ${currentTab === 'export' ? 'active' : ''}`}
          onClick={() => onSelectTab('export')}
        >
          <Download size={15} />
          Export
        </button>
      </nav>

      <div className="nav-status">
        {activeAdapterName && (
          <span style={{ color: 'var(--text-muted)' }}>
            Store: <strong style={{ color: 'var(--text-primary)' }}>{activeAdapterName}</strong>
          </span>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span
            className={`status-dot ${isRunning ? 'busy' : health ? 'online' : ''}`}
          />
          <span>{isRunning ? 'Run in progress' : health ? 'Ready' : 'Offline'}</span>
        </div>
      </div>
    </header>
  );
};
