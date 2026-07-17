<script lang="ts">
  // "Explain this" affordance — POSTs the current scope to /api/explain and shows
  // the returned plain-language text inline. Degrades gracefully: if the endpoint
  // is missing (404) it shows a quiet "explanation unavailable" note instead of an error.
  import Icon from '$lib/Icon.svelte';

  let { version, branch, product, date, label = 'Explain this', context }: {
    version?: string; branch?: string; product?: string; date?: string;
    label?: string; context?: Record<string, unknown>;
  } = $props();

  let open    = $state(false);
  let loading = $state(false);
  let text    = $state<string | null>(null);
  let missing = $state(false);   // endpoint absent → hide gracefully
  let failed  = $state(false);

  async function toggle() {
    if (open) { open = false; return; }
    open = true;
    if (text || loading) return;   // already have it
    loading = true; failed = false;
    try {
      const r = await fetch('/api/explain', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ version, branch, product, date, context }),
      });
      if (r.status === 404) { missing = true; open = false; return; }
      if (!r.ok) throw new Error(String(r.status));
      const d = await r.json();
      text = (d && typeof d.text === 'string' && d.text.trim()) ? d.text : 'Explanation unavailable right now.';
    } catch {
      failed = true;
    } finally {
      loading = false;
    }
  }
</script>

{#if !missing}
  <div class="inline-flex flex-col items-start gap-2">
    <button type="button" class="btn-subtle btn-sm" aria-expanded={open} onclick={toggle}>
      <Icon name="info" class="w-3.5 h-3.5" /> {label}
    </button>

    {#if open}
      <div class="rounded-xl border border-accent/25 bg-accent/[0.04] px-4 py-3 max-w-md text-sm text-ink shadow-soft">
        {#if loading}
          <div class="flex items-center gap-2 text-muted">
            <Icon name="refresh" class="w-4 h-4 animate-spin" /> Working it out…
          </div>
        {:else if failed}
          <div class="text-muted">Explanation unavailable right now. Try again in a moment.</div>
        {:else}
          <p class="leading-relaxed">{text}</p>
        {/if}
      </div>
    {/if}
  </div>
{/if}
