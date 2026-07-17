"""
Order-slice extra views: dim_warehouse.

Call ensure_views() once at router startup (via lifespan or direct import with a
module-level call). Adds views to the shared DuckDB connection without touching
duck.py or duck.con() — compatible with the singleton pattern.
"""
from __future__ import annotations
import pathlib
from deps.duck import con, RAW

_registered = False


def ensure_views() -> None:
    """Register dim_warehouse view if not yet present. Idempotent."""
    global _registered
    if _registered:
        return
    c = con()
    dw = (RAW / "dim_warehouse.parquet").as_posix()
    try:
        c.execute("SELECT 1 FROM dim_warehouse LIMIT 0")
    except Exception:
        c.execute(f"""
            CREATE VIEW dim_warehouse AS
            SELECT
                WarehouseId        AS warehouse_id,
                WarehouseName      AS warehouse_name,
                Code               AS warehouse_code,
                BranchId           AS wh_branch_id,
                ActiveFlag         AS active
            FROM read_parquet('{dw}')
        """)
    _registered = True
