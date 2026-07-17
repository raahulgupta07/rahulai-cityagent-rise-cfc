"""
Phase 8 — Serving pipeline + self-learning + drift monitor.

Self-learning loop (champion/challenger):
  retrain  -> train P50/P85/P95 on data < cutoff, register a versioned model, score on holdout,
              promote to champion ONLY if it beats current champion by >= MIN_GAIN. (else stays challenger)
  predict  -> load champion, forecast a target date, run newsvendor -> nightly order plan + picklist.
  monitor  -> data drift (PSI on features + target) + accuracy drift (rolling WMAPE creep) vs champion.
              Flags when retrain is warranted.

Registry: models/registry/<version>/{lgbm_p50,p85,p95}.txt + meta.json ; pointer models/champion.json.
Runs offline on data/features/train.parquet (simulates nightly ops on the historical panel).

CLI:
  python3 src/pipeline.py retrain [--cutoff YYYY-MM-DD]
  python3 src/pipeline.py predict --date YYYY-MM-DD
  python3 src/pipeline.py monitor [--ref-cutoff YYYY-MM-DD]
"""
import sys, os, json, argparse, pathlib, datetime as dt
import numpy as np, pandas as pd
import lightgbm as lgb

ROOT = pathlib.Path(__file__).resolve().parent.parent
FEAT = ROOT/"data"/"features"/"train.parquet"
REG  = ROOT/"models"/"registry"; REG.mkdir(parents=True, exist_ok=True)
CHAMP = ROOT/"models"/"champion.json"
PRED = ROOT/"data"/"predictions"; REP = ROOT/"reports"

MIN_GAIN  = 0.01    # challenger must beat champion WMAPE by >=1% (rel) to promote
PSI_WARN  = 0.20    # PSI > 0.2 = notable population shift
WMAPE_WARN= 0.10    # recent WMAPE > champion holdout WMAPE * (1+10%) = accuracy drift

PARAMS = dict(objective="quantile", n_estimators=600, learning_rate=0.05,
              num_leaves=255, min_child_samples=100, subsample=0.8,
              colsample_bytree=0.8, n_jobs=-1, verbosity=-1)
# Memory-lean mode (CFC_TRAIN_LEAN=1): lighter trees so in-container retrain does not OOM.
# Heavy full-fidelity training belongs on Fabric. Default OFF (full behaviour preserved).
LEAN = os.getenv("CFC_TRAIN_LEAN", "0") == "1"
if LEAN:
    PARAMS.update(n_estimators=400, num_leaves=63, max_bin=127, force_row_wise=True)
QS=[(0.5,"p50"),(0.85,"p85"),(0.95,"p95")]
CAT=["BranchId","ProductId","dow","month","is_weekend","is_public_holiday","is_festival",
     "is_thingyan","promo_active","city","CatLvl2_Name","CatLvl3_Name","ChannelId","Segment",
     "branch_city","is_rainy","is_heavy_rain","is_hot"]

def wmape(y,yh):
    y,yh=np.asarray(y),np.asarray(yh); return np.abs(y-yh).sum()/max(np.abs(y).sum(),1e-9)

def feats():
    base=(ROOT/"data"/"features"/"feature_list.txt").read_text().strip().split("\n")
    f=list(dict.fromkeys(base+["BranchId","ProductId"]))
    return f,[c for c in CAT if c in f]

def load_df(cols=None):
    df=pd.read_parquet(FEAT,columns=cols)
    if "BranchId" in df: df["BranchId"]=df.BranchId.astype(int)
    if "ProductId" in df: df["ProductId"]=df.ProductId.astype(int)
    return df

def champ(): return json.loads(CHAMP.read_text()) if CHAMP.exists() else None

# ---------- retrain (champion/challenger) ----------
def cmd_retrain(cutoff):
    F,C=feats()
    df=load_df()
    if LEAN:
        max_rows=int(os.getenv("CFC_MAX_ROWS","1500000"))
        if len(df)>max_rows:
            df=df.sort_values("date").tail(max_rows).reset_index(drop=True)
            print(f"[lean] capped to most-recent {len(df):,} rows")
    if cutoff: cut=pd.Timestamp(cutoff)
    else: cut=df.date.max().normalize()-pd.Timedelta(days=60)   # default holdout = last 60d
    tr=df[df.date<cut]; ho=df[df.date>=cut]
    ver="v_"+pd.Timestamp(cut).strftime("%Y%m%d")
    vdir=REG/ver; vdir.mkdir(exist_ok=True)
    Xtr=tr[F].copy(); Xho=ho[F].copy()
    for c in C: Xtr[c]=Xtr[c].astype("category"); Xho[c]=Xho[c].astype("category")
    metrics={}
    for q,name in QS:
        m=lgb.LGBMRegressor(alpha=q,**PARAMS); m.fit(Xtr,tr.y,categorical_feature=C)
        m.booster_.save_model(str(vdir/f"lgbm_{name}.txt"))
        if name=="p50":
            ph=np.clip(m.predict(Xho),0,None); metrics["wmape"]=float(wmape(ho.y,ph))
            metrics["holdout_cover_p50"]=float((ho.y<=ph).mean())
    meta=dict(version=ver,cutoff=str(cut.date()),train_rows=int(len(tr)),holdout_rows=int(len(ho)),
              feats=F,cats=C,**metrics)
    (vdir/"meta.json").write_text(json.dumps(meta,indent=2))
    print(f"trained {ver}: holdout WMAPE {metrics['wmape']:.3f} ({len(tr):,} train / {len(ho):,} holdout)")
    cur=champ()
    if cur is None:
        CHAMP.write_text(json.dumps(meta,indent=2)); print(f"-> no champion existed. PROMOTED {ver}.")
    else:
        gain=1-metrics["wmape"]/cur["wmape"]
        print(f"champion {cur['version']} WMAPE {cur['wmape']:.3f} | challenger {metrics['wmape']:.3f} | gain {gain*100:+.1f}%")
        if gain>=MIN_GAIN:
            CHAMP.write_text(json.dumps(meta,indent=2)); print(f"-> PROMOTED {ver} (gain >= {MIN_GAIN*100:.0f}%).")
        else:
            print(f"-> kept champion {cur['version']} (challenger gain < {MIN_GAIN*100:.0f}%). {ver} stays challenger.")
    _log_run("retrain",meta)

# ---------- predict (nightly) ----------
def cmd_predict(date):
    cur=champ()
    if cur is None: sys.exit("no champion. run: python3 src/pipeline.py retrain")
    F,C=cur["feats"],cur["cats"]
    df=load_df()
    day=df[df.date==pd.Timestamp(date)]
    if day.empty: sys.exit(f"no feature rows for {date} (range {df.date.min().date()}..{df.date.max().date()})")
    X=day[F].copy()
    for c in C: X[c]=X[c].astype("category")
    vdir=REG/cur["version"]; out=day[["date","BranchId","ProductId","y"]].copy()
    for q,name in QS:
        b=lgb.Booster(model_file=str(vdir/f"lgbm_{name}.txt"))
        out[name]=np.clip(b.predict(X),0,None)
    # newsvendor order via per-product econ (reuse order_qty logic)
    from order_qty import econ_table, q_at
    e=econ_table(out.rename(columns={}).assign(ListPrice=day.ListPrice.values))
    out=out.merge(e,on="ProductId",how="left")
    out["order_qty"]=q_at(out.CR.values,out.p50.values,out.p85.values,out.p95.values)
    op=PRED/f"order_plan_{date}.parquet"; out.to_parquet(op)
    print(f"champion {cur['version']} | {date}: {len(out):,} (branch×product) "
          f"-> {out.order_qty.sum():,.0f} units ordered. wrote {op.name}")
    print(f"realised demand that day: {out.y.sum():,.0f} | forecast P50 sum {out.p50.sum():,.0f}")
    _log_run("predict",{"date":date,"version":cur["version"],"order_units":float(out.order_qty.sum())})

# ---------- monitor (drift) ----------
def psi(ref,cur,bins=10):
    ref,cur=np.asarray(ref,float),np.asarray(cur,float)
    ref=ref[~np.isnan(ref)]; cur=cur[~np.isnan(cur)]
    if len(ref)<50 or len(cur)<50: return np.nan
    qs=np.unique(np.quantile(ref,np.linspace(0,1,bins+1)))
    if len(qs)<3: return np.nan
    r,_=np.histogram(ref,qs); c,_=np.histogram(cur,qs)
    r=r/max(r.sum(),1)+1e-6; c=c/max(c.sum(),1)+1e-6
    return float(((c-r)*np.log(c/r)).sum())

def cmd_monitor(ref_cutoff):
    cur=champ()
    F=cur["feats"] if cur else feats()[0]
    df=load_df()
    cut=pd.Timestamp(ref_cutoff) if ref_cutoff else df.date.max().normalize()-pd.Timedelta(days=30)
    ref=df[df.date<cut]; rec=df[df.date>=cut]
    watch=["y","lag_7","rmean_28","rstd_28","ListPrice","tmax_c","rain_mm","promo_active","dow"]
    watch=[w for w in watch if w in df]
    L=["# CFC Drift Monitor (Phase 8)\n",
       f"Reference < {cut.date()} ({len(ref):,} rows) vs recent >= {cut.date()} ({len(rec):,} rows).\n",
       "## Data drift — PSI per feature\n| feature | PSI | status |","|---|---|---|"]
    drift_flag=False
    for w in watch:
        p=psi(ref[w],rec[w])
        st="ok" if (np.isnan(p) or p<PSI_WARN) else "DRIFT"
        if st=="DRIFT": drift_flag=True
        L.append(f"| {w} | {p:.3f} | {st} |" if not np.isnan(p) else f"| {w} | n/a | n/a |")
    # accuracy drift: score champion on recent vs its holdout wmape
    acc_flag=False
    if cur:
        vdir=REG/cur["version"]; b=lgb.Booster(model_file=str(vdir/"lgbm_p50.txt"))
        C=cur["cats"]; X=rec[F].copy()
        for c in C: X[c]=X[c].astype("category")
        rw=wmape(rec.y,np.clip(b.predict(X),0,None))
        thr=cur["wmape"]*(1+WMAPE_WARN)
        acc_flag=rw>thr
        L.append("\n## Accuracy drift — champion WMAPE\n")
        L.append(f"- champion holdout WMAPE (train time): {cur['wmape']:.3f}")
        L.append(f"- recent-window WMAPE (now): {rw:.3f}  (warn threshold {thr:.3f})")
        L.append(f"- status: {'DRIFT — retrain' if acc_flag else 'ok'}")
    verdict="RETRAIN RECOMMENDED" if (drift_flag or acc_flag) else "stable — no action"
    L.append(f"\n## Verdict: **{verdict}**")
    L.append(f"(data drift={'yes' if drift_flag else 'no'}, accuracy drift={'yes' if acc_flag else 'no'})")
    (REP/"drift_monitor.md").write_text("\n".join(L))
    print("\n".join(L)); print("\nwrote reports/drift_monitor.md")
    _log_run("monitor",{"drift":drift_flag,"acc_drift":acc_flag,"verdict":verdict,
                        "recent_wmape":float(rw) if cur else None,
                        "champion_wmape":float(cur["wmape"]) if cur else None})

def _log_run(kind,info):
    f=ROOT/"models"/"pipeline_log.jsonl"
    rec={"kind":kind,"ts":dt.datetime.now().isoformat(timespec="seconds"),
         **{k:v for k,v in info.items() if k not in("feats","cats")}}
    with open(f,"a") as fh: fh.write(json.dumps(rec,default=str)+"\n")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd")
    rt=sub.add_parser("retrain"); rt.add_argument("--cutoff",default=None)
    pr=sub.add_parser("predict"); pr.add_argument("--date",required=True)
    mo=sub.add_parser("monitor"); mo.add_argument("--ref-cutoff",default=None)
    a=ap.parse_args()
    if a.cmd=="retrain": cmd_retrain(a.cutoff)
    elif a.cmd=="predict": cmd_predict(a.date)
    elif a.cmd=="monitor": cmd_monitor(a.ref_cutoff)
    else: ap.print_help()
