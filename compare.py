"""Score the three methods against each other, in every held-out year.

Written and run after data/rivals.csv.gz was committed. Nothing here can change an
estimate, only measure one.

The 2025 run left two questions open. Is being 20% wrong bad, when nobody had measured
what the alternatives cost? And was 2025 a normal year, or is the whole finding an
artifact of one quiet market?

    python3 compare.py
    python3 compare.py data/clean.csv.gz
    python3 compare.py --test
"""

import collections
import csv
import gzip
import os
import statistics
import sys

import predict as comps_module
import rivals

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RIVALS = os.path.join(DATA, "rivals.csv.gz")


def source(path=None):
    """Which frozen prediction file to score. An explicit path or an argument wins.

    rivals.py also emits data/clean.csv.gz, a rerun with the mismeasured unit sales
    taken out of the comp pool as well as the answer key. Scoring it needs no change
    here, which is the point: the scorer is fixed before that file exists.
    """
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    return path or (args[0] if args else RIVALS)


METHODS = ["comps", "hedonic", "assessed"]
LABEL = {"comps": "comparable sales", "hedonic": "hedonic regression",
         "assessed": "city market value"}

BOROUGH = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn",
           "4": "Queens", "5": "Staten Island"}

BANDS = [(0, 2_000, "under 2k sqft"), (2_000, 5_000, "2k to 5k"),
         (5_000, 20_000, "5k to 20k"), (20_000, 100_000, "20k to 100k"),
         (100_000, 10**12, "100k+")]


def band(sqft):
    return next(lbl for lo, hi, lbl in BANDS if lo <= sqft < hi)


def condo_unit_keys():
    """Sales the source measures wrongly: a unit's price against a building's area.

    See rivals.is_unit_sale. These are dropped from the scoring, because the error they
    generate is a measurement error in the source rather than anything a valuation did.
    Dropping them costs the methods rather than flatters them: it makes the error on
    100,000 square foot buildings worse, not better.
    """
    raw = comps_module.load()
    folded, _ = comps_module.collapse_bulk(raw)
    return {(r["sale_date"], r["borough"], r["address"], r["sqft"])
            for r in folded if rivals.is_unit_sale(r)}


def load(path=None):
    """Every frozen estimate, tagged with whether the source measured the asset."""
    with gzip.open(source(path), "rt", newline="") as fh:
        rows = list(csv.DictReader(fh))
    units = condo_unit_keys()
    for r in rows:
        r["condo_unit"] = (r["sale_date"], r["borough"], r["address"],
                           float(r["sqft"])) in units
        r["holdout"] = int(r["holdout"])
        r["sqft"] = float(r["sqft"])
        r["comp_n"] = int(r["comp_n"])
        r["actual"] = float(r["actual"])
        for m in METHODS:
            v = float(r[m]) if r[m] not in ("", "0", "0.0") else None
            r[m] = v
            r[m + "_err"] = (v - r["actual"]) / r["actual"] if v else None
    return rows


def summarise(rows, method):
    errs = [r[method + "_err"] for r in rows if r[method + "_err"] is not None]
    if not errs:
        return None
    a = [abs(e) for e in errs]
    return {
        "n": len(errs),
        "bias": statistics.median(errs),
        "mdape": statistics.median(a),
        "within10": sum(1 for e in a if e <= 0.10) / len(a),
        "within20": sum(1 for e in a if e <= 0.20) / len(a),
        "over2x": sum(1 for e in errs if e >= 1.0) / len(errs),
        "under_half": sum(1 for e in errs if e <= -0.5) / len(errs),
    }


def row(label, s, width=30):
    if not s:
        return f"{label[:width - 1]:<{width}}{'no coverage':>9}"
    return (f"{label[:width - 1]:<{width}}{s['n']:>8,}{s['bias']:>9.1%}"
            f"{s['mdape']:>9.1%}{s['within10']:>12.1%}{s['within20']:>12.1%}")


def head(title, width=30):
    print(f"\n{title}\n")
    print(f"{'':<{width}}{'n':>8}{'bias':>9}{'MdAPE':>9}{'within 10%':>12}{'within 20%':>12}")


def cut(rows, keyfn, title, order=None, method="comps", floor=50):
    groups = collections.defaultdict(list)
    for r in rows:
        groups[keyfn(r)].append(r)
    head(title)
    for k in (order or sorted(groups, key=lambda k: -len(groups[k]))):
        g = groups.get(k)
        if g and len(g) >= floor:
            print(row(str(k), summarise(g, method)))


def report():
    everything = load()
    rows = [r for r in everything if not r["condo_unit"]]
    dropped = len(everything) - len(rows)
    years = sorted({r["holdout"] for r in rows})
    print(f"{len(rows):,} held-out sales, {years[0]} to {years[-1]}, each valued from "
          f"sales that closed\nin the twelve months before its year began.")
    print(f"{dropped:,} condominium unit sales are excluded: the source puts the whole "
          f"building's\narea on the unit's lot, so every method priced a tower and the "
          f"buyer bought a flat.")

    # Only sales all three methods priced, or the comparison is between populations.
    both = [r for r in rows if all(r[m] is not None for m in METHODS)]
    head("Head to head, on the sales every method priced")
    for m in METHODS:
        print(row(LABEL[m], summarise(both, m)))
    print(f"\n{len(both):,} sales in {min(r['holdout'] for r in both)} to "
          f"{max(r['holdout'] for r in both)}, the years the assessment roll covers.")

    c, h, a = (summarise(both, m) for m in METHODS)
    best = min((c, "comparable sales"), (h, "the hedonic regression"),
               (a, "the city's market value"), key=lambda t: t[0]["mdape"])[1]
    print(f"The work an analyst does by hand is beaten by {best}.")
    print(f"Comps miss by {c['mdape']:.1%} at the median. The assessment roll, which is "
          f"published for\nfree and takes no work at all, misses by {a['mdape']:.1%}. "
          f"A regression on the same\ntwelve months of sales misses by {h['mdape']:.1%}.")

    head("By held-out year, comparable sales")
    for y in years:
        print(row(str(y), summarise([r for r in rows if r["holdout"] == y], "comps")))

    head("By held-out year, city market value")
    for y in years:
        s = summarise([r for r in rows if r["holdout"] == y], "assessed")
        print(row(str(y), s))

    head("By held-out year, hedonic regression")
    for y in years:
        print(row(str(y), summarise([r for r in rows if r["holdout"] == y], "hedonic")))

    worst = max(years, key=lambda y: summarise(
        [r for r in rows if r["holdout"] == y], "comps")["mdape"])
    best_y = min(years, key=lambda y: summarise(
        [r for r in rows if r["holdout"] == y], "comps")["mdape"])
    ws = summarise([r for r in rows if r["holdout"] == worst], "comps")
    bs = summarise([r for r in rows if r["holdout"] == best_y], "comps")
    print(f"\nComps are worst in {worst} at {ws['mdape']:.1%} and best in {best_y} at "
          f"{bs['mdape']:.1%}, a spread of\n{(ws['mdape'] - bs['mdape']) * 100:.0f} "
          f"points across seven years. The 2025 figure is not a one-year accident.")

    for m in METHODS:
        cut(rows, lambda r: band(r["sqft"]), f"By building size, {LABEL[m]}",
            order=[b[2] for b in BANDS], method=m)

    cut(rows, lambda r: BOROUGH.get(r["borough"].strip(), r["borough"]),
        "By borough, comparable sales", order=list(BOROUGH.values()))
    cut(both, lambda r: BOROUGH.get(r["borough"].strip(), r["borough"]),
        "By borough, city market value", order=list(BOROUGH.values()), method="assessed")

    cut(rows, lambda r: r["comp_level"], "By how tight the comp set was",
        order=["nbhd+class+size", "nbhd+class", "nbhd+category", "boro+category+size",
               "boro+category", "category", "citywide"])

    big = [r for r in both if r["sqft"] >= 20_000]
    if len(big) >= 50:
        cb, ab = summarise(big, "comps"), summarise(big, "assessed")
        print(f"\nOn buildings over 20,000 square feet, {len(big):,} of them, comps miss "
              f"by {cb['mdape']:.1%}\nand the free number misses by {ab['mdape']:.1%}.")


def test():
    everything = load()
    flagged = [r for r in everything if r["condo_unit"]]
    rows = [r for r in everything if not r["condo_unit"]]
    assert len(rows) > 100_000, f"only {len(rows)} rows"

    # The condo-unit rule has to be picking out mismeasured rows, not arbitrary ones.
    # A price per square foot of a few dollars is the signature: a unit's price over a
    # building's area. Real New York trades in the hundreds.
    ppsf = sorted(r["actual"] / r["sqft"] for r in flagged)
    assert ppsf, "the condo-unit rule matched nothing"
    assert ppsf[len(ppsf) // 2] < 60, \
        f"flagged rows trade at ${ppsf[len(ppsf) // 2]:,.0f}/sqft, so the rule is wrong"
    kept = sorted(r["actual"] / r["sqft"] for r in rows)
    assert kept[len(kept) // 2] > 100, "the kept rows do not look like a real market"

    years = sorted({r["holdout"] for r in rows})
    assert len(years) >= 6, f"only {len(years)} held-out years"
    # Each year must be scored against sales from that year only. A cutoff that leaked
    # forward would put later sales in an earlier year's holdout.
    assert all(r["sale_date"][:4] == str(r["holdout"]) for r in rows), \
        "a sale is scored in the wrong holdout year"

    assert all(r["actual"] > 0 for r in rows), "a non-positive sale price"
    assert all(r["comps"] > 0 for r in rows), "a non-positive comp estimate"

    # A method is only comparable to another on rows where both priced the property.
    both = [r for r in rows if all(r[m] is not None for m in METHODS)]
    assert len(both) > 50_000, f"only {len(both)} sales priced by all three"
    for m in METHODS:
        s = summarise(both, m)
        assert 0.02 < s["mdape"] < 0.90, f"{m} MdAPE {s['mdape']:.1%} is not credible"
        assert s["within10"] < 0.80, f"{m} within-10% of {s['within10']:.1%} suggests a leak"

    # The assessment roll is only joined where a roll exists, 2023 onward. If it shows
    # up in 2020 the roll year was matched wrongly and the rival saw the future.
    have = {r["holdout"] for r in rows if r["assessed"] is not None}
    assert have == {2023, 2024, 2025}, f"assessments present in {sorted(have)}"

    print(f"ok: {len(rows):,} estimates over {years[0]}-{years[-1]}, "
          f"{len(both):,} priced three ways, no year mismatch\n")
    report()


if __name__ == "__main__":
    test() if "--test" in sys.argv else report()
