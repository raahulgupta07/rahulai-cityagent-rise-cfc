"""
Phase 9 — Dashboard & handoff.
Builds a single self-contained reports/dashboard.html (Chart.js via CDN) from the pipeline outputs:
KPI cards, forecast-vs-actual trend, accuracy by ABC, service-vs-waste curve, top picklist, drift status.
All numbers computed live from parquet/reports — no hardcoding.
Run: python3 src/dashboard.py
"""
import json, pathlib
import numpy as np, pandas as pd

ROOT=pathlib.Path(__file__).resolve().parent.parent
PRED=ROOT/"data"/"predictions"; REP=ROOT/"reports"

def wmape(y,yh): y,yh=np.asarray(y),np.asarray(yh); return float(np.abs(y-yh).sum()/max(np.abs(y).sum(),1e-9))

bt=pd.read_parquet(PRED/"backtest_preds.parquet")
op=pd.read_parquet(PRED/"order_plan.parquet")
champ=json.loads((ROOT/"models"/"champion.json").read_text()) if (ROOT/"models"/"champion.json").exists() else {}

# ---- KPIs ----
floor=wmape(bt.y,bt.rmean_7); lg=wmape(bt.y,bt.p50)
kpi=dict(
  lgbm_wmape=round(lg,3), floor_wmape=round(floor,3), improve=round((1-lg/floor)*100),
  champ_wmape=round(champ.get("wmape",float("nan")),3), champ_ver=champ.get("version","-"),
  cover85=round((bt.y<=bt.p85).mean()*100,1), cover95=round((bt.y<=bt.p95).mean()*100,1),
  rows=int(len(bt)), products=int(bt.ProductId.nunique()), branches=int(bt.BranchId.nunique()),
)

# ---- forecast vs actual (daily aggregate) ----
daily=bt.groupby(bt.date.dt.strftime("%Y-%m-%d")).agg(actual=("y","sum"),p50=("p50","sum"),p85=("p85","sum")).reset_index()
trend=dict(labels=daily.date.tolist(),
           actual=daily.actual.round().tolist(), p50=daily.p50.round().tolist(), p85=daily.p85.round().tolist())

# ---- accuracy by ABC ----
abc=[]
for c in ["A","B","C"]:
    s=bt[bt.abc==c]; abc.append(dict(cls=c, lgbm=round(wmape(s.y,s.p50),3), floor=round(wmape(s.y,s.rmean_7),3),
                                      vol=round(s.y.sum()/bt.y.sum()*100)))

# ---- service vs waste sweep (recompute) ----
GM=0.35; price=op.price.clip(lower=1).values; Cu=price*GM; Co=price*(1-GM)
def q_at(cr,p50,p85,p95):
    s1=p50*(cr/0.5); s2=p50+(cr-0.5)/0.35*(p85-p50); s3=p85+(cr-0.85)/0.10*(p95-p85)
    return np.clip(np.round(np.select([cr<0.5,cr<0.85,cr<0.95],[s1,s2,s3],default=p95)),0,None)
d=op.y.values; sweep=[]
for cr in [0.30,0.50,0.70,0.85,0.95]:
    o=q_at(np.full(len(op),cr),op.p50.values,op.p85.values,op.p95.values)
    under=np.maximum(d-o,0); over=np.maximum(o-d,0); cost=(Cu*under+Co*over).sum()
    sweep.append(dict(svc=int(cr*100), stockout=round((d>o).mean()*100,1),
                      waste=round(over.sum()/max(o.sum(),1)*100,1),
                      fill=round(np.minimum(o,d).sum()/max(d.sum(),1)*100,1), cost=round(cost/1e9,2)))

# ---- picklist (latest date in order_plan) ----
op["date"]=pd.to_datetime(op.date); last=op.date.max()
dp=pd.read_parquet(ROOT/"data"/"raw"/"dim_product.parquet")[["ProductId","ProductName"]]
day=op[op.date==last]
pl=(day.groupby("ProductId").agg(units=("order_qty","sum"),outlets=("BranchId","nunique")).reset_index()
      .merge(dp,on="ProductId",how="left").sort_values("units",ascending=False).head(15))
pick=dict(date=last.strftime("%Y-%m-%d"),
          rows=[dict(name=str(r.ProductName)[:34],units=int(r.units),outlets=int(r.outlets)) for r in pl.itertuples()],
          total_units=int(day.order_qty.sum()), total_products=int(day.ProductId.nunique()))

# ---- drift (parse monitor report verdict if present) ----
drift_txt=(REP/"drift_monitor.md").read_text() if (REP/"drift_monitor.md").exists() else "not run"
verdict="RETRAIN RECOMMENDED" if "RETRAIN RECOMMENDED" in drift_txt else ("stable" if "stable" in drift_txt else "-")

DATA=dict(kpi=kpi,trend=trend,abc=abc,sweep=sweep,pick=pick,verdict=verdict)

HTML=r"""<!doctype html><html><head><meta charset=utf8><title>CFC Demand Forecasting — Ops Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root{--bg:#0f1117;--card:#1a1d27;--ink:#e8eaf0;--mut:#8b90a0;--acc:#ff8a4c;--ok:#46c98b;--warn:#ffcf5c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px}
h1{font-size:22px;margin:0 0 2px}.sub{color:var(--mut);margin-bottom:22px}
.grid{display:grid;gap:16px}.k{grid-template-columns:repeat(6,1fr)}.two{grid-template-columns:1fr 1fr}
.card{background:var(--card);border:1px solid #262a36;border-radius:14px;padding:16px}
.kc .v{font-size:26px;font-weight:700}.kc .l{color:var(--mut);font-size:12px;margin-top:2px}
.acc{color:var(--acc)}.ok{color:var(--ok)}.warn{color:var(--warn)}
h3{font-size:14px;margin:0 0 12px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:6px 4px;border-bottom:1px solid #262a36}
th{color:var(--mut);font-weight:600}.r{text-align:right}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
.b-warn{background:#3a2f12;color:var(--warn)}.b-ok{background:#16382a;color:var(--ok)}
canvas{max-height:280px}
</style></head><body><div class=wrap>
<h1>CFC Bakery — Demand Forecasting & Ordering</h1>
<div class=sub>CityFood Concepts · forecast → order → warehouse picklist · self-learning loop · <span id=meta></span></div>

<div class="grid k" id=kpis></div>

<div class="grid two" style="margin-top:16px">
 <div class=card><h3>Forecast vs actual (daily, backtest)</h3><canvas id=trend></canvas></div>
 <div class=card><h3>Accuracy by ABC class (WMAPE, lower=better)</h3><canvas id=abc></canvas></div>
</div>

<div class="grid two" style="margin-top:16px">
 <div class=card><h3>Service level vs waste (the dial)</h3><canvas id=sweep></canvas></div>
 <div class=card><h3>Drift monitor</h3><div id=drift></div></div>
</div>

<div class="card" style="margin-top:16px"><h3>Warehouse picklist — <span id=pickdate></span></h3><div id=pick></div></div>
<div class=sub style="margin-top:18px">Demo econ (GM 35%, same-day spoilage). Edit data/product_econ.csv for real margin+shelf-life. See HANDOFF.md.</div>
</div>
<script>
const D=%%DATA%%;
document.getElementById('meta').textContent=D.kpi.rows.toLocaleString()+' test rows · '+D.kpi.products+' products · '+D.kpi.branches+' branches';
const K=[['LGBM WMAPE',D.kpi.lgbm_wmape,'vs floor '+D.kpi.floor_wmape,'acc'],
 ['Improvement','+'+D.kpi.improve+'%','over baseline','ok'],
 ['Champion WMAPE',D.kpi.champ_wmape,D.kpi.champ_ver,'acc'],
 ['P85 coverage',D.kpi.cover85+'%','target 85%','ok'],
 ['P95 coverage',D.kpi.cover95+'%','target 95%','ok'],
 ['Picklist/day',D.pick.total_units.toLocaleString(),D.pick.total_products+' products','acc']];
document.getElementById('kpis').innerHTML=K.map(k=>`<div class="card kc"><div class="v ${k[3]}">${k[1]}</div><div class=l>${k[0]}</div><div class=l>${k[2]}</div></div>`).join('');

new Chart(trend,{type:'line',data:{labels:D.trend.labels,datasets:[
 {label:'actual',data:D.trend.actual,borderColor:'#e8eaf0',pointRadius:0,tension:.3},
 {label:'P50',data:D.trend.p50,borderColor:'#ff8a4c',pointRadius:0,tension:.3},
 {label:'P85',data:D.trend.p85,borderColor:'#46c98b',borderDash:[4,4],pointRadius:0,tension:.3}]},
 options:{plugins:{legend:{labels:{color:'#8b90a0'}}},scales:{x:{ticks:{color:'#8b90a0',maxTicksLimit:8},grid:{color:'#222'}},y:{ticks:{color:'#8b90a0'},grid:{color:'#222'}}}}});

new Chart(abc,{type:'bar',data:{labels:D.abc.map(a=>'Class '+a.cls+' ('+a.vol+'% vol)'),datasets:[
 {label:'LGBM',data:D.abc.map(a=>a.lgbm),backgroundColor:'#ff8a4c'},
 {label:'floor',data:D.abc.map(a=>a.floor),backgroundColor:'#3a3f4d'}]},
 options:{plugins:{legend:{labels:{color:'#8b90a0'}}},scales:{x:{ticks:{color:'#8b90a0'},grid:{display:false}},y:{ticks:{color:'#8b90a0'},grid:{color:'#222'}}}}});

new Chart(sweep,{data:{labels:D.sweep.map(s=>s.svc+'% svc'),datasets:[
 {type:'line',label:'cost ₭B',data:D.sweep.map(s=>s.cost),borderColor:'#ff8a4c',yAxisID:'y',tension:.3},
 {type:'bar',label:'stockout%',data:D.sweep.map(s=>s.stockout),backgroundColor:'#46c98b88',yAxisID:'y1'},
 {type:'bar',label:'waste%',data:D.sweep.map(s=>s.waste),backgroundColor:'#ffcf5c88',yAxisID:'y1'}]},
 options:{plugins:{legend:{labels:{color:'#8b90a0'}}},scales:{x:{ticks:{color:'#8b90a0'},grid:{display:false}},
 y:{position:'left',ticks:{color:'#ff8a4c'},grid:{color:'#222'},title:{display:true,text:'cost ₭B',color:'#ff8a4c'}},
 y1:{position:'right',ticks:{color:'#8b90a0'},grid:{display:false},title:{display:true,text:'%',color:'#8b90a0'}}}}});

const warn=D.verdict.includes('RETRAIN');
document.getElementById('drift').innerHTML=`<span class="badge ${warn?'b-warn':'b-ok'}">${D.verdict}</span>
 <p style="color:#8b90a0;margin-top:12px">PSI on features + champion accuracy creep. Weather (rain/tmax) drifts seasonally (monsoon); the retrain trigger is sustained accuracy drift, not weather alone. Full table: reports/drift_monitor.md</p>`;

document.getElementById('pickdate').textContent=D.pick.date;
document.getElementById('pick').innerHTML='<table><tr><th>Product</th><th class=r>order units</th><th class=r>outlets</th></tr>'+
 D.pick.rows.map(r=>`<tr><td>${r.name}</td><td class=r>${r.units.toLocaleString()}</td><td class=r>${r.outlets}</td></tr>`).join('')+'</table>';
</script></body></html>"""

out=REP/"dashboard.html"
out.write_text(HTML.replace("%%DATA%%", json.dumps(DATA)))
print(f"wrote {out}")
print(f"KPIs: LGBM {kpi['lgbm_wmape']} (+{kpi['improve']}%), champion {kpi['champ_wmape']}, "
      f"picklist {pick['total_units']:,}u/{pick['total_products']}prod on {pick['date']}, drift={verdict}")
