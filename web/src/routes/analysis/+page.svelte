<script lang="ts">
  import { onMount } from 'svelte';
  import { analysisApi, type Analysis, type Table } from '$lib/api/analysis';

  let a = $state<Analysis | null>(null);
  let error = $state<string | null>(null);

  onMount(async () => {
    try { a = await analysisApi.get(); } catch (e) { error = String(e); }
  });

  function fmt(n: number | null | undefined): string {
    if (n == null) return '—';
    if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(0) + 'k';
    return String(n);
  }
  const pct = (x: number, max: number) => `${Math.max(2, (x / max) * 100)}%`;
</script>

<div class="space-y-8">
  <div>
    <h1 class="font-display text-2xl text-ink mb-1">Analysis</h1>
    <p class="text-sm text-muted max-w-2xl">The full story behind the model — data profile, accuracy,
      calibration, cost and drift. Every number is read live from the latest pipeline run.</p>
  </div>

  {#if error}<div class="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>{/if}
  {#if !a}<div class="text-muted text-sm animate-pulse">Loading analysis…</div>{:else}

  <!-- 01 glance -->
  <section>
    <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">01 · Data at a glance</div>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      {#each [['Net units', a.data_glance.net_units], ['Revenue ₭', a.data_glance.revenue_ks], ['Outlets', a.data_glance.branches], ['Products', a.data_glance.products], ['Days', a.data_glance.days], ['Series', a.data_glance.series]] as [k, v]}
        <div class="rounded-xl border border-line bg-surface p-3">
          <div class="text-xs text-muted">{k}</div>
          <div class="font-mono text-xl font-semibold mt-1">{fmt(v as number)}</div>
        </div>
      {/each}
    </div>
  </section>

  <!-- 02 trend + brand -->
  <section class="grid md:grid-cols-2 gap-6">
    <div>
      <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">02 · Units by year · peak {a.dow.peak_day} ({a.dow.peak_ratio}×)</div>
      <div class="rounded-xl border border-line bg-surface p-4 space-y-2">
        {#each a.yearly as y}
          <div class="flex items-center gap-3">
            <span class="w-12 text-xs font-mono text-muted">{y.year}</span>
            <div class="flex-1 h-3 rounded-full bg-bg overflow-hidden">
              <div class="h-full rounded-full bg-accent" style="width:{pct(y.units, Math.max(...a.yearly.map(x=>x.units)))}"></div>
            </div>
            <span class="w-14 text-right text-xs font-mono">{fmt(y.units)}</span>
          </div>
        {/each}
      </div>
    </div>
    <div>
      <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">Brand share · festival {a.festival.holiday_pct ? '+' + a.festival.holiday_pct + '%' : ''} / −{a.festival.thingyan_pct}%</div>
      <div class="rounded-xl border border-line bg-surface p-4 space-y-2">
        {#each a.brand_mix as b}
          <div class="flex items-center gap-3">
            <span class="w-20 text-xs truncate">{b.brand}</span>
            <div class="flex-1 h-3 rounded-full bg-bg overflow-hidden">
              <div class="h-full rounded-full bg-sage" style="width:{pct(b.share_pct, 100)}"></div>
            </div>
            <span class="w-12 text-right text-xs font-mono">{b.share_pct}%</span>
          </div>
        {/each}
      </div>
    </div>
  </section>

  <!-- 03 concentration -->
  <section class="grid md:grid-cols-2 gap-6">
    <div>
      <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">03 · Top outlets (top10 = {a.concentration.top10_branch_pct}%)</div>
      <div class="rounded-xl border border-line bg-surface p-4 space-y-1.5 text-sm">
        {#each a.concentration.top_branches as b}
          <div class="flex justify-between"><span class="truncate">{b.name}</span><span class="font-mono text-muted">{fmt(b.units)}</span></div>
        {/each}
      </div>
    </div>
    <div>
      <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">Top products</div>
      <div class="rounded-xl border border-line bg-surface p-4 space-y-1.5 text-sm">
        {#each a.concentration.top_products as p}
          <div class="flex justify-between"><span class="truncate">{p.name}</span><span class="font-mono text-muted">{fmt(p.units)}</span></div>
        {/each}
      </div>
    </div>
  </section>

  <!-- 04 patterns + ABC -->
  <section>
    <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">04 · Demand pattern &amp; ABC (A: {a.abc.a} SKUs = {a.abc.a_vol_pct}% vol)</div>
    {#if a.patterns.length}
      <div class="rounded-xl border border-line bg-surface overflow-hidden">
        <table class="w-full text-sm">
          <thead><tr class="bg-bg text-xs text-muted border-b border-line">
            <th class="text-left px-4 py-2 font-medium">Pattern</th><th class="text-left px-4 py-2 font-medium">Series</th>
            <th class="text-left px-4 py-2 font-medium">% series</th><th class="text-left px-4 py-2 font-medium">% volume</th></tr></thead>
          <tbody>{#each a.patterns as r}<tr class="border-b border-line/50 last:border-0">
            {#each r.slice(0,4) as c}<td class="px-4 py-2 {c === r[0] ? 'font-medium' : 'font-mono text-muted'}">{c}</td>{/each}</tr>{/each}</tbody>
        </table>
      </div>
    {/if}
  </section>

  <!-- 05 accuracy folds + by class -->
  <section class="grid md:grid-cols-2 gap-6">
    <div>
      <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">05 · Accuracy by period (overall {a.accuracy.overall}%)</div>
      <div class="rounded-xl border border-line bg-surface p-4 space-y-2.5">
        {#each a.accuracy.folds as f}
          <div class="flex items-center gap-3">
            <span class="w-16 text-xs font-mono text-muted">{f.period}</span>
            <div class="flex-1 h-3 rounded-full bg-bg overflow-hidden">
              <div class="h-full rounded-full bg-accent" style="width:{f.model_acc}%"></div>
            </div>
            <span class="w-12 text-right text-xs font-mono">{f.model_acc}%</span>
            <span class="w-10 text-right text-xs font-mono text-sage">+{f.gain_pct}%</span>
          </div>
        {/each}
      </div>
    </div>
    <div>
      <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">By product size</div>
      <div class="rounded-xl border border-line bg-surface p-4 space-y-2.5">
        {#each a.accuracy.by_class as c}
          <div class="flex items-center gap-3">
            <span class="w-24 text-xs">Class {c.cls} · {c.vol_share}%</span>
            <div class="flex-1 h-3 rounded-full bg-bg overflow-hidden">
              <div class="h-full rounded-full {c.cls === 'A' ? 'bg-sage' : c.cls === 'B' ? 'bg-accent' : 'bg-warn'}" style="width:{c.accuracy}%"></div>
            </div>
            <span class="w-12 text-right text-xs font-mono">{c.accuracy}%</span>
          </div>
        {/each}
      </div>
    </div>
  </section>

  <!-- 06 calibration + baselines -->
  <section class="grid md:grid-cols-2 gap-6">
    <div>
      <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">06 · Calibration (coverage vs target)</div>
      <div class="rounded-xl border border-line bg-surface overflow-hidden">
        <table class="w-full text-sm"><thead><tr class="bg-bg text-xs text-muted border-b border-line">
          <th class="text-left px-4 py-2 font-medium">Level</th><th class="text-right px-4 py-2 font-medium">Coverage</th>
          <th class="text-right px-4 py-2 font-medium">Target</th></tr></thead>
          <tbody>{#each a.calibration as c}<tr class="border-b border-line/50 last:border-0">
            <td class="px-4 py-2 font-medium">{c.level}</td><td class="px-4 py-2 text-right font-mono">{c.coverage}%</td>
            <td class="px-4 py-2 text-right font-mono text-muted">{c.target}%</td></tr>{/each}</tbody></table>
      </div>
    </div>
    {#if a.baselines}
      <div>
        <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">Simple-method floor</div>
        <div class="rounded-xl border border-line bg-surface overflow-x-auto">
          <table class="w-full text-sm"><thead><tr class="bg-bg text-xs text-muted border-b border-line">
            {#each a.baselines.columns as c}<th class="text-left px-3 py-2 font-medium">{c}</th>{/each}</tr></thead>
            <tbody>{#each a.baselines.rows as r}<tr class="border-b border-line/50 last:border-0">
              {#each r as c, i}<td class="px-3 py-2 {i === 0 ? 'font-medium' : 'font-mono text-muted'}">{c}</td>{/each}</tr>{/each}</tbody></table>
        </div>
      </div>
    {/if}
  </section>

  <!-- 07 cost sim -->
  {#if a.cost_sim}
    <section>
      <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">07 · Cost simulation — order policy vs realised demand</div>
      <div class="rounded-xl border border-line bg-surface overflow-x-auto">
        <table class="w-full text-sm"><thead><tr class="bg-bg text-xs text-muted border-b border-line">
          {#each a.cost_sim.columns as c}<th class="text-left px-3 py-2 font-medium">{c}</th>{/each}</tr></thead>
          <tbody>{#each a.cost_sim.rows as r}<tr class="border-b border-line/50 last:border-0">
            {#each r as c, i}<td class="px-3 py-2 {i === 0 ? 'font-medium' : 'font-mono text-muted'}">{c}</td>{/each}</tr>{/each}</tbody></table>
      </div>
    </section>
  {/if}

  <!-- 08 service tradeoff -->
  {#if a.service_tradeoff}
    <section>
      <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">08 · Service level vs waste</div>
      <div class="rounded-xl border border-line bg-surface overflow-x-auto">
        <table class="w-full text-sm"><thead><tr class="bg-bg text-xs text-muted border-b border-line">
          {#each a.service_tradeoff.columns as c}<th class="text-left px-3 py-2 font-medium">{c}</th>{/each}</tr></thead>
          <tbody>{#each a.service_tradeoff.rows as r}<tr class="border-b border-line/50 last:border-0">
            {#each r as c, i}<td class="px-3 py-2 {i === 0 ? 'font-medium' : 'font-mono text-muted'}">{c}</td>{/each}</tr>{/each}</tbody></table>
      </div>
    </section>
  {/if}

  <!-- 09 drift -->
  <section>
    <div class="text-xs font-mono uppercase tracking-wide text-muted mb-3 pb-2 border-b border-line">09 · Drift monitor — {a.drift.verdict}</div>
    <div class="grid md:grid-cols-[1fr_1fr] gap-6">
      <div class="rounded-xl border border-line bg-surface overflow-hidden">
        <table class="w-full text-sm"><thead><tr class="bg-bg text-xs text-muted border-b border-line">
          <th class="text-left px-4 py-2 font-medium">Signal</th><th class="text-right px-4 py-2 font-medium">Shift</th>
          <th class="text-left px-4 py-2 font-medium">Status</th></tr></thead>
          <tbody>{#each a.drift.psi as r}<tr class="border-b border-line/50 last:border-0">
            <td class="px-4 py-2 font-mono text-xs">{r[0]}</td><td class="px-4 py-2 text-right font-mono">{r[1]}</td>
            <td class="px-4 py-2"><span class="text-xs px-2 py-0.5 rounded-full {r[2] === 'ok' ? 'bg-sage/15 text-sage' : 'bg-warn/15 text-warn'}">{r[2]}</span></td></tr>{/each}</tbody></table>
      </div>
      <div class="rounded-xl border border-line bg-surface p-5">
        <div class="grid grid-cols-2 gap-3 mb-4">
          <div><div class="text-xs text-muted">Model error at train</div><div class="font-mono text-xl font-semibold">{a.drift.champion_error}</div></div>
          <div><div class="text-xs text-muted">Recent error</div><div class="font-mono text-xl font-semibold text-sage">{a.drift.recent_error}</div></div>
        </div>
        <div class="text-sm text-muted">
          Data drift: <span class="font-medium {a.drift.data_drift ? 'text-warn' : 'text-sage'}">{a.drift.data_drift ? 'yes' : 'no'}</span> ·
          Accuracy drift: <span class="font-medium {a.drift.accuracy_drift ? 'text-warn' : 'text-sage'}">{a.drift.accuracy_drift ? 'yes' : 'no'}</span>.
          The accuracy gate is the real retrain trigger — data shift alone (monsoon weather) is expected seasonality.
        </div>
      </div>
    </div>
  </section>

  {/if}
</div>
