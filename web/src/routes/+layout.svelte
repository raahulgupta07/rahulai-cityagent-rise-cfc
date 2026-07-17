<script lang="ts">
  import '../app.css';
  import { NAV } from '$lib/nav/registry';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api';
  import { authApi, type Me } from '$lib/api/auth';
  let { children } = $props();

  let online = $state<boolean | null>(null);
  $effect(() => { api.health().then(h => online = h.ok).catch(() => online = false); });

  // ── auth gate ────────────────────────────────────────────────────────────
  let me = $state<Me | null>(null);              // null = still checking
  let isLogin = $derived($page.url.pathname === '/login');

  $effect(() => {
    if (isLogin) return;                          // login page renders bare, no gate
    authApi.me().then(m => {
      me = m;
      if (!m.authenticated) goto('/login');
    }).catch(() => { me = { authenticated: false, configured: false }; goto('/login'); });
  });

  async function logout() {
    try { await authApi.logout(); } catch { /* ignore */ }
    me = null;
    goto('/login');
  }

  function initials(email?: string) {
    if (!email) return 'DS';
    return email.slice(0, 2).toUpperCase();
  }

  // active page title/subtitle for the topbar. Exact match first; else the LONGEST
  // nav prefix wins so drill pages (/network/{id}, /ordering/product/{x}, …) keep
  // their section's title instead of falling back to "Overview". '/' only matches itself.
  let active = $derived(
    NAV.find(n => n.href === $page.url.pathname) ??
    [...NAV].filter(n => n.href !== '/' && $page.url.pathname.startsWith(n.href + '/'))
            .sort((a, b) => b.href.length - a.href.length)[0]
  );
  let title    = $derived(active?.label ?? 'Overview');
  let subtitle = $derived(active?.blurb ?? 'CFC bakery demand — plan, forecast, order');
</script>

{#if isLogin}
  {@render children()}
{:else if me === null}
  <div class="min-h-screen grid place-items-center bg-rail">
    <span class="text-railink2 text-sm font-mono">checking session…</span>
  </div>
{:else if me.authenticated}
<div class="min-h-screen grid grid-cols-[248px_1fr]">
  <!-- fixed dark navy rail -->
  <aside class="bg-rail flex flex-col px-4 py-5 sticky top-0 h-screen">
    <a href="/" class="flex items-center gap-2.5 px-2 pb-5 mb-1 border-b border-railline">
      <span class="w-8 h-8 rounded-[9px] flex-none" style="background:#BE6B41"></span>
      <span class="leading-tight">
        <span class="font-extrabold text-white text-[15px] tracking-tight block leading-none">City Agent <span class="text-accent">RISE</span></span>
        <span class="text-[11px] font-mono text-railink2">CFC · Demand AI</span>
      </span>
    </a>

    {#snippet navlink(item)}
      {@const isActive = $page.url.pathname === item.href}
      <a href={item.href}
         class="flex items-center gap-2.5 px-3 py-2.5 rounded-[9px] text-sm font-semibold transition-colors
                {isActive ? 'bg-rail2 text-white' : 'text-railink hover:bg-rail2 hover:text-white'}">
        <span class="w-2 h-2 rounded-full flex-none {isActive ? 'bg-accent' : 'bg-railink2'}"></span>
        <span class="flex-1">{item.label}</span>
        {#if isActive}<span class="w-1.5 h-1.5 rounded-full bg-accent"></span>{/if}
      </a>
    {/snippet}

    <div class="mt-4 flex-1 space-y-0.5 overflow-y-auto">
      <div class="text-[11px] font-bold tracking-[0.08em] uppercase text-railink2 px-3 pt-2 pb-1.5">Workspace</div>
      {#each NAV as item}{@render navlink(item)}{/each}
    </div>

    <div class="border-t border-railline pt-3.5 flex items-center gap-2.5">
      <span class="w-[30px] h-[30px] rounded-full grid place-items-center flex-none font-mono font-bold text-[12px] text-railink"
            style="background:#3A4152">{initials(me.email)}</span>
      <span class="leading-tight min-w-0 flex-1">
        <span class="text-[13px] font-semibold text-white block truncate">{me.email}</span>
        <span class="text-[11px] text-railink2 capitalize">{me.role}</span>
      </span>
      <button onclick={logout} title="Sign out"
              class="text-railink2 hover:text-white text-[11px] font-semibold px-2 py-1 rounded-md hover:bg-rail2 transition-colors">
        Sign out
      </button>
    </div>
  </aside>

  <div class="min-w-0 flex flex-col">
    <!-- topbar -->
    <div class="h-16 flex-none bg-surface border-b border-line px-7 flex items-center justify-between sticky top-0 z-10">
      <div>
        <div class="text-[17px] font-extrabold tracking-tight text-ink">{title}</div>
        <div class="text-[12.5px] text-muted">{subtitle}</div>
      </div>
      <div class="flex items-center gap-3.5">
        <span class="pill {online ? 'bg-sage/12 text-sage border border-sage/25' : 'bg-line text-muted'}">
          <span class="w-[7px] h-[7px] rounded-full {online ? 'bg-sage' : 'bg-muted'}"></span>
          {online === null ? 'connecting…' : online ? 'Model live · champion' : 'offline'}
        </span>
        <span class="w-[34px] h-[34px] rounded-full grid place-items-center text-white font-mono font-extrabold text-[13px] flex-none"
              style="background:#BE6B41">{initials(me.email)}</span>
      </div>
    </div>

    <main class="p-7 max-w-[1360px] w-full mx-auto">{@render children()}</main>
  </div>
</div>
{/if}
