<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { authApi } from '$lib/api/auth';
  import Icon from '$lib/Icon.svelte';

  let email = $state('');
  let password = $state('');
  let remember = $state(true);
  let showPw = $state(false);
  let error = $state<string | null>(null);
  let busy = $state(false);

  let ssoEnabled = $state(false);
  let ssoProvider = $state('SSO');
  let ssoUrl = $state('/api/auth/sso/login');

  const today = new Date().toISOString().slice(0, 10);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  const SSO_ERR: Record<string, string> = {
    state: 'SSO session expired — try again.',
    exchange: 'SSO sign-in failed. Check with your admin.',
    discovery: 'SSO provider unreachable. Check with your admin.'
  };
  let ssoError = $derived(SSO_ERR[$page.url.searchParams.get('sso_error') ?? ''] ?? null);

  // if already logged in, skip the form; load SSO config for the button
  $effect(() => {
    authApi.me().then(m => { if (m.authenticated) goto('/'); }).catch(() => {});
    authApi.ssoConfig().then(c => { ssoEnabled = c.enabled; ssoProvider = c.provider; ssoUrl = c.login_url; });
  });

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    error = null; busy = true;
    try {
      await authApi.login(email.trim(), password, remember);
      await goto('/');
    } catch (err) {
      error = err instanceof Error ? err.message : 'Login failed';
    } finally {
      busy = false;
    }
  }
</script>

<div class="min-h-screen bg-surface flex flex-col">
  <!-- top bar -->
  <header class="flex items-center justify-between px-6 md:px-10 py-5">
    <div class="flex items-center gap-2.5">
      <span class="w-9 h-9 rounded-[10px] flex-none grid place-items-center text-white font-extrabold"
            style="background:#BE6B41">R</span>
      <span class="leading-tight">
        <span class="font-extrabold text-ink text-[17px] tracking-tight block leading-none">City Agent <span class="text-accent">RISE</span></span>
        <span class="text-[10.5px] font-mono text-muted">Replenishment Intelligence &amp; Stock Engine</span>
      </span>
    </div>
    <span class="pill bg-line/60 text-muted"><span class="w-[7px] h-[7px] rounded-full bg-sage"></span> v1.0.0</span>
  </header>

  <!-- two-column body -->
  <main class="flex-1 grid lg:grid-cols-2 gap-10 xl:gap-16 items-center max-w-[1200px] w-full mx-auto px-6 md:px-10 py-8">

    <!-- LEFT — greeting + form -->
    <div class="max-w-[440px] w-full">
      <h1 class="text-[34px] md:text-[40px] font-extrabold tracking-tight text-ink leading-[1.1]">
        {greeting},<br />sign in to City Agent <span class="text-accent">RISE</span>
      </h1>
      <p class="text-[15px] text-muted mt-3">Demand forecasting &amp; smart ordering — one plan across every outlet.</p>

      <div class="flex items-center gap-2 text-[12.5px] text-muted mt-4">
        <span class="w-[8px] h-[8px] rounded-full bg-sage"></span>
        <span><b class="text-ink">84</b> outlets · <b class="text-ink">22,755</b> SKUs · data {today}</span>
      </div>

      <form onsubmit={submit} class="mt-6 space-y-3">
        {#if error || ssoError}
          <div class="text-[12.5px] rounded-lg px-3 py-2 bg-red-50 text-red-700 border border-red-200">{error ?? ssoError}</div>
        {/if}

        <input type="email" bind:value={email} required autocomplete="username" placeholder="Email"
               class="w-full rounded-xl border border-line px-4 py-3.5 text-sm text-ink bg-white
                      focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent" />

        <div class="relative">
          <input type={showPw ? 'text' : 'password'} bind:value={password} required autocomplete="current-password"
                 placeholder="Password"
                 class="w-full rounded-xl border border-line px-4 py-3.5 pr-16 text-sm text-ink bg-white
                        focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent" />
          <button type="button" onclick={() => showPw = !showPw}
                  class="absolute right-4 top-1/2 -translate-y-1/2 text-[12.5px] font-semibold text-muted hover:text-ink">
            {showPw ? 'Hide' : 'Show'}
          </button>
        </div>

        <label class="flex items-center gap-2.5 text-[13px] text-muted cursor-pointer select-none pt-1">
          <input type="checkbox" bind:checked={remember} class="w-4 h-4 rounded accent-[#BE6B41]" />
          Remember me on this device
        </label>

        <button type="submit" disabled={busy}
                class="w-full rounded-xl bg-ink text-white font-semibold py-3.5 text-sm hover:opacity-90
                       disabled:opacity-60 transition-opacity">
          {busy ? 'Signing in…' : 'Continue with email'}
        </button>

        {#if ssoEnabled}
          <div class="flex items-center gap-3 py-1 text-[11px] text-muted">
            <span class="h-px bg-line flex-1"></span> OR <span class="h-px bg-line flex-1"></span>
          </div>

          <a href={ssoUrl}
             class="w-full rounded-xl border border-line bg-line/40 hover:bg-line/70 font-semibold py-3.5 text-sm
                    text-ink flex items-center justify-center gap-2.5 transition-colors">
            <Icon name="diamond" class="w-4 h-4 text-accent" />
            Continue with {ssoProvider}
          </a>
        {/if}
      </form>
    </div>

    <!-- RIGHT — live demo panel -->
    <div class="rounded-[20px] p-6 md:p-7 text-white shadow-2xl hidden lg:block" style="background:#0f1218">
      <div class="flex items-center gap-2 text-[12px] text-white/60 mb-5">
        <span class="w-[7px] h-[7px] rounded-full bg-[#E0864F] animate-pulse"></span>
        live · tomorrow's plan across 84 outlets
      </div>

      <!-- chat mock -->
      <div class="space-y-3">
        <div class="inline-block rounded-2xl rounded-tl-md bg-white/[0.06] px-4 py-2.5 text-[13px] text-white/85 max-w-[85%]">
          How many croissants for Junction Square tomorrow?
        </div>
        <div class="flex justify-end">
          <div class="inline-block rounded-2xl rounded-tr-md px-4 py-2.5 text-[13px] max-w-[88%]" style="background:#BE6B41">
            Order <b>132 units</b> — forecast 128 (P50), safety +4.
            <span class="opacity-80">₭0.53M · +6% vs last week.</span>
          </div>
        </div>
        <div class="inline-flex gap-1 items-center rounded-full bg-white/[0.06] px-3 py-2">
          <span class="w-1.5 h-1.5 rounded-full bg-white/40 animate-pulse"></span>
          <span class="w-1.5 h-1.5 rounded-full bg-white/40 animate-pulse" style="animation-delay:.15s"></span>
          <span class="w-1.5 h-1.5 rounded-full bg-white/40 animate-pulse" style="animation-delay:.3s"></span>
        </div>
      </div>

      <!-- quick tiles -->
      <div class="grid grid-cols-2 gap-2.5 mt-6">
        {#each [
          { i: 'trend', t: 'Forecast' }, { i: 'box', t: 'Smart Ordering' },
          { i: 'activity', t: 'Accuracy' }, { i: 'refresh', t: 'Sync live' }
        ] as q, idx}
          <div class="rounded-xl px-3.5 py-3 text-[12.5px] font-medium flex items-center gap-2.5
                      {idx === 1 ? 'ring-1' : ''}"
               style="background:#171b22;{idx === 1 ? 'box-shadow:inset 0 0 0 1px #BE6B41' : ''}">
            <Icon name={q.i} class="w-4 h-4 text-[#E0864F]" /> {q.t}
          </div>
        {/each}
      </div>

      <div class="flex items-center gap-4 mt-6 text-[12px] text-white/50">
        <span><b class="text-white/80">84</b> outlets</span>
        <span><b class="text-white/80">22,755</b> SKUs</span>
        <span><b class="text-white/80">champion</b> live</span>
      </div>
    </div>
  </main>

  <footer class="text-center text-[11.5px] text-muted py-6">
    © 2026 City Agent RISE · Demand Forecasting &amp; Smart Ordering · CityFood Concepts
  </footer>
</div>
