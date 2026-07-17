// Insights client — business-value views (economics, promo, stockout).
// Mirrors api/routes/insights.py.
const base = '/api';
async function get<T>(path: string): Promise<T> {
  const r = await fetch(base + path);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

export type EconomicsImpact = {
  available: boolean;
  is_uniform?: boolean;
  product_count?: number;
  critical_ratio_spread?: number;
  gm_stats?: Record<string, number>;
  shelf_life_stats?: Record<string, number>;
  message?: string;
};

export const insightsApi = {
  economics: () => get<EconomicsImpact>('/insights/economics-impact')
};
