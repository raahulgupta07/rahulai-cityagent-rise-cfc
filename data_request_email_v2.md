# Email — Data Request v2 (to make the forecast production-grade)

**Subject: Data needed to turn the CFC demand forecast into real order quantities**

Hi [Finance / Ops / Supply Chain],

Quick update: the demand-forecasting model for the CFC outlets (Seasons, NBH, Bistro, Gong Cha) is
built and working. It learns from 3.5 years of daily sales (7.08M records, 84 outlets, 3,580 products)
and predicts tomorrow's demand per product per outlet. On honest back-testing it is ~16% more accurate
than the current "repeat last week" method, and in simulation it cuts combined stockout + waste cost
by ~21%.

To take it from "good forecast" to "trustworthy daily order list the warehouse can act on", I need a
few pieces of business data that don't live in the sales tables. Listed below by priority.

---

## 1. Product economics — THE main unlock (from Finance + Ops)
Right now the order quantities assume every product has the same 35% margin and spoils in 1 day
(a placeholder). With real numbers, the system orders high-margin / long-life items generously and
keeps perishables lean — automatically, no code change.

Per product (or per category if per-product is hard):
- **Gross margin %** (or cost price + sell price).
- **Shelf life (days)** — 1 = sells same day, 3 = a few days, 90 = frozen, etc.
- **Salvage value** — what %, if any, is recovered on unsold units (markdown, staff meals, return to
  warehouse). 0 if simply thrown away.

## 2. Lead time / SLA — factory & warehouse → outlet
The model forecasts "tomorrow", but if an order placed today only reaches the outlet in 2 days, we
must forecast further ahead and hold the right buffer. Need:
- **Order cut-off time** — by what time must an outlet place its order each day.
- **Lead time (hours/days)** from order placed → delivered on shelf, per outlet or per route.
- **Delivery frequency** — daily? specific weekdays? once vs twice a day?
- **Production lead time** at the factory/central kitchen (how long to make a batch).
- Any **minimum order quantity / batch size / pack size** (e.g. must order in trays of 12).

## 3. Inventory data (from Ops / WMS / POS)
We currently see only what *sold*. We don't see what was *available*. This is the biggest blind spot:
- **Opening + closing stock per outlet per product per day** (units on shelf).
- **Units delivered/received** per outlet per day (what was actually sent).
- **Units wasted / written off / returned** per outlet per day (expiry, damage).
- **Warehouse / central stock on hand** per product per day.

Why it matters: a "0 sold" day might be no demand — or a stockout (sold out, demand was higher). Without
stock data we can't tell those apart, which caps accuracy on best-sellers.

## 4. Order history (from procurement / WMS)
- Historical **outlet → warehouse order quantities** per day (what was ordered vs what we now forecast).
  Lets us measure improvement against current practice directly.

## 5. Promotions & events calendar (from Marketing)
- **Promo / discount calendar** — which products, which outlets, which dates, what mechanic
  (buy-1-get-1, % off). Promotions spike demand; without flags the model blames the spike on noise.
- **New product launch / discontinue dates** — so we don't forecast dead SKUs or cold-start blindly.
- **Outlet open / close / renovation dates** — to explain sudden zeros.

## 6. Useful extras (nice-to-have, not blocking)
- **Outlet attributes** — size, seating, location type (mall / street / transit), opening hours.
- **Price changes** over time (price affects volume).
- **Capacity limits** — max units an outlet can display/store, or factory daily capacity per line.
- **Substitution / recipe links** — products that share ingredients or substitute for each other.
- **Weather** we already have for 6 cities; confirm which outlets map to which city if any are off.

---

## Format & questions
- A daily CSV/Excel export is fine for all of the above — doesn't need to be live API yet.
- For economics (#1) even a one-time spreadsheet gets us to production numbers immediately.
- Which of these already exist in Fabric / the WMS / POS, and which need to be pulled from elsewhere?
- Who owns each: who do I talk to for economics, for lead times/SLA, for inventory?

Priority order if it has to be staged: **#1 economics → #2 lead time → #3 inventory**. Those three turn
the forecast into reliable, money-saving order quantities.

Thanks,
Rahul
