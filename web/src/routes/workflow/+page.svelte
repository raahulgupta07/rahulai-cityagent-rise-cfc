<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '$lib/Icon.svelte';
  import { getWorkflow, type WorkflowStatus } from '$lib/api/workflow';

  let s = $state<WorkflowStatus | null>(null);
  let err = $state<string | null>(null);
  let loading = $state(true);
  let selected = $state<string>('gate');   // node id

  onMount(load);
  async function load() {
    loading = true; err = null;
    // exponential backoff (~30s) so a cold/restarting API self-heals instead of "local mode / none"
    for (let i = 0; i < 8; i++) {
      try { s = await getWorkflow(); err = null; break; }
      catch (e) {
        err = String(e);
        if (i < 7) await new Promise(r => setTimeout(r, Math.min(4000, 500 * 2 ** i)));
      }
    }
    loading = false;
  }

  function short(v?: string | null) { return v ?? '—'; }
  function when(t?: string | null) { return t ? String(t).replace('T', ' ').slice(0, 16) : '—'; }

  // node → detail descriptor (fields + deep link), computed from live status
  type Field = { k: string; v: string; tone?: 'good' | 'warn' | 'muted' };
  let detail = $derived.by<{ title: string; icon: string; blurb: string; fields: Field[]; link?: { href: string; label: string } }>(() => {
    const d = s;
    switch (selected) {
      case 'source':
        return { title: 'Fabric data source', icon: 'database',
          blurb: 'Sales stay native in the Lakehouse — read in place, aggregated server-side. You supply the small manual signals.',
          fields: [
            { k: 'Fact table', v: d?.source.table ?? '—' },
            { k: 'Grain', v: d?.source.grain ?? '—' },
            { k: 'You provide', v: d?.source.manual.join(' · ') ?? '—', tone: 'muted' },
            { k: 'Engine', v: d?.fabric ? 'Microsoft Fabric (live)' : 'local fallback', tone: d?.fabric ? 'good' : 'warn' },
          ],
          link: { href: '/data', label: 'Open Data Explorer' } };
      case 'train':
        return { title: 'Training lane · on demand', icon: 'play',
          blurb: 'You launch a real run — the full pipeline trains in Fabric next to the data (~15 min) and registers a challenger.',
          fields: [
            { k: 'Last run', v: short(d?.last_run?.version) },
            { k: 'Last run at', v: when(d?.last_run?.at) },
            { k: 'Total runs', v: String(d?.runs_total ?? 0), tone: 'muted' },
          ],
          link: { href: '/experiments/run', label: 'Run an experiment' } };
      case 'daily':
        return { title: 'Daily lane · automatic', icon: 'rotate',
          blurb: 'A scheduled run refreshes the order plan every day and retrains ONLY when accuracy actually drifted — no daily churn.',
          fields: [
            { k: 'Schedule', v: d?.schedule ? `${d.schedule.type} ${d.schedule.times?.join(', ')}` : 'not set', tone: d?.schedule?.enabled ? 'good' : 'warn' },
            { k: 'Timezone', v: d?.schedule?.timezone ?? '—', tone: 'muted' },
            { k: 'Enabled', v: d?.schedule?.enabled ? 'yes' : 'no', tone: d?.schedule?.enabled ? 'good' : 'warn' },
          ],
          link: { href: '/deploy', label: 'Deploy & schedule' } };
      case 'challenger':
        return { title: 'Challenger', icon: 'diamond',
          blurb: 'Every new run registers as a challenger — never auto-promoted. It waits for a human decision.',
          fields: d?.challenger ? [
            { k: 'Version', v: d.challenger.version },
            { k: 'Accuracy', v: d.challenger.accuracy != null ? d.challenger.accuracy + '%' : '—' },
            { k: 'vs champion', v: d.challenger.delta != null ? (d.challenger.delta >= 0 ? '+' : '') + d.challenger.delta + ' pts' : '—', tone: (d.challenger.delta ?? 0) >= 0 ? 'good' : 'warn' },
            { k: 'Registered', v: when(d.challenger.created), tone: 'muted' },
          ] : [{ k: 'Status', v: 'none waiting', tone: 'muted' }],
          link: { href: '/leaderboard', label: 'Review on Leaderboard' } };
      case 'gate':
        return { title: 'Approval gate · human', icon: 'check',
          blurb: 'Nothing goes live without you. Approve promotes the challenger in Fabric; reject keeps the current champion. Live plans stay on the approved champion until you promote.',
          fields: d?.awaiting_approval && d?.challenger ? [
            { k: 'Awaiting', v: d.challenger.version, tone: 'warn' },
            { k: 'Challenger acc', v: d.challenger.accuracy != null ? d.challenger.accuracy + '%' : '—' },
            { k: 'Champion acc', v: d.champion?.accuracy != null ? d.champion.accuracy + '%' : '—' },
          ] : [{ k: 'Status', v: 'nothing to review', tone: 'good' }],
          link: { href: '/leaderboard', label: 'Approve / Reject' } };
      case 'champion':
        return { title: 'Live champion', icon: 'star',
          blurb: 'The approved model. Every screen reads from it. Rolling back = promoting an older version.',
          fields: [
            { k: 'Version', v: short(d?.champion?.version), tone: 'good' },
            { k: 'Accuracy', v: d?.champion?.accuracy != null ? d.champion.accuracy + '%' : '—' },
            { k: 'Live since', v: when(d?.champion?.since), tone: 'muted' },
          ],
          link: { href: '/results', label: 'Open Model Evidence' } };
      case 'ordering':
        return { title: 'Smart Ordering', icon: 'box',
          blurb: 'Outlet × SKU order quantities from the approved champion, exportable to Excel.',
          fields: [
            { k: 'Plan date', v: d?.order_plan?.date ?? '—' },
            { k: 'Rows', v: d?.order_plan ? d.order_plan.rows.toLocaleString() : '—', tone: 'muted' },
          ],
          link: { href: '/ordering', label: 'Open Smart Ordering' } };
      case 'monitor':
        return { title: 'Monitoring', icon: 'activity',
          blurb: 'Drift and accuracy over time. Feeds the daily lane’s retrain decision.',
          fields: d?.drift ? [
            { k: 'Verdict', v: d.drift.verdict ?? '—', tone: d.drift.accuracy_drift ? 'warn' : 'good' },
            { k: 'Data drift', v: d.drift.data_drift ? 'yes' : 'no', tone: d.drift.data_drift ? 'warn' : 'muted' },
            { k: 'Accuracy drift', v: d.drift.accuracy_drift ? 'yes' : 'no', tone: d.drift.accuracy_drift ? 'warn' : 'good' },
            { k: 'Checked', v: when(d.drift.at), tone: 'muted' },
          ] : [{ k: 'Status', v: 'no check yet', tone: 'muted' }],
          link: { href: '/learning', label: 'Open Monitoring' } };
      default:
        return { title: '', icon: 'info', blurb: '', fields: [] };
    }
  });

  // small helpers for node badges
  function node(id: string) { return selected === id; }
</script>

<div class="grid lg:grid-cols-[1fr_340px] gap-6 items-start">
  <!-- MAP -->
  <div class="space-y-3">
    <div class="flex items-end justify-between gap-3 flex-wrap">
      <div>
        <h1 class="font-display text-2xl text-ink mb-1">Workflow</h1>
        <p class="text-sm text-muted max-w-xl">The whole pipeline, live. Click any step for detail and to jump there.</p>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs px-2.5 py-1 rounded-full font-medium {s?.fabric ? 'bg-sage/15 text-sage' : 'bg-warn/15 text-warn'}">
          {s?.fabric ? 'Fabric · live' : 'local mode'}
        </span>
        <button class="btn-subtle btn-sm" onclick={load} disabled={loading} aria-label="Refresh">
          <Icon name="refresh" class="w-3.5 h-3.5 {loading ? 'animate-spin' : ''}" /> Refresh
        </button>
      </div>
    </div>

    {#if err}
      <div class="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{err}</div>
    {/if}

    <!-- SOURCE -->
    <button class="wf-node {node('source') ? 'wf-on' : ''}" onclick={() => selected = 'source'}>
      <div class="wf-ico"><Icon name="database" class="w-4 h-4" /></div>
      <div class="flex-1 text-left">
        <div class="wf-title">Microsoft Fabric · Lakehouse</div>
        <div class="wf-sub">{s?.source.table ?? 'CFC_Sales_Trans'} · read in place + manual signals</div>
      </div>
    </button>

    <div class="wf-arrow"><span></span></div>

    <!-- LANES -->
    <div class="grid grid-cols-2 gap-3">
      <button class="wf-node wf-lane {node('train') ? 'wf-on' : ''}" onclick={() => selected = 'train'}>
        <div class="wf-ico"><Icon name="play" class="w-4 h-4" /></div>
        <div class="flex-1 text-left">
          <div class="wf-title">Training lane</div>
          <div class="wf-sub">on demand · Run experiment</div>
        </div>
      </button>
      <button class="wf-node wf-lane {node('daily') ? 'wf-on' : ''}" onclick={() => selected = 'daily'}>
        <div class="wf-ico"><Icon name="rotate" class="w-4 h-4" /></div>
        <div class="flex-1 text-left">
          <div class="wf-title">Daily lane</div>
          <div class="wf-sub">
            {#if s?.schedule?.enabled}auto · {s.schedule.times?.join(', ')}{:else}schedule off{/if}
          </div>
        </div>
      </button>
    </div>

    <div class="wf-arrow wf-merge"><span></span></div>

    <!-- CHALLENGER -->
    <button class="wf-node {node('challenger') ? 'wf-on' : ''}" onclick={() => selected = 'challenger'}>
      <div class="wf-ico"><Icon name="diamond" class="w-4 h-4" /></div>
      <div class="flex-1 text-left">
        <div class="wf-title">Challenger registered</div>
        <div class="wf-sub">{s?.challenger ? s.challenger.version + ' · ' + (s.challenger.accuracy ?? '—') + '%' : 'none waiting'}</div>
      </div>
      {#if s?.challenger}<span class="wf-pill bg-line text-muted">promoted = false</span>{/if}
    </button>

    <div class="wf-arrow"><span></span></div>

    <!-- GATE -->
    <button class="wf-node wf-gate {node('gate') ? 'wf-on' : ''}" onclick={() => selected = 'gate'}>
      <div class="wf-ico wf-ico-accent"><Icon name="check" class="w-4 h-4" /></div>
      <div class="flex-1 text-left">
        <div class="wf-title">Approval gate · human decision</div>
        <div class="wf-sub">Approve &amp; promote or reject — nothing goes live without you</div>
      </div>
      {#if s?.awaiting_approval}
        <span class="wf-pill bg-warn/15 text-warn">1 awaiting</span>
      {:else}
        <span class="wf-pill bg-sage/15 text-sage">clear</span>
      {/if}
    </button>

    <div class="wf-arrow"><span></span></div>

    <!-- CHAMPION -->
    <button class="wf-node {node('champion') ? 'wf-on' : ''}" onclick={() => selected = 'champion'}>
      <div class="wf-ico wf-ico-sage"><Icon name="star" class="w-4 h-4" /></div>
      <div class="flex-1 text-left">
        <div class="wf-title">Live champion</div>
        <div class="wf-sub">{s?.champion ? s.champion.version + ' · ' + (s.champion.accuracy ?? '—') + '%' : 'none'}</div>
      </div>
    </button>

    <div class="wf-arrow"><span></span></div>

    <!-- CONSUMPTION -->
    <div class="grid grid-cols-2 gap-3">
      <button class="wf-node wf-lane {node('ordering') ? 'wf-on' : ''}" onclick={() => selected = 'ordering'}>
        <div class="wf-ico"><Icon name="box" class="w-4 h-4" /></div>
        <div class="flex-1 text-left">
          <div class="wf-title">Smart Ordering</div>
          <div class="wf-sub">{s?.order_plan ? s.order_plan.date : '—'}</div>
        </div>
      </button>
      <button class="wf-node wf-lane {node('monitor') ? 'wf-on' : ''}" onclick={() => selected = 'monitor'}>
        <div class="wf-ico"><Icon name="activity" class="w-4 h-4" /></div>
        <div class="flex-1 text-left">
          <div class="wf-title">Monitoring</div>
          <div class="wf-sub">{s?.drift ? s.drift.verdict : '—'}</div>
        </div>
      </button>
    </div>
  </div>

  <!-- DETAIL PANEL -->
  <aside class="card !p-5 lg:sticky lg:top-4">
    <div class="flex items-center gap-2 mb-2">
      <div class="wf-ico wf-ico-accent"><Icon name={detail.icon} class="w-4 h-4" /></div>
      <h2 class="font-display text-lg text-ink">{detail.title}</h2>
    </div>
    <p class="text-sm text-muted mb-4">{detail.blurb}</p>
    <div class="space-y-2 mb-4">
      {#each detail.fields as f}
        <div class="flex items-center justify-between gap-3 text-sm border-b border-line/50 pb-1.5 last:border-0">
          <span class="text-muted">{f.k}</span>
          <span class="font-mono text-right {f.tone === 'good' ? 'text-sage' : f.tone === 'warn' ? 'text-warn' : f.tone === 'muted' ? 'text-muted' : 'text-ink'}">{f.v}</span>
        </div>
      {/each}
    </div>
    {#if detail.link}
      <a class="btn-primary w-full justify-center" href={detail.link.href}>{detail.link.label} <Icon name="arrowRight" class="w-4 h-4" /></a>
    {/if}

    {#if selected === 'champion' && s?.feature_top?.length}
      <div class="mt-5">
        <div class="text-[11px] font-bold text-muted uppercase tracking-wide mb-2">Top drivers</div>
        <div class="space-y-1.5">
          {#each s.feature_top as f, i}
            <div class="flex items-center gap-2 text-xs">
              <span class="font-mono text-muted w-4">{i + 1}</span>
              <div class="flex-1 h-1.5 rounded-full bg-line overflow-hidden">
                <div class="h-full rounded-full bg-accent" style="width: {(f.gain / s.feature_top[0].gain) * 100}%"></div>
              </div>
              <span class="font-mono text-ink w-24 truncate text-right">{f.name}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </aside>
</div>

<style>
  /* Meridian warm skin — hexes mirror tailwind.config.ts */
  .wf-node {
    display: flex; align-items: center; gap: 0.75rem; width: 100%;
    padding: 0.85rem 1rem; border-radius: 0.9rem;
    border: 1px solid #E9E7E1; background: #FFFFFF;
    cursor: pointer; transition: border-color .15s, background .15s, box-shadow .15s;
  }
  .wf-node:hover { background: #FBFAF7; }
  .wf-on { border-color: #BE6B41; box-shadow: 0 0 0 2px rgba(190,107,65,0.18); }
  .wf-lane { padding: 0.75rem 0.9rem; }
  .wf-gate { border-style: dashed; }
  .wf-title { font-weight: 600; font-size: 0.9rem; color: #2A2F3A; }
  .wf-sub { font-size: 0.75rem; color: #737A88; margin-top: 1px; }
  .wf-ico {
    display: grid; place-items: center; width: 2rem; height: 2rem; flex: none;
    border-radius: 0.6rem; background: #FBFAF7; color: #737A88;
  }
  .wf-ico-accent { background: rgba(190,107,65,0.12); color: #BE6B41; }
  .wf-ico-sage { background: rgba(46,139,104,0.15); color: #2E8B68; }
  .wf-pill { font-size: 0.65rem; font-weight: 600; padding: 0.15rem 0.5rem; border-radius: 999px; flex: none; }
  .wf-arrow { display: flex; justify-content: center; height: 0.9rem; }
  .wf-arrow > span { width: 2px; height: 100%; background: #E9E7E1; }
  .wf-merge > span { height: 100%; }
</style>
