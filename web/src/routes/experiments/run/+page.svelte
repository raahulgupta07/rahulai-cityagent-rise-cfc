<script lang="ts">
  import { onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { experimentsApi, type RunOpts } from '$lib/api/experiments';
  import Icon from '$lib/Icon.svelte';

  type StageState = { id: string; label: string; status: 'wait'|'run'|'done'|'error'; secs?: number; summary?: string };
  type LogLine = { stage: string; level: string; source: string; msg: string; rows?: number; secs?: number; ts?: string };
  type Metric = { key: string; label: string; value: number; unit?: string; stage: string };

  // ── config ──
  const ALL_STAGES = [
    { id: 'extract',  label: 'Extract dims' },
    { id: 'sync',     label: 'Download sales' },
    { id: 'features', label: 'Features' },
    { id: 'train',    label: 'Train' },
    { id: 'backtest', label: 'Backtest' },
    { id: 'gate',     label: 'Gate' },
    { id: 'order',    label: 'Order qty' },
    { id: 'predict',  label: 'Predict' },
    { id: 'monitor',  label: 'Monitor' }
  ];
  let sim       = $state(true);
  let speed     = $state(4);
  let cutoff    = $state('');
  let chosen    = $state<Record<string, boolean>>(Object.fromEntries(ALL_STAGES.map(s => [s.id, true])));

  // ── run state ──
  let running   = $state(false);
  let version   = $state<string | null>(null);
  let stages    = $state<StageState[]>([]);
  let logs      = $state<LogLine[]>([]);
  let metrics   = $state<Record<string, Metric>>({});
  let progress  = $state<{ stage: string; pct: number; note: string } | null>(null);
  let gate      = $state<{ promoted: boolean; gain: number; challenger: number; champion: number } | null>(null);
  let done      = $state<{ version: string; wmape: number | null; promoted: boolean | null; secs: number } | null>(null);
  let errMsg    = $state<string | null>(null);
  let elapsed   = $state(0);

  let es: EventSource | null = null;
  let timer: any = null;
  let logBox: HTMLDivElement | null = $state(null);

  const activeIdx = $derived(stages.findIndex(s => s.status === 'run'));

  function launch() {
    reset();
    running = true;
    const opts: RunOpts = { sim, speed, stages: enabledStages() };
    if (cutoff) opts.cutoff = cutoff;
    const url = experimentsApi.runStreamUrl(opts);
    es = new EventSource(url);
    es.onmessage = (e) => handle(JSON.parse(e.data));
    es.onerror = () => { if (running && !done) { errMsg = 'Stream disconnected.'; stop(); } };
    const t0 = Date.now();
    timer = setInterval(() => { elapsed = (Date.now() - t0) / 1000; }, 100);
  }

  function enabledStages(): string {
    const on = ALL_STAGES.filter(s => chosen[s.id]).map(s => s.id);
    return on.length === ALL_STAGES.length ? '' : on.join(',');
  }

  function handle(d: any) {
    switch (d.type) {
      case 'experiment_start':
        version = d.version;
        stages = d.stages.map((s: any) => ({ id: s.id, label: s.label, status: 'wait' }));
        break;
      case 'stage_start':
        stages = stages.map(s => s.id === d.stage ? { ...s, status: 'run' } : s);
        progress = null;
        break;
      case 'log':
        logs = [...logs.slice(-500), { stage: d.stage, level: d.level, source: d.source, msg: d.msg, rows: d.rows, secs: d.secs, ts: d.ts }];
        break;
      case 'progress':
        progress = { stage: d.stage, pct: d.pct, note: d.note };
        break;
      case 'metric':
        metrics = { ...metrics, [d.key]: { key: d.key, label: d.label, value: d.value, unit: d.unit, stage: d.stage } };
        break;
      case 'stage_done':
        stages = stages.map(s => s.id === d.stage ? { ...s, status: d.status === 'error' ? 'error' : 'done', secs: d.secs, summary: d.summary } : s);
        progress = null;
        break;
      case 'gate':
        gate = { promoted: d.promoted, gain: d.gain, challenger: d.challenger, champion: d.champion };
        break;
      case 'done':
        done = { version: d.version, wmape: d.wmape, promoted: d.promoted, secs: d.secs };
        stop();
        break;
      case 'error':
        errMsg = d.msg; break;
    }
  }

  function stop() {
    running = false;
    es?.close(); es = null;
    if (timer) { clearInterval(timer); timer = null; }
  }
  function reset() {
    stop();
    version = null; stages = []; logs = []; metrics = {}; progress = null;
    gate = null; done = null; errMsg = null; elapsed = 0;
  }
  onDestroy(stop);

  // auto-scroll log to bottom on new lines
  $effect(() => { logs.length; if (logBox) logBox.scrollTop = logBox.scrollHeight; });

  const metricList = $derived(Object.values(metrics));
  function fmt(v: number, unit?: string) {
    if (unit === '%') return v.toFixed(1) + '%';
    if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + 'M';
    if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(1) + 'k';
    return Number.isInteger(v) ? String(v) : v.toFixed(3);
  }
  const levelColor: Record<string, string> = {
    info: 'text-railink2', good: 'text-sage', warn: 'text-warn', err: 'text-red-400'
  };
</script>

<div class="flex flex-col gap-5">
  <!-- header -->
  <div class="flex items-end justify-between gap-4 flex-wrap">
    <div>
      <h1 class="text-[22px] font-extrabold tracking-tight">Run Experiment</h1>
      <p class="text-sm text-muted max-w-2xl">
        Launch the whole pipeline end-to-end — Fabric extract → feature build → LightGBM training →
        walk-forward backtest → champion/challenger gate → order plan → predict → drift check —
        and watch every step live.
      </p>
    </div>
    {#if running}
      <button class="btn-warn" onclick={stop}><Icon name="stop" class="w-4 h-4" /> Stop</button>
    {:else if done || version}
      <button class="btn-subtle" onclick={reset}><Icon name="refresh" class="w-4 h-4" /> New run</button>
    {/if}
  </div>

  {#if errMsg}
    <div class="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{errMsg}</div>
  {/if}

  <!-- CONFIG (idle) -->
  {#if !version}
    <div class="card flex flex-col gap-5">
      <div class="grid md:grid-cols-2 gap-5">
        <!-- mode -->
        <div>
          <div class="text-[11px] font-bold text-muted uppercase tracking-wide mb-2">Mode</div>
          <div class="flex gap-2">
            <button class="flex-1 rounded-xl border px-4 py-3 text-left transition-colors
                           {sim ? 'border-accent bg-accent/8' : 'border-line hover:bg-bg'}"
                    onclick={() => sim = true}>
              <div class="font-semibold text-sm">Simulate</div>
              <div class="text-xs text-muted">Instant rehearsal · no creds · demo-safe</div>
            </button>
            <button class="flex-1 rounded-xl border px-4 py-3 text-left transition-colors
                           {!sim ? 'border-accent bg-accent/8' : 'border-line hover:bg-bg'}"
                    onclick={() => sim = false}>
              <div class="font-semibold text-sm">Real run · Fabric</div>
              <div class="text-xs text-muted">Trains in Microsoft Fabric · ~15 min · one at a time</div>
            </button>
          </div>
        </div>
        <!-- params -->
        <div class="flex flex-col gap-3">
          <div>
            <label class="text-[11px] font-bold text-muted uppercase tracking-wide" for="cutoff">Train cutoff (optional)</label>
            <input id="cutoff" type="date" bind:value={cutoff}
                   class="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm font-mono" />
          </div>
          {#if sim}
            <div>
              <label class="text-[11px] font-bold text-muted uppercase tracking-wide" for="speed">Animation speed · {speed}×</label>
              <input id="speed" type="range" min="1" max="8" step="1" bind:value={speed} class="mt-1 w-full accent-accent" />
            </div>
          {/if}
        </div>
      </div>
      <!-- stages -->
      <div>
        <div class="text-[11px] font-bold text-muted uppercase tracking-wide mb-2">Stages</div>
        <div class="flex flex-wrap gap-2">
          {#each ALL_STAGES as s}
            <button class="text-xs font-medium rounded-lg px-3 py-1.5 border transition-colors
                           {chosen[s.id] ? 'border-accent bg-accent/10 text-accent' : 'border-line text-muted hover:bg-bg'}"
                    onclick={() => chosen[s.id] = !chosen[s.id]}>{s.label}</button>
          {/each}
        </div>
      </div>
      {#if !sim}
        <div class="rounded-lg bg-warn/8 border border-warn/25 px-3 py-2 text-xs text-warn">
          Real run submits the full pipeline to <strong>Microsoft Fabric</strong> (features → train →
          backtest → predict → monitor, ~15 min) next to the Lakehouse data. Stage picks are ignored —
          Fabric runs the whole chain. It registers a <strong>challenger</strong> you then approve on the
          Leaderboard. Holds the single-experiment slot until done.
        </div>
      {/if}
      <div>
        <button class="btn-primary" onclick={launch}><Icon name="play" class="w-4 h-4" /> Launch experiment</button>
      </div>
    </div>
  {/if}

  <!-- RUNNING / DONE -->
  {#if version}
    <!-- stepper -->
    <div class="card !p-4">
      <div class="flex items-center justify-between mb-3">
        <div class="font-mono text-sm text-ink">{version}
          <span class="text-xs text-muted ml-2">{sim ? 'simulated' : 'real'} · {stages.filter(s=>s.status==='done').length}/{stages.length} stages</span>
        </div>
        <div class="font-mono text-xs text-muted tabular-nums">{elapsed.toFixed(1)}s</div>
      </div>
      <div class="flex items-center gap-1 overflow-x-auto pb-1">
        {#each stages as s, i}
          <div class="flex items-center gap-1 flex-none">
            <div class="flex flex-col items-center gap-1 min-w-[76px]">
              <div class="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-none
                          {s.status==='done' ? 'bg-sage text-white' :
                            s.status==='run' ? 'bg-accent text-white animate-pulse' :
                            s.status==='error' ? 'bg-red-500 text-white' : 'bg-line text-muted'}">
                {#if s.status==='done'}<Icon name="check" class="w-4 h-4" />
                {:else if s.status==='error'}<Icon name="x" class="w-4 h-4" />
                {:else}{i+1}{/if}
              </div>
              <span class="text-[10px] text-center leading-tight {s.status==='run' ? 'text-accent font-semibold' : 'text-muted'}">{s.label}</span>
            </div>
            {#if i < stages.length-1}
              <div class="h-0.5 w-4 rounded {stages[i].status==='done' ? 'bg-sage' : 'bg-line'}"></div>
            {/if}
          </div>
        {/each}
      </div>
    </div>

    <div class="grid lg:grid-cols-[1.6fr_1fr] gap-4">
      <!-- CLI LOG -->
      <div class="rounded-2xl border border-railline bg-rail overflow-hidden flex flex-col" style="min-height:420px">
        <div class="flex items-center gap-2 px-4 py-2.5 border-b border-railline bg-rail2">
          <span class="w-2.5 h-2.5 rounded-full bg-red-400"></span>
          <span class="w-2.5 h-2.5 rounded-full bg-yellow-400"></span>
          <span class="w-2.5 h-2.5 rounded-full bg-green-400"></span>
          <span class="ml-2 font-mono text-xs text-railink2">experiment · live log</span>
          {#if running}<span class="ml-auto font-mono text-[11px] text-accent flex items-center gap-1.5">
            <Icon name="activity" class="w-3.5 h-3.5 animate-pulse" /> streaming</span>{/if}
        </div>
        <div bind:this={logBox} class="flex-1 overflow-y-auto px-4 py-3 font-mono text-[12px] leading-relaxed space-y-0.5" style="max-height:520px">
          {#each logs as l}
            <div class="flex gap-2 items-baseline">
              <span class="text-railink2/50 flex-none w-16 tabular-nums">{l.ts ?? ''}</span>
              <span class="text-accent/80 flex-none w-16 truncate">{l.source}</span>
              <span class="{levelColor[l.level] ?? 'text-railink2'} flex-1 break-all">{l.msg}</span>
              {#if l.rows != null}<span class="text-railink2 flex-none tabular-nums">{fmt(l.rows)} rows</span>{/if}
              {#if l.secs != null}<span class="text-railink2/60 flex-none w-12 text-right tabular-nums">{l.secs}s</span>{/if}
            </div>
          {/each}
          {#if running}
            <div class="flex gap-2 items-center text-accent">
              <span class="w-16"></span><span class="animate-pulse">▍</span>
            </div>
          {/if}
        </div>
        {#if progress}
          <div class="px-4 py-2 border-t border-railline bg-rail2">
            <div class="flex justify-between text-[11px] font-mono text-railink2 mb-1">
              <span>{progress.stage} · {progress.note}</span><span>{progress.pct}%</span>
            </div>
            <div class="h-1.5 rounded-full bg-railline overflow-hidden">
              <div class="h-full rounded-full bg-accent transition-all duration-200" style="width:{progress.pct}%"></div>
            </div>
          </div>
        {/if}
      </div>

      <!-- METRICS + GATE + DONE -->
      <div class="flex flex-col gap-4">
        {#if metricList.length}
          <div class="grid grid-cols-2 gap-3">
            {#each metricList as m}
              <div class="card !p-3.5">
                <div class="text-[10px] font-bold text-muted uppercase tracking-wide truncate">{m.label}</div>
                <div class="font-mono font-extrabold text-xl mt-1 {m.key==='wmape' ? 'text-accent' : ''}">{fmt(m.value, m.unit)}</div>
              </div>
            {/each}
          </div>
        {:else}
          <div class="card !p-4 text-sm text-muted">Metrics appear here as stages compute them…</div>
        {/if}

        {#if gate}
          <div class="rounded-2xl border px-4 py-3.5 {gate.promoted ? 'border-sage/40 bg-sage/8' : 'border-line bg-bg'}">
            <div class="flex items-center gap-2 text-sm font-bold {gate.promoted ? 'text-sage' : 'text-muted'}">
              <Icon name={gate.promoted ? 'check' : 'info'} class="w-4 h-4" />
              {gate.promoted ? 'PROMOTED to champion' : 'Held as challenger'}
            </div>
            <div class="text-xs text-muted font-mono mt-1.5">
              challenger {gate.challenger} vs champion {gate.champion} · gain +{gate.gain}%
            </div>
          </div>
        {/if}

        {#if done}
          <div class="rounded-2xl border border-accent/30 bg-accent/6 px-5 py-4">
            <div class="flex items-center gap-2 font-extrabold text-accent"><Icon name="check" class="w-5 h-5" /> Experiment complete</div>
            <div class="text-sm text-muted mt-1 font-mono">
              {done.version} · {done.wmape != null ? `WMAPE ${done.wmape}` : 'done'}
              {done.promoted ? ' · promoted' : ''} · {done.secs}s
            </div>
            <div class="flex gap-2 mt-3 flex-wrap">
              <button class="btn-primary" onclick={() => goto(`/leaderboard/${done!.version}`)}>
                View full evidence <Icon name="arrowRight" class="w-4 h-4" /></button>
              <a class="btn-teal" href="/api/order/export.xlsx" download>
                <Icon name="download" class="w-4 h-4" /> Order plan (outlet × SKU)</a>
              <a class="btn-subtle" href="/ordering">Smart Ordering</a>
            </div>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
