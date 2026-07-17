"""
Non-technical executive deck — story + diagrams, minimal jargon.
Builds reports/exec_presentation.html (+ PDF via Chrome). ~15 slides.
"""
import pathlib
ROOT=pathlib.Path(__file__).resolve().parent.parent

HEAD=r"""<!doctype html><html><head><meta charset=utf8><title>CFC — Smart Ordering (Executive)</title>
<style>
:root{--bg:#101826;--card:#18233a;--ink:#f2f5fb;--mut:#9fb0cc;--acc:#ff8a4c;--ok:#3ecf8e;--bad:#e0556b;--line:#26344f}
*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,sans-serif}
body{background:#070b12}
.slide{position:relative;width:1280px;height:720px;margin:22px auto;background:linear-gradient(160deg,#101826,#0c1320);
 border:1px solid var(--line);border-radius:20px;padding:56px 70px;overflow:hidden;page-break-after:always;color:var(--ink)}
.slide:after{content:attr(data-n);position:absolute;right:28px;bottom:18px;color:#46567a;font-size:13px}
.brand{position:absolute;left:70px;bottom:18px;color:#46567a;font-size:13px;letter-spacing:.5px}
h2{font-size:34px;font-weight:800;margin-bottom:10px;letter-spacing:-.3px}
.lead{color:var(--acc);font-size:21px;font-weight:600;margin-bottom:30px;max-width:1050px}
.big{font-size:26px;line-height:1.55;color:#e7ecf6;max-width:1050px}
.big b{color:var(--acc)}
/* title */
.ts{display:flex;flex-direction:column;justify-content:center;height:100%;text-align:center}
.ts h1{font-size:52px;font-weight:900;letter-spacing:-1px;line-height:1.08}
.ts .s{color:#cdd7ea;font-size:24px;margin-top:22px;align-self:center;max-width:920px}
.ts .tag{color:var(--acc);font-size:17px;margin-top:36px;letter-spacing:2px;text-transform:uppercase}
/* flow row */
.flow{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:50px;flex-wrap:wrap}
.fb{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px 18px;text-align:center;
 min-width:150px;flex:1}
.fb .ic{font-size:38px;display:block;margin-bottom:10px}
.fb .t{font-size:17px;font-weight:700}.fb .d{font-size:13px;color:var(--mut);margin-top:4px}
.arr{color:var(--acc);font-size:30px;font-weight:800}
/* two big columns */
.cols{display:flex;gap:26px;margin-top:24px}
.col{flex:1;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:30px;text-align:center}
.col .ic{font-size:54px;display:block;margin-bottom:14px}
.col h3{font-size:24px;margin-bottom:10px}.col p{color:#cdd7ea;font-size:18px}
.col.bad{border-color:#5a2733}.col.bad h3{color:var(--bad)}
.col.good{border-color:#1f5640}.col.good h3{color:var(--ok)}
/* balance scale */
.scale{display:flex;justify-content:space-around;align-items:flex-start;margin-top:30px}
.pan{flex:1;max-width:360px;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:28px;text-align:center;margin:0 16px}
.pan .ic{font-size:46px}.pan h3{font-size:21px;margin:10px 0}.pan p{color:#cdd7ea;font-size:16px}
.mid{align-self:center;text-align:center;color:var(--acc);font-weight:800;font-size:20px}
/* loop */
.loop{display:flex;align-items:center;justify-content:center;gap:14px;margin-top:46px;flex-wrap:wrap}
.ln{background:var(--card);border:1px solid var(--line);border-radius:50px;padding:20px 26px;font-size:17px;font-weight:600;text-align:center}
.ln .ic{font-size:26px;display:block}
/* big number cards */
.nums{display:flex;gap:22px;margin-top:40px}
.nc{flex:1;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:34px 22px;text-align:center}
.nc .v{font-size:46px;font-weight:900;color:var(--acc)}.nc .l{color:#cdd7ea;font-size:17px;margin-top:10px}
/* simple list */
ul{list-style:none;margin-top:10px}li{font-size:23px;margin:18px 4px;padding-left:38px;position:relative;color:#e7ecf6}
li:before{content:"✓";position:absolute;left:2px;color:var(--ok);font-weight:800}
.warn li:before{content:"!";color:var(--acc)}
/* picklist mock */
.pl{margin-top:20px;background:var(--card);border:1px solid var(--line);border-radius:16px;overflow:hidden}
.pl .row{display:flex;justify-content:space-between;padding:15px 28px;border-bottom:1px solid var(--line);font-size:20px}
.pl .row.h{color:var(--mut);font-size:14px;text-transform:uppercase;letter-spacing:.6px}
.pl .row b{color:var(--acc)}
.note{position:absolute;left:70px;right:70px;bottom:48px;color:var(--mut);font-size:16px;font-style:italic}
.bars{margin-top:36px}
.bar{display:flex;align-items:center;gap:18px;margin:18px 0;font-size:20px}
.bar .lab{width:230px;text-align:right;color:#cdd7ea}
.bar .track{flex:1;background:#0c1320;border-radius:10px;height:38px;position:relative;border:1px solid var(--line)}
.bar .fill{height:100%;border-radius:10px;display:flex;align-items:center;padding-left:14px;font-weight:700;color:#06101e}
@media print{body{background:#fff}.slide{margin:0;border:none;border-radius:0}}
</style></head><body>
"""

SL=[]
def add(html): SL.append(html)
def wrap(inner, n, cls=""):
    return f'<section class="slide {cls}" data-n="{n}">{inner}<div class="brand">CFC · CityFood Concepts</div></section>'

# 1 title
add(('<div class=ts><h1>Smart Daily Ordering for CFC Bakery</h1>'
     '<div class=s>Stop guessing how much to send each shop. Let the numbers decide — '
     'less waste, fewer empty shelves.</div>'
     '<div class=tag>CityFood Concepts · Executive Summary</div></div>'))

# 2 problem
add(('<h2>The problem we set out to solve</h2>'
     '<div class=lead>Every day, 84 shops order fresh bakery from the warehouse. Getting the amount wrong costs money — both ways.</div>'
     '<div class=cols>'
     '<div class="col bad"><span class=ic>📦</span><h3>Order too MUCH</h3><p>Unsold bakery spoils by night. Cash thrown in the bin.</p></div>'
     '<div class="col bad"><span class=ic>🚫</span><h3>Order too LITTLE</h3><p>Empty shelves. Lost sales. Disappointed customers.</p></div>'
     '</div>'
     '<div class=note>Today this is decided by gut feel and rough averages — so both mistakes happen every single day.</div>'))

# 3 idea / analogy
add(('<h2>Our idea</h2>'
     '<div class=lead>Build a "weather forecast" — but for sales.</div>'
     '<div class=big>Just like a weather app learns from history to predict tomorrow\'s rain, '
     'our system learns from <b>3.5 years of sales</b> to predict <b>tomorrow\'s demand</b> — '
     'for every product, in every shop.<br><br>'
     'Then it tells the warehouse <b>exactly how much to make and send</b>.</div>'))

# 4 big flow
add(('<h2>How it works — the whole picture</h2>'
     '<div class=lead>Five simple steps, fully automatic.</div>'
     '<div class=flow>'
     '<div class=fb><span class=ic>🗄️</span><div class=t>Past sales</div><div class=d>3.5 years</div></div>'
     '<span class=arr>→</span>'
     '<div class=fb><span class=ic>🧠</span><div class=t>Learning engine</div><div class=d>finds patterns</div></div>'
     '<span class=arr>→</span>'
     '<div class=fb><span class=ic>🔮</span><div class=t>Forecast</div><div class=d>tomorrow\'s demand</div></div>'
     '<span class=arr>→</span>'
     '<div class=fb><span class=ic>🧮</span><div class=t>Order amount</div><div class=d>balances cost</div></div>'
     '<span class=arr>→</span>'
     '<div class=fb><span class=ic>📋</span><div class=t>Warehouse list</div><div class=d>make & send</div></div>'
     '</div>'
     '<div class=note>The system runs this every night, on its own.</div>'))

# 5 what feeds it
add(('<h2>What the engine learns from</h2>'
     '<div class=lead>Three kinds of signal — the same things a smart shop manager would consider.</div>'
     '<div class=cols>'
     '<div class=col><span class=ic>🧾</span><h3>Sales history</h3><p>What sold, where, when. Weekday rhythm, paydays, trends.</p></div>'
     '<div class=col><span class=ic>🌧️</span><h3>Weather</h3><p>Rain and heat change how many people walk in.</p></div>'
     '<div class=col><span class=ic>🎉</span><h3>Holidays & festivals</h3><p>Public holidays lift demand; Thingyan closes shops.</p></div>'
     '</div>'))

# 6 how good - simple bars
add(('<h2>How good is the forecast?</h2>'
     '<div class=lead>16% more accurate than the simple averages used today.</div>'
     '<div class=bars>'
     '<div class=bar><div class=lab>Old way (averages)</div><div class=track><div class=fill style="width:80%;background:#4a5a78">more mistakes</div></div></div>'
     '<div class=bar><div class=lab>Our system</div><div class=track><div class=fill style="width:64%;background:#3ecf8e">fewer mistakes ✓</div></div></div>'
     '</div>'
     '<div class=note>Tested honestly on months the system had never seen — and it won every month.</div>'))

# 7 range not guess
add(('<h2>It gives a range, not a single guess</h2>'
     '<div class=lead>Because real demand is never exactly one number.</div>'
     '<div class=nums>'
     '<div class=nc><div class=v>Likely</div><div class=l>the middle estimate — normal days</div></div>'
     '<div class=nc><div class=v>Safe</div><div class=l>stock a bit more — rarely run out</div></div>'
     '<div class=nc><div class=v>Very safe</div><div class=l>almost never run out — for key items</div></div>'
     '</div>'
     '<div class=note>This lets us choose how cautious to be — product by product.</div>'))

# 8 balance scale - order decision
add(('<h2>Turning the forecast into an order</h2>'
     '<div class=lead>The order amount balances two costs — like a scale.</div>'
     '<div class=scale>'
     '<div class=pan><span class=ic>🚫</span><h3>Stockout cost</h3><p>Lost profit when shelves go empty</p></div>'
     '<div class=mid>⚖️<br>BALANCE</div>'
     '<div class=pan><span class=ic>🗑️</span><h3>Spoilage cost</h3><p>Money lost when bakery is unsold</p></div>'
     '</div>'
     '<div class=note>High-profit, long-lasting items → stock more. Cheap, quick-to-spoil items → stock lean.</div>'))

# 9 picklist
add(('<h2>The daily output — one warehouse list</h2>'
     '<div class=lead>Every morning: exactly what to make and how much. Example day below.</div>'
     '<div class=pl>'
     '<div class="row h"><span>Product</span><span>Make / send</span></div>'
     '<div class=row><span>Golden Chicken Floss</span><b>2,704</b></div>'
     '<div class=row><span>Croissant 6\'S</span><b>1,758</b></div>'
     '<div class=row><span>Egg Pudding</span><b>1,693</b></div>'
     '<div class=row><span>Today\'s Brew</span><b>1,383</b></div>'
     '<div class=row><span>… 230 more products</span><b>~34,000 total</b></div>'
     '</div>'
     '<div class=note>One clear list, instead of 84 shops guessing separately.</div>'))

# 10 the dial
add(('<h2>You set the policy — the dial</h2>'
     '<div class=lead>Want fuller shelves or less waste? Management chooses the target.</div>'
     '<div class=cols>'
     '<div class=col><span class=ic>💰</span><h3>Save money</h3><p>Order lean. Lowest cost, accept a few stockouts.</p></div>'
     '<div class=col><span class=ic>⚖️</span><h3>Balanced</h3><p>The cost-smart middle — recommended default.</p></div>'
     '<div class=col><span class=ic>🛍️</span><h3>Full shelves</h3><p>Rarely run out. Costs more in waste.</p></div>'
     '</div>'
     '<div class=note>The system shows the trade-off for each choice — you decide the policy.</div>'))

# 11 self-learning loop
add(('<h2>It keeps improving by itself</h2>'
     '<div class=lead>No yearly rebuild. The system relearns as new sales come in.</div>'
     '<div class=loop>'
     '<div class=ln><span class=ic>🌙</span>Predict<br>tonight</div><span class=arr>→</span>'
     '<div class=ln><span class=ic>🧾</span>See what<br>really sold</div><span class=arr>→</span>'
     '<div class=ln><span class=ic>📈</span>Learn<br>from it</div><span class=arr>→</span>'
     '<div class=ln><span class=ic>✅</span>Improve<br>if better</div><span class=arr>↻</span>'
     '</div>'
     '<div class=note>It also watches for big changes (like monsoon) and flags when it should relearn.</div>'))

# 12 whats done vs missing
add(('<h2>What\'s ready — and the one thing we need</h2>'
     '<div class=lead>The forecast is built and proven. One piece of business data unlocks the rest.</div>'
     '<ul>'
     '<li>Sales data — collected, cleaned, 3.5 years</li>'
     '<li>Forecast engine — built and accurate (+16%)</li>'
     '<li>Daily ordering & warehouse list — working</li>'
     '<li>Self-learning loop — running</li>'
     '</ul>'
     '<ul class=warn><li>We need: each product\'s <b>profit margin</b> + <b>shelf-life</b> (from Finance & Ops)</li></ul>'
     '<div class=note>Until then, ordering uses sensible placeholder economics. Real numbers make it truly smart.</div>'))

# 13 impact
add(('<h2>The impact</h2>'
     '<div class=lead>What CFC gets from this.</div>'
     '<div class=nums>'
     '<div class=nc><div class=v>↓ Waste</div><div class=l>less unsold bakery binned</div></div>'
     '<div class=nc><div class=v>↓ Stockouts</div><div class=l>fuller shelves, more sales</div></div>'
     '<div class=nc><div class=v>~21%</div><div class=l>lower ordering cost (early estimate)</div></div>'
     '<div class=nc><div class=v>1 list</div><div class=l>daily, automatic, auditable</div></div>'
     '</div>'))

# 14 next step
add(('<h2>Next step</h2>'
     '<div class=lead>Simple and quick.</div>'
     '<div class=big>1.  Finance shares <b>profit margin</b> per product.<br><br>'
     '2.  Operations shares <b>shelf-life</b> per product.<br><br>'
     '3.  We load it in — <b>no rebuild</b> — and ordering becomes fully smart.<br><br>'
     '4.  Run a pilot in a few shops, measure the saving, then roll out.</div>'))

# 15 thank you
add(('<div class=ts><h1>From guesswork to a smart, self-learning system</h1>'
     '<div class=s>Less waste. Fuller shelves. One daily list. Ready to pilot once we have product margins & shelf-life.</div>'
     '<div class=tag>Thank you · Questions?</div></div>'))

html=[HEAD]
for i,s in enumerate(SL,1):
    cls="" if "<h2" in s else ""
    html.append(wrap(s,i,cls))
html.append("</body></html>")
out=ROOT/"reports"/"exec_presentation.html"
out.write_text("".join(html))
print(f"wrote {out} — {len(SL)} slides")
