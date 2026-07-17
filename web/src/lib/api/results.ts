// Typed client for results / learning / pipeline slices.
// Mirrors api/routes/results.py + learning.py + pipeline.py (client-facing names only).
// Vite proxies /api -> FastAPI :8000.

const base = '/api';

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const u = new URL(base + path, location.origin);
  for (const [k, v] of Object.entries(params ?? {})) if (v != null) u.searchParams.set(k, String(v));
  const r = await fetch(u.pathname + u.search);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

async function post<T>(path: string): Promise<T> {
  const r = await fetch(base + path, { method: 'POST' });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

// ── results types ────────────────────────────────────────────────────────────

export type ClassAccuracy = {
  label: string;         // "Top sellers" | "Mid-range" | "Rare items"
  accuracy_pct: number;
  vol_share_pct?: number;
};

export type FoldStability = {
  period: string;        // "Apr 2026"
  accuracy_pct: number;
  beat_simple: boolean;
};

export type ResultsSummary = {
  accuracy_pct: number;
  improvement_pct: number;
  safe_level_honesty_pct: number;
  max_level_honesty_pct: number;
  cost_saving_pct: number;
  by_class: ClassAccuracy[];
  stability: FoldStability[];
  stable_all_periods: boolean;
};

// ── learning types ───────────────────────────────────────────────────────────

export type DriftItem = {
  signal: string;
  severity: 'watch' | 'ok';
  detail: string;
};

export type CandidateInfo = {
  available: boolean;
  accuracy_pct?: number;
  gain_pct?: number;
  status: string;
};

export type LearningStatus = {
  live_version: string;
  live_accuracy_pct: number;
  recent_accuracy_pct: number;
  accuracy_trend: 'improving' | 'stable' | 'declining';
  candidate: CandidateInfo;
  drift_watch: DriftItem[];
  verdict: string;
  last_checked?: string;
};

export type LogEntry = {
  ts?: string;
  kind: string;
  summary: string;
};

export type LearningLog = {
  entries: LogEntry[];
};

// ── pipeline types ───────────────────────────────────────────────────────────

export type PipelineStage = {
  id: string;
  label: string;
  description: string;
  heavy: boolean;
  status: 'done' | 'pending' | 'running';
  last_run?: string;
};

export type RunResult = {
  stage_id: string;
  label: string;
  mode: 'dry-run' | 'live';
  stream_url: string;
};

export type PipelineJob = {
  id: string;
  stage: string;
  params: Record<string, unknown>;
  heavy: boolean;
  mode: 'live' | 'dry-run';
  status: 'running' | 'done' | 'error';
  exit_code: number | null;
  error: string | null;
  started: string;
  finished: string | null;
};

// ── api surface ───────────────────────────────────────────────────────────────

export const resultsApi = {
  summary: ()                => get<ResultsSummary>('/results/summary'),
  learningStatus: ()         => get<LearningStatus>('/learning/status'),
  learningLog: (limit = 50)  => get<LearningLog>('/learning/log', { limit }),
  pipelineStages: ()         => get<PipelineStage[]>('/pipeline/stages'),
  pipelineJobs: (limit = 50) => get<PipelineJob[]>('/pipeline/jobs', { limit }),
  pipelineRun: (id: string, guard = true, params: Record<string, string> = {}) => {
    const q = new URLSearchParams({ guard: String(guard), ...params });
    return post<RunResult>(`/pipeline/run/${id}?${q}`);
  },
  /** Returns a native EventSource for SSE streaming of stage stdout */
  pipelineStream: (id: string, guard = true, params: Record<string, string> = {}): EventSource => {
    const q = new URLSearchParams({ guard: String(guard), ...params });
    return new EventSource(`/api/pipeline/stream/${id}?${q}`);
  },
};
