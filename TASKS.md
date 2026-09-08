# Tasks — week of 8 September

Submission is **Friday 11 September**. Five tasks. Nobody is assigned; put your
name against one by **Tuesday 9:00 AM**.

None of these require you to already know how to do them. Each says what to
learn first and roughly how long that takes. They are ordered easiest to
hardest — pick honestly, not ambitiously, because a task returned unfinished on
Thursday is worse than one nobody claimed on Tuesday.

**You do not need to understand the scraper or SQLite.** Everything below reads
one CSV file, `data/fares_export.csv`, with `pandas.read_csv()`.

---

## T1 — Index weights
**Due Tuesday 22:00 · no programming at all · ~2 hours**

Owner: _______________

The index has to weight routes by how many people actually fly them, and weight
air fares by how much of household spending they represent. Both numbers are
public. Somebody has to go and get them.

**Produce two files:**

1. `data/cpi_airfare_weight.md` — the item-level CPI weight for air fare in the
   2024=100 series, as a single number, with the page you found it on and a
   screenshot.
2. `data/route_weights.csv` — columns `origin,destination,passengers,share`
   for all 12 basket routes, shares summing to 1.

**Where to look:** CPI weights at `esankhyiki.mospi.gov.in` (the dataset link
printed on the problem statement page itself). Route traffic from the GitHub
repo `Vonter/india-aviation-traffic`, file `aggregated/domestic/city.csv` —
monthly city-pair passenger counts, already cleaned from DGCA sources. Use the
most recent 12 months.

**Learn first:** nothing. Excel or Google Sheets is fine.

**Why it's first:** the index cannot be computed until these land. This is the
smallest task here and it blocks the largest one.

---

## T2 — Compliance and documentation
**Due Wednesday 22:00 · no programming · ~3 hours**

Owner: _______________

The problem statement asks for robots.txt compliance, terms-of-service
compliance, rate limiting and "ethical-scraping safeguards" in the same breath
as the technical requirements. Most teams ignore this entirely, which is why
it is worth real marks.

**Produce `docs/compliance.md` containing:**

- For each portal we touch: what its `robots.txt` says, and the date you
  checked. Visit `https://www.goindigo.in/robots.txt` and equivalents — it is
  a plain text file, readable by anyone.
- The request rate we actually use (it is in `fareindex/config.py`,
  `REQUEST_DELAY_SECONDS`).
- The argument for why this is legitimate: public list prices, rate limited,
  honest User-Agent, and production deployment assuming MoSPI-negotiated data
  sharing with the portals. The UK's Office for National Statistics already
  publishes research price indices built from web-scraped data — find that page
  and cite it.

**Learn first:** what a `robots.txt` file is. Fifteen minutes of reading.

---

## T3 — Slides
**Due Thursday 12:00 · no programming · ~4 hours**

Owner: _______________

Ten slides. Follow this outline — it is the argument, in order:

1. CPI collects air fares manually; over 90% of tickets sell online
2. The same route varies 200–400% within one day
3. Why manual collection cannot fix that: 5 windows × 12 routes, every day
4. Our approach: the route × advance-purchase-window grid
5. Architecture: scraper adapters → cleaned database → index → dashboard
6. Live demo
7. The index: Laspeyres, weighted by CPI item weight and DGCA traffic
8. Backtest results
9. Precedent: ONS already does this; MoSPI's own 2024=100 revision explicitly
   admits alternative data sources. We are extending a programme, not
   proposing a novelty.
10. Ethics and compliance

**One rule:** no slide claims a result we do not have. If the backtest is
unfinished, the slide states the method, not an answer.

**You will have to chase people** for their outputs. Take this only if you are
willing to do that chasing on Wednesday, not Thursday morning.

---

## T4 — Dashboard
**Due Thursday 12:00 · light programming · ~6 hours including learning**

Owner: _______________

The most visible thing we ship. The judges will look at this for longer than
they look at the code.

**Produce `dashboard/app.py`**, run with `streamlit run dashboard/app.py`.

**Three charts, from `data/fares_export.csv`:**

1. **Price trend** — the daily index over time. A line.
2. **Sector heatmap** — routes down the side, advance-purchase windows across,
   cheapest fare in each cell.
3. **Lead-time elasticity curve** — the cheapest fare plotted against
   `advance_window_days`. This is the picture our whole sampling design exists
   to produce, so it is the one that proves the method works.

Plus a plain table of the raw rows underneath.

**Learn first:** Streamlit's own "Get started" tutorial, about 30 minutes. It is
the friendliest thing in Python — a chart is genuinely one line:

```python
import streamlit as st
import pandas as pd

df = pd.read_csv("data/fares_export.csv")
st.title("Airfare Price Index")
st.line_chart(df.groupby("collection_date")["total_fare_inr"].min())
st.dataframe(df)
```

That is already a working dashboard. Everything else is refinement.

**Start before the data exists.** Run `python collect.py --export` and you get
the CSV with correct headers even when empty. Make up a few hundred rows in
Excel to build against, then swap to the real file on Thursday morning.

**One rule:** filter out `source_portal == 'serpapi'` in every chart. Those rows
are for development only and must never appear in anything we present.

---

## T5 — Backtest
**Due Wednesday 22:00 · moderate programming · ~6 hours including learning**

Owner: _______________

We will only have three days of live collection, because collection started on
Tuesday and a collection date cannot be backfilled. Three days demonstrates the
collector. It does not demonstrate the index.

So the index gets demonstrated separately, on historical data. This is what the
problem statement means by "30 days of back-tested results" — it never expected
us to scrape for a month.

**Produce `backtest/backtest.py`, `backtest/README.md`, and one chart image.**

**What it does:** load a historical Indian airfare dataset, rename its columns
to match ours, compute the index across at least 30 consecutive days, plot it.

**The dataset must have a days-until-departure column.** Without that our index
cannot be computed on it and the dataset is useless to us however large it is.
The Kaggle "Flight Price Prediction" dataset has a `days_left` column and covers
Indian metros — check its columns yourself before committing to it.

**Do this part first, today:** find out whether DGCA actually publishes a
downloadable monthly average-fare series. The problem statement assumes one
exists. If it does not, say so in the group immediately — it changes what we
are allowed to claim, and discovering it on Thursday would be fatal.

**Learn first:** pandas `read_csv` and `groupby`. Two hours with the official
"10 minutes to pandas" guide gets you there.

---

## T6 — Manual fare log
**Start Tuesday morning · two people · no programming · ~2 hours**

Owners: _______________ and _______________

Collect fares **by hand** today: the same 6 city pairs, the same 5 booking
windows, typed into `data/manual_fares.csv`. Sixty lookups. Use the airline
websites like an ordinary traveller would.

**Time yourselves.** Write down the minutes it took.

Columns, exactly these, so `validate.py` can read it:

```
origin,destination,departure_date,collection_date,advance_window_days,total_fare_inr,carrier
```

**Why this matters more than it looks.** It gives us three things:

- A validation set. "Our scraped fares match human-collected fares on the same
  day" is the answer to the question every judge asks — *how do you know your
  scraper is right?*
- A real number for slide 3. Right now that slide claims manual collection
  cannot keep up. After today it can say "two people took 90 minutes to collect
  one day's basket by hand; the scraper does it in four minutes."
- You will have felt why manual collection fails, which means you can talk
  about it.

Do it today, because it only works as a comparison if it happens on the same
day the scraper runs.

---

# Code tasks

Small, self-contained, and each one closes a requirement the problem statement
asks for and we do not currently meet. All of them read
`data/fares_export.csv` — no SQL, no database, nothing to install beyond pandas.

Every one comes with starter code that runs. You are editing something that
works, not facing a blank file.

**Put your file where the task says. Do not touch anything inside
`fareindex/`** — importing from it is fine, editing it is not.

---

## C1 — Outlier flagging
**Due Wednesday 22:00 · ~2 hours · closes a stated PS requirement**

Owner: _______________

The PS requires the cleaning pipeline to remove outliers. A scraper sometimes
catches a business-class fare or a mispriced seat, and one ₹90,000 row in a cell
of ₹5,000 fares wrecks any average computed over it.

**Produce `clean/outliers.py`** which writes `data/fares_flagged.csv` — the same
rows plus an `is_outlier` column — and prints how many it flagged.

The rule: flag any fare more than 3 median absolute deviations from the median
of its (route, window) group. A rule you can state and defend beats a clever
one.

```python
import pandas as pd

df = pd.read_csv("data/fares_export.csv")
df = df[df.source_portal != "serpapi"]

def flag(group):
    median = group.total_fare_inr.median()
    mad = (group.total_fare_inr - median).abs().median()
    if len(group) < 5 or mad == 0:
        group["is_outlier"] = False        # too few fares to judge
    else:
        group["is_outlier"] = (group.total_fare_inr - median).abs() > 3 * mad
    return group

groups = ["origin", "destination", "advance_window_days"]
out = df.groupby(groups, group_keys=False).apply(flag)
out.to_csv("data/fares_flagged.csv", index=False)
print(f"flagged {out.is_outlier.sum()} of {len(out)} fares")
```

**Note why the grouping is what it is** — a judge may well ask. We pool across
collection days rather than looking at one day in isolation, because a single
(route, window, day) cell holds only about three fares and you cannot measure
spread from three numbers. Pooling gives roughly nine, which is enough. That is
also why the `len(group) < 5` guard is there: with too few observations the rule
either flags nothing or flags everything.

**Then go further:** print *which* fares were flagged and why, so we can show a
judge the rule is removing business-class seats and mispricings rather than
deleting real data.

---

## C2 — Coverage report
**Due Wednesday 22:00 · ~2 hours · closes a stated PS requirement**

Owner: _______________

The PS requires the pipeline to handle missing values. Step one is knowing which
values are missing. We expect 12 routes × 5 windows on every collection day —
which cells did we actually get?

**Produce `clean/coverage.py`**, writing `data/missing_cells.csv` and printing a
completeness percentage.

```python
import sys
import pandas as pd
sys.path.insert(0, ".")
from fareindex import config          # read it, never edit it

df = pd.read_csv("data/fares_export.csv")
days = sorted(df.collection_date.unique())

expected = [
    (o, d, w, day)
    for (o, d) in config.ROUTES
    for w in config.WINDOWS
    for day in days
]
got = set(zip(df.origin, df.destination,
              df.advance_window_days, df.collection_date))
missing = [cell for cell in expected if cell not in got]

print(f"{len(expected) - len(missing)}/{len(expected)} cells filled "
      f"({100 * (1 - len(missing) / len(expected)):.1f}%)")
pd.DataFrame(missing, columns=["origin", "destination",
                               "advance_window_days", "collection_date"]
             ).to_csv("data/missing_cells.csv", index=False)
```

A completeness figure is a good slide on its own — it is the kind of number a
statistics ministry cares about far more than a pretty chart.

---

## C3 — Scraper validation
**Due Thursday 12:00 · ~2 hours · needs T6 to have run**

Owner: _______________

Compare what the scraper collected against what the humans collected on the same
day. This produces the single most useful sentence in the presentation.

**Produce `clean/validate.py`**, writing `data/validation.csv` and printing the
agreement figures.

```python
import pandas as pd

auto = pd.read_csv("data/fares_export.csv")
auto = auto[auto.source_portal != "serpapi"]
manual = pd.read_csv("data/manual_fares.csv")

key = ["origin", "destination", "advance_window_days", "collection_date"]
a = auto.groupby(key).total_fare_inr.min().rename("scraped")
m = manual.groupby(key).total_fare_inr.min().rename("human")

both = pd.concat([a, m], axis=1).dropna()
both["diff_pct"] = 100 * (both.scraped - both.human).abs() / both.human

print(f"{len(both)} cells compared")
print(f"mean absolute difference: {both.diff_pct.mean():.1f}%")
print(f"within 5%: {(both.diff_pct <= 5).mean() * 100:.0f}% of cells")
both.to_csv("data/validation.csv")
```

If the agreement is poor, that is a **finding, not a failure** — report it
immediately. It means the scraper is picking a different fare than a human
would, and we would much rather know that on Thursday morning than be told it
by a judge.

---

## C4 — Charts for the slide deck
**Due Wednesday 22:00 · ~3 hours**

Owner: _______________

The slides need images and should not wait on the dashboard. Separate job,
separate person, no dependency.

**Produce `charts/make_charts.py`** writing three PNGs into `docs/charts/`.

```python
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

os.makedirs("docs/charts", exist_ok=True)
df = pd.read_csv("data/fares_export.csv")
df = df[df.source_portal != "serpapi"]

# 1. Lead-time elasticity: the chart that proves the whole method
curve = df.groupby("advance_window_days").total_fare_inr.min()
ax = curve.plot(marker="o")
ax.set_xlabel("days booked before departure")
ax.set_ylabel("cheapest fare (INR)")
ax.set_title("Fare against advance-purchase window")
plt.tight_layout()
plt.savefig("docs/charts/lead_time.png", dpi=150)
plt.close()
```

Two more: cheapest fare per route as a bar chart, and fares over collection date
as a line. Large fonts — these get projected, and a chart nobody can read from
the back of the room is worth nothing.

---

## C5 — Weekly and monthly index
**Due Thursday 12:00 · ~1 hour · closes a requirement we nearly missed**

Owner: _______________

The PS asks for the index at **daily, weekly and monthly** frequencies. We had
only planned the daily one.

**Produce `index/frequencies.py`** reading `data/apix_daily.csv` (produced by
the index module) and writing `data/apix_weekly.csv` and `data/apix_monthly.csv`.

```python
import pandas as pd

daily = pd.read_csv("data/apix_daily.csv", parse_dates=["date"]).set_index("date")
daily.resample("W").mean().to_csv("data/apix_weekly.csv")
daily.resample("MS").mean().to_csv("data/apix_monthly.csv")
print("wrote weekly and monthly series")
```

That is nearly the whole task. Spend the rest of the hour making it behave
sensibly when there are only three days of data — the weekly figure is one
partial week, and it should be labelled as partial rather than presented as a
full week.

**Not blocked:** if `apix_daily.csv` does not exist yet, make one up with three
columns and ten rows and build against that.

---

## Working in this repo

You do not need to know git well. Four commands cover everything:

```bash
git pull                     # ALWAYS do this before you start working
git add <your files>         # only your own files
git commit -m "what you did"
git push
```

**Rules that prevent the two ways this goes wrong:**

- **Only add your own files.** Never `git add .` — it sweeps up other people's
  work in progress and the database file.
- **Do not edit anything inside `fareindex/`.** That is the collector, and it
  is the critical path. If you think something there needs changing, say so
  rather than changing it.
- **Pull before you start, push when you stop.** A day's work sitting
  uncommitted on your laptop is a day's work nobody else can see.

---

## Deadlines, in one place

| When | What |
|---|---|
| Tue 9:00 | All five tasks have names against them |
| Tue 12:00 | Someone has confirmed 26056 is not on the SPOC's blocked list, and that our faculty mentor is registered |
| Tue 22:00 | T1 weights |
| Wed 22:00 | T2 compliance, T5 backtest |
| Thu 12:00 | T3 slides, T4 dashboard |
| Thu afternoon | Full dry run of the demo, start to finish, timed |
| Fri | Submit. Nothing new gets built on Friday. |

If you are stuck for more than an hour, say so in the group. Being stuck is
normal. Being quietly stuck until Thursday is not.
