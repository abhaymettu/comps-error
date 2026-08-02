# comps-error

Every commercial real estate valuation starts the same way: find recent sales of similar
buildings nearby, take their price per square foot, multiply by the subject's area. It
is the first number in the memo and often the one the decision rests on.

Nobody publishes how wrong it is.

This measures it. Value every New York City property that sold in 2025 using only sales
that closed before 2025, then score the estimates against what the buildings actually
paid.

## Why the blindness is checkable

The comp pool is drawn strictly from sales dated before 2025-01-01. Estimates for the
held-out year are written to `data/predictions.csv` and **committed before `score.py`
exists in the repository**. The git history is the evidence that the numbers were fixed
before anyone looked at the answers, which is not something a portfolio piece can
usually demonstrate about itself.

`predict.py --test` asserts the split directly: every comp predates the cutoff, every
scored sale follows it.

## Method

The comparable-sales method, done mechanically so it can be scored. For each subject,
the tightest comp set with at least 8 recent sales wins, falling back down a hierarchy:

1. neighbourhood, building class, size band
2. neighbourhood, building class
3. neighbourhood, building class category
4. borough, category, size band
5. borough, category
6. category
7. citywide

Size bands are log2 of gross square feet, so a 2,000 and a 200,000 square foot building
are never comps for each other. The comp pool is the trailing twelve months before the
cutoff, because that is the window an analyst actually works from.

## Status

Predictions committed. Scoring not yet run.

## Data

NYC Citywide Annualized Calendar Sales, `data.cityofnewyork.us` `w2pb-icbu`, 845,607
recorded sales from 2016 to 2025. Public, no key.

After dropping transfers under $100,000 (nominal conveyances, corrections and
intra-family deed transfers, which are a large share of the file) and records with no
building area, 270,920 sales remain.

## A trap in the source that had to be handled first

New York records the sale of a package of lots as **one row per lot, each carrying the
full package price**. Left alone, a $40m portfolio of eight buildings becomes eight
separate $40m buildings, and every one of them is an enormous outlier in price per
square foot, both in the comp pool and in the scoring set.

6,370 rows are affected. `predict.py` folds them into single transactions whose area is
the package total, and its test asserts that folding shrinks the extreme tail of the
price-per-square-foot distribution rather than growing it.
