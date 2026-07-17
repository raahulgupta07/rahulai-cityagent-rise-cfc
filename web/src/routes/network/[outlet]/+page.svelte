<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { outlet as fetchOutlet, dates, type SkuRow } from '$lib/api/network';

  // ── route params ────────────────────────────────────────────────────────────
  let outletId = $derived(Number($page.params.outlet));
  let dateParam = $derived($page.url.searchParams.get('date') ?? '');

  // ── state ───────────────────────────────────────────────────────────────────
  let availDates = $state<string[]>([]);
  let selectedDate = $state('');
  let rows = $state<SkuRow[]>([]);
  let loading = $state(true);
  let error = $state('');
  let hideZero = $state(false);

  // derive outlet name from first row
  let outletName = $derived(rows.length > 0 ? '' : '');

  // ── init dates ───────────────────────────────────────────────────────────────
  $effect(() => {
    dates().then(d => {
      availDates = d;
      selectedDate = dateParam || d.at(-1) || '';
    }).catch(e => { error = String(e); loading = false; });
  });

  // ── load SKUs ────────────────────────────────────────────────────────────────
  $effect(() => {
    if (!selectedDate || !outletId) return;
    loading = true;
    error = '';
    fetchOutlet(outletId, selectedDate, hideZero)
      .then(d => { rows = d; })
      .catch(e => { error = String(e); })
      .finally(() => { loading = false; });
  });

  // ── helpers ──────────────────────────────────────────────────────────────────
  function trendIcon(t?: string) {
    if (t === 'up')   return '▲';
    if (t === 'down') return '▼';
    return '▬';
  }
  function trendClass(t?: string) {
    if (t === 'up')   return 'text-sage';
    if (t === 'down') return 'text-accent';
    return 'text-muted';
  }
  function fmtN(v?: number | null) {
    if (v == null) return '—';
    return v.toLocaleString(undefined, { maximumFractionDigits: 1 });
  }
</script>

<!-- ── back + header ─────────────────────────────────────────────────────── -->
<div class="mb-1">
  <a href="/network?date={selectedDate}" class="text-muted text-sm hover:text-ink transition">
    ← Network
  </a>
</div>

<div class="flex items-start justify-between mb-6">
  <div>
    <h1 class="text-3xl mb-1">Outlet {outletId}</h1>
    <p class="text-muted text-sm">SKU-level plan · {selectedDate}</p>
  </div>

  <div class="flex items-center gap-3">
    <!-- hide-zero toggle -->
    <label class="flex items-center gap-2 text-sm text-muted cursor-pointer select-none">
      <input
        type="checkbox"
        bind:checked={hideZero}
        class="rounded accent-accent"
      />
      Hide zero-demand
    </label>

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
</div>

<!-- ── summary pills ──────────────────────────────────────────────────────── -->
{#if !loading && rows.length}
  <div class="flex gap-3 mb-5 flex-wrap">
    <span class="pill pill-ghost">{rows.length} SKUs</span>
    <span class="pill pill-ghost">
      {rows.reduce((s, r) => s + r.order_qty, 0).toLocaleString()} units ordered
    </span>
  </div>
{/if}

<!-- ── table ───────────────────────────────────────────────────────────────── -->
{#if error}
  <div class="card text-accent">{error}</div>
{:else if loading}
  <div class="card text-muted animate-pulse">Loading SKUs…</div>
{:else if !rows.length}
  <div class="card text-muted">No SKUs found for this outlet / date.</div>
{:else}
  <div class="card p-0 overflow-hidden">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-muted">
          <th class="px-4 py-3 text-left font-medium">Product</th>
          <th class="px-4 py-3 text-right font-medium">Expected</th>
          <th class="px-4 py-3 text-right font-medium">Safe</th>
          <th class="px-4 py-3 text-right font-medium">Max</th>
          <th class="px-4 py-3 text-right font-medium">Order</th>
          <th class="px-4 py-3 text-right font-medium">Yesterday</th>
          <th class="px-4 py-3 text-right font-medium">Avg 7d</th>
          <th class="px-4 py-3 text-center font-medium">Trend</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row}
          <tr
            class="border-b border-line last:border-0 hover:bg-bg transition cursor-pointer"
            onclick={() => goto(`/network/${outletId}/${row.product_id}?date=${selectedDate}`)}
          >
            <td class="px-4 py-3 font-medium max-w-xs truncate" title={row.product_name}>
              {row.product_name}
            </td>
            <td class="px-4 py-3 text-right tabular-nums">{fmtN(row.expected)}</td>
            <td class="px-4 py-3 text-right tabular-nums text-muted">{fmtN(row.safe)}</td>
            <td class="px-4 py-3 text-right tabular-nums text-muted">{fmtN(row.max_safe)}</td>
            <td class="px-4 py-3 text-right tabular-nums font-semibold">{fmtN(row.order_qty)}</td>
            <td class="px-4 py-3 text-right tabular-nums text-muted">{fmtN(row.yesterday)}</td>
            <td class="px-4 py-3 text-right tabular-nums text-muted">{fmtN(row.avg_7d)}</td>
            <td class="px-4 py-3 text-center {trendClass(row.trend)}">{trendIcon(row.trend)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
