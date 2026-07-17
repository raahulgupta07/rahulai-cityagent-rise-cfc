<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { experimentsApi, type Evidence } from '$lib/api/experiments';
  import Icon from '$lib/Icon.svelte';

  let ev = $state<Evidence | null>(null);
  let err = $state<string | null>(null);
  let msg = $state<string | null>(null);
  let version = $derived($page.params.version);

  onMount(async () => {
    try { ev = await experimentsApi.evidence(version); }
    catch (e) { err = String(e); }
  });

  let busy = $state(false);

  async function pollJob(id: string): Promise<boolean> {
    for (let i = 0; i < 120; i++) {
      await new Promise(r => setTimeout(r, 3000));
      let s;
      try { s = await experimentsApi.jobStatus(id); } catch { continue; }
      msg = `Applying in Fabric… ${s.status}`;
      if (s.status === 'Completed') return true;
      if (s.status === 'Failed' || s.status === 'Cancelled') {
        msg = `Fabric job ${s.status}${s.failure ? ': ' + s.failure : ''}`; return false;
      }
    }
    msg = 'Fabric job still running — refresh shortly.'; return false;
  }

  async function promote() {
    busy = true;
    try {
      const r = await experimentsApi.promote(version);
      if (r.mode === 'fabric' && r.job_id) {
        msg = `Approved — applying in Fabric (job ${r.job_id.slice(0, 8)})…`;
        if (await pollJob(r.job_id)) { msg = `${version} is now the live champion.`; ev = await experimentsApi.evidence(version); }
      } else {
        msg = r.changed ? `${version} promoted to live.` : `${version} already live.`;
      }
    } catch (e) { msg = String(e); } finally { busy = false; }
  }
  async function reject() {
    busy = true;
    try { await experimentsApi.reject(version); msg = `Rejected ${version}. Champion unchanged.`; }
    catch (e) { msg = String(e); } finally { busy = false; }
  }
  async function rerun() {
    try { const r = await experimentsApi.rerun(version); msg = `Re-run queued (cutoff ${r.cutoff}).`; }
    catch (e) { msg = String(e); }
  }

  // chart geometry helpers
  let maxResid = $derived(ev ? Math.max(1, ...ev.residuals.map(r => r.n)) : 1);
  let scatMax = $derived(ev ? Math.max(1, ...ev.scatter.map(p => Math.max(p.actual, p.pred))) : 1);
  let maxClass = $derived(ev ? Math.max(0.01, ...ev.by_class.map(c => c.wmape)) : 1);
  function acc(w: number) { return ((1 - w) * 100).toFixed(1); }
</script>

<div class="flex flex-col gap-5">
  <a href="/leaderboard" class="text-sm text-accent font-semibold w-max">← Model Leaderboard</a>

  {#if err}
    <div class="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{err}</div>
  {:else if !ev}
    <div class="text-muted text-sm">Loading experiment…</div>
  {:else}
    {#if msg}<div class="rounded-xl bg-accent/8 border border-accent/25 px-4 py-3 text-sm">{msg}</div>{/if}

    <!-- hero -->
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-[22px] font-extrabold tracking-tight">{ev.version} · {ev.name}
          <span class="text-[11px] font-extrabold px-2.5 py-1 rounded-full align-middle ml-1.5
                       {ev.is_champion ? 'bg-sage/15 text-sage' : 'bg-line text-muted'}">{ev.status}</span>
        </h1>
        <div class="text-[13px] text-muted font-mono mt-1">
          cutoff {ev.cutoff} · trained on {(ev.train_rows ?? 0).toLocaleString()} rows · holdout {(ev.holdout_rows ?? 0).toLocaleString()}
        </div>
      </div>
      <div class="flex gap-2 flex-wrap">
        <a class="btn-teal" href={`/api/order/export.xlsx`} download><Icon name="download" class="w-4 h-4" /> Export order plan (outlet × SKU .xlsx)</a>
        <button class="btn-subtle" onclick={rerun} disabled={busy}>Re-run</button>
        {#if !ev.is_champion}
          <button class="btn-subtle" onclick={reject} disabled={busy}>Reject</button>
          <button class="btn-primary" onclick={promote} disabled={busy}>Approve &amp; promote</button>
        {/if}
      </div>
    </div>

    {#if ev.note}<div class="text-xs text-muted italic">{ev.note}</div>{/if}

    <!-- KPI strip -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {#each [
        {l:'WMAPE (backtest)', v:ev.metrics.wmape.toFixed(3), n:`+${(((ev.metrics.floor_wmape-ev.metrics.wmape)/ev.metrics.floor_wmape)*100).toFixed(0)}% vs floor ${ev.metrics.floor_wmape}`, hero:true},
        {l:'P85 coverage', v:ev.metrics.cover_p85+'%', n:'target 85%'},
        {l:'P95 coverage', v:ev.metrics.cover_p95+'%', n:'target 95%'},
        {l:'P50 bias', v:ev.metrics.p50_bias.toFixed(3), n:'near-unbiased'},
        {l:'Class-A WMAPE', v:(ev.metrics.class_a_wmape??0).toFixed(3), n:'80% of volume'},
        {l:'Test rows', v:(ev.metrics.test_rows/1e3).toFixed(0)+'k', n:'walk-forward'}
      ] as k}
        <div class="card !p-4">
          <div class="text-[11px] font-bold text-muted uppercase tracking-wide">{k.l}</div>
          <div class="font-mono font-extrabold text-2xl mt-1.5 {k.hero ? 'text-accent' : ''}">{k.v}</div>
          <div class="text-xs text-muted mt-1">{k.n}</div>
        </div>
      {/each}
    </div>

    <!-- feature importance + calibration -->
    <div class="grid lg:grid-cols-2 gap-4">
      <div class="card">
        <h3 class="text-[15px] font-extrabold">Feature impact</h3>
        <div class="text-[12.5px] text-muted mb-3">Gain importance (LightGBM), top 12</div>
        <div class="space-y-1.5">
          {#each ev.feature_importance as f}
            <div class="flex items-center gap-2 text-xs">
              <span class="font-mono w-28 truncate">{f.name}</span>
              <div class="flex-1 h-3 rounded bg-line overflow-hidden">
                <div class="h-full rounded bg-accent" style="width:{f.gain*100}%"></div>
              </div>
              <span class="font-mono text-muted w-9 text-right">{f.gain.toFixed(2)}</span>
            </div>
          {/each}
        </div>
      </div>
      <div class="card">
        <h3 class="text-[15px] font-extrabold">Quantile calibration</h3>
        <div class="text-[12.5px] text-muted mb-3">Actual coverage vs target quantile</div>
        <svg viewBox="0 0 400 220" class="w-full">
          <line x1="40" y1="180" x2="380" y2="180" stroke="#E9E7E1"/><line x1="40" y1="20" x2="40" y2="180" stroke="#E9E7E1"/>
          <line x1="40" y1="180" x2="380" y2="20" stroke="#C9C6BF" stroke-dasharray="4 4"/>
          <polyline
            points={'40,180 ' + ev.calibration.map(c => `${40+(c.target/100)*340},${180-((c.actual??0)/100)*160}`).join(' ')}
            fill="none" stroke="#BE6B41" stroke-width="2.5"/>
          {#each ev.calibration as c}
            <circle cx={40+(c.target/100)*340} cy={180-((c.actual??0)/100)*160} r="4" fill="#BE6B41"/>
            <text x={40+(c.target/100)*340} y={180-((c.actual??0)/100)*160-8} font-size="10" fill="#737A88" text-anchor="middle" font-family="monospace">P{c.level}→{c.actual}</text>
          {/each}
        </svg>
      </div>
    </div>

    <!-- residuals + scatter -->
    <div class="grid lg:grid-cols-2 gap-4">
      <div class="card">
        <h3 class="text-[15px] font-extrabold">Residuals (actual − P50)</h3>
        <div class="text-[12.5px] text-muted mb-3">Centered near zero, symmetric</div>
        <svg viewBox="0 0 400 200" class="w-full">
          <line x1="20" y1="175" x2="380" y2="175" stroke="#E9E7E1"/>
          {#each ev.residuals as r, i}
            {@const bw = 340/ev.residuals.length}
            <rect x={20 + i*bw} y={175 - (r.n/maxResid)*150} width={bw-2} height={(r.n/maxResid)*150} rx="1.5"
                  fill="#BE6B41" opacity={Math.abs(r.bin) < 6 ? 1 : 0.55}/>
          {/each}
          <line x1="200" y1="20" x2="200" y2="175" stroke="#C9C6BF" stroke-dasharray="3 3"/>
        </svg>
      </div>
      <div class="card">
        <h3 class="text-[15px] font-extrabold">Forecast vs actual</h3>
        <div class="text-[12.5px] text-muted mb-3">Sample of outlet × product × day · dashed = perfect</div>
        <svg viewBox="0 0 400 200" class="w-full">
          <line x1="30" y1="170" x2="380" y2="170" stroke="#E9E7E1"/><line x1="30" y1="20" x2="30" y2="170" stroke="#E9E7E1"/>
          <line x1="30" y1="170" x2="360" y2="30" stroke="#C9C6BF" stroke-dasharray="4 4"/>
          {#each ev.scatter as p}
            <circle cx={30 + (p.actual/scatMax)*330} cy={170 - (p.pred/scatMax)*140} r="2.6" fill="#BE6B41" opacity="0.5"/>
          {/each}
        </svg>
      </div>
    </div>

    <!-- accuracy by class + folds -->
    <div class="grid lg:grid-cols-2 gap-4">
      <div class="card">
        <h3 class="text-[15px] font-extrabold">Accuracy by ABC class</h3>
        <div class="text-[12.5px] text-muted mb-3">WMAPE (lower = better) · champion vs floor {ev.metrics.floor_wmape}</div>
        <div class="space-y-2.5 mt-2">
          {#each ev.by_class as cl}
            <div class="flex items-center gap-3 text-sm">
              <span class="w-16 font-semibold">Class {cl.cls}</span>
              <div class="flex-1 h-4 rounded bg-line overflow-hidden">
                <div class="h-full rounded bg-accent" style="width:{(cl.wmape/maxClass)*100}%"></div>
              </div>
              <span class="font-mono text-muted w-24 text-right">{cl.wmape.toFixed(3)} · {acc(cl.wmape)}%</span>
            </div>
          {/each}
        </div>
      </div>
      <div class="card">
        <h3 class="text-[15px] font-extrabold">Per-fold WMAPE</h3>
        <div class="text-[12.5px] text-muted mb-3">Walk-forward, rolling monthly folds</div>
        <div class="space-y-2.5 mt-2">
          {#each ev.folds as f}
            <div class="flex items-center gap-3 text-sm">
              <span class="w-20 font-mono">{f.fold}</span>
              <div class="flex-1 h-4 rounded bg-line overflow-hidden">
                <div class="h-full rounded bg-sage" style="width:{(f.wmape/maxClass)*100}%"></div>
              </div>
              <span class="font-mono text-muted w-14 text-right">{f.wmape.toFixed(3)}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>

    <!-- hyperparams + run history -->
    <div class="grid lg:grid-cols-2 gap-4">
      <div class="card">
        <h3 class="text-[15px] font-extrabold mb-3">Hyperparameters</h3>
        <table class="w-full text-sm">
          <tbody>
            {#each Object.entries(ev.hyperparams) as [k, v]}
              <tr class="border-b border-line/60 last:border-0">
                <td class="py-1.5 text-muted">{k}</td>
                <td class="py-1.5 font-mono text-right">{v}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="card">
        <h3 class="text-[15px] font-extrabold mb-3">Run history</h3>
        {#if ev.run_history.length}
          {#each ev.run_history as r}
            <div class="flex items-center gap-3 py-2 border-t border-line/60 first:border-0 text-[13px]">
              <span class="w-2 h-2 rounded-full flex-none {r.kind==='retrain'?'bg-sage':r.drift?'bg-warn':'bg-accent'}"></span>
              <span class="flex-1">{r.kind}{r.note ? ' · ' + r.note : ''}</span>
              <span class="font-mono text-muted text-xs">{r.ts ?? ''}</span>
            </div>
          {/each}
        {:else}<div class="text-sm text-muted">No runs logged yet.</div>{/if}
      </div>
    </div>

    <!-- config -->
    <div class="card">
      <h3 class="text-[15px] font-extrabold mb-1">Configuration</h3>
      <div class="text-[12.5px] text-muted mb-3">{ev.feats.length} features · {ev.cats.length} categorical</div>
      <div class="flex flex-wrap gap-1.5 mb-2.5">
        {#each ev.feats.filter(f => !ev.cats.includes(f)) as f}
          <span class="font-mono text-[11.5px] bg-bg border border-line rounded px-2 py-0.5">{f}</span>
        {/each}
      </div>
      <div class="flex flex-wrap gap-1.5">
        {#each ev.cats as c}
          <span class="font-mono text-[11.5px] bg-accent/10 border border-accent/20 rounded px-2 py-0.5 text-accent">{c}</span>
        {/each}
      </div>
    </div>
  {/if}
</div>
