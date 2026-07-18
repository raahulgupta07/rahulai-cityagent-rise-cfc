<script lang="ts">
  import { onMount } from 'svelte';
  import { resultsApi, type PipelineStage, type PipelineJob } from '$lib/api/results';
  import Icon from '$lib/Icon.svelte';

  let stages = $state<PipelineStage[]>([]);
  let jobs = $state<PipelineJob[]>([]);
  let error = $state<string | null>(null);

  async function refreshJobs() {
    try { jobs = await resultsApi.pipelineJobs(12); } catch { /* ignore */ }
  }
  function fmtDur(j: PipelineJob): string {
    if (!j.finished) return '…';
    const ms = new Date(j.finished).getTime() - new Date(j.started).getTime();
    return ms < 1000 ? '<1s' : ms < 60000 ? Math.round(ms / 1000) + 's' : Math.round(ms / 60000) + 'm';
  }

  // Live-log state per stage
  let activeStage = $state<string | null>(null);
  let logLines = $state<string[]>([]);
  let running = $state(false);
  let es: EventSource | null = null;

  onMount(async () => {
    try {
      stages = await resultsApi.pipelineStages();
      await refreshJobs();
    } catch (e) {
      error = String(e);
    }
  });

  function statusDot(s: PipelineStage) {
    if (s.id === activeStage && running) return 'bg-accent animate-pulse';
    if (s.status === 'done') return 'bg-sage';
    return 'bg-line';
  }

  function statusLabel(s: PipelineStage) {
    if (s.id === activeStage && running) return 'running…';
    if (s.status === 'done') return 'done';
    return 'pending';
  }

  async function runStage(stageId: string, guard = true) {
    // Close any existing stream
    if (es) { es.close(); es = null; }

    activeStage = stageId;
    logLines = [];
    running = true;

    // POST to kick (fires immediately via SSE)
    try {
      await resultsApi.pipelineRun(stageId, guard);
    } catch (e) {
      logLines = [`Error: ${e}`];
      running = false;
      return;
    }

    // Open SSE stream
    es = resultsApi.pipelineStream(stageId, guard);

    es.onmessage = (ev) => {
      const line = ev.data;
      if (line) logLines = [...logLines, line];
      if (line === '[DONE]' || line.startsWith('[DONE]') || line.startsWith('[ERROR]')) {
        running = false;
        es?.close(); es = null;
        // Refresh stage statuses + run history
        resultsApi.pipelineStages().then(s => stages = s).catch(() => {});
        refreshJobs();
      }
    };

    es.onerror = () => {
      logLines = [...logLines, '[stream closed]'];
      running = false;
      es?.close(); es = null;
    };
  }
</script>

<h1 class="text-3xl mb-1">Pipeline</h1>
<p class="text-muted text-sm mb-6">8-stage rebuild · each stage can be run independently</p>

{#if error}
  <div class="card border-warn text-warn mb-4">{error}</div>
{/if}

<div class="grid grid-cols-[1fr_380px] gap-5">

  <!-- ── stage table ── -->
  <div class="card">
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-muted border-b border-line">
          <th class="pb-2 font-medium w-5"></th>
          <th class="pb-2 font-medium">Stage</th>
          <th class="pb-2 font-medium text-muted hidden sm:table-cell">Last run</th>
          <th class="pb-2 font-medium text-right">Action</th>
        </tr>
      </thead>
      <tbody>
        {#each stages as stage, i}
          <tr class="border-b border-line/50 hover:bg-bg transition-colors {activeStage === stage.id ? 'bg-bg' : ''}">
            <td class="py-3 pr-3">
              <span class="inline-block w-2.5 h-2.5 rounded-full {statusDot(stage)}"></span>
            </td>
            <td class="py-3">
              <div class="font-medium flex items-center gap-2">
                {stage.label}
                {#if stage.runs_on === 'fabric'}
                  <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20 font-mono" title="Real runs execute on the Microsoft Fabric notebook, next to the data — not on this server">runs on Fabric</span>
                {/if}
              </div>
              <div class="text-xs text-muted mt-0.5">{stage.description}</div>
            </td>
            <td class="py-3 text-muted text-xs hidden sm:table-cell">
              {stage.last_run ?? '—'}
              <div class="text-xs {stage.status === 'done' ? 'text-sage' : 'text-muted'}">{statusLabel(stage)}</div>
            </td>
            <td class="py-3 text-right">
              <div class="flex gap-2 justify-end">
                {#if stage.heavy}
                  <button
                    class="pill-ghost text-xs py-1 px-3"
                    onclick={() => runStage(stage.id, true)}
                    disabled={running}
                  >
                    Dry run
                  </button>
                  <button
                    class="pill text-xs py-1 px-3 bg-warn/10 text-warn hover:bg-warn/20 border border-warn/20"
                    onclick={() => runStage(stage.id, false)}
                    disabled={running}
                    aria-label="Live run {stage.label}"
                  >
                    Run <Icon name="zap" class="w-3.5 h-3.5" />
                  </button>
                {:else}
                  <button
                    class="pill-accent text-xs py-1 px-3"
                    onclick={() => runStage(stage.id, false)}
                    disabled={running}
                  >
                    <Icon name="play" class="w-3.5 h-3.5" /> Run
                  </button>
                {/if}
              </div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>

    {#if stages.length === 0 && !error}
      <div class="text-muted text-sm py-6 text-center animate-pulse">Loading stages…</div>
    {/if}
  </div>

  <!-- ── live log panel ── -->
  <div class="card flex flex-col" style="height: fit-content; min-height: 300px; max-height: 600px;">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-base">Live log</h3>
      {#if activeStage}
        <span class="text-xs text-muted">{activeStage}</span>
      {/if}
      {#if running}
        <span class="dot animate-ping"></span>
      {/if}
    </div>

    {#if !activeStage}
      <div class="flex-1 flex items-center justify-center text-muted text-sm">
        Select a stage to run
      </div>
    {:else}
      <div class="flex-1 overflow-y-auto font-mono text-xs bg-bg rounded-xl p-3 space-y-0.5" style="min-height:200px">
        {#if logLines.length === 0}
          <div class="text-muted animate-pulse">Starting…</div>
        {:else}
          {#each logLines as line}
            <div
              class="{line.startsWith('[ERROR]') ? 'text-warn' :
                      line.startsWith('[DONE]')  ? 'text-sage font-medium' :
                      line.startsWith('[DRY')    ? 'text-muted italic' :
                      line.startsWith('[START]') ? 'text-accent font-medium' :
                      'text-ink'}"
            >{line}</div>
          {/each}
        {/if}
      </div>
    {/if}
  </div>
</div>

<!-- ── legend ── -->
<div class="mt-4 flex gap-6 text-xs text-muted">
  <div class="flex items-center gap-1.5"><span class="inline-block w-2 h-2 rounded-full bg-sage"></span> done</div>
  <div class="flex items-center gap-1.5"><span class="inline-block w-2 h-2 rounded-full bg-line"></span> pending</div>
  <div class="flex items-center gap-1.5"><span class="inline-block w-2 h-2 rounded-full bg-accent"></span> running</div>
  <div class="flex items-center gap-1.5 ml-4"><Icon name="zap" class="w-3.5 h-3.5" /> = live run · heavy stages default to dry-run for safety</div>
</div>

<!-- ── run history (P2 job store) ── -->
<div class="mt-8">
  <h3 class="text-base mb-3">Run history</h3>
  <div class="card">
    {#if jobs.length === 0}
      <div class="text-muted text-sm py-4 text-center">No runs yet — kick a stage above.</div>
    {:else}
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-muted border-b border-line text-xs">
            <th class="pb-2 font-medium">Stage</th>
            <th class="pb-2 font-medium">Settings</th>
            <th class="pb-2 font-medium">Status</th>
            <th class="pb-2 font-medium">Duration</th>
            <th class="pb-2 font-medium hidden sm:table-cell">Started</th>
          </tr>
        </thead>
        <tbody>
          {#each jobs as j}
            <tr class="border-b border-line/50 last:border-0">
              <td class="py-2 font-medium">{j.stage}</td>
              <td class="py-2 text-xs font-mono text-muted">
                {Object.keys(j.params).length ? JSON.stringify(j.params) : '—'}
              </td>
              <td class="py-2">
                <span class="text-xs px-2 py-0.5 rounded-full font-medium
                  {j.status === 'done' ? 'bg-sage/15 text-sage' :
                   j.status === 'error' ? 'bg-warn/15 text-warn' : 'bg-accent/10 text-accent'}">
                  {j.status}{j.exit_code != null && j.status === 'error' ? ` (${j.exit_code})` : ''}
                </span>
              </td>
              <td class="py-2 text-xs tabular-nums text-muted">{fmtDur(j)}</td>
              <td class="py-2 text-xs text-muted hidden sm:table-cell font-mono">{j.started.slice(0, 19).replace('T', ' ')}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</div>
