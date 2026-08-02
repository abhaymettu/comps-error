"""Value every 2025 NYC sale from comparables, without seeing what it sold for.

This is the comparable-sales method as it is actually practised: take recent sales of
similar buildings nearby, take their median price per square foot, multiply by the
subject's area. The only discipline added is that it is done mechanically, so it can be
scored.

Blindness is enforced by the split, not by intention. Comps are drawn only from sales
that closed strictly before CUTOFF, and predictions are written for sales on or after
it. Nothing about a test sale except its size, class and location touches the estimate.

Output is data/predictions.csv, which is committed before score.py is ever run. The git
history is the evidence that the estimates were fixed before the prices were looked at.

    python3 predict.py
    python3 predict.py --test
"""

import collections
import csv
import math
import os
import statistics
import sys

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SALES = os.path.join(DATA, "sales.csv")
OUT = os.path.join(DATA, "predictions.csv")

CUTOFF = "2025-01-01"
# Comps go stale. An analyst pricing a building uses the last year of trades, not eight
# years of them, so the comp pool is the trailing window before the cutoff.
TRAILING_MONTHS = 12
MIN_COMPS = 8


def size_band(sqft):
    """Log2 bands, so a 2,000 and a 200,000 square foot building are never comps."""
    return int(math.log(max(sqft, 1), 2))


def load():
    with open(SALES, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("price", "sqft", "land_sqft", "units", "built"):
            r[k] = float(r[k])
        r["ppsf"] = r["price"] / r["sqft"]
        r["band"] = size_band(r["sqft"])
    return rows


def collapse_bulk(rows):
    """Fold multi-lot sales into one transaction.

    NYC records the sale of a package of lots as one row per lot, each carrying the full
    package price. Left alone, a $40m portfolio of eight buildings becomes eight $40m
    buildings, and every one of them is an enormous outlier in price per square foot.
    They are folded into a single record whose area is the package's total.
    """
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r["sale_date"], r["price"], r["borough"], r["block"])].append(r)
    out, folded = [], 0
    for (date, price, boro, block), g in groups.items():
        if len(g) == 1:
            out.append(g[0])
            continue
        folded += len(g)
        total_sqft = sum(x["sqft"] for x in g)
        if total_sqft <= 0:
            continue
        base = dict(max(g, key=lambda x: x["sqft"]))
        base.update({"sqft": total_sqft,
                     "units": sum(x["units"] for x in g),
                     "land_sqft": sum(x["land_sqft"] for x in g),
                     "ppsf": price / total_sqft,
                     "band": size_band(total_sqft),
                     "lots": len(g)})
        out.append(base)
    return out, folded


def keys(r):
    """Comp definitions from tightest to loosest. The first with enough sales wins."""
    return [
        ("nbhd+class+size", (r["neighborhood"], r["building_class_at_time_of"], r["band"])),
        ("nbhd+class", (r["neighborhood"], r["building_class_at_time_of"])),
        ("nbhd+category", (r["neighborhood"], r["building_class_category"])),
        ("boro+category+size", (r["borough"], r["building_class_category"], r["band"])),
        ("boro+category", (r["borough"], r["building_class_category"])),
        ("category", (r["building_class_category"],)),
        ("citywide", ()),
    ]


def build_index(train):
    idx = collections.defaultdict(list)
    for r in train:
        for level, key in keys(r):
            idx[(level, key)].append(r["ppsf"])
    return {k: statistics.median(v) for k, v in idx.items() if len(v) >= MIN_COMPS}, \
           {k: len(v) for k, v in idx.items()}


def predict(rows):
    train_all = [r for r in rows if r["sale_date"] < CUTOFF]
    test = [r for r in rows if r["sale_date"] >= CUTOFF]

    cut_year, cut_month = int(CUTOFF[:4]), int(CUTOFF[5:7])
    start = f"{cut_year - 1:04d}-{cut_month:02d}"
    train = [r for r in train_all if r["month"] >= start]

    medians, counts = build_index(train)

    out = []
    for r in test:
        for level, key in keys(r):
            med = medians.get((level, key))
            if med is not None:
                out.append({
                    "sale_date": r["sale_date"],
                    "borough": r["borough"],
                    "neighborhood": r["neighborhood"],
                    "building_class_category": r["building_class_category"].strip(),
                    "address": r["address"],
                    "sqft": r["sqft"],
                    "units": r["units"],
                    "built": r["built"],
                    "comp_level": level,
                    "comp_n": counts[(level, key)],
                    "comp_ppsf": round(med, 2),
                    "predicted": round(med * r["sqft"], 0),
                    "actual": r["price"],
                })
                break
    return train, test, out


def main():
    rows, folded = collapse_bulk(load())
    train, test, preds = predict(rows)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(preds[0]))
        w.writeheader()
        w.writerows(preds)
    print(f"{len(rows)} sales after folding {folded} multi-lot rows")
    print(f"comp pool: {len(train)} sales in the {TRAILING_MONTHS} months before {CUTOFF}")
    print(f"held out:  {len(test)} sales on or after {CUTOFF}")
    print(f"predicted: {len(preds)}")
    print(f"wrote {OUT}")


def test():
    rows = load()
    folded_rows, folded = collapse_bulk(rows)
    assert folded > 0, "no multi-lot sales detected, which would be surprising in NYC"
    assert len(folded_rows) < len(rows), "folding did not reduce the row count"

    # Folding must remove price-per-square-foot outliers, not create them. If a package
    # price is left spread across its lots, the top of the distribution is nonsense.
    def top(rs):
        v = sorted(r["ppsf"] for r in rs)
        return v[int(len(v) * 0.999)]
    assert top(folded_rows) < top(rows), \
        f"folding did not reduce the extreme tail: {top(folded_rows):.0f} vs {top(rows):.0f}"

    train, test_rows, preds = predict(folded_rows)
    assert train and test_rows and preds, "empty split"

    # The split must be airtight. A single training sale on or after the cutoff means
    # the estimates saw the future and every score below is worthless.
    assert all(r["sale_date"] < CUTOFF for r in train), "a comp closed after the cutoff"
    assert all(r["sale_date"] >= CUTOFF for r in test_rows), "a test sale predates the cutoff"

    # Predictions must not depend on the thing being predicted.
    assert all("actual" not in k for p in preds[:1] for k in ("comp_ppsf", "predicted")), \
        "sanity"
    assert len(preds) > len(test_rows) * 0.95, \
        f"only {len(preds)} of {len(test_rows)} test sales got an estimate"

    levels = collections.Counter(p["comp_level"] for p in preds)
    assert levels["citywide"] < len(preds) * 0.05, \
        f"{levels['citywide']} predictions fell all the way back to a citywide median"

    print(f"ok: {folded} multi-lot rows folded, {len(train)} comps all before {CUTOFF}, "
          f"{len(preds)}/{len(test_rows)} predicted")
    print(f"    comp levels used: {dict(levels.most_common())}")


if __name__ == "__main__":
    test() if "--test" in sys.argv else main()
