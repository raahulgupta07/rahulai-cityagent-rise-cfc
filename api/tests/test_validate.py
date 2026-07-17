"""Upload validation: bad rows blocked, clean rows accepted, templates downloadable."""
import io
import pandas as pd
from services.validate import validate_upload


def _first_valid_outlet() -> int:
    from services.validate import _valid_branch_ids
    return sorted(_valid_branch_ids())[0]


def test_promo_bad_range_blocked():
    oid = _first_valid_outlet()
    df = pd.DataFrame({
        "date": ["2026-06-20", "2026-06-21"],
        "outlet_id": [oid, oid],
        "discount_pct": [10, 999],          # 999 out of [0,90]
        "promo_type": ["BOGO", "banana"],   # invalid type
    })
    res = validate_upload("promo_calendar", df)
    assert res["ok"] is False
    assert any("discount_pct" in e for e in res["range_errors"])
    assert any("promo_type" in e for e in res["range_errors"])


def test_promo_clean_accepted():
    oid = _first_valid_outlet()
    df = pd.DataFrame({
        "date": ["2026-06-20"],
        "outlet_id": [oid],
        "discount_pct": [15],
        "promo_type": ["%off"],
    })
    res = validate_upload("promo_calendar", df)
    assert res["ok"] is True
    assert res["matched"] == 1
    assert res["range_errors"] == []


def test_template_downloadable(client):
    for key in ("promo_calendar", "lead_time_sla", "product_economics", "inventory_daily"):
        r = client.get(f"/data/template/{key}")
        assert r.status_code == 200, f"template {key} → {r.status_code}"
        # openpyxl xlsx or csv — must be non-empty binary
        assert len(r.content) > 100
