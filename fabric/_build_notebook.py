"""Builder → emits CFC_ML_Pipeline_Fabric.ipynb (valid nbformat v4 JSON, no deps).
Run: python3 fabric/_build_notebook.py

Additive lanes (do not break existing MODEs):
  * Daily accuracy: pred_vs_actual() scores any preds frame that carries realized `y` against the
    P50 forecast, writing cfc_pred_vs_actual (per dt/branch/product + abs_err) and cfc_daily_accuracy
    (per dt: accuracy=clip(1-WMAPE,0,1), wmape, units_off, n_rows). Called inside backtest() and
    predict(), so it fires in the backtest, predict, all and auto modes. No retraining/re-aggregation.
  * Demand uncensoring: predict() adds is_stockout (conservative censoring flag: zero-sales day while
    trailing-28d mean is clearly positive, OR sales pinned at the trailing-28d max two days running)
    and demand_est (un-censors stockout days toward the P85 demand proxy) to cfc_order_plan. Emitted by
    every predict-running mode (predict, all, auto)."""
import json, pathlib

HERE = pathlib.Path(__file__).resolve().parent

def md(src):   return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}
def code(src, tags=None):
    meta = {"tags": tags} if tags else {}
    return {"cell_type": "code", "execution_count": None, "metadata": meta, "outputs": [], "source": src.strip("\n").splitlines(keepends=True)}

cells = []

cells.append(md("""\
# CFC Demand Forecasting — Fabric ML Pipeline

Ports the local engine (`src/features.py · train.py · backtest.py · pipeline.py`) into **Microsoft Fabric**.
Runs **next to the data** (Lakehouse) — no local RAM ceiling, no ODBC egress. Tracks models in **MLflow**.

**Modes** (set in the parameters cell, or pass from a Data Pipeline):
- `all` — features → train → backtest → gate → predict (full experiment)
- `features` · `train` · `backtest` · `predict` — single stage

**Reads** (Lakehouse tables): `demand_panel`, `dim_product`, `dim_branch`, `myanmar_holidays`, `weather_daily`, `promo_calendar` (optional).
**Writes** (Lakehouse tables the app reads): `cfc_features`, `cfc_backtest_preds`, `cfc_order_plan` (+ `is_stockout`/`demand_est`), `cfc_model_runs`, `cfc_champion`, `cfc_pred_vs_actual`, `cfc_daily_accuracy`.
**MLflow**: experiment `CFC_Demand`, registered model `CFC_Demand_P50` with alias `champion`.

> Attach this notebook to your Lakehouse (Explorer → add Lakehouse) so `spark.read.table(name)` resolves.
"""))

# ---- deps cell (subprocess install, works headless AND interactive; avoids %pip session restart) ----
cells.append(md("## 0 · Install deps  \nFabric's Spark runtime has mlflow/pandas/pyarrow but **not lightgbm** — install it. Uses subprocess pip (not `%pip`) so it also works in a scheduled/headless Data Pipeline run."))
cells.append(code('''
import importlib, subprocess, sys
def _ensure(pkg, imp=None):
    try:
        importlib.import_module(imp or pkg)
    except ImportError:
        print(f"installing {pkg} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])
_ensure("lightgbm")
'''))

# ---- parameters cell ----
cells.append(md("## 1 · Parameters  \nTag = `parameters` so a Fabric Data Pipeline can override these."))
cells.append(code('''
# PARAMETERS  (Fabric injects overrides above this cell at runtime)
MODE          = "auto"         # DEFAULT for scheduled runs: predict daily + retrain ONLY on drift.
                               # all | features | train | backtest | predict | monitor | auto | tune | promote
CUTOFF        = "2026-04-01"    # train/backtest window split (train < CUTOFF)
PREDICT_DATE  = ""             # predict mode target date YYYY-MM-DD; "" = last date in panel
MIN_GAIN      = 0.01            # challenger must beat champion WMAPE by >=1% (rel) to promote
AUTO_PROMOTE  = False           # False = train registers a CHALLENGER; a human approves via MODE=promote
PROMOTE_VERSION = ""           # MODE=promote: the version to make champion (approval from the app)
EXPERIMENT    = "CFC_Demand"    # MLflow experiment name
MODEL_NAME    = "CFC_Demand_P50"  # MLflow registered model
ABC_CUTOFF    = 0.95            # keep products up to 95% cumulative volume (Class A+B)

# --- auto-loop (drift monitor + self-triggered retrain) ---
MONITOR_REF_DAYS = 30           # recent window = last N days vs the reference before it
PSI_WARN         = 0.20         # PSI > 0.20 = notable population shift (data drift)
WMAPE_WARN       = 0.10         # recent WMAPE > champion holdout * (1+10%) = accuracy drift -> RETRAIN
# --- Optuna finetune ---
TUNE_TRIALS      = 20           # MODE=tune: hyperparameter search trials
# --- demand uncensoring (predict lane): sales are censored by availability ---
STOCKOUT_MIN_MEAN = 1.0         # a zero-sales day counts as a likely stockout only if the trailing-28d
                                # mean exceeded this (conservative: avoids flagging genuinely dead SKUs)

# --- Fabric source tables (shortcut LK_CFC_Sales -> this Lakehouse; NOT moved) ---
T_SALES     = "CFC_Sales_Trans"   # RAW transactions (19.6M). Aggregated in-place below.
SALES_IS_RAW = True               # True -> GROUP BY to daily grain; False -> already daily
T_PRODUCT   = "Ref_ProductMaster" # ProductId, CatLvl1_Name (FG), CatLvl2/3_Name, ListPrice, Active
T_BRANCH    = "Ref_BranchMaster"  # BranchId, Address, ChannelId, Segment
SALES_START = "20230101"          # demand window start (DayKey varchar YYYYMMDD)
SCHEMA      = "dbo"               # schema-enabled Lakehouse -> tables live under dbo. "" = no schema.

# --- manual data (user-provided via the app -> OneLake Files/manual/*.csv) ---
MANUAL_DIR  = "Files/manual"      # holidays.csv, weather.csv, promo.csv, econ.csv
# holidays.csv : date,is_public_holiday,type,multi_day_event
# weather.csv  : date,city,rain_mm,is_rainy,is_heavy_rain,tmax_c,is_hot,humidity_pct
# promo.csv    : date            (optional; else derived from PromoFlag / promo_active=0)
# econ.csv     : ProductId,gm,shelf_life_days,salvage_frac  (optional; else demo CR=0.35)

# --- output table names ---
O_FEATURES = "cfc_features"
O_FEATLIST = "cfc_feature_list"  # tiny 1-row table holding the ordered feature list
O_BACKTEST = "cfc_backtest_preds"
O_ORDER    = "cfc_order_plan"
O_RUNS     = "cfc_model_runs"
O_CHAMP    = "cfc_champion"
O_DRIFT    = "cfc_drift"          # monitor output (PSI + accuracy verdict over time)
O_BEST     = "cfc_best_params"    # Optuna best hyperparameters (train reads if present)
O_FEATIMP  = "cfc_feature_importance"  # per-version LightGBM gain importance (for the UI)
O_PRED_VS_ACTUAL = "cfc_pred_vs_actual"  # per (dt,branch,product) forecast vs realized net_units + abs_err
O_DAILY_ACC      = "cfc_daily_accuracy"  # per-day accuracy = 1 - WMAPE(day), units_off, n_rows
''', tags=["parameters"]))

# ---- setup / IO helpers ----
cells.append(md("## 2 · Setup & Lakehouse IO helpers"))
cells.append(code('''
import numpy as np, pandas as pd, json, datetime as dt, warnings, bisect
import lightgbm as lgb
import mlflow, mlflow.lightgbm
from pyspark.sql import SparkSession
warnings.filterwarnings("ignore")
spark = SparkSession.builder.getOrCreate()

def _q(name):
    """Qualify a table name with the Lakehouse schema (schema-enabled -> dbo.<name>)."""
    return f"{SCHEMA}.{name}" if SCHEMA else name

def read_table(name, required=True):
    """Lakehouse delta table -> pandas. required=False returns None if absent."""
    try:
        return spark.read.table(_q(name)).toPandas()
    except Exception as e:
        if required: raise
        print(f"[warn] optional table '{name}' not found -> skipping ({e})")
        return None

def _clean_for_spark(pdf):
    """Make a pandas frame safe for spark.createDataFrame: no category dtype, no mixed
    object, no NaN in would-be int columns. Spark infers types from clean pandas."""
    pdf = pdf.reset_index(drop=True).copy()
    for c in pdf.columns:
        s = pdf[c]
        if str(s.dtype) == "category":
            pdf[c] = s.astype("int64") if s.cat.categories.dtype.kind in "iu" else s.astype(str)
        elif s.dtype == object:
            pdf[c] = s.astype(str)
        elif str(s.dtype).startswith("datetime"):
            pass  # -> spark timestamp
        elif s.dtype.kind == "f":
            pdf[c] = s.astype("float64")   # keep NaN as double null (safe)
    return pdf

def write_table(pdf, name):
    """pandas -> Lakehouse delta table (overwrite)."""
    (spark.createDataFrame(_clean_for_spark(pdf))
          .write.mode("overwrite").option("overwriteSchema", "true")
          .format("delta").saveAsTable(_q(name)))
    print(f"[write] {_q(name)}: {len(pdf):,} rows")

def read_manual_csv(fname, required=True):
    """User-provided CSV from OneLake Files/manual/*. Returns pandas or None."""
    path = f"/lakehouse/default/{MANUAL_DIR}/{fname}"
    try:
        return pd.read_csv(path)
    except Exception as e:
        if required: raise RuntimeError(f"manual file missing: {path} — upload it via the app. ({e})")
        print(f"[warn] optional manual file '{fname}' not found -> default"); return None

def load_sales():
    """Sales at daily grain. Aggregates the RAW transaction table IN FABRIC (Spark, no egress)."""
    if not SALES_IS_RAW:
        return read_table(T_SALES)
    print(f"aggregating {T_SALES} in-place (Spark GROUP BY, no data moved)...")
    # NOTE: RefundQuantity / VoidQuantity are NULL on ~all rows -> COALESCE to 0
    # (else Quantity - NULL - NULL = NULL and net_units is empty).
    q = f"""
        SELECT DayKey, BranchId, ProductId,
               SUM(COALESCE(Quantity,0))                                                    AS gross_units,
               SUM(COALESCE(Quantity,0) - COALESCE(RefundQuantity,0) - COALESCE(VoidQuantity,0)) AS net_units,
               SUM(COALESCE(Amount,0))                                                      AS amount,
               SUM(COALESCE(Discount,0))                                                    AS discount,
               COUNT(DISTINCT OrderId)                                                      AS txns,
               MAX(COALESCE(CAST(PromoFlag AS INT), 0))                                     AS promo_flag
        FROM {_q(T_SALES)}
        WHERE DayKey >= '{SALES_START}'
        GROUP BY DayKey, BranchId, ProductId
    """
    pdf = spark.sql(q).toPandas()
    # Spark DECIMAL -> pandas object(Decimal); force numeric so downstream math/sum works.
    for c in ["gross_units", "net_units", "amount", "discount", "txns", "promo_flag"]:
        if c in pdf.columns:
            pdf[c] = pd.to_numeric(pdf[c], errors="coerce")
    pdf["net_units"] = pdf["net_units"].fillna(0.0)
    print(f"  aggregated {len(pdf):,} daily rows | net_units sum {pdf.net_units.sum():,.0f}")
    return pdf

mlflow.set_experiment(EXPERIMENT)
print("MODE =", MODE, "| CUTOFF =", CUTOFF)
'''))

# ---- model config (shared) ----
cells.append(md("## 3 · Model config (identical to the local engine)"))
cells.append(code('''
PARAMS = dict(objective="quantile", n_estimators=600, learning_rate=0.05,
              num_leaves=255, min_child_samples=100, subsample=0.8,
              colsample_bytree=0.8, n_jobs=-1, verbosity=-1)
QS  = [(0.5, "p50"), (0.85, "p85"), (0.95, "p95")]
CAT = ["BranchId","ProductId","dow","month","is_weekend","is_public_holiday","is_festival",
       "is_thingyan","promo_active","city","CatLvl2_Name","CatLvl3_Name","ChannelId",
       "Segment","branch_city","is_rainy","is_heavy_rain","is_hot"]

def wmape(y, yh):
    y, yh = np.asarray(y, float), np.asarray(yh, float)
    return np.abs(y - yh).sum() / max(np.abs(y).sum(), 1e-9)

def current_params():
    """Base PARAMS, overridden by Optuna best (cfc_best_params) if it exists."""
    p = dict(PARAMS)
    try:
        bp = read_table(O_BEST, required=False)
        if bp is not None and len(bp):
            p.update(json.loads(bp["params"].iloc[0])); print("  using tuned params from", O_BEST)
    except Exception:
        pass
    return p
'''))

# ---- FEATURES (port of features.py) ----
cells.append(md("## 4 · Feature engineering  \nPort of `src/features.py` — reads Lakehouse, writes `cfc_features`."))
cells.append(code('''
def build_features():
    d = load_sales()
    d["DayKey"] = d["DayKey"].astype(str)
    d = d[d.DayKey >= SALES_START].copy()
    d["date"] = pd.to_datetime(d.DayKey, format="%Y%m%d")
    promo_by_day = d[["date","promo_flag"]] if "promo_flag" in d else None
    pr = read_table(T_PRODUCT); br = read_table(T_BRANCH)

    # FG only + Class A+B (cumulative volume)
    fg = set(pr.loc[pr.CatLvl1_Name == "FG", "ProductId"])
    d = d[d.ProductId.isin(fg)].copy()
    psum = d.groupby("ProductId").net_units.sum().sort_values(ascending=False)
    if len(psum) == 0 or psum.sum() <= 0:
        raise RuntimeError(f"No positive net_units after FG filter (rows={len(d)}, fg_products={len(fg)}, "
                           f"net_sum={psum.sum()}). Check the sales aggregation / CatLvl1_Name=='FG' / ProductId types.")
    cum = psum.cumsum() / psum.sum()
    keep = set(cum[cum <= ABC_CUTOFF].index) | {psum.index[0]}
    d = d[d.ProductId.isin(keep)].copy()
    print(f"universe: {d.ProductId.nunique()} products, {d.BranchId.nunique()} branches, {len(d):,} rows")

    # complete daily calendar per (branch,product) over active span (zero-fill)
    base = d[["BranchId","ProductId","date","net_units"]].copy()
    def series(g):
        s, e = g.date.min(), g.date.max()
        out = g.set_index("date").reindex(pd.date_range(s, e, freq="D"))
        out["BranchId"] = g.name[0]; out["ProductId"] = g.name[1]
        out["net_units"] = out["net_units"].fillna(0.0)
        return out.reset_index().rename(columns={"index": "date"})
    cal = base.groupby(["BranchId","ProductId"], group_keys=False).apply(series)
    cal = cal[["BranchId","ProductId","date","net_units"]].sort_values(["BranchId","ProductId","date"])
    print(f"calendar-completed panel: {len(cal):,} rows")

    # lags / rolling (leak-safe shift>=1)
    g = cal.groupby(["BranchId","ProductId"])["net_units"]
    for L in (1,7,14,28):  cal[f"lag_{L}"]  = g.shift(L)
    for W in (7,14,28):
        cal[f"rmean_{W}"] = g.shift(1).rolling(W).mean()
        cal[f"rstd_{W}"]  = g.shift(1).rolling(W).std()
    cal["rmax_28"] = g.shift(1).rolling(28).max()
    cal["dow_mean_28"] = (cal.groupby(["BranchId","ProductId", cal.date.dt.dayofweek])["net_units"]
                             .shift(1).rolling(4).mean())

    # calendar
    cal["dow"] = cal.date.dt.dayofweek; cal["dom"] = cal.date.dt.day
    cal["month"] = cal.date.dt.month
    cal["weekofyear"] = cal.date.dt.isocalendar().week.astype(int)
    cal["is_weekend"] = (cal.dow >= 5).astype(int)

    # holidays / festivals (manual — user-provided)
    hol = read_manual_csv("holidays.csv"); hol["date"] = pd.to_datetime(hol.date)
    ph   = set(hol.loc[hol.is_public_holiday == 1, "date"])
    fest = set(hol.loc[hol.type == "festival", "date"])
    thg  = set(hol.loc[hol.get("multi_day_event").astype(str).str.contains("Thingyan", na=False), "date"]) \\
           if "multi_day_event" in hol else set()
    cal["is_public_holiday"] = cal.date.isin(ph).astype(int)
    cal["is_festival"]       = cal.date.isin(fest).astype(int)
    cal["is_thingyan"]       = cal.date.isin(thg).astype(int)
    hsorted = sorted(ph)
    def dth(x):
        i = bisect.bisect_left(hsorted, x)
        return (hsorted[i]-x).days if i < len(hsorted) else 99
    cal["days_to_holiday"] = cal.date.map(dth).clip(upper=30)

    # promo: manual calendar (user) -> else derived from sales PromoFlag -> else 0
    promo = read_manual_csv("promo.csv", required=False)
    if promo is not None and "date" in promo:
        pdates = set(pd.to_datetime(promo.date))
        cal["promo_active"] = cal.date.isin(pdates).astype(int)
    elif promo_by_day is not None:
        pf = promo_by_day.groupby("date").promo_flag.max()
        cal["promo_active"] = cal.date.map(pf).fillna(0).astype(int)
    else:
        cal["promo_active"] = 0

    # weather (manual — user-provided; branch -> city -> daily)
    wx = read_manual_csv("weather.csv"); wx["date"] = pd.to_datetime(wx.date)
    cities = ["Mandalay","Naypyidaw","Bago","Pyay","Taunggyi","Yangon"]
    def city_of(addr):
        a = str(addr).lower()
        for c in cities:
            if c.lower() in a: return c
        return "Yangon"
    br["city"] = br.Address.map(city_of)
    cal["city"] = cal.BranchId.map(br.set_index("BranchId").city.to_dict()).fillna("Yangon")
    wxk = wx[["date","city","rain_mm","is_rainy","is_heavy_rain","tmax_c","is_hot","humidity_pct"]]
    cal = cal.merge(wxk, on=["date","city"], how="left")

    # product & branch attributes
    cal = cal.merge(pr[["ProductId","ListPrice","CatLvl2_Name","CatLvl3_Name"]], on="ProductId", how="left")
    ba = br[["BranchId","ChannelId","Segment","city"]].rename(columns={"city":"branch_city"})
    cal = cal.merge(ba, on="BranchId", how="left")
    for c in ["CatLvl2_Name","CatLvl3_Name","Segment","branch_city","city"]:
        cal[c] = cal[c].astype("category").cat.codes
    cal["ChannelId"] = cal.ChannelId.fillna(-1).astype(int)

    cal = cal.rename(columns={"net_units":"y"})
    cal = cal[cal["lag_28"].notna()].copy()          # drop warmup
    feat_cols = [c for c in cal.columns if c not in ("BranchId","ProductId","date","y","amount","discount","txns")]
    write_table(cal, O_FEATURES)
    write_table(pd.DataFrame({"features": [",".join(feat_cols)]}), O_FEATLIST)  # tiny 1-row list
    print(f"FEATURES: {len(feat_cols)} cols, {len(cal):,} rows -> {O_FEATURES}")
    return cal, feat_cols

def load_features():
    cal = read_table(O_FEATURES)
    cal["date"] = pd.to_datetime(cal["date"])
    feat_cols = read_table(O_FEATLIST)["features"].iloc[0].split(",")
    cal["BranchId"] = cal.BranchId.astype(int); cal["ProductId"] = cal.ProductId.astype(int)
    cal["y"] = pd.to_numeric(cal["y"], errors="coerce").fillna(0.0)
    # Delta round-trip can store Decimal/object cols as strings -> coerce numeric feats back
    # (categoricals stay as-is; _as_cat turns them into category dtype at fit time).
    for c in feat_cols:
        if c in cal.columns and c not in CAT:
            cal[c] = pd.to_numeric(cal[c], errors="coerce")
    return cal, feat_cols

'''))

# ---- helper: assemble FEATS/CATS ----
cells.append(md("## 5 · Train  \nPort of `src/train.py` — logs params/metrics/model to **MLflow**, writes a run row."))
cells.append(code('''
def feat_sets(feat_cols):
    F = list(dict.fromkeys(feat_cols + ["BranchId","ProductId"]))
    C = [c for c in CAT if c in F]
    return F, C

def _as_cat(X, cats):
    X = X.copy()
    for c in cats: X[c] = X[c].astype("category")
    return X

def train(cutoff):
    cal, feat_cols = load_features()
    F, C = feat_sets(feat_cols)
    cut = pd.Timestamp(cutoff)
    tr = cal[cal.date < cut]; ho = cal[cal.date >= cut]
    ver = "v_" + cut.strftime("%Y%m%d") + "_" + dt.datetime.utcnow().strftime("%H%M")
    print(f"train {len(tr):,} (<{cut.date()}) | holdout {len(ho):,} | ver {ver}")
    Xtr = _as_cat(tr[F], C)
    P = current_params()

    metrics = {}
    with mlflow.start_run(run_name=ver) as run:
        mlflow.log_params({**P, "cutoff": str(cut.date()), "n_features": len(F), "n_cats": len(C)})
        p50_model = None
        for q, name in QS:
            m = lgb.LGBMRegressor(alpha=q, **P)
            m.fit(Xtr, tr.y, categorical_feature=C)
            if name == "p50":
                p50_model = m
                ph = np.clip(m.predict(_as_cat(ho[F], C)), 0, None)
                metrics["wmape"] = float(wmape(ho.y, ph))
                metrics["holdout_cover_p50"] = float((ho.y <= ph).mean())
            # log each quantile booster as an artifact
            mlflow.lightgbm.log_model(m, artifact_path=f"model_{name}")
        mlflow.log_metrics(metrics)
        # register the P50 model (champion candidate)
        mv = mlflow.register_model(f"runs:/{run.info.run_id}/model_p50", MODEL_NAME)
        meta = dict(version=ver, cutoff=str(cut.date()), train_rows=int(len(tr)),
                    holdout_rows=int(len(ho)), feats=F, cats=C,
                    run_id=run.info.run_id, mlflow_version=int(mv.version), **metrics)

    # per-version feature importance -> table the UI reads
    try:
        gains = p50_model.booster_.feature_importance(importance_type="gain").astype(float)
        mx = gains.max() or 1.0
        imp = pd.DataFrame({"version": ver, "feature": F,
                            "gain": gains, "gain_norm": gains / mx}).sort_values("gain", ascending=False)
        hist = read_table(O_FEATIMP, required=False)
        write_table(pd.concat([hist, imp], ignore_index=True) if hist is not None else imp, O_FEATIMP)
    except Exception as e:
        print("[warn] feature importance skipped:", e)

    print(f"trained {ver}: holdout WMAPE {metrics['wmape']:.3f} (MLflow v{mv.version})")
    gate_and_log(meta)
    return meta

def gate_and_log(meta):
    """Champion/challenger gate (mirrors pipeline.py) + MLflow 'champion' alias + Lakehouse tables."""
    champ = read_table(O_CHAMP, required=False)
    from mlflow.tracking import MlflowClient
    client = MlflowClient()
    promoted = False
    if champ is None or len(champ) == 0:
        promoted = True; note = "no champion existed -> PROMOTED (bootstrap)"   # first model must go live
    else:
        cur = champ.sort_values("created").iloc[-1]
        gain = 1 - meta["wmape"] / float(cur["wmape"])
        print(f"champion {cur['version']} WMAPE {float(cur['wmape']):.3f} | challenger {meta['wmape']:.3f} | gain {gain*100:+.1f}%")
        if AUTO_PROMOTE and gain >= MIN_GAIN:
            promoted = True; note = f"AUTO-PROMOTED (gain +{gain*100:.1f}% >= {MIN_GAIN*100:.0f}%)"
        else:
            note = (f"CHALLENGER (gain +{gain*100:.1f}%) — awaiting human approval"
                    if gain >= MIN_GAIN else
                    f"CHALLENGER (gain +{gain*100:.1f}% < {MIN_GAIN*100:.0f}%) — awaiting human approval")
    print("->", note)

    created = dt.datetime.utcnow().isoformat()
    run_row = pd.DataFrame([{**{k: meta[k] for k in ("version","cutoff","train_rows","holdout_rows","wmape","holdout_cover_p50","run_id","mlflow_version")},
                             "promoted": promoted, "note": note, "created": created,
                             "feats": ",".join(meta["feats"]), "cats": ",".join(meta["cats"])}])
    # append to runs history
    hist = read_table(O_RUNS, required=False)
    write_table(pd.concat([hist, run_row], ignore_index=True) if hist is not None else run_row, O_RUNS)

    if promoted:
        try:
            client.set_registered_model_alias(MODEL_NAME, "champion", str(meta["mlflow_version"]))
        except Exception as e:
            print("[warn] alias set skipped:", e)
        write_table(run_row, O_CHAMP)     # champion pointer = latest promoted row
    return promoted

def promote(version):
    """Human-approved promotion (from the app). Make `version` the live champion +
    set the MLflow 'champion' alias. Reversible: promote an older version to roll back."""
    if not version:
        raise ValueError("MODE=promote needs PROMOTE_VERSION")
    runs = read_table(O_RUNS)
    row = runs[runs.version == version].sort_values("created").tail(1)
    if len(row) == 0:
        raise RuntimeError(f"version {version} not found in {O_RUNS}")
    r = row.iloc[0].to_dict()
    from mlflow.tracking import MlflowClient
    try:
        MlflowClient().set_registered_model_alias(MODEL_NAME, "champion", str(int(r["mlflow_version"])))
    except Exception as e:
        print("[warn] alias set skipped:", e)
    r["promoted"] = True; r["note"] = "APPROVED via app"; r["created"] = dt.datetime.utcnow().isoformat()
    write_table(pd.DataFrame([r]), O_CHAMP)
    print(f"PROMOTED {version} -> champion (approved)")
    return version

'''))

# ---- BACKTEST ----
cells.append(md("## 6 · Backtest  \nPort of `src/backtest.py` — walk-forward folds, writes `cfc_backtest_preds` (the app's evidence source)."))
cells.append(code('''
def backtest():
    cal, feat_cols = load_features()
    F, C = feat_sets(feat_cols)
    pv = cal.groupby("ProductId").y.sum(); cum = pv.sort_values(ascending=False).cumsum()/pv.sum()
    abc = pd.cut(cum, [0,.8,.95,1.001], labels=["A","B","C"]).to_dict()
    cal["abc"] = cal.ProductId.map(abc)
    mper = cal.date.dt.to_period("M").astype(str)
    # derive 3 most-recent complete months at/after CUTOFF as folds
    months = sorted(mper[cal.date >= pd.Timestamp(CUTOFF)].unique())[:3]
    print("folds:", months)
    P = current_params()

    all_preds = []
    for fold in months:
        fs = pd.Timestamp(fold + "-01")
        tr = cal[cal.date < fs]; te = cal[mper == fold].copy()
        Xtr = _as_cat(tr[F], C); Xte = _as_cat(te[F], C)
        with mlflow.start_run(run_name=f"backtest_{fold}", nested=False):
            for q, name in QS:
                m = lgb.LGBMRegressor(alpha=q, **P); m.fit(Xtr, tr.y, categorical_feature=C)
                te[name] = np.clip(m.predict(Xte), 0, None)
            fw = wmape(te.y, te.p50)
            mlflow.log_metric("fold_wmape", fw); mlflow.log_param("fold", fold)
        te["fold"] = fold; all_preds.append(te)
        print(f"fold {fold}: train {len(tr):,} test {len(te):,} WMAPE {fw:.3f}")

    bt = pd.concat(all_preds, ignore_index=True)
    keep = ["date","BranchId","ProductId","y","p50","p85","p95","fold","abc","ListPrice",
            "rmean_7","lag_1","lag_7","dow_mean_28"]
    write_table(bt[[c for c in keep if c in bt]], O_BACKTEST)
    print(f"overall backtest WMAPE {wmape(bt.y, bt.p50):.3f} | {len(bt):,} rows -> {O_BACKTEST}")
    pred_vs_actual(bt)   # daily forecast-vs-actual accuracy (backtest folds have realized y)
    return bt

'''))

# ---- PRED-VS-ACTUAL + DAILY ACCURACY ----
cells.append(md("""\
## 6.5 · Daily prediction-vs-actual accuracy

Whenever a lane produces forecasts that also carry the **realized** target (`y` = aggregated
`net_units`, the same GROUP BY sales value), we score them day-by-day. This is additive: it only
reads the preds frame the predict/backtest lanes already built (no retraining, no re-aggregation).

- **`cfc_pred_vs_actual`** — one row per `(dt, branch, product)` that has an actual:
  `y_pred` (the P50 forecast), `y_actual` (realized net_units), `abs_err = |y_pred − y_actual|`.
- **`cfc_daily_accuracy`** — per `dt`: `wmape` (day WMAPE), `accuracy = clip(1 − wmape, 0, 1)`,
  `units_off = mean(abs_err)`, `n_rows`.

Rows without a realized actual (genuine future-dated forecasts) are skipped — you can only score a
day once its sales exist.
"""))
cells.append(code('''
def pred_vs_actual(preds, pred_col="p50"):
    """Score forecasts against realized net_units, per day. `preds` must carry date, BranchId,
    ProductId, y (realized net_units == aggregated sales target) and a P50 column. Reuses the y
    already on the frame (the features/backtest join to aggregated sales); does NOT recompute.
    Keeps only rows where an actual exists. Writes cfc_pred_vs_actual + cfc_daily_accuracy."""
    df = preds.copy()
    if "y" not in df or pred_col not in df:
        print(f"[warn] pred_vs_actual skipped: need 'y' and '{pred_col}' columns"); return None, None
    df = df[pd.to_numeric(df["y"], errors="coerce").notna()].copy()
    if df.empty:
        print("[warn] pred_vs_actual: no rows with a realized actual -> skipped"); return None, None
    pv = pd.DataFrame({
        "dt":       pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"),
        "branch":   pd.to_numeric(df["BranchId"], errors="coerce").astype("Int64").astype("int64"),
        "product":  pd.to_numeric(df["ProductId"], errors="coerce").astype("Int64").astype("int64"),
        "y_pred":   np.clip(pd.to_numeric(df[pred_col], errors="coerce").fillna(0.0), 0, None),
        "y_actual": pd.to_numeric(df["y"], errors="coerce").fillna(0.0),
    })
    pv["abs_err"] = (pv["y_pred"] - pv["y_actual"]).abs()
    write_table(pv, O_PRED_VS_ACTUAL)

    # per-day accuracy = 1 - WMAPE(day); WMAPE(day) = sum|err| / sum|actual|.
    def _agg(g):
        denom = g["y_actual"].abs().sum()
        w = float(g["abs_err"].sum() / denom) if denom > 1e-9 else np.nan
        return pd.Series({"wmape": w, "units_off": float(g["abs_err"].mean()), "n_rows": int(len(g))})
    da = pv.groupby("dt").apply(_agg).reset_index()
    da["accuracy"] = (1.0 - da["wmape"]).clip(0.0, 1.0)   # NaN wmape (all-zero day) -> NaN accuracy
    da = da[["dt","accuracy","wmape","units_off","n_rows"]]
    write_table(da, O_DAILY_ACC)
    print(f"pred_vs_actual: {len(pv):,} scored rows over {da['dt'].nunique()} day(s) "
          f"-> {O_PRED_VS_ACTUAL} / {O_DAILY_ACC}")
    return pv, da

'''))

# ---- PREDICT ----
cells.append(md("## 7 · Predict  \nPort of `src/pipeline.py predict` — champion → newsvendor order plan, writes `cfc_order_plan`."))
cells.append(code('''
def q_at(cr, p50, p85, p95):
    """Newsvendor pick from quantile anchors by critical ratio (mirrors src/order_qty.q_at)."""
    cr = np.asarray(cr, float)
    out = np.where(cr < 0.5, p50 * (cr/0.5),
          np.where(cr < 0.85, p50 + (p85-p50)*((cr-0.5)/0.35),
          np.where(cr < 0.95, p85 + (p95-p85)*((cr-0.85)/0.10), p95)))
    return np.clip(out, 0, None)

def predict(date):
    cal, feat_cols = load_features()
    champ = read_table(O_CHAMP, required=False)
    if champ is None or len(champ) == 0:
        raise RuntimeError("no champion — run train first")
    cur = champ.sort_values("created").iloc[-1]
    F = cur["feats"].split(","); C = cur["cats"].split(",")
    day = cal[cal.date == (pd.Timestamp(date) if date else cal.date.max())].copy()
    if day.empty: raise RuntimeError(f"no feature rows for {date}")

    # load champion boosters from MLflow (alias 'champion')
    import mlflow.pyfunc
    Xd = _as_cat(day[F], C)
    for q, name in QS:
        # each quantile logged under model_<name> in the champion run
        uri = f"runs:/{cur['run_id']}/model_{name}"
        booster = mlflow.lightgbm.load_model(uri)
        day[name] = np.clip(booster.predict(Xd), 0, None)

    # per-product critical ratio from MANUAL econ (the newsvendor unlock). Missing -> demo CR=0.35.
    econ = read_manual_csv("econ.csv", required=False)
    if econ is not None and {"ProductId","gm","shelf_life_days"}.issubset(econ.columns):
        e = econ.copy()
        e["salvage_frac"] = e.get("salvage_frac", 0.0)
        # Cu = price*gm ; Co = (price*(1-gm) - salvage)*spoil_frac ; CR = Cu/(Cu+Co)
        e["spoil_frac"] = 1.0 / e["shelf_life_days"].clip(lower=1)
        day = day.merge(e[["ProductId","gm","salvage_frac","spoil_frac"]], on="ProductId", how="left")
        price = day.get("ListPrice", pd.Series(1.0, index=day.index)).fillna(1).clip(lower=1)
        cu = price * day["gm"].fillna(0.35)
        co = (price * (1 - day["gm"].fillna(0.35)) - day["salvage_frac"].fillna(0)) * day["spoil_frac"].fillna(1)
        day["CR"] = (cu / (cu + co)).clip(0.01, 0.99).fillna(0.35)
    else:
        day["CR"] = 0.35
    day["order_qty"] = q_at(day.CR.values, day.p50.values, day.p85.values, day.p95.values)

    # --- demand uncensoring (sales != demand) --------------------------------------------------
    # Observed sales are CENSORED by availability: a stockout / not-stocked day shows low or zero
    # sales even though true demand was higher. We flag likely-censored days with a CONSERVATIVE
    # heuristic, then un-censor them toward the P85 forecast as an unconstrained-demand proxy.
    #
    # is_stockout = TRUE when either:
    #   (a) zero-sales day while the trailing-28d mean was clearly positive (> STOCKOUT_MIN_MEAN)
    #       -> the item normally sells but sold nothing today = likely out of stock / not stocked; OR
    #   (b) sales pinned at the trailing-28d max BOTH today and yesterday (lag_1) with rmax_28 > 0
    #       -> demand clipped at the shelf ceiling on consecutive days = censored-high.
    # Everything else is treated as genuine (uncensored) sales. Missing features -> not flagged.
    obs    = pd.to_numeric(day["y"], errors="coerce").fillna(0.0)
    mean28 = pd.to_numeric(day.get("rmean_28", np.nan), errors="coerce")
    rmax28 = pd.to_numeric(day.get("rmax_28",  np.nan), errors="coerce")
    lag1   = pd.to_numeric(day.get("lag_1",    np.nan), errors="coerce")
    zero_stockout = (obs <= 0) & (mean28 > STOCKOUT_MIN_MEAN)
    clip_stockout = (obs >= rmax28) & (lag1 >= rmax28) & (rmax28 > 0)
    day["is_stockout"] = (zero_stockout.fillna(False) | clip_stockout.fillna(False)).astype(bool)
    # sales are censored by availability; demand_est un-censors stockout days using the P85 quantile
    # as demand proxy (never below observed); non-stockout days keep observed sales.
    day["demand_est"] = np.where(day["is_stockout"].values,
                                 np.maximum(obs.values, np.clip(day.p85.values, 0, None)),
                                 obs.values).astype(float)

    out = day[["date","BranchId","ProductId","y","p50","p85","p95","CR","order_qty",
               "is_stockout","demand_est"]].copy()
    write_table(out, O_ORDER)
    print(f"champion {cur['version']} | {out.date.iloc[0].date()}: {len(out):,} rows, "
          f"{out.order_qty.sum():,.0f} units ordered | "
          f"{int(out.is_stockout.sum()):,} stockout-day(s) un-censored -> {O_ORDER}")
    pred_vs_actual(out)   # daily forecast-vs-actual accuracy (predict day carries realized y)
    return out

'''))

cells.append(md("""\
## 7.1 · Demand uncensoring (sales ≠ demand)

Observed sales **understate demand** whenever an item is out of stock or was never stocked that
day — the POS can only record what was on the shelf. Ordering off censored sales quietly bakes in
past stockouts. The predict lane therefore adds two columns to **`cfc_order_plan`**:

- **`is_stockout`** (bool) — a **conservative** censoring flag. TRUE when either
  (a) a **zero-sales day** occurs while the trailing-28-day mean was clearly positive
  (`rmean_28 > STOCKOUT_MIN_MEAN`, default 1.0 unit/day) — the SKU normally sells but sold nothing,
  i.e. likely out of stock / not stocked; **or**
  (b) sales are **pinned at the trailing-28-day max on two consecutive days** (`y ≥ rmax_28` and
  `lag_1 ≥ rmax_28`, `rmax_28 > 0`) — demand clipped at the shelf ceiling. Everything else is
  treated as genuine sales; missing features are never flagged.
- **`demand_est`** (float) — **sales are censored by availability; `demand_est` un-censors stockout
  days using the P85 quantile as the demand proxy** (`max(observed, P85)`, never below observed);
  non-stockout days keep `demand_est = observed`.

The heuristic is intentionally simple and conservative (only obvious censoring signals) so it never
inflates ordinary quiet days. Tune the aggressiveness via `STOCKOUT_MIN_MEAN` in the parameters cell.
"""))
cells.append(md("## 7.5 · Monitor  \nPSI drift + champion accuracy vs recent — writes `cfc_drift`. Accuracy drift (not data drift alone) is the retrain trigger."))
cells.append(code('''
def _psi(ref, cur, bins=10):
    ref = np.asarray(ref, float); cur = np.asarray(cur, float)
    ref = ref[~np.isnan(ref)]; cur = cur[~np.isnan(cur)]
    if len(ref) < 50 or len(cur) < 50: return np.nan
    qs = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(qs) < 3: return np.nan
    r, _ = np.histogram(ref, qs); c, _ = np.histogram(cur, qs)
    r = r / max(r.sum(), 1) + 1e-6; c = c / max(c.sum(), 1) + 1e-6
    return float(((c - r) * np.log(c / r)).sum())

def monitor():
    cal, feat = load_features()
    champ = read_table(O_CHAMP, required=False)
    cut = cal.date.max().normalize() - pd.Timedelta(days=MONITOR_REF_DAYS)
    ref = cal[cal.date < cut]; rec = cal[cal.date >= cut]
    watch = [w for w in ["y","lag_7","rmean_28","rstd_28","ListPrice","tmax_c","rain_mm","promo_active","dow"] if w in cal]
    drift = {}; data_drift = False
    for w in watch:
        p = _psi(ref[w], rec[w]); drift[w] = None if np.isnan(p) else round(p, 3)
        if not np.isnan(p) and p > PSI_WARN: data_drift = True
    acc_drift = False; recent_wmape = None; champ_wmape = None
    if champ is not None and len(champ):
        cur = champ.sort_values("created").iloc[-1]; champ_wmape = float(cur["wmape"])
        F = cur["feats"].split(","); C = cur["cats"].split(",")
        booster = mlflow.lightgbm.load_model(f"runs:/{cur['run_id']}/model_p50")
        pr = np.clip(booster.predict(_as_cat(rec[F], C)), 0, None)
        recent_wmape = float(wmape(rec.y, pr))
        acc_drift = recent_wmape > champ_wmape * (1 + WMAPE_WARN)
    verdict = "RETRAIN (accuracy drift)" if acc_drift else ("watch (data drift only)" if data_drift else "healthy")
    row = pd.DataFrame([{"ts": dt.datetime.utcnow().isoformat(), "ref_cutoff": str(cut.date()),
                         "champ_wmape": champ_wmape, "recent_wmape": recent_wmape,
                         "data_drift": bool(data_drift), "accuracy_drift": bool(acc_drift),
                         "verdict": verdict, "psi": json.dumps(drift)}])
    hist = read_table(O_DRIFT, required=False)
    write_table(pd.concat([hist, row], ignore_index=True) if hist is not None else row, O_DRIFT)
    print(f"monitor: {verdict} | recent {recent_wmape} vs champ {champ_wmape} | data_drift={data_drift}")
    return acc_drift, verdict

'''))

cells.append(md("## 7.6 · Finetune (Optuna)  \n`MODE=tune` — searches hyperparameters on a validation split, saves best to `cfc_best_params`. `train`/`backtest` auto-use it next run."))
cells.append(code('''
def tune(n_trials=TUNE_TRIALS):
    try:
        import optuna
    except ImportError:
        import subprocess, sys as _s
        subprocess.check_call([_s.executable, "-m", "pip", "install", "-q", "optuna"]); import optuna
    cal, feat = load_features(); F, C = feat_sets(feat)
    cut = pd.Timestamp(CUTOFF)
    tr = cal[cal.date < cut]; va = cal[cal.date >= cut]
    Xtr = _as_cat(tr[F], C); Xva = _as_cat(va[F], C)
    def objective(t):
        p = dict(objective="quantile", n_jobs=-1, verbosity=-1,
                 n_estimators=t.suggest_int("n_estimators", 300, 1200, step=100),
                 learning_rate=t.suggest_float("learning_rate", 0.02, 0.1, log=True),
                 num_leaves=t.suggest_int("num_leaves", 63, 511),
                 min_child_samples=t.suggest_int("min_child_samples", 20, 200),
                 subsample=t.suggest_float("subsample", 0.6, 1.0),
                 colsample_bytree=t.suggest_float("colsample_bytree", 0.6, 1.0))
        m = lgb.LGBMRegressor(alpha=0.5, **p); m.fit(Xtr, tr.y, categorical_feature=C)
        return wmape(va.y, np.clip(m.predict(Xva), 0, None))
    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    best = dict(objective="quantile", n_jobs=-1, verbosity=-1, **study.best_params)
    write_table(pd.DataFrame({"params": [json.dumps(best)], "val_wmape": [study.best_value],
                              "ts": [dt.datetime.utcnow().isoformat()]}), O_BEST)
    with mlflow.start_run(run_name="tune"): mlflow.log_metric("tune_best_val_wmape", study.best_value)
    print(f"tune: best val WMAPE {study.best_value:.3f} -> saved to {O_BEST}")
    print(json.dumps(study.best_params, indent=2))
    return best

'''))

cells.append(md("## 8 · Run  \nSingle dispatch on `MODE`. `auto` = monitor then retrain **only if** accuracy drifted. Any failure writes the full traceback to `Files/errors/last_error.txt` (fetchable) and re-raises."))
cells.append(code('''
import os, traceback
def _log_error(tb):
    try:
        p = "/lakehouse/default/Files/errors"; os.makedirs(p, exist_ok=True)
        with open(f"{p}/last_error.txt", "w") as fh:
            fh.write(f"MODE={MODE}\\n{dt.datetime.utcnow().isoformat()}\\n\\n{tb}")
        print("[error logged] Files/errors/last_error.txt")
    except Exception as e:
        print("could not write error file:", e)

try:
    print(f"=== RUN MODE={MODE} ===")
    if   MODE == "features": build_features()
    elif MODE == "train":    train(CUTOFF)
    elif MODE == "backtest": backtest()
    elif MODE == "predict":  predict(PREDICT_DATE)
    elif MODE == "monitor":  monitor()
    elif MODE == "tune":     tune()
    elif MODE == "promote":  promote(PROMOTE_VERSION)
    elif MODE == "all":
        build_features(); train(CUTOFF); backtest(); predict(PREDICT_DATE); monitor()
    elif MODE == "auto":
        need, verdict = monitor()
        if need:
            print("auto: accuracy drift -> rebuild features + retrain + backtest + predict")
            build_features(); train(CUTOFF); backtest(); predict(PREDICT_DATE)
        else:
            print(f"auto: {verdict} -> predict only (no retrain)")
            predict(PREDICT_DATE)
    else:
        raise ValueError(f"unknown MODE: {MODE}")
    print(f"=== DONE MODE={MODE} ===")
except Exception:
    tb = traceback.format_exc(); print(tb); _log_error(tb); raise
'''))

cells.append(md("""\
## 9 · Outputs

The app reads these Lakehouse tables (Phase 3 wires the FastAPI `deps/duck.py` to the Lakehouse SQL endpoint):
- `cfc_backtest_preds` → Model Evidence / Leaderboard charts
- `cfc_order_plan` → Smart Ordering + outlet×SKU Excel (now also carries `is_stockout` + `demand_est`)
- `cfc_pred_vs_actual` → per (dt,branch,product) forecast vs realized net_units + `abs_err`
- `cfc_daily_accuracy` → per-day `accuracy = 1 − WMAPE(day)`, `wmape`, `units_off`, `n_rows`
- `cfc_model_runs` / `cfc_champion` → Leaderboard rows + champion pointer
- MLflow experiment `CFC_Demand`, model `CFC_Demand_P50` alias `champion` → lineage / one-click rollback

`cfc_pred_vs_actual` + `cfc_daily_accuracy` are emitted by the **predict**, **backtest**, **all** and
**auto** modes (any lane that produces forecasts alongside a realized `y`). `cfc_order_plan`'s
demand-uncensoring columns are emitted by every mode that runs **predict** (predict, all, auto).

**Schedule** — a single **daily** notebook schedule runs with the baked default `MODE=auto`:
refreshes the order plan every day (`predict`) and retrains **only when accuracy actually drifted**
(monitor→conditional retrain), so no daily churn. On a drift day it registers a *challenger*
(promoted=False) awaiting human approval in the app — the live order plan stays on the approved
champion until someone promotes. Created via the Fabric Job Scheduler REST API (`items/{nb}/jobs/RunNotebook/schedules`).
**Trigger from the app** (Phase 2) — the Run-Experiment button calls the Fabric **Job Scheduler REST API** to run this notebook and streams status into the existing CLI-log UI.
"""))

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "microsoft": {"language": "python"},
    },
    "nbformat": 4, "nbformat_minor": 5,
}
out = HERE / "CFC_ML_Pipeline_Fabric.ipynb"
out.write_text(json.dumps(nb, indent=1))
print("wrote", out, "-", len(cells), "cells")
