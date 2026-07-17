"""
Hydrate local serving parquet from Fabric.

The demand / forecast / ordering screens read local parquet (data/predictions/*.parquet via
deps/duck.py). On a fresh server those files don't exist (data/ is not shipped). The same data
IS in Fabric (cfc_order_plan, cfc_backtest_preds), so at boot we pull those tables down into the
exact parquet files the app expects — the server then serves every screen with NO shipped data.

Best-effort + idempotent: only writes a file if it's missing; never raises. Must run
single-threaded (pyodbc is not thread-safe) — called from the one startup background thread.

Not hydrated (not available in the LK_CFC_Sales SQL endpoint):
  - dim_product / dim_branch names  -> Network shows outlet/product IDs instead of names
  - demand_panel (raw amount/txns)  -> Demand EDA stays "run a sync" until real data is loaded
"""
from __future__ import annotations
import logging, pathlib

log = logging.getLogger(__name__)
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PRED = ROOT / "data" / "predictions"
RAW = ROOT / "data" / "raw"


def hydrate_from_fabric() -> None:
    from deps import fabric
    if not fabric.enabled():
        return
    try:
        import pandas as pd
    except Exception:
        return
    PRED.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    op_path = PRED / "order_plan.parquet"
    bt_path = PRED / "backtest_preds.parquet"

    # ── stub dim tables (names not in the SQL endpoint → use IDs) so joins don't 500 ──
    dp_path = RAW / "dim_product.parquet"
    db_path = RAW / "dim_branch.parquet"
    if not dp_path.exists():
        try:
            dp = pd.DataFrame(fabric.q(
                "SELECT ProductId, MAX(ListPrice) ListPrice, MAX(CatLvl2_Name) CatLvl2_Name, "
                "MAX(CatLvl3_Name) CatLvl3_Name FROM cfc_features GROUP BY ProductId"))
            if len(dp):
                dp["ProductName"] = "Product " + dp["ProductId"].astype(str)
                dp["ProductCode"] = dp["ProductId"].astype(str)
                dp.to_parquet(dp_path, index=False)
                log.info("hydrate: wrote %s (%d products)", dp_path.name, len(dp))
        except Exception as exc:
            log.warning("hydrate dim_product failed: %s", exc)
    if not db_path.exists():
        try:
            db = pd.DataFrame(fabric.q(
                "SELECT BranchId, MAX(Segment) Segment, MAX(ChannelId) ChannelId, "
                "MAX(branch_city) branch_city FROM cfc_features GROUP BY BranchId"))
            if len(db):
                db["BranchName"] = "Outlet " + db["BranchId"].astype(str)
                db["BranchCode"] = db["BranchId"].astype(str)
                db["Address"] = db["branch_city"].astype(str)
                db["Segment"] = db["Segment"].astype(str)   # brand must be string (OutletRow model)
                db.to_parquet(db_path, index=False)
                log.info("hydrate: wrote %s (%d branches)", db_path.name, len(db))
        except Exception as exc:
            log.warning("hydrate dim_branch failed: %s", exc)

    # ── order_plan (small): cfc_order_plan + per-product price/abc lookup ──
    if not op_path.exists():
        try:
            op = pd.DataFrame(fabric.q(
                "SELECT date,BranchId,ProductId,y,p50,p85,p95,CR,order_qty FROM cfc_order_plan"))
            if len(op):
                look = pd.DataFrame(fabric.q(
                    "SELECT ProductId, MAX(ListPrice) price, MAX(abc) abc "
                    "FROM cfc_backtest_preds GROUP BY ProductId"))
                if len(look):
                    op = op.merge(look, on="ProductId", how="left")
                if "price" not in op:
                    op["price"] = 1.0
                if "abc" not in op:
                    op["abc"] = "C"
                op["price"] = op["price"].fillna(1.0)
                op["abc"] = op["abc"].fillna("C")
                op.to_parquet(op_path, index=False)
                log.info("hydrate: wrote %s (%d rows from Fabric cfc_order_plan)", op_path.name, len(op))
        except Exception as exc:
            log.warning("hydrate order_plan failed: %s", exc)

    # ── backtest_preds (larger): direct copy of cfc_backtest_preds ──
    if not bt_path.exists():
        try:
            bt = pd.DataFrame(fabric.q(
                "SELECT date,BranchId,ProductId,y,p50,p85,p95,fold,abc,ListPrice,"
                "rmean_7,lag_1,lag_7,dow_mean_28 FROM cfc_backtest_preds"))
            if len(bt):
                bt.to_parquet(bt_path, index=False)
                log.info("hydrate: wrote %s (%d rows from Fabric cfc_backtest_preds)", bt_path.name, len(bt))
        except Exception as exc:
            log.warning("hydrate backtest_preds failed: %s", exc)
