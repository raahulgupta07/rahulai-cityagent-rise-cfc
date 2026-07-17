<script lang="ts">
  import { onMount } from 'svelte';
  import { experimentsApi } from '$lib/api/experiments';
  import type { ExperimentRow, Compare } from '$lib/api/experiments';
  import Icon from '$lib/Icon.svelte';

  let rows      = $state<ExperimentRow[]>([]);
  let champion  = $state<string | null>(null);
  let unitsOff  = $state<number | null>(null);
  let loading   = $state(true);
  let error     = $state<string | null>(null);

  // Simple (everyone) vs Expert (data-science) view. Simple is the default.
  let mode      = $state<'simple' | 'expert'>('simple');
  onMount(() => {
    try { const m = localStorage.getItem('lb_mode'); if (m === 'expert' || m === 'simple') mode = m; } catch {}
  });
  function setMode(m: 'simple' | 'expert') { mode = m; try { localStorage.setItem('lb_mode', m); } catch {} }

  let selected  = $state<string[]>([]);      // up to 2 versions
  let cmp       = $state<Compare | null>(null);
  let rerunMsg  = $state<string | null>(null);
  let jobMsg    = $state<string | null>(null);
  let busy      = $state<string | null>(null);   // version currently promoting/rejecting

  let maxAcc = $derived(Math.max(1, ...rows.map(r => r.accuracy ?? 0)));

  // Approval gate: best non-champion candidate vs the live champion.
  let champRow  = $derived(rows.find(r => r.is_champion) ?? null);
  let challenger = $derived(rows.find(r => !r.is_champion) ?? null);
  let accDelta  = $derived(
    challenger && champRow && challenger.accuracy != null && champRow.accuracy != null
      ? Math.round((challenger.accuracy - champRow.accuracy) * 10) / 10 : null);

  onMount(load);
  async function load() {
    loading = true;
    try {
      const lb = await experimentsApi.list();
      rows = lb.experiments;
      champion = lb.champion;
      unitsOff = lb.champion_units_off ?? null;
    } catch (e) { error = String(e); } finally { loading = false; }
  }

  async function toggle(v: string) {
    if (selected.includes(v)) selected = selected.filter(x => x !== v);
    else if (selected.length < 2) selected = [...selected, v];
    else selected = [selected[1], v];              // slide window
    cmp = null;
    if (selected.length === 2) {
      try { cmp = await experimentsApi.compare(selected[0], selected[1]); } catch (e) { error = String(e); }
    }
  }

  async function rerun(v: string, ev: Event) {
    ev.stopPropagation();
    rerunMsg = null;
    try {
      const d = await experimentsApi.rerun(v);
      rerunMsg = `Queued a fresh experiment reusing ${v}'s window (${d.cutoff}). Watch it on the Pipeline page.`;
    } catch (e) { rerunMsg = String(e); }
  }

  async function pollJob(id: string) {
    // Poll a Fabric promote job until it settles; drives the status line.
    for (let i = 0; i < 120; i++) {
      await new Promise(r => setTimeout(r, 3000));
      let s;
      try { s = await experimentsApi.jobStatus(id); } catch { continue; }
      jobMsg = `Applying in Fabric… ${s.status}`;
      if (s.status === 'Completed') return true;
      if (s.status === 'Failed' || s.status === 'Cancelled') {
        jobMsg = `Fabric job ${s.status}${s.failure ? ': ' + s.failure : ''}`;
        return false;
      }
    }
    jobMsg = 'Fabric job still running — refresh shortly.';
    return false;
  }

  async function makeLive(v: string, ev?: Event) {
    ev?.stopPropagation();
    rerunMsg = null; jobMsg = null; busy = v;
    try {
      const r = await experimentsApi.promote(v);
      if (r.mode === 'fabric' && r.job_id) {
        jobMsg = `Approved ${v} — applying in Fabric (job ${r.job_id.slice(0, 8)})…`;
        const ok = await pollJob(r.job_id);
        if (ok) { jobMsg = `${v} is now the live champion.`; await load(); }
      } else {
        rerunMsg = r.changed ? `${v} is now the live model${r.previous ? ` (was ${r.previous})` : ''}.` : `${v} is already live.`;
        await load();
      }
    } catch (e) { rerunMsg = String(e); } finally { busy = null; }
  }

  async function rejectVersion(v: string, ev?: Event) {
    ev?.stopPropagation();
    rerunMsg = null; jobMsg = null; busy = v;
    try {
      await experimentsApi.reject(v);
      rerunMsg = `Rejected ${v}. Champion ${champion ?? '—'} stays live.`;
    } catch (e) { rerunMsg = String(e); } finally { busy = null; }
  }

  function fmtRows(n: number | null) {
    if (n == null) return '—';
    return n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(0) + 'k' : String(n);
  }
  function deltaCls(v: number | null, goodPositive = true) {
    if (v == null || v === 0) return 'text-muted';
    const good = goodPositive ? v > 0 : v < 0;
    return good ? 'text-sage' : 'text-warn';
  }
  function sign(v: number | null) { return v == null ? '—' : (v > 0 ? '+' : '') + v; }

  // ── plain-language translation (Simple view) ────────────────────────────────
  function grade(acc: number | null): { g: string; tone: string; say: string } {
    if (acc == null) return { g: '—', tone: 'text-muted', say: 'not scored yet' };
    if (acc >= 70) return { g: 'A', tone: 'text-sage',  say: 'excellent — trust it for ordering' };
    if (acc >= 60) return { g: 'B', tone: 'text-sage',  say: 'good — reliable for daily orders' };
    if (acc >= 50) return { g: 'C', tone: 'text-warn',  say: 'okay — usable, watch the big days' };
    return { g: 'D', tone: 'text-warn', say: 'weak — use with care' };
  }
  // The verdict shown in the decision banner, in plain words.
  let decision = $derived.by(() => {
    if (!challenger || !champRow) return null;
    const d = accDelta ?? 0;
    if (Math.abs(d) < 1)
      return { kind: 'same', head: 'A new forecast is ready — it’s about the same as the one you use now.',
               sub: 'Switching won’t change your orders much. Safe to keep the current one.' };
    if (d >= 1)
      return { kind: 'better', head: `A new forecast is ready — it’s better (about ${d} points more accurate).`,
               sub: 'Switching should make your order suggestions a bit more accurate.' };
    return { kind: 'worse', head: 'A new forecast is ready — but it’s not as good as the one you use now.',
             sub: 'Best to keep the current forecast.' };
  });
</script>

<div class="space-y-6">
  <div class="flex items-end justify-between gap-4 flex-wrap">
    <div>
      <h1 class="font-display text-2xl text-ink mb-1">{mode === 'simple' ? 'Forecast Accuracy' : 'Leaderboard'}</h1>
      <p class="text-sm text-muted max-w-2xl">
        {#if mode === 'simple'}
          How good the forecast is, and whether to switch to a newer one — in plain terms.
        {:else}
          Every trained model, ranked by accuracy on identical validation folds. Pick two to compare, or re-run one with the same window.
        {/if}
      </p>
    </div>
    <div class="flex items-center gap-3">
      <!-- Simple / Expert toggle -->
      <div class="inline-flex rounded-lg border border-line overflow-hidden text-xs font-medium">
        <button class="px-3 py-1.5 transition-colors {mode === 'simple' ? 'bg-accent text-white' : 'bg-surface text-muted hover:bg-bg'}"
                onclick={() => setMode('simple')}>Simple</button>
        <button class="px-3 py-1.5 transition-colors {mode === 'expert' ? 'bg-accent text-white' : 'bg-surface text-muted hover:bg-bg'}"
                onclick={() => setMode('expert')}>Expert</button>
      </div>
      <a class="btn-primary" href="/experiments/run"><Icon name="play" class="w-4 h-4" /> New forecast</a>
      {#if mode === 'expert'}
        <span class="text-xs px-2.5 py-1 rounded-full bg-line text-muted font-medium">{selected.length}/2 selected</span>
      {/if}
    </div>
  </div>

  {#if error}
    <div class="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
  {/if}
  {#if rerunMsg}
    <div class="rounded-xl bg-sage/10 border border-sage/30 px-4 py-3 text-sm text-sage">{rerunMsg}</div>
  {/if}
  {#if jobMsg}
    <div class="rounded-xl bg-accent/10 border border-accent/30 px-4 py-3 text-sm text-accent flex items-center gap-2">
      {#if busy}<Icon name="refresh" class="w-4 h-4 animate-spin" />{/if}{jobMsg}
    </div>
  {/if}

  {#if mode === 'simple'}
    <!-- ══ SIMPLE VIEW — plain language for everyone ══ -->
    {#if loading}
      <div class="card !p-6"><div class="h-5 w-2/3 rounded bg-line animate-pulse"></div></div>
    {:else if !champRow}
      <div class="card !p-6 text-sm text-muted">No forecast yet. Click <strong>New forecast</strong> to create the first one.</div>
    {:else}
      {@const cg = grade(champRow.accuracy)}
      <!-- current forecast, in plain terms -->
      <div class="card !p-6">
        <div class="text-[11px] font-bold text-muted uppercase tracking-wide mb-3">The forecast you use now</div>
        <div class="flex items-center gap-5 flex-wrap">
          <div class="flex items-center justify-center w-16 h-16 rounded-2xl bg-sage/10 {cg.tone} font-display text-4xl font-bold">{cg.g}</div>
          <div class="flex-1 min-w-[220px]">
            <div class="text-lg font-semibold text-ink">Grade {cg.g} · {cg.say}</div>
            <div class="text-sm text-muted mt-0.5">
              {#if unitsOff != null}
                On a normal day the forecast is usually within <strong>~{unitsOff} units</strong> per store — close enough to order from.
              {:else}
                Scored on past sales it hadn’t seen, so the grade reflects real-world accuracy.
              {/if}
            </div>
          </div>
          <a class="btn-subtle btn-sm" href={`/leaderboard/${champRow.version}`}>See the evidence <Icon name="arrowRight" class="w-3.5 h-3.5" /></a>
        </div>
      </div>

      <!-- decision: is there a newer one, and should we switch? -->
      {#if decision && challenger}
        <div class="card !p-6 border {decision.kind === 'better' ? 'border-sage/40' : 'border-line'}">
          <div class="flex items-start gap-3">
            <div class="mt-0.5 flex items-center justify-center w-9 h-9 rounded-xl {decision.kind === 'better' ? 'bg-sage/12 text-sage' : 'bg-accent/10 text-accent'}">
              <Icon name={decision.kind === 'better' ? 'trend' : 'info'} class="w-4 h-4" />
            </div>
            <div class="flex-1">
              <div class="text-base font-semibold text-ink">{decision.head}</div>
              <p class="text-sm text-muted mt-1">{decision.sub}</p>
              <div class="flex gap-2 mt-4">
                {#if decision.kind === 'better'}
                  <button class="btn-primary" disabled={!!busy} onclick={() => makeLive(challenger.version)}>
                    <Icon name="check" class="w-4 h-4" /> Switch to the new one</button>
                  <button class="btn-subtle" disabled={!!busy} onclick={() => rejectVersion(challenger.version)}>Keep current</button>
                {:else}
                  <button class="btn-primary" disabled={!!busy} onclick={() => rejectVersion(challenger.version)}>
                    <Icon name="check" class="w-4 h-4" /> Keep current forecast</button>
                  <button class="btn-subtle" disabled={!!busy} onclick={() => makeLive(challenger.version)}>Switch anyway</button>
                {/if}
              </div>
            </div>
          </div>
        </div>
      {:else}
        <div class="card !p-5 text-sm text-muted flex items-center gap-2">
          <Icon name="check" class="w-4 h-4 text-sage" /> You’re on the best forecast available. Nothing to decide right now.
        </div>
      {/if}

      <button class="text-sm text-accent font-medium hover:underline inline-flex items-center gap-1"
              onclick={() => setMode('expert')}>
        <Icon name="bars" class="w-4 h-4" /> Show details — versions, accuracy scores, charts
      </button>
    {/if}

  {:else}
  <!-- ══ EXPERT VIEW ══ -->
  <!-- Approval gate: a fresh challenger is waiting for a human decision -->
  {#if !loading && challenger && champRow}
    <div class="rounded-2xl border border-accent/30 bg-accent/5 shadow-soft p-5">
      <div class="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div class="text-[11px] font-semibold tracking-wide text-accent uppercase mb-1">Awaiting your approval</div>
          <h2 class="font-display text-lg text-ink">Challenger <span class="font-mono">{challenger.version}</span> vs champion <span class="font-mono">{champRow.version}</span></h2>
          <p class="text-sm text-muted mt-1 max-w-xl">
            Review the scores below. Approve to make the challenger live (applied in Fabric); reject to keep the current champion.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button class="btn-primary" disabled={!!busy} onclick={() => makeLive(challenger!.version)}>
            <Icon name="check" class="w-4 h-4" /> Approve &amp; promote</button>
          <button class="btn-subtle" disabled={!!busy} onclick={() => rejectVersion(challenger!.version)}>
            <Icon name="x" class="w-4 h-4" /> Reject</button>
        </div>
      </div>
      <div class="grid grid-cols-3 gap-3 mt-4">
        <div class="rounded-xl bg-surface border border-line p-3">
          <div class="text-xs text-muted mb-0.5">Accuracy</div>
          <div class="font-mono text-lg tabular-nums">{challenger.accuracy ?? '—'}%
            {#if accDelta != null}<span class="text-xs {accDelta >= 0 ? 'text-sage' : 'text-warn'}">{accDelta >= 0 ? '+' : ''}{accDelta}</span>{/if}
          </div>
          <div class="text-[11px] text-muted">champion {champRow.accuracy ?? '—'}%</div>
        </div>
        <div class="rounded-xl bg-surface border border-line p-3">
          <div class="text-xs text-muted mb-0.5">Calibration</div>
          <div class="font-mono text-lg tabular-nums">{challenger.median_hit ?? '—'}%</div>
          <div class="text-[11px] text-muted">champion {champRow.median_hit ?? '—'}%</div>
        </div>
        <div class="rounded-xl bg-surface border border-line p-3">
          <div class="text-xs text-muted mb-0.5">Train rows</div>
          <div class="font-mono text-lg tabular-nums">{fmtRows(challenger.train_rows)}</div>
          <a class="text-[11px] text-accent hover:underline" href={`/leaderboard/${challenger.version}`}>See full evidence →</a>
        </div>
      </div>
    </div>
  {/if}

  <div class="rounded-2xl border border-line bg-surface shadow-soft overflow-hidden">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line bg-bg text-xs text-muted">
          <th class="text-left px-3 py-2.5 font-medium w-8"></th>
          <th class="text-left px-3 py-2.5 font-medium">Version</th>
          <th class="text-left px-3 py-2.5 font-medium">Window</th>
          <th class="text-left px-3 py-2.5 font-medium">Accuracy</th>
          <th class="text-right px-3 py-2.5 font-medium">Calibration</th>
          <th class="text-right px-3 py-2.5 font-medium">Train rows</th>
          <th class="px-3 py-2.5 font-medium text-center">Action</th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          {#each Array(3) as _}
            <tr class="border-b border-line last:border-0"><td colspan="7" class="px-3 py-3">
              <div class="h-4 rounded bg-line animate-pulse w-2/3"></div></td></tr>
          {/each}
        {:else if rows.length === 0}
          <tr><td colspan="7" class="px-3 py-8 text-center text-muted text-sm">
            No experiments yet — run a retrain on the Pipeline page to register the first one.</td></tr>
        {:else}
          {#each rows as r}
            <tr class="border-b border-line/60 last:border-0 cursor-pointer transition-colors
                       {selected.includes(r.version) ? 'bg-accent/5' : 'hover:bg-bg/60'}"
                onclick={() => toggle(r.version)}>
              <td class="px-3 py-3">
                <input type="checkbox" checked={selected.includes(r.version)} readonly
                       class="accent-accent pointer-events-none" />
              </td>
              <td class="px-3 py-3">
                <span class="font-mono text-xs text-ink">#{r.rank} {r.version}</span>
                {#if r.is_champion}
                  <span class="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-sage/15 text-sage font-semibold inline-flex items-center gap-1"><Icon name="star" class="w-3 h-3" /> champion</span>
                {/if}
              </td>
              <td class="px-3 py-3 text-xs text-muted font-mono">{r.trained_on ?? '—'}</td>
              <td class="px-3 py-3">
                <div class="flex items-center gap-2">
                  <div class="flex-1 h-1.5 rounded-full bg-line overflow-hidden min-w-[70px]">
                    <div class="h-full rounded-full bg-gradient-to-r from-sage to-accent"
                         style="width: {((r.accuracy ?? 0) / maxAcc) * 100}%"></div>
                  </div>
                  <span class="font-mono text-xs tabular-nums w-12 text-right">{r.accuracy ?? '—'}%</span>
                </div>
              </td>
              <td class="px-3 py-3 text-right font-mono text-xs tabular-nums text-muted">{r.median_hit ?? '—'}%</td>
              <td class="px-3 py-3 text-right font-mono text-xs tabular-nums text-muted">{fmtRows(r.train_rows)}</td>
              <td class="px-3 py-3 text-center">
                <div class="flex gap-1.5 justify-center">
                  <a class="btn-primary btn-sm" href={`/leaderboard/${r.version}`} onclick={(e) => e.stopPropagation()}
                     aria-label="Open {r.version} evidence">Details <Icon name="arrowRight" class="w-3.5 h-3.5" /></a>
                  {#if !r.is_champion}
                    <button class="btn-sm inline-flex items-center gap-1.5 rounded-lg bg-sage/10 border border-sage/30 text-sage hover:bg-sage/20 transition-colors font-medium disabled:opacity-50"
                            disabled={busy === r.version} onclick={(e) => makeLive(r.version, e)} aria-label="Make {r.version} the live model">
                      <Icon name="check" class="w-3.5 h-3.5" /> Make live</button>
                  {/if}
                  <button class="btn-subtle btn-sm" onclick={(e) => rerun(r.version, e)} aria-label="Re-run {r.version}">
                    <Icon name="refresh" class="w-3.5 h-3.5" /> Re-run</button>
                </div>
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>

  <!-- compare panel -->
  {#if cmp}
    <div class="grid grid-cols-[1fr_auto_1fr] rounded-2xl border border-line bg-surface shadow-soft overflow-hidden">
      <div class="p-5 bg-accent/5">
        <div class="text-xs font-mono text-muted mb-1">Selected A</div>
        <div class="font-mono font-semibold">{cmp.a.version}</div>
        <div class="mt-3 space-y-1.5 text-sm">
          <div class="flex justify-between border-b border-line/50 pb-1.5">Accuracy <span class="font-mono font-semibold">{cmp.a.accuracy}%</span></div>
          <div class="flex justify-between border-b border-line/50 pb-1.5">Calibration <span class="font-mono font-semibold">{cmp.a.median_hit}%</span></div>
          <div class="flex justify-between">Train rows <span class="font-mono font-semibold">{fmtRows(cmp.a.train_rows)}</span></div>
        </div>
      </div>
      <div class="p-5 bg-bg border-x border-line text-center min-w-[130px]">
        <div class="text-xs font-mono text-muted mb-3">Δ (B − A)</div>
        <div class="space-y-3.5 text-sm mt-1">
          <div class="font-mono font-semibold {deltaCls(cmp.deltas.accuracy, true)}">{sign(cmp.deltas.accuracy)} pts</div>
          <div class="font-mono font-semibold {deltaCls(cmp.deltas.median_hit, true)}">{sign(cmp.deltas.median_hit)} pts</div>
          <div class="font-mono font-semibold text-muted">{sign(cmp.deltas.train_rows == null ? null : Math.round(cmp.deltas.train_rows/1000))}k</div>
        </div>
      </div>
      <div class="p-5 bg-sage/5">
        <div class="text-xs font-mono text-muted mb-1">Selected B</div>
        <div class="font-mono font-semibold">{cmp.b.version}
          {#if cmp.b.is_champion}<span class="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-sage/15 text-sage inline-flex"><Icon name="star" class="w-3 h-3" /></span>{/if}
        </div>
        <div class="mt-3 space-y-1.5 text-sm">
          <div class="flex justify-between border-b border-line/50 pb-1.5">Accuracy <span class="font-mono font-semibold">{cmp.b.accuracy}%</span></div>
          <div class="flex justify-between border-b border-line/50 pb-1.5">Calibration <span class="font-mono font-semibold">{cmp.b.median_hit}%</span></div>
          <div class="flex justify-between">Train rows <span class="font-mono font-semibold">{fmtRows(cmp.b.train_rows)}</span></div>
        </div>
      </div>
    </div>
  {:else if selected.length === 1}
    <p class="text-sm text-muted text-center py-2">Select one more version to compare.</p>
  {/if}
  {/if}
</div>
