"""SpiceJet fare source — POST /api/v2/search/lowfare.

Third platform note: SpiceJet runs dotREZ (Navitaire), the same engine as
IndiGo, and its bearer token is issued by it — the JWT decodes to
{"sub": "dotREZ API", "iss": "dotREZ API"}. Unlike IndiGo, though, the
captured request carries NO cookies at all, so there is no Akamai wall
here and plain HTTP works, exactly as with Akasa.

CAUTION ABOUT THIS ENDPOINT

The payload takes `centerDate`, not a departure date, which means this is
a low-fare *calendar*: it returns the cheapest fare for a span of dates
around the one asked for, rather than the full set of flights on one day.

Two consequences, both settled once the response shape is known:

  * The parser must pick out the exact departure date we asked for.
    Storing a neighbouring date's fare against our advance-purchase
    window would silently corrupt the index.
  * A calendar response may not carry flight numbers, departure times or
    the base/tax split. That is acceptable for the index, which uses the
    cheapest fare per cell anyway, but it means SpiceJet rows will have
    thinner metadata than Akasa rows. If the full availability endpoint
    turns out to be reachable, prefer it.

CREDENTIALS

    SPICEJET_TOKEN, or a .spicejet_token file, or minted automatically by
    fareindex.token_broker — the collector handles this itself.
"""

from __future__ import annotations

import json
import time
from datetime import date
from typing import List

import requests

from ..config import REQUEST_DELAY_SECONDS
from ..model import FareOffer
from .base import FareSource, FareSourceError
from .indigo import IndigoSource

ENDPOINT = "https://www.spicejet.com/api/v2/search/lowfare"


class SpiceJetSource(FareSource):
    name = "spicejet"
    daily_request_budget = 400
    default_carrier = "SG"

    @staticmethod
    def _obtain_token(force: bool = False) -> str:
        if not force:
            token = IndigoSource._credential("SPICEJET_TOKEN",
                                             ".spicejet_token")
            if token:
                return token
        from ..token_broker import TokenUnavailable, get
        try:
            return get("spicejet", force=force)
        except TokenUnavailable as exc:
            raise FareSourceError(
                f"Could not obtain a SpiceJet token automatically: {exc}\n"
                f"Fall back to pasting the 'Authorization' header from "
                f"DevTools into .spicejet_token"
            ) from exc

    def __init__(self, timeout: int = 30):
        token = self._obtain_token()
        self._token_refreshed = False
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": token,
            "content-type": "application/json",
            "origin": "https://www.spicejet.com",
            "os": "web",                      # SpiceJet requires this header
            # The client-hint headers are sent verbatim from the captured
            # request. The API is served from the same host as the website,
            # so the site's WAF sees these calls and a request that looks
            # unlike a browser gets a 9-byte "Forbidden".
            "sec-ch-ua": ('"Google Chrome";v="153", "Not_A Brand";v="8", '
                          '"Chromium";v="153"'),
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
        })

    @staticmethod
    def _referer(origin: str, destination: str,
                 departure_date: date) -> str:
        """The search page a real browser would be on for this query.

        A generic site referer gets refused. The captured request carried
        the full search URL, and it has to match the route and date being
        asked about — the WAF appears to check it.
        """
        return (f"https://www.spicejet.com/search?from={origin}"
                f"&to={destination}&tripType=1"
                f"&departure={departure_date.isoformat()}"
                f"&adult=1&child=0&srCitizen=0&infant=0"
                f"&currency=INR&redirectTo=/")

    @staticmethod
    def _payload(origin: str, destination: str,
                 departure_date: date) -> dict:
        """The captured body, with our route and date substituted."""
        return {
            "pax": {"journeyClass": "ff", "adult": 1, "child": 0,
                    "infant": 0, "srCitizen": 0},
            "codes": {"currency": "INR"},
            "origin": origin,
            "destination": destination,
            "centerDate": departure_date.isoformat(),
        }

    def fetch(self, origin: str, destination: str,
              departure_date: date) -> List[FareOffer]:
        try:
            response = self._session.post(
                ENDPOINT,
                data=json.dumps(self._payload(origin, destination,
                                              departure_date)),
                headers={"referer": self._referer(origin, destination,
                                                  departure_date)},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise FareSourceError(
                f"spicejet request failed for {origin}-{destination} "
                f"{departure_date}: {exc}"
            ) from exc
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

        if response.status_code in (401, 403):
            if not self._token_refreshed:
                self._token_refreshed = True
                print(f"[spicejet] {response.status_code} — refreshing token")
                self._session.headers["authorization"] = \
                    self._obtain_token(force=True)
                return self.fetch(origin, destination, departure_date)
            raise FareSourceError(
                f"spicejet returned {response.status_code} even after "
                f"refreshing the token."
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise FareSourceError(f"spicejet HTTP error: {exc}") from exc
        except ValueError as exc:
            raise FareSourceError(
                f"spicejet returned non-JSON (first 200 chars: "
                f"{response.text[:200]!r})"
            ) from exc

        offers = self._parse(payload, origin, destination, departure_date)
        if not offers:
            raise FareSourceError(
                f"no fares parsed for {origin}-{destination} "
                f"{departure_date}. Top-level keys: "
                f"{list(payload)[:10] if isinstance(payload, dict) else type(payload)}. "
                f"Run 'py probe.py --source spicejet' and adjust _parse."
            )
        return offers

    def _parse(self, payload, origin: str, destination: str,
               departure_date: date) -> List[FareOffer]:
        """Read the low-fare calendar.

        Verified against a live response. Shape:

            data.lowFareDateMarkets[] = {
                origin, destination,
                departureDate: "2026-09-10T00:00:00",
                lowestFareAmount: {fareAmount, taxesAndFeesAmount} | null
            }

        Three things this has to get right:

        * The fare amount sits in a CHILD object while the date sits on
          the parent, so they must be read together. An earlier version
          searched for both in one dict, matched nothing, and reported
          every cell as empty rather than as an error — which is how a
          parser bug disguises itself as missing data.
        * The calendar returns a span of dates around the one requested.
          Only the exact departure date is kept; storing a neighbouring
          date against our advance-purchase window would silently
          corrupt the index.
        * lowestFareAmount is null on days with no fare. That is a real
          empty cell, not a failure.

        Assumption worth checking against the site: fareAmount and
        taxesAndFeesAmount are treated as components that sum to what a
        traveller pays. On the sample, 4900 + 1547 = 6447 for DEL-BOM.
        They are siblings with those names, so this is the natural
        reading — but compare one cell against spicejet.com before the
        numbers go on a slide.

        A calendar carries no flight number, departure time or fare
        class, so SpiceJet rows are thinner than Akasa's. That is fine
        for the index, which uses the cheapest fare per cell anyway.
        """
        collection_date = date.today()
        wanted = departure_date.isoformat()
        data = (payload or {}).get("data") or {}
        offers: List[FareOffer] = []

        for market in data.get("lowFareDateMarkets") or []:
            if not isinstance(market, dict):
                continue
            if not str(market.get("departureDate", "")).startswith(wanted):
                continue
            if (market.get("origin") != origin
                    or market.get("destination") != destination):
                continue

            low = market.get("lowestFareAmount")
            if not isinstance(low, dict):
                continue                      # null — no fare on this date

            base = low.get("fareAmount")
            taxes = low.get("taxesAndFeesAmount")
            if not isinstance(base, (int, float)) or base <= 0:
                continue
            base = float(base)
            taxes = float(taxes) if isinstance(taxes, (int, float)) else None
            total = base + (taxes or 0.0)

            offers.append(FareOffer(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                collection_date=collection_date,
                total_fare_inr=total,
                base_fare_inr=base,
                taxes_inr=taxes,
                source_portal=self.name,
                carrier=self.default_carrier,
                raw=market,
            ))

        return offers

    def close(self) -> None:
        self._session.close()
