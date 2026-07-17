"""
Analysis slice — P5. The full report, wired live from the pipeline outputs.

Parses the markdown reports + deck_metrics.json into structured, NEUTRALISED sections
(the Analysis screen renders these). Method/metric names are stripped on the way out:
WMAPE -> Error, P50/P85/P95 -> Expected/Safe/Max, LGBM -> Model, etc.

Endpoint:
  GET /analysis  -> { data_glance, yearly, dow, brand_mix, concentration, patterns,
                      abc, festival, baselines, accuracy, calibration, cost_sim,
                      service_tradeoff, drift }
"""
from __future__ import annotations
import json
import re
import pathlib
from fastapi import APIRouter

router = APIRouter(prefix="/analysis", tags=["analysis"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REP = ROOT / "reports"


def _read(name: str) -> str:
    p = REP / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


# ── neutraliser: never leak method/metric names ─────────────────────────────
_NEUTRAL = {
    "LGBM newsvendor (CR=0.35)": "Smart order",
    "newsvendor (per-product CR)": "Smart order",
    "baseline (moving_avg_7)": "7-day average",
    "baseline mov_avg_7": "7-day average",
    "moving_avg_28": "28-day average",
    "moving_avg_7": "7-day average",
    "seasonal_naive_7 (same wkday)": "Same weekday",
    "seasonal_naive_7": "Same weekday",
    "naive_lag1 (yesterday)": "Yesterday",
    "naive_lag1": "Yesterday",
    "dow_mean_28 (wkday avg)": "Weekday average",
    "dow_mean_28": "Weekday average",
    "LGBM P50": "Expected", "LGBM P85": "Safe", "LGBM P95": "Max",
    "flat P50": "Expected", "flat P85": "Safe", "flat P95": "Max",
    "P50": "Expected", "P85": "Safe", "P95": "Max",
    "WMAPE": "Error", "LGBM": "Model", "pinball": "score",
    "order quantile": "order level", "quantile": "level",
}
_NEUTRAL_KEYS = sorted(_NEUTRAL, key=len, reverse=True)


def _neutralise(s: str) -> str:
    out = s
    for k in _NEUTRAL_KEYS:
        out = re.sub(re.escape(k), _NEUTRAL[k], out, flags=re.IGNORECASE)
    # catch any remaining quantile notation (~P30, P70, …) not in the map
    out = re.sub(r"~?P\d+", "level", out)
    return out


# ── generic markdown-table parser ───────────────────────────────────────────
def _tables(md: str) -> list[dict]:
    """Return [{columns:[...], rows:[[cells]]}] for every pipe-table in md."""
    tables: list[dict] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|?$", lines[i + 1].strip()):
            cols = [c.strip() for c in line.strip("|").split("|")]
            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines) and lines[j].strip() == "":   # tolerate blank line after separator
                j += 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if any(cells):
                    rows.append([_neutralise(c) for c in cells])
                j += 1
            tables.append({"columns": [_neutralise(c) for c in cols], "rows": rows})
            i = j
        else:
            i += 1
    return tables


def _find_table(md: str, must_have: list[str]) -> dict | None:
    """First table whose header row contains all `must_have` substrings (post-neutralise)."""
    for t in _tables(md):
        hdr = " ".join(t["columns"]).lower()
        if all(h.lower() in hdr for h in must_have):
            return t
    return None


def _num(pat: str, txt: str, comma=False):
    m = re.search(pat, txt)
    if not m:
        return None
    s = m.group(1).replace(",", "") if comma else m.group(1)
    try:
        return float(s)
    except ValueError:
        return None


# ── assemble ─────────────────────────────────────────────────────────────────
@router.get("")
def analysis():
    prof = _read("demand_profile.md")
    ev = _read("eval.md")
    base = _read("baselines.md")
    svc = _read("service_tradeoff.md")
    drift = _read("drift_monitor.md")
    metrics = {}
    mf = REP / "deck_metrics.json"
    if mf.exists():
        try:
            metrics = json.loads(mf.read_text())
        except Exception:
            metrics = {}

    # 1. data at a glance (prose in demand_profile.md)
    data_glance = {
        "net_units": _num(r"Net units sold \(all time\):\s*\*\*([\d,]+)", prof, comma=True),
        "revenue_ks": _num(r"Revenue \(all time\):\s*\*\*([\d,]+)", prof, comma=True),
        "branches": _num(r"Active branches:\s*\*\*(\d+)", prof),
        "products": _num(r"active products:\s*\*\*(\d+)", prof),
        "days": _num(r"days:\s*\*\*(\d+)", prof),
        "series": _num(r"active series \(branch.SKU\):\s*\*\*([\d,]+)", prof, comma=True),
    }

    # 2. net units by year (bullet list)
    yearly = [{"year": y, "units": int(u.replace(",", ""))}
              for y, u in re.findall(r"- (20\d\d):\s*([\d,]+)", prof)]

    # 3. day of week
    dow = {
        "peak_day": (re.search(r"Peak day:\s*\*\*(\w+)", prof) or [None, None])[1] if re.search(r"Peak day", prof) else None,
        "peak_ratio": _num(r"Peak/trough ratio:\s*\*\*([0-9.]+)", prof),
    }

    # 4. brand mix (bullet list with %)
    brand_mix = [{"brand": b, "units": int(u.replace(",", "")), "share_pct": float(p)}
                 for b, u, p in re.findall(r"- (\w[\w ]*?):\s*([\d,]+) units,[^(]*\(([\d.]+)%\)", prof)]

    # 5. concentration
    concentration = {
        "top10_branch_pct": _num(r"Top 10 branches\s*=\s*\*\*(\d+)%", prof),
        "top_branches": [{"name": n.strip(), "units": int(u.replace(",", ""))}
                         for n, u in re.findall(r"- ([\w ]+Branch):\s*([\d,]+)", prof)][:5],
        "top_products": [{"name": n.strip(), "units": int(u.replace(",", ""))}
                         for n, u in re.findall(r"- ([\w '&]+?):\s*([\d,]+)",
                                                prof.split("Top 10 products by units:")[-1])][:5],
    }

    # 6. demand patterns + 7. ABC + 8. festival (tables/prose)
    pat_tbl = _find_table(prof, ["Pattern", "Series"])
    patterns = pat_tbl["rows"] if pat_tbl else []
    abc = {
        "a": _num(r"A:\s*(\d+) products", prof), "b": _num(r"B:\s*(\d+) products", prof),
        "c": _num(r"C:\s*(\d+) products", prof),
        "a_vol_pct": 80 if _num(r"\((\d+)\) drive 80%", prof) else None,
    }
    festival = {
        "normal": _num(r"Normal day avg:\s*([\d,]+)", prof, comma=True),
        "holiday_pct": _num(r"Public holiday avg:.*?\(\+([0-9]+)%", prof),
        "thingyan_pct": _num(r"Thingyan window avg:.*?\(-([0-9]+)%", prof),
    }

    # 9. baselines (neutralised table)
    baselines = _find_table(base, ["Baseline", "Error"]) or _find_table(base, ["Baseline"])

    # 10. accuracy — folds + by-class from eval.md
    folds = []
    for m in re.finditer(r"\|\s*(2026-\d\d)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*\+(\d+)%", ev):
        folds.append({"period": m.group(1), "model_acc": round((1 - float(m.group(2))) * 100, 1),
                      "floor_acc": round((1 - float(m.group(3))) * 100, 1), "gain_pct": int(m.group(4))})
    by_class = []
    for m in re.finditer(r"\|\s*([ABC])\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*\+(\d+)%\s*\|\s*(\d+)%", ev):
        by_class.append({"cls": m.group(1), "accuracy": round((1 - float(m.group(2))) * 100, 1),
                         "gain_pct": int(m.group(4)), "vol_share": int(m.group(5))})

    # 11. calibration (deck_metrics.json — neutral labels)
    calibration = [
        {"level": "Expected", "coverage": metrics.get("cov50"), "target": 50, "score": metrics.get("pin50")},
        {"level": "Safe", "coverage": metrics.get("cov85"), "target": 85, "score": metrics.get("pin85")},
        {"level": "Max", "coverage": metrics.get("cov95"), "target": 95, "score": metrics.get("pin95")},
    ]

    # 12. cost sim (eval.md order-policy table, neutralised)
    cost_sim = _find_table(ev, ["policy", "cost"]) or _find_table(ev, ["cost"])

    # 13. service tradeoff
    service_tradeoff = _find_table(svc, ["service"]) or (_tables(svc)[0] if _tables(svc) else None)

    # 14. drift
    drift_psi = _find_table(drift, ["feature", "PSI"])
    drift_out = {
        "psi": drift_psi["rows"] if drift_psi else [],
        "champion_error": _num(r"champion holdout WMAPE.*?:\s*([0-9.]+)", drift),
        "recent_error": _num(r"recent-window WMAPE.*?:\s*([0-9.]+)", drift),
        "verdict": (re.search(r"Verdict:\s*\*\*(.+?)\*\*", drift) or [None, None])[1] if "Verdict" in drift else None,
        "data_drift": "data drift=yes" in drift,
        "accuracy_drift": "accuracy drift=yes" in drift,
    }

    return {
        "data_glance": data_glance,
        "yearly": yearly,
        "dow": dow,
        "brand_mix": brand_mix,
        "concentration": concentration,
        "patterns": patterns,
        "abc": abc,
        "festival": festival,
        "baselines": baselines,
        "accuracy": {"folds": folds, "by_class": by_class,
                     "overall": round((1 - metrics.get("wmape", 0.341)) * 100, 1) if metrics else None},
        "calibration": calibration,
        "cost_sim": cost_sim,
        "service_tradeoff": service_tradeoff,
        "drift": drift_out,
    }
