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

## Findings

22,343 held-out 2025 sales, valued from pre-2025 comps.

| | |
|---|---|
| median signed error | **-4.3%** |
| median absolute error | **20.5%** |
| within 10% of price | 25.5% |
| within 20% of price | 48.9% |
| overvalued by 2x or more | 6.5% |
| undervalued by half or more | 4.0% |

**The method is close to unbiased and individually unreliable, and those are different
failures.** A bias can be corrected with one factor. Dispersion cannot be corrected by
anything. Half of all valuations miss by more than a fifth, one in four lands within a
tenth, and one in sixteen is out by a factor of two or more.

### It fails hardest exactly where institutional money goes

| building size | n | bias | MdAPE | within 10% |
|---|---|---|---|---|
| under 2k sqft | 11,255 | -7.7% | 18.0% | 28.8% |
| 2k to 5k | 9,040 | -0.7% | 21.3% | 24.7% |
| 5k to 20k | 1,376 | +15.5% | 43.9% | 11.5% |
| 20k to 100k | 489 | +17.4% | **61.5%** | 6.5% |
| 100k+ | 183 | +7.8% | 52.4% | 16.9% |

| borough | n | MdAPE | within 10% |
|---|---|---|---|
| Queens | 8,508 | 17.9% | 29.1% |
| Staten Island | 3,638 | 18.4% | 28.4% |
| Bronx | 2,551 | 21.2% | 25.0% |
| Brooklyn | 6,769 | 23.5% | 21.7% |
| **Manhattan** | 877 | **49.6%** | 8.7% |

| building class | n | bias | MdAPE |
|---|---|---|---|
| one family dwellings | 9,828 | -5.1% | 18.1% |
| two family dwellings | 7,250 | -3.8% | 19.4% |
| three family dwellings | 1,991 | -5.8% | 21.0% |
| rentals, walkup | 1,437 | +4.1% | 37.5% |
| store buildings | 459 | -1.3% | 35.5% |
| office buildings | 235 | -15.6% | 43.4% |
| rentals, elevator | 261 | -18.1% | **53.8%** |

The method holds up on small houses in the outer boroughs, which is the bulk of the
transaction count and almost none of the invested capital. On the assets an acquisitions
desk actually buys, elevator apartment buildings, offices, anything over 20,000 square
feet, or anything in Manhattan, the median valuation is wrong by 40% to 60%.

Note also that bias flips sign with size: small properties are undervalued by the method
and large ones overvalued, so a single correction factor applied across a portfolio would
make both worse.

### Better comps help, and less than the effort implies

| comp set | n | bias | MdAPE | within 10% |
|---|---|---|---|---|
| neighbourhood + class + size | 12,936 | -4.7% | 16.9% | 30.6% |
| neighbourhood + class | 3,189 | -5.2% | 24.3% | 21.2% |
| neighbourhood + category | 3,412 | -1.5% | 26.0% | 19.6% |
| borough + category + size | 2,134 | -5.8% | 34.2% | 14.9% |
| borough + category | 521 | +3.9% | 51.1% | 10.0% |

Monotone, so the hierarchy is ordered correctly and comp selection genuinely matters.
But the best comp set available anywhere in this data, same neighbourhood, same building
class, same size band, still misses by 16.9% at the median and lands within a tenth of
the price only 30.6% of the time.

That is the floor, and it is not a comp-selection problem. Two buildings of the same
class and size on the same street do not sell for the same price per square foot.

## Status

Complete. Predictions were committed in `382233c`, before `score.py` existed.

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
