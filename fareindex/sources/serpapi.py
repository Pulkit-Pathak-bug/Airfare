"""SerpAPI (Google Flights) adapter -- NOT the collector. Do not ship this.

READ THIS BEFORE USING THIS FILE FOR ANYTHING.

SIH26056 Expected Solution (a) asks for "a robust, ethically-designed
multi-source web-scraping engine using Python (Scrapy/Selenium/Playwright)".
SerpAPI is a commercial third party selling Google's data behind a paid
key. That is buying data, not scraping it, and fares collected through it
CANNOT form part of the APIx series. If these rows reach the demo index,
deliverable (a) does not exist and the submission fails its primary
requirement no matter how good the index maths is.

Two legitimate uses, neither of which is daily collection:

  1. Development fixture -- real-shaped data so the index module, the
     cleaning pipeline and the dashboard can be built and tested while the
     actual scrapers are still being cracked.
  2. Cross-validation -- pull a handful of cells once, show that scraped
     fares agree with an independent source to within some tolerance, and
     say so openly on the slide. That is a data-quality check, which the
     PS cleaning requirements reward.

Rows from this source carry source_portal='serpapi'. Exclude them from any
index query with:   WHERE source_portal != 'serpapi'

The real collector is sources/airline_web.py. Hitting an airline's own JSON
availability endpoint IS scraping: the endpoint belongs to the site you are
collecting from, it is undocumented, and it serves the same data the page
renders. JSON versus HTML is not the distinction -- whose endpoint it is,
is.

Quota: the free tier is roughly 100 searches per MONTH against a 60-call
day, so this could not be the collector even if it were permitted.

Implementation notes (differences from the original flight_search.py):
  * type=2 (ONE WAY). The original used type=1 with a return_date, which
    prices a round trip -- two products bundled, impossible to place on a
    single advance-purchase axis.
  * Reads best_flights AND other_flights. The original took
    other_flights[0], which is not the cheapest offer.
  * API key from the SERPAPI_KEY environment variable, never a literal.
  * raise_for_status(), a timeout, and an explicit check of SerpAPI's own
    "error" field, which arrives with HTTP 200.
"""

from __future__ import annotations

import os
from datetime import date
from typing import List, Optional

import requests

from ..model import FareOffer
from .base import FareSource, FareSourceError

ENDPOINT = "https://serpapi.com/search"


class SerpApiSource(FareSource):
    name = "serpapi"
    daily_request_budget = 25   # ~100/month spread over four collection days

    def __init__(self, api_key: Optional[str] = None, timeout: int = 30):
        key = api_key or os.environ.get("SERPAPI_KEY")
        if not key:
            raise FareSourceError(
                "SERPAPI_KEY is not set. Export the rotated key first."
            )
        self._key = key
        self._timeout = timeout

    def fetch(self, origin: str, destination: str,
              departure_date: date) -> List[FareOffer]:
        params = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": departure_date.isoformat(),
            "type": "2",            # one way
            "adults": "1",
            "currency": "INR",
            "gl": "in",
            "hl": "en",
            "api_key": self._key,
        }

        try:
            response = requests.get(ENDPOINT, params=params,
                                    timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise FareSourceError(
                f"serpapi request failed for {origin}-{destination} "
                f"{departure_date}: {exc}"
            ) from exc
        except ValueError as exc:
            raise FareSourceError("serpapi returned non-JSON") from exc

        # SerpAPI reports its own failures inside a 200 response.
        if isinstance(payload, dict) and payload.get("error"):
            raise FareSourceError(f"serpapi error: {payload['error']}")

        collection_date = date.today()
        offers: List[FareOffer] = []

        for bucket in ("best_flights", "other_flights"):
            for itinerary in payload.get(bucket, []) or []:
                offer = self._parse(itinerary, origin, destination,
                                    departure_date, collection_date)
                if offer is not None:
                    offers.append(offer)

        return offers

    @staticmethod
    def _parse(itinerary: dict, origin: str, destination: str,
               departure_date: date, collection_date: date) -> Optional[FareOffer]:
        price = itinerary.get("price")
        if not isinstance(price, (int, float)) or price <= 0:
            return None

        legs = itinerary.get("flights") or []
        carrier = legs[0].get("airline") if legs else None

        depart_time = None
        if legs:
            raw_time = (legs[0].get("departure_airport") or {}).get("time")
            if isinstance(raw_time, str) and " " in raw_time:
                depart_time = raw_time.split(" ", 1)[1][:5]

        flight_number = legs[0].get("flight_number") if legs else None

        # Google Flights exposes only the all-in price. base/taxes/UDF/
        # convenience fee stay None -- an honest "not exposed by this
        # portal", which the cleaning layer can distinguish from zero.
        return FareOffer(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            collection_date=collection_date,
            total_fare_inr=float(price),
            source_portal=SerpApiSource.name,
            carrier=carrier,
            flight_number=flight_number,
            depart_time_local=depart_time,
            fare_class=(legs[0].get("travel_class") if legs else None),
            raw=itinerary,
        )
