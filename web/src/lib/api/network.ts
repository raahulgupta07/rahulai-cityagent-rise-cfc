// Typed network-drill API client (Wave-2 Agent A).
// Mirrors /demand/* endpoints in api/routes/demand.py.
// Vite proxies /api -> FastAPI :8000.

export type OutletRow = {
  outlet_id: number;
  outlet_name: string;
  brand?: string;
  order_units: number;
  value_ks: number;
  sku_count: number;
  accuracy?: number;
};

export type SkuRow = {
  product_id: number;
  product_name: string;
  expected: number;
  safe: number;
  max_safe: number;
  order_qty: number;
  yesterday?: number;
  avg_7d?: number;
  trend?: string; // 'up' | 'flat' | 'down'
};

export type Driver = { label: string; effect_pct: number; note?: string };

export type SkuDetail = {
  product_id: number;
  product_name: string;
  outlet_id: number;
  outlet_name: string;
  price?: number;
  category?: string;
  date: string;
  expected: number;
  safe: number;
  max_safe: number;
  order_qty: number;
  history: Array<{ date: string; actual: number; expected: number; safe: number }>;
  drivers: Driver[];
  accuracy?: number;
};

const base = '/api';

async function get<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>
): Promise<T> {
  const u = new URL(base + path, location.origin);
  for (const [k, v] of Object.entries(params ?? {}))
    if (v != null) u.searchParams.set(k, String(v));
  const r = await fetch(u.pathname + u.search);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

/** L1 — all outlets for a date (latest if omitted). */
export const network = (date?: string) =>
  get<OutletRow[]>('/demand/network', { date });

/** L2 — all SKUs for one outlet on a date. Pass hide_zero=true to collapse zero-demand rows. */
export const outlet = (id: number, date?: string, hide_zero?: boolean) =>
  get<SkuRow[]>(`/demand/outlet/${id}`, { date, hide_zero });

/** L3 — single SKU detail (history + drivers + accuracy). */
export const sku = (outlet_id: number, product_id: number, date?: string) =>
  get<SkuDetail>('/demand/sku', { outlet_id, product_id, date });

/** Available forecast dates (ascending). */
export const dates = () => get<string[]>('/demand/dates');
