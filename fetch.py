"""Pull NYC property sales with the attributes a valuation can be built from.

Source: NYC Citywide Annualized Calendar Sales, `data.cityofnewyork.us` `w2pb-icbu`,
845,607 recorded sales from 2016 to 2025.

Everything kept here is known before a sale closes: size, unit counts, age, building
class, location. Nothing derived from the price is retained beyond the price itself, so
a valuation built on these columns is genuinely working with what an analyst would have
in hand.

    python3 fetch.py
    python3 fetch.py --test
"""

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT = os.path.join(DATA, "sales.csv")
HOST = "data.cityofnewyork.us"
VIEW = "w2pb-icbu"
PAGE = 50000

# Below this a transfer is not a sale. NYC records deed transfers between related
# parties, corrections and nominal conveyances at $0 or $1, and they are a large share
# of the file.
MIN_PRICE = 100_000
MIN_SQFT = 200

FIELDS = ["borough", "neighborhood", "building_class_category",
          "building_class_at_time_of", "tax_class_at_time_of_sale",
          "block", "lot", "address", "zip_code",
          "residential_units", "commercial_units", "total_units",
          "land_square_feet", "gross_square_feet", "year_built",
          "sale_price", "sale_date"]

KEEP = FIELDS + ["price", "sqft", "land_sqft", "units", "built", "year", "month"]


def fetch_page(offset):
    params = {
        "$select": ",".join(FIELDS),
        "$where": f"sale_price > {MIN_PRICE}",
        "$order": "sale_date, block, lot",
        "$limit": PAGE,
        "$offset": offset,
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


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def normalise(raw):
    out = []
    for r in raw:
        price = num(r.get("sale_price"))
        sqft = num(r.get("gross_square_feet"))
        date = (r.get("sale_date") or "")[:10]
        # Gross square feet is text in the published extract and is blank or zero for
        # most condo units, which have no building-level area recorded against the lot.
        if not price or not sqft or not date or sqft < MIN_SQFT:
            continue
        row = {k: (r.get(k) or "") for k in FIELDS}
        row.update({
            "price": price,
            "sqft": sqft,
            "land_sqft": num(r.get("land_square_feet")) or 0,
            "units": num(r.get("total_units")) or 0,
            "built": num(r.get("year_built")) or 0,
            "year": int(date[:4]),
            "month": date[:7],
        })
        row["sale_date"] = date
        out.append(row)
    return out


def main():
    rows, offset = [], 0
    while True:
        raw = fetch_page(offset)
        if not raw:
            break
        rows += normalise(raw)
        offset += PAGE
        print(f"  {offset} scanned, {len(rows)} kept", end="\r", flush=True)
        if len(raw) < PAGE:
            break
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=KEEP, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {len(rows)} sales to {OUT}")


def test():
    raw = fetch_page(0)
    assert raw, "no rows returned"
    rows = normalise(raw)
    assert rows, "everything was filtered out"

    assert all(r["price"] > MIN_PRICE for r in rows), "a sub-threshold price survived"
    assert all(r["sqft"] >= MIN_SQFT for r in rows), "a tiny building survived"

    # Price per square foot must be in a range a real market produces. If the size
    # column is being parsed wrongly this is where it shows.
    ppsf = sorted(r["price"] / r["sqft"] for r in rows)
    med = ppsf[len(ppsf) // 2]
    assert 50 < med < 2000, f"median $/sqft is {med:.0f}, which is not a real market"

    print(f"ok: {len(rows)} of {len(raw)} rows kept, median ${med:,.0f}/sqft")


if __name__ == "__main__":
    test() if "--test" in sys.argv else main()
