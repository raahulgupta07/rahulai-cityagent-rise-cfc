"""
Data Hub + Upload slice — Wave-2 B.

Prefix: /data
Auto-mounted by routes/__init__.py. Never edit main.py.

Endpoints:
  GET  /data/sync/status        — 15 tables, parquet presence + row counts
  GET  /data/manual             — files in data/external/ + root xlsx
  GET  /data/gaps               — 12 missing business inputs
  GET  /data/template/{key}     — download filled xlsx template
  POST /data/upload/{key}       — validate (and optionally accept) an upload
"""
from __future__ import annotations
import io, pathlib, logging
import duckdb
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query

from deps.auth import current_user
from fastapi.responses import StreamingResponse

from services.templates import build_template
from services.validate  import validate_upload
from deps.store         import record_audit

log = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RAW  = ROOT / "data" / "raw"
EXT  = ROOT / "data" / "external"
ECON = ROOT / "data" / "product_econ.csv"

# ── 15 tables from DATA_DICTIONARY.md ──────────────────────────────────────
_TABLES = [
    "CFC_PBID_Sales_Summary",
    "CFC_PBID_BranchSales",
    "CFC_PBID_SlipDiscount_Summary",
    "CFC_PBID_BranchSlipDiscount",
    "Ref_Branch_Master",
    "Ref_Product_Master",
    "Ref_Partner_Master",
    "Ref_StockWarehouse_Master",
    "Ref_StockLocation_Master",
    "Ref_Uom_Master",
    "Dim_Channel",
    "Dim_Company",
    "Dim_Segment",
    "Dim_CostCenter",
    "Dim_ProfitCenter",
]

# parquet file name mapping (some are stored under shorter names)
_PARQUET_ALIASES = {
    "Ref_Branch_Master":   "dim_branch",
    "Ref_Product_Master":  "dim_product",
    "CFC_PBID_Sales_Summary": "demand_panel",
}


def _parquet_path(table: str) -> pathlib.Path:
    alias = _PARQUET_ALIASES.get(table, table)
    return RAW / f"{alias}.parquet"


# ── 12 gap inputs (from data_request_email_v2.md) ──────────────────────────
_GAPS = [
    {"key": "product_economics",  "label": "Product Economics (GM, shelf life, salvage)", "owner": "Finance / Ops",       "status": "pending", "has_template": True},
    {"key": "inventory_daily",    "label": "Daily Inventory (open/close stock, wasted)",  "owner": "Ops / WMS",           "status": "pending", "has_template": True},
    {"key": "lead_time_sla",      "label": "Lead Time & SLA (factory → outlet)",          "owner": "Supply Chain",        "status": "pending", "has_template": True},
    {"key": "order_history",      "label": "Historical Order Quantities (WMS)",           "owner": "Procurement / WMS",   "status": "pending", "has_template": False},
    {"key": "promo_calendar",     "label": "Promotions & Events Calendar",                "owner": "Marketing",           "status": "pending", "has_template": True},
    {"key": "lifecycle_dates",    "label": "Product Launch / Discontinue Dates",          "owner": "Marketing / Category","status": "pending", "has_template": False},
    {"key": "outlet_attrs",       "label": "Outlet Attributes (size, hours, type)",       "owner": "Ops",                 "status": "pending", "has_template": False},
    {"key": "price_changes",      "label": "Price Change History",                        "owner": "Finance",             "status": "pending", "has_template": False},
    {"key": "capacity",           "label": "Outlet / Factory Capacity Limits",            "owner": "Ops / Production",    "status": "pending", "has_template": False},
    {"key": "substitution",       "label": "Product Substitution / Recipe Links",         "owner": "Category / R&D",      "status": "pending", "has_template": False},
    {"key": "salvage_detail",     "label": "Salvage Detail (markdown %, staff meals)",    "owner": "Finance",             "status": "pending", "has_template": False},
    {"key": "demand_override",    "label": "Manual Demand Overrides",                     "owner": "Demand Planner",      "status": "pending", "has_template": False},
]


# ── helpers ─────────────────────────────────────────────────────────────────

def _count_rows(path: pathlib.Path) -> int | None:
    try:
        c = duckdb.connect(":memory:")
        result = c.execute(f"SELECT COUNT(*) FROM read_parquet('{path.as_posix()}')").fetchone()
        return int(result[0]) if result else None
    except Exception:
        return None


def _freshness(path: pathlib.Path) -> str:
    try:
        import datetime
        mtime = path.stat().st_mtime
        dt = datetime.datetime.fromtimestamp(mtime)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "unknown"


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/sync/status")
def sync_status():
    """Check which of the 15 Fabric tables are present as parquet."""
    result = []
    for table in _TABLES:
        path = _parquet_path(table)
        present = path.exists()
        rows = _count_rows(path) if present else None
        freshness = _freshness(path) if present else None
        result.append({
            "table": table,
            "present": present,
            "rows": rows,
            "freshness": freshness,
        })
    return result


@router.get("/manual")
def manual_files():
    """List manually uploaded files in data/external/ and product_econ.csv."""
    files = []

    # data/external/ dir
    if EXT.exists():
        for f in sorted(EXT.iterdir()):
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "loaded": True,
                })

    # product_econ.csv in root data/
    if ECON.exists():
        files.append({
            "name": "product_econ.csv",
            "size_kb": round(ECON.stat().st_size / 1024, 1),
            "loaded": True,
        })

    # any xlsx files in root data/ dir
    for f in sorted((ROOT / "data").iterdir()):
        if f.is_file() and f.suffix.lower() == ".xlsx":
            files.append({
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "loaded": False,  # not yet ingested
            })

    return {"files": files}


@router.get("/gaps")
def gaps():
    """Return the 12 missing business inputs with metadata."""
    return _GAPS


@router.get("/template/{key}")
def template(key: str):
    """Download a pre-filled xlsx template for the given gap key."""
    try:
        xlsx_bytes = build_template(key)
    except KeyError:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No template for key '{key}'")

    filename = f"{key}_template.xlsx"
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/upload/{key}")
async def upload(
    key: str,
    file: UploadFile = File(...),
    accept: bool = Query(False),
    user: dict = Depends(current_user),
):
    # accept=true OVERWRITES a canonical input CSV (e.g. product_econ.csv drives order
    # quantities) — ops/admin only. Validate-only stays open to any logged-in user.
    if accept and user["role"] not in ("ops", "admin"):
        raise HTTPException(403, "Accepting an upload requires the ops or admin role")
    """
    Validate (and optionally accept) an uploaded xlsx/csv.

    ?accept=false  → validate only, return results
    ?accept=true   → validate + if ok, write to canonical location + audit
    """
    content = await file.read()
    filename = file.filename or "upload"

    # Parse
    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        return {"ok": False, "error": f"Could not parse file: {exc}",
                "matched": 0, "unmatched": [], "range_errors": [str(exc)],
                "blank_count": 0, "preview": []}

    result = validate_upload(key, df)
    result["filename"] = filename
    result["rows_uploaded"] = len(df)

    if accept and result["ok"]:
        # Write product_economics to canonical product_econ.csv
        if key == "product_economics":
            col_map = {c.lower(): c for c in df.columns}
            out_cols = {
                "ProductId":      col_map.get("productid"),
                "ListPrice":      col_map.get("listprice"),
                "gm":             col_map.get("gm"),
                "shelf_life_days":col_map.get("shelf_life_days"),
                "salvage_frac":   col_map.get("salvage_frac"),
            }
            # build output frame with only present columns. NOTE: the validator only
            # checks non-null ProductId rows, so a file can pass ok=True and still hold
            # blank ProductId cells — coerce + drop those rows instead of 500ing on
            # astype(int) (IntCastingNaNError).
            out = pd.DataFrame()
            if out_cols["ProductId"]:
                pid = pd.to_numeric(df[out_cols["ProductId"]], errors="coerce")
                keep = df[pid.notna()].reset_index(drop=True)
                out["ProductId"] = pid.dropna().astype(int).values
            else:
                keep = df
                out["ProductId"] = None
            for col in ["ListPrice", "gm", "shelf_life_days", "salvage_frac"]:
                src = out_cols.get(col)
                out[col] = keep[src].values if src else None
            out.to_csv(ECON, index=False)
            result["saved_to"] = str(ECON)

        # Other keyed inputs → canonical csv under data/external/ (verbatim)
        elif key in ("promo_calendar", "lead_time_sla"):
            dest = EXT / f"{key}.csv"
            EXT.mkdir(parents=True, exist_ok=True)
            df.to_csv(dest, index=False)
            result["saved_to"] = str(dest)

        # Audit
        record_audit(key, filename, len(df), accepted=True)
        result["accepted"] = True
    else:
        result["accepted"] = False

    return result
