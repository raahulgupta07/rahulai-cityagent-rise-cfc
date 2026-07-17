"""
Phase 7 — Order quantity (newsvendor) + warehouse picklist.

Turns forecast distribution (P50/P85/P95 from backtest) into an actual order number per
(branch, product, day), via per-product critical ratio, then rolls up to a warehouse picklist.

Newsvendor:
    CR = Cu / (Cu + Co)
    Cu = price * GM                       (lost margin if we under-order / stockout)
    Co = (price*(1-GM) - salvage) * spoil (loss per unsold unit; spoil=1 for same-day bakery)
    order_qty = demand quantile at CR     (interpolated from P50/P85/P95)

ECON INPUTS (data/product_econ.csv) — auto-stubbed with DEMO defaults (GM 35%, shelf-life 1 day,
no salvage). EDIT THIS FILE with real margin + shelf-life for production numbers.

CLI:
    python3 src/order_qty.py build              -> order_plan.parquet + reports/order_policy.md
    python3 src/order_qty.py picklist --date YYYY-MM-DD   -> data/predictions/picklist_<date>.csv
    python3 src/order_qty.py sweep              -> reports/service_tradeoff.md
"""
import sys, argparse, pathlib
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRED = ROOT/"data"/"predictions"
REP  = ROOT/"reports"
ECON_CSV = ROOT/"data"/"product_econ.csv"

# ---------- DEMO econ defaults (EDIT product_econ.csv for real values) ----------
DEFAULT_GM       = 0.35   # gross margin
DEFAULT_SHELF    = 1      # shelf life (days) — 1 = same-day perishable bakery
DEFAULT_SALVAGE  = 0.0    # salvage fraction of cost recovered on unsold (markdown/staff)

def load_preds():
    p = PRED/"backtest_preds.parquet"
    if not p.exists(): sys.exit("run src/backtest.py first (need backtest_preds.parquet)")
    return pd.read_parquet(p)

def econ_table(bt):
    """Per-product economics. Stub from ListPrice if csv missing; else load real csv."""
    prod = bt.groupby("ProductId").ListPrice.median().reset_index()
    if ECON_CSV.exists():
        e = pd.read_csv(ECON_CSV)
        e = prod.merge(e.drop(columns=[c for c in ["ListPrice"] if c in e], errors="ignore"),
                       on="ProductId", how="left")
    else:
        e = prod.copy()
    for col, dflt in [("gm",DEFAULT_GM),("shelf_life_days",DEFAULT_SHELF),("salvage_frac",DEFAULT_SALVAGE)]:
        if col not in e: e[col] = dflt
        e[col] = e[col].fillna(dflt)
    e["price"] = e.ListPrice.clip(lower=1)
    # spoilage fraction: same-day perishable=1; longer shelf-life dilutes per-day spoil risk
    e["spoil_frac"] = (1.0/e.shelf_life_days).clip(0, 1)
    e["Cu"] = e.price * e.gm
    e["Co"] = ((e.price*(1-e.gm)) - (e.price*(1-e.gm)*e.salvage_frac)) * e.spoil_frac
    e["Co"] = e.Co.clip(lower=0.01)
    e["CR"] = (e.Cu/(e.Cu+e.Co)).clip(0.01,0.99)
    if not ECON_CSV.exists():
        e[["ProductId","ListPrice","gm","shelf_life_days","salvage_frac"]].to_csv(ECON_CSV,index=False)
        print(f"stubbed DEMO econ -> {ECON_CSV} (edit with real margin+shelf-life)")
    return e[["ProductId","price","gm","shelf_life_days","CR","Cu","Co"]]

def q_at(cr, p50, p85, p95):
    """Piecewise-linear demand quantile at critical ratio cr, from P50/P85/P95 anchors."""
    cr=np.asarray(cr); p50=np.asarray(p50); p85=np.asarray(p85); p95=np.asarray(p95)
    s1 = p50*(cr/0.5)                              # cr<0.5  : 0 -> p50
    s2 = p50 + (cr-0.5)/0.35*(p85-p50)            # .5-.85
    s3 = p85 + (cr-0.85)/0.10*(p95-p85)           # .85-.95
    s4 = p95                                       # >=.95 cap
    out = np.select([cr<0.5, cr<0.85, cr<0.95],[s1,s2,s3], default=s4)
    return np.clip(np.round(out),0,None)

def sim(d, o, Cu, Co):
    o=np.clip(np.round(o),0,None)
    under=np.maximum(d-o,0); over=np.maximum(o-d,0)
    cost=(Cu*under+Co*over).sum()
    return dict(cost=cost, stockout_pct=(d>o).mean()*100,
                waste_pct=over.sum()/max(o.sum(),1)*100,
                fill=np.minimum(o,d).sum()/max(d.sum(),1)*100, avg_order=o.mean())

def attach(bt):
    e = econ_table(bt)
    bt = bt.merge(e, on="ProductId", how="left")
    bt["order_qty"] = q_at(bt.CR.values, bt.p50.values, bt.p85.values, bt.p95.values)
    return bt, e

# ---------- build ----------
def cmd_build():
    bt = load_preds()
    bt, e = attach(bt)
    keep=["date","BranchId","ProductId","abc","p50","p85","p95","CR","order_qty","y","price"]
    bt[keep].to_parquet(PRED/"order_plan.parquet")
    d=bt.y.values
    pol = {"newsvendor (per-product CR)":bt.order_qty.values,
           "flat P50":bt.p50.values,"flat P85":bt.p85.values,
           "baseline mov_avg_7":bt.rmean_7.values}
    base=sim(d,bt.rmean_7.values,bt.Cu.values,bt.Co.values)["cost"]
    L=["# CFC Order Policy — Newsvendor (Phase 7)\n",
       f"DEMO econ: GM {DEFAULT_GM:.0%}, shelf-life {DEFAULT_SHELF}d, salvage {DEFAULT_SALVAGE:.0%}. "
       f"Edit `data/product_econ.csv` for real values.",
       f"Order plan: {len(bt):,} (branch×product×day) rows over backtest folds.\n",
       "## Critical ratio by ABC class\n| Class | products | avg CR | median order/day | vol share |",
       "|---|---|---|---|---|"]
    tot=bt.y.sum()
    for cls in ["A","B","C"]:
        s=bt[bt.abc==cls]
        L.append(f"| {cls} | {s.ProductId.nunique()} | {s.CR.mean():.2f} | {s.order_qty.median():.1f} | {s.y.sum()/tot*100:.0f}% |")
    L.append("\n## Order policy vs realised demand (cost, ₭)\n")
    L.append("| Policy | cost ₭ | stockout% | waste% | fill% | avg order |")
    L.append("|---|---|---|---|---|---|")
    res={}
    for nm,o in pol.items():
        r=sim(d,o,bt.Cu.values,bt.Co.values); res[nm]=r
        L.append(f"| {nm} | {r['cost']:,.0f} | {r['stockout_pct']:.1f} | {r['waste_pct']:.1f} | {r['fill']:.1f} | {r['avg_order']:.2f} |")
    best=min(res.items(),key=lambda kv:kv[1]['cost'])
    nv=res["newsvendor (per-product CR)"]
    L.append(f"\n**Lowest cost: {best[0]} — ₭{best[1]['cost']:,.0f}.** "
             f"Newsvendor vs baseline ₭{base:,.0f} = {(1-nv['cost']/base)*100:+.0f}%.")
    L.append("At flat GM 35% same-day spoilage, CR<0.5 → newsvendor≈lean order, close to P50 "
             "(matches Phase 6). Real per-product margin+shelf-life will spread CR → high-margin/"
             "long-shelf SKUs get more safety stock.\n")
    (REP/"order_policy.md").write_text("\n".join(L))
    print("\n".join(L)); print(f"\nwrote {PRED/'order_plan.parquet'} + reports/order_policy.md")

# ---------- picklist ----------
def cmd_picklist(date):
    op = pd.read_parquet(PRED/"order_plan.parquet")
    op["date"]=pd.to_datetime(op.date)
    day = op[op.date==pd.Timestamp(date)]
    if day.empty:
        avail = sorted(op.date.dt.strftime("%Y-%m-%d").unique())
        sys.exit(f"no rows for {date}. available: {avail[0]}..{avail[-1]}")
    # product names
    dp = pd.read_parquet(ROOT/"data"/"raw"/"dim_product.parquet")[["ProductId","ProductName","ProductCode"]]
    pl = (day.groupby("ProductId")
            .agg(order_units=("order_qty","sum"), n_outlets=("BranchId","nunique"),
                 fcst_p50=("p50","sum"), value_ks=("price","first"))
            .reset_index())
    pl["value_ks"]=pl.order_units*pl.value_ks
    pl=pl.merge(dp,on="ProductId",how="left").sort_values("order_units",ascending=False)
    pl=pl[["ProductId","ProductCode","ProductName","order_units","n_outlets","fcst_p50","value_ks"]]
    out=PRED/f"picklist_{date}.csv"; pl.to_csv(out,index=False)
    print(f"WAREHOUSE PICKLIST {date} — {len(pl)} products, {pl.order_units.sum():,.0f} units, "
          f"₭{pl.value_ks.sum():,.0f}\n")
    print(pl.head(20).to_string(index=False))
    print(f"\nwrote {out}")

# ---------- sweep ----------
def cmd_sweep():
    bt = load_preds(); bt,e = attach(bt)
    d=bt.y.values
    L=["# CFC Service-Level vs Waste Tradeoff (Phase 7)\n",
       "Order = demand quantile at target service level. Pick the dial mgmt wants.\n",
       "| target service | order quantile | stockout% | waste% | fill% | cost ₭ |",
       "|---|---|---|---|---|---|"]
    for cr in [0.30,0.50,0.70,0.85,0.95]:
        o=q_at(np.full(len(bt),cr),bt.p50.values,bt.p85.values,bt.p95.values)
        r=sim(d,o,bt.Cu.values,bt.Co.values)
        L.append(f"| {cr:.0%} | ~P{int(cr*100)} | {r['stockout_pct']:.1f} | {r['waste_pct']:.1f} | {r['fill']:.1f} | {r['cost']:,.0f} |")
    L.append("\nHigher service → fewer stockouts but waste cost climbs. Cost-min sits where "
             "marginal margin saved = marginal spoilage. At GM35% same-day that's a low quantile.\n")
    (REP/"service_tradeoff.md").write_text("\n".join(L))
    print("\n".join(L)); print("\nwrote reports/service_tradeoff.md")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd")
    sub.add_parser("build"); sub.add_parser("sweep")
    pp=sub.add_parser("picklist"); pp.add_argument("--date",required=True)
    a=ap.parse_args()
    if a.cmd=="build": cmd_build()
    elif a.cmd=="picklist": cmd_picklist(a.date)
    elif a.cmd=="sweep": cmd_sweep()
    else: ap.print_help()
