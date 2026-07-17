<script lang="ts">
  import { page } from '$app/stores';
  import { orderApi, type ProductionResponse, type ProductionRow } from '$lib/api/order';
  import { api } from '$lib/api';

  // ── state ────────────────────────────────────────────────────────────────────
  let availDates   = $state<string[]>([]);
  let selectedDate = $state('');
  let data         = $state<ProductionResponse | null>(null);
  let loading      = $state(true);
  let error        = $state('');
  let search       = $state('');

  // ── derived ──────────────────────────────────────────────────────────────────
  let productId = $derived(parseInt($page.params.id, 10));

  let visible = $derived(
    (data?.rows ?? []).filter(r =>
      r.outlet_name.toLowerCase().includes(search.toLowerCase())
    )
  );

  // ── helpers ──────────────────────────────────────────────────────────────────
  function fmtK(v: number): string {
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000)     return (v / 1_000).toFixed(0) + 'K';
    return v.toFixed(0);
  }

  function trendIcon(t?: string): string {
    if (t === 'up')   return '↑';
    if (t === 'down') return '↓';
    return '→';
  }

  function trendColor(t?: string): string {
    if (t === 'up')   return 'text-sage';
    if (t === 'down') return 'text-accent';
    return 'text-muted';
  }

  // ── effects ──────────────────────────────────────────────────────────────────
  $effect(() => {
    api.dates()
      .then(d => {
        availDates = d;
        // prefer date from URL query param
        const urlDate = new URLSearchParams(window.location.search).get('date');
        selectedDate = urlDate && d.includes(urlDate) ? urlDate : (d.at(-1) ?? '');
      })
      .catch(e => { error = String(e); loading = false; });
  });

  $effect(() => {
    if (!selectedDate || !productId) return;
    loading = true; error = '';
    orderApi.production(productId, selectedDate)
      .then(d  => { data = d; })
      .catch(e => { error = String(e); })
      .finally(() => { loading = false; });
  });
</script>

<!-- ── back + header ─────────────────────────────────────────────────────────── -->
<div class="mb-6">
  <a href="/ordering" class="text-muted text-sm hover:text-ink transition">← Picklist</a>
</div>

<div class="flex items-center justify-between mb-6">
  <div>
    {#if data}
      <h1 class="text-3xl mb-1">{data.product_name}</h1>
      <p class="text-muted text-sm">
        {#if data.product_code}<span class="font-mono">{data.product_code}</span> ·{/if}
        {data.category ?? 'Bakery'}
        · Production sheet
      </p>
    {:else}
      <h1 class="text-3xl mb-1 text-muted animate-pulse">Loading…</h1>
    {/if}
  </div>

  <!-- date picker -->
  <select
    bind:value={selectedDate}
    class="bg-surface border border-line rounded-xl px-3 py-2 text-sm text-ink focus:outline-none focus:ring-1 focus:ring-accent"
  >
    {#each [...availDates].reverse() as d}
      <option value={d}>{d}</option>
    {/each}
  </select>
</div>

<!-- ── summary pills ─────────────────────────────────────────────────────────── -->
{#if data}
  <div class="flex gap-3 mb-6 flex-wrap">
    <span class="pill pill-accent">
      Make total: {data.make_total.toLocaleString()} units
    </span>
    <span class="pill pill-ghost">
      <span class="text-muted text-xs">Outlets</span>
      <strong>{data.outlets_count}</strong>
    </span>
    <span class="pill pill-ghost">
      <span class="text-muted text-xs">Date</span>
      <strong>{data.date}</strong>
    </span>
  </div>
{/if}

<!-- ── search ─────────────────────────────────────────────────────────────────── -->
<div class="mb-4">
  <input
    type="text"
    placeholder="Search outlets…"
    bind:value={search}
    class="w-full max-w-xs bg-surface border border-line rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
  />
</div>

<!-- ── production table ───────────────────────────────────────────────────────── -->
{#if error}
  <div class="card text-accent">{error}</div>
{:else if loading}
  <div class="card text-muted animate-pulse">Loading production sheet…</div>
{:else if data}
  <div class="card p-0 overflow-hidden">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-muted">
          <th class="px-4 py-3 text-left font-medium">Outlet</th>
          <th class="px-4 py-3 text-left font-medium">Brand</th>
          <th class="px-4 py-3 text-right font-medium">Order qty</th>
          <th class="px-4 py-3 text-right font-medium">Expected</th>
          <th class="px-4 py-3 text-right font-medium">Safe (P85)</th>
          <th class="px-4 py-3 text-right font-medium">Actual</th>
          <th class="px-4 py-3 text-center font-medium">Trend</th>
        </tr>
      </thead>
      <tbody>
        {#each visible as row}
          <tr class="border-b border-line last:border-0 hover:bg-bg transition">
            <td class="px-4 py-3 font-medium">{row.outlet_name}</td>
            <td class="px-4 py-3 text-muted text-xs">{row.brand ?? '—'}</td>
            <td class="px-4 py-3 text-right tabular-nums font-semibold text-accent">
              {(row.order_qty ?? 0).toLocaleString()}
            </td>
            <td class="px-4 py-3 text-right tabular-nums">{row.expected?.toFixed(1) ?? '—'}</td>
            <td class="px-4 py-3 text-right tabular-nums text-muted">{row.safe?.toFixed(1) ?? '—'}</td>
            <td class="px-4 py-3 text-right tabular-nums text-muted">
              {row.actual != null ? row.actual.toFixed(1) : '—'}
            </td>
            <td class="px-4 py-3 text-center font-medium {row.trend === 'up' ? 'text-sage' : row.trend === 'down' ? 'text-accent' : 'text-muted'}">
              {row.trend === 'up' ? '↑' : row.trend === 'down' ? '↓' : '→'}
            </td>
          </tr>
        {:else}
          <tr>
            <td colspan="7" class="px-4 py-8 text-center text-muted">No outlets match.</td>
          </tr>
        {/each}
      </tbody>
      {#if data.rows.length > 0}
        <tfoot>
          <tr class="border-t border-line bg-bg font-semibold text-sm">
            <td class="px-4 py-3" colspan="2">Make total ({data.outlets_count} outlets)</td>
            <td class="px-4 py-3 text-right tabular-nums text-accent">
              {data.make_total.toLocaleString()}
            </td>
            <td colspan="4"></td>
          </tr>
        </tfoot>
      {/if}
    </table>
  </div>
{/if}
