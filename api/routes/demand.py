"""
Reference feature slice — demand drill L1 -> L2 -> L3.

Wave-0 ships this as the TEMPLATE (and Wave-2 Agent A extends it). Shows the pattern:
self-registering router + neutral DuckDB views + contract models. Copy this shape for
data / order / results slices.
"""
from __future__ import annotations
from fastapi import APIRouter, Query
from deps.duck import q
from models.contracts import OutletRow, SkuRow, SkuDetail, Driver

router = APIRouter(prefix="/demand", tags=["demand"])

def _latest_date() -> str:
    r = q("SELECT max(date) d FROM forecast")
    return str(r[0]["d"]) if r and r[0]["d"] else ""

@router.get("/dates")
def dates():
    return [str(r["d"]) for r in q("SELECT DISTINCT date d FROM forecast ORDER BY d")]

@router.get("/network", response_model=list[OutletRow])
def network(date: str | None = Query(None)):
    date = date or _latest_date()
    return q("""
        SELECT f.outlet_id, b.outlet_name, b.brand,
               sum(f.order_qty)             AS order_units,
               sum(f.order_qty*f.price)     AS value_ks,
               count(DISTINCT f.product_id) AS sku_count,
               1 - (sum(abs(f.actual-f.expected)) / nullif(sum(abs(f.actual)),0)) AS accuracy
        FROM forecast f LEFT JOIN dim_branch b USING (outlet_id)
        WHERE f.date = ?
        GROUP BY 1,2,3 ORDER BY order_units DESC
    """, [date])

@router.get("/outlet/{outlet_id}", response_model=list[SkuRow])
def outlet(outlet_id: int, date: str | None = Query(None), hide_zero: bool = Query(False)):
    date = date or _latest_date()
    # Compute yesterday + avg_7d via window functions over the full history for this outlet
    sql = """
        WITH hist AS (
            SELECT product_id, outlet_id, date, actual,
                   LAG(actual) OVER (PARTITION BY outlet_id, product_id ORDER BY date)      AS yesterday,
                   AVG(actual) OVER (PARTITION BY outlet_id, product_id ORDER BY date
                                     ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING)              AS avg_7d
            FROM forecast
            WHERE outlet_id = ?
        )
        SELECT f.product_id, p.product_name,
               round(f.expected,1)    AS expected,
               round(f.safe,1)        AS safe,
               round(f.max_safe,1)    AS max_safe,
               round(f.order_qty,0)   AS order_qty,
               round(h.yesterday,1)   AS yesterday,
               round(h.avg_7d,1)      AS avg_7d,
               CASE WHEN f.expected > COALESCE(h.avg_7d, f.actual)*1.05 THEN 'up'
                    WHEN f.expected < COALESCE(h.avg_7d, f.actual)*0.95 THEN 'down'
                    ELSE 'flat' END   AS trend
        FROM forecast f
        LEFT JOIN dim_product p USING (product_id)
        LEFT JOIN hist h ON h.outlet_id = f.outlet_id
                        AND h.product_id = f.product_id
                        AND h.date       = f.date
        WHERE f.outlet_id = ? AND f.date = ?
    """
    if hide_zero:
        sql += " AND (f.expected > 0 OR f.order_qty > 0)"
    sql += " ORDER BY f.order_qty DESC"
    return q(sql, [outlet_id, outlet_id, date])

@router.get("/sku", response_model=SkuDetail)
def sku(outlet_id: int, product_id: int, date: str | None = Query(None)):
    date = date or _latest_date()
    head = q("""
        SELECT f.product_id, p.product_name, f.outlet_id, b.outlet_name, f.price, p.category,
               f.expected, f.safe, f.max_safe, f.order_qty
        FROM forecast f LEFT JOIN dim_product p USING (product_id)
                        LEFT JOIN dim_branch  b USING (outlet_id)
        WHERE f.outlet_id=? AND f.product_id=? AND f.date=?
    """, [outlet_id, product_id, date])
    h = head[0] if head else {}

    history = q("""
        SELECT CAST(date AS VARCHAR) date, round(actual,1) actual,
               round(expected,1) expected, round(safe,1) safe
        FROM forecast WHERE outlet_id=? AND product_id=? ORDER BY date
    """, [outlet_id, product_id])

    # Accuracy over full history
    acc_row = q("""
        SELECT 1 - (sum(abs(actual - expected)) / nullif(sum(abs(actual)), 0)) AS accuracy
        FROM forecast WHERE outlet_id=? AND product_id=?
    """, [outlet_id, product_id])
    accuracy = acc_row[0]["accuracy"] if acc_row else None

    # Drivers: weekend lift + recent trend (honest/simple, no model internals)
    drv_row = q("""
        SELECT
            AVG(CASE WHEN dayofweek(date) IN (1, 7) THEN actual END)     AS weekend_avg,
            AVG(CASE WHEN dayofweek(date) NOT IN (1, 7) THEN actual END) AS weekday_avg,
            AVG(CASE WHEN date >= (CAST(? AS DATE) - INTERVAL 7 DAY) THEN actual END)  AS recent_7,
            AVG(CASE WHEN date >= (CAST(? AS DATE) - INTERVAL 14 DAY)
                      AND date <  (CAST(? AS DATE) - INTERVAL 7 DAY) THEN actual END)  AS prior_7
        FROM forecast WHERE outlet_id=? AND product_id=?
    """, [date, date, date, outlet_id, product_id])
    d = drv_row[0] if drv_row else {}

    drivers: list[Driver] = []

    # Recent trend
    r7 = d.get("recent_7") or 0.0
    p7 = d.get("prior_7") or 0.0
    if p7 and p7 > 0:
        trend_pct = round((r7 - p7) / p7 * 100, 1)
        sign = "up" if trend_pct > 0 else "down" if trend_pct < 0 else "flat"
        drivers.append(Driver(
            label="recent trend",
            effect_pct=trend_pct,
            note=f"{sign} {abs(trend_pct)}% vs prior week"
        ))
    else:
        drivers.append(Driver(label="recent trend", effect_pct=0.0, note="vs prior week"))

    # Weekend lift (only meaningful if there's variance)
    we_avg = d.get("weekend_avg") or 0.0
    wd_avg = d.get("weekday_avg") or 0.0
    if wd_avg and wd_avg > 0 and we_avg > 0:
        lift_pct = round((we_avg - wd_avg) / wd_avg * 100, 1)
        if abs(lift_pct) >= 5:
            drivers.append(Driver(
                label="weekend pattern",
                effect_pct=lift_pct,
                note=f"weekends avg {round(we_avg,1)} vs weekdays {round(wd_avg,1)}"
            ))

    return SkuDetail(
        product_id=h.get("product_id", product_id),
        product_name=h.get("product_name", ""),
        outlet_id=outlet_id, outlet_name=h.get("outlet_name", ""),
        price=h.get("price"), category=h.get("category"), date=date,
        expected=h.get("expected", 0), safe=h.get("safe", 0),
        max_safe=h.get("max_safe", 0), order_qty=h.get("order_qty", 0),
        history=history, drivers=drivers,
        accuracy=accuracy,
    )
