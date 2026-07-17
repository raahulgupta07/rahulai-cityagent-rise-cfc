<script lang="ts">
  import { onMount } from 'svelte';
  import { edaApi, type Eda } from '$lib/api/eda';
  import Icon from '$lib/Icon.svelte';

  let d = $state<Eda | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);

  onMount(load);
  async function load() {
    loading = true; error = null;
    try { d = await edaApi.get(); } catch (e) { error = String(e); } finally { loading = false; }
  }

  function fmt(n: number): string {
    if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(0) + 'k';
    return String(Math.round(n));
  }
  function fmtDay(k?: string): string {
    // DayKey is YYYYMMDD -> YYYY-MM-DD
    if (!k) return '—';
    return k.length === 8 ? `${k.slice(0, 4)}-${k.slice(4, 6)}-${k.slice(6, 8)}` : k;
  }
  function fmtMonth(ym: string): string {
    // YYYYMM -> Mon 'YY
    const M = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    if (ym.length !== 6) return ym;
    return `${M[Number(ym.slice(4, 6)) - 1] ?? ym.slice(4, 6)} ${ym.slice(2, 4)}`;
  }
  const w = (v: number, max: number) => `${Math.max(2, (v / max) * 100)}%`;
</script>

<div class="space-y-6">
  <!-- header -->
  <div class="flex items-end justify-between gap-4 flex-wrap">
    <div>
      <h1 class="font-display text-2xl text-ink mb-1">Data Explorer — EDA</h1>
      <p class="text-sm text-muted max-w-2xl">
        A live look at the sales history the forecast learns from — recomputed on every visit,
        so it always reflects the latest sync.
      </p>
    </div>
    <div class="flex items-center gap-3">
      {#if d}
        <span class="text-xs px-2.5 py-1 rounded-full bg-line text-muted font-medium inline-flex items-center gap-1.5">
          <Icon name="database" class="w-3.5 h-3.5" /> fresh {d.freshness}
        </span>
      {/if}
      <button class="btn-subtle btn-sm" onclick={load} disabled={loading} aria-label="Recompute">
        <Icon name="refresh" class="w-3.5 h-3.5 {loading ? 'animate-spin' : ''}" /> Recompute
      </button>
    </div>
  </div>

  {#if error}
    <div class="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
  {/if}

  {#if loading || !d}
    <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
      {#each Array(5) as _}
        <div class="card"><div class="h-4 w-2/3 rounded bg-line animate-pulse"></div><div class="h-6 mt-3 rounded bg-line animate-pulse"></div></div>
      {/each}
    </div>
  {:else}

  <!-- summary tiles -->
  <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
    {#each [
      ['Rows', fmt(d.summary.rows)],
      ['Net units', fmt(d.summary.net_units)],
      ['Revenue ₭', fmt(d.summary.revenue)],
      ['Outlets', String(d.summary.branches)],
      ['Products', String(d.summary.products)],
    ] as [k, v]}
      <div class="card">
        <div class="font-mono text-[10px] uppercase tracking-wide text-muted">{k}</div>
        <div class="mono text-xl font-semibold mt-1 tabular-nums">{v}</div>
      </div>
    {/each}
  </div>

  <!-- date range strip -->
  <div class="card !py-4 flex items-center gap-3 flex-wrap text-sm">
    <span class="text-muted">Date range</span>
    <span class="font-mono font-semibold text-ink">{fmtDay(d.summary.first_day)}</span>
    <Icon name="arrowRight" class="w-4 h-4 text-muted" />
    <span class="font-mono font-semibold text-ink">{fmtDay(d.summary.latest_day)}</span>
    <span class="text-muted ml-auto">daily grain · zero-filled per active series</span>
  </div>

  <div class="grid md:grid-cols-2 gap-6">
    <!-- by day of week -->
    <div class="card">
      <h3 class="text-base mb-3">Units by day of week</h3>
      <div class="flex items-end gap-2 h-40">
        {#each d.by_dow as x}
          {@const mx = Math.max(...d.by_dow.map(v => v.units))}
          <div class="flex-1 flex flex-col items-center justify-end gap-1 h-full">
            <div class="w-full rounded-t transition-colors {x.dow === 'Sun' ? 'bg-accent' : 'bg-sage'}"
                 style="height:{(x.units / mx) * 100}%" title="{x.dow}: {fmt(x.units)}"></div>
            <span class="text-[10px] font-mono text-muted">{x.dow}</span>
          </div>
        {/each}
      </div>
    </div>

    <!-- by month -->
    <div class="card">
      <h3 class="text-base mb-3">Units by month <span class="text-xs text-muted font-normal">· last 12</span></h3>
      <div class="flex items-end gap-1.5 h-40">
        {#each d.by_month as m}
          {@const mx = Math.max(...d.by_month.map(v => v.units))}
          <div class="flex-1 flex flex-col items-center justify-end gap-1 h-full">
            <div class="w-full rounded-t bg-accent/80" style="height:{(m.units / mx) * 100}%" title="{fmtMonth(m.ym)}: {fmt(m.units)}"></div>
            <span class="text-[9px] font-mono text-muted whitespace-nowrap">{fmtMonth(m.ym)}</span>
          </div>
        {/each}
      </div>
    </div>
  </div>

  <div class="grid md:grid-cols-2 gap-6">
    <!-- top products -->
    <div class="card">
      <h3 class="text-base mb-3">Top products</h3>
      {#if d.top_products.length === 0}
        <p class="text-sm text-muted">No product names available.</p>
      {:else}
        <div class="space-y-1.5">
          {#each d.top_products as p}
            {@const mx = d.top_products[0]?.units || 1}
            <div class="flex items-center gap-3">
              <span class="w-40 text-xs truncate" title={p.name}>{p.name}</span>
              <div class="flex-1 h-2.5 rounded-full bg-line overflow-hidden">
                <div class="h-full rounded-full bg-accent" style="width:{w(p.units, mx)}"></div>
              </div>
              <span class="w-12 text-right text-xs font-mono text-muted tabular-nums">{fmt(p.units)}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- top outlets -->
    <div class="card">
      <h3 class="text-base mb-3">Top outlets</h3>
      {#if d.top_branches.length === 0}
        <p class="text-sm text-muted">No outlet names available.</p>
      {:else}
        <div class="space-y-1.5">
          {#each d.top_branches as b}
            {@const mx = d.top_branches[0]?.units || 1}
            <div class="flex items-center gap-3">
              <span class="w-40 text-xs truncate" title={b.name}>{b.name}</span>
              <div class="flex-1 h-2.5 rounded-full bg-line overflow-hidden">
                <div class="h-full rounded-full bg-sage" style="width:{w(b.units, mx)}"></div>
              </div>
              <span class="w-12 text-right text-xs font-mono text-muted tabular-nums">{fmt(b.units)}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>

  {/if}
</div>
