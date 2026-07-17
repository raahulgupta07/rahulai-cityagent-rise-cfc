<script lang="ts">
  import {
    stockoutCorrection, promoUplift, economicsImpact,
    type StockoutInsight, type PromoInsight, type EconomicsInsight,
  } from '$lib/api/schema';
  import Icon from '$lib/Icon.svelte';

  // ── state ──────────────────────────────────────────────────────────────────
  let stockout   = $state<StockoutInsight | null>(null);
  let promo      = $state<PromoInsight | null>(null);
  let economics  = $state<EconomicsInsight | null>(null);

  let loadingA = $state(true);
  let loadingB = $state(true);
  let loadingC = $state(true);

  // ── load all three in parallel ─────────────────────────────────────────────
  $effect(() => {
    stockoutCorrection()
      .then(d => { stockout = d; })
      .catch(() => { stockout = null; })
      .finally(() => { loadingA = false; });

    promoUplift()
      .then(d => { promo = d; })
      .catch(() => { promo = null; })
      .finally(() => { loadingB = false; });

    economicsImpact()
      .then(d => { economics = d; })
      .catch(() => { economics = null; })
      .finally(() => { loadingC = false; });
  });

  // ── helpers ───────────────────────────────────────────────────────────────
  function pct(n: number | null | undefined) {
    return n != null ? (n > 0 ? '+' : '') + n.toFixed(1) + '%' : '—';
  }

  function fmtNum(n: number | null | undefined, digits = 0) {
    return n != null ? n.toLocaleString(undefined, { maximumFractionDigits: digits }) : '—';
  }
</script>

<!-- ── page header ─────────────────────────────────────────────────────────── -->
<div class="mb-8">
  <h1 class="text-3xl mb-1">Gap Payoffs</h1>
  <p class="text-muted text-sm">
    Each card shows the value unlocked by a missing business input.
    Live insights appear automatically once the data is uploaded.
  </p>
</div>

<div class="flex flex-col gap-6">

  <!-- ══ CARD 1: Stockout Correction ═════════════════════════════════════════ -->
  <div class="card">
    <div class="flex items-start justify-between gap-4 mb-4 flex-wrap">
      <div>
        <h2 class="text-xl font-display mb-0.5">Stockout Correction</h2>
        <p class="text-muted text-sm">How many "zero demand" days were actually out-of-stock events?</p>
      </div>
      {#if loadingA}
        <span class="pill pill-ghost text-xs animate-pulse">Checking…</span>
      {:else if stockout?.available}
        <span class="pill text-xs py-1 px-3 bg-sage/10 text-sage">Live</span>
      {:else}
        <span class="pill text-xs py-1 px-3 bg-warn/10 text-warn">Awaiting upload</span>
      {/if}
    </div>

    {#if loadingA}
      <div class="h-24 rounded-xl bg-line/50 animate-pulse"></div>
    {:else if stockout?.available}
      <!-- live result -->
      {@const s = stockout.summary}
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
        <div class="bg-bg rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums">{fmtNum(s.total_zero_demand_days)}</div>
          <div class="text-xs text-muted mt-1">Zero-demand days</div>
        </div>
        <div class="bg-accent/5 border border-accent/20 rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums text-accent">{fmtNum(s.probable_stockout_days)}</div>
          <div class="text-xs text-muted mt-1">Probable stockouts</div>
        </div>
        <div class="bg-bg rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums">{fmtNum(s.true_zero_demand_days)}</div>
          <div class="text-xs text-muted mt-1">True zero demand</div>
        </div>
        <div class="bg-sage/5 border border-sage/20 rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums text-sage">{s.stockout_pct_of_zeros}%</div>
          <div class="text-xs text-muted mt-1">Of zeros = stockouts</div>
        </div>
      </div>
      <p class="text-sm text-muted leading-relaxed">{stockout.interpretation}</p>
    {:else if stockout}
      <!-- awaiting upload -->
      <div class="flex gap-4 items-start bg-bg rounded-xl p-4">
        <div class="text-muted/40"><Icon name="box" class="w-8 h-8" /></div>
        <div class="flex-1 min-w-0">
          <p class="text-sm text-ink mb-2">{stockout.explanation}</p>
          {#if stockout.potential_value}
            <p class="text-xs text-muted mb-3 italic">{stockout.potential_value}</p>
          {/if}
          {#if stockout.upload_path}
            <a
              href={stockout.upload_path}
              class="pill pill-accent text-sm"
            >Upload inventory_daily</a>
          {/if}
        </div>
      </div>
    {:else}
      <div class="text-sm text-muted">Unable to load stockout insight.</div>
    {/if}
  </div>

  <!-- ══ CARD 2: Promo Uplift ════════════════════════════════════════════════ -->
  <div class="card">
    <div class="flex items-start justify-between gap-4 mb-4 flex-wrap">
      <div>
        <h2 class="text-xl font-display mb-0.5">Promo Uplift</h2>
        <p class="text-muted text-sm">How much does a promotion boost daily demand?</p>
      </div>
      {#if loadingB}
        <span class="pill pill-ghost text-xs animate-pulse">Checking…</span>
      {:else if promo?.available}
        <span class="pill text-xs py-1 px-3 bg-sage/10 text-sage">Live</span>
      {:else}
        <span class="pill text-xs py-1 px-3 bg-warn/10 text-warn">Awaiting upload</span>
      {/if}
    </div>

    {#if loadingB}
      <div class="h-24 rounded-xl bg-line/50 animate-pulse"></div>
    {:else if promo?.available}
      {@const s = promo.summary}
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
        <div class="bg-bg rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums">{fmtNum(s.promo_days_in_calendar)}</div>
          <div class="text-xs text-muted mt-1">Promo days</div>
        </div>
        <div class="bg-bg rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums">{fmtNum(s.matched_demand_days)}</div>
          <div class="text-xs text-muted mt-1">Matched in demand</div>
        </div>
        <div class="bg-bg rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums">{fmtNum(s.promo_avg_daily_units, 0)}</div>
          <div class="text-xs text-muted mt-1">Promo avg units/day</div>
        </div>
        <div class="bg-sage/5 border border-sage/20 rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums text-sage">{pct(s.lift_pct)}</div>
          <div class="text-xs text-muted mt-1">vs baseline</div>
        </div>
      </div>
      <p class="text-sm text-muted leading-relaxed">{promo.interpretation}</p>
    {:else if promo}
      <div class="flex gap-4 items-start bg-bg rounded-xl p-4">
        <div class="text-muted/40"><Icon name="calendar" class="w-8 h-8" /></div>
        <div class="flex-1 min-w-0">
          <p class="text-sm text-ink mb-2">{promo.explanation}</p>
          {#if promo.potential_value}
            <p class="text-xs text-muted mb-3 italic">{promo.potential_value}</p>
          {/if}
          {#if promo.upload_path}
            <a
              href={promo.upload_path}
              class="pill pill-accent text-sm"
            >Upload promo_calendar</a>
          {/if}
        </div>
      </div>
    {:else}
      <div class="text-sm text-muted">Unable to load promo uplift insight.</div>
    {/if}
  </div>

  <!-- ══ CARD 3: Economics Impact ═══════════════════════════════════════════ -->
  <div class="card">
    <div class="flex items-start justify-between gap-4 mb-4 flex-wrap">
      <div>
        <h2 class="text-xl font-display mb-0.5">Economics Impact</h2>
        <p class="text-muted text-sm">How much does per-product margin and shelf life change what to order?</p>
      </div>
      {#if loadingC}
        <span class="pill pill-ghost text-xs animate-pulse">Checking…</span>
      {:else if economics?.available}
        {#if economics.is_uniform}
          <span class="pill text-xs py-1 px-3 bg-warn/10 text-warn">Uniform — upload real data</span>
        {:else}
          <span class="pill text-xs py-1 px-3 bg-sage/10 text-sage">Differentiated</span>
        {/if}
      {:else}
        <span class="pill text-xs py-1 px-3 bg-accent/10 text-accent">Missing</span>
      {/if}
    </div>

    {#if loadingC}
      <div class="h-24 rounded-xl bg-line/50 animate-pulse"></div>
    {:else if economics?.available}
      <!-- stats grid -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
        <div class="bg-bg rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums">{fmtNum(economics.product_count)}</div>
          <div class="text-xs text-muted mt-1">Products in econ table</div>
        </div>
        <div class="bg-bg rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums">
            {economics.gm_stats['mean'] != null ? (economics.gm_stats['mean'] * 100).toFixed(0) + '%' : '—'}
          </div>
          <div class="text-xs text-muted mt-1">Avg gross margin</div>
        </div>
        <div class="bg-bg rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums">
            {economics.shelf_life_stats['mean'] != null ? economics.shelf_life_stats['mean'].toFixed(1) + 'd' : '—'}
          </div>
          <div class="text-xs text-muted mt-1">Avg shelf life</div>
        </div>
        <div class="{economics.is_uniform ? 'bg-warn/5 border border-warn/20' : 'bg-sage/5 border border-sage/20'} rounded-xl p-4 text-center">
          <div class="text-2xl font-display tabular-nums {economics.is_uniform ? 'text-warn' : 'text-sage'}">
            {economics.critical_ratio_spread > 0 ? economics.critical_ratio_spread.toFixed(3) : '0'}
          </div>
          <div class="text-xs text-muted mt-1">CR spread (0 = uniform)</div>
        </div>
      </div>

      <!-- message -->
      <div class="{economics.is_uniform ? 'bg-warn/5 border border-warn/20' : 'bg-sage/5 border border-sage/20'} rounded-xl p-4 mb-3">
        <p class="text-sm text-ink leading-relaxed">{economics.message}</p>
        {#if economics.unlock_value}
          <p class="text-xs text-muted mt-2 italic">{economics.unlock_value}</p>
        {/if}
      </div>

      {#if economics.is_uniform && economics.action}
        <a
          href="/data/upload/product_economics"
          class="pill pill-accent text-sm"
        >Upload real product economics</a>
      {/if}

      <!-- CR detail table (only when differentiated) -->
      {#if !economics.is_uniform && Object.keys(economics.critical_ratio_stats).length > 0}
        <div class="mt-4 border-t border-line pt-4">
          <p class="text-xs font-medium text-muted uppercase tracking-wide mb-3">Critical ratio distribution</p>
          <div class="flex gap-6 flex-wrap text-sm">
            {#each [['min','Min'], ['25%','P25'], ['50%','Median'], ['75%','P75'], ['max','Max']] as [k, label]}
              {#if economics.critical_ratio_stats[k] != null}
                <div class="text-center">
                  <div class="font-display tabular-nums">{economics.critical_ratio_stats[k].toFixed(3)}</div>
                  <div class="text-xs text-muted">{label}</div>
                </div>
              {/if}
            {/each}
          </div>
        </div>
      {/if}
    {:else if economics}
      <div class="flex gap-4 items-start bg-bg rounded-xl p-4">
        <div class="text-muted/40"><Icon name="coins" class="w-8 h-8" /></div>
        <div class="flex-1 min-w-0">
          <p class="text-sm text-ink mb-2">{economics.explanation}</p>
          {#if economics.upload_path}
            <a
              href={economics.upload_path}
              class="pill pill-accent text-sm"
            >Upload product economics</a>
          {/if}
        </div>
      </div>
    {:else}
      <div class="text-sm text-muted">Unable to load economics insight.</div>
    {/if}
  </div>

</div>

<!-- ── footer note ─────────────────────────────────────────────────────────── -->
<div class="mt-8 card bg-bg text-sm text-muted">
  <span class="font-medium text-ink">How this works:</span>
  Each card above corresponds to a data gap.
  Upload the required file via the <a href="/data" class="text-accent underline">Data Hub</a> and
  the insight activates automatically on next load.
  The schema view (<a href="/data/schema" class="text-accent underline">Data → Schema</a>) shows
  the full table structure and relationships.
</div>
