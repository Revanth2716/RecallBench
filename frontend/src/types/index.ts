export type BenchmarkCategory =
  | 'TEMPORAL_RECALL'
  | 'STALE_FACT_DETECTION'
  | 'CONTRADICTION_HANDLING'
  | 'ENTITY_ISOLATION'
  | 'DELETION_COMPLIANCE';

export type QueryStatus =
  | 'FOUND'
  | 'NOT_FOUND'
  | 'CONTRADICTION'
  | 'TOMBSTONED_DELETED'
  | 'SUPERSEDED_STALE';

export type ContradictionPolicy =
  | 'DETERMINISTIC_ABSTAIN'
  | 'LAST_ASSERTION_WINS'
  | 'CONFIDENCE_WEIGHTED'
  | 'MULTIVALUED_COLLECTION';

export interface HealthResponse {
  status: string;
  version: string;
  catalog_version: string;
  scenarios_count: number;
}

export interface BenchmarkSummary {
  scenario_id: string;
  category: BenchmarkCategory;
  description: string;
  file: string;
  queries_count: number;
}

export interface BenchmarksListResponse {
  categories: string[];
  scenarios: BenchmarkSummary[];
}

export interface TimelineEvent {
  event_type: string;
  event_id: string;
  timestamp: string;
  entity_id: string;
  attribute?: string;
  value?: any;
  valid_from?: string;
  valid_to?: string;
  effective_time?: string;
  policy?: string;
  confidence?: number;
}

export interface ScenarioQuery {
  query_id: string;
  query: {
    entity_id: string;
    attribute: string;
    as_of_valid_time?: string;
    as_of_assertion_time?: string;
  };
  ground_truth: {
    expected_status: QueryStatus;
    expected_abstention?: boolean;
    expected_value?: any;
    forbidden_values?: any[];
    valid_interval?: (string | null)[];
  };
}

export interface ScenarioDetailResponse {
  scenario_id: string;
  version: string;
  category: BenchmarkCategory;
  description: string;
  contradiction_policy: ContradictionPolicy;
  timeline_events: TimelineEvent[];
  queries: ScenarioQuery[];
}

export interface LatencyStats {
  count: number;
  mean_ms?: number;
  p50_ms?: number;
  p95_ms?: number;
  p99_ms?: number;
}

export interface AggregateMetrics {
  total_queries: number;
  passed_queries: number;
  failed_queries: number;
  overall_score?: number;
  micro_pass_rate?: number;
  temporal_recall_accuracy?: number;
  stale_fact_rate?: number;
  stale_fact_accuracy?: number;
  contradiction_handling_score?: number;
  entity_isolation_accuracy?: number;
  deletion_compliance?: number;
  latency: LatencyStats;
}

export interface EvaluationResult {
  scenario_id: string;
  query_id: string;
  category: BenchmarkCategory;
  passed: boolean;
  expected_status: QueryStatus;
  actual_status: QueryStatus;
  expected_value: any;
  actual_value: any;
  is_stale_leak: boolean;
  is_tombstone_leak: boolean;
  is_entity_crossover: boolean;
  error_message?: string;
  latency_ms: number;
}

export interface ScenarioRunResult {
  scenario_id: string;
  category: BenchmarkCategory;
  evaluations: EvaluationResult[];
  passed_count: number;
  total_count: number;
  all_passed: boolean;
}

export interface BenchmarkRunReport {
  run_id: string;
  store_name: string;
  timestamp: string;
  scenarios_evaluated: number;
  total_queries: number;
  passed_queries: number;
  failed_queries: number;
  scenario_results: ScenarioRunResult[];
  aggregate_metrics: AggregateMetrics;
}

export interface RunSummaryResponse {
  run_id: string;
  store_name: string;
  timestamp: string;
  scenarios_evaluated: number;
  total_queries: number;
  passed_queries: number;
  failed_queries: number;
  overall_score?: number;
  micro_pass_rate?: number;
}
