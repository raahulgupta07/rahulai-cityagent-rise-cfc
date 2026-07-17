<script lang="ts">
  import { goto } from '$app/navigation';
  import { network, dates, type OutletRow } from '$lib/api/network';
  import ExplainButton from '$lib/ExplainButton.svelte';
  import Icon from '$lib/Icon.svelte';

  // ── state ──────────────────────────────────────────────────────────────────
  let availDates = $state<string[]>([]);
  let selectedDate = $state('');
  let rows = $state<OutletRow[]>([]);
  let loading = $state(true);
  let error = $state('');

  // search + sort
  let search = $state('');
  let sortKey = $state<keyof OutletRow>('order_units');
  let sortAsc = $state(false);

  // ── derived: filtered + sorted rows ────────────────────────────────────────
  let visible = $derived(
    rows
      .filter(r => r.outlet_name.toLowerCase().includes(search.toLowerCase()))
      .slice()
      .sort((a, b) => {
        const av = a[sortKey] ?? 0;
        const bv = b[sortKey] ?? 0;
        if (typeof av === 'string' && typeof bv === 'string')
          return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
        return sortAsc ? (av as number) - (bv as number) : (bv as number) - (av as number);
      })
  );

  // ── effects ─────────────────────────────────────────────────────────────────
  $effect(() => {
    dates().then(d => {
      availDates = d;
      selectedDate = d.at(-1) ?? '';
    }).catch(e => { error = String(e); loading = false; });
  });

  $effect(() => {
    if (!selectedDate) return;
    loading = true;
    error = '';
    network(selectedDate)
      .then(d => { rows = d; })
      .catch(e => { error = String(e); })
      .finally(() => { loading = false; });
  });

  // ── helpers ──────────────────────────────────────────────────────────────────
  function toggleSort(key: keyof OutletRow) {
    if (sortKey === key) sortAsc = !sortAsc;
    else { sortKey = key; sortAsc = false; }
  }

  function chevron(key: keyof OutletRow) {
    if (sortKey !== key) return '⇕';
    return sortAsc ? '↑' : '↓';
  }

  function fmtK(v: number) {
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000)     return (v / 1_000).toFixed(0) + 'K';
    return v.toFixed(0);
  }

  function accColor(a?: number) {
    if (a == null) return 'bg-line';
    if (a >= 0.85) return 'bg-sage';
    if (a >= 0.70) return 'bg-warn';
    return 'bg-accent';
  }
</script>

<!-- ── page header ─────────────────────────────────────────────────────────── -->
<div class="flex items-end justify-between gap-4 flex-wrap mb-6">
  <div>
    <h1 class="font-display text-2xl text-ink mb-1">Network</h1>
    <p class="text-muted text-sm">Every outlet's order plan for the selected day. Click a row for the SKU breakdown.</p>
  </div>

  <div class="flex items-center gap-3">
    <ExplainButton date={selectedDate} label="How the forecast works" />
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

<!-- ── search bar ──────────────────────────────────────────────────────────── -->
<div class="mb-4 relative max-w-xs">
  <Icon name="search" class="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
  <input
    type="text"
    placeholder="Search outlets…"
    bind:value={search}
    aria-label="Search outlets"
    class="w-full bg-surface border border-line rounded-xl pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent hover:border-muted transition-colors"
  />
</div>

<!-- ── summary pills ──────────────────────────────────────────────────────── -->
{#if !loading && rows.length}
  <div class="flex gap-3 mb-5 flex-wrap">
    <span class="pill pill-ghost">{rows.length} outlets</span>
    <span class="pill pill-ghost">
      {rows.reduce((s, r) => s + r.order_units, 0).toLocaleString()} units
    </span>
    <span class="pill pill-ghost">
      ₭{fmtK(rows.reduce((s, r) => s + r.value_ks, 0))}
    </span>
  </div>
{/if}

<!-- ── table ───────────────────────────────────────────────────────────────── -->
{#if error}
  <div class="card text-accent">{error}</div>
{:else if loading}
  <div class="card text-muted animate-pulse">Loading outlets…</div>
{:else}
  <div class="card p-0 overflow-hidden">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-muted">
          {#each [
            { key: 'outlet_name', label: 'Outlet' },
            { key: 'brand',       label: 'Brand' },
            { key: 'order_units', label: 'Order units' },
            { key: 'value_ks',    label: '₭ Value' },
            { key: 'sku_count',   label: 'SKUs' },
            { key: 'accuracy',    label: 'Accuracy' },
          ] as col}
            <th
              class="px-4 py-3 text-left font-medium cursor-pointer select-none hover:text-ink transition"
              onclick={() => toggleSort(col.key as keyof OutletRow)}
            >
              {col.label}
              <span class="ml-1 text-xs opacity-50">{chevron(col.key as keyof OutletRow)}</span>
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each visible as row, i}
          <tr
            class="border-b border-line last:border-0 hover:bg-bg transition cursor-pointer"
            onclick={() => goto(`/network/${row.outlet_id}?date=${selectedDate}`)}
          >
            <td class="px-4 py-3 font-medium">{row.outlet_name}</td>
            <td class="px-4 py-3 text-muted">{row.brand || '—'}</td>
            <td class="px-4 py-3 tabular-nums">{row.order_units.toLocaleString()}</td>
            <td class="px-4 py-3 tabular-nums">₭{fmtK(row.value_ks)}</td>
            <td class="px-4 py-3 tabular-nums">{row.sku_count}</td>
            <td class="px-4 py-3">
              {#if row.accuracy != null}
                <div class="flex items-center gap-2">
                  <div class="w-16 h-1.5 rounded-full bg-line overflow-hidden">
                    <div class="{accColor(row.accuracy)} h-full rounded-full" style="width:{(row.accuracy*100).toFixed(0)}%"></div>
                  </div>
                  <span class="tabular-nums text-xs">{(row.accuracy*100).toFixed(0)}%</span>
                </div>
              {:else}
                <span class="text-muted">—</span>
              {/if}
            </td>
          </tr>
        {:else}
          <tr><td colspan="6" class="px-4 py-8 text-center text-muted">No outlets match.</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
