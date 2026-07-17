"""Compute all real numbers/series for the management deck → reports/deck_data.json."""
import json, pathlib
import numpy as np, pandas as pd
ROOT=pathlib.Path(__file__).resolve().parent.parent
PRED=ROOT/"data"/"predictions"; RAW=ROOT/"data"/"raw"
def wmape(y,yh): y,yh=np.asarray(y,float),np.asarray(yh,float); return float(np.abs(y-yh).sum()/max(np.abs(y).sum(),1e-9))

bt=pd.read_parquet(PRED/"backtest_preds.parquet")
dp=pd.read_parquet(RAW/"dim_product.parquet")[["ProductId","ProductName","CatLvl2_Name","CatLvl3_Name","ListPrice"]]
dp.columns=["ProductId","pname","cat2","cat3","price"]
bt=bt.merge(dp,on="ProductId",how="left")

D={}
# monthly demand whole history
panel=pd.read_parquet(RAW/"demand_panel.parquet",columns=["DayKey","net_units"])
panel["m"]=panel.DayKey.astype(str).str.slice(0,6)
mo=panel.groupby("m").net_units.sum().reset_index()
mo=mo[mo.m>="202301"]
D["monthly"]={"labels":mo.m.tolist(),"units":mo.net_units.round().tolist()}

# forecast vs actual daily (test window)
daily=bt.groupby(bt.date.dt.strftime("%Y-%m-%d")).agg(a=("y","sum"),p50=("p50","sum"),p85=("p85","sum")).reset_index()
D["fva"]={"labels":daily.date.tolist(),"actual":daily.a.round().tolist(),"p50":daily.p50.round().tolist(),"p85":daily.p85.round().tolist()}

# accuracy by real category (cat2) — top by volume
cat=bt.groupby("cat2").apply(lambda s:pd.Series({"vol":s.y.sum(),"wmape":wmape(s.y,s.p50),"floor":wmape(s.y,s.rmean_7),"n":s.ProductId.nunique()})).reset_index()
cat=cat.sort_values("vol",ascending=False).head(10)
D["bycat"]=[{"cat":str(r.cat2)[:24],"wmape":round(r.wmape,3),"floor":round(r.floor,3),"vol":int(r.vol),"n":int(r.n)} for r in cat.itertuples()]

# top SKUs by volume + their accuracy
sku=bt.groupby(["ProductId","pname"]).apply(lambda s:pd.Series({"vol":s.y.sum(),"wmape":wmape(s.y,s.p50)})).reset_index()
sku=sku.sort_values("vol",ascending=False).head(15)
D["bysku"]=[{"name":str(r.pname)[:30],"vol":int(r.vol),"wmape":round(r.wmape,3)} for r in sku.itertuples()]

# one hero SKU: predicted vs actual daily (top product, summed across branches)
top_pid=int(sku.iloc[0].ProductId)
h=bt[bt.ProductId==top_pid].groupby(bt.date.dt.strftime("%Y-%m-%d")).agg(a=("y","sum"),p50=("p50","sum"),p85=("p85","sum")).reset_index()
D["hero"]={"name":str(sku.iloc[0].pname),"labels":h.date.tolist(),"actual":h.a.round().tolist(),"p50":h.p50.round().tolist(),"p85":h.p85.round().tolist()}

# scatter pred vs actual (sample 1500 rows)
samp=bt.sample(min(1500,len(bt)),random_state=1)
D["scatter"]=[{"x":float(round(a,1)),"y":float(round(p,1))} for a,p in zip(samp.y,samp.p50)]
D["scatter_max"]=float(np.percentile(bt.y,99))

# train/test sizes
D["split"]={"train":7721315,"test":608261,"champ_train":7901044,"champ_holdout":428532}
json.dump(D,open(ROOT/"reports"/"deck_data.json","w"))
print("wrote reports/deck_data.json | cats",len(D["bycat"]),"skus",len(D["bysku"]),"hero",D["hero"]["name"],"monthly",len(D["monthly"]["labels"]))
