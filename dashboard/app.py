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

from fareindex.apix import (EXPORT_CSV, build_index,  # noqa: E402
                            cell_prices, load_fares, resample)

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
def load(path: str):
    df = load_fares(path)
    df["fare_class"] = df.fare_class.fillna("—")
    daily, meta = build_index(df)
    weekly, monthly = resample(daily)
    return df, daily, weekly, monthly, meta


if not os.path.exists(EXPORT_CSV):
    st.error(
        f"`{EXPORT_CSV}` not found. Run the collector first:\n\n"
        "```\npy collect.py --source akasa\npy collect.py --export\n```\n\n"
        "Run streamlit from the repo root, not from inside dashboard/."
    )
    st.stop()

df_all, daily, weekly, monthly, meta = load(EXPORT_CSV)

st.title("APIx — Real-time Airfare Price Index")
st.caption(
    "Prototype for SIH 2026 problem statement 26056 (MoSPI). Fares collected "
    "daily by automated scraping on a fixed route × advance-purchase-window "
    "grid. Laspeyres index, fixed base-period weights, cheapest fare per cell."
)

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

# ------------------------------------------------------------ stat tiles
latest = daily.iloc[-1] if not daily.empty else None
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("APIx (latest)", f"{latest.apix:,.2f}" if latest is not None else "—",
          help=f"Base {meta.get('base_period', '—')} = 100")
c2.metric("Collection days", meta.get("collection_days", 0))
c3.metric("Fare observations", f"{len(df):,}")
c4.metric("Cells filled",
          f"{df.groupby(['route', 'advance_window_days']).ngroups}/60")
c5.metric("Cheapest fare", f"₹{df.total_fare_inr.min():,.0f}")

st.caption(f"Weights: {meta.get('weight_source', '—')}. "
           f"Basket: {meta.get('basket_cells', 0)} cells.")

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
    line = alt.Chart(daily).mark_line(
        strokeWidth=2, point=alt.OverlayMarkDef(size=90, filled=True),
        color=SERIES[0],
    ).encode(
        x=alt.X("date:T", title="Collection date"),
        y=alt.Y("apix:Q", title="APIx (base = 100)",
                scale=alt.Scale(zero=False, nice=True)),
        tooltip=[alt.Tooltip("date:T", title="Date"),
                 alt.Tooltip("apix:Q", title="APIx", format=".2f"),
                 alt.Tooltip("cells:Q", title="Cells"),
                 alt.Tooltip("carried_forward:Q", title="Carried forward")],
    )
    baseline = alt.Chart(pd.DataFrame({"y": [100]})).mark_rule(
        color=INK_MUTED, strokeDash=[4, 4], opacity=0.5).encode(y="y:Q")
    st.altair_chart(chart_base((baseline + line).properties(height=280)),
                    use_container_width=True)
    tab_d, tab_w, tab_m = st.tabs(["Daily", "Weekly", "Monthly"])
    tab_d.dataframe(daily, use_container_width=True, hide_index=True)
    tab_w.dataframe(weekly, use_container_width=True, hide_index=True)
    tab_m.dataframe(monthly, use_container_width=True, hide_index=True)

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
curve = (per_cell.groupby(["advance_window_days", "fare_class"], as_index=False)
                 .total_fare_inr.median()
                 .rename(columns={"total_fare_inr": "fare"}))

n_series = curve.fare_class.nunique()
colour = alt.Color("fare_class:N", title="Fare class",
                   scale=alt.Scale(range=SERIES[:max(n_series, 1)]),
                   legend=alt.Legend(orient="top-right") if n_series > 1 else None)

elastic = alt.Chart(curve).mark_line(
    strokeWidth=2, point=alt.OverlayMarkDef(size=90, filled=True),
).encode(
    x=alt.X("advance_window_days:O", title="Days booked before departure",
            axis=alt.Axis(labelAngle=0)),
    y=alt.Y("fare:Q", title="Median cheapest fare (₹)",
            scale=alt.Scale(zero=False, nice=True)),
    color=colour,
    tooltip=[alt.Tooltip("advance_window_days:O", title="Window (days)"),
             alt.Tooltip("fare_class:N", title="Class"),
             alt.Tooltip("fare:Q", title="Median cheapest", format=",.0f")],
)
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
