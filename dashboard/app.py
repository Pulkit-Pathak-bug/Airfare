"""APIx dashboard — PS deliverable (d).

Run:  streamlit run dashboard/app.py     (from the repo root)

Reads data/fares_export.csv. Never touches the database, never writes
anything — it is a read-only view over the collector's output, so it can
be run while a collection is in progress.

The three visualisations the problem statement names:
  * price trends      — the daily APIx over time
  * sector heatmap    — cheapest fare by route x advance-purchase window
  * lead-time         — fare against how far ahead you book. This is the
    elasticity curve   chart the whole sampling design exists to produce.
"""

from __future__ import annotations

import json
import os
import sys

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fareindex.apix import (EXPORT_CSV, ROUTE_WEIGHTS_CSV,  # noqa: E402
                            build_index,
                            cell_prices, load_fares, resample, source_spans,
                            split_sources)
from fareindex.config import ROUTES, WINDOWS  # noqa: E402

GRID_CELLS = len(ROUTES) * len(WINDOWS)

# Label for a fare with no class from the portal. Not a class — an absence.
UNDISCLOSED = "class not disclosed"

# Validated palette (see the data-viz reference instance). Categorical
# slots 1 and 2 clear every CVD and normal-vision gate as a pair; the
# sequential blue ramp is used light->dark for magnitude.
SERIES = ["#2a78d6", "#eb6834"]
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#104281"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#52514e"
GRID = "#e6e6e3"

st.set_page_config(page_title="APIx — Airfare Price Index",
                   page_icon="✈", layout="wide")


def chart_base(chart):
    """House style: recessive chrome, text in ink tokens not series colour."""
    return (chart
            .configure_view(strokeWidth=0, fill=SURFACE)
            .configure_axis(grid=True, gridColor=GRID, gridOpacity=0.9,
                            domainColor=GRID, tickColor=GRID,
                            labelColor=INK_MUTED, titleColor=INK_MUTED,
                            labelFontSize=12, titleFontSize=12,
                            titleFontWeight="normal")
            .configure_legend(labelColor=INK, titleColor=INK_MUTED,
                              labelFontSize=12, titleFontSize=11,
                              symbolStrokeWidth=3)
            .configure_title(color=INK, fontSize=15, anchor="start",
                             fontWeight=600))


@st.cache_data
def load(path: str, mtimes: tuple):
    """Load and index the store.

    `mtimes` is not used in the body — it is here to be part of the
    cache key. Streamlit caches on the arguments, so caching on the path alone
    would keep serving the first load for the life of the process: run a
    fresh collection during a demo and the page would show yesterday's
    numbers while insisting they were current. Passing the file's
    modification time makes a rewritten file a cache miss.
    """
    df = load_fares(path)
    # Not every portal discloses a fare class. SpiceJet's endpoint is a
    # low-fare calendar: it returns a price for a date and nothing else.
    # Those rows are labelled for what they are rather than with a dash,
    # which reads like a class called "—" and quietly invents a category.
    df["fare_class"] = df.fare_class.fillna(UNDISCLOSED)

    # The headline index uses only sources collecting since day one. A
    # source that joins later makes its cells look cheaper — there is
    # simply one more airline in the "cheapest fare" comparison — and an
    # index that let that through would report a price fall caused by our
    # own collection schedule. See the basket-continuity note in apix.py.
    continuous, late = split_sources(df)
    headline_df = df[df.source_portal.isin(continuous)] if continuous else df
    daily, meta = build_index(headline_df)
    meta["headline_sources"] = continuous
    meta["late_sources"] = late
    weekly, monthly = resample(daily)

    # One index per source, each on its own base. This is what makes the
    # continuity rule visible rather than merely asserted in a caption.
    series = []
    for name in sorted(df.source_portal.unique()):
        sdaily, smeta = build_index(df[df.source_portal == name])
        if sdaily.empty:
            continue
        block = sdaily[["date", "apix"]].copy()
        block["series"] = name
        series.append(block)
    by_source = (pd.concat(series, ignore_index=True) if series
                 else pd.DataFrame(columns=["date", "apix", "series"]))

    return df, daily, weekly, monthly, meta, by_source, source_spans(df)


if not os.path.exists(EXPORT_CSV):
    st.error(
        f"`{EXPORT_CSV}` not found. Run the collector first:\n\n"
        "```\npy collect.py --source akasa\npy collect.py --export\n```\n\n"
        "Run streamlit from the repo root, not from inside dashboard/."
    )
    st.stop()

def _mtimes() -> tuple:
    """Every input file's mtime, as part of the cache key.

    Keying on the export alone was not enough: the weights CSV is read
    deep inside build_index, so editing or adding it changed nothing on
    screen until the cache was cleared by hand. A presenter who drops the
    real DGCA weights in minutes before a demo and refreshes the tab would
    have seen the old weight source reported as current.
    """
    out = []
    for path in (EXPORT_CSV, ROUTE_WEIGHTS_CSV):
        try:
            out.append(os.path.getmtime(path))
        except OSError:
            out.append(0.0)
    return tuple(out)


df_all, daily, weekly, monthly, meta, by_source, spans = load(
    EXPORT_CSV, _mtimes())

_, refresh = st.columns([6, 1])
if refresh.button("↻ Reload", help="Re-read the export after a fresh "
                                   "collection run", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.title("APIx — Real-time Airfare Price Index")
st.caption(
    "Prototype for SIH 2026 problem statement 26056 (MoSPI). Fares collected "
    "daily by automated scraping on a fixed route × advance-purchase-window "
    "grid. Laspeyres index, fixed base-period weights, cheapest fare per cell."
)

# The basket-continuity explanation used to sit here as a full-width
# callout. It pushed the index and the charts below the fold, which is the
# wrong trade for the one screen a judge actually looks at. The fact is not
# lost: the "Collection health" expander names each source's basket role,
# and the "Index by source" chart shows the separated series directly.

# ---------------------------------------------------------------- filters
routes_all = sorted(df_all.route.unique())
classes_all = sorted(df_all.fare_class.unique())
f1, f2, f3 = st.columns([3, 2, 2])
routes = f1.multiselect("Routes", routes_all, default=routes_all,
                        placeholder="all routes")
classes = f2.multiselect("Fare class", classes_all, default=classes_all,
                         placeholder="all classes")
source = f3.selectbox("Source", ["all"] + sorted(df_all.source_portal.unique()))

df = df_all.copy()
if routes:
    df = df[df.route.isin(routes)]
if classes:
    df = df[df.fare_class.isin(classes)]
if source != "all":
    df = df[df.source_portal == source]

if df.empty:
    st.warning("No fares match those filters.")
    st.stop()

filtered = (len(routes) < len(routes_all) or len(classes) < len(classes_all)
            or source != "all")
if filtered:
    # The headline index is a FIXED basket. Recomputing it from a filtered
    # subset would not be "the index for these routes" — it would be a
    # different index on a different basket with a different base. So the
    # filters move the fare tables and charts and deliberately leave the
    # index alone; saying so is the difference between a design decision
    # and a page that looks broken when someone filters it.
    st.caption(
        "Filters apply to the fare observations, the lead-time chart, the "
        "heatmap and the table below. **The APIx figure and the price-trend "
        "chart are unfiltered by design** — the index is a fixed basket "
        "with fixed weights, so a subset of it is not a smaller index, it "
        "is a different one."
    )

# ------------------------------------------------------------ stat tiles
latest = daily.iloc[-1] if not daily.empty else None
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("APIx (latest)", f"{latest.apix:,.2f}" if latest is not None else "—",
          help=f"Base {meta.get('base_period', '—')} = 100")
c2.metric("Collection days", meta.get("collection_days", 0))
c3.metric("Fare observations", f"{len(df):,}")
c4.metric("Grid cells reached",
          f"{df.groupby(['route', 'advance_window_days']).ngroups}"
          f"/{GRID_CELLS}",
          help="Cells that have returned a fare on at least one collection "
               "day, out of the full sampling grid. This is coverage of the "
               "GRID. The index basket, quoted below, is smaller: it is "
               "fixed at whatever the base date contained, because a "
               "fixed-weight index cannot admit new cells later.")
c5.metric("Cheapest fare", f"₹{df.total_fare_inr.min():,.0f}")

carried = int(daily.carried_forward.sum()) if not daily.empty else 0
short = meta.get("routes_short_of_full_windows") or {}
st.caption(
    f"Weights: {meta.get('weight_source', '—')}. "
    f"Index basket: {meta.get('basket_cells', 0)} of {GRID_CELLS} cells — "
    f"smaller than the grid reached above because a cell absent on the base "
    f"date cannot join a fixed-weight basket. "
    f"Cell-days imputed by carry-forward so far: {carried}."
    + (f" Routes short of a full window set on the base date: "
       f"{', '.join(f'{r} ({n}/{len(WINDOWS)})' for r, n in short.items())}."
       if short else "")
)

# ------------------------------------------------------------ price trend
st.subheader("Price trend")
if len(daily) < 2:
    st.info(
        f"**{meta.get('collection_days', 0)} collection day so far, so the "
        f"series is a single point at 100.** A collection date cannot be "
        f"backfilled — the index gains one point per day the collector runs. "
        f"Everything else on this page is computed from today's cross-section "
        f"and is already complete."
    )
else:
    # Autoscaling a near-flat series turns a 0.03% move into a cliff. The
    # y-axis is therefore never allowed to span less than two index
    # points around 100 — a small move has to LOOK like a small move, or
    # the chart lies more effectively than a wrong number would.
    lo, hi = float(daily.apix.min()), float(daily.apix.max())
    mid = (lo + hi) / 2
    if hi - lo < 2.0:
        lo, hi = mid - 1.0, mid + 1.0
    else:
        pad = (hi - lo) * 0.1
        lo, hi = lo - pad, hi + pad

    line = alt.Chart(daily).mark_line(
        strokeWidth=2, point=alt.OverlayMarkDef(size=90, filled=True),
        color=SERIES[0],
    ).encode(
        # A three-point daily series autoscales to hour-of-day ticks,
        # which makes a once-a-day process look intraday. Pin it to days.
        x=alt.X("date:T", title="Collection date",
                axis=alt.Axis(format="%d %b", tickCount={"interval": "day",
                                                        "step": 1})),
        y=alt.Y("apix:Q", title="APIx (base = 100)",
                scale=alt.Scale(domain=[lo, hi], zero=False, nice=False)),
        tooltip=[alt.Tooltip("date:T", title="Date"),
                 alt.Tooltip("apix:Q", title="APIx", format=".2f"),
                 alt.Tooltip("cells:Q", title="Cells"),
                 alt.Tooltip("carried_forward:Q", title="Carried forward")],
    )
    baseline = alt.Chart(pd.DataFrame({"y": [100]})).mark_rule(
        color=INK_MUTED, strokeDash=[4, 4], opacity=0.5).encode(y="y:Q")
    st.altair_chart(chart_base((baseline + line).properties(height=280)),
                    use_container_width=True)
    def datestamped(frame):
        """Dates, not midnight timestamps — nobody needs 00:00:00."""
        out = frame.copy()
        if "date" in out:
            out["date"] = pd.to_datetime(out.date).dt.date
        return out

    tab_d, tab_w, tab_m = st.tabs(["Daily", "Weekly", "Monthly"])
    tab_d.dataframe(datestamped(daily), use_container_width=True,
                    hide_index=True)
    tab_w.dataframe(datestamped(weekly), use_container_width=True,
                    hide_index=True)
    tab_m.dataframe(datestamped(monthly), use_container_width=True,
                    hide_index=True)

# ------------------------------------------------------- index by source
_plottable = by_source.groupby("series").size()
if (_plottable >= 2).sum() >= 1 and by_source.series.nunique() > 1:
    st.subheader("Index by source")
    st.caption(
        "Each source indexed on its own base, which is the only way to "
        "compare them. These are deliberately not merged into the headline "
        "series: a source that starts later would make its cells look cheaper "
        "because the cheapest-fare comparison widened, not because fares fell."
    )
    # A source with a single collection day sits at exactly 100 by
    # construction — it IS its own base. Drawn on the same axis as a
    # multi-day line it reads as "this carrier is cheaper", which is not a
    # statement the data supports. Plot only series that have moved, and
    # name the rest.
    counts = by_source.groupby("series").size()
    plotted = sorted(counts[counts >= 2].index)
    single = sorted(counts[counts < 2].index)
    if single:
        st.caption(
            f"{', '.join(single)} has one collection day so far, so its "
            "index is 100 by definition and is not plotted — a single point "
            "cannot be compared with a series that has moved."
        )
    by_source = by_source[by_source.series.isin(plotted)]

    # With only one plottable series this chart is a duplicate of the price
    # trend above it. Say why the section is here and skip the picture.
    if len(plotted) < 2:
        st.caption(
            "Only one source has enough history to plot, so this chart is "
            "held back until a second one does — it would otherwise just "
            "repeat the headline series above."
        )
    if len(plotted) >= 2:
        names = plotted
        palette = [SERIES[i % len(SERIES)] for i in range(len(names))]
        multi = alt.Chart(by_source).mark_line(
            strokeWidth=2, point=alt.OverlayMarkDef(size=70, filled=True),
        ).encode(
            x=alt.X("date:T", title="Collection date",
                    axis=alt.Axis(format="%d %b", tickCount={"interval": "day",
                                                            "step": 1})),
            y=alt.Y("apix:Q", title="Index (each source's own base = 100)",
                    scale=alt.Scale(zero=False, nice=True)),
            color=alt.Color("series:N", title="Source",
                            scale=alt.Scale(domain=names, range=palette),
                            legend=alt.Legend(orient="top-right")),
            tooltip=[alt.Tooltip("series:N", title="Source"),
                     alt.Tooltip("date:T", title="Date"),
                     alt.Tooltip("apix:Q", title="Index", format=".2f")],
        )
        st.altair_chart(chart_base(multi.properties(height=260)),
                        use_container_width=True)

# ------------------------------------------------------ collection health
with st.expander("Collection health — what was attempted, and what came back"):
    st.caption(
        "Coverage is evidence, not decoration: the problem statement asks for "
        "scheduled daily extraction, and an empty cell has to be "
        "distinguishable from a cell that was never tried."
    )
    span_view = spans.reset_index()
    span_view.columns = ["Source", "First collected", "Last collected",
                         "Fare records"]
    span_view["First collected"] = span_view["First collected"].dt.date
    span_view["Last collected"] = span_view["Last collected"].dt.date
    span_view["Basket role"] = [
        "headline" if s in (meta.get("headline_sources") or []) else
        "own series (started late)" for s in span_view.Source]
    st.dataframe(span_view, use_container_width=True, hide_index=True)

    # Which cells of the grid never produced a fare on the latest day.
    latest_day = df_all.collection_date.max()
    seen = set(map(tuple, df_all[df_all.collection_date == latest_day]
                   [["route", "advance_window_days"]].drop_duplicates()
                   .itertuples(index=False, name=None)))
    missing = [f"{o}-{d} @ T+{w}" for o, d in ROUTES for w in WINDOWS
               if (f"{o}-{d}", w) not in seen]
    st.write(f"**{GRID_CELLS - len(missing)} of {GRID_CELLS} cells returned a "
             f"fare on {latest_day.date()}.**")
    if missing:
        st.caption("Empty on that date: " + ", ".join(missing))
    else:
        st.caption("Full grid coverage on that date.")

# ------------------------------------------------- lead-time elasticity
st.subheader("Lead-time elasticity")
st.caption(
    "Cheapest fare against how far ahead the ticket is bought, median across "
    "routes. This is the curve the sampling design exists to measure, and the "
    "reason an average fare per route is not a price index: a seat 1 day out "
    "and a seat 45 days out are different products."
)

# Cheapest fare per cell first, then the median across routes — so a route
# with many fares cannot drag the curve more than a route with few.
per_cell = (df.groupby(["route", "advance_window_days", "fare_class"],
                       as_index=False).total_fare_inr.min())
grouped = per_cell.groupby(["advance_window_days", "fare_class"])
curve = grouped.total_fare_inr.median().rename("fare").reset_index()
curve["cells"] = grouped.total_fare_inr.size().values

# Colour is assigned explicitly rather than by slicing the palette. Two
# reasons: the categorical palette holds two validated colours, so asking
# for a third silently reused one and drew two different series in the
# same blue; and "class not disclosed" is an absence, not a category, so
# it gets a neutral grey rather than competing for a category colour.
classes = sorted(curve.fare_class.unique())
real = [c for c in classes if c != UNDISCLOSED]
domain, rng = [], []
for i, cls in enumerate(real):
    domain.append(cls)
    rng.append(SERIES[i % len(SERIES)])
if UNDISCLOSED in classes:
    domain.append(UNDISCLOSED)
    rng.append(INK_MUTED)

thin = sorted(set(curve[curve.cells < 4].fare_class)) if "cells" in curve else []
if thin:
    st.caption(
        f"⚠ {', '.join(thin)} rests on very few cells at some windows — "
        "hover a point to see how many. A series drawn from a handful of "
        "observations is not an elasticity curve; read it as scattered "
        "points that happen to be joined."
    )

n_series = len(classes)
colour = alt.Color("fare_class:N", title="Fare class",
                   scale=alt.Scale(domain=domain, range=rng),
                   legend=alt.Legend(orient="top-right") if n_series > 1 else None)

# A series resting on a handful of cells is drawn thin and dashed, so it
# cannot be mistaken at a glance for the twelve-cell curves beside it. The
# caption says it; the line weight has to say it too, because nobody reads
# the caption before they read the picture.
# Styled per CLASS, not per point: splitting one series into solid and
# dashed segments would break the line in the middle and read as missing
# data rather than as a thin sample.
curve["thin"] = curve.fare_class.isin(thin)
_enc = dict(
    x=alt.X("advance_window_days:O", title="Days booked before departure",
            axis=alt.Axis(labelAngle=0)),
    y=alt.Y("fare:Q", title="Median cheapest fare (₹)",
            scale=alt.Scale(zero=False, nice=True)),
    color=colour,
    tooltip=[alt.Tooltip("advance_window_days:O", title="Window (days)"),
             alt.Tooltip("fare_class:N", title="Class"),
             alt.Tooltip("fare:Q", title="Median cheapest", format=",.0f"),
             alt.Tooltip("cells:Q", title="Cells behind this point")],
)
_parts = []
for is_thin, block in curve.groupby("thin"):
    if block.empty:
        continue
    mark = (dict(strokeWidth=1, strokeDash=[4, 3], opacity=0.8,
                 point=alt.OverlayMarkDef(size=45, filled=True)) if is_thin
            else dict(strokeWidth=2,
                      point=alt.OverlayMarkDef(size=90, filled=True)))
    _parts.append(alt.Chart(block).mark_line(**mark).encode(**_enc))
elastic = _parts[0]
for extra in _parts[1:]:
    elastic = elastic + extra
# Direct labels at the right-hand end: identity is never colour alone.
ends = curve.sort_values("advance_window_days").groupby("fare_class").tail(1)
labels = alt.Chart(ends).mark_text(
    align="left", dx=8, dy=0, fontSize=12, color=INK,
).encode(x=alt.X("advance_window_days:O"), y=alt.Y("fare:Q"),
         text="fare_class:N")
st.altair_chart(chart_base((elastic + labels).properties(height=340)),
                use_container_width=True)

# ---------------------------------------------------------- sector heatmap
st.subheader("Sector heatmap")
st.caption("Cheapest fare in each route × window cell. Blanks are cells the "
           "collector attempted but found no fares in — recorded, not dropped.")

heat_df = (df.groupby(["route", "advance_window_days"], as_index=False)
             .total_fare_inr.min().rename(columns={"total_fare_inr": "fare"}))
heat = alt.Chart(heat_df).mark_rect(stroke=SURFACE, strokeWidth=2).encode(
    x=alt.X("advance_window_days:O", title="Days before departure",
            axis=alt.Axis(labelAngle=0)),
    y=alt.Y("route:N", title=None, sort=alt.SortField("fare", "descending")),
    color=alt.Color("fare:Q", title="Cheapest fare (₹)",
                    scale=alt.Scale(range=SEQ_BLUE),
                    legend=alt.Legend(orient="right", gradientLength=200)),
    tooltip=[alt.Tooltip("route:N", title="Route"),
             alt.Tooltip("advance_window_days:O", title="Window (days)"),
             alt.Tooltip("fare:Q", title="Cheapest", format=",.0f")],
).properties(height=max(360, 36 * heat_df.route.nunique()))  # room for every
#                                       route label; Vega drops them if cramped
st.altair_chart(chart_base(heat), use_container_width=True)

# ------------------------------------------------------------------ table
st.subheader("Observations")
st.caption("Every fare behind the charts above. Sortable; download for the "
           "backtest or the outlier work.")
show = df[["collection_date", "departure_date", "advance_window_days", "route",
           "carrier", "flight_number", "depart_time_local", "fare_class",
           "total_fare_inr", "base_fare_inr", "taxes_inr", "source_portal"]].copy()
show["collection_date"] = show.collection_date.dt.date
st.dataframe(show.sort_values(["route", "advance_window_days",
                               "total_fare_inr"]),
             use_container_width=True, hide_index=True, height=420)
st.download_button("Download filtered CSV", show.to_csv(index=False),
                   "apix_fares_filtered.csv", "text/csv")

# -------------------------------------------------------------------- API
with st.expander("API — machine-readable output for NSO / RBI"):
    st.caption("Regenerated with the index by `py -m fareindex.apix`, at a "
               "stable path any static host can serve.")
    api_path = "docs/api/index.json"
    if os.path.exists(api_path):
        with open(api_path, encoding="utf-8") as handle:
            st.json(json.load(handle))
    else:
        st.info("Not generated yet — run `py -m fareindex.apix`.")
