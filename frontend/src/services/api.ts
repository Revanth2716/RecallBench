import type {
  BenchmarkRunReport,
  BenchmarksListResponse,
  HealthResponse,
  RunSummaryResponse,
  ScenarioDetailResponse,
} from '../types';

const API_BASE = '';

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function fetchBenchmarks(): Promise<BenchmarksListResponse> {
  const res = await fetch(`${API_BASE}/api/benchmarks`);
  if (!res.ok) throw new Error(`Failed to load benchmarks catalog: ${res.statusText}`);
  return res.json();
}

export async function fetchScenarioDetail(scenarioId: string): Promise<ScenarioDetailResponse> {
  const res = await fetch(`${API_BASE}/api/benchmarks/${encodeURIComponent(scenarioId)}`);
  if (!res.ok) throw new Error(`Failed to load scenario '${scenarioId}': ${res.statusText}`);
  return res.json();
}

export async function triggerBenchmarkRun(
  adapter: 'sqlite' | 'in_memory' = 'sqlite',
  scenarioIds?: string[]
): Promise<BenchmarkRunReport> {
  const body: any = { adapter };
  if (scenarioIds && scenarioIds.length > 0) {
    body.scenario_ids = scenarioIds;
  }

  const res = await fetch(`${API_BASE}/api/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (res.status === 409) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'A benchmark run is already in progress.');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Benchmark run failed: ${res.statusText}`);
  }

  return res.json();
}

export async function fetchRunsHistory(): Promise<RunSummaryResponse[]> {
  const res = await fetch(`${API_BASE}/api/runs`);
  if (!res.ok) throw new Error(`Failed to load runs history: ${res.statusText}`);
  return res.json();
}

export async function fetchRunReport(runId: string): Promise<BenchmarkRunReport> {
  const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) throw new Error(`Failed to load report '${runId}': ${res.statusText}`);
  return res.json();
}

export function getExportDownloadUrl(runId: string, format: 'json' | 'markdown'): string {
  return `${API_BASE}/api/runs/${encodeURIComponent(runId)}/export?format=${format}`;
}
