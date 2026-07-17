// Settings + Schedule API client.
// Vite proxies /api → FastAPI :8000

const base = '/api';

async function get<T>(path: string): Promise<T> {
  const r = await fetch(base + path);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(base + path, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body:    body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`POST ${path} → ${r.status}`);
  return r.json();
}

// ── Response types ────────────────────────────────────────────────────────────

export type EconStatus = {
  found:      boolean;
  row_count:  number | null;
  gm_uniform: boolean | null;
  gm_values?: number[];
  warn:       boolean;
  message:    string;
};

export type ScheduleSummary = {
  any_enabled:  boolean;
  job_count:    number;
  enabled_jobs: string[];
};

export type SettingsOverview = {
  brand:            string;
  version:          string;
  auth_mode:        string;
  fabric_connected: boolean;
  fabric_server:    string;
  econ:             EconStatus;
  schedule:         ScheduleSummary;
  current_user:     { actor: string; role: string };
};

export type ScheduleJob = {
  id:          string;
  label:       string;
  description: string;
  enabled:     boolean;
  schedule:    string;
  last_run:    string | null;
  last_status: string | null;
};

export type AuditEvent = {
  id:     number;
  actor:  string;
  action: string;
  target: string;
  ts:     string;
};

// ── API functions ─────────────────────────────────────────────────────────────

export type SsoStatus = {
  enabled: boolean;
  provider: string;
  issuer: string | null;
  client_id: string | null;
  redirect_uri: string | null;
  redirect_uri_hint: string;
  default_role: string;
  admin_group: string | null;
  discovery_ok: boolean | null;
  error: string | null;
  env_keys: string[];
};

export const settingsApi = {
  getSettings: (): Promise<SettingsOverview> =>
    get('/settings'),

  getSso: (): Promise<SsoStatus> =>
    get('/settings/sso'),

  reconnectFabric: (): Promise<{ ok: boolean; message: string }> =>
    post('/settings/reconnect'),

  getAudit: (limit = 50): Promise<{ events: AuditEvent[] }> =>
    get(`/settings/audit?limit=${limit}`),

  getSchedule: (): Promise<{ jobs: ScheduleJob[] }> =>
    get('/schedule/status'),

  toggleJob: (jobId: string): Promise<{ job: ScheduleJob }> =>
    post(`/schedule/toggle/${jobId}`),

  runNow: (jobId: string): Promise<{ job_id: string; queued: boolean }> =>
    post(`/schedule/run-now/${jobId}`),
};
