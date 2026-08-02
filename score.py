"""Score the frozen estimates against what the buildings actually sold for.

Written and run after data/predictions.csv was committed. Nothing here can change an
estimate, only measure one.

Two numbers matter and they are different questions:

  bias        median signed error. Does the method run high or low overall, which a
              shop could correct for with a single factor.
  dispersion  median absolute error. How wrong an individual valuation is, which no
              factor corrects and which is what an underwriter actually carries.

A method can be perfectly unbiased and still useless, and that turns out to be roughly
the situation.

    python3 score.py
    python3 score.py --test
"""

import collections
import csv
import os
import statistics
import sys

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PREDICTIONS = os.path.join(DATA, "predictions.csv")

BOROUGH = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn",
           "4": "Queens", "5": "Staten Island"}

BANDS = [(0, 2_000, "under 2k sqft"), (2_000, 5_000, "2k to 5k"),
         (5_000, 20_000, "5k to 20k"), (20_000, 100_000, "20k to 100k"),
         (100_000, 10**12, "100k+")]


def load():
    with open(PREDICTIONS, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["predicted"] = float(r["predicted"])
        r["actual"] = float(r["actual"])
        r["sqft"] = float(r["sqft"])
        r["err"] = (r["predicted"] - r["actual"]) / r["actual"]
        r["abs_err"] = abs(r["err"])
    return rows


def summarise(rows):
    errs = [r["err"] for r in rows]
    abs_errs = [r["abs_err"] for r in rows]
    return {
        "n": len(rows),
        "bias": statistics.median(errs),
        "mdape": statistics.median(abs_errs),
        "within10": sum(1 for e in abs_errs if e <= 0.10) / len(rows),
        "within20": sum(1 for e in abs_errs if e <= 0.20) / len(rows),
        "over2x": sum(1 for r in rows if r["predicted"] > 2 * r["actual"]) / len(rows),
        "under_half": sum(1 for r in rows if r["predicted"] < 0.5 * r["actual"]) / len(rows),
    }


def table(rows, keyfn, label, order=None):
    groups = collections.defaultdict(list)
    for r in rows:
        groups[keyfn(r)].append(r)
    keys = order or sorted(groups, key=lambda k: -len(groups[k]))
    print(f"\n{label}\n")
    print(f"{'':<26}{'n':>7}{'bias':>9}{'MdAPE':>9}{'within 10%':>12}{'within 20%':>12}")
    for k in keys:
        g = groups.get(k)
        if not g or len(g) < 50:
            continue
        s = summarise(g)
        print(f"{str(k)[:25]:<26}{s['n']:>7,}{s['bias']:>8.1%}{s['mdape']:>9.1%}"
              f"{s['within10']:>11.1%}{s['within20']:>11.1%}")


def report():
    rows = load()
    s = summarise(rows)

    print(f"Comparable-sales valuation, {s['n']:,} New York City sales in 2025,")
    print("valued from sales that closed before 2025.\n")
    print(f"  median signed error   {s['bias']:+.1%}")
    print(f"  median absolute error {s['mdape']:.1%}")
    print(f"  within 10% of price   {s['within10']:.1%}")
    print(f"  within 20% of price   {s['within20']:.1%}")
    print(f"  overvalued by 2x+     {s['over2x']:.1%}")
    print(f"  undervalued by half   {s['under_half']:.1%}")

    print(f"\nThe method is close to unbiased and individually unreliable. Half of all")
    print(f"valuations miss by more than {s['mdape']:.0%}, and only {s['within10']:.0%} land "
          f"within a tenth of the price.")
    print("Those are different failures. A bias can be corrected with one factor. This")
    print("dispersion cannot be corrected by anything, and it is what sits underneath a")
    print("valuation presented to an investment committee as a single number.")

    table(rows, lambda r: r["comp_level"], "By how tight the comp set was",
          order=["nbhd+class+size", "nbhd+class", "nbhd+category",
                 "boro+category+size", "boro+category", "category", "citywide"])
    table(rows, lambda r: BOROUGH.get(r["borough"].strip(), r["borough"]),
          "By borough", order=list(BOROUGH.values()))
    table(rows, lambda r: next(lbl for lo, hi, lbl in BANDS if lo <= r["sqft"] < hi),
          "By building size", order=[b[2] for b in BANDS])
    table(rows, lambda r: r["building_class_category"], "By building class category")

    tight = [r for r in rows if r["comp_level"] == "nbhd+class+size"]
    loose = [r for r in rows if r["comp_level"] in ("category", "citywide",
                                                    "boro+category")]
    if tight and loose:
        t, l = summarise(tight), summarise(loose)
        print(f"\nTighter comps help, and less than the effort implies: MdAPE "
              f"{t['mdape']:.1%} on the")
        print(f"closest comp set against {l['mdape']:.1%} on the loosest, a gap of "
              f"{(l['mdape'] - t['mdape']) * 100:.0f} points.")
        print("The floor is not comp selection. It is that two buildings of the same")
        print("class, size and street do not sell for the same price per square foot.")


def test():
    rows = load()
    assert len(rows) > 10000, f"only {len(rows)} predictions"

    # Errors must be computable and finite, or the summary is meaningless.
    assert all(r["actual"] > 0 for r in rows), "a non-positive sale price survived"
    assert all(r["predicted"] > 0 for r in rows), "a non-positive estimate"

    s = summarise(rows)
    # A comps method should be roughly unbiased by construction, since it is a median of
    # like properties. A large bias means the comp pool and the test set are not
    # comparable populations, most likely a stale trailing window.
    assert abs(s["bias"]) < 0.25, f"median signed error is {s['bias']:+.1%}, too large"

    # And it must be materially worse than a coin flip on accuracy, or something has
    # leaked from the test set into the comps.
    assert s["within10"] < 0.60, \
        f"{s['within10']:.1%} of estimates within 10% suggests the split leaked"
    assert s["mdape"] > 0.05, f"MdAPE of {s['mdape']:.1%} is implausibly good"

    # Tighter comps should not be worse than looser ones. If they are, the hierarchy is
    # ordered wrongly and the whole fallback design is backwards.
    tight = summarise([r for r in rows if r["comp_level"] == "nbhd+class+size"])
    loose = summarise([r for r in rows if r["comp_level"] in ("category", "citywide")])
    assert tight["mdape"] < loose["mdape"], (
        f"tight comps ({tight['mdape']:.1%}) are worse than loose ones "
        f"({loose['mdape']:.1%}), so the hierarchy is inverted")

    print(f"ok: {len(rows):,} estimates, bias {s['bias']:+.1%}, MdAPE {s['mdape']:.1%}, "
          f"tight comps beat loose\n")
    report()


if __name__ == "__main__":
    test() if "--test" in sys.argv else report()
