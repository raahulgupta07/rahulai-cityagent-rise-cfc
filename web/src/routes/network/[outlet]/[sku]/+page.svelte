<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { sku as fetchSku, dates, type SkuDetail } from '$lib/api/network';
  import ExplainButton from '$lib/ExplainButton.svelte';
  import Chart from 'chart.js/auto';

  // ── route params ─────────────────────────────────────────────────────────────
  let outletId  = $derived(Number($page.params.outlet));
  let productId = $derived(Number($page.params.sku));
  let dateParam = $derived($page.url.searchParams.get('date') ?? '');

  // ── state ────────────────────────────────────────────────────────────────────
  let availDates = $state<string[]>([]);
  let selectedDate = $state('');
  let detail = $state<SkuDetail | null>(null);
  let loading = $state(true);
  let error = $state('');

  // chart
  let canvasEl = $state<HTMLCanvasElement | null>(null);
  let chart: Chart | null = null;

  // ── init ─────────────────────────────────────────────────────────────────────
  $effect(() => {
    dates().then(d => {
      availDates = d;
      selectedDate = dateParam || d.at(-1) || '';
    }).catch(e => { error = String(e); loading = false; });
  });

  $effect(() => {
    if (!selectedDate || !outletId || !productId) return;
    loading = true;
    error = '';
    fetchSku(outletId, productId, selectedDate)
      .then(d => { detail = d; })
      .catch(e => { error = String(e); })
      .finally(() => { loading = false; });
  });

  // ── chart (render/update whenever detail changes) ─────────────────────────────
  $effect(() => {
    if (!detail || !canvasEl) return;

    // destroy previous instance
    if (chart) { chart.destroy(); chart = null; }

    const hist = detail.history.slice(-30); // last 30 days
    const labels = hist.map(h => h.date.slice(5)); // MM-DD
    const actuals  = hist.map(h => h.actual);
    const expected = hist.map(h => h.expected);
    const safe     = hist.map(h => h.safe);

    chart = new Chart(canvasEl, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Actual',
            data: actuals,
            borderColor: '#2B2722',
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: '#2B2722',
            tension: 0.3,
            fill: false,
          },
          {
            label: 'Expected',
            data: expected,
            borderColor: '#C96442',
            borderWidth: 1.5,
            borderDash: [],
            pointRadius: 0,
            tension: 0.3,
            fill: false,
          },
          {
            label: 'Safe',
            data: safe,
            borderColor: '#C96442',
            borderWidth: 1,
            borderDash: [4, 3],
            pointRadius: 0,
            tension: 0.3,
            backgroundColor: 'rgba(201,100,66,0.07)',
            fill: '-1', // fill between expected and safe
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'top',
            labels: { color: '#8A8073', font: { size: 12 }, boxWidth: 16, padding: 16 }
          },
          tooltip: {
            backgroundColor: '#FFFDF9',
            titleColor: '#2B2722',
            bodyColor: '#8A8073',
            borderColor: '#E7E0D5',
            borderWidth: 1,
          },
        },
        scales: {
          x: {
            ticks: { color: '#8A8073', font: { size: 11 }, maxRotation: 0 },
            grid: { color: '#E7E0D5' },
          },
          y: {
            ticks: { color: '#8A8073', font: { size: 11 } },
            grid: { color: '#E7E0D5' },
            beginAtZero: true,
          },
        },
      },
    });
  });

  // ── helpers ──────────────────────────────────────────────────────────────────
  function fmtN(v?: number | null, dec = 1) {
    if (v == null) return '—';
    return v.toLocaleString(undefined, { maximumFractionDigits: dec });
  }
  function fmtPct(v?: number | null) {
    if (v == null) return '—';
    return (v * 100).toFixed(0) + '%';
  }
  function effectSign(pct: number) {
    if (pct > 0) return '+';
    return '';
  }
  function effectClass(pct: number) {
    if (pct > 3)  return 'text-sage';
    if (pct < -3) return 'text-accent';
    return 'text-muted';
  }
</script>

<!-- ── breadcrumb ───────────────────────────────────────────────────────────── -->
<div class="mb-1 text-sm text-muted">
  <a href="/network?date={selectedDate}" class="hover:text-ink transition">Network</a>
  <span class="mx-1">›</span>
  <a href="/network/{outletId}?date={selectedDate}" class="hover:text-ink transition">Outlet {outletId}</a>
  <span class="mx-1">›</span>
  <span class="text-ink">{detail?.product_name ?? productId}</span>
</div>

<!-- ── date picker ──────────────────────────────────────────────────────────── -->
<div class="flex items-center justify-between mb-6">
  <div>
    <h1 class="text-3xl mb-1">{detail?.product_name ?? '…'}</h1>
    <p class="text-muted text-sm">
      {detail?.outlet_name ?? `Outlet ${outletId}`}
      {#if detail?.category} · {detail.category}{/if}
    </p>
  </div>
  <select
    bind:value={selectedDate}
    class="bg-surface border border-line rounded-xl px-3 py-2 text-sm text-ink focus:outline-none focus:ring-1 focus:ring-accent"
  >
    {#each [...availDates].reverse() as d}
      <option value={d}>{d}</option>
    {/each}
  </select>
</div>

{#if error}
  <div class="card text-accent">{error}</div>
{:else if loading}
  <div class="card text-muted animate-pulse">Loading…</div>
{:else if detail}

  <!-- ── tomorrow's numbers ──────────────────────────────────────────────────── -->
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
    <div class="card text-center">
      <div class="text-2xl font-display">{fmtN(detail.expected)}</div>
      <div class="text-muted text-xs mt-1">Expected</div>
    </div>
    <div class="card text-center">
      <div class="text-2xl font-display text-muted">{fmtN(detail.safe)}</div>
      <div class="text-muted text-xs mt-1">Safe</div>
    </div>
    <div class="card text-center">
      <div class="text-2xl font-display text-muted">{fmtN(detail.max_safe)}</div>
      <div class="text-muted text-xs mt-1">Max</div>
    </div>
    <div class="card text-center bg-accent/5 border-accent/20">
      <div class="text-2xl font-display text-accent">{fmtN(detail.order_qty, 0)}</div>
      <div class="text-muted text-xs mt-1">Order qty</div>
    </div>
  </div>

  <!-- ── accuracy pill + explain ────────────────────────────────────────────── -->
  <div class="mb-6 flex items-center gap-3 flex-wrap">
    {#if detail.accuracy != null}
      <span class="pill pill-ghost">
        Accuracy {fmtPct(detail.accuracy)}
        {#if detail.price}· ₭{detail.price.toLocaleString()} / unit{/if}
      </span>
    {/if}
    <ExplainButton
      branch={detail.outlet_name}
      product={detail.product_name}
      date={selectedDate}
      label="Explain this forecast" />
  </div>

  <!-- ── 30-day chart ─────────────────────────────────────────────────────────── -->
  <div class="card mb-6">
    <h2 class="text-lg mb-4">30-day history</h2>
    <div class="relative" style="height: 240px;">
      <canvas bind:this={canvasEl}></canvas>
    </div>
  </div>

  <!-- ── why this number ────────────────────────────────────────────────────── -->
  <div class="card">
    <h2 class="text-lg mb-4">Why this number</h2>
    {#if detail.drivers.length === 0}
      <p class="text-muted text-sm">No driver data available.</p>
    {:else}
      <ul class="space-y-3">
        {#each detail.drivers as d}
          <li class="flex items-start gap-3">
            <span class="pill pill-ghost py-1 text-xs {effectClass(d.effect_pct)} shrink-0">
              {effectSign(d.effect_pct)}{d.effect_pct.toFixed(1)}%
            </span>
            <div>
              <div class="font-medium text-sm capitalize">{d.label}</div>
              {#if d.note}<div class="text-muted text-xs">{d.note}</div>{/if}
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </div>

{/if}
