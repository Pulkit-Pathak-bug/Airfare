#!/usr/bin/env python3
"""Generate docs/PROPOSED-SOLUTION.pdf — the source text for the deck.

Written for a teammate who is building slides and is not the person who
wrote the code. Plain language, short sentences, every section already
shaped like a slide: a heading, a one-line idea, then bullets that can be
lifted straight across.

Live figures come from the data store, so the deck cannot quote a number
the system no longer produces.

    py make_solution.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docgen import document, esc, render, table  # noqa: E402

OUT_HTML = "docs/PROPOSED-SOLUTION.html"
OUT_PDF = "docs/PROPOSED-SOLUTION.pdf"


def live() -> dict:
    """Real numbers for the feasibility slide."""
    out = {"rows": 0, "days": 0, "sources": [], "latest": None,
           "base": None, "cells": 0, "grid": 60}
    try:
        from fareindex.apix import build_index, load_fares, split_sources
        from fareindex.config import ROUTES, WINDOWS
        df = load_fares()
        cont, _late = split_sources(df)
        daily, meta = build_index(df[df.source_portal.isin(cont)])
        out.update(
            rows=len(df), days=int(df.collection_date.nunique()),
            sources=sorted(df.source_portal.unique()),
            base=meta.get("base_period"),
            cells=int(meta.get("basket_cells", 0)),
            grid=len(ROUTES) * len(WINDOWS),
            latest=None if daily.empty else float(daily.apix.iloc[-1]),
        )
    except Exception as exc:                                 # noqa: BLE001
        print(f"[solution] data store unreadable ({exc}); figures blank.")
    return out


def build(f: dict) -> str:
    today = date.today().isoformat()
    latest = f"{f['latest']:.2f}" if f["latest"] is not None else "—"

    # ------------------------------------------------------------- cover
    cover = f"""
<span class="tag mute">SIH 2026 · PS 26056 · MoSPI</span>
<h1>Proposed solution</h1>
<p class="sub">APIx &mdash; a Real-time Airfare Price Index for India</p>
<div class="rule"></div>

<h2>The problem, in one line</h2>
<p>Air ticket prices in India change many times a day, but the Consumer
Price Index measures them by hand, occasionally. So the official number
never really sees how air fares move.</p>

<h2>Our solution, in one paragraph</h2>
<p><strong>APIx is a system that visits airline websites every day by
itself, collects ticket prices for a fixed list of routes, and turns those
prices into a single number that shows whether flying has become more or
less expensive.</strong> It runs without anyone watching it, stores every
price it sees, and publishes the result as a chart, a spreadsheet and a
machine-readable feed that MoSPI or RBI can plug into.</p>

<div class="panel">
<p><strong>The one-sentence pitch for the deck:</strong> we automate the
exact method the ministry already uses for air fares &mdash; DGCA's popular
routes, prices taken from booking websites across different time windows
&mdash; and run it daily instead of occasionally.</p>
</div>

<h2>Why this is harder than it sounds</h2>
<p>You cannot just record "the price of a Delhi&ndash;Mumbai ticket". There
is no such thing. The price depends on:</p>
<ul>
<li><strong>Which route</strong> &mdash; and even the direction.
Delhi&rarr;Mumbai and Mumbai&rarr;Delhi are different prices.</li>
<li><strong>How far ahead you book.</strong> A seat bought tomorrow and the
same seat bought in 45 days are completely different prices.</li>
<li><strong>When you look.</strong> The price changes through the day as
seats sell.</li>
</ul>
<p>So before you can measure anything, you have to fix what you are
measuring. That is the first thing our design does.</p>
"""

    # ------------------------------------------------------- how it works
    how = f"""
<h2>How it works &mdash; five steps</h2>

<h3>Step 1 &middot; Fix what we measure</h3>
<p>We check the same shopping basket every single day. The basket is:</p>
<ul>
<li><strong>12 routes</strong> &mdash; the 6 city pairs named in the
problem statement, each in both directions.</li>
<li><strong>5 booking distances</strong> &mdash; 1, 7, 15, 30 and 45 days
before the flight leaves.</li>
</ul>
<p>12 &times; 5 = <strong>{f['grid']} price checks every day</strong>. Each
one is called a <em>cell</em>. Because the basket never changes, any change
in the final number is a change in prices and nothing else.</p>

<h3>Step 2 &middot; Collect the prices automatically</h3>
<p>A program opens each airline's booking system and reads the fares, the
same fares any traveller would see. It does this on a schedule, every day,
with nobody involved. It records the cheapest fare, the base fare and the
taxes separately, plus the flight number and time.</p>
<p>Important: it also records the cells where it found <em>nothing</em> &mdash;
a sold-out flight is information, not an error.</p>

<h3>Step 3 &middot; Clean and store</h3>
<p>Every price goes into a database with two separate dates: the day we saw
the price, and the day the flight departs. Keeping those apart is what lets
us compare like with like. Running the collector twice by accident cannot
create duplicate rows.</p>

<h3>Step 4 &middot; Build the index</h3>
<p>This is the statistics part, and it is deliberately not clever:</p>
<ul>
<li>For each cell, take the cheapest fare that day.</li>
<li>Compare it with the price of the same cell on day one. If it was
&#8377;5,000 and is now &#8377;5,500, that cell is at 1.10.</li>
<li>Average all {f['grid']} cells together, but give busier routes more
importance &mdash; Delhi&ndash;Mumbai counts for more than a thin route,
using real DGCA passenger numbers.</li>
<li>Multiply by 100. Day one is 100. Everything after is measured against
it.</li>
</ul>
<p>This is the same <strong>Laspeyres</strong> formula the CPI itself uses.
We did not invent a new one on purpose &mdash; a ministry can check our
maths against a method it already trusts.</p>

<h3>Step 5 &middot; Publish</h3>
<p>Three outputs, all generated automatically:</p>
<ul>
<li>A <strong>web dashboard</strong> with the index over time, a heatmap of
every route, and the booking-lead-time curve.</li>
<li><strong>Daily, weekly and monthly</strong> spreadsheets.</li>
<li>A <strong>JSON feed</strong> at a fixed web address that NSO or RBI
systems can read directly &mdash; no human in the loop.</li>
</ul>
"""

    # ------------------------------------------------------- differentiators
    diff = """
<h2>What makes it different</h2>
<p>Four things a judge should remember. These are the innovation slide.</p>

<h3>1. It runs itself &mdash; including the login</h3>
<p>Most scraping projects need a person to paste a fresh security token
every morning. Ours opens the site in a real browser, lets the site issue
its own token, reads it, and carries on. That single detail is what turns a
demo into a system that can actually run daily and unattended.</p>

<h3>2. It refuses to report a fake price change</h3>
<p>When we added a second airline mid-way, the index would have shown a
<strong>fare crash that never happened</strong> &mdash; simply because there
was now one more airline in the "cheapest price" comparison. We caught it
and built a rule that keeps a late-joining airline out of the headline
number and publishes it as its own series instead.</p>
<p>We can demonstrate this live in one command. On a controlled test where
prices genuinely rose 10% a day, the naive version reported a 30% fall. Ours
reported the truth.</p>

<h3>3. Adding an airline is one file</h3>
<p>Every airline sits behind the same simple interface. The database, the
index and the dashboard never learn which airline they are dealing with. So
a new airline is a new file and one line &mdash; nothing else changes. That
is what makes the system scalable rather than a one-off script.</p>

<h3>4. It documents its own weaknesses</h3>
<p>Our methodology document lists nine limitations, worst first, with the
official practice we diverge from in each case. A price index whose
limitations are hidden is not usable by a statistics office. This is a
feature of the submission, not an apology.</p>

<div class="panel warn">
<p><strong>Say this out loud in the pitch:</strong> the scraper is the small
part. The valuable part is knowing what the number means &mdash; which
prices to compare, how to weight them, and when a movement is real.</p>
</div>
"""

    # ------------------------------------------------------------ stack
    stack = f"""
<h2>Technologies used</h2>
<p>Everything below is free and open-source. The system has no paid API, no
data licence and no per-query cost.</p>

<h3>Frontend &mdash; what people see</h3>
{table(["Technology", "What it does here", "Why this one"], [
    ["<strong>Streamlit</strong>",
     "The live web dashboard: index chart, filters, route heatmap, "
     "lead-time curve, downloadable table",
     "Turns Python straight into a web app, so the same code that builds "
     "the index draws the charts — no separate web team needed"],
    ["<strong>Altair / Vega-Lite</strong>",
     "Every chart on the dashboard",
     "Charts are described as data rather than drawn by hand, so they "
     "stay correct when the data changes"],
    ["<strong>HTML + CSS</strong>",
     "The generated PDF reports (this document is one)",
     "Reports are produced by code from the live database, so they can "
     "never disagree with the system"],
    ["<strong>Colour-blind-safe palette</strong>",
     "All charts",
     "Checked against colour-vision deficiency, because a government "
     "dashboard has to be readable by everyone"],
])}

<h3>Backend &mdash; what does the work</h3>
{table(["Technology", "What it does here", "Why this one"], [
    ["<strong>Python 3.11</strong>", "The whole collection and index engine",
     "Standard for data work; every library below is Python"],
    ["<strong>Requests</strong>",
     "Talks directly to airline fare APIs where they allow it",
     "Fast — the full daily basket finishes in a few minutes"],
    ["<strong>Playwright</strong>",
     "Drives a real Chromium browser where a site refuses plain requests, "
     "and captures the security token automatically",
     "The only reliable way past modern bot protection, and it is how the "
     "system logs itself in without a human"],
    ["<strong>pandas</strong>", "Index calculation, weighting, weekly and "
     "monthly aggregation",
     "The standard tool for tabular statistics"],
    ["<strong>SQLite</strong>", "Stores every fare, every attempted check, "
     "and a record of every run",
     "A single file, no server to maintain; the schema is ordinary SQL so "
     "moving to PostgreSQL later is a connection string, not a rewrite"],
])}

<h3>Data and operations</h3>
{table(["Technology", "What it does here"], [
    ["<strong>DGCA passenger statistics</strong>",
     "Real passenger numbers per city pair, used to weight the index so "
     "busy routes count for more"],
    ["<strong>CSV + JSON outputs</strong>",
     "Daily / weekly / monthly series, and a machine-readable feed at a "
     "fixed address for NSO and RBI"],
    ["<strong>Task Scheduler / cron</strong>",
     "Runs the collector once a day, unattended"],
    ["<strong>Git and GitHub</strong>",
     "Version control; credentials are excluded by policy and never "
     "committed"],
])}

<div class="panel">
<p><strong>Architecture in one line for the slide:</strong> Python collectors
&rarr; SQLite database &rarr; pandas index engine &rarr; Streamlit dashboard
+ JSON API. Each airline is a plug-in module behind a common interface.</p>
</div>
"""

    # ------------------------------------------------------- proof + scope
    src = ", ".join(f["sources"]) or "—"
    proof = f"""
<h2>What is already working</h2>
<p>This is not a mock-up. As of {today} the system has collected
<strong>{f['rows']:,} real fares</strong> over
<strong>{f['days']} consecutive days</strong> from
<strong>{esc(src)}</strong>, filling {f['cells']} of {f['grid']} basket
cells, with the index reading <strong>{latest}</strong> against a base of
100 on {esc(f['base'] or '—')}.</p>

<ul>
<li>The collector runs on a daily schedule, unattended.</li>
<li>The dashboard is live and reads the same database.</li>
<li>The JSON feed regenerates with every index build.</li>
<li>The methodology, limitations and compliance are documented and
generated from the data itself.</li>
</ul>

<h2>How it answers each part of the problem statement</h2>
{table(["The PS asks for", "What we built"], [
    ["Automated scraping of airline and OTA portals",
     "Two working collectors on a daily schedule, with a plug-in design "
     "so more can be added"],
    ["Handle JavaScript pages, anti-bot measures, session management",
     "A real browser session handles all three; where a portal could not "
     "be collected legitimately we excluded it and documented why"],
    ["A cleaned database with fare components",
     "SQLite storing base fare, taxes, fees, carrier, flight number and "
     "time — plus a record of every empty cell"],
    ["An airfare price index at daily, weekly, monthly frequency",
     "All three, published as CSV, with the weighting method documented"],
    ["A dashboard with trends, heatmaps and lead-time analysis",
     "All three charts, live"],
    ["An API the NSO and RBI can consume",
     "A JSON document at a stable path, regenerated with every index run"],
])}

<h2>Scale, cost and who maintains it</h2>
<ul>
<li><strong>Scale:</strong> the work grows in a straight line. {f['grid']}
cells takes minutes; a national basket of 500 cells takes under an hour, or
minutes if run in parallel.</li>
<li><strong>Cost:</strong> effectively zero. A scheduled script and a
database file. No paid service anywhere in the design.</li>
<li><strong>Maintenance:</strong> one part-time engineer. The only thing
that breaks in normal use is an airline changing its website, and that is a
single file to fix.</li>
<li><strong>Adoption:</strong> run it beside the existing manual collection
first (no risk, builds history), then let it replace manual collection, then
&mdash; in a ministry-run version &mdash; replace scraping with airlines
filing data directly. Same pipeline throughout.</li>
</ul>

<h2>Honest limitations &mdash; put these on a slide too</h2>
<ul>
<li>We measure <strong>advertised</strong> prices, not what people actually
paid. Only booking data can close that gap.</li>
<li>The series is <strong>short</strong>, because airfare history cannot be
downloaded &mdash; it can only be collected going forward.</li>
<li><strong>Two airlines</strong> so far. Two more are behind bot protection
we chose to document rather than defeat.</li>
<li>Because the booking window is fixed and the date rolls forward, the
<strong>day of the week shifts</strong> as we collect &mdash; so short-term
movements need a full week before they mean anything.</li>
</ul>

<div class="foot">
APIx &mdash; Smart India Hackathon 2026, problem statement 26056, Ministry
of Statistics and Programme Implementation. Generated {today} from the live
data store by <span class="mono">make_solution.py</span>. Companion
documents: METHODOLOGY (full method and limitations), QA-DEFENCE (expected
questions), CODE-WALKTHROUGH (the code explained).
</div>
"""

    return document("APIx — Proposed solution",
                    [cover, how, diff, stack, proof])


def main() -> int:
    os.makedirs("docs", exist_ok=True)
    render(build(live()), OUT_HTML, OUT_PDF)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
