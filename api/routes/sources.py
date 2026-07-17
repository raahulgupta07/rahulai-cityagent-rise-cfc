"""
Data provenance slice — P1.

Prefix: /sources
Auto-mounted by routes/__init__.py. Never edit main.py.

Splits every model input into two lanes, exactly as the Data screen shows them:
  - synced : pulled automatically from the database (read-only parquet in data/raw + external)
  - manual : provided by the user via a fixed template (upload + validate)

Endpoints:
  GET /sources          -> {"synced": [...], "manual": [...], "summary": {...}}
"""
from __future__ import annotations
import datetime
import pathlib
import duckdb
from fastapi import APIRouter

router = APIRouter(prefix="/sources", tags=["sources"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "data" / "raw"
EXT = ROOT / "data" / "external"
ECON = ROOT / "data" / "product_econ.csv"

# ── database-synced inputs (read-only, auto) ────────────────────────────────
# label -> parquet basename in data/raw (or external csv)
_SYNCED = [
    ("Sales fact (day×outlet×product)", RAW / "demand_panel.parquet"),
    ("Product master",                  RAW / "dim_product.parquet"),
    ("Outlet master",                   RAW / "dim_branch.parquet"),
    ("Warehouse master",                RAW / "dim_warehouse.parquet"),
    ("Channel master",                  RAW / "dim_channel.parquet"),
    ("Segment master",                  RAW / "dim_segment.parquet"),
    ("UOM master",                      RAW / "dim_uom.parquet"),
    ("Stock location master",           RAW / "dim_stocklocation.parquet"),
    ("Weather daily",                   EXT / "weather_daily.csv"),
    ("Holidays / festivals",            EXT / "myanmar_holidays.csv"),
]

# ── manual inputs (user fills a fixed template) ─────────────────────────────
# key, label, canonical file to detect "provided", has_template, required?
_MANUAL = [
    ("product_economics", "Product economics", ECON,                          True,  True),
    ("promo_calendar",    "Promotion calendar", EXT / "promo_calendar.csv",   True,  True),
    ("inventory_daily",   "Daily inventory",    RAW / "inventory_daily.parquet", True, False),
    ("lead_time_sla",     "Lead times",         EXT / "lead_time_sla.csv",     True,  False),
    ("weather_backfill",  "Weather back-fill",  EXT / "weather_backfill.csv",  False, False),
]


def _rows(path: pathlib.Path) -> int | None:
    if not path.exists():
        return None
    try:
        c = duckdb.connect(":memory:")
        reader = "read_parquet" if path.suffix == ".parquet" else "read_csv_auto"
        return int(c.execute(f"SELECT COUNT(*) FROM {reader}('{path.as_posix()}')").fetchone()[0])
    except Exception:
        return None


def _fresh(path: pathlib.Path) -> str | None:
    if not path.exists():
        return None
    return datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


@router.get("")
def sources():
    synced = []
    for label, path in _SYNCED:
        present = path.exists()
        synced.append({
            "name": label,
            "source": "database",
            "rows": _rows(path),
            "last_sync": _fresh(path),
            "status": "ok" if present else "missing",
        })

    manual = []
    for key, label, canonical, has_tpl, required in _MANUAL:
        provided = canonical.exists()
        if provided:
            status = "valid"
        elif required:
            status = "needs_you"
        else:
            status = "optional"
        manual.append({
            "key": key,
            "name": label,
            "source": "manual",
            "has_template": has_tpl,
            "required": required,
            "rows": _rows(canonical),
            "last_upload": _fresh(canonical),
            "status": status,
        })

    summary = {
        "synced_ok": sum(1 for s in synced if s["status"] == "ok"),
        "synced_total": len(synced),
        "manual_needs_you": sum(1 for m in manual if m["status"] == "needs_you"),
        "manual_valid": sum(1 for m in manual if m["status"] == "valid"),
    }
    return {"synced": synced, "manual": manual, "summary": summary}
