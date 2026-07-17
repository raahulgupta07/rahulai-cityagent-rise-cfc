// Typed client for the /workflow slice — live state of the pipeline map.
export type WorkflowStatus = {
  fabric: boolean;
  source: { table: string; grain: string; manual: string[] };
  champion: { version: string; accuracy: number | null; since: string | null } | null;
  challenger: { version: string; accuracy: number | null; created: string; delta: number | null } | null;
  awaiting_approval: boolean;
  last_run: { version: string; accuracy: number | null; at: string; promoted: boolean } | null;
  drift: { at: string; verdict: string; data_drift: boolean; accuracy_drift: boolean } | null;
  order_plan: { date: string; rows: number } | null;
  runs_total: number;
  schedule: { id: string; enabled: boolean; type: string; times: string[]; timezone: string } | null;
  feature_top: { name: string; gain: number }[];
};

export async function getWorkflow(): Promise<WorkflowStatus> {
  const r = await fetch('/api/workflow/status');
  if (!r.ok) throw new Error(`GET /workflow/status → ${r.status}`);
  return r.json();
}
