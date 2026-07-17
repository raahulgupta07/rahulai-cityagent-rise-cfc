// Typed client for the /experiments slice (P3).
// Vite proxies /api -> FastAPI. Neutral fields only (no method/metric names).

async function get<T>(path: string): Promise<T> {
  const r = await fetch('/api/experiments' + path);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}
async function post<T>(path: string): Promise<T> {
  const r = await fetch('/api/experiments' + path, { method: 'POST' });
  if (!r.ok) throw new Error(`POST ${path} → ${r.status}`);
  return r.json();
}

export type ExperimentRow = {
  version: string;
  rank: number;
  trained_on: string | null;
  train_rows: number | null;
  holdout_rows: number | null;
  accuracy: number | null;     // %
  error: number | null;        // lower better
  median_hit: number | null;   // %
  is_champion: boolean;
};

export type Leaderboard = {
  experiments: ExperimentRow[];
  champion: string | null;
  count: number;
  champion_units_off?: number | null;   // plain-English: typical daily miss in units
};

export type Compare = {
  a: ExperimentRow;
  b: ExperimentRow;
  deltas: {
    accuracy: number | null;
    error: number | null;
    median_hit: number | null;
    train_rows: number | null;
  };
};

export type RerunDescriptor = {
  stage_id: string;
  reused_from: string;
  cutoff: string | null;
  stream_url: string;
};

export type PromoteResult = {
  ok: boolean; version: string; changed: boolean;
  previous?: string | null; note?: string; at?: string;
  mode?: 'fabric' | 'local'; job_id?: string; poll?: string;
};

export type RejectResult = { ok: boolean; version: string; rejected: boolean; champion: string | null; at: string };

export type JobStatus = {
  job_id: string;
  status: 'NotStarted' | 'InProgress' | 'Completed' | 'Failed' | 'Cancelled' | string | null;
  start?: string | null; end?: string | null; failure?: string | null;
};

export type Evidence = {
  version: string; name: string; status: string; is_champion: boolean;
  cutoff: string | null; train_rows: number | null; holdout_rows: number | null;
  metrics: {
    wmape: number; p50_bias: number; cover_p50: number; cover_p85: number; cover_p95: number;
    test_rows: number; class_a_wmape: number | null; floor_wmape: number;
  };
  calibration: { level: number; target: number; actual: number | null }[];
  by_class: { cls: string; wmape: number; n: number }[];
  folds: { fold: string; wmape: number }[];
  residuals: { bin: number; n: number }[];
  scatter: { actual: number; pred: number }[];
  feature_importance: { name: string; gain: number }[];
  hyperparams: Record<string, string | number>;
  feats: string[]; cats: string[];
  run_history: { kind: string; ts: string | null; wmape: number | null; note: string | null; drift: boolean }[];
  note: string | null;
};

export type RunOpts = {
  cutoff?: string; stages?: string; sim?: boolean; speed?: number; service_level?: number;
  fabric?: boolean;
};
// SSE URL for a full-experiment run (consumed via EventSource). Vite/Caddy proxy /api.
function runStreamUrl(o: RunOpts = {}): string {
  const p = new URLSearchParams();
  if (o.cutoff) p.set('cutoff', o.cutoff);
  if (o.stages) p.set('stages', o.stages);
  p.set('sim', String(o.sim ?? true));
  if (o.speed != null) p.set('speed', String(o.speed));
  if (o.service_level != null) p.set('service_level', String(o.service_level));
  if (o.fabric != null) p.set('fabric', String(o.fabric));
  return '/api/experiments/run?' + p.toString();
}

export const experimentsApi = {
  list:    ()                    => get<Leaderboard>(''),
  runStreamUrl,
  detail:  (v: string)          => get<ExperimentRow & { feature_count: number }>(`/${v}`),
  evidence:(v: string)          => get<Evidence>(`/${v}/evidence`),
  compare: (a: string, b: string) => get<Compare>(`/compare?a=${a}&b=${b}`),
  rerun:   (v: string)          => post<RerunDescriptor>(`/${v}/rerun`),
  promote: (v: string)          => post<PromoteResult>(`/${v}/promote`),
  reject:  (v: string)          => post<RejectResult>(`/${v}/reject`),
  jobStatus: (id: string)       => get<JobStatus>(`/jobs/${id}`),
};
