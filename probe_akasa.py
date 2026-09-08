#!/usr/bin/env python3
"""Make one Akasa call, save the raw JSON, and map where the fares live.

Run:  py probe_akasa.py

Writes data/akasa_sample.json and prints every path in the response whose
key looks like money. That tells us exactly what the parser should read,
instead of guessing at field names.

This is throwaway diagnostic tooling — it is not part of the collector.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

from fareindex.sources.akasa import ENDPOINT, AkasaSource   # noqa: E402

MONEY_HINTS = ("fare", "amount", "price", "total", "tax", "charge")


def walk(node, path="", depth=0, hits=None, seen_paths=None):
    """Collect paths whose key names look monetary, plus a shape sketch."""
    if hits is None:
        hits, seen_paths = [], set()

    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if (any(h in key.lower() for h in MONEY_HINTS)
                    and isinstance(value, (int, float))
                    and value not in (0, 1)):
                generic = here.replace("[0]", "[]")
                if generic not in seen_paths:
                    seen_paths.add(generic)
                    hits.append((generic, value))
            walk(value, here, depth + 1, hits, seen_paths)
    elif isinstance(node, list) and node:
        walk(node[0], f"{path}[0]", depth + 1, hits, seen_paths)

    return hits


def sketch(node, path="", depth=0, max_depth=7, lines=None):
    if lines is None:
        lines = []
    if depth > max_depth:
        return lines
    pad = "  " * depth
    if isinstance(node, dict):
        for key, value in list(node.items())[:14]:
            kind = type(value).__name__
            if isinstance(value, (dict, list)):
                size = len(value)
                lines.append(f"{pad}{key}: {kind}({size})")
                sketch(value, f"{path}.{key}", depth + 1, max_depth, lines)
            else:
                shown = repr(value)[:48]
                lines.append(f"{pad}{key} = {shown}")
    elif isinstance(node, list) and node:
        lines.append(f"{pad}[0 of {len(node)}]")
        sketch(node[0], f"{path}[0]", depth + 1, max_depth, lines)
    return lines


def main() -> int:
    source = AkasaSource()
    departure = date.today() + timedelta(days=7)
    payload = source._payload("DEL", "BOM", departure)

    print(f"POST {ENDPOINT}")
    print(f"     DEL-BOM departing {departure}")
    response = source._session.post(ENDPOINT, data=json.dumps(payload),
                                    timeout=30)
    print(f"     HTTP {response.status_code}, {len(response.content)} bytes\n")
    response.raise_for_status()
    data = response.json()

    os.makedirs("data", exist_ok=True)
    with open("data/akasa_sample.json", "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    print("saved -> data/akasa_sample.json\n")

    print("=== money-looking fields ===")
    hits = walk(data)
    if not hits:
        print("  none found — the route may genuinely have no flights,")
        print("  or fares are nested behind a key we are not walking into.")
    for path, value in hits[:40]:
        print(f"  {path} = {value}")

    print("\n=== structure sketch ===")
    for line in sketch(data)[:80]:
        print("  " + line)

    source.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
