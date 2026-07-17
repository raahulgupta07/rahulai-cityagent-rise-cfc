"""
DuckDB spine — read-only views over the engine's parquet outputs.

CENTRAL field-neutralizer: internal model column names (p50/p85/p95) are renamed here
ONCE to client-facing terms (expected/safe/max). Every feature slice queries these views,
so method names can NEVER leak to the UI and there is one place to change the mapping.

Forecast data stays in parquet (data/predictions, data/raw). Uploaded/business data
lives in SQLite (deps/db.py). This module is the only reader of parquet.
"""
from __future__ import annotations
import logging, pathlib
import duckdb

log = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PRED = ROOT / "data" / "predictions"
RAW = ROOT / "data" / "raw"

_con: duckdb.DuckDBPyConnection | None = None

def con() -> duckdb.DuckDBPyConnection:
    """Singleton read-only connection with neutral views registered.

    Each view is created independently and FAIL-SOFT: on a fresh deploy the parquet
    outputs may not exist yet (data/ is not shipped; live data comes from Fabric or a
    later pipeline run). A missing file must NOT crash app import — the view is just
    skipped (endpoints that need it degrade; the rest of the app + Fabric path work).
    Re-create views (pick up newly-arrived parquet) by restarting the API.
    """
    global _con
    if _con is not None:
        return _con
    c = duckdb.connect(database=":memory:")
    op = (PRED / "order_plan.parquet").as_posix()
    bt = (PRED / "backtest_preds.parquet").as_posix()
    dp = (RAW / "dim_product.parquet").as_posix()
    db = (RAW / "dim_branch.parquet").as_posix()

    def _view(name: str, sql: str) -> None:
        try:
            c.execute(sql)
        except Exception as exc:
            log.warning("duck: view '%s' not created (missing/unreadable parquet): %s", name, exc)

    # ── neutral forecast view: p50/p85/p95 -> expected/safe/max (names hidden) ──
    _view("forecast", f"""
        CREATE VIEW forecast AS
        SELECT
            CAST(date AS DATE)          AS date,
            BranchId                    AS outlet_id,
            ProductId                   AS product_id,
            CAST(p50 AS DOUBLE)         AS expected,
            CAST(p85 AS DOUBLE)         AS safe,
            CAST(p95 AS DOUBLE)         AS max_safe,
            CAST(order_qty AS DOUBLE)   AS order_qty,
            CAST(y AS DOUBLE)           AS actual,
            CAST(price AS DOUBLE)       AS price,
            abc                         AS class
        FROM read_parquet('{op}')
    """)
    _view("dim_product", f"CREATE VIEW dim_product AS SELECT ProductId AS product_id, ProductName AS product_name, ProductCode AS product_code, CatLvl2_Name AS category, ListPrice AS list_price FROM read_parquet('{dp}')")
    _view("dim_branch",  f"CREATE VIEW dim_branch  AS SELECT BranchId AS outlet_id, BranchName AS outlet_name, BranchCode AS outlet_code, Segment AS brand, ChannelId AS channel_id, Address AS address FROM read_parquet('{db}')")
    _view("backtest",    f"CREATE VIEW backtest AS SELECT CAST(date AS DATE) AS date, BranchId AS outlet_id, ProductId AS product_id, CAST(y AS DOUBLE) AS actual, CAST(p50 AS DOUBLE) AS expected, CAST(p85 AS DOUBLE) AS safe FROM read_parquet('{bt}')")
    _con = c
    return _con

def q(sql: str, params: list | None = None):
    """Run a query, return list[dict]."""
    cur = con().execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def healthcheck() -> tuple[bool, str]:
    """Deep health: the analytics spine can open and query its parquet-backed views.

    Returns (ok, detail). Used by /health so orchestrators (compose, load balancer)
    see a real readiness signal, not just 'process is up'.
    """
    try:
        con().execute("SELECT 1 FROM forecast LIMIT 1").fetchone()
        return True, "ok"
    except Exception as exc:
        log.warning("duck healthcheck failed: %s", exc)
        return False, f"analytics store unavailable: {exc}"
