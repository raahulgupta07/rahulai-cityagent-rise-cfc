"""
CFC Bakery — data extraction (staged).

Stage A: small tables (masters + dims) — fast, validate joins/structure first.
Stage B: the 13.4M demand fact — chunked by month (run after A is verified).

Usage:
    python3 src/extract.py small          # Stage A — all master/dim tables
    python3 src/extract.py fact           # Stage B — demand panel (INCREMENTAL if it exists)
    python3 src/extract.py fact --full    # force a full rebuild of the demand panel
    python3 src/extract.py all            # A then B

Incremental behaviour (Stage B):
    - First run (no demand_panel.parquet)  -> full pull from START.
    - Later runs                            -> pull only DayKey >= (max local DayKey - OVERLAP_DAYS),
                                               then upsert into the existing panel. The overlap re-pulls
                                               a tail window because same-day rows change as refunds/voids
                                               post after the fact. Keyed on DayKey x BranchId x ProductId.
"""
import sys, time, pathlib, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import fabric_user_connector as fc

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

DB = "HUB_REPORTING_DB"
START = "20230101"                 # demand window start (first full pull)
OVERLAP_DAYS = 7                   # re-pull this many days behind the watermark (late adjustments)
FACT = RAW / "demand_panel.parquet"


def _end_key() -> str:
    """Upper bound (exclusive) = tomorrow, so today's partial day is included."""
    return (dt.date.today() + dt.timedelta(days=1)).strftime("%Y%m%d")


def rq(sql, tries=5):
    for i in range(tries):
        try:
            return fc.q(sql)
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


# ---- Stage A: small tables ----
SMALL = {
    # file_stem : (schema.table, select-cols or "*")
    "dim_product":      ("cfc.Ref_Product_Master",
        "ProductId,ProductName,ProductCode,OldProductCode,ListPrice,UoM,Factor,Active,"
        "CategoryId,CategoryName,CatLvl1_Name,CatLvl2_Name,CatLvl3_Name,CatLvl4_Name,CatLvl5_Name"),
    "dim_branch":       ("cfc.Ref_Branch_Master",
        "BranchId,BranchName,BranchCode,V5LocationCode,CompanyId,CompanyName,Segment,CostCenter,"
        "ProfitCenter,PartnerId,StockInId,StockOutId,MainBranch,OpeningDate,TimingInfo,ChannelId,Address,Telephone"),
    "dim_warehouse":    ("cfc.Ref_StockWarehouse_Master",
        "WarehouseId,WarehouseName,Code,ActiveFlag,CompanyId,PartnerId,BranchId,"
        "BuyToResupply,ManufactureToResupply,ManuTypeId,Sequence"),
    "dim_stocklocation":("cfc.Ref_StockLocation_Master",
        "StockLocId,StockLocName,ParentPathName,ActiveFlag,Usage,BranchId,CompanyId,"
        "StockLocLvl1_Name,StockLocLvl2_Name,StockLocLvl3_Name"),
    "dim_uom":          ("cfc.Ref_Uom_Master", "*"),
    "dim_partner":      ("cfc.Ref_Partner_Master", "*"),
    "dim_channel":      ("cfc.Dim_Channel", "*"),
    "dim_company":      ("cfc.Dim_Company", "*"),
    "dim_costcenter":   ("cfc.Dim_CostCenter", "*"),
    "dim_profitcenter": ("cfc.Dim_ProfitCenter", "*"),
    "dim_segment":      ("cfc.Dim_Segment", "*"),
}


def extract_small():
    print("=== Stage A: small tables ===")
    summary = []
    for stem, (tab, cols) in SMALL.items():
        df = rq(f"SELECT {cols} FROM {DB}.{tab}")
        out = RAW / f"{stem}.parquet"
        df.to_parquet(out, index=False)
        print(f"  {stem:18} {len(df):>6} rows, {df.shape[1]:>2} cols -> {out.name}")
        summary.append((stem, tab, len(df), df.shape[1]))

    # derived branch -> warehouse map
    import pandas as pd
    br = pd.read_parquet(RAW / "dim_branch.parquet")
    wh = pd.read_parquet(RAW / "dim_warehouse.parquet")
    mp = br[["BranchId", "BranchName", "BranchCode", "StockInId", "StockOutId"]].copy()
    whb = wh[["WarehouseId", "WarehouseName", "Code", "BranchId"]].rename(
        columns={"BranchId": "wh_BranchId"})
    mp = mp.merge(whb, left_on="BranchId", right_on="wh_BranchId", how="left")
    mp.to_parquet(RAW / "branch_warehouse_map.parquet", index=False)
    print(f"  {'branch_warehouse_map':18} {len(mp):>6} rows -> branch_warehouse_map.parquet")

    print("\n--- QC ---")
    prod = pd.read_parquet(RAW / "dim_product.parquet")
    print(f"  products: {len(prod)} | active: {int(prod['Active'].sum())} | "
          f"FG: {int((prod['CatLvl1_Name']=='FG').sum())}")
    print(f"  branches: {len(br)} | with StockOut: {int(br['StockOutId'].notna().sum())}")
    print(f"  warehouses: {len(wh)} | linked to branch: {int(wh['BranchId'].notna().sum())}")
    unmapped = mp['WarehouseId'].isna().sum()
    print(f"  branches with NO warehouse match: {unmapped}")
    return summary


# ---- Stage B: demand fact (chunked by month) ----
def month_bounds(start, end):
    y, m = int(start[:4]), int(start[4:6])
    ey, em = int(end[:4]), int(end[4:6])
    out = []
    while (y, m) < (ey, em):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((f"{y}{m:02d}01", f"{ny}{nm:02d}01"))
        y, m = ny, nm
    return out


_FACT_COLS = "DayKey, BranchId, ProductId"


def _watermark():
    """Max DayKey already in the local panel, or None if there is no panel yet."""
    if not FACT.exists():
        return None
    import pandas as pd
    try:
        s = pd.read_parquet(FACT, columns=["DayKey"]).DayKey.astype(str)
        return s.max() if len(s) else None
    except Exception:
        return None


def _pull_range(start_key: str, end_key: str):
    """Pull the fact in monthly batches over [start_key, end_key). Returns a DataFrame."""
    import pandas as pd
    parts = []
    for ms, me in month_bounds(start_key, end_key):
        sql = f"""
            SELECT DayKey, BranchId, ProductId,
                   SUM(Quantity)                                 AS gross_units,
                   SUM(Quantity - RefundQuantity - VoidQuantity) AS net_units,
                   SUM(RefundQuantity)                           AS refund_units,
                   SUM(VoidQuantity)                             AS void_units,
                   SUM(Amount)                                   AS amount,
                   SUM(Discount)                                 AS discount,
                   SUM(TransCount)                               AS txns
            FROM {DB}.edm.CFC_PBID_Sales_Summary
            WHERE DayKey >= '{ms}' AND DayKey < '{me}'
            GROUP BY DayKey, BranchId, ProductId
        """
        df = rq(sql)
        parts.append(df)
        print(f"  batch {ms[:6]}: {len(df):>7} rows")
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def extract_fact(full: bool = False):
    import pandas as pd
    end = _end_key()
    wm = None if full else _watermark()

    if wm is None:
        print(f"=== Stage B: demand fact — FULL pull {START}..{end} (monthly batches) ===")
        panel = _pull_range(START, end)
    else:
        # re-pull a tail window behind the watermark to catch late refund/void adjustments
        wm_date = dt.datetime.strptime(str(wm), "%Y%m%d").date()
        repull_start = (wm_date - dt.timedelta(days=OVERLAP_DAYS)).strftime("%Y%m%d")
        print(f"=== Stage B: demand fact — INCREMENTAL. watermark {wm}, re-pull from {repull_start}..{end} ===")
        fresh = _pull_range(repull_start, end)
        old = pd.read_parquet(FACT)
        # drop the overlap range from the old panel, then append the fresh pull (upsert by replace)
        old["DayKey"] = old.DayKey.astype(str)
        kept = old[old.DayKey < repull_start]
        panel = pd.concat([kept, fresh], ignore_index=True)
        print(f"  kept {len(kept):,} old rows (< {repull_start}) + {len(fresh):,} fresh -> merge")

    if panel.empty:
        print("  no rows pulled (nothing new). panel unchanged.")
        return

    panel = (panel.sort_values(["DayKey", "BranchId", "ProductId"])
                  .drop_duplicates(["DayKey", "BranchId", "ProductId"], keep="last")
                  .reset_index(drop=True))
    panel.to_parquet(FACT, index=False)
    print(f"\nTOTAL {len(panel):,} rows -> {FACT}")
    print(f"  date range: {panel.DayKey.min()} .. {panel.DayKey.max()}")
    print(f"  branches: {panel.BranchId.nunique()} | products: {panel.ProductId.nunique()}")
    print(f"  negative net_units rows: {int((panel.net_units < 0).sum())}")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else "small"
    full = "--full" in args
    if cmd in ("small", "all"):
        extract_small()
    if cmd in ("fact", "all"):
        extract_fact(full=full)
