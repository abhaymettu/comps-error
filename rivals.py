"""Value seven held-out years three ways, and freeze all of it before scoring.

Three questions the single 2025 run could not answer:

  Is 20% off good or bad?   Nothing was measured against it. Here the same sales are
                            also valued by the city's published market value, which is
                            free and takes no work, and by a hedonic regression fitted
                            on the same twelve-month window the comps use.

  Was 2025 special?         The cutoff rolls back through 2019, so the method is scored
                            in the 2020 freeze, the 2021 melt-up and the 2023 rate shock
                            as well as in a quiet year.

  Where is it safe?         Every estimate keeps the conditions it was made under, so
                            the error can be cut by size, class, borough, comp tightness
                            and comp count rather than reported as one number.

The comps are not reimplemented. `predict.py` is imported and its own `predict()` is
called with the module cutoff rebound, so the estimates for 2025 come out of exactly the
code that produced the frozen `data/predictions.csv`, and the test below asserts they
reproduce it row for row.

Output is data/rivals.csv.gz, committed before compare.py or safezone.py exist, on the same
discipline as the original run.

    python3 rivals.py
    python3 rivals.py --test
"""

import collections
import csv
import gzip
import os
import sys

import hedonic
import predict as comps

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ASSESSED = os.path.join(DATA, "assessed.csv")
OUT = os.path.join(DATA, "rivals.csv.gz")

YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]

COLUMNS = ["holdout", "sale_date", "borough", "neighborhood",
           "building_class_category", "building_class", "address",
           "sqft", "units", "built", "comp_level", "comp_n", "comp_ppsf",
           "comps", "hedonic", "assessed", "actual"]


def lots_by_sale(raw):
    """Which lots made up each recorded transaction, keyed as predict.py folds them."""
    groups = collections.defaultdict(list)
    for r in raw:
        groups[(r["sale_date"], r["price"], r["borough"], r["block"])].append(r["lot"])
    return groups


def assessed_values():
    """parid -> roll year -> the city's market value on the roll published before it."""
    if not os.path.exists(ASSESSED):
        return {}
    out = collections.defaultdict(dict)
    with open(ASSESSED, newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["parid"]][int(r["roll_year"])] = float(r["market_value"])
    return out


def run_year(rows, groups, roll, year):
    """Every estimate for one held-out year, from all three methods."""
    comps.CUTOFF = f"{year}-01-01"
    train, held, preds = comps.predict(rows)

    model = hedonic.fit(train)

    # predict() emits estimates in held-out order, skipping only a sale that matched no
    # comp set at all, so the two lists are walked together rather than joined on
    # address: two lots on one block can share a date, an address and an area.
    pairs, j = [], 0
    for r in held:
        p = preds[j] if j < len(preds) else None
        if p and (p["sale_date"], p["address"], p["sqft"]) == \
                (r["sale_date"], r["address"], r["sqft"]):
            pairs.append((p, r))
            j += 1
    assert j == len(preds), f"{j} of {len(preds)} estimates matched a held-out sale"

    # predict() holds out everything on or after the cutoff. Only the twelve months
    # immediately after it are scored, so each year is valued from comps that are at
    # most a year stale, exactly as the 2025 run was.
    out = []
    for p, r in pairs:
        if r["sale_date"][:4] != str(year):
            continue

        # A package sale is one transaction over several lots, so its assessment is the
        # sum of the lots' assessments, matched to the fiscal roll for the sale year.
        total, complete = 0.0, True
        for lot in groups[(r["sale_date"], r["price"], r["borough"], r["block"])]:
            v = roll.get(f"{int(r['borough'])}{int(r['block']):05d}{int(lot):04d}",
                         {}).get(year)
            if not v:
                complete = False
                break
            total += v

        out.append({
            "holdout": year,
            "sale_date": p["sale_date"],
            "borough": p["borough"],
            "neighborhood": p["neighborhood"],
            "building_class_category": p["building_class_category"],
            "building_class": r["building_class_at_time_of"],
            "address": p["address"],
            "sqft": p["sqft"],
            "units": p["units"],
            "built": p["built"],
            "comp_level": p["comp_level"],
            "comp_n": p["comp_n"],
            "comp_ppsf": p["comp_ppsf"],
            "comps": p["predicted"],
            "hedonic": round(hedonic.predict(model, r), 0),
            "assessed": round(total, 0) if complete and total > 0 else "",
            "actual": p["actual"],
        })
    return out


def main():
    raw = comps.load()
    groups = lots_by_sale(raw)
    rows, folded = comps.collapse_bulk(raw)
    roll = assessed_values()
    print(f"{len(rows)} sales after folding {folded} multi-lot rows, "
          f"{len(roll)} lots with a published market value")

    everything = []
    for year in YEARS:
        got = run_year(rows, groups, roll, year)
        n_assessed = sum(1 for r in got if r["assessed"] != "")
        everything += got
        print(f"  {year}: {len(got):,} estimates, {n_assessed:,} with an assessment")

    with gzip.open(OUT, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(everything)
    print(f"wrote {len(everything):,} rows to {OUT}")


def test():
    raw = comps.load()
    groups = lots_by_sale(raw)
    rows, _ = comps.collapse_bulk(raw)
    roll = assessed_values()

    got = run_year(rows, groups, roll, 2025)
    assert got, "no estimates for 2025"

    # The comps here must be the frozen comps. If this drifts, every year-over-year
    # comparison below is comparing two different methods rather than two markets.
    with open(os.path.join(DATA, "predictions.csv"), newline="") as fh:
        frozen = list(csv.DictReader(fh))
    assert len(got) == len(frozen), f"{len(got)} estimates against {len(frozen)} frozen"
    for r, f in zip(got, frozen):
        assert (r["sale_date"], r["address"]) == (f["sale_date"], f["address"]), \
            f"row order diverged at {r['sale_date']} {r['address']}"
        assert abs(r["comps"] - float(f["predicted"])) < 1, \
            f"{r['address']}: {r['comps']} now against {f['predicted']} frozen"

    # Rolling the cutoff back must actually move the split, not silently reuse 2025.
    early = run_year(rows, groups, roll, 2020)
    assert all(r["sale_date"][:4] == "2020" for r in early), "the 2020 cutoff leaked"
    assert 0.5 < len(early) / len(got) < 2.0, \
        f"{len(early)} estimates in 2020 against {len(got)} in 2025, one year is broken"

    # Every method has to produce a usable number on the same rows, or the comparison
    # is between different populations.
    assert all(r["hedonic"] > 0 for r in got), "a non-positive hedonic estimate"
    with_assess = [r for r in got if r["assessed"] != ""]
    assert len(with_assess) > 0.7 * len(got), \
        f"only {len(with_assess)}/{len(got)} 2025 sales have a published market value"

    print(f"ok: 2025 comps reproduce the frozen file on all {len(got):,} rows, "
          f"{len(with_assess):,} have an assessment, 2020 gives {len(early):,} estimates")


if __name__ == "__main__":
    test() if "--test" in sys.argv else main()
