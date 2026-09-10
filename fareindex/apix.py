"""APIx — index construction. PS deliverable (c).

METHOD

The index mirrors the Laspeyres form CPI itself uses, because a novel
formula is a liability when the intended consumer is a statistics
ministry. It does not invent anything.

  1. A CELL is one (route, advance-purchase window) pair. There are
     12 routes x 5 windows = 60 cells in the basket.

  2. The PRICE of a cell on a collection date is the cheapest available
     one-way fare observed in it. Cheapest, not mean: a traveller buys
     the lowest fare that suits them, not the average of the cabin.

  3. A PRICE RELATIVE is that cell's price on date t divided by its
     price in the base period (the first collection date). Relatives,
     not raw fares, are what get aggregated — otherwise expensive routes
     would dominate the index purely by being expensive.

  4. The INDEX is the weighted mean of the price relatives x 100, using
     fixed base-period weights. Fixed weights are what makes it a
     Laspeyres index: the basket does not shift under you, so a change
     in the index is a change in price and nothing else.

  5. A cell missing on date t carries its last observed relative
     forward, flagged. Dropping it instead would bias the index upward
     exactly when cheap seats sell out — the worst possible bias for a
     price index.

WEIGHTS

Route weights should come from DGCA passenger traffic, so that DEL-BOM
counts for more than a thin route. Until data/route_weights.csv exists
the index falls back to EQUAL weights and says so in its output. Windows
are weighted equally by design — we have no data on how bookings
distribute across advance-purchase windows, and inventing a distribution
would be worse than declaring a uniform one.

BASKET CONTINUITY — why the headline index uses only some sources

A cell's price is the cheapest fare seen in it, across every source. So
the day a new carrier starts being collected, cells it flies can get
cheaper for a reason that has nothing to do with prices: there is simply
one more airline in the comparison. An index that let that through would
report a fare drop caused by our own collection schedule. That is the
single most embarrassing failure mode a price index has, and it is not
hypothetical here — SpiceJet joined on day 3.

The rule, therefore: THE HEADLINE INDEX USES ONLY SOURCES PRESENT FROM
THE BASE PERIOD ONWARD. A source that starts later is not silently
folded in. It gets its own index, based on its own first day, and a
combined index is published separately with its base moved to the first
date on which every source was collecting. Three series, each internally
consistent, none of them mixing a composition change with a price
change. This is the same reason national statistical offices re-base
rather than splice.

FREQUENCIES

The PS asks for daily, weekly and monthly. Weekly and monthly are means
of the daily series over the period, and are marked partial when the
period is incomplete.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import pandas as pd

from .config import WINDOWS

EXPORT_CSV = "data/fares_export.csv"
ROUTE_WEIGHTS_CSV = "data/route_weights.csv"
BASE_VALUE = 100.0

# Rows from this source are development fixtures and must never enter the
# index. See fareindex/sources/serpapi.py.
EXCLUDED_SOURCES = ("serpapi",)


def load_fares(path: str = EXPORT_CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[~df.source_portal.isin(EXCLUDED_SOURCES)].copy()
    df["collection_date"] = pd.to_datetime(df.collection_date)
    df["route"] = df.origin + "-" + df.destination
    return df


def cell_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Cheapest fare per (route, window, collection date)."""
    return (df.groupby(["route", "advance_window_days", "collection_date"],
                       as_index=False)
              .total_fare_inr.min()
              .rename(columns={"total_fare_inr": "price"}))


def route_weights(routes, path: str = ROUTE_WEIGHTS_CSV):
    """DGCA-derived route weights if present, else equal.

    Returns (series, description). The description is printed in the
    output, shown on the dashboard and quoted in the methodology PDF, so
    it has to distinguish *absent* from *present but unusable* — a file
    sitting in data/ while the document says it is absent reads as a lie
    to anyone who looks in the folder.
    """
    equal = pd.Series(1.0 / len(routes), index=routes)
    if not os.path.exists(path):
        return equal, "equal (data/route_weights.csv not present)"
    try:
        w = pd.read_csv(path)
        w["route"] = w.origin + "-" + w.destination
        s = w.set_index("route")["share"].astype(float)
        s = s.reindex(routes).fillna(0.0)
    except Exception as exc:                                 # noqa: BLE001
        return equal, (f"equal — data/route_weights.csv could not be read "
                       f"({type(exc).__name__}); expected columns "
                       f"origin, destination, share")
    if s.sum() <= 0:
        return equal, ("equal — data/route_weights.csv has no weight for any "
                       "route in the collected data; check the origin and "
                       "destination codes match")
    missing = [r for r in routes if r not in set(w["route"])]
    note = f" ({len(missing)} route(s) unweighted)" if missing else ""
    return s / s.sum(), f"DGCA passenger traffic{note}"


def source_spans(df: pd.DataFrame) -> pd.DataFrame:
    """First day, last day and row count for each source portal.

    This is the table that decides basket continuity, so it is worth
    being able to print on its own.
    """
    g = (df.groupby("source_portal").collection_date
           .agg(first="min", last="max", rows="count")
           .sort_values("first"))
    return g


def split_sources(df: pd.DataFrame):
    """(continuous, late) source names.

    Continuous = collecting since the very first day of the series, so
    including it cannot change basket composition mid-stream. Late =
    started afterwards, and therefore must not enter the headline index.
    """
    spans = source_spans(df)
    if spans.empty:
        return [], []
    base = spans["first"].min()
    continuous = sorted(spans.index[spans["first"] == base])
    late = sorted(spans.index[spans["first"] > base])
    return continuous, late


def build_index(df: pd.DataFrame):
    """Return (daily_index_df, meta). Daily has columns date, apix, cells."""
    prices = cell_prices(df)
    if prices.empty:
        return pd.DataFrame(columns=["date", "apix", "cells",
                                     "carried_forward"]), {}

    dates = sorted(prices.collection_date.unique())
    base_date = dates[0]

    base = (prices[prices.collection_date == base_date]
            .set_index(["route", "advance_window_days"]).price)
    # An unusable base price is not a basket cell. Dropping it here rather
    # than skipping it later matters: cells_per_route is built from this
    # index, so counting a cell that can never contribute a relative would
    # divide the route's weight by one too many and quietly hand the
    # shortfall to other routes for the life of the series.
    base = base[base > 0]

    routes = sorted(prices.route.unique())
    weights, weight_source = route_weights(routes)

    # A route's weight is its share of the BASKET, so it has to be split
    # across however many window-cells that route actually contributed on
    # the base date — not applied whole to each of them.
    #
    # Why this matters: the base basket is whatever returned a price on day
    # one. If DEL-BOM contributed 5 cells and MAA-DEL only 4, giving both
    # cells the full route weight and then normalising makes DEL-BOM count
    # 5/4 times more than its DGCA share says it should, permanently, for
    # the life of the series. The index would silently disagree with the
    # weights table printed beside it.
    cells_per_route: dict = {}
    for route, _window in base.index:
        cells_per_route[route] = cells_per_route.get(route, 0) + 1

    rows, carried_total = [], 0
    last_relative: dict = {}

    for date in dates:
        today = (prices[prices.collection_date == date]
                 .set_index(["route", "advance_window_days"]).price)

        relatives, cell_weights, carried = [], [], 0
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
            relatives.append(relative)
            n_cells = cells_per_route.get(cell[0], 1) or 1
            cell_weights.append(float(weights.get(cell[0], 0.0)) / n_cells)

        if not relatives:
            continue
        series = pd.Series(relatives)
        w = pd.Series(cell_weights)
        w = w / w.sum() if w.sum() > 0 else pd.Series(1.0 / len(series),
                                                      index=series.index)
        carried_total += carried
        rows.append({"date": pd.Timestamp(date),
                     "apix": round(BASE_VALUE * float((series * w).sum()), 2),
                     "cells": len(series),
                     "carried_forward": carried})

    # Explicit columns, so an empty result always has the documented
    # schema whatever the reason it is empty — otherwise write_outputs
    # emits a CSV with no header row at all and a consumer expecting
    # date,apix,cells,carried_forward breaks on a file it cannot read.
    daily = pd.DataFrame(rows, columns=["date", "apix", "cells",
                                        "carried_forward"])
    meta = {
        "base_period": pd.Timestamp(base_date).date().isoformat(),
        "base_value": BASE_VALUE,
        "basket_cells": int(len(base)),
        # Cells absent on the base date can never join a fixed-weight
        # basket, so say how many are missing rather than letting the
        # basket quietly be smaller than the grid.
        # Iterated over every route in the data, not just those that made
        # it into the basket — a route with ZERO usable cells on the base
        # date is the worst case and would otherwise be invisible here,
        # because it never becomes a key in cells_per_route at all.
        "routes_short_of_full_windows": {
            route: int(cells_per_route.get(route, 0)) for route in routes
            if cells_per_route.get(route, 0) < len(WINDOWS)
        },
        "weight_source": weight_source,
        "collection_days": len(daily),
        "cells_carried_forward": carried_total,
        "formula": "Laspeyres, fixed base-period weights, cheapest fare per cell",
    }
    return daily, meta


def resample(daily: pd.DataFrame):
    """Weekly and monthly series. PS requires all three frequencies.

    A period is 'partial' when fewer days were collected than the period
    actually contains. The month length has to be read off the calendar,
    not assumed: a fixed threshold of 28 would pass a January missing
    three days as a complete month, and the methodology document promises
    that a partial month is never presented as a month.
    """
    if daily.empty:
        empty = pd.DataFrame(columns=["date", "apix", "periods", "partial"])
        return empty, empty.copy()
    s = daily.set_index("date").apix

    def agg(rule, expected):
        g = s.resample(rule)
        out = g.mean().round(2).reset_index()
        out["periods"] = g.count().values
        out["expected_days"] = [expected(d) for d in out.date]
        out["partial"] = out.periods < out.expected_days
        return out

    import calendar
    return (agg("W", lambda d: 7),
            agg("MS", lambda d: calendar.monthrange(d.year, d.month)[1]))


def write_outputs(daily, weekly, monthly, meta, outdir="data",
                  api_path="docs/api/index.json", extra_series=None):
    """Write the headline series, and any secondary series alongside it.

    extra_series maps a label to (daily_df, meta_dict). These go into
    apix_by_series.csv and into the API document under "series", but
    apix_daily.csv stays the headline alone — the dashboard and every
    slide read that file, and the headline must never quietly become
    something else.
    """
    os.makedirs(outdir, exist_ok=True)
    daily.to_csv(f"{outdir}/apix_daily.csv", index=False)
    weekly.to_csv(f"{outdir}/apix_weekly.csv", index=False)
    monthly.to_csv(f"{outdir}/apix_monthly.csv", index=False)

    if extra_series:
        frames = []
        for label, (sdaily, smeta) in extra_series.items():
            if sdaily.empty:
                continue
            block = sdaily.copy()
            block.insert(0, "series", label)
            block["base_period"] = smeta.get("base_period")
            frames.append(block)
        if frames:
            pd.concat(frames, ignore_index=True).to_csv(
                f"{outdir}/apix_by_series.csv", index=False)

    # PS deliverable: "an API that the NSO and RBI can consume". For a
    # prototype that is a machine-readable document at a stable path,
    # regenerated with the index and servable by any static host.
    os.makedirs(os.path.dirname(api_path), exist_ok=True)
    with open(api_path, "w", encoding="utf-8") as handle:
        json.dump({
            "index": "APIx — Real-time Airfare Price Index (prototype)",
            "methodology": meta,
            "daily": [{"date": r.date.date().isoformat(), "value": r.apix,
                       "cells": int(r.cells)} for r in daily.itertuples()],
            "weekly": [{"week_ending": r.date.date().isoformat(),
                        "value": None if pd.isna(r.apix) else r.apix,
                        "partial": bool(r.partial)} for r in weekly.itertuples()],
            "monthly": [{"month": r.date.date().isoformat(),
                         "value": None if pd.isna(r.apix) else r.apix,
                         "partial": bool(r.partial)} for r in monthly.itertuples()],
            "series": {
                label: {
                    "methodology": smeta,
                    "daily": [{"date": r.date.date().isoformat(),
                               "value": r.apix, "cells": int(r.cells)}
                              for r in sdaily.itertuples()],
                }
                for label, (sdaily, smeta) in (extra_series or {}).items()
                if not sdaily.empty
            },
        }, handle, indent=2)
    return api_path


def _show(label: str, daily: pd.DataFrame, meta: dict) -> None:
    if daily.empty:
        print(f"\n{label}: no data")
        return
    print(f"\n{label}  (base {meta['base_period']} = {meta['base_value']}, "
          f"{meta['basket_cells']} cells)")
    print(f"{'date':<12}{'APIx':>9}{'cells':>8}{'carried':>9}")
    for r in daily.itertuples():
        print(f"{r.date.date()!s:<12}{r.apix:>9.2f}{r.cells:>8}"
              f"{r.carried_forward:>9}")


def main() -> int:
    df = load_fares()
    if df.empty:
        print("no fares to index — run collect.py --export first")
        return 1

    spans = source_spans(df)
    continuous, late = split_sources(df)

    print("source coverage")
    for name, row in spans.iterrows():
        tag = "headline" if name in continuous else "started late"
        print(f"  {name:<12} {row['first'].date()} -> {row['last'].date()}  "
              f"{int(row['rows']):>5} rows   [{tag}]")

    # ---- headline: only sources present from day one -------------------
    headline_df = df[df.source_portal.isin(continuous)]
    daily, meta = build_index(headline_df)
    meta["series"] = "headline"
    meta["sources"] = continuous
    meta["sources_excluded"] = {
        name: {"first_collected": spans.loc[name, "first"].date().isoformat(),
               "reason": "started after the base period; including it "
                         "would change basket composition, not price"}
        for name in late
    }

    extra: dict = {}

    # ---- combined: every source, re-based to the first day they all ran -
    if late:
        all_start = spans["first"].max()
        combined_df = df[df.collection_date >= all_start]
        cdaily, cmeta = build_index(combined_df)
        cmeta["series"] = "all-sources"
        cmeta["sources"] = sorted(df.source_portal.unique())
        cmeta["note"] = (
            f"Re-based to {all_start.date()}, the first date on which "
            f"every source was collecting. Not comparable with the "
            f"headline series before that date."
        )
        extra["all-sources"] = (cdaily, cmeta)

    # ---- one index per source, each on its own base --------------------
    for name in sorted(df.source_portal.unique()):
        sdaily, smeta = build_index(df[df.source_portal == name])
        smeta["series"] = name
        smeta["sources"] = [name]
        extra[name] = (sdaily, smeta)

    weekly, monthly = resample(daily)
    api = write_outputs(daily, weekly, monthly, meta, extra_series=extra)

    print(f"\nweights: {meta['weight_source']}")
    _show("HEADLINE  " + ", ".join(continuous), daily, meta)
    for label, (sdaily, smeta) in extra.items():
        _show(label, sdaily, smeta)

    if late:
        print(f"\nNote: {', '.join(late)} started after the base period and "
              f"is therefore kept out of the headline index. Its own series "
              f"is above, and the all-sources series is re-based to the day "
              f"every source was running.")

    print("\nwrote data/apix_daily.csv, apix_weekly.csv, apix_monthly.csv")
    if extra:
        print("wrote data/apix_by_series.csv")
    print(f"wrote {api}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
