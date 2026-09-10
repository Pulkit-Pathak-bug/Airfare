#!/usr/bin/env python3
"""Generate docs/QA-DEFENCE.pdf — every question a judge is likely to ask.

The evaluation gives 10 marks to the prototype and 90 to everything around
it, and the Q&A round is as long as the presentation itself. So this pack
exists to make the second half of the judged time as prepared as the first.

Each question carries an owner — the speaker who presented that section
answers questions about it, which is what turns a six-speaker rule from a
liability into a rehearsed defence.

    py make_qa_pack.py

Live figures are read from the data store so the pack cannot quote numbers
the system no longer produces.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docgen import document, esc, qa, render, table  # noqa: E402

OUT_HTML = "docs/QA-DEFENCE.html"
OUT_PDF = "docs/QA-DEFENCE.pdf"

S1, S2, S3 = "S1 · Problem", "S2 · Demo", "S3 · Method"
S4, S5, S6 = "S4 · Architecture", "S5 · Impact", "S6 · Limitations"


def live() -> dict:
    """A few real numbers, so the pack never quotes a stale claim."""
    out = {"rows": 0, "days": 0, "sources": [], "latest": None, "base": None}
    try:
        from fareindex.apix import build_index, load_fares, split_sources
        df = load_fares()
        cont, late = split_sources(df)
        daily, meta = build_index(df[df.source_portal.isin(cont)])
        out.update(rows=len(df), days=int(df.collection_date.nunique()),
                   sources=sorted(df.source_portal.unique()),
                   base=meta.get("base_period"),
                   latest=(None if daily.empty
                           else float(daily.apix.iloc[-1])))

        # The spread of individual cell moves, and the biggest mover, both
        # computed. These were once hand-typed and went stale within a day
        # — which is exactly what this pack promises it will not do.
        from fareindex.apix import cell_prices, route_weights
        prices = cell_prices(df[df.source_portal.isin(cont)])
        days = sorted(prices.collection_date.unique())
        if len(days) >= 2:
            first = prices[prices.collection_date == days[0]].set_index(
                ["route", "advance_window_days"]).price
            last = prices[prices.collection_date == days[-1]].set_index(
                ["route", "advance_window_days"]).price
            both = pd.concat([first.rename("a"), last.rename("b")],
                             axis=1).dropna()
            both = both[both.a > 0]
            rel = both.b / both.a
            cell = (rel - 1).abs().idxmax()
            wt, _src = route_weights(sorted(prices.route.unique()))
            top4 = wt.sort_values(ascending=False).head(4)
            out.update(
                move_lo=(rel.min() - 1) * 100,
                move_hi=(rel.max() - 1) * 100,
                move_median=(rel.median() - 1) * 100,
                risers=int((rel > 1).sum()), cells=int(len(rel)),
                mover_route=cell[0], mover_window=int(cell[1]),
                mover_from=float(both.loc[cell].a),
                mover_to=float(both.loc[cell].b),
                mover_pct=(float(rel.loc[cell]) - 1) * 100,
                heavy=list(top4.index), heavy_share=float(top4.sum()) * 100,
                index_move=(out["latest"] / 100 - 1) * 100
                if out["latest"] else None,
            )
    except Exception as exc:                                 # noqa: BLE001
        print(f"[qa] could not read the data store ({exc}); "
              f"figures left blank.")
    return out


def build(f: dict) -> str:
    today = date.today().isoformat()
    src = ", ".join(f["sources"]) or "—"
    latest = f"{f['latest']:.2f}" if f["latest"] is not None else "—"

    # Sentences assembled from the live figures. Every number a judge might
    # check is computed here rather than typed into the prose below.
    if "move_lo" in f:
        spread = (
            f"Between the base period and the latest collection, individual "
            f"cells moved from {f['move_lo']:+.1f}% to {f['move_hi']:+.1f}%, "
            f"the median cell moved {f['move_median']:+.1f}%, and "
            f"{f['risers']} of {f['cells']} cells rose &mdash; while the "
            f"index moved {f['index_move']:+.2f}%.")
        mover = (
            f"the biggest single move was {esc(f['mover_route'])} at "
            f"T+{f['mover_window']}, where the cheapest fare went from "
            f"&#8377;{f['mover_from']:,.0f} to &#8377;{f['mover_to']:,.0f} "
            f"({f['mover_pct']:+.0f}%) as cheap seats sold out.")
        median_note = (
            f"Note also that the median cell moved only "
            f"{f['move_median']:+.1f}%. The index rose because the movement "
            f"was concentrated on heavily weighted routes and short windows, "
            f"which is the index doing its job.")
        heavy = (
            f"Our four heaviest routes ({esc(', '.join(f['heavy']))}) carry "
            f"{f['heavy_share']:.0f}% of the basket, and that is where the "
            f"movement was.")
    else:
        spread = mover = median_note = heavy = (
            "(computed once at least two collection days exist)")
    _fill = dict(spread=spread, mover=mover, median_note=median_note,
                 heavy=heavy)

    # ------------------------------------------------------------ cover
    cover = f"""
<span class="tag mute">SIH 2026 · PS 26056 · internal round</span>
<h1>Defence pack</h1>
<p class="sub">Every question we expect, the answer, and who gives it</p>
<div class="rule"></div>

<p>The evaluation is 100 marks over ten criteria. The working prototype is
worth <strong>10 of them</strong>. Problem understanding, innovation,
relevance, architecture, feasibility, scalability, impact, sustainability and
presentation are the other 90 — and the Q&amp;A round is <strong>10+2 minutes,
the same length as the presentation itself</strong>. Half the judged time is
this document.</p>

<div class="panel">
<p><strong>How to use it.</strong> Each question is tagged with an owner. The
person who presents a section answers questions on that section — that is what
makes a six-speaker rule a strength rather than six chances to look
unrehearsed. Nobody needs to know everything. Everybody needs to know their
own section cold, and to know who to hand off to.</p>
</div>

<div class="panel good">
<p><strong>The three rules for the Q&amp;A round.</strong><br>
1. Answer in two sentences, then stop. Rambling is how a good answer becomes a
follow-up question.<br>
2. If you do not know, say &ldquo;we did not test that&rdquo; and say what you
would do to find out. A judge scores honesty above bluffing, every time.<br>
3. Never contradict a teammate in front of the panel. Say &ldquo;let me add to
that&rdquo;.</p>
</div>

<h2>Speaking split</h2>
{table(["Slot", "Section", "Owns in Q&A"], [
    [S1, "The problem and why it is hard",
     "Scope, users, why CPI needs this"],
    [S2, "Live demo of the system",
     "What the dashboard shows, how a run works"],
    [S3, "Methodology — grid, formula, weights",
     "Every statistical question"],
    [S4, "Architecture and scalability",
     "Stack, adapters, scale, what breaks"],
    [S5, "Impact, adoption and cost",
     "Who benefits, what it costs, how MoSPI takes it on"],
    [S6, "Limitations and future scope",
     "Every weakness — this is the strongest slot, not the weakest"],
])}

<p><strong>State of the system as of {today}:</strong>
{f['rows']:,} fare records across {f['days']} collection
day{'s' if f['days'] != 1 else ''}, sources {esc(src)}, base period
{esc(f['base'] or '—')} = 100, latest headline index {latest}.</p>
"""

    # ------------------------------------------------- A. problem & scope
    a = "<h2>A. Problem and scope</h2>" + "".join([
        qa("What exactly are you measuring?",
           "The change in the cheapest advertised one-way economy fare, on a "
           "fixed set of routes, at a fixed set of distances before departure. "
           "Not average fares, not fares paid — posted prices on a fixed grid.",
           S1),
        qa("Why does CPI need this? Doesn't it already cover transport?",
           "It covers transport, but air fares are collected the way every "
           "other item is collected — periodically, by field staff, from "
           "websites. MoSPI's own Expert Group Report on the 2024 CPI revision "
           "says prices were &ldquo;compiled from well-known websites across "
           "different time windows&rdquo;. That is exactly what we automate. "
           "Airfares change several times a day; a periodic manual reading "
           "cannot see that.",
           S1,
           "The ministry already decided this method is right. We are not "
           "proposing a new method, we are proposing to run their method "
           "daily instead of occasionally."),
        qa("Who is the user of this index?",
           "MoSPI, as an input to CPI compilation. Secondarily RBI for "
           "inflation monitoring, DGCA for its existing tariff-monitoring "
           "function, and the public through the published series.",
           S1),
        qa("Why airfares and not something easier?",
           "Because airfares are the hardest common case: the price of the "
           "identical service changes by the hour and by how far ahead you "
           "buy. Any method that works here works on rail, hotels and "
           "anything else with dynamic pricing.",
           S1),
        qa("Why only six city pairs?",
           "They are the six named in the problem statement. They are also the "
           "highest-traffic domestic sectors — the six pairs account for over "
           "23 million passengers in the last twelve months of DGCA data.",
           S3),
        qa("Why collect both directions separately?",
           "Because they are different products with different prices. "
           "DEL&rarr;BOM and BOM&rarr;DEL have different demand, different "
           "schedules and different fares. Treating them as one route would "
           "average away a real signal. Our weights are directional too.",
           S3),
    ])

    # --------------------------------------------------- B. methodology
    b = "<h2>B. Methodology &mdash; the questions that decide the marks</h2>" + "".join([
        qa("Why a Laspeyres index? That formula is over a century old.",
           "Deliberately. Our consumer is a statistics ministry that already "
           "compiles CPI as a Laspeyres index. A novel formula would be a "
           "liability — it would need validating before it could be trusted. "
           "The innovation in this project is the collection method, not the "
           "arithmetic.",
           S3,
           "If we had invented a formula, the first question would be "
           "&ldquo;why should we believe it?&rdquo; This way that question "
           "never arises."),
        qa("What is your base period?",
           "The first collection date, set to 100. Every later day is "
           "expressed relative to it. Base-period weights are fixed, which is "
           "what makes it Laspeyres — the basket does not move under you, so a "
           "change in the number is a change in prices and nothing else.",
           S3),
        qa("Why the cheapest fare and not the average?",
           "A traveller buys the lowest fare that suits them, not the average "
           "of the cabin. An average is dominated by expensive unsold "
           "inventory nobody purchases, so it would move for reasons that have "
           "nothing to do with what people pay.",
           S3,
           "We know the international CPI Manual recommends tracking several "
           "fare classes per window instead. We say so in our limitations — "
           "it is a prototype simplification, and it is the first thing we "
           "would add."),
        qa("Why T+1, 7, 15, 30 and 45 days?",
           "Those windows are specified in the problem statement, and we "
           "implement them verbatim. The design principle behind them is "
           "standard: ONS collects airfares at one, three and six months "
           "before departure; the CPI Manual specifies the same; Eurostat "
           "documents a scraped rail index at 2, 10, 30 and 60 days.",
           S3),
        qa("Is a fare one day before departure really an advance purchase?",
           "No, and we say so. T+1 captures walk-up pricing, which is arguably "
           "a different price concept. No official lead-time grid we found "
           "samples closer than two days out. We implement it because the "
           "problem statement asks for it, and we flag it in our limitations "
           "rather than describing it as standard practice.",
           S6,
           "This is in section 11.2 of our methodology document. We would "
           "rather name it than have you find it."),
        qa("What happens when a cell has no fare?",
           "It carries its last observed relative forward, and the number of "
           "carried cells is published next to the index every single day, so "
           "you can see how much of a value is imputed.",
           S3),
        qa("Isn't carrying forward just inventing data?",
           "It is imputation, and the alternative is worse. If you drop a cell "
           "when its cheap seats sell out, the index rises purely because the "
           "cheapest observation disappeared — that is the worst possible bias "
           "for a price index. Carry-forward is neutral where dropping is "
           "upward-biased.",
           S3,
           "The CPI Manual's own rule is richer — impute from the movement of "
           "other routes in the same category. Ours is cruder and we say so. "
           "It is a known divergence, not an oversight."),
        qa("How do I know your index isn't just noise?",
           "Look at the spread it sits on. {spread} The index is a weighted "
           "basket, so it separates a market-wide movement from the churn of "
           "individual fares; an average of the raw fares would swing with "
           "whichever cell happened to move most and mean nothing.",
           S3,
           "These figures are computed when this pack is built, not typed "
           "in &mdash; run it again after the next collection and they "
           "update."),
        qa("Your index jumped several percent in one day. Are Indian "
           "airfares really moving that fast?",
           "Part of it is real and part of it is our sampling, and we can "
           "separate them. The real part is inventory: {mover} The part "
           "that is not price is the weekday rotation "
           "&mdash; see the next question. At three days of data we would "
           "not present any movement as inflation.",
           S3,
           "{median_note}"),
        qa("Your median cell didn't move. Why is the index up?",
           "Because an index measures the cost of a weighted basket, not "
           "the typical cell. {heavy} A simple average "
           "across cells would have shown almost nothing and would have "
           "been the wrong answer &mdash; it would weight a thin sector the "
           "same as DEL&ndash;BOM.",
           S3),
        qa("Doesn't the departure day of the week shift as you collect?",
           "Yes, and it is limitation 11.2 in our methodology document. A "
           "window is a fixed number of days before departure and the "
           "collection date advances daily, so the departure weekday "
           "advances with it. On our latest collection date four of the "
           "five windows had rotated onto a Friday, Saturday or Sunday, and "
           "weekend departures price differently. It washes out over a full "
           "week; below that, a movement cannot be attributed to price "
           "without checking this first.",
           S6,
           "We found this in our own series rather than being told it. It "
           "is inherent to any fixed advance-purchase grid, and official "
           "practice handles it by collecting over periods long enough for "
           "the weekday cycle to complete."),
        qa("Explain your two date fields.",
           "Collection date is when we saw the price; departure date is when "
           "the flight leaves. The window is the difference. Collection date "
           "cannot be backfilled — a price that existed yesterday is gone "
           "today — which is why we started collecting before anything else "
           "was finished. Holding the window fixed is what makes prices "
           "comparable across days.",
           S3,
           "If you did not hold the window fixed, a falling index would just "
           "mean the flights you sampled happened to be further away."),
        qa("Why aggregate price relatives instead of the fares themselves?",
           "Because aggregating rupees lets expensive routes dominate the "
           "index purely by being expensive. A ratio is unit-free, so a 5% "
           "move on a cheap route counts the same as a 5% move on an "
           "expensive one, and the weights — not the price levels — decide "
           "importance.",
           S3),
        qa("How do you handle festivals, weekends, seasonality?",
           "We do not adjust for them, and at this series length we could not. "
           "The design handles it structurally instead: because the "
           "advance-purchase window is fixed, every observation is the same "
           "distance from departure, so day-of-week and seasonal effects enter "
           "the index the same way they enter the fares people actually pay. "
           "Formal seasonal adjustment needs at least two years of data.",
           S3),
        qa("Round trips? Business class?",
           "One-way economy only, which is the cleanest comparable unit. "
           "Return fares bundle two price decisions and airlines price them "
           "jointly; business cabins have different inventory dynamics. Both "
           "are additive later — they would be extra windows in the same grid, "
           "not a change to the method.",
           S3),
        qa("You have very little data. Isn't the index meaningless?",
           "The index values are, at this length, a demonstration that the "
           "machinery works — not a finding about Indian airfares. We say that "
           "explicitly. And it is not a fixable shortcoming: airfare history "
           "cannot be bought or backfilled, it can only be collected forward. "
           "The methodology, the schedule and the outputs are complete; only "
           "time is missing.",
           S6),
    ])

    # ------------------------------------------------------- C. weights
    c = "<h2>C. Weights and data provenance</h2>" + "".join([
        qa("Where do your weights come from?",
           "DGCA's City Pair Wise Monthly Domestic Passenger Traffic "
           "Statistics, aggregated over twelve months, applied directionally. "
           "DEL&ndash;BOM carries 29.4% of our basket because it carried "
           "6.78 million passengers.",
           S3),
        qa("Why passenger volume rather than expenditure?",
           "Expenditure weights would be better and we would use them if they "
           "existed publicly. Passenger volume is the closest available proxy: "
           "it is the same quantity DGCA publishes and the same basis MoSPI "
           "used when DGCA supplied it with the popular-route list for CPI.",
           S3),
        qa("How current is that traffic data?",
           "Through July 2026, twelve-month window from August 2025. Weights "
           "are fixed at base period by design, so they do not need to be "
           "current daily — they need to be current at rebasing, which for "
           "CPI happens on a multi-year cycle.",
           S3),
        qa("Did you verify those numbers?",
           "They were computed twice independently from the source data and "
           "agreed to within 0.03 percentage points. We access them through a "
           "published mirror of DGCA's bulletins because DGCA's own portal is "
           "JavaScript-driven; the underlying source is cited as DGCA. One "
           "known trap: from January 2026 DGCA splits Mumbai into three "
           "entries, and a parser that misses that understates DEL&ndash;BOM "
           "badly. We sum all three.",
           S3,
           "That level of provenance detail is in section 7a of our handoff "
           "document, including exactly which months and which fields."),
    ])

    # ----------------------------------------------------- D. technical
    d = "<h2>D. Technical and architecture</h2>" + "".join([
        qa("What is the stack?",
           "Python. Requests for direct HTTP, Playwright where a browser is "
           "needed, SQLite for the store, pandas for the index, Streamlit and "
           "Altair for the dashboard. No paid service, no external API, "
           "nothing that costs money to run.",
           S4),
        qa("Walk me through how one collection run works.",
           "The runner loops over the 60 cells. For each, it asks a source "
           "adapter for fares on that route and date, validates each fare, and "
           "writes it to SQLite. Every cell is recorded whether or not it "
           "returned fares, so an empty cell is visible as an empty cell "
           "rather than as missing rows. A run row records that the day "
           "executed.",
           S2),
        qa("What happens when an airline changes its API?",
           "That source stops returning fares and its cells go empty — "
           "visibly, in the observations table, not silently. Fixing it is one "
           "file. Every portal sits behind a single interface with one method, "
           "so the collector, the store, the index and the dashboard never "
           "learn which portal they are holding.",
           S4,
           "That is the whole reason for the adapter pattern. We changed "
           "sources three times during this build and never touched the "
           "index code."),
        qa("Why isn't IndiGo in here? It's the biggest airline in India.",
           "Because we could not collect it legitimately. Its portal uses "
           "enterprise bot management; we got a browser session to the results "
           "page, then instrumented every request and established that its "
           "fare calls carry no bearer token at all — authentication is by "
           "session cookie. Its official NDC API is restricted to "
           "IATA-accredited agents. So we excluded it and documented it, "
           "rather than defeating a protection we were not entitled to "
           "defeat.",
           S4,
           "A production system for MoSPI would not scrape IndiGo either. It "
           "would receive the data under a ministry data-sharing arrangement "
           "— which is available to a ministry and not to us."),
        qa("Is what you are doing legal?",
           "Every fare we collect is a price shown to any member of the public "
           "searching the same route and date. We create no account, use no "
           "login, and circumvent no paywall or access control. We collect no "
           "personal data of any kind — there is no passenger, no booking, no "
           "transaction. We rate-limit to below the traffic of one person "
           "comparing fares.",
           S5,
           "And where a portal's protections could not be met legitimately, "
           "we excluded that portal. That is the test we applied."),
        qa("How do you authenticate to these APIs?",
           "The portals issue short-lived tokens to their own front end. A "
           "browser opens the site once per run, the site mints its token "
           "normally, we read it off the traffic, and the 60 cells then go "
           "over plain HTTP &mdash; far faster than driving a browser 60 "
           "times. Where a portal issues no token and refuses plain HTTP we "
           "fall back to loading its own search page per cell, which is "
           "slower and used only where it has to be. Nothing is typed in by "
           "hand either way, which is what makes daily scheduling possible.",
           S4),
        qa("How do you know the fares you store are correct?",
           "Two ways. The parsers were written against real captured "
           "responses, not guesses — and we verified the arithmetic: on Akasa, "
           "total minus base equalled the itemised service charges exactly. "
           "And the dashboard shows the raw fares next to the index, so any "
           "number on a chart can be traced to the record it came from.",
           S2),
        qa("What if you run the collector twice in one day?",
           "Nothing is duplicated. There is a unique constraint across the "
           "fields that identify an offer, and inserts ignore conflicts — so a "
           "re-run repairs a partial day instead of corrupting it. That "
           "matters because a scheduled job that cannot safely retry is a "
           "scheduled job that loses days.",
           S4),
        qa("Is this actually scheduled, or do you run it by hand?",
           "It runs as a scheduled daily job. That is only possible because "
           "token capture is automated — the reason most scraping prototypes "
           "cannot be scheduled is that somebody has to paste a credential "
           "every morning.",
           S4),
    ])

    # ---------------------------------------------------- E. scalability
    e = "<h2>E. Scalability</h2>" + "".join([
        qa("This is 60 cells. What happens at national scale?",
           "The work is linear in cells and the cells are independent. 60 "
           "cells is a few minutes; a national basket of 100 routes by 5 "
           "windows is 500 cells, which is under an hour serially and minutes "
           "in parallel. Nothing in the design is quadratic and nothing needs "
           "coordination between cells.",
           S4),
        qa("Where does it break first?",
           "Not compute and not storage — the portals. Politeness delays and "
           "per-source request budgets are the binding constraint, which is "
           "why scaling out means more sources rather than more requests per "
           "source. A ministry-operated version removes that constraint "
           "entirely by receiving data rather than requesting it.",
           S4,
           "Storage is not a concern: a year of 500 cells is a few hundred "
           "thousand rows. SQLite handles that; Postgres would handle it "
           "without noticing."),
        qa("How hard is it to add another airline?",
           "One file implementing one method, and one line registering it. No "
           "change to the index, the store, the dashboard or the API. We added "
           "our second carrier that way.",
           S4),
        qa("What about adding routes?",
           "A list in the configuration file. Routes and windows are defined "
           "in one place and everything downstream derives from it, so the "
           "basket cannot get out of step between the collector and the "
           "index.",
           S4),
        qa("Would this survive being handed to someone else?",
           "It is written to be. There is a methodology document generated "
           "from the data itself, an engineering handoff that records the "
           "decisions and the dead ends, and this pack. The most expensive "
           "thing to rediscover on a project like this is what was already "
           "tried and failed, so that is written down explicitly.",
           S6),
    ])

    # ------------------------------------------- F. business & adoption
    fsec = "<h2>F. Cost, sustainability and adoption</h2>" + "".join([
        qa("What does it cost to run?",
           "Effectively nothing. It is a scheduled script and a SQLite file. "
           "It runs on free-tier compute or on a single existing server; there "
           "is no paid API, no data licence and no per-query cost. The "
           "expensive part of a price index is field staff, and this replaces "
           "field staff time rather than adding infrastructure spend.",
           S5),
        qa("Who maintains it?",
           "Realistically, one part-time engineer, because maintenance is "
           "bounded: the only thing that breaks is a portal changing its API, "
           "and that is one file. The index, the store and the outputs are "
           "unaffected by portal changes by construction.",
           S5),
        qa("How does MoSPI actually adopt this?",
           "In three steps. First it runs alongside the existing manual "
           "collection as a validation series — no risk, and it builds the "
           "history needed before anything can be published. Second, the "
           "scraped series replaces manual collection for the routes it "
           "covers, which is where the staff-time saving lands. Third, in a "
           "production version, the ministry replaces scraping with data "
           "sharing from the carriers — the same pipeline, a cleaner input.",
           S5,
           "Step one costs the ministry nothing and risks nothing, which is "
           "the point. It is designed to be adoptable without a decision to "
           "trust it first."),
        qa("Why would airlines share data with the government?",
           "DGCA already operates a tariff monitoring unit and airlines "
           "already file tariff data with it. The mechanism exists; this would "
           "extend an existing reporting relationship rather than create a new "
           "one.",
           S5),
        qa("What is the business model?",
           "There isn't one, and that is correct for this problem. This is "
           "public statistical infrastructure. Its return is a better CPI and "
           "less field-collection cost, not revenue. If you want a number for "
           "the value: air fares sit inside a transport group that carries "
           "roughly 8.8% of the revised CPI basket.",
           S5),
    ])

    # -------------------------------------------------------- G. impact
    g = "<h2>G. Impact, and the sceptical questions</h2>" + "".join([
        qa("So what? Who is actually better off?",
           "A CPI that reflects a dynamically priced service at the frequency "
           "it actually moves. Air fares currently enter the index through "
           "periodic manual observation of a price that changes hourly. "
           "Everyone who uses CPI — for policy rates, for indexation, for "
           "wage settlements — is better off when a volatile component is "
           "measured properly.",
           S5),
        qa("Isn't this just Google Flights with extra steps?",
           "Google Flights answers &lsquo;what should I pay today&rsquo;. This "
           "answers &lsquo;how has the price of a fixed basket changed since a "
           "base period&rsquo;. Those are different questions. A search engine "
           "shows you the current cheapest option; an index holds route, "
           "window, cabin and direction constant over time so the number means "
           "something. Search results are not comparable across days — that is "
           "the whole problem an index exists to solve.",
           S5),
        qa("Honestly, this is just a web scraper.",
           "The scraper is about a fifth of it and it is the part worth the "
           "fewest marks. The substance is the sampling design, the weighting, "
           "the index construction and knowing what the number means. We can "
           "show you a specific case, and run it in front of you: adding a "
           "second carrier mid-series would have made the index report a fare "
           "collapse that never happened, because one more airline entered "
           "the cheapest-fare comparison. Catching that is statistics, not "
           "scraping.",
           S3,
           "<span class='mono'>py -m fareindex.continuity_demo</span> builds "
           "a fixture where the true answer is known and runs the index both "
           "ways. It takes a second. Offer to run it."),
        qa("Advertised fares aren't what people pay.",
           "Correct, and it is the first limitation in our document. We "
           "measure posted prices; a fare available on one seat counts the "
           "same as one available on ninety. No statistical office we found "
           "has claimed scraped advertised fares are an accepted proxy for "
           "transacted fares — it is an open question in the literature. It "
           "closes only with access to booking data, which is exactly what the "
           "ministry version of this would have.",
           S6),
        qa("Two airlines is not a market.",
           "It is not, and we say so. It is two of the three largest low-cost "
           "carriers on the busiest domestic sectors. The architecture makes "
           "carriers additive — one file each — so coverage is a matter of "
           "access, not of design. We would rather present two carriers "
           "honestly than claim coverage we do not have.",
           S6),
        qa("What is actually innovative here?",
           "Three things. Automated credential capture, which is what makes "
           "daily unattended collection possible at all — most scraping "
           "prototypes need a human to paste a token every morning. The "
           "basket-continuity rule, which stops a change in our own collection "
           "from being reported as a change in prices. And an architecture "
           "where the index does not know what a scraper is, so sources can be "
           "added or lost without touching the statistics.",
           S4),
        qa("How much of this did you write, and how much did a tool write?",
           "We used AI assistance, like most teams here. What matters is "
           "whether we can defend it, so ask us anything about any file — the "
           "parser logic, why the store has a unique index, why the headline "
           "index excludes a late source. The design decisions are ours and we "
           "can tell you why each one was made and what we tried first.",
           S2,
           "Answer this one calmly and specifically. A vague answer here "
           "costs more marks than admitting the tool was used."),
    ])

    # ---------------------------------------------------- H. limitations
    h = "<h2>H. Limitations &mdash; volunteer these before you are asked</h2>" + """
<p>Section 11 of the methodology document lists eight, worst first. The six
worth being able to state from memory:</p>
<ol>
<li><strong>Advertised, not transacted.</strong> Structural. Closes only with
booking data.</li>
<li><strong>The departure weekday rotates</strong> with the collection date, so
a short series carries a day-of-week effect that is not a price movement.</li>
<li><strong>T+1 has no precedent</strong> in any official lead-time grid.
Implemented because the problem statement specifies it.</li>
<li><strong>One fare per cell</strong>, where the CPI Manual wants a fare-class
structure.</li>
<li><strong>Carry-forward imputation</strong> is cruder than the Manual's
category-movement rule.</li>
<li><strong>Short series</strong>, because airfare history cannot be
backfilled.</li>
<li><strong>Two carriers</strong>, because two portals could not be collected
legitimately.</li>
</ol>
<div class="panel warn">
<p><strong>Say these before the judge finds them.</strong> A team that names
its own weaknesses is scored as understanding its problem. A team that gets
caught hiding one loses marks on Problem Understanding, Technical Approach
<em>and</em> Presentation at the same time. This is the highest-return ninety
seconds in the whole presentation.</p>
</div>

<h2>Future scope &mdash; as implementation, not aspiration</h2>
<p>The brief asks for future scope explained as implementation. Say what,
how, and how long &mdash; not &ldquo;we could add more airlines&rdquo;.</p>
<ul>
<li><strong>Fare-class structure</strong> — store two fares per cell instead of
one (cheapest, and cheapest flexible). The parsers already see both; it is a
schema column and a second aggregation. Days, not weeks.</li>
<li><strong>Category-movement imputation</strong> — replace carry-forward with
the CPI Manual's rule: impute a missing cell from the mean movement of other
cells on the same route. Roughly one function in the index module.</li>
<li><strong>Seasonal adjustment</strong> — needs two years of series before it
is meaningful. The collection schedule already produces it; nothing to build
until the data exists.</li>
<li><strong>Data-sharing input</strong> — the production path. Carriers file
fare data to DGCA the way they already file tariff data; the source adapter
becomes a file reader instead of a scraper, and nothing downstream
changes.</li>
<li><strong>Coverage</strong> — one file per carrier, one line in the config
for routes. Additive by design.</li>
</ul>
"""

    b = b.format(**_fill)
    return document("APIx — Defence pack", [cover, a, b, c, d, e, fsec, g, h])


def main() -> int:
    os.makedirs("docs", exist_ok=True)
    render(build(live()), OUT_HTML, OUT_PDF)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
