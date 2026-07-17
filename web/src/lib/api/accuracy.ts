// Typed client for the /accuracy slice — live pred-vs-actual accuracy over time.
// Mirrors api/routes/accuracy.py (built in parallel). Vite proxies /api -> FastAPI.

const base = '/api';

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const u = new URL(base + path, location.origin);
  for (const [k, v] of Object.entries(params ?? {})) if (v != null) u.searchParams.set(k, String(v));
  const r = await fetch(u.pathname + u.search);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

// One day of scored forecast-vs-actual.
export type AccuracyRow = {
  dt: string;          // YYYY-MM-DD
  accuracy: number;    // 0-100 (%)
  units_off: number;   // mean absolute units the forecast missed by, per series
  n_rows: number;      // series scored that day
  wmape: number;       // 0-1
};

export type AccuracyDaily = {
  rows: AccuracyRow[];
  source: string;      // "fabric" | "local" | …
};

export type AccuracySummary = {
  latest_accuracy: number | null;     // most recent day's accuracy %
  accuracy_7d_avg: number | null;     // trailing 7-day mean accuracy %
  accuracy_change_7d: number | null;  // latest vs 7d avg, in points
  units_off: number | null;           // typical daily miss, units
  drift: string | null;               // "stable" | "watch" | "drifting" | …
  source: string;
};

export const accuracyApi = {
  getDaily:   (days = 30) => get<AccuracyDaily>('/accuracy/daily', { days }),
  getSummary: ()          => get<AccuracySummary>('/accuracy/summary'),
};
