"""SQLite persistence for observed fares.

Three tables:
  fares        -- one row per observed offer, deduplicated so re-running a
                  collection on the same day is idempotent.
  observations -- one row per (cell, run), INCLUDING cells that returned
                  nothing. The PS requires the cleaning pipeline to
                  "account for cancellations/sold-out flights"; you can
                  only do that if an empty cell is recorded as an observed
                  absence rather than being silently missing.
  runs         -- one row per collection run, so you can prove at demo time
                  that the collector ran on each day.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterable, Optional

from .model import FareOffer

SCHEMA = """
CREATE TABLE IF NOT EXISTS fares (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    origin               TEXT NOT NULL,
    destination          TEXT NOT NULL,
    departure_date       TEXT NOT NULL,   -- ISO YYYY-MM-DD
    collection_date      TEXT NOT NULL,   -- ISO YYYY-MM-DD
    collection_ts        TEXT NOT NULL,
    advance_window_days  INTEGER NOT NULL,

    total_fare_inr       REAL NOT NULL,
    base_fare_inr        REAL,
    taxes_inr            REAL,
    udf_inr              REAL,
    convenience_fee_inr  REAL,

    carrier              TEXT,
    flight_number        TEXT,
    depart_time_local    TEXT,
    fare_class           TEXT,
    is_refundable        INTEGER,

    source_portal        TEXT NOT NULL,
    run_id               TEXT NOT NULL,
    raw_json             TEXT
);

-- What makes two offers the SAME offer. INSERT OR IGNORE then makes the
-- collector idempotent: a re-run repairs a partial day instead of
-- duplicating it.
--
-- fare_class is part of the key. Without it, two genuinely different fare
-- families on the same flight at the same price collapse into one row —
-- a real offer silently dropped rather than a duplicate caught. (On the
-- data collected so far this never fired: AV and EC are never priced
-- identically on the same flight, so no existing row was lost.)
--
-- Every nullable column is COALESCEd because in SQL NULL is not equal to
-- NULL: two rows that both have a null flight number would not collide,
-- and the constraint would silently do nothing.
CREATE UNIQUE INDEX IF NOT EXISTS ux_fares_offer ON fares (
    origin, destination, departure_date, collection_date,
    source_portal, COALESCE(carrier, ''), COALESCE(flight_number, ''),
    COALESCE(depart_time_local, ''), COALESCE(fare_class, ''),
    total_fare_inr
);

CREATE INDEX IF NOT EXISTS ix_fares_axis
    ON fares (origin, destination, advance_window_days, collection_date);

-- Every cell the collector attempted, whether or not fares came back.
CREATE TABLE IF NOT EXISTS observations (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               TEXT NOT NULL,
    origin               TEXT NOT NULL,
    destination          TEXT NOT NULL,
    departure_date       TEXT NOT NULL,
    collection_date      TEXT NOT NULL,
    advance_window_days  INTEGER NOT NULL,
    source_portal        TEXT NOT NULL,
    status               TEXT NOT NULL,   -- ok | empty | error
    n_offers             INTEGER NOT NULL DEFAULT 0,
    detail               TEXT
);

CREATE INDEX IF NOT EXISTS ix_obs_cell
    ON observations (origin, destination, advance_window_days,
                     collection_date);

CREATE TABLE IF NOT EXISTS runs (
    run_id           TEXT PRIMARY KEY,
    source_portal    TEXT NOT NULL,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    collection_date  TEXT NOT NULL,
    cells_attempted  INTEGER DEFAULT 0,
    cells_ok         INTEGER DEFAULT 0,
    cells_failed     INTEGER DEFAULT 0,
    offers_written   INTEGER DEFAULT 0,
    notes            TEXT
);
"""


def _migrate_offer_index(conn: sqlite3.Connection) -> None:
    """Bring an older database's uniqueness rule up to the current one.

    CREATE UNIQUE INDEX IF NOT EXISTS does NOT replace an index that
    already exists under that name, so a database created before
    fare_class joined the key would keep enforcing the old rule for ever,
    silently, with the schema in this file saying otherwise. That is worse
    than the original defect: the code and the data disagree and nothing
    says so.

    Recreating is safe in this direction. The new key has strictly more
    columns, so it is a weaker constraint — every row that satisfied the
    old index satisfies the new one, and the rebuild cannot fail on
    existing data.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' "
        "AND name='ux_fares_offer'").fetchone()
    if row is None or row[0] is None:
        return
    if "fare_class" in row[0]:
        return                                  # already current
    conn.execute("DROP INDEX ux_fares_offer")
    conn.executescript(SCHEMA)                  # recreates it, current
    conn.commit()
    print("[store] upgraded ux_fares_offer to include fare_class "
          "(older databases enforced a coarser rule)")


@contextmanager
def connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _migrate_offer_index(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def start_run(conn: sqlite3.Connection, source_portal: str,
              collection_date: date) -> str:
    run_id = uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO runs (run_id, source_portal, started_at, collection_date)"
        " VALUES (?, ?, ?, ?)",
        (run_id, source_portal, datetime.now().isoformat(timespec="seconds"),
         collection_date.isoformat()),
    )
    conn.commit()
    return run_id


def finish_run(conn: sqlite3.Connection, run_id: str, attempted: int, ok: int,
               failed: int, written: int, notes: Optional[str] = None) -> None:
    conn.execute(
        "UPDATE runs SET finished_at=?, cells_attempted=?, cells_ok=?,"
        " cells_failed=?, offers_written=?, notes=? WHERE run_id=?",
        (datetime.now().isoformat(timespec="seconds"), attempted, ok, failed,
         written, notes, run_id),
    )
    conn.commit()


def record_observation(conn: sqlite3.Connection, run_id: str, origin: str,
                       destination: str, departure_date: date,
                       collection_date: date, source_portal: str, status: str,
                       n_offers: int = 0, detail: Optional[str] = None) -> None:
    """Log one attempted cell. Call this for EVERY cell, including failures."""
    conn.execute(
        "INSERT INTO observations (run_id, origin, destination,"
        " departure_date, collection_date, advance_window_days, source_portal,"
        " status, n_offers, detail) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (run_id, origin, destination, departure_date.isoformat(),
         collection_date.isoformat(),
         (departure_date - collection_date).days, source_portal, status,
         n_offers, detail),
    )
    conn.commit()


def write_offers(conn: sqlite3.Connection, offers: Iterable[FareOffer],
                 run_id: str) -> int:
    """Insert offers, skipping duplicates. Returns rows actually written."""
    now = datetime.now().isoformat(timespec="seconds")
    written = 0
    for offer in offers:
        offer.validate()
        cur = conn.execute(
            "INSERT OR IGNORE INTO fares ("
            " origin, destination, departure_date, collection_date,"
            " collection_ts, advance_window_days, total_fare_inr,"
            " base_fare_inr, taxes_inr, udf_inr, convenience_fee_inr,"
            " carrier, flight_number, depart_time_local, fare_class,"
            " is_refundable, source_portal, run_id, raw_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                offer.origin,
                offer.destination,
                offer.departure_date.isoformat(),
                offer.collection_date.isoformat(),
                now,
                offer.advance_window_days,
                float(offer.total_fare_inr),
                offer.base_fare_inr,
                offer.taxes_inr,
                offer.udf_inr,
                offer.convenience_fee_inr,
                offer.carrier,
                offer.flight_number,
                offer.depart_time_local,
                offer.fare_class,
                None if offer.is_refundable is None else int(offer.is_refundable),
                offer.source_portal,
                run_id,
                json.dumps(offer.raw) if offer.raw is not None else None,
            ),
        )
        written += cur.rowcount
    conn.commit()
    return written


def coverage(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Rows per collection_date per source -- the demo's proof-of-life query."""
    return conn.execute(
        "SELECT collection_date, source_portal, COUNT(*) AS offers,"
        " COUNT(DISTINCT origin || destination || advance_window_days) AS cells"
        " FROM fares GROUP BY collection_date, source_portal"
        " ORDER BY collection_date, source_portal"
    ).fetchall()


def export_csv(conn: sqlite3.Connection, path: str) -> int:
    """Dump every fare to a flat CSV. Returns rows written.

    This exists so that nobody except the collector needs to understand
    SQLite. The dashboard and the backtest both read this file with
    pandas.read_csv() instead of writing SQL.
    """
    import csv
    import os

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    rows = conn.execute(
        "SELECT origin, destination, departure_date, collection_date,"
        " advance_window_days, total_fare_inr, base_fare_inr, taxes_inr,"
        " udf_inr, convenience_fee_inr, carrier, flight_number,"
        " depart_time_local, fare_class, source_portal"
        " FROM fares ORDER BY collection_date, origin, destination,"
        " advance_window_days"
    ).fetchall()

    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if rows:
            writer.writerow(rows[0].keys())
            writer.writerows(tuple(r) for r in rows)
        else:
            writer.writerow([
                "origin", "destination", "departure_date", "collection_date",
                "advance_window_days", "total_fare_inr", "base_fare_inr",
                "taxes_inr", "udf_inr", "convenience_fee_inr", "carrier",
                "flight_number", "depart_time_local", "fare_class",
                "source_portal",
            ])
    return len(rows)


def empty_cells(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Cells observed but with no fares -- sold out, cancelled, or blocked.

    This is the query that answers "how does your pipeline account for
    sold-out flights". The answer is: it records them.
    """
    return conn.execute(
        "SELECT collection_date, origin, destination, advance_window_days,"
        " source_portal, status, detail FROM observations"
        " WHERE status != 'ok' ORDER BY collection_date, origin, destination"
    ).fetchall()
