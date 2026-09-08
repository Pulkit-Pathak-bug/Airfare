"""Skeleton for a direct-airline web source. THIS IS THE ONE THAT MATTERS.

SerpAPI cannot carry the collection (about 100 searches a month against a
60-call day). Whatever you fill in here is what actually produces the
dataset, and it is also the "automated web scraping" MoSPI asked for.

HOW TO FILL THIS IN, in the order that fails fastest:

 1. Open the airline's booking page in Chrome, DevTools -> Network, filter
    XHR, and run one search. Almost every airline booking flow is a React
    front end talking to a JSON availability endpoint. Find the request
    that carries fares in its response.
 2. Right-click it -> Copy as cURL. Replay it in the terminal. If it works
    unauthenticated, you are done: port the cURL into requests below and
    you have a source that does hundreds of calls a day with no browser.
 3. If it needs a token, check whether the token comes from a cheap
    unauthenticated call earlier in the flow (very common). Fetch it once
    per run and reuse it.
 4. Only if 1-3 all fail, drive the page with Playwright and intercept the
    same JSON response. Slower and more fragile, but still a scraper.

Timebox each carrier to 45 minutes. Order: IndiGo (largest domestic
carrier, so a defensible basket on its own), then Akasa, then Air India
Express. Do not start on an OTA until all three are exhausted.

BEFORE YOU RUN IT AT VOLUME: read the site's robots.txt, keep
REQUEST_DELAY_SECONDS at 2s or higher, and identify the client honestly in
the User-Agent. You will be asked about this by a judge, and "public list
prices, rate limited, robots respected" is the answer you want to already
be true.
"""

from __future__ import annotations

import time
from datetime import date
from typing import List

import requests

from ..config import REQUEST_DELAY_SECONDS
from ..model import FareOffer
from .base import FareSource, FareSourceError

USER_AGENT = (
    "MIT-Bengaluru-SIH26056-research/0.1 "
    "(academic airfare price index; contact: pulkitpathak1000@gmail.com)"
)


class AirlineWebSource(FareSource):
    """Fill in ENDPOINT, _build_request and _parse. Nothing else changes."""

    name = "airline_web"        # rename to "indigo" / "akasa" once chosen
    daily_request_budget = 400

    ENDPOINT = ""               # TODO: the JSON availability URL from step 1

    def __init__(self, timeout: int = 30):
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-IN,en;q=0.9",
        })

    def fetch(self, origin: str, destination: str,
              departure_date: date) -> List[FareOffer]:
        if not self.ENDPOINT:
            raise FareSourceError(
                "AirlineWebSource.ENDPOINT is not configured yet -- "
                "see the module docstring for how to find it."
            )

        method, url, kwargs = self._build_request(origin, destination,
                                                  departure_date)
        try:
            response = self._session.request(method, url,
                                             timeout=self._timeout, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise FareSourceError(
                f"{self.name} request failed for {origin}-{destination} "
                f"{departure_date}: {exc}"
            ) from exc
        except ValueError as exc:
            raise FareSourceError(
                f"{self.name} returned non-JSON (bot wall? check the body)"
            ) from exc
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

        return self._parse(payload, origin, destination, departure_date)

    # ------------------------------------------------------------------
    # Fill these two in. Everything above and below is already correct.
    # ------------------------------------------------------------------

    def _build_request(self, origin: str, destination: str,
                       departure_date: date):
        """Return (method, url, kwargs) for one one-way availability call."""
        raise NotImplementedError(
            "Port the 'Copy as cURL' request here. Return e.g.\n"
            "  return 'GET', self.ENDPOINT, {'params': {...}}\n"
            "or 'POST', self.ENDPOINT, {'json': {...}}"
        )

    def _parse(self, payload, origin: str, destination: str,
               departure_date: date) -> List[FareOffer]:
        """Walk the JSON and emit one FareOffer per bookable one-way fare."""
        raise NotImplementedError(
            "Emit FareOffer(origin=..., destination=..., "
            "departure_date=departure_date, collection_date=date.today(), "
            "fare_inr=..., source_portal=self.name, carrier=..., "
            "depart_time_local='HH:MM', raw=<the offer dict>)"
        )

    def close(self) -> None:
        self._session.close()
