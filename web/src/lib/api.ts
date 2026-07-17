// Typed API client. Mirrors api/models/contracts.py (client-facing names only).
// Vite proxies /api -> FastAPI :8000 (see vite.config.ts).
const base = '/api';
async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const u = new URL(base + path, location.origin);
  for (const [k, v] of Object.entries(params ?? {})) if (v != null) u.searchParams.set(k, String(v));
  const r = await fetch(u.pathname + u.search);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}
export type OutletRow = { outlet_id: number; outlet_name: string; brand?: string; order_units: number; value_ks: number; sku_count: number; accuracy?: number };
export type SkuRow = { product_id: number; product_name: string; expected: number; safe: number; max_safe: number; order_qty: number; yesterday?: number; avg_7d?: number; trend?: string };
export type Driver = { label: string; effect_pct: number; note?: string };
export type SkuDetail = { product_id: number; product_name: string; outlet_id: number; outlet_name: string; price?: number; category?: string; date: string; expected: number; safe: number; max_safe: number; order_qty: number; history: any[]; drivers: Driver[]; accuracy?: number };

export const api = {
  health: () => get<{ ok: boolean }>('/health'),
  dates: () => get<string[]>('/demand/dates'),
  network: (date?: string) => get<OutletRow[]>('/demand/network', { date }),
  outlet: (id: number, date?: string) => get<SkuRow[]>(`/demand/outlet/${id}`, { date }),
  sku: (outlet_id: number, product_id: number, date?: string) => get<SkuDetail>('/demand/sku', { outlet_id, product_id, date })
};
