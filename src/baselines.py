"""
Phase 4 — Baselines. Establish the WMAPE floor the ML model must beat.
Uses precomputed leak-safe lag/rolling cols in data/features/train.parquet.
Backtest: rolling-origin, 3 monthly folds (last 3 months as successive test windows).
Writes reports/baselines.md.
"""
import pathlib
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
df = pd.read_parquet(ROOT/"data"/"features"/"train.parquet",
                     columns=["BranchId","ProductId","date","y","lag_1","lag_7",
                              "rmean_7","rmean_28","dow_mean_28"])
df = df.sort_values("date")

# ABC label (product volume) for segmented scoring
pv = df.groupby("ProductId").y.sum().sort_values(ascending=False)
cum = pv.cumsum()/pv.sum()
abc = pd.cut(cum,[0,.8,.95,1.001],labels=["A","B","C"]).to_dict()
df["abc"] = df.ProductId.map(abc)

# baseline predictions (all already leak-safe)
BASE = {
    "naive_lag1 (yesterday)":      "lag_1",
    "seasonal_naive_7 (same wkday)":"lag_7",
    "moving_avg_7":                "rmean_7",
    "moving_avg_28":               "rmean_28",
    "dow_mean_28 (wkday avg)":     "dow_mean_28",
}

def wmape(y, yh):
    m = y.notna() & yh.notna()
    return (y[m]-yh[m]).abs().sum() / max(y[m].abs().sum(), 1e-9)
def mae(y, yh):
    m = y.notna() & yh.notna(); return (y[m]-yh[m]).abs().mean()
def bias(y, yh):
    m = y.notna() & yh.notna(); return (yh[m]-y[m]).mean()

# rolling-origin: last 3 calendar months as 3 test folds
months = sorted(df.date.dt.to_period("M").astype(str).unique())
test_months = months[-3:]
print("test folds (months):", test_months)

L = ["# CFC Bakery — Baseline Floor (Phase 4)\n",
     f"Rolling-origin backtest, 3 monthly folds: {', '.join(test_months)}.",
     "Metric = WMAPE (lower better). These are the floors the ML model must beat.\n"]

rows = []
for name, col in BASE.items():
    ws, maes, biases = [], [], []
    for tm in test_months:
        t = df[df.date.dt.to_period("M").astype(str) == tm]
        ws.append(wmape(t.y, t[col])); maes.append(mae(t.y, t[col])); biases.append(bias(t.y, t[col]))
    rows.append((name, np.mean(ws), np.mean(maes), np.mean(biases)))

rows.sort(key=lambda r: r[1])
L.append("## Overall (all products)\n")
L.append("| Baseline | WMAPE | MAE | Bias |")
L.append("|---|---|---|---|")
for n,w,m,b in rows:
    L.append(f"| {n} | {w:.3f} | {m:.2f} | {b:+.2f} |")
best = rows[0]
L.append(f"\n**Best baseline: {best[0]} — WMAPE {best[1]:.3f}.** ML target: beat this by ≥20% (≤{best[1]*0.8:.3f}).\n")

# segmented by ABC for the best baseline col
bestcol = BASE[best[0]]
L.append(f"## Best baseline ({best[0]}) by ABC class\n")
L.append("| Class | WMAPE | share of volume |")
L.append("|---|---|---|")
tot = df.y.sum()
for cls in ["A","B","C"]:
    sub = df[(df.abc==cls) & (df.date.dt.to_period("M").astype(str).isin(test_months))]
    L.append(f"| {cls} | {wmape(sub.y, sub[bestcol]):.3f} | {df[df.abc==cls].y.sum()/tot*100:.0f}% |")
L.append("\n→ Class-A WMAPE is the number that matters most (80% of volume).\n")

# all baselines x class table
L.append("## All baselines × class (WMAPE)\n")
L.append("| Baseline | A | B | C |")
L.append("|---|---|---|---|")
for name,col in BASE.items():
    cells=[]
    for cls in ["A","B","C"]:
        sub = df[(df.abc==cls) & (df.date.dt.to_period("M").astype(str).isin(test_months))]
        cells.append(f"{wmape(sub.y, sub[col]):.3f}")
    L.append(f"| {name} | {cells[0]} | {cells[1]} | {cells[2]} |")

(ROOT/"reports"/"baselines.md").write_text("\n".join(L))
print("\n".join(L))
