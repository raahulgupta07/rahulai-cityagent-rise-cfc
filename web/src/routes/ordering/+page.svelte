<script lang="ts">
  import { onMount } from 'svelte';
  import { orderApi, type PicklistRow, type PicklistResponse, type DialPoint } from '$lib/api/order';
  import { api } from '$lib/api';
  import Icon from '$lib/Icon.svelte';

  // ── state ───────────────────────────────────────────────────────────────────
  let availDates   = $state<string[]>([]);
  let selectedDate = $state('');
  let data         = $state<PicklistResponse | null>(null);
  let loading      = $state(true);
  let error        = $state('');

  // dial
  let dialLoading  = $state(false);
  let dialPoints   = $state<DialPoint[]>([]);
  let dialLevel    = $state(50);   // current slider value
  let activePoint  = $derived(
    dialPoints.find(p => p.service_level === snap(dialLevel)) ?? dialPoints[1] ?? null
  );

  // search
  let search = $state('');

  // chart
  let chartCanvas = $state<HTMLCanvasElement | null>(null);
  let chartInst:   any = null;

  // ── derived ─────────────────────────────────────────────────────────────────
  let visible = $derived(
    (data?.rows ?? []).filter(r =>
      r.product_name.toLowerCase().includes(search.toLowerCase())
    )
  );

  // ── helpers ─────────────────────────────────────────────────────────────────
  function snap(v: number): number {
    const levels = [30, 50, 70, 85, 95];
    return levels.reduce((prev, cur) => Math.abs(cur - v) < Math.abs(prev - v) ? cur : prev);
  }

  function fmtK(v: number): string {
    if (v >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + 'B';
    if (v >= 1_000_000)     return (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000)         return (v / 1_000).toFixed(0) + 'K';
    return v.toFixed(0);
  }

  function trendIcon(t?: string): string {
    if (t === 'up')   return '↑';
    if (t === 'down') return '↓';
    return '→';
  }

  function trendClass(t?: string): string {
    if (t === 'up')   return 'text-sage';
    if (t === 'down') return 'text-accent';
    return 'text-muted';
  }

  // ── chart rendering ──────────────────────────────────────────────────────────
  async function renderChart(points: DialPoint[]) {
    if (!chartCanvas || !points.length) return;

    // dynamic import Chart.js (bundled via npm in the project)
    const { Chart, registerables } = await import('chart.js');
    Chart.register(...registerables);

    if (chartInst) { chartInst.destroy(); chartInst = null; }

    const labels   = points.map(p => `${p.service_level}%`);
    const costs    = points.map(p => p.cost / 1_000_000);   // ₭M
    const stockout = points.map(p => p.stockout_pct);
    const waste    = points.map(p => p.waste_pct);

    chartInst = new Chart(chartCanvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            type: 'line' as const,
            label: 'Cost (₭M)',
            data: costs,
            borderColor: '#C96442',
            backgroundColor: 'transparent',
            yAxisID: 'y2',
            tension: 0.35,
            pointRadius: 4,
            pointBackgroundColor: '#C96442',
          },
          {
            type: 'bar' as const,
            label: 'Stockout %',
            data: stockout,
            backgroundColor: '#C96442aa',
            yAxisID: 'y1',
          },
          {
            type: 'bar' as const,
            label: 'Waste %',
            data: waste,
            backgroundColor: '#6F8F6Aaa',
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { font: { family: 'Georgia', size: 11 }, color: '#8A8073' } },
          tooltip: {
            callbacks: {
              label: (ctx: any) => {
                const val = ctx.parsed.y;
                if (ctx.dataset.label === 'Cost (₭M)') return `Cost: ₭${val.toFixed(1)}M`;
                return `${ctx.dataset.label}: ${val.toFixed(1)}%`;
              }
            }
          }
        },
        scales: {
          y1: {
            type: 'linear', position: 'left',
            title: { display: true, text: '%', color: '#8A8073', font: { size: 10 } },
            ticks: { color: '#8A8073' }, grid: { color: '#E7E0D5' },
          },
          y2: {
            type: 'linear', position: 'right',
            title: { display: true, text: '₭M', color: '#C96442', font: { size: 10 } },
            ticks: { color: '#C96442' }, grid: { drawOnChartArea: false },
          },
          x: { ticks: { color: '#8A8073' }, grid: { color: '#E7E0D5' } },
        },
      },
    });
  }

  // ── data loading ─────────────────────────────────────────────────────────────
  $effect(() => {
    api.dates()
      .then(d => {
        availDates   = d;
        selectedDate = d.at(-1) ?? '';
      })
      .catch(e => { error = String(e); loading = false; });
  });

  $effect(() => {
    if (!selectedDate) return;
    loading = true; error = '';
    orderApi.picklist(selectedDate)
      .then(d  => { data = d; })
      .catch(e => { error = String(e); })
      .finally(() => { loading = false; });

    // load dial data for this date
    dialLoading = true;
    orderApi.dial(selectedDate)
      .then(d => { dialPoints = d.points; })
      .catch(() => { dialPoints = []; })
      .finally(() => { dialLoading = false; });
  });

  // re-render chart when dial data or canvas changes
  $effect(() => {
    if (dialPoints.length && chartCanvas) renderChart(dialPoints);
  });
</script>

<!-- ── header ────────────────────────────────────────────────────────────────── -->
<div class="flex items-center justify-between mb-6">
  <div>
    <h1 class="text-3xl mb-1">Ordering</h1>
    <p class="text-muted text-sm">Warehouse picklist · central-kitchen production quantities</p>
  </div>

  <div class="flex items-center gap-3">
    <a href="/ordering/warehouse" class="pill pill-ghost text-xs">By warehouse</a>

    <!-- downloads -->
    {#if selectedDate}
      <a href={orderApi.picklistCsvUrl(selectedDate)} download class="pill pill-ghost text-xs">
        <Icon name="download" class="w-3.5 h-3.5" /> CSV (product roll-up)</a>
      <a href={`/api/order/export.xlsx?date=${selectedDate}`} download class="pill pill-accent text-xs">
        <Icon name="download" class="w-3.5 h-3.5" /> Excel — by outlet × SKU</a>
    {/if}

    <!-- stub: send to ops -->
    <button
      class="pill pill-accent text-xs"
      aria-label="Send this picklist to Ops"
      onclick={() => alert('Send to Ops — integration stub. Wire to your messaging/ERP system.')}
    >
      <Icon name="send" class="w-3.5 h-3.5" /> Send to Ops
    </button>

    <!-- date picker -->
    <select
      bind:value={selectedDate}
      aria-label="Plan date"
      class="bg-surface border border-line rounded-xl px-3 py-2 text-sm text-ink focus:outline-none focus:ring-1 focus:ring-accent hover:border-muted transition-colors"
    >
      {#each [...availDates].reverse() as d}
        <option value={d}>{d}</option>
      {/each}
    </select>
  </div>
</div>

<!-- ── totals pills ───────────────────────────────────────────────────────────── -->
{#if data}
  <div class="flex gap-3 mb-6 flex-wrap">
    <span class="pill pill-ghost">
      <span class="text-muted text-xs">Products</span>
      <strong>{data.totals.products.toLocaleString()}</strong>
    </span>
    <span class="pill pill-ghost">
      <span class="text-muted text-xs">Total units</span>
      <strong>{data.totals.order_units.toLocaleString()}</strong>
    </span>
    <span class="pill pill-ghost">
      <span class="text-muted text-xs">₭ Value</span>
      <strong>₭{fmtK(data.totals.value_ks)}</strong>
    </span>
  </div>
{/if}

<!-- ── two-column: dial + chart ──────────────────────────────────────────────── -->
<div class="grid grid-cols-[1fr_1.8fr] gap-5 mb-6">

  <!-- SERVICE DIAL card -->
  <div class="card flex flex-col gap-4">
    <div>
      <h2 class="text-base font-semibold mb-0.5">Service Dial</h2>
      <p class="text-xs text-muted">Drag to explore stockout vs waste tradeoff</p>
    </div>

    <!-- slider -->
    <div class="flex flex-col gap-1">
      <div class="flex justify-between text-xs text-muted">
        <span>30%</span><span>Service level</span><span>95%</span>
      </div>
      <input
        type="range" min="30" max="95" step="1"
        bind:value={dialLevel}
        class="w-full accent-accent"
      />
      <div class="text-center font-display text-2xl font-bold text-accent">
        {snap(dialLevel)}%
      </div>
    </div>

    <!-- KPI mini-cards -->
    {#if activePoint}
      <div class="grid grid-cols-2 gap-2 text-sm">
        <div class="bg-bg rounded-xl p-3 text-center">
          <div class="text-muted text-xs mb-1">Stockout</div>
          <div class="font-semibold text-accent">{activePoint.stockout_pct.toFixed(1)}%</div>
        </div>
        <div class="bg-bg rounded-xl p-3 text-center">
          <div class="text-muted text-xs mb-1">Waste</div>
          <div class="font-semibold text-sage">{activePoint.waste_pct.toFixed(1)}%</div>
        </div>
        <div class="bg-bg rounded-xl p-3 text-center">
          <div class="text-muted text-xs mb-1">Fill rate</div>
          <div class="font-semibold">{activePoint.fill_pct.toFixed(1)}%</div>
        </div>
        <div class="bg-bg rounded-xl p-3 text-center">
          <div class="text-muted text-xs mb-1">Cost</div>
          <div class="font-semibold">₭{fmtK(activePoint.cost)}</div>
        </div>
      </div>
      <p class="text-xs text-muted">
        GM 35% placeholder · same-day spoilage. Edit <code class="text-accent">data/product_econ.csv</code> for real margins.
      </p>
    {:else if dialLoading}
      <div class="text-muted text-sm animate-pulse">Loading dial…</div>
    {/if}
  </div>

  <!-- CHART card -->
  <div class="card flex flex-col gap-3">
    <div>
      <h2 class="text-base font-semibold mb-0.5">Cost · Stockout · Waste by Service Level</h2>
      <p class="text-xs text-muted">Line = total cost (₭M right axis) · bars = % rates (left axis)</p>
    </div>
    {#if dialLoading}
      <div class="flex-1 flex items-center justify-center text-muted animate-pulse text-sm">Loading chart…</div>
    {:else if dialPoints.length === 0}
      <div class="flex-1 flex items-center justify-center text-muted text-sm">No dial data for this date.</div>
    {:else}
      <div class="relative" style="height:220px">
        <canvas bind:this={chartCanvas}></canvas>
      </div>
    {/if}
  </div>

</div>

<!-- ── search ─────────────────────────────────────────────────────────────────── -->
<div class="mb-4">
  <input
    type="text"
    placeholder="Search products…"
    bind:value={search}
    class="w-full max-w-xs bg-surface border border-line rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
  />
</div>

<!-- ── picklist table ─────────────────────────────────────────────────────────── -->
{#if error}
  <div class="card text-accent">{error}</div>
{:else if loading}
  <div class="card text-muted animate-pulse">Loading picklist…</div>
{:else if data}
  <div class="card p-0 overflow-hidden">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-muted">
          <th class="px-4 py-3 text-left font-medium">Product</th>
          <th class="px-4 py-3 text-left font-medium">Category</th>
          <th class="px-4 py-3 text-right font-medium">Order units</th>
          <th class="px-4 py-3 text-right font-medium">Outlets</th>
          <th class="px-4 py-3 text-right font-medium">₭ Value</th>
          <th class="px-4 py-3 text-right font-medium"></th>
        </tr>
      </thead>
      <tbody>
        {#each visible as row}
          <tr
            class="border-b border-line last:border-0 hover:bg-bg transition cursor-pointer"
            onclick={() => window.location.href = `/ordering/product/${row.product_id}?date=${selectedDate}`}
          >
            <td class="px-4 py-3 font-medium max-w-[280px] truncate" title={row.product_name}>
              {row.product_name}
            </td>
            <td class="px-4 py-3 text-muted text-xs">{row.category ?? '—'}</td>
            <td class="px-4 py-3 text-right tabular-nums font-semibold">
              {(row.order_units ?? 0).toLocaleString()}
            </td>
            <td class="px-4 py-3 text-right tabular-nums text-muted">{row.outlets}</td>
            <td class="px-4 py-3 text-right tabular-nums">₭{fmtK(row.value_ks ?? 0)}</td>
            <td class="px-4 py-3 text-right text-muted text-xs">→</td>
          </tr>
        {:else}
          <tr>
            <td colspan="6" class="px-4 py-8 text-center text-muted">No products match.</td>
          </tr>
        {/each}
      </tbody>
      <tfoot>
        <tr class="border-t border-line bg-bg font-semibold text-sm">
          <td class="px-4 py-3" colspan="2">Total ({data.totals.products} products)</td>
          <td class="px-4 py-3 text-right tabular-nums">{data.totals.order_units.toLocaleString()}</td>
          <td class="px-4 py-3"></td>
          <td class="px-4 py-3 text-right tabular-nums">₭{fmtK(data.totals.value_ks)}</td>
          <td></td>
        </tr>
      </tfoot>
    </table>
  </div>
{/if}
