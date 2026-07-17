<script lang="ts">
  import { onMount } from 'svelte';
  import { deployApi, type Versions, type ApiSample } from '$lib/api/deploy';

  let versions = $state<Versions | null>(null);
  let sample   = $state<ApiSample | null>(null);
  let msg      = $state<string | null>(null);

  onMount(async () => {
    try { [versions, sample] = await Promise.all([deployApi.versions(), deployApi.apiSample()]); }
    catch (e) { msg = String(e); }
  });

  function activate(id: string) {
    msg = `${id} activation requested — promote from Model Leaderboard to change the champion.`;
  }

  let reqJson = $derived(sample ? JSON.stringify(sample.request, null, 2) : '');
  let resJson = $derived(sample ? JSON.stringify(sample.response, null, 2) : '');
</script>

<div class="flex flex-col gap-5">

  {#if msg}
    <div class="rounded-xl bg-accent/8 border border-accent/25 px-4 py-3 text-sm text-ink">{msg}</div>
  {/if}

  <!-- Model versions -->
  <div class="bg-surface border border-line rounded-xl overflow-hidden">
    <div class="px-6 py-4 border-b border-line text-[15px] font-extrabold">Model versions</div>
    {#if versions}
      {#each versions.versions as v}
        <div class="grid grid-cols-[70px_1.7fr_1fr_120px_120px] items-center px-6 py-4 border-t border-line/70 text-sm first:border-t-0">
          <div class="font-mono font-extrabold text-ink">{v.id}</div>
          <div>
            <div class="font-bold">{v.name}</div>
            <div class="text-[12.5px] text-muted mt-0.5">{v.date}</div>
          </div>
          <div class="font-mono text-muted">WMAPE {v.wmape.toFixed(3)}</div>
          <div>
            <span class="text-[11.5px] font-bold px-2.5 py-1 rounded-full
                         {v.active ? 'bg-sage/15 text-sage' : 'bg-line text-muted'}">{v.status}</span>
          </div>
          <div>
            {#if !v.active}
              <button class="btn-primary btn-sm" aria-label="Activate {v.name}"
                      onclick={() => activate(v.id)}>Activate</button>
            {/if}
          </div>
        </div>
      {/each}
    {:else}
      <div class="px-6 py-8 text-center text-muted text-sm">Loading versions…</div>
    {/if}
  </div>

  <!-- Endpoint request / response -->
  <div class="grid grid-cols-2 gap-4">
    <div class="bg-rail rounded-xl p-6 text-railink">
      <div class="text-[13px] font-bold text-railink2 uppercase tracking-wide mb-3">Endpoint · request</div>
      <pre class="font-mono text-[13px] leading-[1.7] whitespace-pre-wrap m-0 text-[#dfe3ee]">POST /v1/forecast
{reqJson}</pre>
    </div>
    <div class="bg-rail rounded-xl p-6 text-railink">
      <div class="text-[13px] font-bold text-railink2 uppercase tracking-wide mb-3">Endpoint · response</div>
      <pre class="font-mono text-[13px] leading-[1.7] whitespace-pre-wrap m-0 text-[#dfe3ee]">{resJson}</pre>
    </div>
  </div>

  <!-- Integration notes -->
  <div class="bg-surface border border-line rounded-xl p-6">
    <div class="text-[15px] font-extrabold mb-2.5">Integration notes</div>
    <div class="text-sm text-ink/80 leading-[1.7]">
      Warehouse ERP calls the endpoint once nightly per outlet × product, receives P50/P85/P95, and
      applies the newsvendor order rule from Smart Ordering to generate the next-day picklist automatically.
    </div>
  </div>

</div>
