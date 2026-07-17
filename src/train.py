"""
Phase 5 — LightGBM quantile model for smooth/erratic series (LightGBM universe).
Trains P50 (point) + P85, P95 (safety-stock quantiles).
Time split: train < 2026-04-01, test = 2026-04..06 (same window as baselines for fair compare).
Saves models/ + writes reports/model_lgbm.md.
"""
import pathlib, json, argparse, os
import numpy as np, pandas as pd
import lightgbm as lgb

# Train-window split is parametrizable (default preserves original behaviour).
# CLI: python3 src/train.py --cutoff 2026-04-01   |  env: CFC_TRAIN_CUTOFF
_ap = argparse.ArgumentParser()
_ap.add_argument("--cutoff", default=os.getenv("CFC_TRAIN_CUTOFF", "2026-04-01"))
_args, _ = _ap.parse_known_args()

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = ROOT/"models"; MODELS.mkdir(exist_ok=True)
df = pd.read_parquet(ROOT/"data"/"features"/"train.parquet")

# Memory-lean mode (CFC_TRAIN_LEAN=1): bound rows + lighter trees so in-container training
# does not OOM. Heavy full-fidelity training belongs on Fabric. Default OFF (full behaviour).
LEAN = os.getenv("CFC_TRAIN_LEAN", "0") == "1"
if LEAN:
    max_rows = int(os.getenv("CFC_MAX_ROWS", "1500000"))
    if len(df) > max_rows:
        df = df.sort_values("date").tail(max_rows).reset_index(drop=True)
        print(f"[lean] capped to most-recent {len(df):,} rows (CFC_MAX_ROWS={max_rows})")

# feature set: precomputed feats + BranchId/ProductId as categoricals (high-signal)
base_feats = (ROOT/"data"/"features"/"feature_list.txt").read_text().split("\n")
df["BranchId"] = df.BranchId.astype(int)
df["ProductId"] = df.ProductId.astype(int)
CAT = ["BranchId","ProductId","dow","month","is_weekend","is_public_holiday","is_festival",
       "is_thingyan","promo_active","city","CatLvl2_Name","CatLvl3_Name","ChannelId",
       "Segment","branch_city","is_rainy","is_heavy_rain","is_hot"]
FEATS = base_feats + ["BranchId","ProductId"]
FEATS = [f for f in dict.fromkeys(FEATS)]           # dedupe, keep order
CATS = [c for c in CAT if c in FEATS]

SPLIT = pd.Timestamp(_args.cutoff)
tr = df[df.date < SPLIT]
te = df[df.date >= SPLIT]
print(f"train {len(tr):,} rows (<{SPLIT.date()}) | test {len(te):,} rows")

Xtr, ytr = tr[FEATS], tr["y"]
Xte, yte = te[FEATS], te["y"]
for c in CATS:
    Xtr[c] = Xtr[c].astype("category"); Xte[c] = Xte[c].astype("category")

def wmape(y, yh): return (y-yh).abs().sum()/max(y.abs().sum(),1e-9)

PARAMS = dict(objective="quantile", n_estimators=600, learning_rate=0.05,
              num_leaves=255, min_child_samples=100, subsample=0.8,
              colsample_bytree=0.8, n_jobs=-1, verbosity=-1)
if LEAN:
    # smaller trees + row-wise histogram + fewer bins → much lower peak RAM
    PARAMS.update(n_estimators=400, num_leaves=63, max_bin=127, force_row_wise=True)
    print("[lean] LightGBM params: 400 trees / 63 leaves / max_bin 127 / force_row_wise")

models = {}
preds = {}
for q, name in [(0.5,"p50"),(0.85,"p85"),(0.95,"p95")]:
    m = lgb.LGBMRegressor(alpha=q, **PARAMS)
    m.fit(Xtr, ytr, categorical_feature=CATS)
    models[name] = m
    p = np.clip(m.predict(Xte), 0, None)
    preds[name] = p
    m.booster_.save_model(str(MODELS/f"lgbm_{name}.txt"))
    print(f"trained {name} (q={q})")

te = te.assign(p50=preds["p50"], p85=preds["p85"], p95=preds["p95"])

# ABC labels
pv = df.groupby("ProductId").y.sum(); cum = pv.sort_values(ascending=False).cumsum()/pv.sum()
abc = pd.cut(cum,[0,.8,.95,1.001],labels=["A","B","C"]).to_dict()
te["abc"] = te.ProductId.map(abc)

BASE_FLOOR = 0.401; BASE_A = 0.349
L = ["# CFC Bakery — LightGBM Quantile Model (Phase 5)\n",
     f"Train < {SPLIT.date()} ({len(tr):,} rows), test 2026-04..06 ({len(te):,} rows).",
     f"Features: {len(FEATS)} ({len(CATS)} categorical incl BranchId/ProductId).\n",
     "## P50 accuracy vs baseline floor\n",
     "| Segment | LGBM WMAPE | Baseline | Improvement |",
     "|---|---|---|---|"]
ov = wmape(te.y, te.p50)
L.append(f"| Overall | {ov:.3f} | {BASE_FLOOR:.3f} | {(1-ov/BASE_FLOOR)*100:+.0f}% |")
for cls in ["A","B","C"]:
    s = te[te.abc==cls]; w = wmape(s.y, s.p50)
    bl = BASE_A if cls=="A" else (0.534 if cls=="B" else 0.733)
    L.append(f"| Class {cls} | {w:.3f} | {bl:.3f} | {(1-w/bl)*100:+.0f}% |")

# quantile coverage (calibration)
cov85 = (te.y <= te.p85).mean(); cov95 = (te.y <= te.p95).mean()
L.append("\n## Quantile calibration (coverage)\n")
L.append(f"- P85 coverage: {cov85*100:.1f}% (target ~85%)")
L.append(f"- P95 coverage: {cov95*100:.1f}% (target ~95%)")
L.append(f"- P50 bias: {(te.p50-te.y).mean():+.2f}\n")

# feature importance (P50)
imp = pd.Series(models["p50"].feature_importances_, index=FEATS).sort_values(ascending=False)
L.append("## Top 15 features (P50, gain)\n")
for f,v in imp.head(15).items(): L.append(f"- {f}: {int(v)}")

verdict = "BEATS" if ov < BASE_FLOOR else "does NOT beat"
L.append(f"\n## Verdict\nLightGBM P50 **{verdict}** baseline floor "
         f"({ov:.3f} vs {BASE_FLOOR:.3f}). Target ≤0.321.")
(ROOT/"reports"/"model_lgbm.md").write_text("\n".join(L))
print("\n".join(L))
