<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { agentApi } from '$lib/api/agent';
  import type { Autonomy, PlanStep, AgentStatus } from '$lib/api/agent';
  import Icon from '$lib/Icon.svelte';

  let status    = $state<AgentStatus | null>(null);
  let autonomy  = $state<Autonomy>('assisted');
  let guard     = $state(true);                       // safe demo default: heavy stages dry-run

  let steps     = $state<PlanStep[]>([]);
  let stepState = $state<Record<string, 'wait' | 'run' | 'done' | 'error'>>({});
  let narration = $state<string>('');
  let log       = $state<string[]>([]);
  let interpret = $state<string | null>(null);
  let decision  = $state<{ verdict: string; detail: string; champion_accuracy: number | null } | null>(null);
  let awaiting  = $state<string | null>(null);
  let running   = $state(false);
  let es: EventSource | null = null;

  onMount(async () => {
    try {
      status = await agentApi.status();
      autonomy = status.default_autonomy;
      const p = await agentApi.plan(autonomy);
      steps = p.steps; narration = p.narration;
    } catch { /* ignore */ }
  });
  onDestroy(() => es?.close());

  async function refreshPlan() {
    if (running) return;
    try { const p = await agentApi.plan(autonomy); steps = p.steps; narration = p.narration; } catch { /* */ }
  }

  function start() {
    es?.close();
    log = []; interpret = null; decision = null; awaiting = null; running = true;
    stepState = {};

    es = agentApi.run(autonomy, guard);
    es.onmessage = (ev) => {
      let e: any;
      try { e = JSON.parse(ev.data); } catch { return; }
      switch (e.type) {
        case 'plan':
          steps = e.steps; narration = e.narration;
          stepState = Object.fromEntries(e.steps.map((s: PlanStep) => [s.id, 'wait']));
          break;
        case 'step_start': stepState = { ...stepState, [e.id]: 'run' }; break;
        case 'log':        log = [...log, e.line]; break;
        case 'step_done':  stepState = { ...stepState, [e.id]: e.status === 'error' ? 'error' : 'done' }; break;
        case 'interpret':  interpret = e.text; break;
        case 'decision':   decision = { verdict: e.verdict, detail: e.detail, champion_accuracy: e.champion_accuracy }; break;
        case 'awaiting_approval': awaiting = e.reason; break;
        case 'done':       running = false; es?.close(); es = null; break;
        case 'error':      log = [...log, 'error: ' + e.message]; running = false; break;
      }
    };
    es.onerror = () => { running = false; es?.close(); es = null; };
  }

  function stop() {
    es?.close(); es = null; running = false;
    log = [...log, '[stopped by user]'];
  }

  function dotCls(s: string | undefined) {
    return s === 'done' ? 'bg-sage' : s === 'run' ? 'bg-accent animate-pulse'
         : s === 'error' ? 'bg-warn' : 'bg-line';
  }
</script>

<div class="space-y-6">
  <div class="flex items-end justify-between gap-4 flex-wrap">
    <div>
      <h1 class="font-display text-2xl text-ink mb-1">Autopilot</h1>
      <p class="text-sm text-muted max-w-2xl">
        The machine plans and runs the whole experiment — build signals, train a candidate, grade it,
        and decide whether it goes live. You choose how much it does on its own.
      </p>
    </div>
    {#if status}
      <span class="text-xs px-2.5 py-1 rounded-full {status.llm_narration ? 'bg-sage/15 text-sage' : 'bg-line text-muted'} font-medium">
        {status.llm_narration ? `narration: ${status.model}` : 'narration: offline templates'}
      </span>
    {/if}
  </div>

  <!-- controls -->
  <div class="rounded-2xl border border-line bg-surface shadow-soft p-4 flex flex-wrap items-center gap-4">
    <div class="flex gap-1.5">
      {#each (['manual', 'assisted', 'full_auto'] as Autonomy[]) as a}
        <button class="text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors
                       {autonomy === a ? 'bg-accent text-white border-accent' : 'bg-bg border-line text-muted hover:text-ink'}"
                onclick={() => { autonomy = a; refreshPlan(); }} disabled={running}>
          {a === 'full_auto' ? 'full-auto' : a}
        </button>
      {/each}
    </div>
    <label class="text-xs text-muted flex items-center gap-2 cursor-pointer">
      <input type="checkbox" bind:checked={guard} disabled={running} class="accent-accent" />
      safe demo (heavy stages dry-run)
    </label>
    <div class="flex-1"></div>
    {#if running}
      <button class="btn-warn" onclick={stop} aria-label="Stop the run"><Icon name="stop" class="w-4 h-4" /> Stop</button>
    {:else}
      <button class="btn-primary" onclick={start} aria-label="Start Autopilot"><Icon name="play" class="w-4 h-4" /> Start Autopilot</button>
    {/if}
  </div>

  {#if narration}
    <div class="rounded-xl bg-bg border border-line px-4 py-3 text-sm text-ink italic flex gap-2 items-start"><Icon name="info" class="w-4 h-4 mt-0.5 flex-none text-accent not-italic" /> <span>{narration}</span></div>
  {/if}

  <div class="grid gap-6 lg:grid-cols-[1fr_1fr]">
    <!-- plan / steps -->
    <div class="rounded-2xl border border-line bg-surface shadow-soft p-5">
      <h3 class="text-base mb-4">Plan</h3>
      <div class="space-y-3">
        {#each steps as s, i}
          <div class="flex gap-3 items-start">
            <span class="mt-1 inline-block w-2.5 h-2.5 rounded-full flex-none {dotCls(stepState[s.id])}"></span>
            <div>
              <div class="font-medium text-sm">{i + 1}. {s.label}</div>
              <div class="text-xs text-muted">{s.blurb}</div>
            </div>
          </div>
        {/each}
      </div>

      {#if decision}
        <div class="mt-5 rounded-xl border px-4 py-3
                    {decision.verdict === 'promote' ? 'bg-sage/10 border-sage/30' : 'bg-bg border-line'}">
          <div class="text-xs font-mono uppercase tracking-wide {decision.verdict === 'promote' ? 'text-sage' : 'text-muted'}">
            Decision: {decision.verdict}
          </div>
          <div class="text-sm mt-1">{decision.detail}
            {#if decision.champion_accuracy != null}<span class="text-muted">· live accuracy {decision.champion_accuracy}%</span>{/if}
          </div>
        </div>
      {/if}
      {#if interpret}
        <div class="mt-3 text-sm text-ink flex gap-2 items-start"><Icon name="info" class="w-4 h-4 mt-0.5 flex-none text-accent" /> <span>{interpret}</span></div>
      {/if}
      {#if awaiting}
        <div class="mt-3 rounded-xl bg-warn/10 border border-warn/30 px-4 py-3 text-sm text-warn">
          <div class="flex gap-2 items-start"><Icon name="info" class="w-4 h-4 mt-0.5 flex-none" /> <span>{awaiting}</span></div>
          {#if autonomy === 'assisted'}
            <button class="btn-primary btn-sm mt-2.5" onclick={() => { autonomy = 'full_auto'; start(); }}>Approve &amp; continue <Icon name="arrowRight" class="w-3.5 h-3.5" /></button>
          {/if}
        </div>
      {/if}
    </div>

    <!-- live log -->
    <div class="rounded-2xl border border-line bg-surface shadow-soft p-5 flex flex-col">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-base">Agent log</h3>
        {#if running}<span class="dot animate-ping"></span>{/if}
      </div>
      <div class="flex-1 overflow-y-auto font-mono text-xs bg-bg rounded-xl p-3 space-y-0.5"
           style="min-height:220px; max-height:420px">
        {#if log.length === 0}
          <div class="text-muted">Press Start Autopilot — I'll plan the run and stream every step here.</div>
        {:else}
          {#each log as line}
            <div class="{line.startsWith('[ERROR]') || line.startsWith('error') ? 'text-warn'
                        : line.startsWith('[DONE]') ? 'text-sage'
                        : line.startsWith('[START]') ? 'text-accent' : 'text-ink'}">{line}</div>
          {/each}
        {/if}
      </div>
    </div>
  </div>
</div>
