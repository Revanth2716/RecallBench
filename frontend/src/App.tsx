import { useEffect, useState } from 'react';
import { Navbar, type ActiveTab } from './components/Navbar';
import { OverviewView } from './components/views/OverviewView';
import { RunBenchmarkView } from './components/views/RunBenchmarkView';
import { FailureExplorerView } from './components/views/FailureExplorerView';
import { ScenarioExplorerView } from './components/views/ScenarioExplorerView';
import { HistoryComparisonView } from './components/views/HistoryComparisonView';
import { ExportView } from './components/views/ExportView';
import {
  fetchBenchmarks,
  fetchHealth,
  fetchRunReport,
  fetchRunsHistory,
  triggerBenchmarkRun,
} from './services/api';
import type {
  BenchmarkRunReport,
  BenchmarkSummary,
  HealthResponse,
  RunSummaryResponse,
} from './types';

export function App() {
  const [currentTab, setCurrentTab] = useState<ActiveTab>('overview');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [catalogScenarios, setCatalogScenarios] = useState<BenchmarkSummary[]>([]);
  const [historyRuns, setHistoryRuns] = useState<RunSummaryResponse[]>([]);
  const [activeRun, setActiveRun] = useState<BenchmarkRunReport | null>(null);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Load initial laboratory metadata & historical runs on mount
  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch((err) => console.error('Failed to connect to RecallBench API:', err));

    fetchBenchmarks()
      .then((res) => setCatalogScenarios(res.scenarios))
      .catch((err) => console.error('Failed to load benchmarks:', err));

    fetchRunsHistory()
      .then((runs) => {
        setHistoryRuns(runs);
        if (runs.length > 0) {
          fetchRunReport(runs[0].run_id)
            .then(setActiveRun)
            .catch(() => {});
        }
      })
      .catch((err) => console.error('Failed to load runs history:', err));
  }, []);

  const handleExecuteRun = async (
    adapter: 'sqlite' | 'in_memory',
    selectedIds?: string[]
  ) => {
    setIsRunning(true);
    setError(null);
    try {
      const report = await triggerBenchmarkRun(adapter, selectedIds);
      setActiveRun(report);
      // Refresh runs list
      const updatedRuns = await fetchRunsHistory();
      setHistoryRuns(updatedRuns);
      // Navigate to overview to view results
      setCurrentTab('overview');
    } catch (err: any) {
      setError(err.message || 'Benchmark run failed');
    } finally {
      setIsRunning(false);
    }
  };

  const handleSelectRunAsActive = (report: BenchmarkRunReport) => {
    setActiveRun(report);
    setCurrentTab('overview');
  };

  return (
    <div className="app-container">
      <Navbar
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        health={health}
        isRunning={isRunning}
        activeAdapterName={activeRun?.store_name}
      />

      <main className="main-content">
        {currentTab === 'overview' && (
          <OverviewView
            activeRun={activeRun}
            onNavigateToRun={() => setCurrentTab('run')}
            onNavigateToFailures={() => setCurrentTab('failures')}
          />
        )}

        {currentTab === 'run' && (
          <RunBenchmarkView
            scenarios={catalogScenarios}
            isRunning={isRunning}
            onExecuteRun={handleExecuteRun}
            lastRunReport={activeRun}
            error={error}
          />
        )}

        {currentTab === 'failures' && (
          <FailureExplorerView activeRun={activeRun} />
        )}

        {currentTab === 'scenarios' && (
          <ScenarioExplorerView scenarios={catalogScenarios} />
        )}

        {currentTab === 'history' && (
          <HistoryComparisonView
            historyRuns={historyRuns}
            onSelectRunAsActive={handleSelectRunAsActive}
          />
        )}

        {currentTab === 'export' && (
          <ExportView activeRun={activeRun} historyRuns={historyRuns} />
        )}
      </main>
    </div>
  );
}

export default App;
