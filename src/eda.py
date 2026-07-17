"""
Phase 2 — EDA & demand profiling for CFC bakery.
Reads data/raw/*.parquet (+ external CSVs), writes reports/demand_profile.md + reports/figs/*.png.
Local only, no DB.
"""
import pathlib, warnings
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
FIG = ROOT / "reports" / "figs"; FIG.mkdir(parents=True, exist_ok=True)
EXT = ROOT / "data" / "external"

ACCENT = "#c8531b"; ACC2 = "#e8a13c"
def style(ax):
    ax.spines[["top","right"]].set_visible(False); ax.grid(axis="y", alpha=.25)

# ---- load ----
d = pd.read_parquet(RAW/"demand_panel.parquet")
d["date"] = pd.to_datetime(d.DayKey, format="%Y%m%d")
d["dow"] = d.date.dt.day_name()
d["ym"] = d.date.dt.to_period("M").astype(str)
br = pd.read_parquet(RAW/"dim_branch.parquet")
pr = pd.read_parquet(RAW/"dim_product.parquet")
ch = pd.read_parquet(RAW/"dim_channel.parquet")[["ChannelId","ChannelName"]]

d = d.merge(br[["BranchId","BranchName","ChannelId","Segment"]], on="BranchId", how="left")
d = d.merge(ch, on="ChannelId", how="left")
d = d.merge(pr[["ProductId","ProductName","CatLvl1_Name","CatLvl2_Name","ListPrice"]], on="ProductId", how="left")

L = []
def w(s=""): L.append(s)

w("# CFC Bakery — Demand Profile (Phase 2 EDA)\n")
w(f"Generated from `demand_panel.parquet` ({len(d):,} rows), 2023-01-01 → 2026-06-23.\n")

# ---- 1 overall ----
w("## 1. Overall scale")
w(f"- Net units sold (all time): **{d.net_units.sum():,.0f}**")
w(f"- Revenue (all time): **{d.amount.sum():,.0f} Ks**")
w(f"- Active branches: **{d.BranchId.nunique()}** | active products: **{d.ProductId.nunique()}** | days: **{d.date.nunique()}**")
w(f"- Avg lines/day: {len(d)/d.date.nunique():,.0f}\n")

# ---- 2 monthly trend ----
mth = d.groupby("ym").agg(units=("net_units","sum"), amount=("amount","sum")).reset_index()
mth = mth[mth.ym>="2023-01"]
fig,ax=plt.subplots(figsize=(11,3.2)); ax.bar(mth.ym, mth.units, color=ACCENT)
ax.set_xticks(mth.ym[::3]); plt.xticks(rotation=45,ha="right",fontsize=7); style(ax)
ax.set_title("Monthly net units"); plt.tight_layout(); plt.savefig(FIG/"monthly_units.png",dpi=110); plt.close()
yr = d.assign(yr=d.date.dt.year).groupby("yr").net_units.sum()
w("## 2. Trend over time")
w("![monthly](figs/monthly_units.png)\n")
w("Net units by year:")
for y,v in yr.items(): w(f"- {y}: {v:,.0f}")
g = (yr.get(2025,0)/yr.get(2023,1)-1)*100
w(f"\n2023→2025 growth: **{g:+.0f}%**. (2026 partial → June.)\n")

# ---- 3 day of week ----
dow_order=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
dow = d.groupby("dow").net_units.sum().reindex(dow_order)
dowm = (dow/ d.groupby("dow").date.nunique().reindex(dow_order))  # avg per day
fig,ax=plt.subplots(figsize=(7,3)); ax.bar(dow_order, dowm.values, color=ACC2)
plt.xticks(rotation=30,ha="right",fontsize=8); style(ax); ax.set_title("Avg net units by day-of-week")
plt.tight_layout(); plt.savefig(FIG/"dow.png",dpi=110); plt.close()
w("## 3. Day-of-week pattern")
w("![dow](figs/dow.png)\n")
peak=dowm.idxmax(); low=dowm.idxmin()
w(f"- Peak day: **{peak}** ({dowm.max():,.0f}/day) | weakest: **{low}** ({dowm.min():,.0f}/day)")
w(f"- Peak/trough ratio: **{dowm.max()/dowm.min():.2f}×** → day-of-week is a strong driver.\n")

# ---- 4 channel / segment ----
w("## 4. Channel & segment mix")
chg = d.groupby("ChannelName").agg(units=("net_units","sum"),amount=("amount","sum")).sort_values("units",ascending=False)
w("By channel:")
for c,r in chg.iterrows(): w(f"- {c}: {r.units:,.0f} units, {r.amount:,.0f} Ks ({r.units/d.net_units.sum()*100:.1f}%)")
w("")

# ---- 5 category ----
w("## 5. Product category (CatLvl1)")
cat = d.groupby("CatLvl1_Name").agg(units=("net_units","sum"),skus=("ProductId","nunique")).sort_values("units",ascending=False)
for c,r in cat.head(8).iterrows(): w(f"- {c}: {r.units:,.0f} units, {r.skus} SKUs")
w("")

# ---- 6 top branches / products ----
w("## 6. Concentration")
tb = d.groupby("BranchName").net_units.sum().sort_values(ascending=False)
w("Top 10 branches by units:")
for n,v in tb.head(10).items(): w(f"- {n}: {v:,.0f}")
tot=tb.sum(); top10share=tb.head(10).sum()/tot*100
w(f"\nTop 10 branches = **{top10share:.0f}%** of units. Top 20 = {tb.head(20).sum()/tot*100:.0f}%.\n")
tp = d.groupby("ProductName").net_units.sum().sort_values(ascending=False)
w("Top 10 products by units:")
for n,v in tp.head(10).items(): w(f"- {n}: {v:,.0f}")
w("")

# ---- 7 intermittency classification (per branch-SKU series) ----
w("## 7. Demand pattern classification (per branch×SKU series)")
# build per-series stats over each series' active span
d2 = d[["BranchId","ProductId","date","net_units"]].copy()
span = d2.groupby(["BranchId","ProductId"]).date.agg(["min","max"])
span["days_span"] = (span["max"]-span["min"]).dt.days+1
agg = d2.groupby(["BranchId","ProductId"]).agg(
    nz_days=("net_units", lambda s:(s>0).sum()),
    mean_nz=("net_units", lambda s: s[s>0].mean() if (s>0).any() else 0),
    std_nz =("net_units", lambda s: s[s>0].std() if (s>0).sum()>1 else 0),
    total=("net_units","sum"))
agg = agg.join(span["days_span"])
agg["adi"] = agg.days_span/agg.nz_days.replace(0,np.nan)       # avg interval between demands
agg["cv2"] = (agg.std_nz/agg.mean_nz.replace(0,np.nan))**2     # squared CV of nonzero demand
def cls(r):
    if pd.isna(r.adi): return "dead"
    if r.adi<1.32 and r.cv2<0.49: return "smooth"
    if r.adi>=1.32 and r.cv2<0.49: return "intermittent"
    if r.adi<1.32 and r.cv2>=0.49: return "erratic"
    return "lumpy"
agg["pattern"]=agg.apply(cls,axis=1)
pc = agg.pattern.value_counts()
share = agg.groupby("pattern").total.sum()/agg.total.sum()*100
w(f"Total active series (branch×SKU): **{len(agg):,}**")
w("\n| Pattern | Series | % series | % of volume |")
w("|---|---|---|---|")
for p in ["smooth","erratic","intermittent","lumpy","dead"]:
    if p in pc.index:
        w(f"| {p} | {pc[p]:,} | {pc[p]/len(agg)*100:.0f}% | {share.get(p,0):.0f}% |")
w("\n→ **smooth/erratic** = forecast with LightGBM. **intermittent/lumpy** = Croston/SBA. (Syntetos-Boylan-Croston cuts.)\n")

# ---- 8 ABC/XYZ ----
w("## 8. ABC / XYZ (product-level)")
psum = d.groupby("ProductId").net_units.sum().sort_values(ascending=False)
cum = psum.cumsum()/psum.sum()
abc = pd.cut(cum,[0,.8,.95,1.001],labels=["A","B","C"])
# variability per product (monthly CV)
pm = d.groupby(["ProductId","ym"]).net_units.sum().reset_index()
cv = pm.groupby("ProductId").net_units.agg(lambda s: s.std()/s.mean() if s.mean() else np.nan)
xyz = pd.cut(cv,[0,.5,1.0,np.inf],labels=["X","Y","Z"])
abcn = abc.value_counts()
w("ABC (by cumulative volume):")
for k in ["A","B","C"]:
    if k in abcn.index: w(f"- {k}: {abcn[k]} products ({abcn[k]/len(psum)*100:.0f}%)")
w(f"\nClass A products ({abcn.get('A',0)}) drive 80% of volume → focus model effort here.")
w(f"XYZ stability (monthly CV): X(stable)={(xyz=='X').sum()}, Y={ (xyz=='Y').sum()}, Z(volatile)={(xyz=='Z').sum()}.\n")

# ---- 9 festival effect ----
try:
    hol = pd.read_csv(EXT/"myanmar_holidays.csv")
    hol["date"]=pd.to_datetime(hol.date)
    daily = d.groupby("date").net_units.sum().reset_index()
    daily["is_hol"]=daily.date.isin(hol[hol.is_public_holiday==1].date)
    # thingyan window
    thg = hol[hol.multi_day_event.astype(str).str.contains("Thingyan",na=False)].date
    daily["thingyan"]=daily.date.isin(thg)
    base=daily[~daily.is_hol & ~daily.thingyan].net_units.mean()
    holm=daily[daily.is_hol].net_units.mean(); thm=daily[daily.thingyan].net_units.mean()
    w("## 9. Festival / holiday effect")
    w(f"- Normal day avg: {base:,.0f} units")
    w(f"- Public holiday avg: {holm:,.0f} ({holm/base-1:+.0%} vs normal)")
    w(f"- Thingyan window avg: {thm:,.0f} ({thm/base-1:+.0%} vs normal)")
    w("→ Festivals materially shift demand → calendar features essential.\n")
except Exception as e:
    w(f"## 9. Festival effect\n(skip: {e})\n")

# ---- 10 zero-inflation / new SKUs ----
w("## 10. Sparsity & lifecycle")
w(f"- Series classed 'dead' (no positive sales): {pc.get('dead',0):,}")
w(f"- Median active span per series: {agg.days_span.median():.0f} days")
w(f"- Series active <90 days (new/short-lived): {(agg.days_span<90).sum():,}")
w("\n→ Cold-start handling needed for new branch/SKU; backfill zeros on calendar for active series.\n")

w("## Modeling implications")
w("- Global LightGBM quantile on smooth/erratic A/B series (bulk of volume).")
w("- Croston/SBA for intermittent/lumpy long tail.")
w("- Calendar (dow + festivals) + weather + promo features mandatory.")
w("- Focus accuracy on Class-A; tolerate coarser tail.")
w("- Complete daily calendar per active series (fill zeros) before features.\n")

(ROOT/"reports"/"demand_profile.md").write_text("\n".join(L))
print("wrote reports/demand_profile.md +", len(list(FIG.glob('*.png'))), "figs")
print("\n".join(L[:60]))
