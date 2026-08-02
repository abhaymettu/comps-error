"""A hedonic price regression on the same features, as the second rival.

The comparable-sales method is a local median: it throws away every sale that is not
near the subject and takes the middle of what is left. A hedonic regression is the
opposite trade, it keeps every sale in the window and lets location and class enter as
coefficients rather than as a filter. Same data, same information cut-off, different way
of pooling it. If comps are 20% off, the honest question is whether the alternative any
analyst could run in an afternoon is better or worse.

Log price on log area, log lot area, units, age, and fixed effects for neighbourhood,
building class and borough. Ridge-stabilised normal equations, solved by Gaussian
elimination, no dependencies. Levels seen fewer than MIN_LEVEL times in the training
window are dropped rather than fitted on noise.

Fitted only on sales strictly before the cutoff, from the same trailing window the comps
use, so the two methods see exactly the same market.

    python3 hedonic.py --test
"""

import math
import sys

MIN_LEVEL = 30
# Ridge penalty. Small: it is here to keep a rank-deficient dummy block solvable, not to
# shrink the fit in any way that would matter to the coefficients.
RIDGE = 1e-6


def features(r, levels=None):
    """Sparse feature vector as (name, value) pairs. Names become column indices."""
    f = [("_const", 1.0),
         ("log_sqft", math.log(max(r["sqft"], 1))),
         ("log_land", math.log(max(r["land_sqft"], 1) + 1)),
         ("units", min(r["units"], 200) / 100.0)]
    built = r["built"]
    if built and built > 1700:
        f.append(("age", min(2025 - built, 200) / 100.0))
    else:
        f.append(("age_missing", 1.0))
    for name in (f"nbhd={r['neighborhood']}",
                 f"class={r['building_class_at_time_of']}",
                 f"boro={r['borough']}"):
        if levels is None or name in levels:
            f.append((name, 1.0))
    return f


def solve(a, b):
    """Gaussian elimination with partial pivoting. a is destroyed."""
    n = len(b)
    for col in range(n):
        piv = max(range(col, n), key=lambda i: abs(a[i][col]))
        if abs(a[piv][col]) < 1e-12:
            a[col][col] += 1.0  # dead column, pin its coefficient to zero
            piv = col
        a[col], a[piv] = a[piv], a[col]
        b[col], b[piv] = b[piv], b[col]
        d = a[col][col]
        for i in range(col + 1, n):
            m = a[i][col] / d
            if m:
                row_i, row_c = a[i], a[col]
                for j in range(col, n):
                    row_i[j] -= m * row_c[j]
                b[i] -= m * b[col]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = b[i] - sum(a[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / a[i][i]
    return x


def fit(train):
    counts = {}
    for r in train:
        for name, _ in features(r):
            counts[name] = counts.get(name, 0) + 1
    levels = {k for k, v in counts.items() if v >= MIN_LEVEL}

    cols = {}
    for r in train:
        for name, _ in features(r, levels):
            cols.setdefault(name, len(cols))
    p = len(cols)

    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for r in train:
        vec = [(cols[n], v) for n, v in features(r, levels)]
        y = math.log(r["price"])
        for i, vi in vec:
            xty[i] += vi * y
            row = xtx[i]
            for j, vj in vec:
                row[j] += vi * vj
    for i in range(p):
        xtx[i][i] += RIDGE * len(train)

    beta = solve(xtx, xty)
    return {"cols": cols, "levels": levels, "beta": beta}


def predict(model, r):
    b, cols = model["beta"], model["cols"]
    lp = sum(b[cols[n]] * v for n, v in features(r, model["levels"]) if n in cols)
    # exp of a fitted log price is the median of the implied price distribution, which
    # is the same quantity the comps median estimates. No smearing correction, on
    # purpose: this is the regression an analyst would actually run.
    return math.exp(min(lp, 30))


def test():
    import predict as comps

    rows, _ = comps.collapse_bulk(comps.load())
    start = f"{int(comps.CUTOFF[:4]) - 1:04d}-{comps.CUTOFF[5:7]}"
    train = [r for r in rows if start <= r["sale_date"] < comps.CUTOFF]
    held = [r for r in rows if r["sale_date"] >= comps.CUTOFF]
    assert train and held, "empty split"

    model = fit(train)
    assert len(model["cols"]) > 50, "the design matrix collapsed to almost nothing"

    # Fitting must not have seen the scored year, by construction of the split.
    assert all(r["sale_date"] < comps.CUTOFF for r in train), "a training sale is in the future"

    def mdape(rs):
        e = sorted(abs(predict(model, r) - r["price"]) / r["price"] for r in rs)
        return e[len(e) // 2]

    ins, out = mdape(train), mdape(held)
    # In-sample error is the floor the fit could possibly reach. If held-out error is
    # below it something has leaked; if in-sample is near zero the model is memorising
    # through a dummy per property.
    assert 0.05 < ins < 0.60, f"in-sample MdAPE {ins:.1%} is not a real fit"
    assert out > ins * 0.8, f"held-out MdAPE {out:.1%} beats in-sample {ins:.1%}, so it leaked"

    print(f"ok: {len(model['cols'])} columns on {len(train):,} training sales, "
          f"in-sample MdAPE {ins:.1%}, held-out {out:.1%}")


if __name__ == "__main__":
    if "--test" in sys.argv:
        test()
    else:
        print(__doc__.strip().splitlines()[0])
        print("This is a module. Run --test, or use it from rivals.py.")
