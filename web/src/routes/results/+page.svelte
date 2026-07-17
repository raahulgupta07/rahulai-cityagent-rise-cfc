<script lang="ts">
  import { onMount } from 'svelte';
  import { resultsApi, type ResultsSummary } from '$lib/api/results';
  import Chart from 'chart.js/auto';
  import Icon from '$lib/Icon.svelte';

  let data = $state<ResultsSummary | null>(null);
  let error = $state<string | null>(null);
  let chartCanvas = $state<HTMLCanvasElement | null>(null);
  let classCanvas = $state<HTMLCanvasElement | null>(null);
  let chartInst: Chart | null = null;
  let classInst: Chart | null = null;

  onMount(async () => {
    try {
      data = await resultsApi.summary();
    } catch (e) {
      error = String(e);
    }
  });

  // Build accuracy-by-period trend chart once data arrives
  $effect(() => {
    if (!data || !chartCanvas) return;
    if (chartInst) chartInst.destroy();
    const labels = data.stability.map(s => s.period);
    const vals   = data.stability.map(s => s.accuracy_pct);
    chartInst = new Chart(chartCanvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Accuracy %',
          data: vals,
          borderColor: '#C96442',
          backgroundColor: 'rgba(201,100,66,.08)',
          tension: 0.35,
          fill: true,
          pointRadius: 5,
          pointBackgroundColor: '#C96442',
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            min: 50,
            max: 100,
            ticks: { callback: (v) => v + '%' },
            grid: { color: '#E7E0D5' },
          },
          x: { grid: { color: '#E7E0D5' } },
        },
      },
    });
  });

  // Build by-class bar chart
  $effect(() => {
    if (!data || !classCanvas) return;
    if (classInst) classInst.destroy();
    const labels = data.by_class.map(c => c.label);
    const vals   = data.by_class.map(c => c.accuracy_pct);
    const colors = ['#C96442', '#6F8F6A', '#C7913B'];
    classInst = new Chart(classCanvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Accuracy %',
          data: vals,
          backgroundColor: colors,
          borderRadius: 8,
          barThickness: 40,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            min: 0,
            max: 100,
            ticks: { callback: (v) => v + '%' },
            grid: { color: '#E7E0D5' },
          },
          x: { grid: { display: false } },
        },
      },
    });
  });

  function exportBrief() {
    if (!data) return;
    const lines = [
      `CFC Forecasting Results — ${new Date().toLocaleDateString()}`,
      ``,
      `Accuracy: ${data.accuracy_pct}% (+${data.improvement_pct}% vs simple methods)`,
      `Safe level accuracy: ${data.safe_level_honesty_pct}%`,
      `Max level accuracy: ${data.max_level_honesty_pct}%`,
      `Estimated cost saving: ${data.cost_saving_pct}%`,
      ``,
      `By product tier:`,
      ...data.by_class.map(c => `  ${c.label}: ${c.accuracy_pct}% (${c.vol_share_pct}% of volume)`),
      ``,
      `Stability: ${data.stable_all_periods ? 'Consistent across all 3 test periods' : 'Varies by period'}`,
      ...data.stability.map(s => `  ${s.period}: ${s.accuracy_pct}%`),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'cfc-results-brief.txt'; a.click();
  }
</script>

<div class="flex items-center justify-between mb-6">
  <div>
    <h1 class="text-3xl mb-1">Results</h1>
    <p class="text-muted text-sm">Forecasting accuracy · backtest across 3 months · 608 k order-days</p>
  </div>
  <button class="btn-subtle btn-sm" onclick={exportBrief} disabled={!data} aria-label="Export results brief"><Icon name="download" class="w-3.5 h-3.5" /> Export brief</button>
</div>

{#if error}
  <div class="card border-warn text-warn">{error}</div>
{:else if !data}
  <div class="text-muted animate-pulse">Loading results…</div>
{:else}
  <!-- ── KPI cards ── -->
  <div class="grid grid-cols-3 gap-4 mb-6">
    <div class="card">
      <div class="text-xs text-muted mb-1 uppercase tracking-wide">Accuracy</div>
      <div class="text-4xl font-display text-accent">{data.accuracy_pct}%</div>
      <div class="text-sm text-muted mt-1">
        +{data.improvement_pct}% vs simple methods
      </div>
    </div>

    <div class="card">
      <div class="text-xs text-muted mb-1 uppercase tracking-wide">Safe levels hit target</div>
      <div class="text-4xl font-display text-sage">{data.safe_level_honesty_pct}%</div>
      <div class="text-sm text-muted mt-1">
        Max levels: {data.max_level_honesty_pct}% · both calibrated
      </div>
    </div>

    <div class="card">
      <div class="text-xs text-muted mb-1 uppercase tracking-wide">Estimated cost saving</div>
      <div class="text-4xl font-display" style="color:#C7913B">{data.cost_saving_pct}%</div>
      <div class="text-sm text-muted mt-1">vs ordering on simple moving average</div>
    </div>
  </div>

  <!-- ── accuracy over time + by-class ── -->
  <div class="grid grid-cols-2 gap-5 mb-6">
    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-base">Accuracy by period</h3>
        {#if data.stable_all_periods}
          <span class="text-xs bg-sage/10 text-sage px-3 py-1 rounded-full inline-flex items-center gap-1.5">
            <Icon name="check" class="w-3.5 h-3.5" /> stable {data.stability.length}/{data.stability.length} months
          </span>
        {:else}
          <span class="text-xs bg-warn/10 text-warn px-3 py-1 rounded-full">varies by period</span>
        {/if}
      </div>
      <canvas bind:this={chartCanvas}></canvas>
    </div>

    <div class="card">
      <h3 class="text-base mb-3">Accuracy by product tier</h3>
      <canvas bind:this={classCanvas}></canvas>
      <div class="mt-3 grid grid-cols-3 gap-2 text-xs text-center text-muted">
        {#each data.by_class as c}
          <div>
            <div class="font-medium text-ink">{c.label}</div>
            <div>{c.vol_share_pct}% of volume</div>
          </div>
        {/each}
      </div>
    </div>
  </div>

  <!-- ── period breakdown table ── -->
  <div class="card">
    <h3 class="text-base mb-3">Period-by-period breakdown</h3>
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-muted border-b border-line">
          <th class="pb-2 font-medium">Period</th>
          <th class="pb-2 font-medium text-right">Accuracy</th>
          <th class="pb-2 font-medium text-right">Beat simple?</th>
        </tr>
      </thead>
      <tbody>
        {#each data.stability as fold}
          <tr class="border-b border-line/50 hover:bg-bg transition-colors">
            <td class="py-2">{fold.period}</td>
            <td class="py-2 text-right font-display">{fold.accuracy_pct}%</td>
            <td class="py-2 text-right">
              {#if fold.beat_simple}
                <span class="text-sage text-xs inline-flex items-center gap-1"><Icon name="check" class="w-3.5 h-3.5" /> Yes</span>
              {:else}
                <span class="text-warn text-xs inline-flex items-center gap-1"><Icon name="x" class="w-3.5 h-3.5" /> No</span>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
