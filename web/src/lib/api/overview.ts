// Overview snapshot client — one cached payload for the whole page.
// GET /overview = instant cached read; POST /overview/sync = pull live + recache.
const base = '/api';

export type OverviewSnapshot = {
  cached_at: string | null;
  age_seconds: number | null;
  live: boolean;
  building?: boolean;          // cache is being (re)built in the background
  data: Record<string, any>;   // { network, dates, results, learning, accuracy_summary,
                               //   accuracy_daily, versions, health, dial, gaps, econ,
                               //   workflow, jobs, sources }
};

export const overviewApi = {
  snapshot: async (): Promise<OverviewSnapshot> => {
    const r = await fetch(base + '/overview', { credentials: 'same-origin' });
    if (!r.ok) throw new Error(`GET /overview → ${r.status}`);
    return r.json();
  },
  sync: async (): Promise<OverviewSnapshot> => {
    const r = await fetch(base + '/overview/sync', { method: 'POST', credentials: 'same-origin' });
    if (!r.ok) throw new Error(`POST /overview/sync → ${r.status}`);
    return r.json();
  }
};
