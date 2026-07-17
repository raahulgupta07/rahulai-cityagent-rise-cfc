<script lang="ts">
  import Icon from '$lib/Icon.svelte';
  import { api, type OutletRow } from '$lib/api';
  import { resultsApi, type ResultsSummary, type LearningStatus, type PipelineJob } from '$lib/api/results';
  import { accuracyApi, type AccuracySummary, type AccuracyDaily } from '$lib/api/accuracy';
  import { deployApi, type Versions, type Health } from '$lib/api/deploy';
  import { orderApi, type DialResponse } from '$lib/api/order';
  import { dataApi, type GapItem, type Provenance } from '$lib/api/data';
  import { insightsApi, type EconomicsImpact } from '$lib/api/insights';
  import { type WorkflowStatus } from '$lib/api/workflow';
  import { overviewApi } from '$lib/api/overview';

  // ── live datasets (each loads independently; a failure leaves its section blank) ──
  let net       = $state<OutletRow[] | null>(null);
  let dates     = $state<string[] | null>(null);
  let res       = $state<ResultsSummary | null>(null);
  let learn     = $state<LearningStatus | null>(null);
  let acc        = $state<AccuracySummary | null>(null);
  let accDaily  = $state<AccuracyDaily | null>(null);
  let vers      = $state<Versions | null>(null);
  let health    = $state<Health | null>(null);
  let dial      = $state<DialResponse | null>(null);
  let gaps      = $state<GapItem[] | null>(null);
  let econ      = $state<EconomicsImpact | null>(null);
  let wf        = $state<WorkflowStatus | null>(null);
  let jobs      = $state<PipelineJob[] | null>(null);
  let prov      = $state<Provenance | null>(null);

  let loadErr  = $state(false);          // snapshot failed after all retries
  let syncing  = $state(false);          // live sync in flight
  let cachedAt = $state<string | null>(null);
  let ageSec   = $state<number | null>(null);

  // One cached payload powers the whole page (data/cache/overview.json) — no live Fabric
  // per load. "Sync live" pulls fresh from Fabric+local and re-caches on demand.
  function distribute(d: Record<string, any>) {
    net = d.network ?? null;           dates = d.dates ?? null;
    res = d.results ?? null;           learn = d.learning ?? null;
    acc = d.accuracy_summary ?? null;  accDaily = d.accuracy_daily ?? null;
    vers = d.versions ?? null;         health = d.health ?? null;
    dial = d.dial ?? null;             gaps = d.gaps ?? null;
    econ = d.econ ?? null;             wf = d.workflow ?? null;
    jobs = d.jobs ?? null;             prov = d.sources ?? null;
  }

  let building = $state(false);

  async function loadAll() {
    loadErr = false;
    // Cache builds in the background at startup (~30s). Poll until it's ready, then paint.
    for (let i = 0; i < 16; i++) {
      try {
        const s = await overviewApi.snapshot();
        const ready = s?.data && Object.keys(s.data).length > 0 && !(s as any).building;
        if (ready) {
          distribute(s.data); cachedAt = s.cached_at; ageSec = s.age_seconds; building = false;
          return;
        }
        building = true;               // snapshot still building — keep polling
        throw new Error('building');
      } catch {
        if (i === 15) { loadErr = true; building = false; return; }
        await new Promise(r => setTimeout(r, Math.min(4000, 700 * 1.6 ** i)));  // ~40s total
      }
    }
  }

  let syncElapsed = $state(0);
  const SYNC_STEPS = ['model & champion', 'accuracy & backtest', 'ordering & dial', 'drift & data sources'];
  let syncStep = $derived(Math.min(SYNC_STEPS.length - 1, Math.floor(syncElapsed / 8)));

  let syncDenied = $state(false);   // POST /overview/sync is ops/admin-only → explain a 403
  async function syncLive() {
    syncing = true; loadErr = false; syncDenied = false; syncElapsed = 0;
    const t = setInterval(() => syncElapsed += 1, 1000);
    try {
      const s = await overviewApi.sync();
      distribute(s.data || {}); cachedAt = s.cached_at; ageSec = s.age_seconds;
    } catch (e) {
      if (String(e).includes('403')) syncDenied = true;   // not an outage — a role limit
      else loadErr = true;
    }
    finally { clearInterval(t); syncing = false; }
  }

  function agoText(): string {
    if (ageSec == null) return cachedAt ? cachedAt.replace('T', ' ').slice(0, 16) : '—';
    const s = ageSec;
    if (s < 90) return 'just now';
    if (s < 5400) return `${Math.round(s / 60)}m ago`;
    if (s < 172800) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
  }

  $effect(() => { loadAll(); });

  // ── helpers ──────────────────────────────────────────────────────────────
  const pct  = (x: number | null | undefined) =>
    x == null ? null : (x <= 1.5 ? x * 100 : x);
  const nfmt = (x: number) => Math.round(x).toLocaleString('en-US');
  const money = (k: number) =>
    k >= 1e9 ? `₭${(k / 1e9).toFixed(2)}B` : k >= 1e6 ? `₭${(k / 1e6).toFixed(0)}M` :
    k >= 1e3 ? `₭${(k / 1e3).toFixed(0)}K` : `₭${nfmt(k)}`;

  // ── network aggregates ───────────────────────────────────────────────────
  let outlets    = $derived(net?.length ?? null);
  let orderUnits = $derived(net ? net.reduce((s, o) => s + (o.order_units || 0), 0) : null);
  let networkKs  = $derived(net ? net.reduce((s, o) => s + (o.value_ks || 0), 0) : null);
  let topOutlets = $derived(net ? [...net].sort((a, b) => b.value_ks - a.value_ks).slice(0, 6) : []);

  let champVer   = $derived(vers?.active ?? learn?.live_version ?? '—');
  let champ      = $derived(vers?.versions.find(v => v.active) ?? null);
  let dateRange  = $derived(dates?.length ? `${dates[0]} → ${dates[dates.length - 1]}` : null);

  // verdict tone
  let needsRetrain = $derived(!!learn && /retrain/i.test(learn.verdict));

  // ── accuracy trend sparkline (SVG) ─────────────────────────────────────────
  const W = 720, H = 150, pad = 10;
  let tr = $derived.by(() => {
    const rows = accDaily?.rows;
    if (!rows?.length) return null;
    const ys = rows.map(r => (r.accuracy <= 1 ? r.accuracy * 100 : r.accuracy));
    const min = Math.min(...ys), max = Math.max(...ys);
    const lo = Math.max(0, min - 3), hi = Math.min(100, max + 3);
    const n = ys.length;
    const x = (i: number) => pad + (n === 1 ? 0 : (i * (W - 2 * pad)) / (n - 1));
    const y = (v: number) => pad + (1 - (v - lo) / (hi - lo || 1)) * (H - 2 * pad);
    const line = ys.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
    const area = `${line} L${x(n - 1).toFixed(1)} ${H - pad} L${x(0).toFixed(1)} ${H - pad} Z`;
    return { line, area, lo, hi, first: ys[0], last: ys[n - 1], min, max, from: rows[0].dt, to: rows[n - 1].dt };
  });

  // model evolution — lower WMAPE is better; scale bar to best/worst spread
  let versBars = $derived.by(() => {
    const vs = vers?.versions;
    if (!vs?.length) return [];
    const ws = vs.map(v => v.wmape);
    const worst = Math.max(...ws), best = Math.min(...ws);
    return vs.map(v => ({ ...v, frac: 1 - (v.wmape - best) / (worst - best || 1) }));
  });

  let pendingGaps = $derived(gaps ? gaps.filter(g => g.status !== 'accepted' && g.status !== 'done').length : null);
  let readiness   = $derived(gaps?.length ? Math.round(((gaps.length - (pendingGaps ?? 0)) / gaps.length) * 100) : null);

  // ── training / experiments ─────────────────────────────────────────────────
  const shortTime = (s?: string | null) => (s ? s.replace('T', ' ').slice(0, 16) : '—');
  const jobTone = (s: string) => s === 'done' ? 'text-sage' : s === 'error' ? 'text-warn' : 'text-accent';
  const jobNote = (j: PipelineJob) =>
    j.status === 'error' && j.exit_code === -9 ? 'out of memory (−9)'
      : j.status === 'error' ? (j.error ?? 'failed') : j.mode;

  // ── data provenance: real vs estimated vs missing ──────────────────────────
  // ESTIMATED = data present but not ground-truth (placeholder economics, inferred demand, backfilled weather)
  let estimated = $derived.by(() => {
    const out: { label: string; note: string }[] = [];
    if (econ?.available && econ.is_uniform)
      out.push({ label: 'Product economics', note: 'placeholder — flat 35% margin / 1-day shelf for all SKUs' });
    out.push({ label: 'Uncaptured demand', note: 'stockouts inferred; demand = max(observed sales, P85)' });
    out.push({ label: 'Weather history', note: 'early days gap-filled (CSV starts mid-2023)' });
    return out;
  });
  // MISSING = required manual inputs not yet uploaded
  let missingReq = $derived(prov ? prov.manual.filter(m => m.required && m.status !== 'valid') : []);
  let optionalMissing = $derived(prov ? prov.manual.filter(m => !m.required && m.status !== 'valid') : []);
</script>

<div class="mb-5 flex items-start justify-between gap-4 flex-wrap">
  <div>
    <h1 class="text-xl">Overview</h1>
    <p class="text-sm text-muted mt-1">The whole demand-forecasting system on one page — data, model, accuracy,
      ordering, and what still needs to be plugged in.</p>
  </div>
  <div class="flex items-center gap-2 flex-none">
    {#if building}
      <span class="pill bg-line/60 text-muted"><span class="w-[7px] h-[7px] rounded-full bg-accent animate-pulse"></span> building snapshot…</span>
    {:else}
      <span class="text-[11px] text-muted hidden md:inline">as of {agoText()}</span>
    {/if}
    <button onclick={loadAll} disabled={syncing}
            class="pill bg-line/60 text-muted hover:text-ink cursor-pointer disabled:opacity-60"
            title="Re-read the latest saved snapshot (instant, no Fabric)">
      <Icon name="refresh" class="w-3 h-3" /> Refresh
    </button>
    <button onclick={syncLive} disabled={syncing}
            class="pill bg-accent/10 text-accent border border-accent/25 cursor-pointer disabled:opacity-60"
            title="Pull fresh numbers from Fabric + local and re-cache (~30s)">
      <Icon name="refresh" class="w-3 h-3 {syncing ? 'animate-spin' : ''}" /> {syncing ? 'syncing…' : 'Sync live'}
    </button>
    {#if loadErr}
      <button onclick={loadAll} class="pill bg-warn/12 text-warn border border-warn/25 cursor-pointer">
        <Icon name="refresh" class="w-3 h-3" /> retry
      </button>
    {/if}
    {#if syncDenied}
      <span class="pill bg-warn/12 text-warn border border-warn/25" title="Ask an ops or admin user to sync — your role can only read the saved snapshot">
        sync needs ops/admin role
      </span>
    {/if}
    <span class="pill {health?.status === 'healthy' ? 'bg-sage/12 text-sage border border-sage/25' : 'bg-line text-muted'}">
      <span class="w-[7px] h-[7px] rounded-full {health?.status === 'healthy' ? 'bg-sage' : 'bg-muted'}"></span>
      {health?.status === 'healthy' ? 'Pipeline healthy' : 'Pipeline —'}
    </span>
    <span class="pill bg-line/60 text-ink font-mono text-[11px]">champion · {champVer}</span>
  </div>
</div>

{#if syncing}
  <div class="card mb-4 !py-3 border border-accent/25 bg-accent/[0.04]">
    <div class="flex items-center justify-between mb-2">
      <span class="text-[13px] font-semibold text-ink inline-flex items-center gap-2">
        <Icon name="refresh" class="w-3.5 h-3.5 text-accent animate-spin" />
        Syncing live from Fabric…
      </span>
      <span class="text-[12px] text-muted mono">{SYNC_STEPS[syncStep]} · {syncElapsed}s</span>
    </div>
    <div class="h-1.5 rounded-full bg-line overflow-hidden">
      <div class="h-full rounded-full bg-accent animate-pulse" style="width:{Math.min(95, 15 + syncElapsed * 3)}%"></div>
    </div>
  </div>
{/if}

<!-- ── hero status strip ───────────────────────────────────────────────── -->
<div class="card mb-4 grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
  <div>
    <div class="font-mono text-[10px] tracking-wide uppercase text-muted">Live model</div>
    <div class="text-lg font-semibold mt-0.5">LightGBM · quantile</div>
    <div class="text-xs text-muted">P50 / P85 / P95 · newsvendor ordering</div>
  </div>
  <div>
    <div class="font-mono text-[10px] tracking-wide uppercase text-muted">Champion error (WMAPE)</div>
    <div class="mono text-2xl font-semibold mt-0.5">{champ ? champ.wmape.toFixed(3) : '—'}</div>
    <div class="text-xs text-muted">lower is better · stretch ≤ 0.321</div>
  </div>
  <div>
    <div class="font-mono text-[10px] tracking-wide uppercase text-muted">Live accuracy</div>
    <div class="mono text-2xl font-semibold mt-0.5 text-sage">
      {acc?.latest_accuracy != null ? pct(acc.latest_accuracy)!.toFixed(1) + '%' : '—'}
    </div>
    <div class="text-xs text-muted inline-flex items-center gap-1">
      {#if acc?.accuracy_change_7d != null}
        <Icon name={acc.accuracy_change_7d >= 0 ? 'arrowUp' : 'trend'} class="w-3 h-3 {acc.accuracy_change_7d >= 0 ? 'text-sage' : 'text-warn'}" />
        {(acc.accuracy_change_7d >= 0 ? '+' : '') + (pct(acc.accuracy_change_7d)!).toFixed(1)}% vs 7d
      {:else}—{/if}
    </div>
  </div>
  <div>
    <div class="font-mono text-[10px] tracking-wide uppercase text-muted">Self-learning verdict</div>
    <div class="mt-1">
      <span class="pill {needsRetrain ? 'bg-warn/12 text-warn border border-warn/25' : 'bg-sage/12 text-sage border border-sage/25'}">
        <Icon name={needsRetrain ? 'rotate' : 'check'} class="w-3 h-3" />
        {learn?.verdict ?? '—'}
      </span>
    </div>
    <div class="text-xs text-muted mt-1">checked {learn?.last_checked ?? '—'}</div>
  </div>
</div>

<!-- ── training & approvals (latest experiment) ────────────────────────── -->
<div class="card mt-4">
  <div class="flex items-center justify-between mb-3">
    <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="zap" class="w-4 h-4 text-accent" /> Training &amp; approvals</div>
    <div class="flex items-center gap-2 text-[11px] text-muted">
      {#if wf}<span class="pill bg-line/60 text-muted">{wf.runs_total} runs total</span>{/if}
      {#if wf?.schedule?.enabled}<span class="pill bg-sage/12 text-sage">auto · {wf.schedule.type} {wf.schedule.times?.join(', ')}</span>{/if}
      <a href="/experiments/run" class="text-accent font-semibold">Run experiment →</a>
    </div>
  </div>

  {#if wf?.awaiting_approval && wf.challenger}
    <div class="rounded-lg border border-warn/30 bg-warn/[0.07] px-3 py-2 mb-3 flex items-center justify-between gap-3 flex-wrap">
      <div class="text-xs">
        <Icon name="info" class="w-3.5 h-3.5 text-warn inline" />
        Challenger <b class="mono">{wf.challenger.version}</b> awaiting approval —
        accuracy {pct(wf.challenger.accuracy)?.toFixed(1)}%
        (Δ {wf.challenger.delta != null ? (wf.challenger.delta >= 0 ? '+' : '') + wf.challenger.delta.toFixed(1) : '—'} vs champion).
      </div>
      <a href="/leaderboard" class="btn btn-sm btn-primary inline-flex">Review &amp; promote <Icon name="arrowRight" class="w-3.5 h-3.5" /></a>
    </div>
  {/if}

  <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
    <div class="rounded-lg bg-line/40 p-3">
      <div class="font-mono text-[10px] uppercase tracking-wide text-muted">Champion (live)</div>
      <div class="mono text-sm font-semibold mt-1 truncate">{wf?.champion?.version ?? '—'}</div>
      <div class="text-xs text-muted">acc {pct(wf?.champion?.accuracy)?.toFixed(1) ?? '—'}% · since {shortTime(wf?.champion?.since)}</div>
    </div>
    <div class="rounded-lg bg-line/40 p-3">
      <div class="font-mono text-[10px] uppercase tracking-wide text-muted">Challenger (shadow)</div>
      <div class="mono text-sm font-semibold mt-1 truncate">{wf?.challenger?.version ?? 'none'}</div>
      <div class="text-xs text-muted">{wf?.challenger ? `acc ${pct(wf.challenger.accuracy)?.toFixed(1)}% · Δ ${wf.challenger.delta ?? '—'}` : 'no candidate in waiting'}</div>
    </div>
    <div class="rounded-lg bg-line/40 p-3">
      <div class="font-mono text-[10px] uppercase tracking-wide text-muted">Last run</div>
      <div class="mono text-sm font-semibold mt-1 truncate">{wf?.last_run?.version ?? '—'}</div>
      <div class="text-xs text-muted">
        {shortTime(wf?.last_run?.at)} ·
        {#if wf?.last_run}<span class={wf.last_run.promoted ? 'text-sage' : 'text-muted'}>{wf.last_run.promoted ? 'promoted' : 'not promoted'}</span>{/if}
      </div>
    </div>
  </div>

  {#if jobs?.length}
    <div class="mt-3 pt-3 border-t border-line">
      <div class="font-mono text-[10px] uppercase tracking-wide text-muted mb-1.5">Recent pipeline jobs</div>
      <div class="space-y-1">
        {#each jobs.slice(0, 5) as j}
          <div class="flex items-center gap-2.5 text-xs">
            <span class="w-1.5 h-1.5 rounded-full flex-none {j.status === 'done' ? 'bg-sage' : j.status === 'error' ? 'bg-warn' : 'bg-accent'}"></span>
            <span class="font-medium text-ink w-20">{j.stage}</span>
            <span class="mono {jobTone(j.status)} w-16">{j.status}</span>
            <span class="text-muted flex-1 truncate">{jobNote(j)}</span>
            <span class="text-muted mono text-[11px]">{shortTime(j.started)}</span>
          </div>
        {/each}
      </div>
      {#if jobs.some(j => j.status === 'error' && j.exit_code === -9)}
        <div class="text-[11px] text-warn mt-1.5">⚠ A recent training was killed out-of-memory (−9) — heavy training runs on Fabric, not in-container.</div>
      {/if}
    </div>
  {/if}
</div>

<!-- ── headline KPIs (live) ────────────────────────────────────────────── -->
<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
  <div class="card">
    <div class="font-mono text-[10px] tracking-wide uppercase text-muted">Order units / day</div>
    <div class="mono text-2xl font-semibold mt-1.5">{orderUnits != null ? nfmt(orderUnits) : '—'}</div>
    <div class="text-xs text-muted mt-1">{networkKs != null ? money(networkKs) + ' · ' : ''}{outlets ?? '—'} outlets</div>
  </div>
  <div class="card">
    <div class="font-mono text-[10px] tracking-wide uppercase text-muted">Beats simple baseline</div>
    <div class="mono text-2xl font-semibold mt-1.5 text-sage">{res ? '+' + res.improvement_pct.toFixed(0) + '%' : '—'}</div>
    <div class="text-xs text-muted mt-1">{res?.stable_all_periods ? 'stable every month' : 'accuracy vs moving-avg'}</div>
  </div>
  <div class="card">
    <div class="font-mono text-[10px] tracking-wide uppercase text-muted">Order-cost saving</div>
    <div class="mono text-2xl font-semibold mt-1.5">{res ? '−' + res.cost_saving_pct.toFixed(0) + '%' : '—'}</div>
    <div class="text-xs text-muted mt-1">vs baseline ordering</div>
  </div>
  <div class="card">
    <div class="font-mono text-[10px] tracking-wide uppercase text-muted">Inputs pending</div>
    <div class="mono text-2xl font-semibold mt-1.5 {pendingGaps ? 'text-warn' : 'text-sage'}">{pendingGaps ?? '—'}</div>
    <div class="text-xs text-muted mt-1">of {gaps?.length ?? '—'} to full power</div>
  </div>
</div>

<!-- ── accuracy trend ──────────────────────────────────────────────────── -->
<div class="card mt-4">
  <div class="flex items-center justify-between mb-2">
    <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="trend" class="w-4 h-4 text-accent" /> Forecast accuracy — last 30 days</div>
    <div class="flex items-center gap-3 text-xs text-muted">
      {#if acc}<span>typical miss ~{acc.units_off?.toFixed(1)} units/series</span>{/if}
      {#if accDaily}<span class="pill bg-line/60 text-muted">source · {accDaily.source}</span>{/if}
    </div>
  </div>
  {#if tr}
    <svg viewBox="0 0 {W} {H}" class="w-full" style="height:150px" preserveAspectRatio="none" aria-label="Accuracy trend">
      <defs>
        <linearGradient id="accfill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#2E8B68" stop-opacity="0.22" />
          <stop offset="100%" stop-color="#2E8B68" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path d={tr.area} fill="url(#accfill)" />
      <path d={tr.line} fill="none" stroke="#2E8B68" stroke-width="2" vector-effect="non-scaling-stroke" />
    </svg>
    <div class="flex items-center justify-between text-[11px] text-muted mt-1">
      <span>{tr.from}</span>
      <span>range {tr.lo.toFixed(0)}–{tr.hi.toFixed(0)}% · latest <b class="text-ink">{tr.last.toFixed(1)}%</b></span>
      <span>{tr.to}</span>
    </div>
  {:else}
    <div class="h-[150px] grid place-items-center text-xs text-muted">loading trend…</div>
  {/if}
</div>

<!-- ── model evolution + accuracy by segment ───────────────────────────── -->
<div class="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
  <div class="card">
    <div class="flex items-center gap-2 font-semibold text-sm mb-3"><Icon name="bars" class="w-4 h-4 text-accent" /> Model evolution</div>
    <div class="space-y-2.5">
      {#each versBars as v}
        <div>
          <div class="flex items-center justify-between text-xs mb-1">
            <span class="font-medium {v.active ? 'text-ink' : 'text-muted'}">{v.name}
              {#if v.active}<span class="pill bg-sage/12 text-sage ml-1 text-[10px]">ACTIVE</span>{/if}</span>
            <span class="mono text-muted">WMAPE {v.wmape.toFixed(3)}</span>
          </div>
          <div class="h-2 rounded-full bg-line overflow-hidden">
            <div class="h-full rounded-full" style="width:{Math.max(6, v.frac * 100)}%;background:{v.active ? '#2E8B68' : '#BE6B41'}"></div>
          </div>
        </div>
      {:else}
        <div class="text-xs text-muted">loading…</div>
      {/each}
    </div>
    <div class="text-[11px] text-muted mt-3">Baseline → point model → quantile champion. Longer bar = lower error.</div>
  </div>

  <div class="card">
    <div class="flex items-center gap-2 font-semibold text-sm mb-3"><Icon name="grid" class="w-4 h-4 text-accent" /> Accuracy by product class</div>
    <div class="space-y-2.5">
      {#each res?.by_class ?? [] as c}
        <div>
          <div class="flex items-center justify-between text-xs mb-1">
            <span class="font-medium text-ink">{c.label} <span class="text-muted">· {c.vol_share_pct?.toFixed(0)}% of volume</span></span>
            <span class="mono text-muted">{c.accuracy_pct.toFixed(1)}%</span>
          </div>
          <div class="h-2 rounded-full bg-line overflow-hidden">
            <div class="h-full rounded-full" style="width:{c.accuracy_pct}%;background:linear-gradient(90deg,#2E8B68,#BE6B41)"></div>
          </div>
        </div>
      {:else}
        <div class="text-xs text-muted">loading…</div>
      {/each}
    </div>
    <div class="text-[11px] text-muted mt-3">Strongest on top sellers (Class-A, 75% of volume) — where accuracy matters most.</div>
  </div>
</div>

<!-- ── service-vs-waste dial + data foundation ─────────────────────────── -->
<div class="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
  <div class="card">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="box" class="w-4 h-4 text-accent" /> Service vs waste dial</div>
      <span class="text-[11px] text-muted">{dial ? 'plan ' + dial.date : ''}</span>
    </div>
    {#if dial}
      <table class="w-full text-xs">
        <thead class="text-muted"><tr class="text-left">
          <th class="font-medium pb-1.5">Service</th><th class="font-medium pb-1.5 text-right">Stockout</th>
          <th class="font-medium pb-1.5 text-right">Waste</th><th class="font-medium pb-1.5 text-right">Fill</th>
          <th class="font-medium pb-1.5 text-right">Cost</th>
        </tr></thead>
        <tbody>
          {#each dial.points as p}
            {@const isMin = p.cost === Math.min(...dial.points.map(q => q.cost))}
            <tr class="border-t border-line/70 {isMin ? 'bg-sage/[0.06]' : ''}">
              <td class="py-1.5 mono">{p.order_quantile}{#if isMin}<span class="pill bg-sage/12 text-sage ml-1.5 text-[10px]">cost-min</span>{/if}</td>
              <td class="py-1.5 text-right mono">{p.stockout_pct.toFixed(0)}%</td>
              <td class="py-1.5 text-right mono">{p.waste_pct.toFixed(0)}%</td>
              <td class="py-1.5 text-right mono">{p.fill_pct.toFixed(0)}%</td>
              <td class="py-1.5 text-right mono">{money(p.cost)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {:else}<div class="text-xs text-muted">loading dial…</div>{/if}
  </div>

  <div class="card">
    <div class="flex items-center gap-2 font-semibold text-sm mb-3"><Icon name="database" class="w-4 h-4 text-accent" /> Data foundation</div>
    <div class="grid grid-cols-2 gap-3">
      <div><div class="mono text-xl font-semibold">{outlets ?? '—'}</div><div class="text-[11px] text-muted">active outlets</div></div>
      <div><div class="mono text-xl font-semibold">{econ?.product_count ? nfmt(econ.product_count) : '—'}</div><div class="text-[11px] text-muted">products priced</div></div>
      <div><div class="mono text-xl font-semibold">P50/85/95</div><div class="text-[11px] text-muted">forecast quantiles</div></div>
      <div><div class="mono text-xl font-semibold">{health?.plans_generated ?? '—'}</div><div class="text-[11px] text-muted">order plans built</div></div>
    </div>
    <div class="mt-3 pt-3 border-t border-line text-[11px] text-muted space-y-1">
      <div class="flex justify-between"><span>Forecast window</span><span class="mono text-ink">{dateRange ?? '—'}</span></div>
      <div class="flex justify-between"><span>Latest plan</span><span class="mono text-ink">{health?.latest_plan_date ?? '—'}</span></div>
      <div class="flex justify-between"><span>Last prediction</span><span class="mono text-ink">{health?.last_prediction_at ?? '—'}</span></div>
    </div>
    {#if readiness != null}
      <div class="mt-3">
        <div class="flex items-center justify-between mb-1">
          <span class="font-mono text-[10px] tracking-wide uppercase text-muted">Data readiness</span>
          <span class="mono text-[11px] text-muted">{readiness}% · {pendingGaps} inputs to full power</span>
        </div>
        <div class="h-2 rounded-full bg-line overflow-hidden">
          <div class="h-full rounded-full" style="width:{Math.max(4, readiness)}%;background:linear-gradient(90deg,#2E8B68,#BE6B41)"></div>
        </div>
      </div>
    {/if}
  </div>
</div>

<!-- ── data: real vs estimated vs missing ──────────────────────────────── -->
<div class="card mt-3">
  <div class="flex items-center justify-between mb-3">
    <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="database" class="w-4 h-4 text-accent" /> Where every input comes from</div>
    {#if prov}<span class="text-[11px] text-muted">{prov.summary.synced_ok}/{prov.summary.synced_total} DB sources ok · {missingReq.length} required input{missingReq.length === 1 ? '' : 's'} missing</span>{/if}
  </div>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
    <!-- REAL -->
    <div class="rounded-lg border border-sage/25 bg-sage/[0.05] p-3">
      <div class="flex items-center gap-1.5 text-xs font-semibold text-sage mb-2"><Icon name="check" class="w-3.5 h-3.5" /> Real · from database</div>
      <div class="space-y-1">
        {#each (prov?.synced ?? []).slice(0, 8) as s}
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-ink truncate pr-2">{s.name}</span>
            <span class="text-muted mono flex-none">{nfmt(s.rows)}</span>
          </div>
        {:else}
          <div class="text-[11px] text-muted">loading…</div>
        {/each}
      </div>
      {#if prov}<div class="text-[11px] text-muted mt-2 pt-2 border-t border-sage/20">Last sync {prov.synced[0]?.last_sync ?? '—'}</div>{/if}
    </div>

    <!-- ESTIMATED -->
    <div class="rounded-lg border border-warn/25 bg-warn/[0.05] p-3">
      <div class="flex items-center gap-1.5 text-xs font-semibold text-warn mb-2"><Icon name="info" class="w-3.5 h-3.5" /> Estimated · placeholder</div>
      <div class="space-y-2">
        {#each estimated as e}
          <div>
            <div class="text-[11.5px] font-medium text-ink">{e.label}</div>
            <div class="text-[11px] text-muted leading-snug">{e.note}</div>
          </div>
        {/each}
      </div>
      <div class="text-[11px] text-muted mt-2 pt-2 border-t border-warn/20">Present, but not ground-truth — numbers move once real values load.</div>
    </div>

    <!-- MISSING -->
    <div class="rounded-lg border border-line p-3">
      <div class="flex items-center gap-1.5 text-xs font-semibold text-muted mb-2"><Icon name="x" class="w-3.5 h-3.5" /> Missing · needs upload</div>
      <div class="space-y-1.5">
        {#each missingReq as m}
          <a href="/data" class="flex items-center justify-between text-[11.5px] group">
            <span class="text-ink group-hover:text-accent">{m.name}</span>
            <span class="pill bg-warn/12 text-warn text-[10px]">required</span>
          </a>
        {/each}
        {#each optionalMissing as m}
          <a href="/data" class="flex items-center justify-between text-[11px] group">
            <span class="text-muted group-hover:text-accent">{m.name}</span>
            <span class="pill bg-line/60 text-muted text-[10px]">optional</span>
          </a>
        {:else}
          {#if !missingReq.length}<div class="text-[11px] text-muted">nothing outstanding</div>{/if}
        {/each}
      </div>
      <a href="/data" class="text-[11px] text-accent font-semibold mt-2 inline-block">Upload inputs →</a>
    </div>
  </div>
</div>

<!-- ── the unlock: economics still uniform ─────────────────────────────── -->
{#if econ?.available && econ.is_uniform}
  <div class="card mt-3 border-l-4" style="border-left-color:#BE6B41">
    <div class="flex items-start gap-3">
      <Icon name="zap" class="w-5 h-5 text-accent flex-none mt-0.5" />
      <div class="min-w-0">
        <div class="font-semibold text-sm">Biggest unlock — ordering runs on demo economics</div>
        <p class="text-xs text-muted mt-1 leading-relaxed">
          All {nfmt(econ.product_count ?? 0)} products share one margin (GM 35%) and one shelf life (1 day),
          so the newsvendor orders every SKU at the <b>same demand percentile</b> — no difference between
          high-margin fresh pastries and long-shelf goods. Critical-ratio spread is
          <b class="mono">{(econ.critical_ratio_spread ?? 0).toFixed(2)}</b>. Load real per-product gross
          margin + shelf life to switch on differentiated ordering.
        </p>
        <a href="/data" class="btn btn-primary btn-sm mt-2.5 inline-flex">Add product economics <Icon name="arrowRight" class="w-3.5 h-3.5" /></a>
      </div>
    </div>
  </div>
{/if}

<!-- ── data gaps + drift watch ─────────────────────────────────────────── -->
<div class="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
  <div class="card">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="upload" class="w-4 h-4 text-accent" /> Inputs to full power</div>
      <a href="/data" class="text-[11px] text-accent font-semibold">Manage →</a>
    </div>
    <div class="space-y-1.5">
      {#each gaps ?? [] as g}
        {@const done = g.status === 'accepted' || g.status === 'done'}
        <div class="flex items-center gap-2.5 text-xs">
          <Icon name={done ? 'check' : 'x'} class="w-3.5 h-3.5 flex-none {done ? 'text-sage' : 'text-muted'}" />
          <span class="flex-1 {done ? 'text-muted line-through' : 'text-ink'}">{g.label}</span>
          <span class="text-[11px] text-muted">{g.owner}</span>
          {#if g.has_template && !done}<span class="pill bg-line/60 text-muted text-[10px]">template</span>{/if}
        </div>
      {:else}
        <div class="text-xs text-muted">loading inputs…</div>
      {/each}
    </div>
  </div>

  <div class="card">
    <div class="flex items-center gap-2 font-semibold text-sm mb-3"><Icon name="activity" class="w-4 h-4 text-accent" /> Drift watch</div>
    <div class="space-y-2">
      {#each learn?.drift_watch ?? [] as d}
        <div class="flex items-start gap-2.5 text-xs">
          <span class="w-2 h-2 rounded-full flex-none mt-1 {d.severity === 'ok' ? 'bg-sage' : 'bg-warn'}"></span>
          <div class="min-w-0">
            <div class="font-medium text-ink">{d.signal}
              <span class="pill ml-1 text-[10px] {d.severity === 'ok' ? 'bg-sage/12 text-sage' : 'bg-warn/12 text-warn'}">{d.severity}</span></div>
            <div class="text-muted">{d.detail}</div>
          </div>
        </div>
      {:else}
        <div class="text-xs text-muted">loading signals…</div>
      {/each}
    </div>
    {#if learn}
      <div class="text-[11px] text-muted mt-3 pt-3 border-t border-line">
        Data-signal shifts flag on their own; the retrain trigger is <b>accuracy</b> drift. Live
        {pct(learn.live_accuracy_pct)?.toFixed(1)}% · recent {pct(learn.recent_accuracy_pct)?.toFixed(1)}% ({learn.accuracy_trend}).
      </div>
    {/if}
  </div>
</div>

<!-- ── top outlets ─────────────────────────────────────────────────────── -->
{#if topOutlets.length}
  <div class="card mt-3">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="star" class="w-4 h-4 text-accent" /> Top outlets by value / day</div>
      <a href="/network" class="text-[11px] text-accent font-semibold">Forecast dashboard →</a>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-3 gap-2.5">
      {#each topOutlets as o}
        <a href="/network/{o.outlet_id}" class="card-link !p-3">
          <div class="text-sm font-semibold truncate">{o.outlet_name}</div>
          <div class="flex items-center justify-between mt-1 text-xs text-muted">
            <span class="mono">{money(o.value_ks)}</span>
            <span>{nfmt(o.order_units)} u · {o.sku_count} SKU</span>
          </div>
        </a>
      {/each}
    </div>
  </div>
{/if}

<!-- ── quick nav ───────────────────────────────────────────────────────── -->
<div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-3">
  <a href="/accuracy" class="card-link">
    <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="trend" class="w-4 h-4 text-accent" /> Accuracy</div>
    <div class="text-xs text-muted mt-1">How close the forecast came, day by day.</div>
  </a>
  <a href="/leaderboard" class="card-link">
    <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="bars" class="w-4 h-4 text-accent" /> Leaderboard</div>
    <div class="text-xs text-muted mt-1">Compare models, promote or roll back.</div>
  </a>
  <a href="/ordering" class="card-link">
    <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="box" class="w-4 h-4 text-accent" /> Smart Ordering</div>
    <div class="text-xs text-muted mt-1">Tomorrow's picklist across every outlet.</div>
  </a>
  <a href="/learning" class="card-link">
    <div class="flex items-center gap-2 font-semibold text-sm"><Icon name="activity" class="w-4 h-4 text-accent" /> Monitoring</div>
    <div class="text-xs text-muted mt-1">Drift, retraining, pipeline health.</div>
  </a>
</div>
