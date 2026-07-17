// Typed client for the /agent slice (P4 Autopilot).

async function get<T>(path: string): Promise<T> {
  const r = await fetch('/api/agent' + path);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

export type Autonomy = 'manual' | 'assisted' | 'full_auto';

export type PlanStep = { id: string; label: string; blurb: string };

export type AgentStatus = {
  llm_narration: boolean;
  model: string | null;
  autonomy_options: Autonomy[];
  default_autonomy: Autonomy;
};

// One decoded SSE event (see orchestrator.py for the union).
export type AgentEvent = {
  type: 'plan' | 'step_start' | 'log' | 'step_done' | 'interpret'
      | 'decision' | 'awaiting_approval' | 'done' | 'error';
  [k: string]: unknown;
};

export const agentApi = {
  status: () => get<AgentStatus>('/status'),
  plan:   (autonomy: Autonomy) => get<{ autonomy: Autonomy; narration: string; steps: PlanStep[] }>(`/plan?autonomy=${autonomy}`),
  /** Native EventSource streaming plan → steps → decision. */
  run: (autonomy: Autonomy, guard = false): EventSource =>
    new EventSource(`/api/agent/run?autonomy=${autonomy}&guard=${guard}`),
};
