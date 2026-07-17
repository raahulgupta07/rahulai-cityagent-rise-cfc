// Typed client for the /eda slice — live stats from the demand panel.

export type Eda = {
  summary: {
    rows: number; branches: number; products: number;
    net_units: number; revenue: number; first_day: string; latest_day: string;
  };
  by_year: { year: string; units: number }[];
  by_dow: { dow: string; units: number }[];
  by_month: { ym: string; units: number }[];
  top_products: { name: string; units: number }[];
  top_branches: { name: string; units: number }[];
  freshness: string;
};

export const edaApi = {
  get: async (): Promise<Eda> => {
    const r = await fetch('/api/eda');
    if (!r.ok) throw new Error(`GET /eda → ${r.status}`);
    return r.json();
  },
};
