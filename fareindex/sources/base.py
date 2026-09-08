"""The adapter interface every fare source implements.

The whole point of this file: the collector, the schema and the index layer
never learn where a fare came from. Swapping SerpAPI for a Playwright
scraper is a new subclass, not a rewrite. That is also the architecture
slide -- MoSPI asked for scraping, and this is where scraping plugs in.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import List

from ..model import FareOffer


class FareSourceError(Exception):
    """Raised for a cell that failed. Never kills the run."""


class FareSource(ABC):
    #: short, stable identifier written to fares.source_portal
    name: str = "unnamed"

    #: rough ceiling on requests per day for this source, for budgeting
    daily_request_budget: int = 10_000

    @abstractmethod
    def fetch(self, origin: str, destination: str,
              departure_date: date) -> List[FareOffer]:
        """Return every one-way offer for this itinerary.

        One-way, not round trip: a return ticket bundles two products and
        cannot sit on a single advance-purchase axis. Raise FareSourceError
        on failure; return [] when the source legitimately has no fares.
        """

    def close(self) -> None:
        """Release browsers, sessions, etc. Override if needed."""
