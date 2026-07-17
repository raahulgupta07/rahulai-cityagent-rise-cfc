"""
Schema / ER view slice — Wave-3 P8.

Prefix: /schema
Auto-mounted by routes/__init__.py. Never edit main.py.

Endpoints:
  GET /schema/tables              — all 15 tables (name, schema, rows, definition, pk)
  GET /schema/columns/{table}     — columns for one table (name, type, definition, sample)
  GET /schema/relationships       — FK link list
"""
from __future__ import annotations
import pathlib, logging
import duckdb

from fastapi import APIRouter, HTTPException

log = logging.getLogger(__name__)
router = APIRouter(prefix="/schema", tags=["schema"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RAW  = ROOT / "data" / "raw"

# ── parquet file for each table (None = not yet extracted) ──────────────────
_PARQUET: dict[str, str | None] = {
    "CFC_PBID_Sales_Summary":      "demand_panel",
    "CFC_PBID_BranchSales":        None,
    "CFC_PBID_SlipDiscount_Summary": None,
    "CFC_PBID_BranchSlipDiscount": None,
    "Ref_Branch_Master":           "dim_branch",
    "Ref_Product_Master":          "dim_product",
    "Ref_Partner_Master":          "dim_partner",
    "Ref_StockWarehouse_Master":   "dim_warehouse",
    "Ref_StockLocation_Master":    "dim_stocklocation",
    "Ref_Uom_Master":              "dim_uom",
    "Dim_Channel":                 "dim_channel",
    "Dim_Company":                 "dim_company",
    "Dim_Segment":                 "dim_segment",
    "Dim_CostCenter":              "dim_costcenter",
    "Dim_ProfitCenter":            "dim_profitcenter",
}

# ── table metadata from DATA_DICTIONARY.md ──────────────────────────────────
_TABLE_META: dict[str, dict] = {
    "CFC_PBID_Sales_Summary": {
        "schema": "edm",
        "pk": "DayKey + BranchId + ProductId + CardType",
        "definition": (
            "Pre-aggregated daily sales — one row per DayKey × BranchId × ProductId × CardType. "
            "13.39M source rows; 84 active branches, 3,790 products, 2022-06-21 → 2026-06-23. "
            "Forecast target = net_units = Quantity − RefundQuantity − VoidQuantity (SUM over CardType). "
            "DayKey is VARCHAR 'YYYYMMDD' — cast to date and filter ≥ '20230101' to drop garbage 1970 dates."
        ),
        "estimated_rows": 7_084_242,
    },
    "CFC_PBID_BranchSales": {
        "schema": "edm",
        "pk": "DayKey + BranchId",
        "definition": (
            "Branch × day rollup (~86 k rows). Fast branch-level baseline without product grain. "
            "Not yet extracted to local parquet — sample pending approved Fabric pull."
        ),
        "estimated_rows": 86_000,
    },
    "CFC_PBID_SlipDiscount_Summary": {
        "schema": "edm",
        "pk": "DayKey + BranchId + ProductId",
        "definition": (
            "Discount by product × branch × day (~6.7 k rows). "
            "Promo-lift signal source: compare DiscountAmount vs net_units. "
            "Not yet extracted to local parquet."
        ),
        "estimated_rows": 6_700,
    },
    "CFC_PBID_BranchSlipDiscount": {
        "schema": "edm",
        "pk": "DayKey + BranchId",
        "definition": (
            "Discount totals at branch × day level (~5.2 k rows). "
            "Branch-level discount rollup. Not yet extracted to local parquet."
        ),
        "estimated_rows": 5_200,
    },
    "Ref_Branch_Master": {
        "schema": "cfc",
        "pk": "BranchId",
        "definition": (
            "98 outlet master records (84 with sales). "
            "Brand via Segment field; supply chain via StockInId/StockOutId → Ref_StockWarehouse_Master. "
            "Address is used to derive city for weather join. "
            "~14% of ChannelId are null (older branches)."
        ),
        "estimated_rows": 98,
    },
    "Ref_Product_Master": {
        "schema": "cfc",
        "pk": "ProductId",
        "definition": (
            "29,515 SKU master records (3,580 sell). "
            "5-level category tree; filter CatLvl1_Name = 'FG' for sellable finished-goods. "
            "ListPrice present but cost/margin absent — use product_econ.csv for GM + shelf life. "
            "'_Unused_Archived' names = dead SKUs (Active = False)."
        ),
        "estimated_rows": 29_515,
    },
    "Ref_Partner_Master": {
        "schema": "cfc",
        "pk": "PartnerId",
        "definition": (
            "4,918 partners (suppliers, franchisees, etc.) with geo and contact details. "
            "Linked from Ref_Branch_Master.PartnerId and Ref_StockWarehouse_Master.PartnerId. "
            "Mostly out of direct forecast scope."
        ),
        "estimated_rows": 4_918,
    },
    "Ref_StockWarehouse_Master": {
        "schema": "cfc",
        "pk": "WarehouseId",
        "definition": (
            "119 warehouse records with replenishment config. "
            "Picklist target: maps branches to their supplying warehouse via "
            "Ref_Branch_Master.StockInId / StockOutId. "
            "BuyToResupply / ManufactureToResupply flags drive supply logic."
        ),
        "estimated_rows": 119,
    },
    "Ref_StockLocation_Master": {
        "schema": "cfc",
        "pk": "StockLocId",
        "definition": (
            "1,409 physical stock locations in a 3-level hierarchy, linked to BranchId. "
            "Downstream of warehouses; mostly out of direct forecast scope."
        ),
        "estimated_rows": 1_409,
    },
    "Ref_Uom_Master": {
        "schema": "cfc",
        "pk": "UomId",
        "definition": (
            "62 units of measure with conversion factors. "
            "Joined from Ref_Product_Master.UoM (by name). "
            "Common units: SLICE, PCS, Days."
        ),
        "estimated_rows": 62,
    },
    "Dim_Channel": {
        "schema": "cfc",
        "pk": "ChannelId",
        "definition": (
            "7-row channel/brand lookup (LS, Gong Cha, Seasons, …). "
            "Joins to Ref_Branch_Master.ChannelId."
        ),
        "estimated_rows": 7,
    },
    "Dim_Company": {
        "schema": "cfc",
        "pk": "CompanyId",
        "definition": (
            "Single operating company record (CityFood Concepts, CompanyId=1). "
            "Top of the org hierarchy; referenced from most master tables."
        ),
        "estimated_rows": 1,
    },
    "Dim_Segment": {
        "schema": "cfc",
        "pk": "SegmentId",
        "definition": (
            "9-row segment/format dimension. "
            "SegmentName is a coded number (40/41/42 …); "
            "Ref_Branch_Master.Segment carries a longer descriptive string — match by prefix."
        ),
        "estimated_rows": 9,
    },
    "Dim_CostCenter": {
        "schema": "cfc",
        "pk": "CostCenterId",
        "definition": (
            "163 accounting cost centres. "
            "CostCenterName is a numeric code; Description ≈ branch name. "
            "Joins to Ref_Branch_Master.CostCenter by name."
        ),
        "estimated_rows": 163,
    },
    "Dim_ProfitCenter": {
        "schema": "cfc",
        "pk": "ProfitCenterId",
        "definition": (
            "85 profit centres by location/mall. "
            "Description ≈ location name (e.g. Junction-8). "
            "Joins to Ref_Branch_Master.ProfitCenter by name."
        ),
        "estimated_rows": 85,
    },
}

# ── column metadata from DATA_DICTIONARY.md ─────────────────────────────────
# Format: table → list of {name, definition}
_COL_META: dict[str, dict[str, str]] = {
    "CFC_PBID_Sales_Summary": {
        "DayKey":    "Calendar day 'YYYYMMDD' VARCHAR; cast to date for analysis; filter ≥ '20230101'",
        "BranchId":  "Outlet identifier → Ref_Branch_Master",
        "ProductId": "SKU identifier → Ref_Product_Master",
        "CardType":  "Loyalty card / payment channel (multiple rows per day×branch×product; SUM over CardType)",
        "gross_units": "Gross units sold before adjustments (Quantity in source)",
        "net_units": "Model forecast target = Quantity − RefundQuantity − VoidQuantity",
        "refund_units": "Refunded units",
        "void_units": "Voided units",
        "amount":    "Gross sales value in Myanmar Kyat (Ks)",
        "discount":  "Discount value applied",
        "txns":      "Number of receipts / transactions (TransCount)",
        "Quantity":         "Gross units sold",
        "RefundQuantity":   "Refunded units",
        "VoidQuantity":     "Voided units",
        "Amount":           "Gross sales value (Ks)",
        "Discount":         "Discount applied",
        "SubTotal":         "Net subtotal",
        "PriceTotalAfterLoyaltyDiscount": "Post-loyalty-discount net",
        "TransCount":       "Receipt count",
        "LoadDate":         "ETL load timestamp",
    },
    "CFC_PBID_BranchSales": {
        "DayKey":    "Calendar day 'YYYYMMDD'",
        "BranchId":  "Outlet → Ref_Branch_Master",
        "Quantity":  "Total units sold (all products)",
        "Amount":    "Total sales value (Ks)",
        "Discount":  "Total discounts",
        "TransCount":"Receipt count",
        "LoadDate":  "ETL load timestamp",
    },
    "CFC_PBID_SlipDiscount_Summary": {
        "DayKey":        "Calendar day 'YYYYMMDD'",
        "BranchId":      "Outlet → Ref_Branch_Master",
        "ProductId":     "SKU → Ref_Product_Master",
        "DiscountAmount":"Discount value on this product×branch×day",
        "Quantity":      "Units sold with discount",
        "TransCount":    "Receipt count",
        "LoadDate":      "ETL load timestamp",
    },
    "CFC_PBID_BranchSlipDiscount": {
        "DayKey":        "Calendar day 'YYYYMMDD'",
        "BranchId":      "Outlet → Ref_Branch_Master",
        "DiscountAmount":"Total discount value at branch×day",
        "TransCount":    "Receipt count",
        "LoadDate":      "ETL load timestamp",
    },
    "Ref_Branch_Master": {
        "BranchId":      "Outlet primary key",
        "BranchName":    "Full outlet name",
        "BranchCode":    "Short code (e.g. LYDSK-DS)",
        "V5LocationCode":"Legacy POS location code",
        "CompanyId":     "→ Dim_Company",
        "CompanyName":   "Company name (denorm)",
        "Segment":       "Brand/format descriptive string (e.g. '42 Latt Sone Dagon Seikkan Drink')",
        "CostCenter":    "Accounting cost centre name → Dim_CostCenter",
        "ProfitCenter":  "Accounting profit centre name → Dim_ProfitCenter",
        "PartnerId":     "Franchisee/partner → Ref_Partner_Master (null for company-owned)",
        "StockInId":     "Inbound warehouse → Ref_StockWarehouse_Master",
        "StockOutId":    "Supplying warehouse → Ref_StockWarehouse_Master",
        "MainBranch":    "Parent branch flag",
        "OpeningDate":   "Branch opening date",
        "TimingInfo":    "Trading hours text",
        "ChannelId":     "→ Dim_Channel (~14% null for older branches)",
        "Address":       "Physical address — used to derive city for weather join",
        "Telephone":     "Contact number",
    },
    "Ref_Product_Master": {
        "ProductId":   "SKU primary key",
        "ProductName": "Product name ('_Unused_Archived' suffix = dead SKU)",
        "ProductCode": "Long product code",
        "OldProductCode": "Legacy code",
        "ListPrice":   "Selling price (Ks); cost/margin NOT in source — use product_econ.csv",
        "UoM":         "Unit of measure name → Ref_Uom_Master",
        "Factor":      "UoM conversion to base unit",
        "Active":      "Active flag (False = archived)",
        "CategoryId":  "Category id",
        "CategoryName":"Top-level category name",
        "CatLvl1_Name":"L1 category (filter 'FG' for sellable finished goods)",
        "CatLvl2_Name":"L2 category",
        "CatLvl3_Name":"L3 category",
        "CatLvl4_Name":"L4 category",
        "CatLvl5_Name":"L5 category (most specific)",
    },
    "Ref_Partner_Master": {
        "PartnerId":         "Partner primary key",
        "PartnerName":       "Legal name",
        "DisplayName":       "Short display name",
        "CompanyId":         "→ Dim_Company",
        "ActiveFlag":        "Is active",
        "Type":              "Partner type (other, supplier, …)",
        "PartnerLatitude":   "Geo latitude",
        "PartnerLongitude":  "Geo longitude",
        "Email":             "Contact email",
        "IsCompany":         "Company vs individual",
        "LoadDate":          "ETL load timestamp",
    },
    "Ref_StockWarehouse_Master": {
        "WarehouseId":          "Warehouse primary key",
        "WarehouseName":        "Warehouse name",
        "Code":                 "Short code",
        "ActiveFlag":           "Is active",
        "CompanyId":            "→ Dim_Company",
        "PartnerId":            "→ Ref_Partner_Master",
        "BranchId":             "→ Ref_Branch_Master (the branch this WH serves)",
        "BuyToResupply":        "Replenish via purchase order",
        "ManufactureToResupply":"Replenish via internal production",
        "ManuTypeId":           "Manufacture type id",
        "Sequence":             "Processing sequence",
    },
    "Ref_StockLocation_Master": {
        "StockLocId":      "Location primary key",
        "StockLocName":    "Location code/name",
        "ParentPathName":  "Hierarchy path",
        "ActiveFlag":      "Is active",
        "Usage":           "Usage type (internal/transit/…)",
        "BranchId":        "→ Ref_Branch_Master",
        "CompanyId":       "→ Dim_Company",
        "StockLocLvl1_Name":"Level 1 in location hierarchy",
        "StockLocLvl2_Name":"Level 2",
        "StockLocLvl3_Name":"Level 3 (most specific)",
    },
    "Ref_Uom_Master": {
        "UomId":       "UoM primary key",
        "UomName":     "Unit name (SLICE, PCS, Days, …) — joined by name from Product.UoM",
        "CategoryId":  "UoM category",
        "Factor":      "Conversion factor to base unit",
        "Rounding":    "Rounding step",
        "ActiveFlag":  "Is active",
        "UomType":     "reference / bigger / smaller",
        "MeasureType": "Measure class (weight, volume, unit, …)",
    },
    "Dim_Channel": {
        "ChannelId":   "Channel primary key",
        "ChannelName": "Channel name (LS, Gong Cha, Seasons, …)",
        "ChannelCode": "Short code",
        "CreateDate":  "Record created",
        "WriteDate":   "Last modified",
        "LoadDate":    "ETL load timestamp",
    },
    "Dim_Company": {
        "CompanyId":   "Company primary key (only 1: CityFood Concepts)",
        "CompanyName": "Company name",
        "LoadDate":    "ETL load timestamp",
    },
    "Dim_Segment": {
        "SegmentId":    "Segment primary key",
        "SegmentName":  "Coded segment number (40/41/42 …)",
        "Description":  "Same as SegmentName; match to Branch.Segment by prefix",
        "CreateDate":   "Record created",
        "WriteDate":    "Last modified",
        "LoadDate":     "ETL load timestamp",
    },
    "Dim_CostCenter": {
        "CostCenterId":   "Cost centre primary key",
        "CostCenterName": "Numeric accounting code (e.g. '4000081')",
        "Description":    "Branch name (~= Ref_Branch_Master.BranchName)",
        "CreateDate":     "Record created",
        "WriteDate":      "Last modified",
        "LoadDate":       "ETL load timestamp",
    },
    "Dim_ProfitCenter": {
        "ProfitCenterId":   "Profit centre primary key",
        "ProfitCenterName": "Numeric code (e.g. '100003')",
        "Description":      "Location name (e.g. Junction-8)",
        "CreateDate":       "Record created",
        "WriteDate":        "Last modified",
        "LoadDate":         "ETL load timestamp",
    },
}

# ── FK relationships ─────────────────────────────────────────────────────────
_RELATIONSHIPS = [
    {"from_table": "CFC_PBID_Sales_Summary",      "from_col": "BranchId",     "to_table": "Ref_Branch_Master",          "to_col": "BranchId"},
    {"from_table": "CFC_PBID_Sales_Summary",      "from_col": "ProductId",    "to_table": "Ref_Product_Master",         "to_col": "ProductId"},
    {"from_table": "CFC_PBID_BranchSales",        "from_col": "BranchId",     "to_table": "Ref_Branch_Master",          "to_col": "BranchId"},
    {"from_table": "CFC_PBID_SlipDiscount_Summary","from_col": "BranchId",    "to_table": "Ref_Branch_Master",          "to_col": "BranchId"},
    {"from_table": "CFC_PBID_SlipDiscount_Summary","from_col": "ProductId",   "to_table": "Ref_Product_Master",         "to_col": "ProductId"},
    {"from_table": "CFC_PBID_BranchSlipDiscount", "from_col": "BranchId",     "to_table": "Ref_Branch_Master",          "to_col": "BranchId"},
    {"from_table": "Ref_Branch_Master",           "from_col": "CompanyId",    "to_table": "Dim_Company",                "to_col": "CompanyId"},
    {"from_table": "Ref_Branch_Master",           "from_col": "ChannelId",    "to_table": "Dim_Channel",                "to_col": "ChannelId"},
    {"from_table": "Ref_Branch_Master",           "from_col": "Segment",      "to_table": "Dim_Segment",                "to_col": "SegmentName",  "note": "match by prefix/name"},
    {"from_table": "Ref_Branch_Master",           "from_col": "CostCenter",   "to_table": "Dim_CostCenter",             "to_col": "CostCenterName","note": "match by name"},
    {"from_table": "Ref_Branch_Master",           "from_col": "ProfitCenter", "to_table": "Dim_ProfitCenter",           "to_col": "ProfitCenterName","note": "match by name"},
    {"from_table": "Ref_Branch_Master",           "from_col": "StockInId",    "to_table": "Ref_StockWarehouse_Master",  "to_col": "WarehouseId"},
    {"from_table": "Ref_Branch_Master",           "from_col": "StockOutId",   "to_table": "Ref_StockWarehouse_Master",  "to_col": "WarehouseId"},
    {"from_table": "Ref_Branch_Master",           "from_col": "PartnerId",    "to_table": "Ref_Partner_Master",         "to_col": "PartnerId"},
    {"from_table": "Ref_Product_Master",          "from_col": "UoM",          "to_table": "Ref_Uom_Master",             "to_col": "UomName",      "note": "match by name"},
    {"from_table": "Ref_StockWarehouse_Master",   "from_col": "BranchId",     "to_table": "Ref_Branch_Master",          "to_col": "BranchId"},
    {"from_table": "Ref_StockWarehouse_Master",   "from_col": "PartnerId",    "to_table": "Ref_Partner_Master",         "to_col": "PartnerId"},
    {"from_table": "Ref_StockWarehouse_Master",   "from_col": "CompanyId",    "to_table": "Dim_Company",                "to_col": "CompanyId"},
    {"from_table": "Ref_StockLocation_Master",    "from_col": "BranchId",     "to_table": "Ref_Branch_Master",          "to_col": "BranchId"},
    {"from_table": "Ref_StockLocation_Master",    "from_col": "CompanyId",    "to_table": "Dim_Company",                "to_col": "CompanyId"},
]

# ── helpers ──────────────────────────────────────────────────────────────────

def _parquet_path(table: str) -> pathlib.Path | None:
    stem = _PARQUET.get(table)
    if stem is None:
        return None
    return RAW / f"{stem}.parquet"


def _real_count(table: str) -> int | None:
    p = _parquet_path(table)
    if p is None or not p.exists():
        return None
    try:
        c = duckdb.connect(":memory:")
        r = c.execute(f"SELECT COUNT(*) FROM read_parquet('{p.as_posix()}')").fetchone()
        return int(r[0]) if r else None
    except Exception:
        return None


def _describe_parquet(table: str) -> list[dict] | None:
    """Return [{name, type}] from parquet DESCRIBE, or None if not available."""
    p = _parquet_path(table)
    if p is None or not p.exists():
        return None
    try:
        c = duckdb.connect(":memory:")
        rows = c.execute(f"DESCRIBE SELECT * FROM read_parquet('{p.as_posix()}')").fetchall()
        return [{"name": r[0], "type": r[1]} for r in rows]
    except Exception:
        return None


def _sample(table: str, col: str) -> str | None:
    p = _parquet_path(table)
    if p is None or not p.exists():
        return None
    try:
        c = duckdb.connect(":memory:")
        r = c.execute(
            f'SELECT "{col}" FROM read_parquet(\'{p.as_posix()}\') WHERE "{col}" IS NOT NULL LIMIT 1'
        ).fetchone()
        return str(r[0]) if r else None
    except Exception:
        return None


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/tables")
def tables():
    """All 15 tables with name, schema, rows, definition, PK."""
    result = []
    for table, meta in _TABLE_META.items():
        real_count = _real_count(table)
        pq_stem = _PARQUET.get(table)
        has_local = pq_stem is not None and (RAW / f"{pq_stem}.parquet").exists()
        result.append({
            "table":     table,
            "schema":    meta["schema"],
            "pk":        meta["pk"],
            "definition":meta["definition"],
            "rows":      real_count if real_count is not None else meta.get("estimated_rows"),
            "rows_exact":real_count is not None,
            "has_local_parquet": has_local,
            "parquet_file": f"{pq_stem}.parquet" if pq_stem else None,
        })
    return result


@router.get("/columns/{table}")
def columns(table: str):
    """Columns for one table (name, type, definition, sample)."""
    if table not in _TABLE_META:
        raise HTTPException(status_code=404, detail=f"Unknown table '{table}'")

    col_defs = _COL_META.get(table, {})
    parquet_cols = _describe_parquet(table)  # [{name, type}] or None

    # Build type map from parquet where available
    type_map: dict[str, str] = {}
    if parquet_cols:
        for pc in parquet_cols:
            type_map[pc["name"]] = pc["type"]

    # Union: known columns from dictionary + any extra from parquet
    all_col_names: list[str] = []
    seen: set[str] = set()
    for name in col_defs:
        if name not in seen:
            all_col_names.append(name)
            seen.add(name)
    if parquet_cols:
        for pc in parquet_cols:
            if pc["name"] not in seen:
                all_col_names.append(pc["name"])
                seen.add(pc["name"])

    result = []
    for name in all_col_names:
        sample = _sample(table, name) if parquet_cols else None
        result.append({
            "name":       name,
            "type":       type_map.get(name, "VARCHAR"),
            "definition": col_defs.get(name, ""),
            "sample":     sample,
        })
    return {"table": table, "columns": result}


@router.get("/relationships")
def relationships():
    """FK link list across all 15 tables."""
    return _RELATIONSHIPS
