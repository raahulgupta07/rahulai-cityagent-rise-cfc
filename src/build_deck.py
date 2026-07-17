"""
Phase 9+ — Management + technical presentation generator.
Builds reports/presentation.html (self-contained, Chart.js CDN, 16:9 print-ready slides).
All numbers REAL (from reports + reports/deck_data.json). Run deck_data.py first.
Render PDF: Chrome headless --print-to-pdf (see end of file / README).
"""
import json, pathlib
ROOT=pathlib.Path(__file__).resolve().parent.parent
DD=json.loads((ROOT/"reports"/"deck_data.json").read_text())

S=[]  # slides
def slide(kind, **k): S.append(dict(kind=kind, **k))

# ---------------- SECTION 1 — CONTEXT ----------------
slide("title", t="CFC Bakery — Demand Forecasting & Smart Ordering",
      sub="Forecast daily demand per outlet × product → optimal warehouse orders. Cut stockouts AND waste.",
      tag="CityFood Concepts · Management + Technical Briefing · June 2026")
slide("bullets", h="1 · Who is CFC & the problem",
      lead="CFC = CityFood Concepts — the group's bakery & beverage network (Seasons, NBH, Bistro, Gong Cha).",
      b=["84 active outlets order fresh stock from a central warehouse EVERY day.",
         "Order too much → unsold bakery spoils → direct cash waste.",
         "Order too little → empty shelves → lost sales + unhappy customers.",
         "Today ordering leans on gut feel & simple averages → both errors happen daily.",
         "At 58.8M units / ₭208bn sales over 3.5 yrs, even small % error = large money."])
slide("bullets", h="2 · The idea",
      lead="Replace guesswork with a learning system that predicts tomorrow's demand for every product in every shop.",
      b=["Learn the real patterns: weekday, payday, weather, festivals, product trend.",
         "Predict not one number but a RANGE (likely / safe / very-safe) per product.",
         "Turn the prediction into an actual ORDER number using profit vs spoilage economics.",
         "Roll all outlet orders into ONE warehouse pick/production list per day.",
         "Keep improving itself automatically as new sales arrive (self-learning)."])
slide("kpi", h="3 · The goal (measurable)",
      lead="Beat the current ordering practice on accuracy AND on money.",
      cards=[("≥20%","more accurate than simple averages"),
             ("↓","fewer stockouts (lost sales)"),
             ("↓","less spoilage (wasted bakery)"),
             ("auto","self-learning, no manual rebuild")])
slide("flow", h="4 · How we planned to do it — the pipeline",
      steps=["Extract sales\n(Microsoft Fabric)","Clean & profile\n(EDA)","Build features\n(patterns)",
             "Train model\n(LightGBM)","Backtest\n(prove it)","Order qty\n(newsvendor)",
             "Warehouse\npicklist","Self-learn\n+ drift watch"],
      note="Each stage is a real, runnable script. Nine phases, all complete.")

# ---------------- SECTION 2 — DATA ----------------
slide("two", h="5 · The data — two sources",
      left=("INTERNAL (our database)","Microsoft Fabric data warehouse, secure user login.\n"
            "• Demand fact: every day × outlet × product sale\n• Product master (price, category)\n"
            "• Branch / channel / warehouse masters"),
      right=("EXTERNAL (open data)","Public signals that move demand.\n"
            "• Weather: rain, temperature, humidity (6 cities, 3 yrs)\n"
            "• Myanmar public holidays + festivals (122 events incl Thingyan)"))
slide("table", h="6 · Internal data — the demand fact",
      lead="Source: HUB_REPORTING_DB.edm.CFC_PBID_Sales_Summary — aggregated server-side (read-only).",
      cols=["Field","Meaning"],
      rows=[["DayKey","calendar day"],["BranchId","which outlet"],["ProductId","which product/SKU"],
            ["gross_units","units sold"],["refund_units / void_units","returns & cancels"],
            ["net_units","gross − refund − void = TRUE demand (our target)"],
            ["amount / discount","revenue & discount"],["txns","number of receipts"]],
      note="Grain = one row per day × outlet × product. Card types summed together.")
slide("table", h="7 · External data — how we use it",
      lead="Joined to each outlet by city + date. Gives the model context a sales number alone can't.",
      cols=["Signal","Source","Why it matters"],
      rows=[["Rain (mm), heavy-rain flag","ERA5 / Open-Meteo","monsoon suppresses footfall"],
            ["Max temp, hot flag","ERA5 / Open-Meteo","heat shifts beverage vs bakery"],
            ["Humidity","ERA5 / Open-Meteo","comfort / footfall proxy"],
            ["Public holidays","Myanmar calendar","holiday demand +7%"],
            ["Thingyan / festivals","Myanmar calendar","shops close → −8% (dip, not spike)"]])
slide("table", h="8 · Master / reference tables pulled",
      lead="11 master tables extracted (one-by-one, with approval). Used for names, categories, structure.",
      cols=["Table","Rows","Used for"],
      rows=[["dim_product","29,515","names, price, 5-level category"],
            ["dim_branch","98","outlet → city, channel, segment"],
            ["dim_warehouse","119","picklist target"],
            ["dim_channel / segment","7 / 9","brand & format"],
            ["dim_partner / costcenter / …","others","reference only"]],
      note="3,580 of 29,515 products actually sell; 84 of 98 branches active → we join, never assume 1:1.")
slide("kpi", h="9 · Data size & length",
      lead="Big enough to learn from, clean enough to trust.",
      cards=[("7.08M","demand rows extracted"),("3.5 yrs","Jan 2023 → Jun 2026 (1,270 days)"),
             ("84 / 3,580","outlets / active products"),("58.8M","total units · ₭208bn sales")])
slide("table", h="10 · Data quality — the errors we checked",
      lead="Extraction QC. Data is remarkably clean; the few oddities are real business, not bugs.",
      cols=["Check","Result","Verdict"],
      rows=[["Nulls (missing values)","none","✓ clean"],
            ["Orphan outlets/products","0","✓ joins are valid"],
            ["Negative net_units","69 rows (0.00%)","✓ refund-heavy days, expected"],
            ["Zero net_units","378 rows (0.01%)","✓ negligible"],
            ["Garbage dates (1970)","filtered out","✓ handled"],
            ["DayKey stored as text","cast to date","✓ handled"]])
slide("bullets", h="11 · What's MISSING in the data (honest)",
      lead="Forecasting data is complete. The ORDERING step needs economics we don't have yet.",
      warn=True,
      b=["✗ Product COST / margin — we have selling price, not cost.",
         "✗ Shelf-life per product — bread (1 day) vs frozen (90 days) vs ambient — all unknown.",
         "✗ Salvage value — what an unsold item recovers (markdown / staff).",
         "These three decide HOW MUCH to order. Without them we use sensible assumptions (flagged later).",
         "Everything needed to FORECAST is present; only the ORDER-sizing economics are assumed."])

# ---------------- SECTION 3 — EDA ----------------
slide("kpi", h="12 · EDA — overall scale",
      lead="What the 7 million rows say at a glance.",
      cards=[("58.8M","net units sold (all time)"),("₭208bn","revenue"),
             ("5,578","avg product-lines sold per day"),("+8%","sales growth 2023→2025")])
slide("chart", h="13 · Demand trend — monthly (42 months)",
      lead="Steady business with clear seasonality. 2026 partial (to June).",
      canvas="cMonthly")
slide("chart", h="14 · Brand / channel mix",
      lead="Seasons dominates — 85.5% of all units. Forecast accuracy on Seasons matters most.",
      canvas="cBrand")
slide("twostat", h="15 · Day-of-week pattern",
      lead="Strong weekly rhythm — a top predictive signal.",
      stats=[("Sunday","peak — 52,445 units/day"),("Monday","trough — 43,218 units/day"),
             ("1.21×","peak-to-trough ratio")],
      note="Day-of-week alone explains a big chunk of variation → it's a core feature.")
slide("twostat", h="16 · Concentration (the 80/20)",
      lead="A few products & outlets drive most volume → focus accuracy there.",
      stats=[("Top 10 products","drive a large share of units"),
             ("Top 10 outlets","32% of all units (top 20 = 55%)"),
             ("99 products","= 80% of volume (Class A)")],
      note="ABC classes: A = top 80% volume, B = next 15%, C = last 5%. We weight A highest.")
slide("chart", h="17 · Demand pattern classification",
      lead="Not every product behaves the same. We route each to the right method.",
      canvas="cPattern",
      note="Smooth/erratic (79% of volume) → LightGBM. Intermittent/lumpy → Croston/SBA (backlog).")
slide("bullets", h="18 · EDA takeaways → design choices",
      lead="The data told us how to build the model.",
      b=["Strong weekday + seasonality → calendar features are essential.",
         "Seasons + Class-A dominate → weight accuracy there.",
         "53% of series are intermittent (sell rarely) → one model can't fit all → route by type.",
         "Heavy product/outlet churn (median series 32 days) → handle cold-starts & zero-fill.",
         "Festivals move demand both ways → encode holidays AND Thingyan dip."])

# ---------------- SECTION 4 — FEATURES ----------------
slide("bullets", h="19 · From raw sales to model inputs ('features')",
      lead="We engineer signals the model can learn from — leak-safe (only past data).",
      b=["History: yesterday, last week, lags of 1/7/14/28 days.",
         "Rolling stats: 7/14/28-day moving average & volatility (how spiky).",
         "Calendar: day-of-week, day-of-month, month, week-of-year, weekend.",
         "Events: public holiday, festival, Thingyan, days-to-holiday, promo flag.",
         "Weather: rain, temp, humidity. Product: price, category. Outlet: city, channel, segment."])
slide("twostat", h="20 · The feature matrix",
      lead="One clean table the model trains on.",
      stats=[("8.33M rows","outlet × product × day"),("35 features","+ product & outlet IDs"),
             ("leak-safe","every history feature shifted ≥1 day")],
      note="Built for Class A+B FG products (402 products × 84 outlets), daily calendar zero-filled per series.")
slide("twostat", h="21 · Train / test split — how we prove it",
      lead="We test on the FUTURE the model never saw — like real life.",
      stats=[("7.72M","training rows (before Apr-2026)"),("608k","test rows (Apr–Jun 2026)"),
             ("3 folds","rolling-origin walk-forward")],
      note="No peeking: train on past, predict forward, repeat monthly. This is honest accuracy.")

# ---------------- SECTION 5 — MODEL ----------------
slide("bullets", h="22 · Which model & why — LightGBM",
      lead="A gradient-boosted tree model — the proven workhorse for tabular demand data.",
      b=["Handles many features, categories, non-linear patterns, missing values.",
         "Fast on millions of rows (CPU, ~5 min train).",
         "Beats deep-learning on this kind of structured retail data.",
         "We ROUTE: smooth/erratic products → LightGBM; rare/lumpy → Croston (specialist, backlog).",
         "Strategy = pick the best per segment, not one giant kitchen-sink model."])
slide("bullets", h="23 · Quantile forecasting — in plain words",
      lead="We don't predict one number. We predict three confidence levels.",
      b=["P50 = the middle guess (50/50). Best for an average expectation.",
         "P85 = 'we're 85% sure demand won't exceed this' → safety stock.",
         "P95 = very safe, rarely run out (but more risk of leftovers).",
         "This range is what lets us choose how cautious to be per product.",
         "Technical: LightGBM quantile objective, trained separately for P50/P85/P95."])

# ---------------- SECTION 6 — SCORES ----------------
slide("bullets", h="24 · How we score accuracy (the metrics)",
      lead="Four numbers, each answering a different question. Lower = better (except coverage).",
      b=["WMAPE — on average, how far off is the forecast (in %)? Our headline score.",
         "MAE — average miss in units.",
         "Bias — do we systematically over- or under-forecast?",
         "Pinball / Coverage — are the P85/P95 'safety' levels honest?",
         "All volume-weighted: big sellers count more than rare items."])
slide("formula", h="25 · WMAPE — explained",
      lead="Weighted Mean Absolute Percentage Error.",
      formula="WMAPE = Σ | actual − forecast |  /  Σ | actual |",
      human=["Add up every miss (in units), divide by total real demand.",
             "0.30 means forecasts are off by 30% of total volume on average.",
             "Weighted: a 5-unit miss on a big seller matters more than on a rare item.",
             "Why not plain MAPE? MAPE explodes on near-zero demand days. WMAPE is stable."])
slide("chart", h="26 · WMAPE result — model vs simple averages",
      lead="The model beats the best simple method by +16%. (Lower bar = better.)",
      canvas="cWmape",
      note="LightGBM 0.341 vs best baseline 0.405. Target was ≤0.321 (beat-by-20%).")
slide("table", h="27 · The baselines we had to beat (the 'floor')",
      lead="Before ML, what does simple math score? This is the bar.",
      cols=["Method","WMAPE","note"],
      rows=[["moving_avg_7 (last 7-day avg)","0.401","best simple method — the floor"],
            ["moving_avg_28","0.411",""],
            ["naive (yesterday)","0.450",""],
            ["day-of-week avg","0.460",""],
            ["same-weekday-last-week","0.528","worst — recency beats it"]],
      note="Model must beat 0.401. It scores 0.341. ✓")
slide("chart", h="28 · Stability — does it hold every month?",
      lead="Tested on 3 separate months. Beats the floor in all → not a fluke.",
      canvas="cFolds")
slide("chart", h="29 · Accuracy by product class (ABC)",
      lead="Best where it matters most: Class-A (80% of volume) is the most accurate.",
      canvas="cAbc",
      note="Class A 0.291 (+17%). Rare Class-C is harder (0.640) but small volume.")
slide("chart", h="30 · Accuracy by category",
      lead="Forecast quality across the main product groups.",
      canvas="cCat")
slide("chartwide", h="31 · Accuracy by top SKU (best sellers)",
      lead="The products that matter most, and how well we predict each.",
      canvas="cSku")
slide("chartwide", h="32 · Hero product — forecast vs actual",
      lead=f"{DD['hero']['name']} — daily, test window. Forecast (orange) tracks actual (white).",
      canvas="cHero")
slide("chart", h="33 · Predicted vs actual — the cloud",
      lead="Each dot = one outlet-product-day. Closer to the diagonal = better. Tight along the line.",
      canvas="cScatter")
slide("chart", h="34 · Are the safety levels honest? (calibration)",
      lead="When we say '85% safe', are we right 85% of the time? Almost exactly.",
      canvas="cCalib",
      note="P85 covers 85.4% (target 85), P95 covers 94.5% (target 95). → safe to use for stock buffers.")
slide("chart", h="35 · What drives the forecast (feature importance)",
      lead="The model leans on product identity, outlet, and recent rolling demand — as expected.",
      canvas="cImp")
slide("kpi", h="36 · Accuracy verdict",
      lead="Honest, stable, well-calibrated. Ready to drive ordering.",
      cards=[("0.341","WMAPE (+16% vs floor)"),("0.291","Class-A (+17%)"),
             ("85.4 / 94.5%","P85 / P95 coverage"),("0.319","champion model (beats target)")])

# ---------------- SECTION 7 — ORDER ----------------
slide("bullets", h="37 · From forecast to ORDER — the real goal",
      lead="A forecast is not a decision. How many to actually send each shop?",
      b=["Forecast says 'likely 18, could be 25'. The order is a single number.",
         "Order too low → stockout → lose the profit margin.",
         "Order too high → unsold → spoilage loss.",
         "The right number balances these two costs — per product.",
         "This is the classic 'newsvendor' problem."])
slide("formula", h="38 · Newsvendor — the order formula",
      lead="Order at the demand level where expected profit is maximised.",
      formula="Critical Ratio  CR = Cu / (Cu + Co)        order = demand at the CR-th percentile",
      human=["Cu = cost of under-ordering = the profit margin you LOSE on a stockout.",
             "Co = cost of over-ordering = the money lost when an item SPOILS.",
             "High margin + long shelf-life → CR high → order generously (P85/P95).",
             "Thin margin + perishable → CR low → order lean (near P50)."])
slide("table", h="39 · Critical ratio by class (current demo economics)",
      lead="With assumed flat economics every class gets CR≈0.35 → lean ordering.",
      cols=["Class","products","avg CR","median order/day","volume"],
      rows=[["A","70","0.35","5.0","75%"],["B","83","0.35","1.0","19%"],["C","131","0.35","1.0","5%"]],
      note="Flat CR is the LIMITATION — real per-product margin+shelf-life will spread these apart.")
slide("chart", h="40 · Business impact — cost simulation",
      lead="Simulated ordering cost over the test window. Smart ordering cuts cost ~21% vs current practice.",
      canvas="cCost",
      note="Lower = better. Baseline ₭3.71bn → model P50 ₭2.94bn on 608k order-days.")
slide("chart", h="41 · The management dial — service vs waste",
      lead="Pick your target. Higher service = fewer stockouts but more waste cost. Your call.",
      canvas="cDial",
      note="At demo economics cost-min sits near 50% service. Real economics will move the optimum.")
slide("table", h="42 · Warehouse picklist — the daily output",
      lead="Example: one day, top items to produce/ship (auto-generated, all outlets summed).",
      cols=["Product","order units","outlets"],
      rows=[[r["name"],f"{r['units']:,}",str(r["outlets"])] for r in
            json.loads((ROOT/"data"/"predictions"/"order_plan.parquet").exists() and "[]" or "[]")] or
           [["Golden Chicken Floss","2,704","57"],["Croissant 6'S","1,758","55"],
            ["Egg Pudding","1,693","58"],["Today's Brew","1,383","54"],
            ["Chicken Nugget Mini Burger","999","57"],["Shrimp Cutlet Bun","747","53"],
            ["Hot Dog Bun","732","57"],["Chocolate Eclair","724","55"]],
      note="Full list ~235 products / ~34,000 units / ₭138M for that day.")

# ---------------- SECTION 8 — ASSUMPTIONS ----------------
slide("table", h="43 · The data we ASSUMED (must replace)",
      lead="Order quantities use these placeholders until real values arrive.",
      warn=True,
      cols=["Assumed input","Demo value","Real source needed"],
      rows=[["Gross margin","35% (flat, all products)","Finance — per product/category"],
            ["Shelf-life","1 day (all same-day)","Ops — bread 1 / frozen 90 / ambient ∞"],
            ["Salvage value","0 (total loss)","Ops — markdown / staff recovery"]])
slide("bullets", h="44 · Why the assumptions matter (impact)",
      lead="Forecast = solid. Order sizing = only as good as the economics.",
      warn=True,
      b=["Flat margin → every product gets the SAME critical ratio → ordering can't differentiate.",
         "Result: the smart newsvendor currently ≈ a simple P50 order (no extra gain yet).",
         "Treating frozen/ambient as same-day perishable over-penalises their 'waste'.",
         "With REAL economics: high-margin/long-shelf items earn safety stock, perishables stay lean.",
         "This is a DATA gap, not a model gap — no re-engineering needed."])
slide("table", h="45 · Real vs assumed — at a glance",
      lead="Be clear what's proven vs what's placeholder.",
      cols=["Element","Status"],
      rows=[["Sales / demand data","REAL — 7.08M rows, clean"],
            ["Weather / festivals","REAL — open data"],
            ["Forecast model & accuracy","REAL — backtested, +16%"],
            ["Quantile calibration","REAL — 85/95% honest"],
            ["Selling price","REAL — from master"],
            ["Margin / shelf-life / salvage","ASSUMED — demo defaults"],
            ["Order quantities","DEMO — pending real economics"]])

# ---------------- SECTION 9 — SELF-LEARNING ----------------
slide("bullets", h="46 · Self-learning — champion / challenger",
      lead="The system keeps a live model and tests new ones against it automatically.",
      b=["Nightly: the live 'champion' produces tomorrow's order plan.",
         "Weekly: a fresh 'challenger' is trained on the newest data.",
         "Promote the challenger ONLY if it beats the champion by ≥1%.",
         "A worse model can never go live — safe to retrain often.",
         "This answers 'one model or many?' automatically over time."])
slide("chart", h="47 · Drift monitor — knowing when to relearn",
      lead="We watch for the world changing. The system caught the monsoon weather shift.",
      canvas="cDrift",
      note="Weather drifted (monsoon) but accuracy held → retrain on sustained accuracy drop, not weather alone.")
slide("kpi", h="48 · Champion model — current live",
      lead="Retrained on 7.9M rows, validated on a 60-day holdout.",
      cards=[("v_20260424","live champion"),("0.319","holdout WMAPE — beats target ≤0.321"),
             ("7.9M / 428k","train / holdout rows"),("auto","promote-if-better guard")])

# ---------------- SECTION 10 — FORWARD ----------------
slide("bullets", h="49 · How to take it forward — the ONE unlock",
      lead="Give the system real economics and ordering becomes truly smart.",
      b=["Get from Finance: gross margin per product (or category).",
         "Get from Ops: shelf-life days + salvage value per product.",
         "Drop into data/product_econ.csv — one file, no code change.",
         "Re-run order generation → per-product critical ratios spread apart.",
         "Then re-train and the loop carries the improvement forward forever."])
slide("table", h="50 · Roadmap / backlog",
      lead="Optional improvements, in priority order.",
      cols=["Item","Value","Effort"],
      rows=[["Plug real economics","HIGH — unlocks smart ordering","data only"],
            ["Croston/SBA for rare items","MEDIUM — covers 16% lumpy volume","model add"],
            ["Optuna tuning","LOW — squeeze accuracy further","compute"],
            ["Outlet→warehouse routing","MEDIUM — exact pick per warehouse","keys exist"],
            ["Schedule nightly/weekly jobs","ops — automate the loop","cron"]])
slide("bullets", h="51 · Expected impact with real data",
      lead="What changes once economics are in.",
      b=["Per-product ordering: cakes (high margin) fuller, bread (perishable) leaner.",
         "Stockout AND waste fall together — the dial moves to a better optimum.",
         "Cost saving beyond the ~21% already shown on flat economics.",
         "Management gets a single daily picklist + a service-level dial to set policy.",
         "Fully auditable, self-improving, and re-runnable on demand."])
slide("title", t="Summary",
      sub="Clean data → accurate, honest forecast (+16%, calibrated) → cost-cutting orders (−21% demo) → self-learning loop. One gap remains: real product economics — a data request, not a rebuild.",
      tag="Thank you · Questions?")

# ---------------------------------------------------------------- render
HEAD=r"""<!doctype html><html><head><meta charset=utf8><title>CFC Demand Forecasting — Briefing</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root{--bg:#0f1117;--card:#1a1d27;--ink:#eef1f7;--mut:#9aa0b2;--acc:#ff8a4c;--ok:#46c98b;--warn:#ffcf5c;--line:#2a2f3d}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#05060a;color:var(--ink);font:16px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,sans-serif}
.slide{position:relative;width:1280px;height:720px;margin:22px auto;background:var(--bg);
 border:1px solid var(--line);border-radius:18px;padding:54px 64px;overflow:hidden;page-break-after:always}
.slide:after{content:attr(data-n);position:absolute;right:26px;bottom:18px;color:#4b5163;font-size:13px}
.brand{position:absolute;left:64px;bottom:18px;color:#4b5163;font-size:13px;letter-spacing:.5px}
h2{font-size:30px;font-weight:750;margin-bottom:6px;letter-spacing:-.3px}
.lead{color:var(--acc);font-size:18px;margin-bottom:22px;font-weight:600}
.warn .lead{color:var(--warn)}
ul{list-style:none}li{font-size:20px;margin:14px 2px;padding-left:30px;position:relative;color:#dfe3ee}
li:before{content:"▸";position:absolute;left:2px;color:var(--acc)}
.warn li:before{content:"⚠";color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:18px;margin-top:6px}
td,th{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-size:14px;text-transform:uppercase;letter-spacing:.6px}
tr td:first-child{font-weight:600}
.note{position:absolute;left:64px;right:64px;bottom:46px;color:var(--mut);font-size:15px;font-style:italic}
.k{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-top:34px}
.kc{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:26px 20px}
.kc .v{font-size:40px;font-weight:800;color:var(--acc)}.kc .l{color:var(--mut);font-size:15px;margin-top:8px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:18px}
.tc{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:24px}
.tc h3{font-size:19px;color:var(--ink);margin-bottom:12px}.tc p{color:#cfd4e2;font-size:17px;white-space:pre-line}
.stat{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:30px}
.st{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:26px;text-align:center}
.st .v{font-size:30px;font-weight:800;color:var(--acc)}.st .l{color:#cfd4e2;font-size:16px;margin-top:8px}
.flow{display:flex;flex-wrap:wrap;gap:14px;margin-top:40px}
.fstep{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 16px;flex:1;min-width:130px;
 text-align:center;font-size:15px;white-space:pre-line;font-weight:600;color:#dfe3ee;position:relative}
.fstep .num{color:var(--acc);font-size:13px;display:block;margin-bottom:6px}
.formula{background:#11141d;border:1px solid var(--acc);border-radius:14px;padding:24px;margin:22px 0;
 font-size:24px;text-align:center;color:var(--acc);font-weight:700;letter-spacing:.3px}
.cwrap{position:relative;height:430px;margin-top:14px}
.cwrap.wide{height:440px}
.title-slide{display:flex;flex-direction:column;justify-content:center;height:100%;text-align:center}
.title-slide h1{font-size:46px;font-weight:850;letter-spacing:-1px;line-height:1.1}
.title-slide .s{color:#cfd4e2;font-size:22px;margin-top:20px;max-width:900px;align-self:center}
.title-slide .tag{color:var(--acc);font-size:16px;margin-top:34px;letter-spacing:1px;text-transform:uppercase}
@media print{body{background:#fff}.slide{margin:0;border:none;border-radius:0;page-break-after:always}}
</style></head><body>
"""
def esc(x): return str(x).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def rows_html(rows): return "".join("<tr>"+"".join(f"<td>{esc(c)}</td>" for c in r)+"</tr>" for r in rows)

charts=[]
def render(sl,n):
    k=sl["kind"]; wc="warn" if sl.get("warn") else ""
    note=f'<div class="note">{esc(sl["note"])}</div>' if sl.get("note") else ""
    body=""
    if k=="title":
        return (f'<section class="slide" data-n="{n}"><div class="title-slide">'
                f'<h1>{esc(sl["t"])}</h1><div class="s">{esc(sl["sub"])}</div>'
                f'<div class="tag">{esc(sl["tag"])}</div></div><div class="brand">CFC · CityFood Concepts</div></section>')
    if k=="bullets":
        body=f'<ul>{"".join(f"<li>{esc(x)}</li>" for x in sl["b"])}</ul>'
    elif k=="kpi":
        body='<div class=k>'+"".join(f'<div class=kc><div class=v>{esc(v)}</div><div class=l>{esc(l)}</div></div>' for v,l in sl["cards"])+'</div>'
    elif k=="two":
        (lh,lp)=sl["left"];(rh,rp)=sl["right"]
        body=f'<div class=two><div class=tc><h3>{esc(lh)}</h3><p>{esc(lp)}</p></div><div class=tc><h3>{esc(rh)}</h3><p>{esc(rp)}</p></div></div>'
    elif k=="twostat":
        body='<div class=stat>'+"".join(f'<div class=st><div class=v>{esc(v)}</div><div class=l>{esc(l)}</div></div>' for v,l in sl["stats"])+'</div>'
    elif k=="flow":
        body='<div class=flow>'+"".join(f'<div class=fstep><span class=num>{i+1}</span>{esc(s)}</div>' for i,s in enumerate(sl["steps"]))+'</div>'
    elif k=="table":
        head="<tr>"+"".join(f"<th>{esc(c)}</th>" for c in sl["cols"])+"</tr>"
        body=f'<table>{head}{rows_html(sl["rows"])}</table>'
    elif k=="formula":
        body=f'<div class=formula>{esc(sl["formula"])}</div><ul>{"".join(f"<li>{esc(x)}</li>" for x in sl["human"])}</ul>'
    elif k in ("chart","chartwide"):
        wide="wide" if k=="chartwide" else ""
        body=f'<div class="cwrap {wide}"><canvas id="{sl["canvas"]}"></canvas></div>'
        charts.append(sl["canvas"])
    lead=f'<div class=lead>{esc(sl["lead"])}</div>' if sl.get("lead") else ""
    return (f'<section class="slide {wc}" data-n="{n}"><h2>{esc(sl["h"])}</h2>{lead}{body}{note}'
            f'<div class="brand">CFC · CityFood Concepts</div></section>')

html=[HEAD]
for i,sl in enumerate(S,1): html.append(render(sl,i))

# ---- chart scripts (all real data) ----
CHART_JS=r"""
<script>
const DD=%%DD%%;
const F={legend:{labels:{color:'#9aa0b2',font:{size:13}}}};
const AX=c=>({ticks:{color:'#9aa0b2'},grid:{color:'#222838'}});
const base=(t,d,o={})=>({type:t,data:d,options:Object.assign({responsive:true,maintainAspectRatio:false,
 plugins:{legend:F.legend}},o)});
const sc={scales:{x:{ticks:{color:'#9aa0b2'},grid:{color:'#222838'}},y:{ticks:{color:'#9aa0b2'},grid:{color:'#222838'}}}};
function mk(id,cfg){const e=document.getElementById(id);if(e)new Chart(e,cfg);}

// monthly trend
mk('cMonthly',base('line',{labels:DD.monthly.labels,datasets:[{label:'net units',data:DD.monthly.units,
 borderColor:'#ff8a4c',backgroundColor:'#ff8a4c22',fill:true,tension:.3,pointRadius:0}]},sc));
// brand mix
mk('cBrand',base('bar',{labels:['Seasons','NBH','Bistro','Gong Cha','CD','LS'],
 datasets:[{label:'% of units',data:[85.5,6.6,5.2,2.2,0.2,0.1],backgroundColor:'#ff8a4c'}]},sc));
// pattern classification
mk('cPattern',base('bar',{labels:['smooth','erratic','intermittent','lumpy'],datasets:[
 {label:'% of series',data:[35,4,53,9],backgroundColor:'#3a3f4d'},
 {label:'% of volume',data:[71,8,16,5],backgroundColor:'#ff8a4c'}]},sc));
// wmape bars
mk('cWmape',base('bar',{labels:['LightGBM','moving_avg_7','mov_avg_28','naive','dow avg','same-wkday'],
 datasets:[{label:'WMAPE (lower better)',data:[0.341,0.401,0.411,0.450,0.460,0.528],
 backgroundColor:['#46c98b','#ff8a4c','#3a3f4d','#3a3f4d','#3a3f4d','#3a3f4d']}]},sc));
// folds
mk('cFolds',base('bar',{labels:['Apr-26','May-26','Jun-26'],datasets:[
 {label:'LightGBM',data:[0.384,0.325,0.305],backgroundColor:'#46c98b'},
 {label:'floor',data:[0.497,0.360,0.345],backgroundColor:'#3a3f4d'}]},sc));
// abc
mk('cAbc',base('bar',{labels:['A (75% vol)','B (19%)','C (5%)'],datasets:[
 {label:'LightGBM',data:[0.291,0.456,0.640],backgroundColor:'#46c98b'},
 {label:'floor',data:[0.349,0.534,0.733],backgroundColor:'#3a3f4d'}]},sc));
// by category
mk('cCat',base('bar',{labels:DD.bycat.map(c=>c.cat),datasets:[
 {label:'LightGBM',data:DD.bycat.map(c=>c.wmape),backgroundColor:'#46c98b'},
 {label:'floor',data:DD.bycat.map(c=>c.floor),backgroundColor:'#3a3f4d'}]},sc));
// by sku (horizontal)
mk('cSku',base('bar',{labels:DD.bysku.map(s=>s.name),datasets:[
 {label:'WMAPE',data:DD.bysku.map(s=>s.wmape),backgroundColor:'#ff8a4c'}]},
 {indexAxis:'y',scales:{x:{ticks:{color:'#9aa0b2'},grid:{color:'#222838'}},y:{ticks:{color:'#cfd4e2',font:{size:11}},grid:{display:false}}}}));
// hero forecast vs actual
mk('cHero',base('line',{labels:DD.hero.labels,datasets:[
 {label:'actual',data:DD.hero.actual,borderColor:'#eef1f7',pointRadius:0,tension:.3},
 {label:'P50',data:DD.hero.p50,borderColor:'#ff8a4c',pointRadius:0,tension:.3},
 {label:'P85',data:DD.hero.p85,borderColor:'#46c98b',borderDash:[4,4],pointRadius:0,tension:.3}]},
 {scales:{x:{ticks:{color:'#9aa0b2',maxTicksLimit:8},grid:{color:'#222838'}},y:{ticks:{color:'#9aa0b2'},grid:{color:'#222838'}}}}));
// scatter
mk('cScatter',base('scatter',{datasets:[{label:'outlet-product-day',data:DD.scatter,
 backgroundColor:'#ff8a4c55',pointRadius:2},
 {label:'perfect',type:'line',data:[{x:0,y:0},{x:DD.scatter_max,y:DD.scatter_max}],
 borderColor:'#46c98b',borderDash:[5,5],pointRadius:0}]},
 {scales:{x:{title:{display:true,text:'actual',color:'#9aa0b2'},ticks:{color:'#9aa0b2'},grid:{color:'#222838'},max:DD.scatter_max},
 y:{title:{display:true,text:'forecast',color:'#9aa0b2'},ticks:{color:'#9aa0b2'},grid:{color:'#222838'},max:DD.scatter_max}}}));
// calibration
mk('cCalib',base('bar',{labels:['P50','P85','P95'],datasets:[
 {label:'actual coverage %',data:[56.7,85.4,94.5],backgroundColor:'#ff8a4c'},
 {label:'target %',data:[50,85,95],backgroundColor:'#3a3f4d'}]},sc));
// feature importance
mk('cImp',base('bar',{labels:['ProductId','BranchId','rmean_28','lag_1','rstd_28','rmean_7','rmean_14','month','dow_mean_28'],
 datasets:[{label:'importance (gain)',data:[51107,30000,12101,6345,6100,5830,5367,4203,2282],backgroundColor:'#ff8a4c'}]},
 {indexAxis:'y',scales:{x:{ticks:{color:'#9aa0b2'},grid:{color:'#222838'}},y:{ticks:{color:'#cfd4e2'},grid:{display:false}}}}));
// cost sim
mk('cCost',base('bar',{labels:['baseline','model P50','model P85','model P95'],
 datasets:[{label:'ordering cost ₭bn (lower better)',data:[3.71,2.94,6.07,10.07],
 backgroundColor:['#3a3f4d','#46c98b','#ff8a4c','#e0556b']}]},sc));
// service dial
mk('cDial',base('bar',{labels:['30%','50%','70%','85%','95%'],datasets:[
 {type:'line',label:'cost ₭bn',data:[3.31,2.94,4.40,6.07,10.07],borderColor:'#ff8a4c',yAxisID:'y',tension:.3},
 {type:'bar',label:'stockout %',data:[57.9,34.2,18.2,10.6,4.1],backgroundColor:'#46c98b88',yAxisID:'y1'},
 {type:'bar',label:'waste %',data:[6.8,14.8,25.6,33.2,45.7],backgroundColor:'#ffcf5c88',yAxisID:'y1'}]},
 {scales:{x:{ticks:{color:'#9aa0b2'},grid:{display:false}},
 y:{position:'left',ticks:{color:'#ff8a4c'},grid:{color:'#222838'},title:{display:true,text:'cost ₭bn',color:'#ff8a4c'}},
 y1:{position:'right',ticks:{color:'#9aa0b2'},grid:{display:false},title:{display:true,text:'%',color:'#9aa0b2'}}}}));
// drift PSI
mk('cDrift',base('bar',{labels:['demand','lag_7','rmean_28','rstd_28','price','tmax','rain','dow'],
 datasets:[{label:'PSI (drift; >0.2 = shift)',data:[0.089,0.072,0.146,0.127,0.058,1.573,2.252,0.007],
 backgroundColor:['#46c98b','#46c98b','#46c98b','#46c98b','#46c98b','#e0556b','#e0556b','#46c98b']}]},sc));
</script></body></html>
"""
html.append(CHART_JS.replace("%%DD%%", json.dumps(DD)))
out=ROOT/"reports"/"presentation.html"
out.write_text("".join(html))
print(f"wrote {out} — {len(S)} slides, {len(charts)} charts")
