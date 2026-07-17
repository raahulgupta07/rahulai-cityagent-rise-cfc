"""
API response contracts — the agreement between api and web.

Wave-0 locks these shapes so the frontend (Wave 1/2) can build against them (or mock)
WITHOUT waiting for backend impl. Client-facing field names only — no engine terms.
Feature slices add their own contract classes here (append-only, low conflict).
"""
from __future__ import annotations
from pydantic import BaseModel

# ── shared ──
class OutletRow(BaseModel):           # L1 network list
    outlet_id: int
    outlet_name: str
    brand: str | None = None
    order_units: float
    value_ks: float
    sku_count: int
    accuracy: float | None = None     # 0..1, neutral

class SkuRow(BaseModel):              # L2 outlet detail row
    product_id: int
    product_name: str
    expected: float
    safe: float
    max_safe: float
    order_qty: float
    yesterday: float | None = None
    avg_7d: float | None = None
    trend: str | None = None          # up/flat/down

class Driver(BaseModel):
    label: str
    effect_pct: float
    note: str | None = None

class SkuDetail(BaseModel):           # L3 sku detail
    product_id: int
    product_name: str
    outlet_id: int
    outlet_name: str
    price: float | None = None
    category: str | None = None
    date: str
    expected: float
    safe: float
    max_safe: float
    order_qty: float
    history: list[dict]               # [{date, actual, expected, safe}]
    drivers: list[Driver]
    accuracy: float | None = None

class PicklistRow(BaseModel):
    product_id: int
    product_name: str
    order_units: float
    outlets: int
    value_ks: float
