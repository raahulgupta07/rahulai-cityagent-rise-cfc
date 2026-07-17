"""
Explain-forecast slice — plain-language "why is the forecast what it is".

Pulls a few grounding numbers (champion accuracy, typical daily miss in units, the
top feature drivers) from Fabric when it's on, else from the local backtest parquet,
then asks the LLM (services/llm.explain, GLM via OpenRouter) to narrate them in simple
words. If the LLM is unavailable the route returns a deterministic template built from
the SAME numbers, so it always answers — and never leaks internal method/metric names.

Endpoint:
  POST /explain  {version?, branch?, product?, date?, context?} -> {ok, text, model_used, grounded}
"""
from __future__ import annotations
import pathlib
from fastapi import APIRouter
from pydantic import BaseModel

import duckdb

from services import llm

router = APIRouter(prefix="/explain", tags=["explain"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BP = ROOT / "data" / "predictions" / "backtest_preds.parquet"


class ExplainReq(BaseModel):
    version: str | None = None
    branch: str | None = None
    product: str | None = None
    date: str | None = None
    context: dict | None = None


# Raw model feature -> plain everyday phrase (so even the offline template never
# leaks internal column names like rmean_14 / lag_7).
def _humanize(feat: str) -> str:
    f = str(feat).lower()
    if f.startswith(("rmean", "rmed", "roll")):   return "recent sales trend"
    if f.startswith("rstd"):                        return "how bumpy sales have been"
    if f.startswith(("rmax", "rmin")):              return "recent high/low sales"
    if f.startswith("lag"):                         return "what sold on earlier days"
    if "dow" in f or "weekday" in f or "day_of_week" in f: return "day of the week"
    if "month" in f or "season" in f:               return "time of year"
    if "holiday" in f or "festival" in f or "thingyan" in f: return "holidays and festivals"
    if "promo" in f:                                return "promotions"
    if "weather" in f or "rain" in f or "tmax" in f or "temp" in f: return "weather"
    if "product" in f:                              return "the product itself"
    if "branch" in f or "outlet" in f:              return "the outlet"
    if "price" in f or "discount" in f:             return "price and discounts"
    return "recent sales patterns"


def _dedupe(xs: list[str]) -> list[str]:
    out: list[str] = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def _f(v, nd=1):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _grounding_fabric() -> dict | None:
    """{accuracy, units_off, drivers[]} from Fabric, or None if off/unavailable."""
    from deps import fabric
    if not fabric.enabled():
        return None
    try:
        g: dict = {"accuracy": None, "units_off": None, "drivers": []}
        # champion accuracy (1 - wmape) from cfc_model_runs for the live champion version
        try:
            ch = fabric.q(f"SELECT TOP 1 version FROM {fabric.table('cfc_champion')} ORDER BY created DESC")
            if ch:
                mr = fabric.q(f"SELECT TOP 1 wmape FROM {fabric.table('cfc_model_runs')} "
                              f"WHERE version = ? ORDER BY created DESC", (ch[0]["version"],))
                if mr and mr[0].get("wmape") is not None:
                    g["accuracy"] = _f((1 - float(mr[0]["wmape"])) * 100, 1)
        except Exception:
            pass
        # typical daily miss in units (mean abs error of P50)
        try:
            r = fabric.q(f"SELECT AVG(ABS(y - p50)) mae FROM {fabric.table('cfc_backtest_preds')}")
            if r and r[0].get("mae") is not None:
                g["units_off"] = _f(r[0]["mae"], 1)
        except Exception:
            pass
        # top feature drivers
        try:
            FI = fabric.table("cfc_feature_importance")
            rows = fabric.q(f"SELECT TOP 8 feature, gain FROM {FI} ORDER BY gain DESC")
            g["drivers"] = _dedupe([_humanize(r["feature"]) for r in rows if r.get("feature")])[:5]
        except Exception:
            pass
        if g["accuracy"] is None and g["units_off"] is None and not g["drivers"]:
            return None
        return g
    except Exception:
        return None


def _grounding_local() -> dict:
    """{accuracy, units_off, drivers[]} from the local backtest parquet (best-effort)."""
    g: dict = {"accuracy": None, "units_off": None, "drivers": []}
    if not BP.exists():
        return g
    try:
        c = duckdb.connect(":memory:")
        bp = BP.as_posix()
        o = c.execute(f"SELECT SUM(ABS(y-p50))/NULLIF(SUM(y),0) wmape, AVG(ABS(y-p50)) mae "
                      f"FROM read_parquet('{bp}')").fetchone()
        if o and o[0] is not None:
            g["accuracy"] = _f((1 - float(o[0])) * 100, 1)
        if o and o[1] is not None:
            g["units_off"] = _f(o[1], 1)
        c.close()
    except Exception:
        pass
    # Plain-language drivers (recent sales trend, day-of-week, holidays/festivals,
    # weather) — the real signal without exposing model internals.
    g["drivers"] = ["recent sales trend", "day of the week", "holidays and festivals", "weather"]
    return g


def _scope(req: ExplainReq) -> str:
    bits = []
    if req.branch:
        bits.append(f"outlet {req.branch}")
    if req.product:
        bits.append(f"product {req.product}")
    if req.date:
        bits.append(f"for {req.date}")
    return " · ".join(bits) if bits else "this outlet/product"


def _template(req: ExplainReq, g: dict) -> str:
    """Deterministic plain-language fallback built from the grounding numbers."""
    scope = _scope(req)
    parts = [f"The forecast for {scope} is based mainly on how it has been selling recently."]
    if g.get("drivers"):
        drv = g["drivers"][:3]
        if len(drv) == 1:
            parts.append(f"The biggest thing shaping it is {drv[0]}.")
        else:
            parts.append("The biggest things shaping it are " + ", ".join(drv[:-1]) + f" and {drv[-1]}.")
    if g.get("units_off") is not None:
        parts.append(f"On a typical day the forecast is off by only about {g['units_off']} units.")
    if g.get("accuracy") is not None:
        parts.append(f"Overall it has been right about {g['accuracy']}% of the time, so we are fairly confident in it.")
    else:
        parts.append("We track how close it stays over time to keep confidence high.")
    return " ".join(parts)


@router.post("")
def explain(req: ExplainReq):
    fab = _grounding_fabric()
    grounded = fab is not None
    g = fab or _grounding_local()

    scope = _scope(req)
    facts = []
    if g.get("accuracy") is not None:
        facts.append(f"- Overall accuracy: about {g['accuracy']}%")
    if g.get("units_off") is not None:
        facts.append(f"- Typical daily miss: about {g['units_off']} units")
    if g.get("drivers"):
        facts.append("- Main drivers (most to least important): " + ", ".join(g["drivers"][:5]))
    if req.context:
        for k, v in req.context.items():
            facts.append(f"- {k}: {v}")
    facts_block = "\n".join(facts) if facts else "- (no extra numbers available)"

    system = (
        "You explain a bakery demand forecast to a store operator in plain, everyday words. "
        "No jargon, no model or metric names (never say WMAPE, LightGBM, quantile, P50, etc). "
        "Explain in simple words why the forecast for this outlet/product is what it is, what "
        "drives it, and how confident we are. Keep it to 3-4 short sentences."
    )
    user = (
        f"Explain the forecast for {scope}. Use only these facts:\n{facts_block}\n\n"
        "Write 3-4 short, friendly sentences."
    )

    text = llm.explain(system, user, max_tokens=500)
    if text:
        return {"ok": True, "text": text, "model_used": llm.explain_model(),
                "grounded": grounded}
    return {"ok": True, "text": _template(req, g), "model_used": "template",
            "grounded": grounded}
