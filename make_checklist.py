#!/usr/bin/env python3
"""Generate docs/MORNING-CHECKLIST.pdf — the run order for the last day.

Ordered by what blocks what. Everything above the line has to happen before
the presentation exists; everything below it makes the presentation better.

    py make_checklist.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docgen import document, esc, render  # noqa: E402

OUT_HTML = "docs/MORNING-CHECKLIST.html"
OUT_PDF = "docs/MORNING-CHECKLIST.pdf"

EXTRA_CSS = """
<style>
.step { margin: 0 0 11pt; padding-left: 20pt; text-indent: -20pt; }
.step .box { display: inline-block; width: 9pt; height: 9pt;
             border: 1.4px solid #6f7a89; border-radius: 2px;
             margin-right: 7pt; vertical-align: -0.5pt; }
.step .t { font-weight: 640; }
.step .mins { color: #9aa4b2; font-weight: 400; font-size: 8.6pt; }
.step p { margin: 3pt 0 0 20pt; text-indent: 0; }
/* .step sets a hanging indent for the checkbox; code blocks must opt out
   or every line after the first is pushed right. */
.step pre { margin: 5pt 0 0 20pt; text-indent: 0; }
hr.split { border: 0; border-top: 1px solid #252a33; margin: 16pt 0; }
</style>
"""


def step(title: str, mins: str, body: str = "") -> str:
    return (f'<div class="step"><span class="box"></span>'
            f'<span class="t">{title}</span> '
            f'<span class="mins">{mins}</span>{body}</div>')


def state() -> str:
    try:
        from fareindex.apix import load_fares, source_spans
        df = load_fares()
        spans = source_spans(df)
        bits = [f"{name} through {row['last'].date()} ({int(row['rows']):,} rows)"
                for name, row in spans.iterrows()]
        return (f"{len(df):,} records, "
                f"{df.collection_date.nunique()} collection days &mdash; "
                + esc("; ".join(bits)))
    except Exception:                                        # noqa: BLE001
        return "data store not readable from here"


def build() -> str:
    today = date.today().isoformat()

    # Built outside the f-string below: an f-string expression may not
    # contain a backslash, and these carry newlines and quotes.
    s_collect = step(
        "Finish the day-3 collection", "~15 min, mostly waiting",
        "<p>SpiceJet stopped at 20 rows last night, so day three is "
        "incomplete. PowerShell, from the repo root:</p>"
        "<pre>$env:SPICEJET_HEADLESS = &quot;1&quot;\n"
        "py collect.py --source akasa\n"
        "py collect.py --source spicejet_browser\n"
        "py collect.py --export\n"
        "py -m fareindex.apix</pre>"
        "<p>Check the output says three collection days and that no source "
        "reports 0/60. <span class='mono'>set VAR=1</span> does nothing in "
        "PowerShell &mdash; it has to be <span class='mono'>$env:</span>.</p>")

    s_docs = step(
        "Regenerate the four documents", "2 min",
        "<pre>py make_methodology.py\n"
        "py make_qa_pack.py\n"
        "py make_code_walkthrough.py\n"
        "py make_checklist.py</pre>"
        "<p>Every figure in them is read from the store, so they are wrong "
        "until this is run after the final collection.</p>")

    s_verify = step(
        "Verify one SpiceJet fare against the live site", "10 min",
        "<p>The parser assumes <span class='mono'>fareAmount + "
        "taxesAndFeesAmount</span> is what a traveller pays. That has never "
        "been checked. Open spicejet.com, search one route and date the "
        "collector stored, and compare. If it does not match, the SpiceJet "
        "numbers must come off the slides &mdash; a wrong fare in front of a "
        "statistics ministry is worse than one fewer carrier.</p>")

    s_push = step(
        "Commit and push", "10 min",
        "<pre>git add -A\n"
        "git commit -m &quot;Weight normalisation fix, docs, dashboard&quot;\n"
        "git push</pre>"
        "<p>Around twenty files are uncommitted. Confirm "
        "<span class='mono'>.gitignore</span> still excludes every "
        "<span class='mono'>.*_token</span> and <span class='mono'>.*_cookie"
        "</span> file before pushing.</p>")

    s_admin = step(
        "Confirm the administrative blockers",
        "10 min, and not yours to fix if the answer is bad",
        "<p>Two things nobody has confirmed: whether PS 26056 is on the "
        "SPOC's blocked list, and whether the faculty mentor is registered. "
        "Both are fatal and both are somebody else's decision, so ask "
        "early.</p>")

    s_slots = step(
        "Assign the six speaking slots and send out the defence pack",
        "15 min",
        "<p>All six members must speak; the slots and their Q&amp;A ownership "
        "are on page 1 of <span class='mono'>docs/QA-DEFENCE.pdf</span>. Send "
        "it this morning, not tonight &mdash; each person needs time to "
        "actually own a section rather than memorise a paragraph.</p>")

    s_demo = step(
        "Run the continuity demonstration once, and watch it", "2 min",
        "<pre>py -m fareindex.continuity_demo</pre>"
        "<p>This is the strongest thirty seconds you have: a case where the "
        "naive index reports a fare collapse that never happened. Knowing the "
        "output by heart means you can offer to run it live.</p>")

    s_deck = step(
        "Build the deck", "2&ndash;3 hours",
        "<p>Six sections matching the six speakers. The methodology document "
        "is already the script; the deck is its headlines. Ten minutes of "
        "content, not twelve &mdash; overrunning costs marks under "
        "Presentation and eats the Q&amp;A you are prepared for.</p>")

    s_rehearse = step(
        "Rehearse once, with a timer", "45 min",
        "<p>Full run, all six speakers, then a Q&amp;A drill: somebody reads "
        "questions from the defence pack at random and the owner answers in "
        "two sentences. Do the hostile ones &mdash; &ldquo;this is just a web "
        "scraper&rdquo;, &ldquo;how much did you write yourself&rdquo;. Those "
        "are the ones that go badly unrehearsed.</p>")

    s_selftest = step(
        "Read the ten self-test questions", "20 min",
        "<p>Last page of <span class='mono'>docs/CODE-WALKTHROUGH.pdf</span>. "
        "Answer them out loud. Whichever one stalls is the file to "
        "reread.</p>")

    s_dgca = step(
        "Spot-check the DGCA weights against DGCA's own portal", "15 min",
        "<p>The passenger figures came from a published mirror, verified by "
        "recomputation but not against a DGCA PDF. Two months matched is "
        "enough to say it was checked.</p>")

    s_aix = step(
        "Air India Express", "30 min to find out, hours to finish",
        "<p>It runs the same reservation platform as Akasa and flies all six "
        "city pairs. Capture its fare request in DevTools and see whether it "
        "carries a bearer token. <strong>Do not start this before the deck "
        "exists.</strong> A third carrier is worth fewer marks than a "
        "rehearsed presentation, and this is exactly the trap that ate the "
        "last three days.</p>")

    page = EXTRA_CSS + f"""
<span class="tag mute">SIH 2026 · PS 26056</span>
<h1>Morning run order</h1>
<p class="sub">Generated {today}. State right now: {state()}</p>
<div class="rule"></div>

<div class="panel warn">
<p><strong>Collection first, before anything else.</strong> A collection date
cannot be recollected. Every other task on this page can be done at 11pm; this
one cannot be done tomorrow.</p>
</div>

<h2>Blocking &mdash; do these first</h2>

{s_collect}
{s_docs}
{s_verify}
{s_push}
{s_admin}

<hr class="split">

<h2>Presentation &mdash; the 90 marks</h2>

{s_slots}
{s_demo}
{s_deck}
{s_rehearse}
{s_selftest}

<hr class="split">

<h2>Only if everything above is done</h2>

{s_dgca}
{s_aix}

<div class="panel">
<p><strong>If you only get through the first block and the rehearsal, you are
in good shape.</strong> The system works, the numbers are honest, the
methodology is documented and the weaknesses are named. What is left is
delivery, and delivery is what the other 90 marks measure.</p>
</div>
"""
    return document("APIx — Morning run order", [page])


def main() -> int:
    os.makedirs("docs", exist_ok=True)
    render(build(), OUT_HTML, OUT_PDF)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
