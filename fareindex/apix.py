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
    """DGCA-derived route weights if present, else equal. Returns (series, source)."""
    if os.path.exists(path):
        try:
            w = pd.read_csv(path)
            w["route"] = w.origin + "-" + w.destination
            s = w.set_index("route")["share"].astype(float)
            s = s.reindex(routes).fillna(0.0)
            if s.sum() > 0:
                return s / s.sum(), "DGCA passenger traffic"
        except Exception:                                    # noqa: BLE001
            pass
    n = len(routes)
    return pd.Series(1.0 / n, index=routes), "equal (route_weights.csv absent)"


def build_index(df: pd.DataFrame):
    """Return (daily_index_df, meta). Daily has columns date, apix, cells."""
    prices = cell_prices(df)
    if prices.empty:
        return pd.DataFrame(columns=["date", "apix", "cells"]), {}

    dates = sorted(prices.collection_date.unique())
    base_date = dates[0]

    base = (prices[prices.collection_date == base_date]
            .set_index(["route", "advance_window_days"]).price)

    routes = sorted(prices.route.unique())
    weights, weight_source = route_weights(routes)

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
            cell_weights.append(float(weights.get(cell[0], 0.0)))

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

    daily = pd.DataFrame(rows)
    meta = {
        "base_period": pd.Timestamp(base_date).date().isoformat(),
        "base_value": BASE_VALUE,
        "basket_cells": int(len(base)),
        "weight_source": weight_source,
        "collection_days": len(daily),
        "cells_carried_forward": carried_total,
        "formula": "Laspeyres, fixed base-period weights, cheapest fare per cell",
    }
    return daily, meta


def resample(daily: pd.DataFrame):
    """Weekly and monthly series. PS requires all three frequencies."""
    if daily.empty:
        empty = pd.DataFrame(columns=["date", "apix", "periods", "partial"])
        return empty, empty.copy()
    s = daily.set_index("date").apix

    def agg(rule, expected):
        g = s.resample(rule)
        out = g.mean().round(2).reset_index()
        out["periods"] = g.count().values
        out["partial"] = out.periods < expected
        return out

    return agg("W", 7), agg("MS", 28)


def write_outputs(daily, weekly, monthly, meta, outdir="data",
                  api_path="docs/api/index.json"):
    os.makedirs(outdir, exist_ok=True)
    daily.to_csv(f"{outdir}/apix_daily.csv", index=False)
    weekly.to_csv(f"{outdir}/apix_weekly.csv", index=False)
    monthly.to_csv(f"{outdir}/apix_monthly.csv", index=False)

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
        }, handle, indent=2)
    return api_path


def main() -> int:
    df = load_fares()
    daily, meta = build_index(df)
    weekly, monthly = resample(daily)
    api = write_outputs(daily, weekly, monthly, meta)
    print(f"basket: {meta['basket_cells']} cells | base {meta['base_period']} "
          f"= {meta['base_value']}")
    print(f"weights: {meta['weight_source']}")
    print(f"\n{'date':<12}{'APIx':>9}{'cells':>8}{'carried':>9}")
    for r in daily.itertuples():
        print(f"{r.date.date()!s:<12}{r.apix:>9.2f}{r.cells:>8}"
              f"{r.carried_forward:>9}")
    print(f"\nwrote data/apix_daily.csv, apix_weekly.csv, apix_monthly.csv")
    print(f"wrote {api}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
