<script lang="ts">
  import { onMount } from 'svelte';
  import { resultsApi, type LearningStatus, type LogEntry } from '$lib/api/results';
  import Icon from '$lib/Icon.svelte';

  let status = $state<LearningStatus | null>(null);
  let logEntries = $state<LogEntry[]>([]);
  let error = $state<string | null>(null);
  let logError = $state<string | null>(null);
  let checkingNow = $state(false);

  onMount(async () => {
    try {
      [status, { entries: logEntries }] = await Promise.all([
        resultsApi.learningStatus(),
        resultsApi.learningLog(),
      ]);
    } catch (e) {
      error = String(e);
    }
  });

  async function recheckNow() {
    checkingNow = true;
    try {
      status = await resultsApi.learningStatus();
    } catch (e) {
      error = String(e);
    } finally {
      checkingNow = false;
    }
  }

  function trendColor(t: string) {
    if (t === 'improving') return 'text-sage';
    if (t === 'declining') return 'text-warn';
    return 'text-muted';
  }

  function trendIcon(t: string) {
    if (t === 'improving') return '↑';
    if (t === 'declining') return '↓';
    return '→';
  }

  function verdictClass(v: string) {
    if (v.includes('urgent')) return 'bg-warn/10 text-warn border border-warn/20';
    if (v.includes('recommended')) return 'bg-warn/5 text-warn border border-warn/10';
    return 'bg-sage/10 text-sage border border-sage/20';
  }

  function kindIcon(k: string) {
    if (k === 'retrain') return 'rotate';
    if (k === 'predict') return 'diamond';
    if (k === 'monitor') return 'activity';
    return 'info';
  }
</script>

<h1 class="text-3xl mb-1">Model health</h1>
<p class="text-muted text-sm mb-6">Live accuracy · drift signals · self-learning log</p>

{#if error}
  <div class="card border-warn text-warn mb-4">{error}</div>
{/if}

{#if !status}
  <div class="text-muted animate-pulse">Loading health status…</div>
{:else}
  <!-- ── top row: live model health ── -->
  <div class="grid grid-cols-3 gap-4 mb-6">
    <div class="card">
      <div class="text-xs text-muted uppercase tracking-wide mb-1">Live model</div>
      <div class="text-2xl font-display mb-1">{status.live_version}</div>
      <div class="text-4xl font-display text-accent">{status.live_accuracy_pct}%</div>
      <div class="text-sm text-muted mt-1">accuracy at training time</div>
    </div>

    <div class="card">
      <div class="text-xs text-muted uppercase tracking-wide mb-1">Recent accuracy</div>
      <div class="text-4xl font-display {trendColor(status.accuracy_trend)}">
        {trendIcon(status.accuracy_trend)} {status.recent_accuracy_pct}%
      </div>
      <div class="text-sm text-muted mt-1 capitalize">trend: {status.accuracy_trend}</div>
      {#if status.last_checked}
        <div class="text-xs text-muted mt-2">checked {status.last_checked}</div>
      {/if}
    </div>

    <div class="card">
      <div class="text-xs text-muted uppercase tracking-wide mb-1">Candidate model</div>
      {#if status.candidate.available}
        <div class="text-2xl font-display mb-1">
          {status.candidate.accuracy_pct?.toFixed(1)}%
        </div>
        {#if (status.candidate.gain_pct ?? 0) > 0}
          <div class="text-sage text-sm">+{status.candidate.gain_pct?.toFixed(1)}% gain if promoted</div>
        {:else}
          <div class="text-muted text-sm">No gain vs live — holding</div>
        {/if}
        <div class="text-xs text-muted mt-2 capitalize">{status.candidate.status}</div>
      {:else}
        <div class="text-muted text-sm mt-2">No candidate shadowing</div>
        <div class="text-xs text-muted mt-1">Retrain to generate one</div>
      {/if}
    </div>
  </div>

  <!-- ── verdict banner ── -->
  <div class="rounded-2xl p-4 mb-6 {verdictClass(status.verdict.toLowerCase())}">
    <div class="font-medium">{status.verdict}</div>
  </div>

  <!-- ── drift watch ── -->
  <div class="card mb-6">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-base">Input signal watch</h3>
      <div class="flex gap-2">
        <button
          class="btn-subtle btn-sm"
          onclick={recheckNow}
          disabled={checkingNow}
          aria-label="Re-check drift now"
        >
          <Icon name="refresh" class="w-3.5 h-3.5 {checkingNow ? 'animate-spin' : ''}" />
          {checkingNow ? 'Checking…' : 'Re-check now'}
        </button>
        <button class="btn-subtle btn-sm opacity-50 cursor-not-allowed" disabled aria-label="Schedule (coming soon)">
          <Icon name="calendar" class="w-3.5 h-3.5" /> Schedule
        </button>
      </div>
    </div>

    <div class="space-y-3">
      {#each status.drift_watch as item}
        <div class="flex items-start gap-3 p-3 rounded-xl {item.severity === 'watch' ? 'bg-warn/5 border border-warn/15' : 'bg-bg border border-line/60'}">
          <span class="mt-0.5 {item.severity === 'watch' ? 'text-warn' : 'text-sage'}">
            {#if item.severity === 'watch'}<Icon name="info" class="w-4 h-4" />{:else}<Icon name="check" class="w-4 h-4" />{/if}
          </span>
          <div class="flex-1">
            <div class="text-sm font-medium">{item.signal}</div>
            <div class="text-xs text-muted mt-0.5">{item.detail}</div>
          </div>
          <span class="text-xs rounded-full px-2 py-0.5 {item.severity === 'watch' ? 'bg-warn/10 text-warn' : 'bg-sage/10 text-sage'}">
            {item.severity === 'watch' ? 'watch' : 'ok'}
          </span>
        </div>
      {/each}
    </div>
  </div>

  <!-- ── pipeline log ── -->
  <div class="card">
    <h3 class="text-base mb-4">Activity log</h3>
    {#if logError}
      <div class="text-warn text-sm">{logError}</div>
    {:else if logEntries.length === 0}
      <div class="text-muted text-sm">No log entries yet.</div>
    {:else}
      <div class="space-y-2">
        {#each [...logEntries].reverse() as entry}
          <div class="flex items-start gap-3 text-sm py-2 border-b border-line/50 last:border-0">
            <span class="text-muted mt-0.5 w-4 flex justify-center"><Icon name={kindIcon(entry.kind)} class="w-3.5 h-3.5" /></span>
            <div class="flex-1">
              <span class="text-ink">{entry.summary}</span>
              {#if entry.ts}
                <span class="text-muted ml-2 text-xs">{entry.ts}</span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
{/if}
