<script lang="ts">
  import { orderApi, type ByWarehouseResponse, type WarehouseGroup } from '$lib/api/order';
  import { api } from '$lib/api';

  // ── state ────────────────────────────────────────────────────────────────────
  let availDates   = $state<string[]>([]);
  let selectedDate = $state('');
  let data         = $state<ByWarehouseResponse | null>(null);
  let loading      = $state(true);
  let error        = $state('');
  let expanded     = $state<Set<string>>(new Set());

  // ── helpers ──────────────────────────────────────────────────────────────────
  function fmtK(v: number): string {
    if (v >= 1_000_000_000) return (v / 1_000_000_000).toFixed(1) + 'B';
    if (v >= 1_000_000)     return (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000)         return (v / 1_000).toFixed(0) + 'K';
    return v.toFixed(0);
  }

  function toggle(key: string) {
    const next = new Set(expanded);
    if (next.has(key)) next.delete(key); else next.add(key);
    expanded = next;
  }

  // ── effects ──────────────────────────────────────────────────────────────────
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
    orderApi.byWarehouse(selectedDate)
      .then(d  => { data = d; })
      .catch(e => { error = String(e); })
      .finally(() => { loading = false; });
  });
</script>

<!-- ── header ────────────────────────────────────────────────────────────────── -->
<div class="mb-4">
  <a href="/ordering" class="text-muted text-sm hover:text-ink transition">← Picklist</a>
</div>

<div class="flex items-center justify-between mb-6">
  <div>
    <h1 class="text-3xl mb-1">By Warehouse</h1>
    <p class="text-muted text-sm">Picklist split per supplying warehouse</p>
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

<!-- ── note banner ───────────────────────────────────────────────────────────── -->
{#if data?.note}
  <div class="card bg-warn/10 border-warn/30 text-sm mb-5">
    <span class="text-warn font-medium">◈ Mapping note:</span>
    {data.note}
  </div>
{/if}

<!-- ── content ───────────────────────────────────────────────────────────────── -->
{#if error}
  <div class="card text-accent">{error}</div>
{:else if loading}
  <div class="card text-muted animate-pulse">Loading warehouse data…</div>
{:else if data}
  <div class="flex flex-col gap-4">
    {#each data.warehouses as wh}
      {@const key = String(wh.warehouse_id ?? 'net')}
      {@const isOpen = expanded.has(key)}

      <div class="card p-0 overflow-hidden">
        <!-- accordion header -->
        <button
          class="w-full flex items-center justify-between px-5 py-4 hover:bg-bg transition text-left"
          onclick={() => toggle(key)}
        >
          <div class="flex items-center gap-4">
            <span class="font-display text-base font-semibold">{wh.warehouse_name}</span>
            <span class="pill pill-ghost text-xs py-0.5 px-2">{wh.rows.length} products</span>
            <span class="pill pill-ghost text-xs py-0.5 px-2">{(wh.order_units ?? 0).toLocaleString()} units</span>
            <span class="pill pill-ghost text-xs py-0.5 px-2">₭{fmtK(wh.value_ks ?? 0)}</span>
          </div>
          <span class="text-muted text-sm transition-transform {isOpen ? 'rotate-180' : ''}">▾</span>
        </button>

        <!-- accordion body -->
        {#if isOpen}
          <div class="border-t border-line">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-line text-muted">
                  <th class="px-5 py-2 text-left font-medium">Product</th>
                  <th class="px-5 py-2 text-left font-medium text-xs">Category</th>
                  <th class="px-5 py-2 text-right font-medium">Order units</th>
                  <th class="px-5 py-2 text-right font-medium">Outlets</th>
                  <th class="px-5 py-2 text-right font-medium">₭ Value</th>
                </tr>
              </thead>
              <tbody>
                {#each wh.rows as row}
                  <tr
                    class="border-b border-line last:border-0 hover:bg-bg transition cursor-pointer"
                    onclick={() => window.location.href = `/ordering/product/${row.product_id}?date=${selectedDate}`}
                  >
                    <td class="px-5 py-2.5 font-medium max-w-[260px] truncate" title={row.product_name}>
                      {row.product_name}
                    </td>
                    <td class="px-5 py-2.5 text-muted text-xs">{row.category ?? '—'}</td>
                    <td class="px-5 py-2.5 text-right tabular-nums">
                      {(row.order_units ?? 0).toLocaleString()}
                    </td>
                    <td class="px-5 py-2.5 text-right tabular-nums text-muted">{row.outlets}</td>
                    <td class="px-5 py-2.5 text-right tabular-nums">₭{fmtK(row.value_ks ?? 0)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>
    {/each}
  </div>
{/if}
