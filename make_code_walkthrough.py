#!/usr/bin/env python3
"""Generate docs/CODE-WALKTHROUGH.pdf — what you have to understand to
defend this codebase.

Not API documentation. This is the subset of the code that carries an idea
worth explaining, each with the reason it is written that way and the
sentence to say when a judge points at it.

    py make_code_walkthrough.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docgen import document, esc, render, table  # noqa: E402

OUT_HTML = "docs/CODE-WALKTHROUGH.html"
OUT_PDF = "docs/CODE-WALKTHROUGH.pdf"


def code(src: str) -> str:
    """An ABRIDGED excerpt, not a verbatim quote.

    The snippets here keep the lines that carry the idea and drop the rest
    — imports, unrelated fields, guard clauses that are not the point.
    That is the right choice for teaching, and the wrong one to present as
    a copy of the file, so every block says so. A judge who opens the real
    file should find more code than this, never different code.
    """
    return (f"<pre>{esc(src.strip(chr(10)))}</pre>"
            f"<p class='push' style='margin:-4pt 0 0'>abridged excerpt "
            f"&mdash; the file has more lines than this, none contradicting "
            f"it</p>")


def demo_panel() -> str:
    """The continuity numbers, computed at build time — never typed.

    fareindex/continuity_demo.py builds a fixture whose answer is known
    and runs the index both ways. If a judge asks to see the test, it is
    one command.
    """
    try:
        from fareindex.continuity_demo import run
        d = run()
    except Exception as exc:                                 # noqa: BLE001
        print(f"[walkthrough] continuity demo unavailable: {exc}")
        return ""
    arrow = lambda vs: " &rarr; ".join(f"{v:.2f}" for v in vs)  # noqa: E731
    return (
        "<div class='panel warn'><p><strong>The number that proves it "
        "matters &mdash; and you can run it.</strong> "
        "<span class='mono'>py -m fareindex.continuity_demo</span> builds a "
        f"fixture where every fare rises {d['daily_rise_pct']:.0f}% a day and "
        f"a second carrier appears on day three at {d['undercut_pct']:.0f}% "
        "below the first, then runs the index both ways:</p>"
        f"<pre>true movement                {arrow(d['truth'])}\n"
        f"headline index (this design) {arrow(d['fixed'])}   correct\n"
        f"naive index (all sources)    {arrow(d['naive'])}   "
        f"wrong by {d['naive_error_pct']:.1f}%</pre>"
        "<p>No fare fell. The comparison widened. If you remember one number "
        "from this document, remember that one &mdash; and remember that it "
        "is one command to reproduce in front of whoever asks.</p></div>")


def item(path: str, idea: str, body: str) -> str:
    return (f'<h3><span class="mono" style="color:#e6e8eb">{esc(path)}</span>'
            f'</h3><p><span class="tag">the idea</span> {idea}</p>{body}')


def build() -> str:

    # ------------------------------------------------------------- cover
    cover = """
<span class="tag mute">SIH 2026 · PS 26056 · internal</span>
<h1>The code, explained</h1>
<p class="sub">What you have to understand to defend it &mdash; and the
sentence to say when a judge points at a file</p>
<div class="rule"></div>

<p>You do not need to have memorised this codebase. You need to be able to
answer, for any file a judge points at, three things: <strong>what it does,
why it is written that way, and what would break if it were written the
obvious way instead.</strong> That third one is where the marks are, because
it is the only one that proves the decision was made rather than defaulted
into.</p>

<p>This document covers the parts of the code that carry an idea. The rest is
plumbing and nobody will ask about it.</p>

<h2>The shape of the whole thing, in one paragraph</h2>
<p>A runner walks a fixed grid of 60 cells &mdash; 12 routes by 5
advance-purchase windows. For each cell it asks a <em>source adapter</em> for
fares. The adapter knows how one airline's portal works and nothing else. Every
fare that comes back is validated and written to SQLite; every cell is recorded
whether or not it produced fares. A separate step reads the store, reduces it
to one price per cell per day, converts those to price relatives against a base
period, weights them by passenger volume and averages them into the index. A
dashboard reads the same store. Nothing downstream of an adapter knows which
airline it is looking at.</p>

<pre>
  <span class="c">portals</span>          <span class="c">adapters</span>            <span class="c">store</span>          <span class="c">index</span>          <span class="c">outputs</span>

  akasaair.com  ->  akasa.py     \\
                                  >   SQLite   ->   apix.py   ->  CSV + JSON API
  spicejet.com  ->  spicejet_       /  fares                       dashboard
                    browser.py         observations
                                       runs
                    ^
                    |
              token_broker.py
              (browser mints
               the credential)
</pre>

<div class="panel">
<p><strong>The one sentence that explains the architecture:</strong> every
portal sits behind a single interface with one method, so the collector, the
store, the index and the dashboard never learn which portal they are holding.
Adding an airline is one new file. Losing an airline changes nothing but
coverage.</p>
</div>

<h2>Five things to be able to say without looking</h2>
<ol>
<li><strong>Why there are two date fields.</strong> Collection date is when we
saw the price; departure date is when the flight leaves; the window is their
difference. Collection date cannot be backfilled, which is why collection
started before anything else was finished.</li>
<li><strong>Why NULL is not zero.</strong> A missing tax component means the
portal did not disclose it. Zero would be a claim that it was not charged.</li>
<li><strong>Why the store has a unique index.</strong> So the collector can be
re-run on the same day and repair a partial run instead of duplicating it. A
scheduled job that cannot safely retry is a job that loses days.</li>
<li><strong>Why a browser is used for authentication but not for
collection.</strong> The browser exists to make the site mint its own token.
Once we have it, 60 plain HTTP calls are far faster than driving a browser 60
times.</li>
<li><strong>Why the headline index excludes a late-joining source.</strong>
Because the cheapest fare across more airlines is cheaper for a reason that is
not a price change.</li>
</ol>
"""

    # ------------------------------------------------------- config/model
    p_config = "<h2>1. The basket, and the record</h2>" + item(
        "fareindex/config.py",
        "One definition of the sampling grid that everything else derives "
        "from.",
        code("""
WINDOWS = (1, 7, 15, 30, 45)
PS_CITY_PAIRS = [("DEL","BOM"), ("DEL","BLR"), ("BOM","BLR"),
                 ("DEL","CCU"), ("BLR","HYD"), ("MAA","DEL")]
ROUTES = [pair for a, b in PS_CITY_PAIRS for pair in ((a, b), (b, a))]
""")
        + "<p>Six city pairs expanded to twelve directional routes by a "
          "comprehension, times five windows, is the 60 cells. The reason this "
          "lives in one file: if the collector and the index disagreed about "
          "what the basket is, the index would be weighting cells that were "
          "never collected and nobody would notice.</p>"
        + '<p><span class="tag warn">if asked</span> <em>&ldquo;Why both '
          'directions?&rdquo;</em> &mdash; they are different products with '
          'different demand and different prices, and our weights are '
          'directional too.</p>'
    ) + item(
        "fareindex/model.py",
        "One immutable record for one observed fare, that refuses to be "
        "constructed wrong.",
        code("""
@dataclass(frozen=True)
class FareOffer:
    total_fare_inr: float          # what the traveller actually pays
    base_fare_inr: Optional[float] = None    # None means "not disclosed"
    taxes_inr: Optional[float] = None        # -- which is NOT zero

    @property
    def advance_window_days(self) -> int:
        return (self.departure_date - self.collection_date).days

    def validate(self) -> None:
        if self.advance_window_days < 0:
            raise ValueError(
                f"departure {self.departure_date} precedes collection "
                f"{self.collection_date}")
        if not (self.total_fare_inr > 0):
            raise ValueError(f"non-positive fare: {self.total_fare_inr}")
""")
        + "<p>Three decisions here. <strong>frozen=True</strong> means a fare "
          "cannot be modified after it is read &mdash; an observation is a "
          "fact, and a mutable fact is a bug waiting to happen. "
          "<strong>advance_window_days is a property, not a stored field</strong>, "
          "so it cannot disagree with the two dates it is derived from. "
          "<strong>validate() raises rather than warns</strong>, because a fare "
          "with a negative window is not a slightly wrong fare, it is evidence "
          "the parser is misreading the response.</p>"
        + '<p><span class="tag warn">if asked</span> <em>&ldquo;Why store '
          'components at all if you only use the total?&rdquo;</em> &mdash; the '
          'problem statement requires the base/tax decomposition in the '
          'database, and it is what lets us verify a parser: on Akasa, total '
          'minus base equalled the itemised service charges exactly.</p>'
    )

    # ------------------------------------------------------------- store
    p_store = "<h2>2. The store &mdash; and why it can be re-run</h2>" + item(
        "fareindex/store.py",
        "Three tables, and one constraint that makes the whole thing "
        "schedulable.",
        code("""
CREATE UNIQUE INDEX IF NOT EXISTS ux_fares_offer ON fares (
    origin, destination, departure_date, collection_date,
    source_portal, COALESCE(carrier, ''), COALESCE(flight_number, ''),
    COALESCE(depart_time_local, ''), total_fare_inr
);

...

conn.execute("INSERT OR IGNORE INTO fares (...) VALUES (...)")
""")
        + "<p>The unique index defines what makes two offers the same offer. "
          "<span class='mono'>INSERT OR IGNORE</span> then makes the whole "
          "collector <strong>idempotent</strong>: run it twice on the same day "
          "and the second run writes only what the first one missed. That is "
          "not a nicety. A scheduled job fails halfway sometimes, and if the "
          "repair run duplicated everything, the cheapest-fare-per-cell "
          "calculation would still be right but every count in the system "
          "would be wrong.</p>"
        + "<p>Note the <span class='mono'>COALESCE(carrier, '')</span>. In SQL, "
          "NULL is not equal to NULL, so two rows that both have a NULL flight "
          "number would <em>not</em> collide on a plain unique index &mdash; "
          "the duplicate protection would silently do nothing. Coalescing to "
          "empty string is what makes the constraint actually bite.</p>"
        + "<h3>The three tables, and why the second one exists</h3>"
        + table(["Table", "Holds", "Why it matters"], [
            ["<span class='mono'>fares</span>", "One row per observed offer",
             "The data"],
            ["<span class='mono'>observations</span>",
             "One row per <em>cell attempted</em>, with how many fares came "
             "back &mdash; including zero",
             "Without it, an empty cell and a cell that was never tried look "
             "identical. That is the difference between &lsquo;no flights&rsquo; "
             "and &lsquo;our scraper broke&rsquo;."],
            ["<span class='mono'>runs</span>",
             "One row per collection run, with counts and timing",
             "Evidence that daily collection actually happened, which the "
             "problem statement asks for."],
        ])
        + '<p><span class="tag warn">if asked</span> <em>&ldquo;Why SQLite and '
          'not Postgres?&rdquo;</em> &mdash; a year of a national-scale basket '
          'is a few hundred thousand rows; SQLite handles that comfortably and '
          'needs no server. The schema is ordinary SQL, so moving to Postgres '
          'is a connection string, not a rewrite.</p>'
    )

    # ---------------------------------------------------------- adapters
    p_src = "<h2>3. Sources &mdash; the most important design decision</h2>" + item(
        "fareindex/sources/base.py",
        "The entire portal-specific world reduced to one abstract method.",
        code("""
class FareSource(ABC):
    name: str = "unnamed"
    daily_request_budget: int = 10_000

    @abstractmethod
    def fetch(self, origin, destination, departure_date) -> List[FareOffer]:
        '''Raise FareSourceError on failure;
           return [] when the source legitimately has no fares.'''
""")
        + "<p>This is the file to point at when asked about architecture. Every "
          "portal &mdash; a plain HTTP API, a browser-driven scrape, a future "
          "file drop from a data-sharing arrangement &mdash; is the same shape "
          "to everything else in the system.</p>"
        + "<p>The distinction in that docstring is doing real work. "
          "<strong>Raising means the cell failed</strong> and is recorded as a "
          "failure. <strong>Returning an empty list means the airline does not "
          "fly that route that day</strong>, which is data, not an error. "
          "Collapsing the two is how a broken parser disguises itself as "
          "missing data &mdash; which happened to us once and is the reason "
          "the distinction is written down.</p>"
    ) + item(
        "fareindex/sources/akasa.py",
        "A parser written against a real response, joining two halves of the "
        "answer.",
        code("""
# The API returns flights and fares as separate lists joined by a key.
fare_index = {e["key"]: e.get("value") or {}
              for e in data.get("faresAvailable") or []}

for journey in ...:
    des = journey.get("designator") or {}
    if des.get("origin") != origin or des.get("destination") != destination:
        continue          # <- excludes nearby airports the API adds itself
    totals = value.get("totals") or {}
    total = totals.get("fareTotal")       # what the passenger pays
    base  = totals.get("publishedTotal")  # base fare
""")
        + "<p>Two things worth being able to explain. The response splits "
          "flights from fares into separate lists keyed by an id, so the parser "
          "has to join them &mdash; read one half and you get flights with no "
          "prices.</p>"
        + "<p>And the <strong>origin/destination check is not redundant</strong>. "
          "The API searches nearby airports as a courtesy, so a search for "
          "Delhi returns Noida too. Without that filter we would have been "
          "silently storing a different airport's fares in a DEL cell &mdash; "
          "an error that would never crash and never look wrong.</p>"
        + '<p><span class="tag warn">if asked</span> <em>&ldquo;How do you know '
          'the fare is right?&rdquo;</em> &mdash; we checked the arithmetic '
          'against the response: 6,880 minus 5,640 equals 1,240, which matched '
          'the itemised service charges exactly.</p>'
    ) + item(
        "fareindex/sources/spicejet_browser.py",
        "When headers cannot get in, let the page make its own request and "
        "read the answer.",
        code("""
with self._page.expect_response(
        lambda r: "/api/v2/search/lowfare" in r.url,
        timeout=self._timeout) as caught:
    self._page.goto(url, wait_until="commit", timeout=self._timeout)
payload = caught.value.json()
""")
        + "<p>SpiceJet's API returns a nine-byte &lsquo;Forbidden&rsquo; to "
          "plain HTTP even with a valid token and every header copied "
          "verbatim, because its firewall fingerprints the TLS handshake. "
          "Headers cannot fix that; only a real browser can.</p>"
        + "<p>But its results page takes the whole search in the URL. So "
          "instead of forging a request, we navigate to the page and read the "
          "response to the request <em>the page makes on its own behalf</em>. "
          "Nothing is faked &mdash; the request genuinely is the site's.</p>"
        + "<p>The ordering matters and is the part to explain: "
          "<span class='mono'>expect_response</span> is armed <em>before</em> "
          "the navigation starts. Arm it after and the response can arrive "
          "first and be missed.</p>"
    )

    # ------------------------------------------------------------ tokens
    p_tok = "<h2>4. Credentials, without a human</h2>" + item(
        "fareindex/token_broker.py",
        "Browser for authentication, plain HTTP for volume.",
        code("""
def watch(request):
    if api_host in request.url:
        auth = request.headers.get("authorization")
        if auth and len(auth) > 20:
            found.setdefault("token", auth)

page.on("request", watch)
page.goto(site_url)          # the site mints its own token, normally
...
# second place to look: the browser's own cookie jar, which can see
# HttpOnly cookies that page JavaScript cannot.
from_cookie = _token_from_cookies(context.cookies(), cookie_names)
""")
        + "<p>This is the file that makes the project schedulable, and "
          "schedulability is a stated requirement. Most scraping prototypes "
          "need somebody to paste a token every morning; ours opens the site, "
          "lets it authenticate itself the way it normally does, and reads the "
          "credential off its own traffic.</p>"
        + "<p>The cookie path is worth knowing: "
          "<span class='mono'>context.cookies()</span> can read HttpOnly "
          "cookies, which <span class='mono'>document.cookie</span> inside the "
          "page cannot. Earlier attempts to read the token from inside the page "
          "came back empty for exactly that reason.</p>"
        + "<p>Sources then <strong>self-heal</strong>: a 401 or 403 triggers "
          "one forced token refresh and a retry, so an expired credential "
          "costs a second, not a day.</p>"
        + '<p><span class="tag warn">if asked</span> <em>&ldquo;Why not just '
          'use the browser for everything?&rdquo;</em> &mdash; because 60 page '
          'loads take minutes and 60 HTTP calls take seconds. The browser is '
          'the expensive part, so it is used once per run rather than once per '
          'cell.</p>'
    )

    # ------------------------------------------------------------- index
    p_idx = "<h2>5. The index &mdash; where the statistics live</h2>" + item(
        "fareindex/apix.py",
        "Reduce to one price per cell per day, convert to relatives, weight, "
        "average.",
        code("""
def cell_prices(df):
    '''Cheapest fare per (route, window, collection date).'''
    return (df.groupby(["route", "advance_window_days", "collection_date"],
                       as_index=False)
              .total_fare_inr.min())

...

for cell, base_price in base.items():
    if base_price <= 0:
        continue
    if cell in today.index:
        relative = float(today.loc[cell]) / float(base_price)
        last_relative[cell] = relative
    elif cell in last_relative:
        relative = last_relative[cell]     # carried forward, flagged
        carried += 1
    else:
        continue
""")
        + "<p>Read it in that order and the whole method is visible. "
          "<span class='mono'>groupby(...).min()</span> is the price concept "
          "&mdash; cheapest fare per cell. The division is the price relative. "
          "The <span class='mono'>elif</span> is the imputation rule, and note "
          "that <span class='mono'>carried</span> is incremented, not hidden: "
          "the count of imputed cells is published beside the index every "
          "day.</p>"
        + "<p>The final <span class='mono'>else: continue</span> matters too. A "
          "cell that has <em>never</em> been seen has nothing to carry forward, "
          "so it is dropped rather than invented.</p>"
        + item(
            "fareindex/apix.py &mdash; split_sources()",
            "The rule that stops our own collection schedule from looking "
            "like a price movement.",
            code("""
def split_sources(df):
    spans = source_spans(df)
    base = spans["first"].min()
    continuous = sorted(spans.index[spans["first"] == base])
    late       = sorted(spans.index[spans["first"] >  base])
    return continuous, late
""")
            + "<p>A cell's price is the cheapest fare across every source. So "
              "the day a second airline joins the collection, cells it flies "
              "get cheaper &mdash; not because fares fell, but because the "
              "comparison widened. The headline index therefore uses only "
              "sources present from the base period; a later source gets its "
              "own series, and a combined series is re-based to the first day "
              "everything was running.</p>"
            + demo_panel())
    )

    # ---------------------------------------------------- runner + trace
    p_run = "<h2>6. The runner, and one fare's journey</h2>" + item(
        "collect.py",
        "Walk the grid, ask an adapter, record whether it worked.",
        "<p>The runner is deliberately boring: it builds a source by name, "
        "loops the 60 cells, catches "
        "<span class='mono'>FareSourceError</span> per cell so that one bad "
        "cell never kills a run, records an observation either way, and writes "
        "a run row at the end. The flags are "
        "<span class='mono'>--source --limit --thin --coverage --export</span>."
        "</p>"
        "<p><strong>Catching per cell, not per run, is the design point.</strong> "
        "A single route that an airline stopped flying should cost you one "
        "empty cell, not the day's data.</p>"
    ) + """
<h3>Trace one fare, end to end</h3>
<p>If you can narrate this, you can answer almost any code question.</p>
<ol>
<li><span class="mono">collect.py</span> reaches the cell DEL&ndash;BOM at
T+7, computes the departure date as today plus seven days, and calls
<span class="mono">source.fetch("DEL", "BOM", that_date)</span>.</li>
<li>The adapter needs a token. It checks an environment variable, then a
gitignored dotfile, then asks <span class="mono">token_broker</span>, which
opens a browser and reads the token off the site's own traffic.</li>
<li>It POSTs the portal's own payload shape, waits the politeness delay, and
gets JSON back. A 403 triggers one forced refresh and a retry.</li>
<li><span class="mono">_parse</span> walks the response, filters out any
itinerary whose origin and destination are not the ones asked for, and builds
one <span class="mono">FareOffer</span> per flight &mdash; total, base, taxes,
carrier, flight number, departure time.</li>
<li>Back in the runner, each offer is validated, then written with
<span class="mono">INSERT OR IGNORE</span>. An observation row records that this
cell was attempted and how many offers it produced.</li>
<li><span class="mono">--export</span> flattens the store to
<span class="mono">data/fares_export.csv</span>, so everything downstream needs
pandas rather than SQL.</li>
<li><span class="mono">apix.py</span> takes the minimum fare in that cell for
that day, divides it by the same cell's base-period price, multiplies by the
route's DGCA weight, and adds it to the weighted mean that becomes the day's
index.</li>
<li>The dashboard and <span class="mono">docs/api/index.json</span> read the
result.</li>
</ol>
"""

    # ------------------------------------------------------------- final
    p_test = """
<h2>7. Self-test</h2>
<p>Answer these out loud, without opening anything. If one of them stalls, that
is the file to reread.</p>
<ol>
<li>Why is <span class="mono">advance_window_days</span> a property rather than
a column you set?</li>
<li>What breaks if the store has no unique index, and why would you not notice
immediately?</li>
<li>Why does <span class="mono">COALESCE(carrier, '')</span> appear in that
index?</li>
<li>A source returns an empty list. A source raises. What is the difference and
where does each end up?</li>
<li>Why is <span class="mono">expect_response</span> armed before
<span class="mono">goto</span> and not after?</li>
<li>Why is the browser used once per run and not once per cell?</li>
<li>A cell is missing today. Walk through what the index does &mdash; and what
it does if that cell has never been seen at all.</li>
<li>Why does the headline index exclude SpiceJet, and what number shows why
that matters?</li>
<li>Why are price relatives averaged rather than the fares themselves?</li>
<li>Where do the route weights come from, and what is the Mumbai trap?</li>
</ol>

<div class="panel good">
<p><strong>If a judge asks how much of this you wrote yourself</strong>, the
answer is calm and specific: you used AI assistance, like most teams, and the
test of that is whether you can defend it &mdash; so invite them to point at
any file. Then do exactly what this document trains you to do: say what it
does, why it is written that way, and what would break otherwise. A vague
answer to that question costs more marks than the admission does.</p>
</div>

<div class="foot">
APIx &mdash; code walkthrough. Regenerate with
<span class="mono">py make_code_walkthrough.py</span>. Companion documents:
<span class="mono">docs/METHODOLOGY.pdf</span> (method, compliance,
limitations) and <span class="mono">docs/QA-DEFENCE.pdf</span> (every expected
question, with owners).
</div>
"""

    return document("APIx — Code walkthrough",
                    [cover, p_config, p_store, p_src, p_tok, p_idx, p_run,
                     p_test])


def main() -> int:
    os.makedirs("docs", exist_ok=True)
    render(build(), OUT_HTML, OUT_PDF)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
