#!/usr/bin/env python3
"""Run one collection pass over the basket and write fares to SQLite.

    python collect.py --source serpapi --thin
    python collect.py --source airline_web
    python collect.py --coverage          # what has been collected so far

Run this ONCE PER DAY, every day, until the deadline. Each run is one
column of the time series; a day missed is a day that cannot be recovered,
because collection_date cannot be backfilled.

A failing cell is logged and skipped -- the run always completes and always
writes what it got.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from fareindex import config, store
from fareindex.sources.base import FareSource, FareSourceError

log = logging.getLogger("collect")


def build_source(name: str) -> FareSource:
    if name == "serpapi":
        from fareindex.sources.serpapi import SerpApiSource
        return SerpApiSource()
    if name == "airline_web":
        from fareindex.sources.airline_web import AirlineWebSource
        return AirlineWebSource()
    raise SystemExit(f"unknown source: {name}")


def run(source_name: str, thin: bool, db_path: str, limit: int | None) -> int:
    try:
        source = build_source(source_name)
    except FareSourceError as exc:
        log.error("cannot start: %s", exc)
        return 1
    collection_date = date.today()

    cells = list(config.cells(thin=thin))
    if limit:
        cells = cells[:limit]

    budget = source.daily_request_budget
    if len(cells) > budget:
        log.warning(
            "basket needs %d calls but %s budgets %d/day -- truncating. "
            "Use --thin or a source with more headroom.",
            len(cells), source.name, budget,
        )
        cells = cells[:budget]

    attempted = ok = failed = written = 0

    with store.connect(db_path) as conn:
        run_id = store.start_run(conn, source.name, collection_date)
        log.info("run %s | source=%s | %d cells | %s",
                 run_id, source.name, len(cells), collection_date)

        for origin, destination, window in cells:
            departure_date = collection_date + timedelta(days=window)
            attempted += 1

            def observe(status, n=0, detail=None):
                store.record_observation(
                    conn, run_id, origin, destination, departure_date,
                    collection_date, source.name, status, n, detail)

            try:
                offers = source.fetch(origin, destination, departure_date)
            except FareSourceError as exc:
                failed += 1
                observe("error", detail=str(exc)[:500])
                log.error("FAIL %s-%s T+%-3d %s", origin, destination,
                          window, exc)
                continue
            except Exception as exc:                    # noqa: BLE001
                failed += 1
                observe("error", detail=repr(exc)[:500])
                log.exception("FAIL %s-%s T+%-3d unexpected: %s",
                              origin, destination, window, exc)
                continue

            ok += 1
            n = store.write_offers(conn, offers, run_id)
            written += n
            # An empty cell is data: sold out, cancelled, or no service.
            observe("ok" if offers else "empty", len(offers))
            log.info("%-5s %s-%s T+%-3d  %2d offers, %2d new",
                     "ok" if offers else "EMPTY", origin, destination,
                     window, len(offers), n)

        store.finish_run(conn, run_id, attempted, ok, failed, written)
        source.close()

    log.info("done | cells %d/%d ok | %d offers written", ok, attempted, written)
    if ok == 0:
        log.error("NOTHING COLLECTED -- fix the source before tomorrow.")
        return 1
    return 0


def show_coverage(db_path: str) -> int:
    with store.connect(db_path) as conn:
        rows = store.coverage(conn)
        if not rows:
            print("no fares collected yet")
            return 1
        print(f"{'collection_date':<16} {'source':<14} {'offers':>8} {'cells':>7}")
        for row in rows:
            print(f"{row['collection_date']:<16} {row['source_portal']:<14} "
                  f"{row['offers']:>8} {row['cells']:>7}")
        distinct_days = len({row["collection_date"] for row in rows})
        print(f"\n{distinct_days} collection day(s) = "
              f"{distinct_days} point(s) in the index series")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="serpapi")
    parser.add_argument("--thin", action="store_true",
                        help="use the 4-route basket (24 calls/day)")
    parser.add_argument("--db", default=config.DB_PATH)
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after N cells (use --limit 3 to smoke test)")
    parser.add_argument("--coverage", action="store_true",
                        help="print what has been collected and exit")
    parser.add_argument("--export", action="store_true",
                        help="write data/fares_export.csv and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.coverage:
        return show_coverage(args.db)
    if args.export:
        with store.connect(args.db) as conn:
            n = store.export_csv(conn, "data/fares_export.csv")
        print(f"wrote data/fares_export.csv ({n} rows)")
        return 0
    return run(args.source, args.thin, args.db, args.limit)


if __name__ == "__main__":
    sys.exit(main())
