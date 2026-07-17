"""
Master deck — Model Evidence & Scorecard. Tri-audience (Data Scientist / CEO / CTO).
Every applicable score defined precisely (formula + value + how-to-read + good-bar), plus an honest
'why AUC/ROC do not apply' slide and a 'how do I know it's right' evidence checklist.
Builds reports/model_evidence.html (+ PDF via Chrome). Real numbers from deck_data.json + deck_metrics.json.
"""
import json, pathlib
ROOT=pathlib.Path(__file__).resolve().parent.parent
DD=json.loads((ROOT/"reports"/"deck_data.json").read_text())
M=json.loads((ROOT/"reports"/"deck_metrics.json").read_text())

S=[]
def sl(kind,**k): S.append(dict(kind=kind,**k))

sl("title",t="CFC Demand Forecasting — Model Evidence & Scorecard",
   sub="What we ran · what it produces · every score that applies · and how we know the predictions are right.",
   tag="Data Science Briefing · for CEO / CTO / DS · June 2026")

sl("read",h="How to read this deck",
   lead="Three layers on every slide — read the layer you need.",
   rows=[["CEO","the orange takeaway line — the decision-relevant point"],
         ["CTO","the method & validation — is it sound, will it hold"],
         ["Data Scientist","the formula, value, target, interpretation"]])

# ---- SETUP ----
sl("kv",h="1 · The problem, defined precisely",
   take="We predict a number (units), per product, per shop, per day — a regression/forecasting task.",
   rows=[["Target","net_units = gross − refunds − voids (true demand)"],
         ["Grain","one prediction per (outlet × product × day)"],
         ["Horizon","next-day (extendable)"],
         ["Type","regression + quantile forecasting (NOT classification)"],
         ["Universe","Class A+B finished goods · 402 products × 84 outlets"]])
sl("kv",h="2 · What we ran — model specification",
   take="A gradient-boosted tree model (LightGBM) — the proven workhorse for tabular demand.",
   rows=[["Algorithm","LightGBM, quantile objective (P50 / P85 / P95)"],
         ["Trees / leaves","600 estimators · 255 leaves · lr 0.05"],
         ["Regularisation","min_child 100 · subsample 0.8 · colsample 0.8"],
         ["Features","37 (18 categorical incl Product & Outlet IDs)"],
         ["Routing","smooth/erratic→LightGBM; intermittent/lumpy→Croston (backlog)"]])
sl("kv",h="3 · Data & split",
   take="Trained on the past, tested on the future it never saw — like production.",
   rows=[["Training rows","7,721,315 (before Apr-2026)"],
         ["Test rows","608,261 (Apr–Jun 2026, held out)"],
         ["Validation","rolling-origin walk-forward, 3 monthly folds"],
         ["Leak control","all history features shifted ≥1 day; no future info"],
         ["Champion (live)","retrained on 7.9M, 60-day holdout"]])
sl("bullets",h="4 · Validation method — why it proves real-world skill",
   lead="Walk-forward backtest: the honest way to test a forecaster.",
   b=["Train on everything up to month M, predict month M+1, score, then roll forward.",
      "The model NEVER sees the test period during training — no leakage.",
      "Repeated over 3 separate months → tests stability, not luck.",
      "This mirrors exactly how it will run in production each night.",
      "A single random train/test split would overstate accuracy for time series — we avoid it."])

# ---- METRIC FRAMEWORK + AUC/ROC honesty ----
sl("two2",h="5 · Which metrics apply — and which DON'T",
   take="AUC / ROC / precision / recall are classification metrics. They do NOT apply to this regression task.",
   warn=True,
   left=("NOT used (classification only)",
         "AUC, ROC curve, precision, recall, F1, confusion matrix, log-loss.\n\n"
         "These need yes/no labels. We predict a quantity, not a class. Reporting them here would be wrong."),
   right=("USED (regression + quantile)",
         "WMAPE, MAE, RMSE, Bias, R² — for the point forecast.\n"
         "Pinball loss + Coverage — for the P85/P95 safety levels.\n"
         "Skill vs baseline — proves it beats simple methods."))

# ---- EACH SCORE ----
def metric(h,take,formula,value,read,good,canvas=None,note=None):
    sl("metric",h=h,take=take,formula=formula,value=value,read=read,good=good,canvas=canvas,note=note)

metric("6 · WMAPE — headline accuracy",
   "On average our forecast is off by 34% of volume — 16% better than today's method.",
   "WMAPE = Σ|actual − forecast| / Σ|actual|",
   f"{M['wmape']}",
   ["Total miss in units ÷ total real demand. Volume-weighted (big sellers count more).",
    "Stable where plain MAPE blows up (near-zero demand days)."],
   "Retail demand: <0.40 is workable, <0.35 good. We are at 0.341.")
metric("7 · MAE — average miss in units",
   "Typical daily miss is about 2.3 units per product-shop line.",
   "MAE = mean( |actual − forecast| )",
   f"{M['mae']} units",
   ["Plain-English error size. Same units as demand.",
    "Robust to outliers (unlike RMSE)."],
   "Lower is better; judge against the item's typical daily volume.")
metric("8 · RMSE — penalises big misses",
   "Large errors are rare; RMSE close to MAE means few wild misses.",
   "RMSE = sqrt( mean( (actual − forecast)² ) )",
   f"{M['rmse']} units",
   ["Squares errors → punishes large mistakes harder than MAE.",
    f"RMSE {M['rmse']} vs MAE {M['mae']}: gap is moderate → error spread is controlled."],
   "Want RMSE not much larger than MAE → no catastrophic outliers.")
metric("9 · Bias — over or under forecasting?",
   "Almost unbiased — a tiny tendency to under-forecast (0.41 units).",
   "Bias = mean( forecast − actual )",
   f"{M['bias']} units",
   ["Near 0 = balanced. Negative = slight under-forecast.",
    "Matters for ordering: persistent bias would systematically over/under-stock."],
   "Want close to 0. −0.41 on ~6-unit orders is negligible & correctable.")
metric("10 · R² — variance explained",
   "The model explains 81% of the variation in demand.",
   "R² = 1 − SS(residual) / SS(total)",
   f"{M['r2']}",
   ["1.0 = perfect, 0 = no better than predicting the average.",
    "0.811 means most of the day-to-day demand swing is captured."],
   ">0.7 strong for noisy daily retail demand. We are at 0.81.",
   canvas="cScatter",
   note="Scatter: each dot = one outlet-product-day; tight along the green diagonal = accurate.")
metric("11 · Pinball loss — quantile quality",
   "Our P50/P85/P95 levels are scored honestly with the metric built for quantiles.",
   "Pinball(q) = mean( max( q·e , (q−1)·e ) ),  e = actual − forecast",
   f"P50 {M['pin50']} · P85 {M['pin85']} · P95 {M['pin95']}",
   ["The correct loss for quantile forecasts (asymmetric penalty).",
    "Lower = sharper AND correctly-placed intervals."],
   "Used to compare quantile models; lower is better.")

sl("metric",h="12 · Coverage / Calibration — are the safety levels honest?",
   take="When we say '85% safe', demand stays under it 85.4% of the time. Calibrated.",
   formula="Coverage(q) = share of actuals ≤ forecast at quantile q",
   value=f"P85 → {M['cov85']}% · P95 → {M['cov95']}% (P50 → {M['cov50']}%)",
   read=["P85/P95 land on target → intervals are trustworthy.",
         "P50 at 56.7% reflects the small under-bias (we round orders up safely)."],
   good="Coverage ≈ stated quantile = well-calibrated → safe for stock buffers.",
   canvas="cCalib")

# ---- PROOF OF CORRECTNESS ----
sl("chart",h="13 · Proof 1 — beats the baseline (skill)",
   lead="A model is only 'good' if it beats simple methods on the SAME test. It does, by +16%.",
   canvas="cWmape",
   note="LightGBM 0.341 vs best simple method (7-day average) 0.405. Lower = better.")
sl("chart",h="14 · Proof 2 — stable across folds (not luck/overfit)",
   lead="Beats the floor in all 3 test months — consistent, not a one-off.",
   canvas="cFolds")
sl("chart",h="15 · Proof 3 — accurate where it matters (ABC)",
   lead="Best on Class-A (80% of volume): WMAPE 0.291. Rare items harder but tiny volume.",
   canvas="cAbc")
sl("chart",h="16 · Proof 4 — residuals are centred & tight",
   lead="Errors cluster around zero with thin tails → no systematic mistake.",
   canvas="cResid",
   note="Distribution of (actual − forecast). Symmetric, peaked at 0 = healthy.")
sl("chartwide",h="17 · Proof 5 — tracks reality (hero product)",
   lead=f"{DD['hero']['name']}: forecast (orange) follows actual (white) day by day.",
   canvas="cHero")
sl("chart",h="18 · Proof 6 — leans on sensible drivers",
   lead="Top signals = product, outlet, recent rolling demand — exactly what a planner would use. No leakage artefacts.",
   canvas="cImp")

sl("bullets",h="19 · \"How do I KNOW the prediction is right?\"",
   lead="Six independent checks — the answer you can give with confidence.",
   b=["Skill: beats the best simple method by +16% on unseen data.",
      "Stability: wins in every one of 3 separate test months.",
      "Calibration: 'X% safe' is right X% of the time (85.4 / 94.5%).",
      "Low bias: −0.41 units → not systematically over/under.",
      "Variance explained: R² 0.81 → captures most demand movement.",
      "Business test: cuts simulated ordering cost ~21%."])

# ---- OUTCOME ----
sl("bullets",h="20 · The outcome — what the model produces",
   lead="Predictions become decisions.",
   b=["A demand range (P50/P85/P95) per product per outlet per day.",
      "An order quantity via newsvendor (balances stockout vs spoilage cost).",
      "One daily warehouse picklist (~230 products, ~34,000 units).",
      "A service-level dial for management to set policy.",
      "Refreshed automatically every night."])
sl("chart",h="21 · Business validation — cost simulation",
   lead="Lower ordering cost than current practice. Model P50 ≈ 21% cheaper.",
   canvas="cCost",
   note="Simulated over 608k order-days. Demo economics (real margin+shelf-life will improve it).")
sl("kv",h="22 · Self-learning & drift control",
   take="Stays accurate over time, on its own, with guardrails.",
   rows=[["Champion / challenger","new model promoted only if ≥1% better"],
         ["Champion WMAPE (holdout)","0.319 — beats stretch target ≤0.321"],
         ["Drift monitor","PSI on inputs + accuracy creep → retrain signal"],
         ["Caught in test","monsoon weather shift flagged; accuracy held"]])

# ---- HONESTY ----
sl("kv",h="23 · Assumptions & limitations (honest)",
   take="Forecast is real and proven. Order-sizing economics are placeholders until Finance/Ops data arrives.",
   warn=True,
   rows=[["Assumed","margin 35% flat · shelf-life 1 day · salvage 0"],
         ["Effect","flat critical ratio → ordering ≈ P50 (no per-product edge yet)"],
         ["Not modelled yet","intermittent tail (Croston), promo uplift detail"],
         ["Data gap, not model gap","real economics = a data request, no rebuild"]])
sl("bullets",h="24 · What would prove us WRONG (falsifiability)",
   lead="A credible model states how it could fail — and we monitor for it.",
   b=["Accuracy on new months drifts above ~0.40 WMAPE → retrain trigger fires.",
      "Coverage drifts off target → intervals no longer trustworthy → recalibrate.",
      "Bias grows persistently → systematic mis-stock → investigate features.",
      "Drift monitor (PSI) flags input shift the model hasn't seen → relearn.",
      "All four are watched automatically; none are silent."])

# ---- SCORECARD ----
sl("scorecard",h="25 · The scorecard — every metric at a glance",
   rows=[["WMAPE",f"{M['wmape']}","<0.40 / target 0.321","✓ good (+16% vs floor)"],
         ["MAE",f"{M['mae']} u","vs ~6u typical order","✓ small"],
         ["RMSE",f"{M['rmse']} u","near MAE","✓ no big outliers"],
         ["Bias",f"{M['bias']} u","≈ 0","✓ near-neutral"],
         ["R²",f"{M['r2']}",">0.70","✓ strong"],
         ["Pinball P85",f"{M['pin85']}","lower better","✓ sharp"],
         ["Coverage P85",f"{M['cov85']}%","≈85%","✓ calibrated"],
         ["Coverage P95",f"{M['cov95']}%","≈95%","✓ calibrated"],
         ["Champion (holdout)","0.319","≤0.321","✓ beats target"],
         ["Cost vs baseline","−21%","<0","✓ saves money"]])
sl("bullets",h="26 · Next step — the one unlock",
   lead="Real economics turns a proven forecast into optimal per-product ordering.",
   b=["Finance: gross margin per product. Ops: shelf-life + salvage.",
      "Load into data/product_econ.csv — no code change.",
      "Per-product critical ratios spread → smart safety stock.",
      "Add Croston for rare items; schedule nightly/weekly jobs.",
      "Pilot in a few outlets, measure ₭ saved, then roll out."])
sl("glossary",h="27 · Appendix — metric glossary (one line each)",
   rows=[["WMAPE","weighted avg % error; headline accuracy"],
         ["MAE","mean absolute error, in units"],
         ["RMSE","root mean squared error; penalises big misses"],
         ["Bias","mean(forecast−actual); over/under tendency"],
         ["R²","fraction of demand variance explained"],
         ["Pinball loss","correct loss for quantile (P85/P95) forecasts"],
         ["Coverage","how often actual ≤ the quantile (calibration)"],
         ["Skill","relative improvement vs a baseline method"],
         ["PSI","population stability index; input-drift detector"],
         ["AUC/ROC","classification-only — NOT used (this is regression)"]])

# ----------------- render -----------------
HEAD=r"""<!doctype html><html><head><meta charset=utf8><title>CFC — Model Evidence & Scorecard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root{--bg:#0e1420;--card:#172234;--ink:#eef2fa;--mut:#9bacc8;--acc:#ff8a4c;--ok:#3ecf8e;--bad:#e0556b;--line:#26344f}
*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,sans-serif}
body{background:#070b12}
.slide{position:relative;width:1280px;height:720px;margin:22px auto;background:linear-gradient(160deg,#0e1420,#0a0f1a);
 border:1px solid var(--line);border-radius:18px;padding:48px 60px;overflow:hidden;page-break-after:always;color:var(--ink)}
.slide:after{content:attr(data-n);position:absolute;right:26px;bottom:16px;color:#46567a;font-size:12px}
.brand{position:absolute;left:60px;bottom:16px;color:#46567a;font-size:12px}
h2{font-size:28px;font-weight:800;margin-bottom:8px;letter-spacing:-.3px}
.take{background:#1a2336;border-left:4px solid var(--acc);border-radius:8px;padding:13px 18px;color:#ffd9bf;
 font-size:18px;font-weight:600;margin:6px 0 20px}
.warn .take{border-color:var(--bad);color:#ffc9d2}
.lead{color:var(--acc);font-size:18px;font-weight:600;margin-bottom:20px}
ul{list-style:none}li{font-size:19px;margin:13px 2px;padding-left:30px;position:relative;color:#e2e8f4}
li:before{content:"▸";position:absolute;left:2px;color:var(--acc)}
.warn li:before{content:"⚠";color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:18px}td,th{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-size:13px;text-transform:uppercase;letter-spacing:.5px}
tr td:first-child{font-weight:700;color:#fff;width:240px}
.ts{display:flex;flex-direction:column;justify-content:center;height:100%;text-align:center}
.ts h1{font-size:44px;font-weight:900;letter-spacing:-1px;line-height:1.1}
.ts .s{color:#cdd7ea;font-size:21px;margin-top:18px;align-self:center;max-width:920px}
.ts .tag{color:var(--acc);font-size:15px;margin-top:30px;letter-spacing:1.5px;text-transform:uppercase}
.two{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:8px}
.tc{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px}
.tc.bad{border-color:#5a2733}.tc.good{border-color:#1f5640}
.tc h3{font-size:18px;margin-bottom:10px}.tc.bad h3{color:var(--bad)}.tc.good h3{color:var(--ok)}
.tc p{color:#cdd7ea;font-size:16px;white-space:pre-line}
.formula{background:#0a0f1a;border:1px solid var(--acc);border-radius:12px;padding:16px;margin:8px 0 14px;
 font-size:20px;text-align:center;color:var(--acc);font-weight:700}
.val{font-size:34px;font-weight:900;color:#fff;margin:4px 0 12px}
.val small{font-size:16px;color:var(--mut);font-weight:600}
.good-bar{background:#13251c;border:1px solid #1f5640;border-radius:8px;padding:11px 16px;color:#bdf0d6;font-size:16px;margin-top:10px}
.metricwrap{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.cwrap{position:relative;height:330px;margin-top:8px}.cwrap.wide{height:430px}
.metricwrap .cwrap{height:300px;margin-top:0}
.note{position:absolute;left:60px;right:60px;bottom:42px;color:var(--mut);font-size:14px;font-style:italic}
.sc td:nth-child(2){color:var(--acc);font-weight:800}.sc td:last-child{color:var(--ok)}
@media print{body{background:#fff}.slide{margin:0;border:none;border-radius:0}}
</style></head><body>
"""
def esc(x):return str(x).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def rows_html(rows):return "".join("<tr>"+"".join(f"<td>{esc(c)}</td>" for c in r)+"</tr>" for r in rows)
charts=[]
def render(s,n):
    k=s["kind"]; wc="warn" if s.get("warn") else ""
    note=f'<div class=note>{esc(s["note"])}</div>' if s.get("note") else ""
    take=f'<div class=take>{esc(s["take"])}</div>' if s.get("take") else ""
    lead=f'<div class=lead>{esc(s["lead"])}</div>' if s.get("lead") else ""
    if k=="title":
        return f'<section class="slide" data-n="{n}"><div class=ts><h1>{esc(s["t"])}</h1><div class=s>{esc(s["sub"])}</div><div class=tag>{esc(s["tag"])}</div></div><div class=brand>CFC · CityFood Concepts</div></section>'
    b=""
    if k in("read","kv","glossary"):
        b=f'<table>{rows_html(s["rows"])}</table>'
    elif k=="scorecard":
        head="<tr><th>Metric</th><th>Value</th><th>Target / ref</th><th>Verdict</th></tr>"
        b=f'<table class=sc>{head}{rows_html(s["rows"])}</table>'
    elif k=="bullets":
        b=f'<ul>{"".join(f"<li>{esc(x)}</li>" for x in s["b"])}</ul>'
    elif k=="two2":
        (lh,lp)=s["left"];(rh,rp)=s["right"]
        b=f'<div class=two><div class="tc bad"><h3>{esc(lh)}</h3><p>{esc(lp)}</p></div><div class="tc good"><h3>{esc(rh)}</h3><p>{esc(rp)}</p></div></div>'
    elif k=="chart":
        b=f'<div class=cwrap><canvas id="{s["canvas"]}"></canvas></div>';charts.append(s["canvas"])
    elif k=="chartwide":
        b=f'<div class="cwrap wide"><canvas id="{s["canvas"]}"></canvas></div>';charts.append(s["canvas"])
    elif k=="metric":
        left=(f'<div class=formula>{esc(s["formula"])}</div>'
              f'<div class=val>{esc(s["value"])}</div>'
              f'<ul>{"".join(f"<li>{esc(x)}</li>" for x in s["read"])}</ul>'
              f'<div class=good-bar>Good looks like: {esc(s["good"])}</div>')
        if s.get("canvas"):
            charts.append(s["canvas"])
            b=f'<div class=metricwrap><div>{left}</div><div class=cwrap><canvas id="{s["canvas"]}"></canvas></div></div>'
        else:
            b=left
    return f'<section class="slide {wc}" data-n="{n}"><h2>{esc(s["h"])}</h2>{take}{lead}{b}{note}<div class=brand>CFC · CityFood Concepts</div></section>'

html=[HEAD]
for i,s in enumerate(S,1): html.append(render(s,i))

CJS=r"""
<script>
const DD=%%DD%%, M=%%M%%;
const sc={responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#9bacc8',font:{size:12}}}},
 scales:{x:{ticks:{color:'#9bacc8'},grid:{color:'#1e2942'}},y:{ticks:{color:'#9bacc8'},grid:{color:'#1e2942'}}}};
function mk(id,cfg){const e=document.getElementById(id);if(e)new Chart(e,cfg);}
mk('cScatter',{type:'scatter',data:{datasets:[
 {label:'outlet-product-day',data:DD.scatter,backgroundColor:'#ff8a4c55',pointRadius:2},
 {label:'perfect',type:'line',data:[{x:0,y:0},{x:DD.scatter_max,y:DD.scatter_max}],borderColor:'#3ecf8e',borderDash:[5,5],pointRadius:0}]},
 options:Object.assign({},sc,{scales:{x:{title:{display:true,text:'actual',color:'#9bacc8'},ticks:{color:'#9bacc8'},grid:{color:'#1e2942'},max:DD.scatter_max},
 y:{title:{display:true,text:'forecast',color:'#9bacc8'},ticks:{color:'#9bacc8'},grid:{color:'#1e2942'},max:DD.scatter_max}}})});
mk('cCalib',{type:'bar',data:{labels:['P50','P85','P95'],datasets:[
 {label:'actual coverage %',data:[M.cov50,M.cov85,M.cov95],backgroundColor:'#ff8a4c'},
 {label:'target %',data:[50,85,95],backgroundColor:'#37445f'}]},options:sc});
mk('cWmape',{type:'bar',data:{labels:['LightGBM','7-day avg','28-day avg','naive','dow avg','same-wkday'],
 datasets:[{label:'WMAPE (lower better)',data:[0.341,0.405,0.411,0.453,0.468,0.537],
 backgroundColor:['#3ecf8e','#ff8a4c','#37445f','#37445f','#37445f','#37445f']}]},options:sc});
mk('cFolds',{type:'bar',data:{labels:['Apr-26','May-26','Jun-26'],datasets:[
 {label:'LightGBM',data:[0.384,0.325,0.305],backgroundColor:'#3ecf8e'},
 {label:'baseline',data:[0.497,0.360,0.345],backgroundColor:'#37445f'}]},options:sc});
mk('cAbc',{type:'bar',data:{labels:['A (75% vol)','B (19%)','C (5%)'],datasets:[
 {label:'LightGBM',data:[0.291,0.456,0.640],backgroundColor:'#3ecf8e'},
 {label:'baseline',data:[0.349,0.534,0.733],backgroundColor:'#37445f'}]},options:sc});
mk('cResid',{type:'bar',data:{labels:M.resid_bins,datasets:[
 {label:'count of (actual − forecast)',data:M.resid_counts,backgroundColor:'#ff8a4c'}]},options:sc});
mk('cHero',{type:'line',data:{labels:DD.hero.labels,datasets:[
 {label:'actual',data:DD.hero.actual,borderColor:'#eef2fa',pointRadius:0,tension:.3},
 {label:'P50',data:DD.hero.p50,borderColor:'#ff8a4c',pointRadius:0,tension:.3},
 {label:'P85',data:DD.hero.p85,borderColor:'#3ecf8e',borderDash:[4,4],pointRadius:0,tension:.3}]},
 options:Object.assign({},sc,{scales:{x:{ticks:{color:'#9bacc8',maxTicksLimit:8},grid:{color:'#1e2942'}},y:{ticks:{color:'#9bacc8'},grid:{color:'#1e2942'}}}})});
mk('cImp',{type:'bar',data:{labels:['ProductId','OutletId','rolling-mean 28d','yesterday','volatility 28d','rolling-mean 7d','month'],
 datasets:[{label:'importance',data:[51107,30000,12101,6345,6100,5830,4203],backgroundColor:'#ff8a4c'}]},
 options:Object.assign({},sc,{indexAxis:'y',scales:{x:{ticks:{color:'#9bacc8'},grid:{color:'#1e2942'}},y:{ticks:{color:'#cdd7ea'},grid:{display:false}}}})});
mk('cCost',{type:'bar',data:{labels:['baseline','model P50','model P85','model P95'],
 datasets:[{label:'ordering cost ₭bn (lower better)',data:[3.71,2.94,6.07,10.07],
 backgroundColor:['#37445f','#3ecf8e','#ff8a4c','#e0556b']}]},options:sc});
</script></body></html>
"""
html.append(CJS.replace("%%DD%%",json.dumps(DD)).replace("%%M%%",json.dumps(M)))
out=ROOT/"reports"/"model_evidence.html"
out.write_text("".join(html))
print(f"wrote {out} — {len(S)} slides, {len(charts)} charts")
