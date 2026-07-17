"""
Phase 3 — Feature engineering for CFC bakery demand.

Builds a leakage-safe daily feature matrix for the LightGBM universe:
 - FG products, Class A+B (top ~95% of volume), active branches.
 - Complete daily calendar per (branch, product) over its active span (zeros filled).
 - Features: lags, rolling stats, calendar, holidays/festivals, weather, promo, product/branch attrs.

Output: data/features/train.parquet  (+ feature_list.txt)
Local only, no DB.
"""
import pathlib, warnings, re
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT/"data"/"raw"; EXT = ROOT/"data"/"external"
OUT = ROOT/"data"/"features"; OUT.mkdir(parents=True, exist_ok=True)

ABC_CUTOFF = 0.95   # keep products up to 95% cumulative volume (Class A+B)

# ---------- load core ----------
d = pd.read_parquet(RAW/"demand_panel.parquet")
d = d[d.DayKey >= "20230101"].copy()
d["date"] = pd.to_datetime(d.DayKey, format="%Y%m%d")

pr = pd.read_parquet(RAW/"dim_product.parquet")
br = pd.read_parquet(RAW/"dim_branch.parquet")

# FG only
fg = set(pr.loc[pr.CatLvl1_Name == "FG", "ProductId"])
d = d[d.ProductId.isin(fg)].copy()

# Class A+B products (cumulative volume)
psum = d.groupby("ProductId").net_units.sum().sort_values(ascending=False)
cum = psum.cumsum()/psum.sum()
keep_products = set(cum[cum <= ABC_CUTOFF].index) | {psum.index[0]}
d = d[d.ProductId.isin(keep_products)].copy()
print(f"universe: {d.ProductId.nunique()} products (A+B), {d.BranchId.nunique()} branches, {len(d):,} sale-rows")

# ---------- complete daily calendar per (branch,product) over active span ----------
d = d.sort_values(["BranchId","ProductId","date"])
spans = d.groupby(["BranchId","ProductId"]).date.agg(["min","max"]).reset_index()
gmax = d.date.max()
# cap span end at gmax; assume product stays in assortment to its last-seen + 30d or gmax
spans["end"] = spans["max"]
frames = []
# build per series calendar via merge on full grid (vectorized per series group)
base = d[["BranchId","ProductId","date","net_units","amount","discount","txns"]].copy()
def build_series(g):
    bId, pId = g.name
    s, e = g.date.min(), g.date.max()
    idx = pd.date_range(s, e, freq="D")
    out = g.set_index("date").reindex(idx)
    out["BranchId"] = bId; out["ProductId"] = pId
    out["net_units"] = out["net_units"].fillna(0.0)
    return out.reset_index().rename(columns={"index":"date"})
cal = base.groupby(["BranchId","ProductId"], group_keys=False).apply(build_series)
cal = cal[["BranchId","ProductId","date","net_units"]].reset_index(drop=True)
print(f"calendar-completed panel: {len(cal):,} rows (zeros filled)")

# ---------- target + lag/rolling (leak-safe: shift>=1) ----------
cal = cal.sort_values(["BranchId","ProductId","date"])
g = cal.groupby(["BranchId","ProductId"])["net_units"]
for L in (1,7,14,28):
    cal[f"lag_{L}"] = g.shift(L)
for W in (7,14,28):
    cal[f"rmean_{W}"] = g.shift(1).rolling(W).mean()
    cal[f"rstd_{W}"]  = g.shift(1).rolling(W).std()
cal["rmax_28"] = g.shift(1).rolling(28).max()
cal["dow_mean_28"] = (cal.groupby(["BranchId","ProductId", cal.date.dt.dayofweek])["net_units"]
                        .shift(1).rolling(4).mean())  # same-weekday recent avg

# ---------- calendar features ----------
cal["dow"] = cal.date.dt.dayofweek
cal["dom"] = cal.date.dt.day
cal["month"] = cal.date.dt.month
cal["weekofyear"] = cal.date.dt.isocalendar().week.astype(int)
cal["is_weekend"] = (cal.dow >= 5).astype(int)

# ---------- holidays / festivals ----------
hol = pd.read_csv(EXT/"myanmar_holidays.csv"); hol["date"] = pd.to_datetime(hol.date)
ph = set(hol.loc[hol.is_public_holiday == 1, "date"])
fest = set(hol.loc[hol.type == "festival", "date"])
thg = set(hol.loc[hol.multi_day_event.astype(str).str.contains("Thingyan", na=False), "date"])
cal["is_public_holiday"] = cal.date.isin(ph).astype(int)
cal["is_festival"] = cal.date.isin(fest).astype(int)
cal["is_thingyan"] = cal.date.isin(thg).astype(int)
# days to next public holiday
hdays = np.array(sorted(ph))
alld = np.array(sorted(cal.date.unique()))
nxt = {}
import bisect
hsorted = sorted(ph)
for dt in alld:
    i = bisect.bisect_left(hsorted, dt)
    nxt[dt] = (hsorted[i]-dt).days if i < len(hsorted) else 99
cal["days_to_holiday"] = cal.date.map(nxt).clip(upper=30)

# ---------- promo calendar (loyalty xlsx, network-level) ----------
try:
    promo_dates = set()
    for f in ["Loyalty Program current v3.xlsx","Loyalty Program current v4.xlsx"]:
        pf = pd.read_excel(ROOT/f)
        for _,r in pf.iterrows():
            sd, ed = pd.to_datetime(r["Start Date"],errors="coerce"), pd.to_datetime(r["End date"],errors="coerce")
            if pd.notna(sd) and pd.notna(ed):
                for dt in pd.date_range(sd.normalize(), ed.normalize()):
                    promo_dates.add(dt)
    cal["promo_active"] = cal.date.isin(promo_dates).astype(int)
except Exception as e:
    print("promo skip:", e); cal["promo_active"] = 0

# ---------- weather (branch -> city -> daily weather) ----------
wx = pd.read_csv(EXT/"weather_daily.csv"); wx["date"] = pd.to_datetime(wx.date)
cities = ["Mandalay","Naypyidaw","Bago","Pyay","Taunggyi","Yangon"]  # Yangon last = default
def city_of(addr):
    a = str(addr).lower()
    for c in cities:
        if c.lower() in a: return c
    return "Yangon"
br["city"] = br.Address.map(city_of)
b2c = br.set_index("BranchId").city.to_dict()
cal["city"] = cal.BranchId.map(b2c).fillna("Yangon")
wxk = wx[["date","city","rain_mm","is_rainy","is_heavy_rain","tmax_c","is_hot","humidity_pct"]]
cal = cal.merge(wxk, on=["date","city"], how="left")

# ---------- product & branch attributes ----------
pa = pr[["ProductId","ListPrice","CatLvl2_Name","CatLvl3_Name"]].copy()
cal = cal.merge(pa, on="ProductId", how="left")
ba = br[["BranchId","ChannelId","Segment","city"]].rename(columns={"city":"branch_city"})
cal = cal.merge(ba, on="BranchId", how="left")

# categorical encodings (keep as category codes for LightGBM)
for c in ["CatLvl2_Name","CatLvl3_Name","Segment","branch_city","city"]:
    cal[c] = cal[c].astype("category").cat.codes
cal["ChannelId"] = cal.ChannelId.fillna(-1).astype(int)

# target column
cal = cal.rename(columns={"net_units":"y"})

# drop warmup rows lacking the longest lag
cal = cal[cal["lag_28"].notna()].copy()

feat_cols = [c for c in cal.columns if c not in ("BranchId","ProductId","date","y","amount","discount","txns")]
out = OUT/"train.parquet"
cal.to_parquet(out, index=False)
(OUT/"feature_list.txt").write_text("\n".join(feat_cols))

print(f"\nFEATURES: {len(feat_cols)} cols, {len(cal):,} rows -> {out} ({out.stat().st_size/1024/1024:.0f} MB)")
print("date range:", cal.date.min().date(), "..", cal.date.max().date())
print("y: mean=%.2f  nonzero=%.1f%%  max=%.0f" % (cal.y.mean(), (cal.y>0).mean()*100, cal.y.max()))
print("features:", ", ".join(feat_cols))
print("nulls in features:", int(cal[feat_cols].isna().sum().sum()))
