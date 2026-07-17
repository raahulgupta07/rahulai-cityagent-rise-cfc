#!/usr/bin/env python3
"""
Build a Myanmar public-holidays + festivals CSV for 2023-2026.

PART 1: Gazetted public holidays from the `holidays` library (country MM).
        Burmese names are mapped to English.
PART 2: Curated lunar festivals (Thingyan multi-day event, New Year Day,
        Thadingyut, Tazaungdaing, Waso, Kasone, Tabaung) with web-verified
        dates layered on top.

Merge rule: dedupe by (date, normalized-name). If a curated festival shares a
date with a gazetted public holiday, the public-holiday row wins
(is_public_holiday=1, type=public_holiday) but inherits the richest notes /
multi_day_event tag.

Output columns (exact order):
    date,name,type,is_public_holiday,multi_day_event,notes
"""
import csv
import datetime
import holidays

YEARS = [2023, 2024, 2025, 2026]
OUT = "data/external/myanmar_holidays.csv"

# ---------------------------------------------------------------------------
# English translations for the Burmese names emitted by holidays v0.83 (MM).
# Keyed by the Burmese string; fallback keeps the original if unmapped.
# ---------------------------------------------------------------------------
BURMESE_TO_EN = {
    "လွတ်လပ်ရေးနေ့": "Independence Day",
    "ပြည်ထောင်စုနေ့": "Union Day",
    "တောင်သူလယ်သမားနေ့": "Peasants' Day",
    "တပေါင်းလပြည့်နေ့": "Full Moon Day of Tabaung",
    "တပ်မတော်နေ့": "Armed Forces Day",
    "မြန်မာနှစ်သစ်ကူး ရုံးပိတ်ရက်များ": "Thingyan / Myanmar New Year Holiday",
    "မေဒေးနေ့": "Labour Day",
    "ကဆုန်လပြည့်နေ့": "Full Moon Day of Kasone (Buddha Day)",
    "အီဒုလ်အဿွဟာနေ့": "Eid al-Adha",
    "အီဒုလ်အဿွဟာနေ့ (ခန့်မှန်း)": "Eid al-Adha (estimated)",
    "အာဇာနည်နေ့": "Martyrs' Day",
    "ဝါဆိုလပြည့်နေ့": "Full Moon Day of Waso (Beginning of Buddhist Lent)",
    "သီတင်းကျွတ်ပိတ်ရက်များ": "Thadingyut Festival (Festival of Lights)",
    "ဒီပါဝလီနေ့": "Deepavali",
    "တန်ဆောင်တိုင်လပြည့်နေ့": "Full Moon Day of Tazaungmone (Tazaungdaing)",
    "အမျိုးသားနေ့": "National Day",
    "ခရစ္စမတ်နေ့": "Christmas Day",
    "ကရင်နှစ်သစ်ကူးနေ့": "Karen New Year",
    "အလုပ်ပိတ်ရက် (11-01-2025 မှ ပြန်လဲထားသည်)": "Substitute Holiday",
    "နိုင်ငံတကာနှစ်သစ်ကူးနေ့": "International New Year's Day",
    "တရုတ်နှစ်သစ်ကူးနေ့": "Chinese New Year",
    "အလုပ်ပိတ်ရက် (22-03-2025 မှ ပြန်လဲထားသည်)": "Substitute Holiday",
    "အလုပ်ပိတ်ရက် (29-03-2025 မှ ပြန်လဲထားသည်)": "Substitute Holiday",
    "အလုပ်ပိတ်ရက် (08-11-2025 မှ ပြန်လဲထားသည်)": "Substitute Holiday",
    "အလုပ်ပိတ်ရက် (03-01-2026 မှ ပြန်လဲထားသည်)": "Substitute Holiday",
}


def translate(name: str) -> str:
    # Some entries combine two names with "; "
    parts = [p.strip() for p in name.split(";")]
    return "; ".join(BURMESE_TO_EN.get(p, p) for p in parts)


# Notes per English name for public-holiday rows.
NOTES = {
    "Independence Day": "national public holiday",
    "Union Day": "national public holiday",
    "Peasants' Day": "national public holiday",
    "Full Moon Day of Tabaung": "lunar full moon; Tabaung pagoda festivals",
    "Armed Forces Day": "national public holiday",
    "Thingyan / Myanmar New Year Holiday": "gazetted Thingyan closure period",
    "Labour Day": "international workers' day",
    "Full Moon Day of Kasone (Buddha Day)": "lunar full moon; Buddha's birth/enlightenment/death",
    "Eid al-Adha": "Islamic festival of sacrifice",
    "Eid al-Adha (estimated)": "Islamic festival of sacrifice (date estimated)",
    "Martyrs' Day": "national public holiday",
    "Full Moon Day of Waso (Beginning of Buddhist Lent)": "lunar full moon; start of Buddhist Lent",
    "Thadingyut Festival (Festival of Lights)": "lunar; end of Buddhist Lent, lights festival",
    "Deepavali": "Hindu festival of lights",
    "Full Moon Day of Tazaungmone (Tazaungdaing)": "lunar full moon; lights & hot-air balloon festival",
    "National Day": "national public holiday",
    "Christmas Day": "Christian holiday",
    "Karen New Year": "Karen ethnic new year (lunar)",
    "Substitute Holiday": "government substitute day off",
    "International New Year's Day": "Gregorian new year",
    "Chinese New Year": "lunar new year (Chinese community)",
}

# multi_day_event tag for dates that belong to the Thingyan period.
THINGYAN_NAME = "Thingyan / Myanmar New Year Holiday"


# ---------------------------------------------------------------------------
# PART 2 — curated festival rows (web-verified where noted).
# These supplement / annotate the gazetted data. Rows that fall on a gazetted
# public holiday will be merged (public holiday wins) but contribute notes.
# ---------------------------------------------------------------------------
# Thingyan core water-throwing window + New Year Day per year.
# Verified: standard Thingyan window is Apr 13-16 (water days) with New Year
# Day Apr 17. The gazetted closure period (from holidays lib) is wider and is
# the authoritative public-holiday range; here we mark the cultural sub-events.
CURATED = [
    # ---- 2023 ----
    ("2023-04-13", "Thingyan (Water Festival)", "festival", 0, THINGYAN_NAME,
     "biggest festival, water throwing begins (Thingyan a-kya)"),
    ("2023-04-17", "Myanmar New Year Day", "festival", 0, THINGYAN_NAME,
     "Myanmar lunar new year day (Hnit Hsan Ta Yet)"),
    # ---- 2024 ----
    ("2024-04-13", "Thingyan (Water Festival)", "festival", 0, THINGYAN_NAME,
     "biggest festival, water throwing begins (Thingyan a-kya)"),
    ("2024-04-17", "Myanmar New Year Day", "festival", 0, THINGYAN_NAME,
     "Myanmar lunar new year day (Hnit Hsan Ta Yet)"),
    # ---- 2025 ----
    ("2025-04-13", "Thingyan (Water Festival)", "festival", 0, THINGYAN_NAME,
     "biggest festival, water throwing begins (Thingyan a-kya)"),
    ("2025-04-17", "Myanmar New Year Day", "festival", 0, THINGYAN_NAME,
     "Myanmar lunar new year day (Hnit Hsan Ta Yet)"),
    # ---- 2026 ----
    ("2026-04-13", "Thingyan (Water Festival)", "festival", 0, THINGYAN_NAME,
     "biggest festival, water throwing begins (Thingyan a-kya)"),
    ("2026-04-17", "Myanmar New Year Day", "festival", 0, THINGYAN_NAME,
     "Myanmar lunar new year day (Hnit Hsan Ta Yet)"),
]


def in_years(d: str) -> bool:
    return int(d[:4]) in YEARS


def thingyan_range(year, mm):
    """Return sorted list of gazetted Thingyan dates for a year."""
    out = []
    for d, name in mm.items():
        if d.year == year and "မြန်မာနှစ်သစ်ကူး" in name:
            out.append(d)
    return sorted(out)


def main():
    mm = holidays.Myanmar(years=YEARS)

    # date(str) -> row dict
    rows = {}

    def key(date_str, name):
        return (date_str, name.strip().lower())

    # PART 1: gazetted public holidays
    for d in sorted(mm):
        date_str = d.isoformat()
        en = translate(mm[d])
        is_thingyan = "Thingyan" in en
        row = {
            "date": date_str,
            "name": en,
            "type": "public_holiday",
            "is_public_holiday": 1,
            "multi_day_event": THINGYAN_NAME if is_thingyan else "",
            "notes": NOTES.get(en, "public holiday"),
        }
        rows[key(date_str, en)] = row

    # PART 2: curated festivals, merged.
    for (date_str, name, typ, isph, mde, note) in CURATED:
        if not in_years(date_str):
            continue
        # Does a public holiday already exist on this exact date?
        ph_same_date = [r for k, r in rows.items()
                        if r["date"] == date_str and r["is_public_holiday"] == 1]
        k = key(date_str, name)
        if k in rows:
            # exact dup name+date -> enrich notes if richer
            existing = rows[k]
            if note and note not in existing["notes"]:
                existing["notes"] = f"{existing['notes']}; {note}"
            if mde and not existing["multi_day_event"]:
                existing["multi_day_event"] = mde
        elif ph_same_date:
            # A public holiday occupies this date. Keep PH row(s) but make
            # sure the multi_day_event tag + festival flavour is carried.
            for r in ph_same_date:
                if mde and not r["multi_day_event"]:
                    r["multi_day_event"] = mde
                if note and note not in r["notes"]:
                    r["notes"] = f"{r['notes']}; {note}"
            # Still add the distinct festival row (different name) so the
            # cultural event name is queryable, but mark it not a PH.
            rows[k] = {
                "date": date_str, "name": name, "type": typ,
                "is_public_holiday": isph, "multi_day_event": mde, "notes": note,
            }
        else:
            rows[k] = {
                "date": date_str, "name": name, "type": typ,
                "is_public_holiday": isph, "multi_day_event": mde, "notes": note,
            }

    # Tag every gazetted Thingyan-period date with the multi_day_event name
    for year in YEARS:
        for d in thingyan_range(year, mm):
            ds = d.isoformat()
            for r in rows.values():
                if r["date"] == ds and not r["multi_day_event"]:
                    r["multi_day_event"] = THINGYAN_NAME

    # Sort by date then name
    ordered = sorted(rows.values(), key=lambda r: (r["date"], r["name"]))

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "name", "type", "is_public_holiday",
                        "multi_day_event", "notes"],
        )
        w.writeheader()
        w.writerows(ordered)

    # ---------------- verification ----------------
    print(f"Wrote {OUT}")
    print(f"TOTAL ROWS: {len(ordered)}\n")

    print("=== ALL 2026 ROWS ===")
    for r in ordered:
        if r["date"].startswith("2026"):
            print(f"{r['date']} | {r['name']} | {r['type']} | "
                  f"ph={r['is_public_holiday']} | mde={r['multi_day_event']} | {r['notes']}")

    print("\n=== COUNT BY YEAR ===")
    by_year = {}
    for r in ordered:
        by_year[r["date"][:4]] = by_year.get(r["date"][:4], 0) + 1
    for y in sorted(by_year):
        print(f"{y}: {by_year[y]}")

    print("\n=== COUNT BY TYPE ===")
    by_type = {}
    for r in ordered:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    for t in sorted(by_type):
        print(f"{t}: {by_type[t]}")

    print("\n=== THINGYAN PRESENCE PER YEAR ===")
    for year in YEARS:
        days = sorted({r["date"] for r in ordered
                       if r["multi_day_event"] == THINGYAN_NAME
                       and r["date"].startswith(str(year))})
        print(f"{year}: {len(days)} days  {days[0]} .. {days[-1]}" if days
              else f"{year}: MISSING")


if __name__ == "__main__":
    main()
