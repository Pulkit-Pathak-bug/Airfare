# SIH26056 — project handoff

Status as of the evening of Tuesday 8 September. Read this before touching
anything; it is the fastest way to understand where the project stands.

**Submission: Friday 11 September.**

---

## What we are building

Problem statement 26056, MoSPI (Data Informatics & Innovation Division):
a **real-time airfare price index for India, built from automated web
scraping**, to augment the CPI.

India's CPI collects air fares by hand from a small number of outlets,
while over 90% of domestic tickets sell online, and the same route can
cost three different prices on the same day depending on how far ahead you
book. We collect fares automatically on a fixed sampling grid and compute
a daily index from them.

## The one idea everything rests on

A seat 1 day before departure is not the same product as a seat 45 days
before departure. So "the average fare on DEL–BOM" is not a price index —
it moves when the mix of early and late bookers moves, not when prices
move.

Instead we sample every route at **fixed advance-purchase windows**:
**T+1, T+7, T+15, T+30, T+45**. Holding the booking window constant holds
the product constant, so what is left is price. Each window gets its own
sub-index and they are aggregated.

That is also why automation is necessary rather than merely convenient: a
human price collector cannot observe 5 booking windows across 12 routes
every single day.

**Basket** (both directions, 12 routes, 60 lookups per day, taken verbatim
from the problem statement): DEL–BOM, DEL–BLR, BOM–BLR, DEL–CCU, BLR–HYD,
MAA–DEL.

---

## Where we are

**Collection day 1 is banked: 478 fare offers across 12 routes, 57 of 60
cells filled.** That matters more than it sounds — a collection date
cannot be backfilled, so a day not collected is a point missing from the
series permanently.

Built and working:

- the scraping engine, with a pluggable adapter per airline
- a working scraper against **Akasa Air**
- the fare database: de-duplicated, with base fare / taxes / total kept
  separate, and empty cells recorded rather than silently dropped
- a flat CSV export so nobody downstream needs SQL

Still to build: the index module, the dashboard and API, the 30-day
backtest, compliance documentation, and automated tests.

### First real result

The advance-purchase curve from day one, all routes pooled:

```
T+1     mean fare  11,998
T+7     mean fare   8,971
T+15    mean fare   8,422
T+30    mean fare   9,087
T+45    mean fare  11,273
```

It is a **U** — cheapest around two weeks out, more expensive both
last-minute *and* far in advance. A naive "book early, pay less"
assumption predicts the wrong shape. This is the lead-time elasticity
curve the problem statement asks for, measured on our own data.

---

## Scraper status by carrier

**Akasa Air — working.** Plain HTTP, no browser, no cookies. This is the
source currently collecting.

**IndiGo — blocked.** Sits behind Akamai Bot Manager, which fingerprints
the TLS handshake and requires cookies set by JavaScript, several of them
HttpOnly. Copying headers by hand cannot pass it. A Playwright-based
source (`indigo_browser.py`) was written and does establish a real
session, but IndiGo only mints its bearer token when a search is submitted
through the UI, so it needs form automation to finish. Parked.

**Air India — blocked.** Same Akamai wall, and it holds even with a valid
token *and* a full set of live session cookies. The request builder is
written; the parser is not. Parked.

**SpiceJet — not yet attempted. This is the best next target.** Its
booking API is likely Navitaire, the same platform Akasa runs, which means
the existing parser would probably transfer with only a new endpoint and
payload. Roughly a twenty-minute job if it answers plain HTTP.

**This is a finding, not a failure, and it belongs on a slide.** The two
largest carriers run enterprise bot management; the smaller ones do not.
Our architecture answers both cases — direct HTTP where an API is open, a
real browser session where it is not. Most teams will *claim* to handle
anti-bot measures. We can say which carriers we met it on and what we did
about it.

---

## What is in the repo

```
collect.py                      daily runner: --coverage, --export, --limit
probe.py                        diagnostic: dump a source's raw response
fareindex/config.py             the basket — routes and windows. Edit here only.
fareindex/model.py              FareOffer, the normalised fare record
fareindex/store.py              schema, de-duplicated writes, CSV export
fareindex/sources/base.py       the FareSource interface every source implements
fareindex/sources/akasa.py      WORKING
fareindex/sources/indigo.py     blocked (plain HTTP)
fareindex/sources/indigo_browser.py   blocked (Playwright session)
fareindex/sources/airindia.py   parked, parser unwritten
fareindex/sources/airline_web.py      template for a new carrier
fareindex/sources/serpapi.py    DEV FIXTURE ONLY — never in the index
data/fares_export.csv           day 1 fares, 478 rows
data/akasa_sample.json          a raw response, for anyone writing a parser
TASKS.md                        the work packages
```

### How a source plugs in

Every fare source implements one method, `fetch()`, and returns
`FareOffer` objects. The collector calls `fetch()` and never learns which
airline it is talking to. Adding a carrier is one new file plus one line
in `collect.py` — not a redesign. That is what makes this a multi-source
engine rather than a single scraper, and it is the answer when a judge
asks how you would add another airline.

### Three things the database does deliberately

**Re-running is safe.** A unique constraint means the same offer written
twice stores one row. Correctness lives in the schema, not in application
code, so it holds even when the code is wrong.

**Absence is recorded.** Every attempted cell is logged, including ones
that returned nothing. A missing fare is ambiguous — sold out, cancelled,
or blocked — and an index that silently skips missing cells drifts upward
exactly when cheap seats sell out, which is the worst possible bias for a
price index.

**Fares are one-way.** A return ticket bundles two products and cannot sit
on a single advance-purchase axis.

---

## Running it

```bash
pip install -r requirements.txt
```

Akasa needs an authorization token, which you capture from the site:

1. Go to akasaair.com and search any route.
2. DevTools → Network → Fetch/XHR → find `availability/search`.
3. Copy the `authorization` request header value.
4. Paste it into a file named `.akasa_token` in the repo root.

That file is gitignored and must never be committed.

```bash
py collect.py --source akasa           # collect today
py collect.py --coverage               # what has been collected so far
py collect.py --export                 # refresh data/fares_export.csv
```

**If you are not working on the scraper you need none of that.** Everything
downstream reads one flat file:

```python
import pandas as pd
df = pd.read_csv("data/fares_export.csv")
```

Columns you will use most: `collection_date` (the day we looked),
`departure_date` (the day the flight leaves), `advance_window_days` (the
gap between them — the axis the index is built on), `total_fare_inr`,
`origin`, `destination`, `carrier`, `source_portal`.

One rule for every chart and every index query: filter out
`source_portal == 'serpapi'`. Those rows exist for development only and
must never appear in anything presented.

---

## The daily routine, until Friday

Run the collector **once every day**. Morning is better than evening — a
failed run still leaves the rest of the day to fix it.

```bash
py collect.py --source akasa
py collect.py --export
git add data/fares_export.csv && git commit -m "collection day N"
```

If the token has expired, capture a fresh one; it takes thirty seconds.

Three collection days exist in total: Tuesday, Wednesday, Thursday. There
is no way to add a fourth.

---

## What is outstanding

See `TASKS.md` for the full specifications. In short:

- **Index weights** — the CPI air-fare item weight and DGCA route
  passenger traffic. No coding. Blocks the index module, so it is first.
- **Dashboard and API** — daily index, sector heatmap, lead-time
  elasticity curve. Streamlit, reads the CSV.
- **30-day backtest** — the problem statement never expected us to scrape
  for a month; it expects the index method validated on historical data.
  Needs a dataset with a days-until-departure column.
- **Compliance and documentation** — robots.txt review, rate limiting, the
  ethical-scraping argument. No coding, and worth real marks because most
  teams skip it.
- **Slides** — ten of them, outline in `TASKS.md`.
- **Outlier flagging, coverage report, scraper validation, slide charts,
  weekly/monthly index** — five small self-contained scripts, each with
  runnable starter code in `TASKS.md`, each closing a stated requirement.
- **Manual fare log** — two people collecting fares by hand, timed. It
  gives a validation set, a measured number for the "manual collection
  cannot keep up" claim, and insurance if a scraper fails.

## Deadlines

| When | What |
|---|---|
| Wed 22:00 | index weights, backtest, compliance, outlier + coverage scripts |
| Thu 12:00 | dashboard, slides, charts |
| Thu afternoon | integration, then a full timed dry run of the demo |
| Fri | submit — nothing new gets built on Friday |

If you are stuck for more than an hour, say so in the group. Being stuck
is normal. Being quietly stuck until Thursday is not.
