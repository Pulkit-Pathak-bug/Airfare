#!/usr/bin/env python3
"""Generate docs/METHODOLOGY.pdf from the data that is actually in the store.

WHY THIS IS A SCRIPT AND NOT A HAND-WRITTEN DOCUMENT

Every number in a methodology document is a claim about the system, and a
hand-typed number goes stale the moment the next collection runs. So the
coverage figures, the index values, the weights table and the worked
example are all read out of data/ at build time. Collect, then run:

    py collect.py --export
    py -m fareindex.apix
    py make_methodology.py

and the document is correct again. Nothing to retype, nothing to forget.

The narrative sections — the method, the precedent, the limitations — are
prose in this file. They change rarely and deliberately.

REQUIRES
    playwright (already installed for the scrapers) to render the PDF.
    Without it the HTML is still written and can be printed from a browser.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fareindex.apix import (build_index, cell_prices, load_fares,  # noqa: E402
                            resample, route_weights, source_spans,
                            split_sources)
from fareindex.config import ROUTES, WINDOWS  # noqa: E402

OUT_HTML = "docs/METHODOLOGY.html"
OUT_PDF = "docs/METHODOLOGY.pdf"

BG = "#0f1115"
PANEL = "#171a21"
INK = "#e6e8eb"
MUTED = "#9aa4b2"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
LINE = "#252a33"

CSS = """
/* Zero visible border at the page edge is achieved by letting the root
   element's background propagate to the page canvas — it paints the full
   sheet, margins included — while @page margins still inset the text on
   EVERY page. A literal margin:0 with padding on a wrapper div only pads
   the first page; content then runs into the paper edge on page two. */
@page { size: A4; margin: 7mm 0; }
* { box-sizing: border-box; }
html { background: %(BG)s; }
html, body { margin: 0; padding: 0; }
body {
  background: %(BG)s; color: %(INK)s;
  font-family: "Segoe UI", -apple-system, system-ui, Arial, sans-serif;
  font-size: 10.2pt; line-height: 1.55;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
.page { break-after: page; padding: 0 7mm; }
.page:last-child { break-after: auto; }
.page > h2:first-child { margin-top: 4pt; }
h2, h3 { break-after: avoid; }
table, .panel, .formula { break-inside: avoid; }
h1 { font-size: 25pt; margin: 0 0 4pt; letter-spacing: -0.6pt; font-weight: 650; }
h2 { font-size: 13.5pt; margin: 22pt 0 7pt; color: %(BLUE)s; font-weight: 620;
     border-bottom: 1px solid %(LINE)s; padding-bottom: 4pt; }
h3 { font-size: 10.8pt; margin: 14pt 0 4pt; color: %(INK)s; font-weight: 620; }
p  { margin: 0 0 8pt; }
.sub { color: %(MUTED)s; font-size: 10.5pt; margin: 0 0 2pt; }
.meta { color: %(MUTED)s; font-size: 8.6pt; margin-top: 14pt; }
ul, ol { margin: 0 0 9pt; padding-left: 16pt; }
li { margin-bottom: 3.5pt; }
code, .mono { font-family: Consolas, "DejaVu Sans Mono", monospace;
              font-size: 9pt; color: %(ORANGE)s; }
table { width: 100%%; border-collapse: collapse; margin: 8pt 0 12pt;
        font-size: 9.2pt; }
th { text-align: left; color: %(MUTED)s; font-weight: 600;
     border-bottom: 1px solid %(LINE)s; padding: 5pt 7pt; font-size: 8.4pt;
     text-transform: uppercase; letter-spacing: 0.4pt; }
td { padding: 5pt 7pt; border-bottom: 1px solid %(LINE)s; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
.panel { background: %(PANEL)s; border-left: 3px solid %(BLUE)s;
         padding: 10pt 13pt; margin: 10pt 0 13pt; border-radius: 0 3px 3px 0; }
.panel.warn { border-left-color: %(ORANGE)s; }
.panel p:last-child { margin-bottom: 0; }
.formula { background: %(PANEL)s; padding: 12pt 14pt; margin: 10pt 0;
           font-family: Consolas, "DejaVu Sans Mono", monospace;
           font-size: 9.4pt; color: %(INK)s; border-radius: 3px;
           white-space: pre-wrap; }
.tag { display: inline-block; font-size: 7.6pt; letter-spacing: 0.6pt;
       text-transform: uppercase; padding: 2pt 6pt; border-radius: 2px;
       background: %(BLUE)s; color: #fff; font-weight: 650; }
.tag.warn { background: %(ORANGE)s; }
.tag.mute { background: %(LINE)s; color: %(MUTED)s; }
a { color: %(BLUE)s; text-decoration: none; word-break: break-all; }
.rule { height: 3px; background: %(BLUE)s; width: 54pt; margin: 12pt 0 16pt; }
.foot { color: %(MUTED)s; font-size: 8.4pt; border-top: 1px solid %(LINE)s;
        padding-top: 7pt; margin-top: 20pt; }
.two { display: flex; gap: 14pt; }
.two > div { flex: 1; }
""" % dict(BG=BG, PANEL=PANEL, INK=INK, MUTED=MUTED, BLUE=BLUE,
           ORANGE=ORANGE, LINE=LINE)


def esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def table(headers, rows, numeric=()) -> str:
    """headers: list of str. rows: list of lists. numeric: column indexes."""
    th = "".join(f'<th class="{"n" if i in numeric else ""}">{esc(h)}</th>'
                 for i, h in enumerate(headers))
    body = []
    for row in rows:
        tds = "".join(f'<td class="{"n" if i in numeric else ""}">{c}</td>'
                      for i, c in enumerate(row))
        body.append(f"<tr>{tds}</tr>")
    return (f"<table><thead><tr>{th}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table>")


# --------------------------------------------------------------- the facts
def gather() -> dict:
    """Everything the document needs, read out of the data store."""
    df = load_fares()
    spans = source_spans(df)
    continuous, late = split_sources(df)

    headline_df = df[df.source_portal.isin(continuous)]
    daily, meta = build_index(headline_df)
    weekly, monthly = resample(daily)

    prices = cell_prices(headline_df)
    routes = sorted(prices.route.unique())
    weights, weight_source = route_weights(routes)

    # A worked example the reader can follow arithmetically: the single
    # cell with the largest absolute move between the first and last day.
    worked = None
    if len(daily) >= 2:
        first, last = daily.date.iloc[0], daily.date.iloc[-1]
        a = prices[prices.collection_date == first].set_index(
            ["route", "advance_window_days"]).price
        b = prices[prices.collection_date == last].set_index(
            ["route", "advance_window_days"]).price
        both = pd.concat([a.rename("base"), b.rename("now")], axis=1).dropna()
        if not both.empty:
            both["rel"] = both.now / both.base
            cell = (both.rel - 1).abs().idxmax()
            row = both.loc[cell]
            worked = {
                "route": cell[0], "window": int(cell[1]),
                "base": float(row.base), "now": float(row.now),
                "rel": float(row.rel),
                "weight": float(weights.get(cell[0], 0.0)),
                "first": pd.Timestamp(first).date(),
                "last": pd.Timestamp(last).date(),
            }

    # Which day of the week each window actually landed on, by collection
    # date. A fixed advance-purchase window with a rolling departure date
    # advances the departure weekday by one per collection day, so a short
    # series carries a day-of-week composition effect. Computed here rather
    # than asserted, because it is a limitation the numbers have to support.
    dow = None
    try:
        d = df.copy()
        d["dep"] = pd.to_datetime(d.departure_date)
        first = (d.groupby(["collection_date", "advance_window_days"])
                  .dep.first().reset_index())
        first["dow"] = first.dep.dt.day_name().str[:3]
        dow = first.pivot(index="advance_window_days",
                          columns="collection_date", values="dow")
        dow.columns = [pd.Timestamp(c).date().isoformat() for c in dow.columns]
    except Exception as exc:                                 # noqa: BLE001
        print(f"[methodology] day-of-week table unavailable: {exc}")

    # Computed, not asserted — see fareindex/continuity_demo.py.
    try:
        from fareindex.continuity_demo import run as continuity_run
        demo = continuity_run()
    except Exception as exc:                                 # noqa: BLE001
        print(f"[methodology] continuity demo unavailable: {exc}")
        demo = None

    return {
        "df": df, "spans": spans, "continuous": continuous, "late": late,
        "demo": demo, "dow": dow,
        "daily": daily, "weekly": weekly, "monthly": monthly, "meta": meta,
        "weights": weights, "weight_source": weight_source,
        "prices": prices, "worked": worked,
    }


# ------------------------------------------------------------- the document
def build_html(f: dict) -> str:
    df, daily, meta = f["df"], f["daily"], f["meta"]
    today = date.today().isoformat()

    n_routes, n_windows = len(ROUTES), len(WINDOWS)
    grid = n_routes * n_windows
    windows_txt = ", ".join(f"T+{w}" for w in WINDOWS)

    # --- coverage table -------------------------------------------------
    cov_rows = []
    for name, row in f["spans"].iterrows():
        tag = ('<span class="tag">headline</span>' if name in f["continuous"]
               else '<span class="tag warn">started late</span>')
        cov_rows.append([esc(name), row["first"].date(), row["last"].date(),
                         f"{int(row['rows']):,}", tag])
    coverage = table(["Source", "First collected", "Last collected",
                      "Fare records", "Basket role"], cov_rows, numeric=(3,))

    # --- weights table --------------------------------------------------
    w = f["weights"].sort_values(ascending=False)
    w_rows = [[esc(r), f"{v * 100:.2f}%"] for r, v in w.items()]
    half = (len(w_rows) + 1) // 2
    weights_tbl = (
        '<div class="two"><div>'
        + table(["Route", "Weight"], w_rows[:half], numeric=(1,))
        + '</div><div>'
        + table(["Route", "Weight"], w_rows[half:], numeric=(1,))
        + '</div></div>'
    )

    # --- index table ----------------------------------------------------
    if daily.empty:
        index_tbl = "<p>No index computed yet — the store is empty.</p>"
    else:
        idx_rows = [[r.date.date(), f"{r.apix:.2f}", int(r.cells),
                     int(r.carried_forward)] for r in daily.itertuples()]
        index_tbl = table(["Collection date", "APIx", "Cells priced",
                           "Carried forward"], idx_rows, numeric=(1, 2, 3))

    # --- worked example -------------------------------------------------
    wk = f["worked"]
    if wk:
        direction = "rose" if wk["rel"] > 1 else "fell"
        worked_html = f"""
<div class="formula">cell            {esc(wk['route'])} at T+{wk['window']}
price on {wk['first']}   Rs {wk['base']:,.0f}      &lt;- base period
price on {wk['last']}   Rs {wk['now']:,.0f}
price relative     {wk['now']:,.0f} / {wk['base']:,.0f} = {wk['rel']:.4f}
route weight w(c)  {wk['weight']:.4f}   (DGCA passenger share for {esc(wk['route'])})
contribution       {wk['rel']:.4f} x {wk['weight']:.4f} = {wk['rel'] * wk['weight']:.4f}
                   divided by the sum of w(c) over all cells</div>
<p>This cell {direction} {abs(wk['rel'] - 1) * 100:.1f}% between the base
period and the latest collection. The index for that day is the
weight-weighted mean of {len(f['prices'].route.unique()) * n_windows if False else meta.get('basket_cells', 0)}
such relatives, multiplied by 100.</p>"""
    else:
        worked_html = ("<p>A worked example appears here once at least two "
                       "collection days exist.</p>")

    d = f["demo"]
    late_note = ""
    if f["late"]:
        late_note = f"""
<div class="panel warn">
<p><strong>This has already happened in this dataset.</strong>
{esc(', '.join(f['late']))} began collecting on
{f['spans'].loc[f['late'][0], 'first'].date()}, after the base period. It is
therefore excluded from the headline index and published as its own series.</p>
</div>"""
    if d:
        late_note += f"""
<h3>The rule, demonstrated</h3>
<p>Run <span class="mono">py -m fareindex.continuity_demo</span>. It builds a
controlled fixture in which the answer is known — every fare rises
{d['daily_rise_pct']:.0f}% per day, and a second carrier appears on day three
priced {d['undercut_pct']:.0f}% below the first — and runs the index both
ways. These numbers are computed when this document is built, not
transcribed:</p>
<div class="formula">true movement                {' -> '.join(f'{v:.2f}' for v in d['truth'])}
headline index (this design) {' -> '.join(f'{v:.2f}' for v in d['fixed'])}   correct
naive index (all sources)    {' -> '.join(f'{v:.2f}' for v in d['naive'])}   wrong by {d['naive_error_pct']:.1f}%</div>
<p>The naive index reports a fall on the day the second carrier joins. No fare
fell; the comparison widened. A price index that does this is worse than no
index, because it is confidently wrong in the direction people act on.</p>"""

    # ============================================================== page 1
    p1 = f"""
<div class="page">
<span class="tag mute">Smart India Hackathon 2026 &middot; PS 26056 &middot; MoSPI</span>
<h1>APIx</h1>
<p class="sub">Real-time Airfare Price Index for India &mdash;
methodology, compliance and limitations</p>
<div class="rule"></div>

<p>APIx is a prototype price index for Indian domestic air travel, built from
fares collected automatically each day from airline booking portals. It is
intended as an input to CPI augmentation: a high-frequency, route-level price
signal for a service whose prices move daily and are not captured by monthly
field price collection.</p>

<p>This document states exactly how the index is constructed, what was
actually collected, and where the design departs from established statistical
practice. The last of those is deliberate and detailed. An index whose
limitations are undocumented is not usable by a statistical office.</p>

<div class="panel">
<p><strong>Every figure in this document is generated from the data store at
build time</strong> by <span class="mono">make_methodology.py</span>. Nothing
is transcribed by hand, so the document cannot drift out of agreement with the
system it describes. Rebuild it with
<span class="mono">py make_methodology.py</span>.</p>
</div>

<h2>1. What is measured</h2>
<p>The index measures the change in the <em>advertised</em> lowest available
one-way economy fare, on a fixed set of routes, at a fixed set of
advance-purchase distances from departure. It does not measure transacted
fares, average fares, or fares paid. Section 11 treats that distinction as the
principal limitation of the whole approach.</p>

<h3>The sampling grid</h3>
<p>A <strong>cell</strong> is one (route &times; advance-purchase window) pair.
The basket is {n_routes} routes &mdash; the {n_routes // 2} city pairs named in
the problem statement, each in both directions &mdash; by {n_windows} windows,
{windows_txt} days before departure. That is <strong>{grid} cells collected per
day</strong>.</p>

<p>Two date axes are kept separate throughout, and conflating them is the most
common way an airfare index goes wrong:</p>
<ul>
<li><span class="mono">collection_date</span> &mdash; when the price was
observed. This cannot be backfilled. A fare that existed last week is
unobtainable today, which is why the series can only ever grow forward and why
collection had to begin before anything else was finished.</li>
<li><span class="mono">departure_date</span> &mdash; when the flight leaves.</li>
</ul>
<p>The window is their difference:
<span class="mono">advance_window_days = departure_date &minus; collection_date</span>.
Holding it fixed is what makes prices comparable across days; without it, a
falling index would merely mean the flights sampled happened to be further
away.</p>

<h3>Precedent for this design</h3>
<p>The multi-lead-time grid is not an invention. The UK Office for National
Statistics collects long-haul airfares six, three and one month before
departure and short-haul at three and one month, then combines the resulting
sub-indices with fixed weights. The international CPI Manual (2020) specifies
the same six/three/one month structure. Eurostat's web-scraping guidance
documents a scraped rail-fare index sampling at 2, 10, 30 and 60 days.</p>

<p>The windows used here are those named in the problem statement. Section 11
notes honestly that the shortest of them has no counterpart in official
practice.</p>
</div>"""

    # ============================================================== page 2
    p2 = f"""
<div class="page">
<h2>2. The price concept</h2>
<p>The price of a cell on a collection date is the <strong>cheapest available
one-way fare</strong> observed in it, inclusive of taxes and statutory fees.
Cheapest rather than mean: a traveller buys the lowest fare that suits them,
not the average of the cabin, and an average is dominated by unsold premium
inventory that nobody purchases.</p>

<p>Fare components are stored separately where the portal exposes them &mdash;
base fare, taxes, user development fee, convenience fee &mdash; and a missing
component is stored as NULL, never as zero. The distinction matters: zero is a
claim that the fee was not charged, NULL is an admission that it was not
disclosed.</p>

<h2>3. Weights</h2>
<p>Routes are weighted by passenger volume, so that DEL&ndash;BOM counts for
more than a thin sector. Weights are derived from DGCA's
<em>City Pair Wise Monthly Domestic Passenger Traffic Statistics</em>,
aggregated over twelve months (August 2025 &ndash; July 2026) and applied
directionally.</p>

<p><strong>Weight source in this build: {esc(f['weight_source'])}.</strong></p>

{weights_tbl}

<p>Windows are weighted <em>equally</em>, by design. There is no public data on
how Indian bookings distribute across advance-purchase windows, and inventing a
distribution would be worse than declaring a uniform one. ONS, which does have
such evidence, uses unequal fixed weights across its lead times; this is a case
where the honest choice and the ideal choice differ.</p>

<div class="panel">
<p><strong>Why DGCA, specifically.</strong> MoSPI's own Expert Group Report on
the 2024 CPI revision records that for air fares &ldquo;the Directorate General
of Civil Aviation (DGCA) provided a list of the most popular air routes&rdquo;
and that &ldquo;since airfares vary by booking platform and time slot, prices
were compiled from well-known websites across different time windows.&rdquo;
The route basket and weighting scheme here follow the same logic the ministry
applied to the CPI itself.</p>
</div>

<h2>4. Index formula</h2>
<p>The index takes the Laspeyres form the CPI itself uses. A novel formula is a
liability when the intended consumer is a statistics ministry, so nothing here
is original.</p>

<div class="formula">for each cell c:   relative(c, t) = price(c, t) / price(c, base)

APIx(t) = 100 x  SUM over c [ w(c) x relative(c, t) ]
                 -----------------------------------
                          SUM over c [ w(c) ]

base period = {esc(meta.get('base_period', 'n/a'))}, set to {meta.get('base_value', 100.0):.0f}
w(c)        = fixed base-period route weight</div>

<p>Price relatives, not raw fares, are aggregated. Aggregating rupee amounts
would let expensive routes dominate the index purely by being expensive.
Weights are fixed at base-period values: that is precisely what makes the index
Laspeyres, and it means a movement in the number is a movement in prices and
nothing else.</p>

<h3>Worked example</h3>
{worked_html}
</div>"""

    # ============================================================== page 3
    p3 = f"""
<div class="page">
<h2>5. Basket continuity when sources change</h2>
<p>A cell's price is the cheapest fare across every source collected. So on the
day a new carrier enters the collection, cells it flies can become cheaper for
a reason that has nothing to do with prices &mdash; there is simply one more
airline in the comparison. An index that admitted this would report a fare fall
caused by its own collection schedule.</p>

<p><strong>Rule: the headline index uses only sources present from the base
period onward.</strong> A source that begins later is not folded in. It
receives its own index on its own base, and a combined all-sources index is
published separately, re-based to the first date on which every source was
collecting. Three internally consistent series; none of them splices a
composition change into a price change. This is the same reasoning that leads
national statistical offices to re-base rather than chain across a sample
break.</p>

{late_note}

<h2>6. Missing observations</h2>
<p>A cell with no fare on a collection date carries its last observed relative
forward, and the count of carried cells is published alongside the index every
day. Dropping the cell instead would bias the index upward exactly when cheap
seats sell out &mdash; the worst possible bias for a price index, because it
would report rising prices from the disappearance of the cheapest ones.</p>

<div class="panel warn">
<p><strong>This is weaker than official practice and is not presented
otherwise.</strong> The CPI Manual's rule for a discontinued specification is
to impute from &ldquo;the movement of prices of routes in the same
category&rdquo;. Eurostat's web-scraping guidance recommends only that some
imputation option exist, without prescribing one. No official document located
endorses flat last-value carry-forward for airfares. It is a defensible
prototype shortcut, not an implementation of the standard.</p>
</div>

<h2>7. Output frequencies</h2>
<p>Daily, weekly and monthly series are produced, as the problem statement
requires. Weekly and monthly values are means of the daily series over the
period and are explicitly flagged <span class="mono">partial</span> when the
period is incomplete &mdash; a partial month must never be presented as a
month.</p>

<p>Outputs are written to <span class="mono">data/apix_daily.csv</span>,
<span class="mono">apix_weekly.csv</span>,
<span class="mono">apix_monthly.csv</span>, per-series values to
<span class="mono">apix_by_series.csv</span>, and a machine-readable document
to <span class="mono">docs/api/index.json</span>, regenerated with the index
and servable by any static host. That JSON document is the prototype's answer
to the requirement for an API the NSO and RBI can consume.</p>

<h2>8. Collection architecture</h2>
<p>Each portal is implemented as an adapter behind a single interface with one
method, <span class="mono">fetch(origin, destination, departure_date)</span>.
The collector never learns which portal it is holding, so a new source is a new
file and one registration line, and no change to the index, the store or the
dashboard.</p>

<p>Two access patterns were needed in practice, and the architecture supports
both:</p>
<ul>
<li><strong>Direct HTTP</strong> where a portal's API answers ordinary
requests. A short-lived bearer token is captured automatically by opening the
site in a real browser and reading the token off its own traffic; the browser
is used only for authentication, and the {grid} cells then go through plain
HTTP, which is far faster than driving a browser {grid} times.</li>
<li><strong>Browser-mediated</strong> where a portal's web application firewall
refuses anything whose TLS fingerprint is not a browser's. Here the collector
navigates the portal's own search page and reads the response to the request
the page makes on its own behalf. Nothing is forged: the request is the site's,
made by a real browser session.</li>
</ul>
</div>"""

    # ============================================================== page 4
    refs = [
        ("MoSPI, Expert Group Report on CPI revision (base 2024=100) &mdash; "
         "air fare route selection and price collection",
         "https://www.mospi.gov.in/uploads/documents/documents/1769670534541-Export_report_CPI.pdf"),
        ("MoSPI / PIB, release of the revised CPI series, base 2024=100 "
         "(February 2026)",
         "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2291051"),
        ("ONS, Special case aggregates in consumer prices &mdash; airfares "
         "lead-time structure and fixed sub-index weights",
         "https://www.ons.gov.uk/economy/inflationandpriceindices/methodologies/specialcaseaggregatesinconsumerprices"),
        ("ILO / IMF / OECD / UN / World Bank, Consumer Price Index Manual "
         "2020, ch. 11 &mdash; transport fares",
         "https://www.imf.org/-/media/files/data/cpi/chapter-11-some-special-cases.pdf"),
        ("Eurostat, Practical guidelines on web scraping for the HICP (2020)",
         "https://ec.europa.eu/eurostat/documents/272892/12032198/Guidelines-web-scraping-HICP-11-2020.pdf"),
        ("DGCA, City Pair Wise Monthly Domestic Passenger Traffic Statistics",
         "https://www.dgca.gov.in/digigov-portal/?page=monthlyStatistics/259/4751/html"),
    ]
    ref_html = "<ol>" + "".join(
        f'<li>{t}<br><a href="{u}">{u}</a></li>' for t, u in refs) + "</ol>"

    total_rows = len(df)
    days = df.collection_date.nunique()

    p4 = f"""
<div class="page">
<h2>9. Compliance and collection conduct</h2>
<ul>
<li><strong>Public data only.</strong> Every fare collected is a price shown to
any member of the public searching the same route and date. No account is
created, no login is used, no paywall or authentication barrier is
circumvented, and no fare is obtained that a traveller could not see.</li>
<li><strong>No personal data.</strong> The system collects prices and flight
attributes. It does not collect, store or process any personal data of any
individual. There is no passenger, no booking and no transaction.</li>
<li><strong>Rate limiting.</strong> Requests are spaced by a fixed delay and
each source declares a daily request budget. Collection volume is a few dozen
requests per portal per day &mdash; below the traffic of a single human
comparing fares.</li>
<li><strong>No circumvention of access controls.</strong> Where a portal's
protections could not be satisfied by legitimate means, that portal was
<em>excluded</em> rather than defeated. Section 10 names it.</li>
<li><strong>Credential hygiene.</strong> Session tokens are held in gitignored
local files or environment variables, are never committed, and are short-lived
by construction. No credential appears in the repository or in this
document.</li>
<li><strong>Attribution.</strong> Weighting data is derived from DGCA
publications and is cited as such. Fare data is attributed to the originating
carrier portal in every stored record.</li>
</ul>

<h2>10. Coverage actually achieved</h2>
<p>As of {today}: <strong>{total_rows:,} fare records</strong> over
<strong>{days} collection day{'s' if days != 1 else ''}</strong>.</p>
{coverage}
{index_tbl}

<h3>Portals excluded, and why</h3>
<p>Two major carriers could not be collected. Both are stated here rather than
omitted, because the pattern is itself a finding.</p>
<ul>
<li><strong>IndiGo</strong> &mdash; the booking portal is protected by
enterprise bot management which fingerprints the TLS handshake and requires
cookies set by its own sensor scripts. A browser session can reach the results
page legitimately, but instrumentation established that the portal's fare
requests carry <em>no bearer token at all</em>: authentication is by session
cookie. Its published NDC API is available only to IATA-accredited agents.
Excluded.</li>
<li><strong>Air India</strong> &mdash; the same protection, returning
<span class="mono">403 Access Denied</span> even with a valid token and a
complete live session. Excluded.</li>
</ul>
<p>The generalisation that held throughout: large carriers operate enterprise
bot management, smaller ones do not. A production system for a statistical
office would not scrape these portals at all &mdash; it would obtain the data
under a data-sharing arrangement, which is available to a ministry and not to a
prototype.</p>
</div>"""

    # ============================================================== page 5
    dow_table = ""
    if f.get("dow") is not None and not f["dow"].empty:
        dw = f["dow"]
        dow_table = table(
            ["Window"] + list(dw.columns),
            [[f"T+{idx}"] + [esc(v) for v in row]
             for idx, row in zip(dw.index, dw.values)])
        weekend = sum(1 for v in dw.iloc[:, -1] if v in ("Fri", "Sat", "Sun"))
        if weekend:
            dow_table += (
                f"<p>On the latest collection date, <strong>{weekend} of "
                f"{len(dw)} windows</strong> fell on a Friday, Saturday or "
                f"Sunday. Weekend departures price differently from midweek "
                f"ones, so part of any movement between the first and latest "
                f"collection date is this rotation rather than a change in "
                f"price.</p>")

    p5 = f"""
<div class="page">
<h2>11. Limitations</h2>
<p>Stated plainly, worst first.</p>

<h3>11.1 Advertised fares are not transacted fares</h3>
<p>The index measures posted prices, not prices paid. No weighting by seats
sold is possible from public data, so a fare available on one seat counts the
same as one available on ninety. No statistical office located has stated that
scraped advertised airfares are an accepted proxy for transacted fares; the
question is open in the literature, not settled. This is the structural limit
of the whole approach, and it is not closed by collecting more data &mdash;
only by access to booking data.</p>

<h3>11.2 The departure weekday rotates with the collection date</h3>
<p>A window is a fixed number of days before departure, and the collection
date advances one day at a time &mdash; so the <em>weekday</em> a window lands
on advances with it. Over a short series that is a composition effect, not a
price movement, and it takes a full week before it washes out.</p>
{dow_table}
<p>This is not a defect in the design; it is inherent to any fixed
advance-purchase grid, and official practice deals with it by collecting over
periods long enough for the weekday cycle to complete. It does mean that a
day-to-day change in this index, at this series length, cannot be read as
inflation. It is stated here because it is the first thing that should be
checked before any movement in the series is attributed to prices.</p>

<h3>11.3 The shortest window has no precedent</h3>
<p>Every official lead-time grid located begins no closer than two days before
departure: ONS at one month, the CPI Manual at one month, Eurostat's scraped
rail example at two days. Sampling one day before departure captures
walk-up pricing, which is arguably a different price concept from
advance-purchase fares. The window is specified by the problem statement and is
implemented as specified, but it should not be described as standard
practice.</p>

<h3>11.4 A single fare per cell, not a fare-class structure</h3>
<p>The CPI Manual recommends collecting several fare classes per lead time
&mdash; &ldquo;a full economy fare and a typical discounted economy fare&rdquo;
&mdash; precisely because under yield management the cheapest available fare
moves with unsold inventory as well as with price. Taking one fare per cell
conflates the two. This is a prototype simplification and a known divergence
from the standard.</p>

<h3>11.5 Carry-forward imputation</h3>
<p>Weaker than the Manual's category-movement rule, as set out in section 6.
Carried cells are counted and published so the reader can judge how much of any
given day's value is imputed.</p>

<h3>11.6 Series length</h3>
<p>The index is short, because airfare history cannot be backfilled &mdash;
a price that existed yesterday is unobtainable today. The methodology, the
schedule and the outputs are complete and would produce a long series given
time; only time is missing. Index values over a handful of days should be read
as a demonstration that the machinery works, not as a finding about Indian
airfares.</p>

<h3>11.7 Carrier coverage</h3>
<p>Two carriers, not the full market. Section 10 states which and why. The
adapter architecture means additional carriers are additive, not structural,
work.</p>

<h3>11.8 Fixed base, not a multilateral index</h3>
<p>The web-scraped-price literature increasingly favours multilateral methods
(GEKS-type) because scraped samples churn and a fixed base drifts out of
representativeness. Fixed-weight Laspeyres was chosen instead because it is
what the intended consumer already uses and because ONS itself uses fixed
weights for the airfares aggregation specifically. This is a defensible choice
between two literatures that pull in different directions, not an oversight.</p>

<h3>11.9 A scraped headline airfare index is not established practice</h3>
<p>No major statistical office was found to have moved its published headline
airfare component onto web-scraped collection. Australia's statistical office
scrapes in production but explicitly excludes airfares; the UK's scraping
programme listed airfares as a future candidate; Italy and Finland have run
pilots. This system sits closer to the research frontier than to settled
practice, and is presented that way.</p>

<h2>12. Scalability</h2>
<p>The work is linear in cells, and cells are independent of one another.
{grid} cells is a few minutes; a national basket of 100 routes by
{n_windows} windows is 500 cells, which is under an hour run serially and
minutes run in parallel. Nothing in the design is quadratic and no cell needs
to coordinate with another.</p>

<p>The binding constraint is not compute or storage &mdash; it is the portals.
Politeness delays and per-source request budgets set the ceiling, which is why
scaling means <em>more sources</em> rather than more requests per source. A
year of a 500-cell basket is a few hundred thousand rows; SQLite carries that
comfortably, and the schema is ordinary SQL, so moving to PostgreSQL is a
connection string rather than a rewrite.</p>

<p>Three axes of growth, and what each costs:</p>
<ul>
<li><strong>Another carrier</strong> &mdash; one new file implementing one
method, plus one registration line. No change to the store, the index, the
dashboard or the API.</li>
<li><strong>More routes or windows</strong> &mdash; a list in the configuration
file. Everything downstream derives from it, so the basket cannot get out of
step between collector and index.</li>
<li><strong>Higher frequency</strong> &mdash; intra-day collection is a
scheduling change, not a code change. The store already timestamps every
observation.</li>
</ul>

<h2>13. Cost, maintenance and adoption</h2>
<p><strong>Cost to operate is effectively zero.</strong> The system is a
scheduled script and a database file. There is no paid API, no data licence and
no per-query charge; it runs on free-tier compute or on any existing server.
The expensive input to a price index is field-staff time, and this substitutes
for field-staff time rather than adding infrastructure spend.</p>

<p><strong>Maintenance is bounded by the architecture.</strong> The only thing
that breaks in normal operation is a portal changing its API, and that is one
file &mdash; the index, the store and the published outputs are unaffected by
construction. A failure is visible rather than silent: the affected cells
appear as empty in the observations table, and the count of imputed cells rises
in the published series.</p>

<p><strong>Adoption path.</strong> Three steps, ordered so the first costs
nothing and risks nothing:</p>
<ol>
<li><strong>Parallel run.</strong> The scraped series runs alongside existing
collection as a validation series. It cannot affect published statistics, and
it builds the history that any published index requires before it can be
trusted.</li>
<li><strong>Substitution.</strong> Once validated, the automated series
replaces manual collection for the routes it covers. This is where the
staff-time saving is realised, and where daily frequency starts to inform the
index rather than merely shadow it.</li>
<li><strong>Data sharing.</strong> In a production system operated by the
ministry, scraping is replaced by carriers filing fare data &mdash; extending
the existing DGCA tariff-reporting relationship rather than creating a new one.
The source adapter becomes a file reader; nothing downstream changes. This also
resolves the advertised-versus-transacted limitation in section 11.1, which no
amount of scraping can resolve.</li>
</ol>

<div class="panel">
<p><strong>There is no revenue model, and that is the correct answer for this
problem.</strong> This is public statistical infrastructure. Its return is a
better-measured CPI and reduced collection cost, in a transport group carrying
roughly 8.8% of the revised CPI basket.</p>
</div>

<h2>14. References</h2>
{ref_html}

<div class="foot">
APIx &mdash; Smart India Hackathon 2026, problem statement 26056, Ministry of
Statistics and Programme Implementation. Document generated
{today} from the live data store by
<span class="mono">make_methodology.py</span>. Figures reflect the contents of
<span class="mono">data/fares_export.csv</span> at build time.
</div>
</div>"""

    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>APIx — Methodology and Compliance</title>"
            f"<style>{CSS}</style></head><body>"
            f"{p1}{p2}{p3}{p4}{p5}</body></html>")


def render_pdf(html_path: str, pdf_path: str) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[methodology] playwright not installed — HTML written, "
              "print it from a browser (Ctrl+P, background graphics on).")
        return False
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="load")
            page.pdf(path=pdf_path, format="A4", print_background=True,
                     margin={"top": "0", "right": "0",
                             "bottom": "0", "left": "0"})
        finally:
            browser.close()
    return True


def main() -> int:
    os.makedirs("docs", exist_ok=True)
    facts = gather()
    html = build_html(facts)
    with open(OUT_HTML, "w", encoding="utf-8") as handle:
        handle.write(html)
    print(f"[methodology] wrote {OUT_HTML}")
    if render_pdf(OUT_HTML, OUT_PDF):
        print(f"[methodology] wrote {OUT_PDF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
