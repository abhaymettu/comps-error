# comps-error

Every commercial real estate valuation starts the same way: find recent sales of similar
buildings nearby, take their price per square foot, multiply by the subject's area. It
is the first number in the memo and often the one the decision rests on.

Nobody publishes how wrong it is.

This measures it. Value every New York City property that sold in a given year using
only sales that closed before that year began, then score the estimates against what the
buildings actually paid. Seven held-out years, 168,178 sales, and two rivals: the market
value the city publishes for free, and a hedonic regression on the same data.

The short version. Comps miss by **19.4%** at the median. The free number the city
publishes misses by **17.7%**, so the workup loses to doing nothing. The error is the
same in every year from 2019 to 2025, so it is not a market condition. It can be trusted
on small buildings with a tight comp set, which is 57% of transactions and **29% of the
dollars**.

## Why the blindness is checkable

The comp pool is drawn strictly from sales dated before the cutoff. Estimates for the
held-out year are written to `data/predictions.csv` and **committed before `score.py`
exists in the repository**. The same discipline holds for everything added since: the
rivals and the extra years went into `data/rivals.csv.gz` in `d91f508`, before
`compare.py` or `safezone.py` were written. The git history is the evidence that the numbers were fixed
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

## Findings, the original single-year run

22,343 held-out 2025 sales, valued from pre-2025 comps. These are the numbers `score.py`
produces from `data/predictions.csv`, kept as they were published. Everything below the
rivals section uses all seven years with the mismeasured unit sales removed, so a few
figures move by a point or two, and the size gradient sharpens rather than softens.

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

Across all seven years, with the mismeasured unit sales out of both the comp pool and
the scored set, the same gradient reads 17.2%, 20.6%, 42.2%, 47.8% and **66.9%**.

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

Complete, and extended. The 2025 estimates were committed in `382233c` before `score.py`
existed. The rivals and the six extra held-out years were committed in `d91f508` before
`compare.py` and `safezone.py` existed, and the clean rerun was committed after the
scorer that reads it, which takes its input file as an argument and has not been touched
since.

**[The memo, with charts](memo/index.html)** is generated by `memo.py` from the frozen
estimates. Every figure on it is computed, none typed in.

## What the rivals cost

Comps had never been measured against anything. Two rivals see the same information:
the market value New York publishes for every tax lot on the roll released before the
year begins, which is free and takes no work, and a hedonic regression fitted on the
same twelve months of sales the comps come from.

| | n | bias | MdAPE | within 10% | within 20% |
|---|---|---|---|---|---|
| comparable sales | 64,063 | -1.9% | **19.9%** | 26.8% | 50.1% |
| hedonic regression | 64,063 | -6.8% | **17.6%** | 29.2% | 55.8% |
| city market value | 64,063 | -5.8% | **17.7%** | 30.8% | 54.5% |

Sales priced by all three, 2023 to 2025, the years the assessment roll covers on the
open data portal.

**The workup loses to the free number.** Not by much, 2.2 points of median absolute
error, but the free number costs nothing and the workup is the billable line item. It is
also better cut by cut: the roll is closer on small buildings and in Queens, Staten
Island and the Bronx, and worse in Manhattan and on anything between 5,000 and 100,000
square feet, where its own bias runs to -45%.

That is not an argument for the assessment roll. It is an argument that the
comparable-sales workup is not buying the accuracy it is assumed to buy.

## Seven held-out years, not one

| holdout | n | bias | MdAPE | within 20% |
|---|---|---|---|---|
| 2019 | 26,576 | -2.5% | 19.5% | 50.9% |
| 2020 | 20,558 | -2.2% | 19.1% | 52.1% |
| 2021 | 29,606 | -6.4% | 18.8% | 52.8% |
| 2022 | 27,174 | -5.9% | 18.9% | 52.4% |
| 2023 | 20,673 | +1.8% | 19.0% | 52.1% |
| 2024 | 21,422 | -3.3% | 20.4% | 49.2% |
| 2025 | 22,169 | -4.3% | 20.4% | 49.2% |

Each year is valued from the twelve months before it. The spread between the best year
and the worst is 1.6 points. The 2020 freeze and the 2021 melt-up do not move it, and
neither does the 2023 rate shock.

**The method is steadily noisy rather than occasionally noisy**, which is the worse of
the two findings. A method that fails in volatile markets can be flagged in volatile
markets. This one is this wide always.

## When is it safe

`safezone.py` cuts the estimates by conditions known before the sale, fits a tolerance
on 2019 to 2023 and checks it on 2024 and 2025. The tolerance is the one a lender
applies rather than a target: median absolute error under 20%, at least half of
estimates within 20% of the price.

Two conditions out of twenty-five pass:

- buildings under 2,000 square feet with a neighbourhood, class and size comp set
- buildings from 2,000 to 5,000 square feet with the same

Held out on 2024 and 2025 the split holds: **16.7%** median absolute error inside the
rule against **27.5%** outside it.

| | share of transactions | share of dollars |
|---|---|---|
| inside the rule | 57% | **29%** |
| outside | 43% | 71% |

So the deliverable is usable and unflattering at the same time. Comps can be trusted on
most of the transaction count and under a third of the money. Nothing rescues the rest:
no comp set, no borough, and not a bigger comp pool either. Within the tightest comp set,
cells with 8 to 19 comps and cells with 100 or more give the same error to within a
point.

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

## A second trap, found while scoring the rivals

New York also records some single-apartment sales against the **building's** tax lot
with the **building's** floor area, and puts the unit number in the address. A $130,000
flat at 200 Central Park West arrives carrying 1,360,264 square feet. Every method here
multiplies an area by a rate, so every method priced it as a tower.

The signature is an apartment designation on a row of 20,000 square feet or more: nine
tenths of those price out under $50 a square foot, against a median of $258 for the rest
of the large-building rows. Unit sales below that size are left alone, since their
median is about $1,000 a square foot, which is what a Manhattan apartment costs.

`rivals.is_unit_sale` finds them. The scoring drops them, and `rivals.py --clean` rebuilds
every estimate with them out of the comp pool as well, because a $4 per square foot sale
sitting in a large-building cell drags the median that every large building in that cell
is valued from. **It costs the method rather than flatters it**: on 100,000 square foot
buildings the median error goes from 55.6% to 66.9% once they are gone. The size gradient
is real, not a data artifact.

## Files

| | |
|---|---|
| `fetch.py` | pull the sales file |
| `predict.py` | the comparable-sales method, and the frozen 2025 estimates |
| `score.py` | scores `data/predictions.csv` |
| `assess.py` | pull the city's published market value for every lot that sold |
| `hedonic.py` | the regression rival, ridge-stabilised normal equations, no dependencies |
| `rivals.py` | all three methods, seven held-out years, frozen to `data/rivals.csv.gz` |
| `compare.py` | scores any of those files, method against method and year against year |
| `safezone.py` | fits and validates the trust rule |
| `memo.py` | builds `memo/index.html` |

Every script takes `--test`. Nothing here has a dependency outside the standard library.
