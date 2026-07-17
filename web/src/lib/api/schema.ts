// Typed API client for schema + insights endpoints (Wave-3 P8).
// Mirrors api/routes/schema.py and api/routes/insights.py.
// Vite proxies /api -> FastAPI :8000.

// ── Schema types ─────────────────────────────────────────────────────────────

export type TableRow = {
  table: string;
  schema: string;
  pk: string;
  definition: string;
  rows: number;
  rows_exact: boolean;
  has_local_parquet: boolean;
  parquet_file: string | null;
};

export type ColumnRow = {
  name: string;
  type: string;
  definition: string;
  sample: string | null;
};

export type ColumnsResponse = {
  table: string;
  columns: ColumnRow[];
};

export type Relationship = {
  from_table: string;
  from_col: string;
  to_table: string;
  to_col: string;
  note?: string;
};

// ── Insights types ────────────────────────────────────────────────────────────

export type InsightUnavailable = {
  available: false;
  needs: string;
  upload_path?: string;
  explanation: string;
  potential_value?: string;
};

export type StockoutCorrectionResult = {
  available: true;
  summary: {
    total_zero_demand_days: number;
    probable_stockout_days: number;
    true_zero_demand_days: number;
    no_inventory_match_days: number;
    stockout_pct_of_zeros: number;
  };
  interpretation: string;
};

export type PromoUpliftResult = {
  available: true;
  summary: {
    promo_days_in_calendar: number;
    matched_demand_days: number;
    promo_avg_daily_units: number | null;
    baseline_avg_daily_units: number | null;
    lift_pct: number | null;
  };
  interpretation: string;
};

export type EconomicsImpactResult = {
  available: true;
  is_uniform: boolean;
  product_count: number;
  gm_stats: Record<string, number>;
  shelf_life_stats: Record<string, number>;
  critical_ratio_stats: Record<string, number>;
  critical_ratio_spread: number;
  message: string;
  unlock_value: string | null;
  action: string | null;
};

export type StockoutInsight   = StockoutCorrectionResult  | InsightUnavailable;
export type PromoInsight       = PromoUpliftResult         | InsightUnavailable;
export type EconomicsInsight   = EconomicsImpactResult     | InsightUnavailable;

// ── HTTP helpers ──────────────────────────────────────────────────────────────

const base = '/api';

async function get<T>(path: string): Promise<T> {
  const r = await fetch(base + path);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

// ── Schema API ────────────────────────────────────────────────────────────────

/** All 15 source tables with row counts, definitions, PKs. */
export const schemaTables       = () => get<TableRow[]>('/schema/tables');

/** Column list for one table (name, type, definition, sample). */
export const schemaColumns      = (table: string) =>
  get<ColumnsResponse>(`/schema/columns/${encodeURIComponent(table)}`);

/** All FK relationships across the 15 tables. */
export const schemaRelationships = () => get<Relationship[]>('/schema/relationships');

// ── Insights API ──────────────────────────────────────────────────────────────

/** Zero-sold vs sold-out split (needs inventory_daily). */
export const stockoutCorrection = () => get<StockoutInsight>('/insights/stockout-correction');

/** Demand lift on promo days vs baseline (needs promo_calendar). */
export const promoUplift        = () => get<PromoInsight>('/insights/promo-uplift');

/** Uniform vs differentiated critical-ratio analysis (uses product_econ.csv). */
export const economicsImpact    = () => get<EconomicsInsight>('/insights/economics-impact');
