# APIx — Real-time Airfare Price Index

Prototype for **Smart India Hackathon 2026, problem statement 26056** (MoSPI,
Data Informatics & Innovation Division).

India's CPI collects air fares by hand from a small number of outlets, while
over 90% of domestic tickets sell online and the same route can cost three
different prices on the same day depending on how far ahead you book. This
project collects fares automatically, on a fixed sampling grid, and computes a
daily Airfare Price Index from them.

**Status: working prototype.** It collects, it stores, it computes an index.
It is not a production system and does not pretend to be — see *Scope* below.

---

## The one idea

A seat 1 day before departure is not the same product as a seat 45 days before
departure. So "the average fare on DEL–BOM" is not a price index — it moves
when the mix of early and late bookers moves, not when prices move.

Instead we sample every route at **fixed advance-purchase windows**
(T+1, T+7, T+15, T+30, T+45). Holding the booking window constant holds the
product constant, so what remains is price. Each window gets its own sub-index
and the sub-indices are aggregated.

That is also why automation is necessary rather than merely convenient: a human
price collector cannot observe 5 booking windows across 12 routes every day.
A scraper can.

**Basket** (both directions, 12 routes, 60 fare lookups per day):
DEL–BOM, DEL–BLR, BOM–BLR, DEL–CCU, BLR–HYD, MAA–DEL.

Routes and windows are taken verbatim from the problem statement and live in
`fareindex/config.py`.

---

## Quick start

```bash
pip install -r requirements.txt

python collect.py --source airline_web     # collect today's fares
python collect.py --coverage               # what has been collected so far
python collect.py --export                 # write data/fares_export.csv
```

The collector must run **once a day, every day**. A collection date cannot be
backfilled: a day missed is a point missing from the series forever.

### If you are not working on the scraper

You do not need SQLite, and you do not need to run the collector. Everything
downstream reads one flat file:

```python
import pandas as pd
df = pd.read_csv("data/fares_export.csv")
```

One row per observed fare. The columns you will use most:

- `collection_date` — the day we looked
- `departure_date` — the day the flight leaves
- `advance_window_days` — days between them; the axis the index is built on
- `total_fare_inr` — what a traveller actually pays
- `origin`, `destination`, `carrier`, `source_portal`

---

## Layout

```
collect.py                        daily runner + --coverage + --export
fareindex/config.py               the basket: routes and windows
fareindex/model.py                FareOffer — the normalised fare record
fareindex/store.py                database schema, writes, CSV export
fareindex/sources/base.py         the FareSource adapter interface
fareindex/sources/airline_web.py  the airline scraper
fareindex/sources/serpapi.py      development fixture only — NOT a data source
data/fares_export.csv             flat export, regenerated daily
TASKS.md                          who is building what this week
```

### How a source plugs in

Every fare source implements one method, `fetch()`, and returns `FareOffer`
objects. The collector never learns which source it is talking to, so adding a
new portal is a new file plus one line — not a redesign. That is what makes
this a multi-source engine rather than a single scraper.

---

## Data integrity

Three things the database does that are worth knowing about:

**Re-running is safe.** A unique constraint across the identifying columns means
the same offer written twice stores one row. Correctness lives in the database
schema, not in application code, so it holds even when the code is wrong.

**Absence is recorded.** Every cell the collector attempts is logged, including
ones that returned nothing. A missing fare is ambiguous — sold out, cancelled,
or blocked — and an index that silently skips missing cells drifts upward
exactly when cheap seats sell out, which is the worst possible bias for a price
index. So we record the absence instead of losing it.

**Fares are one-way.** A return ticket bundles two products and cannot sit on a
single advance-purchase axis.

---

## Scope

Deliberately **in scope** for this prototype:

- Direct scraping of airline portals
- Daily collection on the PS-specified route × window grid
- Cleaned, de-duplicated fare database with the PS-specified columns
- Daily, weekly and monthly index
- Dashboard with price trends, sector heatmap and lead-time elasticity curve
- Compliance documentation, robots.txt review, rate limiting
- Backtest of the index method on historical fare data

Deliberately **out of scope**, and we will say so rather than imply otherwise:

- **OTA scraping.** The architecture treats an OTA as another source class, but
  we prioritised a working daily index over a second source family.
- **CAPTCHA solving and IP rotation.** We rate-limit and identify ourselves
  honestly instead. A compliant collector at our request volume does not need
  to rotate residential IPs, and doing so would be the wrong precedent for a
  system intended for a statistics ministry.
- **Authentication or scaling on the API.** It is a prototype endpoint.

---

## Ethics

Fares are public list prices. The collector identifies itself in its
User-Agent, rate-limits every request, and respects robots.txt. Production
deployment would assume MoSPI-negotiated data sharing with the portals, which
is how national statistics offices actually run web-scraped price collection —
the UK's ONS publishes research price indices built this way.

See `docs/compliance.md`.

---

## Team

See `TASKS.md`. Read it before asking what to do.
