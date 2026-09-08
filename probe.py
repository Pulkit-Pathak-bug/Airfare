#!/usr/bin/env python3
"""Make one call against any source, save the raw JSON, map where fares live.

    py probe.py --source airindia
    py probe.py --source akasa --route DEL BOM --days 7

Writes data/<source>_sample.json and prints every path whose key looks
monetary, plus a structure sketch. Use it before writing a _parse() so you
are reading real field names instead of guessing at them.

Diagnostic tooling; not part of the collector.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

MONEY_HINTS = ("fare", "amount", "price", "total", "tax", "charge", "cost")


def walk(node, path="", hits=None, seen=None):
    if hits is None:
        hits, seen = [], set()
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if (any(h in key.lower() for h in MONEY_HINTS)
                    and isinstance(value, (int, float))
                    and value not in (0, 1)):
                generic = here.replace("[0]", "[]")
                if generic not in seen:
                    seen.add(generic)
                    hits.append((generic, value))
            walk(value, here, hits, seen)
    elif isinstance(node, list) and node:
        walk(node[0], f"{path}[0]", hits, seen)
    return hits


def sketch(node, depth=0, max_depth=7, lines=None):
    if lines is None:
        lines = []
    if depth > max_depth:
        return lines
    pad = "  " * depth
    if isinstance(node, dict):
        for key, value in list(node.items())[:14]:
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}{key}: {type(value).__name__}({len(value)})")
                sketch(value, depth + 1, max_depth, lines)
            else:
                lines.append(f"{pad}{key} = {repr(value)[:52]}")
    elif isinstance(node, list) and node:
        lines.append(f"{pad}[0 of {len(node)}]")
        sketch(node[0], depth + 1, max_depth, lines)
    return lines


def build(name: str):
    if name == "akasa":
        from fareindex.sources.akasa import AkasaSource, ENDPOINT
        return AkasaSource(), ENDPOINT
    if name == "airindia":
        from fareindex.sources.airindia import AirIndiaSource, ENDPOINT
        return AirIndiaSource(), ENDPOINT
    if name == "indigo":
        from fareindex.sources.indigo import IndigoSource, ENDPOINT
        return IndigoSource(), ENDPOINT
    raise SystemExit(f"unknown source: {name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--route", nargs=2, metavar=("ORIGIN", "DEST"),
                    default=["DEL", "BOM"])
    ap.add_argument("--days", type=int, default=7,
                    help="departure this many days from today")
    args = ap.parse_args()

    source, endpoint = build(args.source)
    origin, destination = args.route
    departure = date.today() + timedelta(days=args.days)

    print(f"POST {endpoint}")
    print(f"     {origin}-{destination} departing {departure}")
    response = source._session.post(
        endpoint,
        data=json.dumps(source._payload(origin, destination, departure)),
        timeout=30,
    )
    print(f"     HTTP {response.status_code}, {len(response.content)} bytes\n")
    if response.status_code >= 400:
        print(response.text[:600])
        return 1
    data = response.json()

    os.makedirs("data", exist_ok=True)
    out = f"data/{args.source}_sample.json"
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    print(f"saved -> {out}\n")

    print("=== money-looking fields ===")
    hits = walk(data)
    if not hits:
        print("  none found — no flights on this route/date, or the fares")
        print("  are nested somewhere the walker did not reach.")
    for path, value in hits[:40]:
        print(f"  {path} = {value}")

    print("\n=== structure sketch ===")
    for line in sketch(data)[:80]:
        print("  " + line)

    source.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
