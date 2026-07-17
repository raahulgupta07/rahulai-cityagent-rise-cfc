<script lang="ts">
  import { onMount } from 'svelte';
  import { settingsApi } from '$lib/api/settings';
  import type { SettingsOverview, ScheduleJob, AuditEvent, SsoStatus } from '$lib/api/settings';
  import Icon from '$lib/Icon.svelte';

  // ── state ─────────────────────────────────────────────────────────────────
  let overview   = $state<SettingsOverview | null>(null);
  let sso        = $state<SsoStatus | null>(null);
  let jobs       = $state<ScheduleJob[]>([]);
  let audit      = $state<AuditEvent[]>([]);
  let showAudit  = $state(false);
  let loading    = $state(true);
  let error      = $state<string | null>(null);
  let reconnecting = $state(false);
  let reconnectMsg = $state<string | null>(null);
  let togglingJob  = $state<string | null>(null);
  let runningJob   = $state<string | null>(null);

  // ── load ──────────────────────────────────────────────────────────────────
  async function load() {
    loading = true; error = null;
    try {
      const [ov, sc] = await Promise.all([
        settingsApi.getSettings(),
        settingsApi.getSchedule(),
      ]);
      overview = ov;
      jobs     = sc.jobs;
      settingsApi.getSso().then(s => sso = s).catch(() => {});
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  onMount(load);

  // ── actions ───────────────────────────────────────────────────────────────
  async function doReconnect() {
    reconnecting = true; reconnectMsg = null;
    try {
      const r = await settingsApi.reconnectFabric();
      reconnectMsg = r.message;
    } catch (e: any) {
      reconnectMsg = `Error: ${e.message}`;
    } finally {
      reconnecting = false;
    }
  }

  async function doToggle(jobId: string) {
    togglingJob = jobId;
    try {
      const r = await settingsApi.toggleJob(jobId);
      jobs = jobs.map(j => j.id === jobId ? r.job : j);
    } catch (e: any) {
      alert(`Toggle failed: ${e.message}`);
    } finally {
      togglingJob = null;
    }
  }

  async function doRunNow(jobId: string) {
    if (!confirm(`Run "${jobs.find(j => j.id === jobId)?.label}" now?`)) return;
    runningJob = jobId;
    try {
      await settingsApi.runNow(jobId);
      await new Promise(r => setTimeout(r, 800));
      await load();
    } catch (e: any) {
      alert(`Run failed: ${e.message}`);
    } finally {
      runningJob = null;
    }
  }

  async function doLoadAudit() {
    showAudit = !showAudit;
    if (showAudit && audit.length === 0) {
      try {
        const r = await settingsApi.getAudit(50);
        audit = r.events;
      } catch {
        audit = [];
      }
    }
  }
</script>

<div class="space-y-8 max-w-3xl">

  <!-- header -->
  <div>
    <h1 class="font-display text-2xl text-ink">Settings</h1>
    <p class="text-sm text-muted mt-1">System connections, schedule, and configuration</p>
  </div>

  {#if loading}
    <div class="text-muted text-sm animate-pulse">Loading…</div>
  {:else if error}
    <div class="rounded-xl bg-warn/10 border border-warn/30 px-4 py-3 text-sm text-ink">
      Could not load settings: {error}
    </div>
  {:else if overview}

    <!-- ── Database / Fabric ───────────────────────────────────────────────── -->
    <section class="bg-surface rounded-2xl shadow-soft p-6 space-y-4">
      <h2 class="font-display text-base font-semibold text-ink">Database</h2>

      <div class="flex items-center gap-3">
        <span class="w-2.5 h-2.5 rounded-full flex-none {overview.fabric_connected ? 'bg-sage' : 'bg-warn'}"></span>
        <div>
          <p class="text-sm font-medium text-ink">
            Microsoft Fabric
            <span class={`ml-2 text-xs px-2 py-0.5 rounded-full ${
              overview.fabric_connected
                ? 'bg-sage/15 text-sage'
                : 'bg-warn/15 text-warn'
            }`}>
              {overview.fabric_connected ? 'Connected' : 'Disconnected'}
            </span>
          </p>
          <p class="text-xs text-muted mt-0.5 font-mono">{overview.fabric_server}</p>
        </div>
        <button
          onclick={doReconnect}
          disabled={reconnecting}
          class="ml-auto text-xs px-3 py-1.5 rounded-lg border border-line
                 hover:bg-bg text-muted hover:text-ink transition-colors disabled:opacity-50"
        >
          {reconnecting ? 'Checking…' : 'Reconnect'}
        </button>
      </div>

      {#if reconnectMsg}
        <p class="text-xs text-muted bg-bg rounded-lg px-3 py-2">{reconnectMsg}</p>
      {/if}
    </section>

    <!-- ── Schedule ───────────────────────────────────────────────────────── -->
    <section class="bg-surface rounded-2xl shadow-soft p-6 space-y-4">
      <h2 class="font-display text-base font-semibold text-ink">Schedule</h2>
      <p class="text-xs text-muted">
        Jobs run in the background. Toggle to enable; disabled by default for safety.
      </p>

      <div class="space-y-3">
        {#each jobs as job}
          <div class="flex items-start gap-4 bg-bg rounded-xl px-4 py-3">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium text-ink">{job.label}</span>
                <span class="text-xs text-muted bg-surface px-2 py-0.5 rounded-full border border-line">
                  {job.schedule}
                </span>
                {#if job.enabled}
                  <span class="text-xs text-sage bg-sage/10 px-2 py-0.5 rounded-full">enabled</span>
                {:else}
                  <span class="text-xs text-muted bg-line/40 px-2 py-0.5 rounded-full">disabled</span>
                {/if}
              </div>
              <p class="text-xs text-muted mt-1">{job.description}</p>
              {#if job.last_run}
                <p class="text-xs text-muted mt-1">
                  Last run: <span class="text-ink">{job.last_run}</span>
                  {#if job.last_status}
                    — <span class={job.last_status === 'ok' ? 'text-sage' : 'text-warn'}>
                        {job.last_status}
                      </span>
                  {/if}
                </p>
              {:else}
                <p class="text-xs text-muted mt-1">Never run</p>
              {/if}
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <!-- toggle switch -->
              <button
                onclick={() => doToggle(job.id)}
                disabled={togglingJob === job.id}
                title={job.enabled ? 'Disable job' : 'Enable job'}
                class={`relative w-10 h-5 rounded-full transition-colors focus:outline-none
                        ${job.enabled ? 'bg-accent' : 'bg-line'}
                        ${togglingJob === job.id ? 'opacity-50' : ''}`}
              >
                <span class={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow
                              transition-transform ${job.enabled ? 'translate-x-5' : ''}`}></span>
              </button>

              <!-- run now -->
              <button
                onclick={() => doRunNow(job.id)}
                disabled={runningJob === job.id}
                title="Run now (admin)"
                class="text-xs px-2.5 py-1 rounded-lg border border-line hover:bg-bg
                       text-muted hover:text-ink transition-colors disabled:opacity-40"
              >
                {#if runningJob === job.id}…{:else}<Icon name="play" class="w-3.5 h-3.5" />{/if}
              </button>
            </div>
          </div>
        {/each}
      </div>
    </section>

    <!-- ── Economics status ───────────────────────────────────────────────── -->
    {#if overview.econ}
      <section class="bg-surface rounded-2xl shadow-soft p-6 space-y-3">
        <h2 class="font-display text-base font-semibold text-ink">Economics</h2>

        <div class={`rounded-xl px-4 py-3 text-sm ${
          overview.econ.warn
            ? 'bg-warn/10 border border-warn/30'
            : 'bg-sage/10 border border-sage/30'
        }`}>
          <div class="flex items-start gap-2">
            <span class="mt-0.5 {overview.econ.warn ? 'text-warn' : 'text-sage'}">
              {#if overview.econ.warn}<Icon name="info" class="w-4 h-4" />{:else}<Icon name="check" class="w-4 h-4" />{/if}
            </span>
            <div>
              <p class="font-medium text-ink">{overview.econ.message}</p>
              {#if overview.econ.row_count != null}
                <p class="text-xs text-muted mt-1">{overview.econ.row_count} products loaded</p>
              {/if}
            </div>
          </div>
        </div>

        {#if overview.econ.warn}
          <p class="text-xs text-muted px-1">
            Edit <code class="bg-bg px-1 rounded">data/product_econ.csv</code> with real
            per-product gross margin and shelf-life days, then re-run order quantity build.
            Newsvendor only differentiates orders once critical ratios vary per product.
          </p>
        {/if}
      </section>
    {/if}

    <!-- ── Single Sign-On (OIDC / Keycloak) ───────────────────────────────── -->
    <section class="bg-surface rounded-2xl shadow-soft p-6 space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="font-display text-base font-semibold text-ink">Single Sign-On</h2>
        {#if sso}
          <span class={`px-2 py-0.5 rounded-full text-xs font-medium ${
            sso.enabled ? 'bg-sage/15 text-sage' : 'bg-line text-muted'}`}>
            {sso.enabled ? `${sso.provider} · on` : 'off'}
          </span>
        {/if}
      </div>

      {#if !sso}
        <p class="text-sm text-muted">Loading…</p>
      {:else if !sso.enabled}
        <p class="text-sm text-muted">
          SSO is off. Register a confidential client in Keycloak, then set the
          <code class="text-xs">OIDC_*</code> keys in <code class="text-xs">.env.prod</code> and
          rebuild the API. Email login keeps working alongside SSO.
        </p>
        <div class="text-xs text-muted">
          <div class="font-semibold text-ink mb-1">Redirect URI to register in Keycloak:</div>
          <code class="block bg-line/50 rounded-lg px-3 py-2 break-all">{sso.redirect_uri_hint}</code>
        </div>
        <div class="text-xs text-muted">
          Env keys: {#each sso.env_keys as k, i}<code class="text-[11px]">{k}</code>{i < sso.env_keys.length - 1 ? ' · ' : ''}{/each}
        </div>
      {:else}
        <div class="grid sm:grid-cols-2 gap-3 text-sm">
          <div><span class="text-muted">Provider</span><div class="text-ink font-medium">{sso.provider}</div></div>
          <div><span class="text-muted">Discovery</span>
            <div class={`font-medium ${sso.discovery_ok ? 'text-sage' : 'text-warn'}`}>
              {sso.discovery_ok === null ? '—' : sso.discovery_ok ? 'reachable ✓' : 'unreachable ✗'}
            </div>
          </div>
          <div class="sm:col-span-2"><span class="text-muted">Issuer</span><div class="text-ink font-mono text-xs break-all">{sso.issuer ?? '—'}</div></div>
          <div><span class="text-muted">Client ID</span><div class="text-ink font-mono text-xs">{sso.client_id ?? '—'}</div></div>
          <div><span class="text-muted">Default role</span><div class="text-ink font-medium">{sso.default_role}</div></div>
          <div class="sm:col-span-2"><span class="text-muted">Redirect URI</span><div class="text-ink font-mono text-xs break-all">{sso.redirect_uri ?? sso.redirect_uri_hint}</div></div>
        </div>
        {#if sso.error}
          <p class="text-xs text-warn">Discovery error: {sso.error}</p>
        {/if}
      {/if}
    </section>

    <!-- ── Access + Audit ─────────────────────────────────────────────────── -->
    <section class="bg-surface rounded-2xl shadow-soft p-6 space-y-4">
      <h2 class="font-display text-base font-semibold text-ink">Access</h2>

      <div class="flex items-center gap-3 text-sm">
        <span class="text-muted">Auth mode:</span>
        <span class={`px-2 py-0.5 rounded-full text-xs font-medium ${
          overview.auth_mode === 'dev-bypass'
            ? 'bg-warn/15 text-warn'
            : 'bg-sage/15 text-sage'
        }`}>
          {overview.auth_mode === 'dev-bypass' ? 'Dev bypass (AUTH_DISABLED=1)' : 'Token auth'}
        </span>
      </div>

      <div class="flex items-center gap-3 text-sm">
        <span class="text-muted">Signed in as:</span>
        <span class="text-ink font-medium">{overview.current_user.actor}</span>
        <span class="text-xs bg-bg border border-line px-2 py-0.5 rounded-full text-muted">
          {overview.current_user.role}
        </span>
      </div>

      <div class="pt-2 border-t border-line">
        <button
          onclick={doLoadAudit}
          class="text-sm text-accent hover:underline"
        >
          {showAudit ? 'Hide' : 'Show'} audit log
        </button>

        {#if showAudit}
          <div class="mt-3 max-h-64 overflow-y-auto rounded-xl border border-line">
            {#if audit.length === 0}
              <p class="text-xs text-muted px-4 py-3">No audit events yet.</p>
            {:else}
              <table class="w-full text-xs">
                <thead class="sticky top-0 bg-bg border-b border-line">
                  <tr>
                    <th class="text-left px-3 py-2 text-muted font-medium">Time</th>
                    <th class="text-left px-3 py-2 text-muted font-medium">Actor</th>
                    <th class="text-left px-3 py-2 text-muted font-medium">Action</th>
                    <th class="text-left px-3 py-2 text-muted font-medium">Target</th>
                  </tr>
                </thead>
                <tbody>
                  {#each audit as ev}
                    <tr class="border-b border-line/50 hover:bg-bg/50">
                      <td class="px-3 py-2 text-muted font-mono whitespace-nowrap">
                        {ev.ts.slice(0, 16).replace('T', ' ')}
                      </td>
                      <td class="px-3 py-2 text-ink">{ev.actor}</td>
                      <td class="px-3 py-2 text-accent">{ev.action}</td>
                      <td class="px-3 py-2 text-muted">{ev.target}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            {/if}
          </div>
        {/if}
      </div>
    </section>

    <!-- ── Brand ──────────────────────────────────────────────────────────── -->
    <section class="bg-surface rounded-2xl shadow-soft p-6">
      <h2 class="font-display text-base font-semibold text-ink mb-3">Brand</h2>
      <div class="flex items-center gap-4">
        <div class="w-10 h-10 rounded-full bg-accent/10 flex items-center justify-center text-accent select-none">
          <Icon name="diamond" class="w-5 h-5" />
        </div>
        <div>
          <p class="text-sm font-medium text-ink">{overview.brand}</p>
          <p class="text-xs text-muted">v{overview.version}</p>
        </div>
      </div>
    </section>

  {/if}
</div>
