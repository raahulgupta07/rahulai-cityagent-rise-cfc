<script lang="ts">
  import { onMount } from 'svelte';
  import { accuracyApi, type AccuracyDaily, type AccuracySummary } from '$lib/api/accuracy';
  import ExplainButton from '$lib/ExplainButton.svelte';
  import Icon from '$lib/Icon.svelte';

  let summary = $state<AccuracySummary | null>(null);
  let daily   = $state<AccuracyDaily | null>(null);
  let loading = $state(true);
  let error   = $state<string | null>(null);

  // Simple (everyone) vs Expert (data-science) view — mirrors the Leaderboard.
  let mode = $state<'simple' | 'expert'>('simple');
  onMount(() => {
    try { const m = localStorage.getItem('acc_mode'); if (m === 'expert' || m === 'simple') mode = m; } catch {}
  });
  function setMode(m: 'simple' | 'expert') { mode = m; try { localStorage.setItem('acc_mode', m); } catch {} }

  // chart
  let canvasEl = $state<HTMLCanvasElement | null>(null);
  let chartInst: any = null;

  onMount(load);
  // Backend returns accuracy as a 0-1 FRACTION (1 - WMAPE) and change_7d in fraction
  // points — normalise to 0-100 % once at load so grade()/chart/table all read %.
  const pc = (x: number | null | undefined): number | null =>
    x == null ? null : (x <= 1.5 ? x * 100 : x);
  async function load() {
    loading = true; error = null;
    try {
      const [s, d] = await Promise.all([accuracyApi.getSummary(), accuracyApi.getDaily(30)]);
      if (s) {
        s.latest_accuracy    = pc(s.latest_accuracy);
        s.accuracy_7d_avg    = pc(s.accuracy_7d_avg);
        s.accuracy_change_7d = s.accuracy_change_7d == null ? null : s.accuracy_change_7d * 100;
      }
      if (d) d.rows = d.rows.map(r => ({ ...r, accuracy: r.accuracy == null ? r.accuracy : (r.accuracy <= 1.5 ? r.accuracy * 100 : r.accuracy) }));
      summary = s; daily = d;
    } catch (e) { error = String(e); } finally { loading = false; }
  }

  // ── plain-language grade (same spirit as the Leaderboard) ────────────────────
  function grade(acc: number | null): { g: string; tone: string; say: string } {
    if (acc == null) return { g: '—', tone: 'text-muted', say: 'not scored yet' };
    if (acc >= 70) return { g: 'A', tone: 'text-sage', say: 'excellent — trust it for ordering' };
    if (acc >= 60) return { g: 'B', tone: 'text-sage', say: 'good — reliable for daily orders' };
    if (acc >= 50) return { g: 'C', tone: 'text-warn', say: 'okay — usable, watch the big days' };
    return { g: 'D', tone: 'text-warn', say: 'weak — use with care' };
  }
  let cg = $derived(grade(summary?.latest_accuracy ?? null));

  // Backend emits drift as a BOOLEAN (true = drifting); tolerate strings for forward-compat.
  function driftTone(d: boolean | string | null): string {
    if (!d) return 'bg-line text-muted';
    if (typeof d !== 'string') return 'bg-warn/15 text-warn';
    const s = d.toLowerCase();
    if (s.includes('drift')) return 'bg-warn/15 text-warn';
    if (s.includes('watch')) return 'bg-warn/10 text-warn';
    return 'bg-sage/15 text-sage';
  }
  function driftLabel(d: boolean | string | null): string {
    return typeof d === 'string' ? d : 'detected';
  }
  function fmt1(v: number | null | undefined) { return v == null ? '—' : v.toFixed(1); }
  function fmt0(v: number | null | undefined) { return v == null ? '—' : Math.round(v).toLocaleString(); }

  // ── daily trend chart (matches the Model Evidence / Results chart styling) ────
  $effect(() => {
    const rows = daily?.rows ?? [];
    if (!canvasEl || rows.length === 0) return;
    (async () => {
      const { Chart, registerables } = await import('chart.js');
      Chart.register(...registerables);
      if (chartInst) { chartInst.destroy(); chartInst = null; }
      chartInst = new Chart(canvasEl!, {
        type: 'line',
        data: {
          labels: rows.map(r => r.dt.slice(5)),   // MM-DD
          datasets: [{
            label: 'Daily accuracy %',
            data: rows.map(r => r.accuracy),
            borderColor: '#C96442',
            backgroundColor: 'rgba(201,100,66,.08)',
            tension: 0.35,
            fill: true,
            pointRadius: 3,
            pointBackgroundColor: '#C96442',
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx: any) => {
                  const r = rows[ctx.dataIndex];
                  return [`Accuracy: ${r.accuracy.toFixed(1)}%`, `Off by ~${r.units_off.toFixed(1)} units · ${r.n_rows.toLocaleString()} series`];
                },
              },
            },
          },
          scales: {
            y: { min: 0, max: 100, ticks: { callback: (v: any) => v + '%', color: '#8A8073' }, grid: { color: '#E7E0D5' } },
            x: { ticks: { color: '#8A8073', maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }, grid: { color: '#E7E0D5' } },
          },
        },
      });
    })();
  });
</script>

<div class="space-y-6">
  <!-- header -->
  <div class="flex items-end justify-between gap-4 flex-wrap">
    <div>
      <h1 class="font-display text-2xl text-ink mb-1">Accuracy</h1>
      <p class="text-sm text-muted max-w-2xl">
        {#if mode === 'simple'}
          How close yesterday's forecast came to what actually sold — in plain terms.
        {:else}
          Daily forecast-vs-actual, scored on real outcomes the model never saw.
        {/if}
      </p>
    </div>
    <div class="flex items-center gap-3">
      <div class="inline-flex rounded-lg border border-line overflow-hidden text-xs font-medium">
        <button class="px-3 py-1.5 transition-colors {mode === 'simple' ? 'bg-accent text-white' : 'bg-surface text-muted hover:bg-bg'}"
                onclick={() => setMode('simple')}>Simple</button>
        <button class="px-3 py-1.5 transition-colors {mode === 'expert' ? 'bg-accent text-white' : 'bg-surface text-muted hover:bg-bg'}"
                onclick={() => setMode('expert')}>Expert</button>
      </div>
      <button class="btn-subtle btn-sm" onclick={load} disabled={loading} aria-label="Refresh accuracy">
        <Icon name="refresh" class="w-3.5 h-3.5 {loading ? 'animate-spin' : ''}" /> Refresh
      </button>
    </div>
  </div>

  {#if error}
    <div class="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
  {/if}

  {#if loading}
    <div class="card !p-6"><div class="h-6 w-1/2 rounded bg-line animate-pulse"></div></div>
  {:else if !summary || summary.latest_accuracy == null}
    <div class="card !p-6 text-sm text-muted">
      No accuracy scored yet. Once the forecast has been compared against real sales, today's grade shows here.
    </div>
  {:else}
    <!-- ── SIMPLE hero ── -->
    <div class="card !p-6">
      <div class="flex items-center justify-between gap-3 mb-3">
        <div class="text-[11px] font-bold text-muted uppercase tracking-wide">Yesterday's accuracy</div>
        {#if summary.drift}
          <span class="text-xs px-2.5 py-1 rounded-full font-medium {driftTone(summary.drift)}">drift · {driftLabel(summary.drift)}</span>
        {/if}
      </div>
      <div class="flex items-center gap-5 flex-wrap">
        <div class="flex items-center justify-center w-16 h-16 rounded-2xl bg-sage/10 {cg.tone} font-display text-4xl font-bold flex-none">{cg.g}</div>
        <div class="flex items-baseline gap-2">
          <span class="font-display text-5xl font-bold text-ink tabular-nums">{fmt1(summary.latest_accuracy)}%</span>
          {#if summary.accuracy_change_7d != null}
            {@const up = summary.accuracy_change_7d >= 0}
            <span class="text-sm font-semibold tabular-nums {up ? 'text-sage' : 'text-warn'}">
              {up ? '↑' : '↓'} {Math.abs(summary.accuracy_change_7d).toFixed(1)} pts vs 7-day
            </span>
          {/if}
        </div>
        <div class="flex-1 min-w-[200px]">
          <div class="text-base font-semibold text-ink">Grade {cg.g} · {cg.say}</div>
          <div class="text-sm text-muted mt-0.5">
            Typical daily miss ≈ <strong>{fmt0(summary.units_off)} units</strong> per store
            {#if summary.accuracy_7d_avg != null}· 7-day average <strong>{fmt1(summary.accuracy_7d_avg)}%</strong>{/if}
          </div>
        </div>
        <ExplainButton context={{ 'latest accuracy': summary.latest_accuracy, 'typical daily miss (units)': summary.units_off }} />
      </div>
      {#if summary.source}
        <div class="text-[11px] text-muted mt-4 font-mono">source · {summary.source}</div>
      {/if}
    </div>

    <!-- ── daily trend ── -->
    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <div>
          <h2 class="text-base font-semibold">Forecast vs actual — last 30 days</h2>
          <p class="text-xs text-muted">Each point is one day's accuracy, scored after the sales came in.</p>
        </div>
      </div>
      {#if (daily?.rows.length ?? 0) === 0}
        <div class="h-[260px] flex items-center justify-center text-sm text-muted">No daily scores yet.</div>
      {:else}
        <div class="relative" style="height:260px"><canvas bind:this={canvasEl}></canvas></div>
      {/if}
    </div>

    <!-- ── EXPERT daily table ── -->
    {#if mode === 'expert'}
      <div class="rounded-2xl border border-line bg-surface shadow-soft overflow-hidden">
        <div class="px-4 py-3 border-b border-line text-sm font-semibold">Daily scores</div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-line bg-bg text-xs text-muted">
                <th class="text-left px-4 py-2.5 font-medium">Date</th>
                <th class="text-right px-4 py-2.5 font-medium">Accuracy</th>
                <th class="text-right px-4 py-2.5 font-medium">Units off</th>
                <th class="text-right px-4 py-2.5 font-medium">WMAPE</th>
                <th class="text-right px-4 py-2.5 font-medium">Series</th>
              </tr>
            </thead>
            <tbody>
              {#each [...(daily?.rows ?? [])].reverse() as r}
                <tr class="border-b border-line/60 last:border-0 hover:bg-bg/60 transition-colors">
                  <td class="px-4 py-2.5 font-mono text-xs text-ink">{r.dt}</td>
                  <td class="px-4 py-2.5 text-right tabular-nums font-semibold">{r.accuracy.toFixed(1)}%</td>
                  <td class="px-4 py-2.5 text-right tabular-nums text-muted">{r.units_off.toFixed(1)}</td>
                  <td class="px-4 py-2.5 text-right tabular-nums text-muted font-mono text-xs">{r.wmape.toFixed(3)}</td>
                  <td class="px-4 py-2.5 text-right tabular-nums text-muted">{r.n_rows.toLocaleString()}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {:else}
      <button class="text-sm text-accent font-medium hover:underline inline-flex items-center gap-1"
              onclick={() => setMode('expert')}>
        <Icon name="bars" class="w-4 h-4" /> Show the daily numbers
      </button>
    {/if}
  {/if}
</div>
