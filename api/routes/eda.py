"""
EDA slice — live exploratory stats computed straight from the demand panel.

Unlike /analysis (which parses the frozen report markdown), this reads
data/raw/demand_panel.parquet via DuckDB on every call — so right after an
incremental sync, these numbers reflect the newly-added data. Descriptive only,
no model/metric names.

Endpoint:
  GET /eda -> { summary, by_year, by_dow, by_month, top_products, top_branches, freshness }
"""
from __future__ import annotations
import datetime
import pathlib
import duckdb
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/eda", tags=["eda"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "data" / "raw"
PANEL = RAW / "demand_panel.parquet"
DIM_P = RAW / "dim_product.parquet"
DIM_B = RAW / "dim_branch.parquet"

_DOW = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}


def _q(sql: str) -> list[dict]:
    c = duckdb.connect(":memory:")
    cur = c.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@router.get("")
def eda():
    if not PANEL.exists():
        return JSONResponse({"error": "no demand panel yet — run a sync first."}, status_code=404)

    p = f"read_parquet('{PANEL.as_posix()}')"

    summary = _q(f"""
        SELECT count(*) AS rows, count(DISTINCT BranchId) AS branches,
               count(DISTINCT ProductId) AS products,
               sum(net_units) AS net_units, sum(amount) AS revenue,
               min(DayKey) AS first_day, max(DayKey) AS latest_day
        FROM {p} WHERE DayKey >= '20230101'
    """)[0]

    by_year = _q(f"""
        SELECT substr(DayKey,1,4) AS year, sum(net_units) AS units
        FROM {p} WHERE DayKey >= '20230101' GROUP BY 1 ORDER BY 1
    """)

    by_dow_raw = _q(f"""
        SELECT isodow(strptime(DayKey,'%Y%m%d')) AS d, sum(net_units) AS units
        FROM {p} WHERE DayKey >= '20230101' GROUP BY 1 ORDER BY 1
    """)
    by_dow = [{"dow": _DOW.get(int(r["d"]), "?"), "units": r["units"]} for r in by_dow_raw]

    by_month = _q(f"""
        SELECT substr(DayKey,1,6) AS ym, sum(net_units) AS units
        FROM {p} WHERE DayKey >= '20230101' GROUP BY 1 ORDER BY 1 DESC LIMIT 12
    """)[::-1]

    top_products = _q(f"""
        SELECT pr.ProductName AS name, sum(f.net_units) AS units
        FROM {p} f LEFT JOIN read_parquet('{DIM_P.as_posix()}') pr USING (ProductId)
        WHERE f.DayKey >= '20230101' GROUP BY 1 ORDER BY units DESC LIMIT 10
    """) if DIM_P.exists() else []

    top_branches = _q(f"""
        SELECT b.BranchName AS name, sum(f.net_units) AS units
        FROM {p} f LEFT JOIN read_parquet('{DIM_B.as_posix()}') b USING (BranchId)
        WHERE f.DayKey >= '20230101' GROUP BY 1 ORDER BY units DESC LIMIT 10
    """) if DIM_B.exists() else []

    freshness = datetime.datetime.fromtimestamp(PANEL.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

    return {
        "summary": summary,
        "by_year": by_year,
        "by_dow": by_dow,
        "by_month": by_month,
        "top_products": top_products,
        "top_branches": top_branches,
        "freshness": freshness,
    }
