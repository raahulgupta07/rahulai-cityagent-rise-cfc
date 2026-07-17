"""
Phase 6 — Rolling-origin backtest + business simulation.
- Expanding-window walk-forward: 3 monthly test folds (2026-04, -05, -06).
  Train < fold start each time → LGBM P50/P85/P95 retrained per fold (no leak).
- Score LGBM vs baselines (moving_avg_7 floor, lag_1, seasonal_naive_7, dow_mean_28)
  on the SAME folds: WMAPE / MAE / bias / pinball / coverage, overall + by ABC.
- Business sim (newsvendor): order policies vs realised demand → stockout% / waste% /
  fill rate / ₭ cost. Compares baseline-point order vs LGBM P50/P85/P95 + newsvendor pick.
Writes reports/eval.md + data/predictions/backtest_preds.parquet.
"""
import pathlib
import numpy as np, pandas as pd
import lightgbm as lgb

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRED = ROOT/"data"/"predictions"; PRED.mkdir(parents=True, exist_ok=True)

base_feats = (ROOT/"data"/"features"/"feature_list.txt").read_text().strip().split("\n")
df = pd.read_parquet(ROOT/"data"/"features"/"train.parquet")
df["BranchId"] = df.BranchId.astype(int)
df["ProductId"] = df.ProductId.astype(int)

FEATS = list(dict.fromkeys(base_feats + ["BranchId","ProductId"]))
CAT = ["BranchId","ProductId","dow","month","is_weekend","is_public_holiday","is_festival",
       "is_thingyan","promo_active","city","CatLvl2_Name","CatLvl3_Name","ChannelId",
       "Segment","branch_city","is_rainy","is_heavy_rain","is_hot"]
CATS = [c for c in CAT if c in FEATS]

PARAMS = dict(objective="quantile", n_estimators=600, learning_rate=0.05,
              num_leaves=255, min_child_samples=100, subsample=0.8,
              colsample_bytree=0.8, n_jobs=-1, verbosity=-1)
QS = [(0.5,"p50"),(0.85,"p85"),(0.95,"p95")]

# ABC label (global product volume)
pv = df.groupby("ProductId").y.sum(); cum = pv.sort_values(ascending=False).cumsum()/pv.sum()
abc = pd.cut(cum,[0,.8,.95,1.001],labels=["A","B","C"]).to_dict()
df["abc"] = df.ProductId.map(abc)

mper = df.date.dt.to_period("M").astype(str)
FOLDS = ["2026-04","2026-05","2026-06"]

def wmape(y,yh):
    m=y.notna()&yh.notna(); return (y[m]-yh[m]).abs().sum()/max(y[m].abs().sum(),1e-9)
def mae(y,yh): m=y.notna()&yh.notna(); return (y[m]-yh[m]).abs().mean()
def bias(y,yh): m=y.notna()&yh.notna(); return (yh[m]-y[m]).mean()
def pinball(y,yh,q):
    e=y-yh; return np.mean(np.maximum(q*e,(q-1)*e))

all_preds=[]
for fold in FOLDS:
    fs = pd.Timestamp(fold+"-01")
    tr = df[df.date < fs]
    te = df[mper == fold].copy()
    Xtr,ytr = tr[FEATS].copy(), tr["y"]
    Xte = te[FEATS].copy()
    for c in CATS: Xtr[c]=Xtr[c].astype("category"); Xte[c]=Xte[c].astype("category")
    for q,name in QS:
        m = lgb.LGBMRegressor(alpha=q,**PARAMS); m.fit(Xtr,ytr,categorical_feature=CATS)
        te[name] = np.clip(m.predict(Xte),0,None)
    te["fold"]=fold
    all_preds.append(te)
    print(f"fold {fold}: train {len(tr):,} test {len(te):,} done")

bt = pd.concat(all_preds, ignore_index=True)
bt.to_parquet(PRED/"backtest_preds.parquet")

# ---------- accuracy table: LGBM vs baselines, pooled over folds ----------
MODELS = {"LGBM P50":"p50","moving_avg_7":"rmean_7","naive_lag1":"lag_1",
          "seasonal_naive_7":"lag_7","dow_mean_28":"dow_mean_28"}
L=["# CFC Bakery — Backtest & Business Sim (Phase 6)\n",
   f"Rolling-origin, 3 expanding folds: {', '.join(FOLDS)}. Retrained per fold.",
   f"Test rows pooled: {len(bt):,}.\n",
   "## Accuracy — point forecast (pooled, volume-weighted WMAPE)\n",
   "| Model | WMAPE | MAE | Bias |","|---|---|---|---|"]
for nm,col in MODELS.items():
    L.append(f"| {nm} | {wmape(bt.y,bt[col]):.3f} | {mae(bt.y,bt[col]):.2f} | {bias(bt.y,bt[col]):+.2f} |")
floor = wmape(bt.y, bt.rmean_7); lg = wmape(bt.y, bt.p50)
L.append(f"\n**LGBM P50 vs floor: {lg:.3f} vs {floor:.3f} "
         f"({(1-lg/floor)*100:+.0f}%).** Stretch target ≤0.321.\n")

# per-fold stability
L.append("## Per-fold WMAPE (LGBM P50 vs floor) — stability check\n")
L.append("| Fold | LGBM | floor | improv |")
L.append("|---|---|---|---|")
for f in FOLDS:
    s=bt[bt.fold==f]; a=wmape(s.y,s.p50); b=wmape(s.y,s.rmean_7)
    L.append(f"| {f} | {a:.3f} | {b:.3f} | {(1-a/b)*100:+.0f}% |")

# by ABC
L.append("\n## LGBM P50 by ABC class\n| Class | WMAPE | floor | improv | vol share |")
L.append("|---|---|---|---|---|")
tot=bt.y.sum()
for cls in ["A","B","C"]:
    s=bt[bt.abc==cls]; a=wmape(s.y,s.p50); b=wmape(s.y,s.rmean_7)
    L.append(f"| {cls} | {a:.3f} | {b:.3f} | {(1-a/b)*100:+.0f}% | {s.y.sum()/tot*100:.0f}% |")

# quantile quality
L.append("\n## Quantile calibration + pinball loss\n| Quantile | coverage | target | pinball |")
L.append("|---|---|---|---|")
for q,name in QS:
    cov=(bt.y<=bt[name]).mean()
    L.append(f"| {name.upper()} | {cov*100:.1f}% | {int(q*100)}% | {pinball(bt.y,bt[name],q):.3f} |")

# ---------- business sim (newsvendor) ----------
# Economics: per-unit margin Cu = price*GM ; spoilage Co = price*(1-GM) (perishable, full loss).
GM = 0.35
bt["price"] = bt["ListPrice"].fillna(bt["ListPrice"].median()).clip(lower=1)
bt["Cu"] = bt.price*GM; bt["Co"] = bt.price*(1-GM)
CR = GM  # critical ratio = Cu/(Cu+Co) = GM -> ~35th pctile target

def sim(order):
    d=bt.y.values; o=np.clip(np.round(order),0,None)
    under=np.maximum(d-o,0); over=np.maximum(o-d,0)
    cost=(bt.Cu.values*under + bt.Co.values*over)
    served=np.minimum(o,d)
    return dict(cost=cost.sum(),
                stockout_pct=(d>o).mean()*100,
                waste_pct=over.sum()/max(o.sum(),1)*100,
                fill=served.sum()/max(d.sum(),1)*100,
                avg_order=o.mean())

# newsvendor pick from available quantiles by critical ratio
# CR ~0.35 sits between P50(0.5) low side -> interpolate p50/p85 by CR; clamp to p50 if CR<=.5
def nv_order():
    # for CR<0.5 use a fraction below p50 toward 0; approximate with p50 scaled
    return bt.p50.values * (CR/0.5) if CR<0.5 else bt.p50.values
POL = {"baseline (moving_avg_7)":bt.rmean_7.values,
       "LGBM P50":bt.p50.values,
       "LGBM P85":bt.p85.values,
       "LGBM P95":bt.p95.values,
       f"LGBM newsvendor (CR={CR:.2f})":nv_order()}
L.append(f"\n## Business simulation — newsvendor (GM={GM:.0%}, full spoilage)\n")
L.append("Order placed per (branch,product,day); compared to realised demand on the backtest folds.")
L.append("Cost = lost margin on stockouts + spoilage on overstock.\n")
L.append("| Order policy | total cost (₭) | stockout% | waste% | fill% | avg order |")
L.append("|---|---|---|---|---|---|")
base_cost=None
res={}
for nm,o in POL.items():
    r=sim(o); res[nm]=r
    if "baseline" in nm: base_cost=r["cost"]
L.append("")
for nm in POL:
    r=res[nm]
    L.append(f"| {nm} | {r['cost']:,.0f} | {r['stockout_pct']:.1f} | {r['waste_pct']:.1f} | {r['fill']:.1f} | {r['avg_order']:.2f} |")
# best policy by cost
best=min(res.items(),key=lambda kv:kv[1]["cost"])
save=(base_cost-best[1]["cost"])/max(base_cost,1)*100
L.append(f"\n**Lowest-cost policy: {best[0]}** — ₭{best[1]['cost']:,.0f} "
         f"vs baseline ₭{base_cost:,.0f} → **{save:.0f}% cost cut** over {len(bt):,} order-days.")
L.append("Note: ₭ cost is on the backtest test window; scales with full network/year.\n")

(ROOT/"reports"/"eval.md").write_text("\n".join(L))
print("\n".join(L))
print("\nwrote reports/eval.md + data/predictions/backtest_preds.parquet")
