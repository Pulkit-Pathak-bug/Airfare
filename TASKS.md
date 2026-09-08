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
