// Typed client for the /deploy slice (P6). Neutral labels only.

async function get<T>(p: string): Promise<T> {
  const r = await fetch('/api/deploy' + p);
  if (!r.ok) throw new Error(`GET ${p} → ${r.status}`);
  return r.json();
}

export type Health = {
  status: string;
  live_version: string | null;
  live_accuracy: number | null;
  plans_generated: number;
  latest_plan_date: string | null;
  last_prediction_at: string | null;
  accuracy_alerts: number;
};

export type HistoryPoint = {
  ts: string | null;
  kind: 'check' | 'retrain';
  accuracy: number | null;
  data_drift: boolean;
  accuracy_drift: boolean;
  verdict: string | null;
};

export type History = {
  points: HistoryPoint[];
  warn_accuracy: number | null;
  baseline_accuracy: number | null;
};

export type CheckResult = {
  should_retrain: boolean;
  reason: string;
  triggered: boolean;
  note?: string;
  stream_url?: string;
};

export type VersionRow = {
  id: string; version: string; name: string; date: string;
  wmape: number; status: string; active: boolean;
};
export type Versions = { versions: VersionRow[]; active: string };
export type ApiSample = {
  request: { outlet_id: string; product_id: string; horizon_days: number };
  response: { p50: number; p85: number; p95: number; model_version: string };
};

export const deployApi = {
  health:  () => get<Health>('/health'),
  history: () => get<History>('/history'),
  versions:  () => get<Versions>('/versions'),
  apiSample: () => get<ApiSample>('/api-sample'),
  check:   async (auto = false): Promise<CheckResult> => {
    const r = await fetch(`/api/deploy/check?auto=${auto}`, { method: 'POST' });
    if (!r.ok) throw new Error(`check → ${r.status}`);
    return r.json();
  },
};
