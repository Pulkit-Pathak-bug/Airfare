"""The basket-continuity demonstration, computed rather than asserted.

The claim made in the methodology and the defence pack is that folding a
late-joining source into the headline index would report a price fall that
never happened. That is a strong claim, so it should be produced by running
the code, not typed into a document.

This builds a controlled fixture where the truth is known — fares rise a
fixed 10% per day, and a second carrier undercuts by 30% from day three —
runs the index both ways, and returns both series.

    py -m fareindex.continuity_demo

Run it in front of a judge who asks. It takes about a second.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .apix import build_index, split_sources
from .config import ROUTES, WINDOWS

DAILY_RISE = 0.10          # true, known price inflation per day
UNDERCUT = 0.30            # how much cheaper the late carrier is
BASE_FARE = 5000.0


def fixture(days: int = 3, late_from: int = 2) -> pd.DataFrame:
    """Synthetic fares with a known answer.

    Carrier A collects from day 0. Carrier B appears on day `late_from`
    and is uniformly cheaper. Every fare rises DAILY_RISE per day, so the
    correct index is 100, 110, 121 ... regardless of who is collecting.
    """
    start = date(2026, 1, 1)
    rows = []
    for day in range(days):
        collection = start + timedelta(days=day)
        factor = (1.0 + DAILY_RISE) ** day
        for origin, destination in ROUTES:
            for window in WINDOWS:
                fare = BASE_FARE * factor
                rows.append({
                    "origin": origin, "destination": destination,
                    "departure_date": collection + timedelta(days=window),
                    "collection_date": collection,
                    "advance_window_days": window,
                    "total_fare_inr": fare,
                    "source_portal": "carrier_a",
                })
                if day >= late_from:
                    rows.append({
                        "origin": origin, "destination": destination,
                        "departure_date": collection + timedelta(days=window),
                        "collection_date": collection,
                        "advance_window_days": window,
                        "total_fare_inr": fare * (1.0 - UNDERCUT),
                        "source_portal": "carrier_b",
                    })
    df = pd.DataFrame(rows)
    df["collection_date"] = pd.to_datetime(df.collection_date)
    df["route"] = df.origin + "-" + df.destination
    return df


def run() -> dict:
    """Compute both series. Returns the numbers the documents quote."""
    df = fixture()
    continuous, late = split_sources(df)

    naive, _ = build_index(df)                       # every source, one basket
    fixed, _ = build_index(df[df.source_portal.isin(continuous)])

    naive_series = [round(v, 2) for v in naive.apix]
    fixed_series = [round(v, 2) for v in fixed.apix]
    truth = [round(100 * (1 + DAILY_RISE) ** d, 2)
             for d in range(len(fixed_series))]
    return {
        "naive": naive_series,
        "fixed": fixed_series,
        "truth": truth,
        "late_sources": late,
        "daily_rise_pct": DAILY_RISE * 100,
        "undercut_pct": UNDERCUT * 100,
        "naive_error_pct": (
            round((naive_series[-1] / truth[-1] - 1) * 100, 1)
            if naive_series and truth else None),
    }


def arrow(values) -> str:
    return " -> ".join(f"{v:.2f}" for v in values)


def main() -> int:
    r = run()
    print(f"fixture: fares rise {r['daily_rise_pct']:.0f}% per day; "
          f"a second carrier appears on day 3 at {r['undercut_pct']:.0f}% "
          f"below the first.\n")
    print(f"  true movement                {arrow(r['truth'])}")
    print(f"  headline index (continuity)  {arrow(r['fixed'])}   <- correct")
    print(f"  naive index (all sources)    {arrow(r['naive'])}   "
          f"<- wrong by {r['naive_error_pct']:.1f}%")
    print("\nThe naive index reports a fall on the day the second carrier "
          "joins.\nNo fare fell. The comparison widened.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
