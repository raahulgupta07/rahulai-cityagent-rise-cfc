// Typed client for the /analysis slice (P5). Neutralised report data.

export type Table = { columns: string[]; rows: string[][] } | null;

export type Analysis = {
  data_glance: Record<string, number | null>;
  yearly: { year: string; units: number }[];
  dow: { peak_day: string | null; peak_ratio: number | null };
  brand_mix: { brand: string; units: number; share_pct: number }[];
  concentration: {
    top10_branch_pct: number | null;
    top_branches: { name: string; units: number }[];
    top_products: { name: string; units: number }[];
  };
  patterns: string[][];
  abc: { a: number | null; b: number | null; c: number | null; a_vol_pct: number | null };
  festival: { normal: number | null; holiday_pct: number | null; thingyan_pct: number | null };
  baselines: Table;
  accuracy: {
    folds: { period: string; model_acc: number; floor_acc: number; gain_pct: number }[];
    by_class: { cls: string; accuracy: number; gain_pct: number; vol_share: number }[];
    overall: number | null;
  };
  calibration: { level: string; coverage: number | null; target: number; score: number | null }[];
  cost_sim: Table;
  service_tradeoff: Table;
  drift: {
    psi: string[][];
    champion_error: number | null;
    recent_error: number | null;
    verdict: string | null;
    data_drift: boolean;
    accuracy_drift: boolean;
  };
};

export const analysisApi = {
  get: async (): Promise<Analysis> => {
    const r = await fetch('/api/analysis');
    if (!r.ok) throw new Error(`GET /analysis → ${r.status}`);
    return r.json();
  },
};
