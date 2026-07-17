"""
Upload validation service.

validate_upload(key, df) -> dict with keys:
    matched      int          # rows whose IDs matched the master dimension
    unmatched    list[str]    # IDs not found in master (up to 20)
    range_errors list[str]    # human-readable range violations (up to 20)
    blank_count  int          # total blank cells in value columns
    preview      list[dict]   # first 5 rows as dicts
    ok           bool         # True if matched>0 and no range errors
"""
from __future__ import annotations
import pathlib
import duckdb
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RAW  = ROOT / "data" / "raw"


def _duck_set(sql: str) -> set:
    c = duckdb.connect(":memory:")
    return {row[0] for row in c.execute(sql).fetchall()}


def _valid_product_ids() -> set[int]:
    parquet = (RAW / "dim_product.parquet").as_posix()
    return _duck_set(f"SELECT DISTINCT ProductId FROM read_parquet('{parquet}')")


def _valid_branch_ids() -> set[int]:
    parquet = (RAW / "dim_branch.parquet").as_posix()
    return _duck_set(f"SELECT DISTINCT BranchId FROM read_parquet('{parquet}')")


def _valid_warehouse_ids() -> set[int]:
    parquet = (RAW / "dim_warehouse.parquet").as_posix()
    return _duck_set(f"SELECT DISTINCT WarehouseId FROM read_parquet('{parquet}')")


# ── per-key validators ──────────────────────────────────────────────────────

def _validate_product_economics(df: pd.DataFrame) -> dict:
    range_errors: list[str] = []
    blank_count = 0
    unmatched: list[str] = []

    # Normalise column names (case-insensitive)
    df.columns = [c.strip() for c in df.columns]
    col_map = {c.lower(): c for c in df.columns}

    # ProductId check
    pid_col = col_map.get("productid")
    if pid_col is None:
        return {
            "matched": 0, "unmatched": [], "range_errors": ["Missing column: ProductId"],
            "blank_count": 0, "preview": [], "ok": False,
        }

    valid_ids = _valid_product_ids()
    df_ids = set(df[pid_col].dropna().astype(int).tolist())
    unmatched = [str(i) for i in sorted(df_ids - valid_ids)][:20]
    matched = len(df_ids & valid_ids)

    # Value columns
    value_cols = ["gm", "cost", "shelf_life_days", "salvage_frac"]
    for col_lower in value_cols:
        real_col = col_map.get(col_lower)
        if real_col is None:
            continue
        series = df[real_col]
        blank_count += int(series.isna().sum())
        non_null = series.dropna()

        if col_lower == "gm":
            bad = non_null[(non_null < 0) | (non_null > 1)]
            for v in bad.head(5):
                range_errors.append(f"gm={v:.4f} out of [0,1]")

        elif col_lower == "shelf_life_days":
            bad = non_null[non_null <= 0]
            for v in bad.head(5):
                range_errors.append(f"shelf_life_days={v} must be > 0")

        elif col_lower == "salvage_frac":
            bad = non_null[(non_null < 0) | (non_null > 1)]
            for v in bad.head(5):
                range_errors.append(f"salvage_frac={v:.4f} out of [0,1]")

    range_errors = range_errors[:20]
    preview = df.head(5).fillna("").to_dict(orient="records")
    ok = matched > 0 and len(range_errors) == 0

    return {
        "matched": matched,
        "unmatched": unmatched,
        "range_errors": range_errors,
        "blank_count": blank_count,
        "preview": preview,
        "ok": ok,
    }


def _validate_inventory_daily(df: pd.DataFrame) -> dict:
    range_errors: list[str] = []
    blank_count = 0
    unmatched: list[str] = []

    df.columns = [c.strip() for c in df.columns]
    col_map = {c.lower(): c for c in df.columns}

    # date column
    date_col = col_map.get("date")
    if date_col is not None:
        try:
            pd.to_datetime(df[date_col])
        except Exception as e:
            range_errors.append(f"date column not parseable: {e}")

    # outlet_id check
    oid_col = col_map.get("outlet_id")
    if oid_col is not None:
        valid_ids = _valid_branch_ids()
        df_ids = set(df[oid_col].dropna().astype(int).tolist())
        unmatched = [str(i) for i in sorted(df_ids - valid_ids)][:20]
        matched = len(df_ids & valid_ids)
    else:
        matched = 0

    # stock columns must be >= 0
    stock_cols = ["open_stock", "close_stock", "received", "wasted"]
    for col_lower in stock_cols:
        real_col = col_map.get(col_lower)
        if real_col is None:
            continue
        series = df[real_col]
        blank_count += int(series.isna().sum())
        non_null = series.dropna()
        bad = non_null[non_null < 0]
        for v in bad.head(5):
            range_errors.append(f"{col_lower}={v} must be >= 0")

    range_errors = range_errors[:20]
    preview = df.head(5).fillna("").to_dict(orient="records")
    ok = matched > 0 and len(range_errors) == 0

    return {
        "matched": matched,
        "unmatched": unmatched,
        "range_errors": range_errors,
        "blank_count": blank_count,
        "preview": preview,
        "ok": ok,
    }


def _validate_promo_calendar(df: pd.DataFrame) -> dict:
    range_errors: list[str] = []
    blank_count = 0
    unmatched: list[str] = []
    df.columns = [c.strip() for c in df.columns]
    col_map = {c.lower(): c for c in df.columns}

    date_col = col_map.get("date")
    if date_col is not None:
        try:
            pd.to_datetime(df[date_col].dropna())
        except Exception as e:
            range_errors.append(f"date column not parseable: {e}")

    oid_col = col_map.get("outlet_id")
    matched = 0
    if oid_col is not None:
        valid_ids = _valid_branch_ids()
        df_ids = set(df[oid_col].dropna().astype(int).tolist())
        unmatched = [str(i) for i in sorted(df_ids - valid_ids)][:20]
        matched = len(df_ids & valid_ids)

    disc_col = col_map.get("discount_pct")
    if disc_col is not None:
        s = df[disc_col]
        blank_count += int(s.isna().sum())
        bad = s.dropna()[(s.dropna() < 0) | (s.dropna() > 90)]
        for v in bad.head(5):
            range_errors.append(f"discount_pct={v} out of [0,90]")

    ptype_col = col_map.get("promo_type")
    if ptype_col is not None:
        allowed = {"bogo", "%off", "bundle"}
        bad = df[ptype_col].dropna()[~df[ptype_col].dropna().astype(str).str.lower().isin(allowed)]
        for v in bad.head(5):
            range_errors.append(f"promo_type='{v}' not in {{BOGO, %off, bundle}}")

    range_errors = range_errors[:20]
    preview = df.head(5).fillna("").to_dict(orient="records")
    return {"matched": matched, "unmatched": unmatched, "range_errors": range_errors,
            "blank_count": blank_count, "preview": preview,
            "ok": matched > 0 and len(range_errors) == 0}


def _validate_lead_time_sla(df: pd.DataFrame) -> dict:
    range_errors: list[str] = []
    blank_count = 0
    unmatched: list[str] = []
    df.columns = [c.strip() for c in df.columns]
    col_map = {c.lower(): c for c in df.columns}

    wid_col = col_map.get("warehouse_id")
    matched = 0
    if wid_col is not None:
        valid_ids = _valid_warehouse_ids()
        df_ids = set(df[wid_col].dropna().astype(int).tolist())
        unmatched = [str(i) for i in sorted(df_ids - valid_ids)][:20]
        matched = len(df_ids & valid_ids)

    ld_col = col_map.get("lead_days")
    if ld_col is not None:
        s = df[ld_col]
        blank_count += int(s.isna().sum())
        bad = s.dropna()[s.dropna() < 0]
        for v in bad.head(5):
            range_errors.append(f"lead_days={v} must be >= 0")
    else:
        range_errors.append("Missing column: lead_days")

    range_errors = range_errors[:20]
    preview = df.head(5).fillna("").to_dict(orient="records")
    return {"matched": matched, "unmatched": unmatched, "range_errors": range_errors,
            "blank_count": blank_count, "preview": preview,
            "ok": matched > 0 and len(range_errors) == 0}


# ── generic fallback ────────────────────────────────────────────────────────

def _validate_generic(df: pd.DataFrame) -> dict:
    blank_count = int(df.isna().sum().sum())
    preview = df.head(5).fillna("").to_dict(orient="records")
    return {
        "matched": len(df),
        "unmatched": [],
        "range_errors": [],
        "blank_count": blank_count,
        "preview": preview,
        "ok": True,
    }


# ── public API ──────────────────────────────────────────────────────────────

_VALIDATORS = {
    "product_economics": _validate_product_economics,
    "inventory_daily":   _validate_inventory_daily,
    "promo_calendar":    _validate_promo_calendar,
    "lead_time_sla":     _validate_lead_time_sla,
}


def validate_upload(key: str, df: pd.DataFrame) -> dict:
    """Validate df for the given upload key.

    Always returns a dict with keys: matched, unmatched, range_errors,
    blank_count, preview, ok.
    """
    fn = _VALIDATORS.get(key, _validate_generic)
    return fn(df)
