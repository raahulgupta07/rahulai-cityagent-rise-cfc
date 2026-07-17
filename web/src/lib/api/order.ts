// Typed client for the /order slice.
// Vite proxies /api -> FastAPI :8000 (vite.config.ts).

const base = '/api';

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const u = new URL(base + path, location.origin);
  for (const [k, v] of Object.entries(params ?? {})) if (v != null) u.searchParams.set(k, String(v));
  const r = await fetch(u.pathname + u.search);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

// ── response shapes ─────────────────────────────────────────────────

export type PicklistRow = {
  product_id: number;
  product_name: string;
  category?: string;
  order_units: number;
  outlets: number;
  value_ks: number;
};

export type PicklistResponse = {
  date: string;
  totals: { products: number; order_units: number; value_ks: number };
  rows: PicklistRow[];
};

export type ProductionRow = {
  outlet_id: number;
  outlet_name: string;
  brand?: string;
  order_qty: number;
  expected: number;
  safe: number;
  actual?: number;
  trend?: 'up' | 'flat' | 'down';
};

export type ProductionResponse = {
  date: string;
  product_id: number;
  product_name: string;
  product_code?: string;
  category?: string;
  make_total: number;
  outlets_count: number;
  rows: ProductionRow[];
};

export type WarehouseGroup = {
  warehouse_id?: number;
  warehouse_name: string;
  outlets_count: number;
  order_units: number;
  value_ks: number;
  rows: PicklistRow[];
};

export type ByWarehouseResponse = {
  date: string;
  note?: string;
  warehouses: WarehouseGroup[];
};

export type DialPoint = {
  service_level: number;
  order_quantile: string;
  stockout_pct: number;
  waste_pct: number;
  fill_pct: number;
  cost: number;
};

export type DialResponse = {
  date: string;
  gm_placeholder: number;
  points: DialPoint[];
};

// ── API functions ────────────────────────────────────────────────────

export const orderApi = {
  picklist: (date?: string) =>
    get<PicklistResponse>('/order/picklist', { date }),

  picklistCsvUrl: (date?: string): string => {
    const u = new URL(base + '/order/picklist.csv', location.origin);
    if (date) u.searchParams.set('date', date);
    return u.pathname + u.search;
  },

  production: (product_id: number, date?: string) =>
    get<ProductionResponse>(`/order/production/${product_id}`, { date }),

  byWarehouse: (date?: string) =>
    get<ByWarehouseResponse>('/order/by-warehouse', { date }),

  dial: (date?: string) =>
    get<DialResponse>('/order/dial', { date }),
};
