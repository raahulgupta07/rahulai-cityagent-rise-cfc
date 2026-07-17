// Typed API client for the /data slice.
// Vite proxies /api -> FastAPI :8000 (see vite.config.ts).

const base = '/api/data';

async function get<T>(path: string): Promise<T> {
  const r = await fetch(base + path);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

// ── Response types ──────────────────────────────────────────────────────────

export type SyncStatus = {
  table: string;
  present: boolean;
  rows: number | null;
  freshness: string | null;
};

export type ManualFile = {
  name: string;
  size_kb: number;
  loaded: boolean;
};

export type GapItem = {
  key: string;
  label: string;
  owner: string;
  status: string;
  has_template: boolean;
};

export type UploadResult = {
  ok: boolean;
  matched: number;
  unmatched: string[];
  range_errors: string[];
  blank_count: number;
  preview: Record<string, unknown>[];
  filename?: string;
  rows_uploaded?: number;
  accepted?: boolean;
  saved_to?: string;
  error?: string;
};

// Provenance (P1): DB-synced vs manual-upload lanes, from /sources
export type SyncedSource = {
  name: string;
  source: 'database';
  rows: number | null;
  last_sync: string | null;
  status: 'ok' | 'missing';
};

export type ManualSource = {
  key: string;
  name: string;
  source: 'manual';
  has_template: boolean;
  required: boolean;
  rows: number | null;
  last_upload: string | null;
  status: 'valid' | 'needs_you' | 'optional';
};

export type Provenance = {
  synced: SyncedSource[];
  manual: ManualSource[];
  summary: {
    synced_ok: number;
    synced_total: number;
    manual_needs_you: number;
    manual_valid: number;
  };
};

// ── API functions ───────────────────────────────────────────────────────────

export const dataApi = {
  /** Provenance: which inputs come from the database vs manual upload. */
  getSources: (): Promise<Provenance> =>
    // note: /sources is a sibling router, not under /data
    fetch('/api/sources').then((r) => {
      if (!r.ok) throw new Error(`GET /sources → ${r.status}`);
      return r.json();
    }),

  /** Check which Fabric tables are present as parquet. */
  getSyncStatus: (): Promise<SyncStatus[]> =>
    get('/sync/status'),

  /** List manually added files. */
  getManualFiles: (): Promise<{ files: ManualFile[] }> =>
    get('/manual'),

  /** List the 12 gap inputs we still need. */
  getGaps: (): Promise<GapItem[]> =>
    get('/gaps'),

  /** Trigger a browser download of a template xlsx. */
  downloadTemplate: async (key: string): Promise<void> => {
    const r = await fetch(`${base}/template/${key}`);
    if (!r.ok) throw new Error(`template ${key} → ${r.status}`);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${key}_template.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  /**
   * Upload a file for the given key.
   * @param accept  if true, write to canonical location after validation succeeds
   */
  uploadFile: async (
    key: string,
    file: File,
    accept = false,
  ): Promise<UploadResult> => {
    const form = new FormData();
    form.append('file', file);
    const r = await fetch(`${base}/upload/${key}?accept=${accept}`, {
      method: 'POST',
      body: form,
    });
    if (!r.ok) {
      const text = await r.text();
      throw new Error(`upload ${key} → ${r.status}: ${text}`);
    }
    return r.json();
  },
};
