"""Pull the city's own market-value estimate for every lot that sold, as of before it sold.

The rival nobody bothers to beat. New York's Department of Finance publishes a market
value for all 1.1m tax lots every year, free, on a public portal. If that number is as
close to the eventual sale price as a comparable-sales workup is, then the workup is
costing a shop time it is not buying anything with.

Blindness is the same discipline as the comps: for a sale in calendar year Y this takes
the assessment roll for fiscal year Y, whose tentative roll is published on 15 January
of calendar year Y-1 and whose final roll is published that May. Both dates precede the
first sale being scored. `curmkttot` is the operative market value on that roll.

Source: Property Valuation and Assessment Data, `data.cityofnewyork.us` `8y4t-faws`,
which covers fiscal 2023 onward. Earlier rolls live in `yjxr-fw8i` and stop at fiscal
2019, so calendar 2020 to 2022 has no published roll on the portal and no assessment
rival can be scored there.

    python3 assess.py
    python3 assess.py --test
"""

import collections
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SALES = os.path.join(DATA, "sales.csv")
OUT = os.path.join(DATA, "assessed.csv")
HOST = "data.cityofnewyork.us"
VIEW = "8y4t-faws"

# Roll years the portal carries. A sale in calendar year Y is matched to roll year Y.
YEARS = [2023, 2024, 2025]
BATCH = 250

FIELDS = ["parid", "year", "period", "curmkttot", "tenmkttot", "curtaxclass",
          "bldg_class", "gross_sqft"]


def bbl(boro, block, lot):
    """Lot identifier as the roll writes it: borough, block padded to 5, lot to 4."""
    return f"{int(boro)}{int(block):05d}{int(lot):04d}"


def sold_lots():
    """Every lot that sold in a year with a published roll, keyed by that year."""
    want = collections.defaultdict(set)
    with open(SALES, newline="") as fh:
        for r in csv.DictReader(fh):
            y = int(r["year"])
            if y in YEARS:
                want[y].add(bbl(r["borough"], r["block"], r["lot"]))
    return want


def fetch(year, parids):
    quoted = ",".join(f"'{p}'" for p in parids)
    params = {
        "$select": ",".join(FIELDS),
        "$where": f"year='{year}' AND parid in({quoted})",
        "$limit": len(parids) * 4,
    }
    url = f"https://{HOST}/resource/{VIEW}.json?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.load(r)
        except Exception as exc:
            if attempt == 3:
                raise
            print(f"  retry {attempt + 1} after {exc}", file=sys.stderr)
            time.sleep(2 ** attempt)


def pick(raw):
    """One row per lot per year: the final roll where it exists, else the tentative.

    Both are published before the calendar year being scored, so this is a choice about
    accuracy rather than about blindness.
    """
    best = {}
    for r in raw:
        if r.get("rectype") not in (None, "1"):
            continue
        val = r.get("curmkttot") or r.get("tenmkttot") or "0"
        try:
            val = float(val)
        except ValueError:
            continue
        if val <= 0:
            continue
        key = (r["parid"], int(r["year"]))
        rank = 1 if r.get("period") == "3" else 0
        if key not in best or rank > best[key][0]:
            best[key] = (rank, {
                "parid": r["parid"],
                "roll_year": int(r["year"]),
                "market_value": val,
                "tax_class": r.get("curtaxclass", ""),
                "bldg_class": r.get("bldg_class", ""),
                "roll_sqft": r.get("gross_sqft", ""),
            })
    return [v[1] for v in best.values()]


def main():
    want = sold_lots()
    out = []
    for year in YEARS:
        parids = sorted(want[year])
        for i in range(0, len(parids), BATCH):
            out += pick(fetch(year, parids[i:i + BATCH]))
            print(f"  roll {year}: {min(i + BATCH, len(parids))}/{len(parids)} lots, "
                  f"{len(out)} values", end="\r", flush=True)
        print()
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["parid", "roll_year", "market_value",
                                           "tax_class", "bldg_class", "roll_sqft"])
        w.writeheader()
        w.writerows(sorted(out, key=lambda r: (r["roll_year"], r["parid"])))
    print(f"wrote {len(out)} assessed values to {OUT}")


def test():
    assert bbl("1", "16", "3859") == "1000163859", "bbl padding is wrong"
    assert bbl("2", "4488", "67") == "2044880067", "bbl padding is wrong"

    want = sold_lots()
    assert all(want[y] for y in YEARS), "no sold lots found for a roll year"

    year = YEARS[-1]
    sample = sorted(want[year])[:BATCH]
    rows = pick(fetch(year, sample))
    assert rows, "the roll returned nothing for lots that demonstrably sold"

    # The join has to cover most of what sold, or the rival is being scored on a
    # self-selected sliver of the market rather than against the comps.
    hit = len(rows) / len(sample)
    assert hit > 0.8, f"only {hit:.0%} of sold lots matched the roll"

    assert all(r["roll_year"] == year for r in rows), "a wrong roll year came back"
    assert all(r["market_value"] > 0 for r in rows), "a zero market value survived"

    # A market value is a market value. If these were assessed values, which for tax
    # class 1 are capped at 6% of market, the median would be an order of magnitude low.
    vals = sorted(r["market_value"] for r in rows)
    med = vals[len(vals) // 2]
    assert 100_000 < med < 20_000_000, f"median market value {med:,.0f} is not a price"

    print(f"ok: {len(rows)}/{len(sample)} lots matched roll {year}, "
          f"median market value ${med:,.0f}")


if __name__ == "__main__":
    test() if "--test" in sys.argv else main()
