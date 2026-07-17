// Pure client-side SPA — every page fetches its data from /api at runtime, so we disable
// SSR and prerendering. Required for adapter-static (single-container) and harmless for
// adapter-node (multi-container).
export const ssr = false;
export const prerender = false;
