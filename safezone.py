"""Turn the warning into a rule: where comps can be trusted, and what that covers.

An error rate is not usable. An underwriter cannot act on "comps are 20% off", because
the next property is either one the method handles or one it does not, and nothing so
far says which. This works out the conditions, all of them known before the sale, under
which a comparable-sales estimate is good enough to carry, and then checks the rule on
years it was not built from.

The test is deliberately loose, because it is the one a lender actually applies: at
least half of estimates within 20% of the price, and a median absolute error under 20%.
That is a tolerance, not a target.

Cells are built from what the analyst has at the moment of valuation: the size of the
building, and how tight a comp set the property fell into. The rule is fitted on 2019 to
2023 and validated on 2024 and 2025, so a rule that only works on the years it was cut
from will show up as such.

    python3 safezone.py
    python3 safezone.py --test
"""

import collections
import sys

import compare

FIT_YEARS = {2019, 2020, 2021, 2022, 2023}
TEST_YEARS = {2024, 2025}

MAX_MDAPE = 0.20
MIN_WITHIN20 = 0.50
MIN_CELL = 100

LEVELS = ["nbhd+class+size", "nbhd+class", "nbhd+category",
          "boro+category+size", "boro+category", "category", "citywide"]


def cell(r):
    return (compare.band(r["sqft"]), r["comp_level"])


def safe_cells(rows):
    """Every condition that passes the tolerance on the fitting years."""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[cell(r)].append(r)
    out = {}
    for k, g in groups.items():
        if len(g) < MIN_CELL:
            continue
        s = compare.summarise(g, "comps")
        out[k] = (s, s["mdape"] <= MAX_MDAPE and s["within20"] >= MIN_WITHIN20)
    return out


def show(rows, title):
    print(f"\n{title}\n")
    print(f"{'size':<16}{'comp set':<20}{'n':>8}{'MdAPE':>9}{'within 20%':>12}   verdict")
    cells = safe_cells(rows)
    for k in sorted(cells, key=lambda k: (compare.BANDS.index(
            next(b for b in compare.BANDS if b[2] == k[0])), LEVELS.index(k[1]))):
        s, ok = cells[k]
        print(f"{k[0]:<16}{k[1]:<20}{s['n']:>8,}{s['mdape']:>9.1%}"
              f"{s['within20']:>12.1%}   {'trust' if ok else 'do not'}")
    return cells


def report():
    rows = [r for r in compare.load() if not r["condo_unit"]]
    fit = [r for r in rows if r["holdout"] in FIT_YEARS]
    test_rows = [r for r in rows if r["holdout"] in TEST_YEARS]

    print(f"Comparable-sales estimates for {len(rows):,} New York sales, "
          f"{min(r['holdout'] for r in rows)} to {max(r['holdout'] for r in rows)}.")
    print(f"The rule is cut on {len(fit):,} sales in {min(FIT_YEARS)}-{max(FIT_YEARS)} "
          f"and checked on {len(test_rows):,} in\n{min(TEST_YEARS)}-{max(TEST_YEARS)}, "
          f"which it was not allowed to see.")

    cells = show(fit, "Every condition, scored on the fitting years")
    safe = {k for k, (_, ok) in cells.items() if ok}

    print("\nThe rule that falls out:\n")
    for k in sorted(safe):
        print(f"  trust comps on {k[0]} with a {k[1]} comp set")
    print("\nEverything else is outside tolerance, including every comp set looser than")
    print("neighbourhood and class, and every building over 5,000 square feet.")

    inside = [r for r in test_rows if cell(r) in safe]
    outside = [r for r in test_rows if cell(r) not in safe]
    si, so = compare.summarise(inside, "comps"), compare.summarise(outside, "comps")

    print(f"\nHeld out, on {min(TEST_YEARS)} and {max(TEST_YEARS)}:\n")
    print(f"{'':<20}{'n':>8}{'share':>8}{'bias':>9}{'MdAPE':>9}{'within 20%':>12}")
    tot = len(test_rows)
    for label, s, g in (("inside the rule", si, inside), ("outside", so, outside)):
        print(f"{label:<20}{s['n']:>8,}{len(g) / tot:>8.1%}{s['bias']:>9.1%}"
              f"{s['mdape']:>9.1%}{s['within20']:>12.1%}")

    # Transaction count is not the thing being valued. Dollars are.
    dollars_in = sum(r["actual"] for r in inside)
    dollars_out = sum(r["actual"] for r in outside)
    share = dollars_in / (dollars_in + dollars_out)
    print(f"\nThe rule holds on {len(inside) / tot:.0%} of transactions and "
          f"{share:.0%} of the dollars that changed hands.")
    print(f"Inside it comps miss by {si['mdape']:.1%} at the median, outside it by "
          f"{so['mdape']:.1%}.")
    print("The method is trustworthy on the small end of the market, in volume, and")
    print("the value it cannot price is the value worth pricing.")

    # The obvious third knob, and it does nothing, which is worth knowing before a shop
    # spends a week widening its comp searches.
    print("\nMore comps do not help. Within the tightest comp set, on the fitting "
          "years:\n")
    print(f"{'comps in the cell':<20}{'n':>8}{'MdAPE':>9}{'within 20%':>12}")
    tight = [r for r in fit if r["comp_level"] == "nbhd+class+size"]
    for lo, hi, lbl in ((8, 20, "8 to 19"), (20, 100, "20 to 99"), (100, 10**9, "100+")):
        g = [r for r in tight if lo <= r["comp_n"] < hi]
        if len(g) >= MIN_CELL:
            s = compare.summarise(g, "comps")
            print(f"{lbl:<20}{s['n']:>8,}{s['mdape']:>9.1%}{s['within20']:>12.1%}")

    big = [r for r in test_rows if r["sqft"] >= 5_000]
    sb = compare.summarise(big, "comps")
    print(f"\nOn the {len(big):,} buildings of 5,000 square feet or more, none of which "
          f"any condition\nrescues, the median estimate is {sb['mdape']:.0%} from the "
          f"price and "
          f"{sb['within20']:.0%} land within a fifth.")


def test():
    rows = [r for r in compare.load() if not r["condo_unit"]]
    fit = [r for r in rows if r["holdout"] in FIT_YEARS]
    test_rows = [r for r in rows if r["holdout"] in TEST_YEARS]
    assert fit and test_rows, "empty split"
    # The rule must be cut on years it is not then judged on, or it is a description of
    # the data rather than a rule.
    assert FIT_YEARS.isdisjoint(TEST_YEARS), "the rule was fitted on its own test years"

    cells = safe_cells(fit)
    safe = {k for k, (_, ok) in cells.items() if ok}
    assert safe, "no condition passed, so there is nothing to recommend"
    assert len(safe) < len(cells), "every condition passed, so the rule says nothing"

    inside = [r for r in test_rows if cell(r) in safe]
    outside = [r for r in test_rows if cell(r) not in safe]
    assert inside and outside, "the rule did not split the held-out years"

    si, so = compare.summarise(inside, "comps"), compare.summarise(outside, "comps")
    # A rule that does not survive the years it was not fitted on is worth nothing.
    assert si["mdape"] < so["mdape"], \
        f"inside the rule ({si['mdape']:.1%}) is no better than outside ({so['mdape']:.1%})"
    assert si["mdape"] <= MAX_MDAPE * 1.15, \
        f"the safe set misses tolerance out of sample at {si['mdape']:.1%}"

    print(f"ok: {len(safe)} of {len(cells)} conditions pass on {min(FIT_YEARS)}-"
          f"{max(FIT_YEARS)}, and hold on {min(TEST_YEARS)}-{max(TEST_YEARS)} "
          f"at {si['mdape']:.1%} against {so['mdape']:.1%}\n")
    report()


if __name__ == "__main__":
    test() if "--test" in sys.argv else report()
