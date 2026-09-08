"""IndiGo fare source — POST /v2/flight/search on the dotREZ booking API.

This is the endpoint the goindigo.in booking page itself calls to draw its
own results. We send the same request the browser sends. That is web
scraping: an undocumented endpoint belonging to the site we are collecting
from, serving the same public list prices the page displays.

CREDENTIALS ARE NEVER HARDCODED. Two values are needed:

    INDIGO_TOKEN     the bearer JWT. Expires 15 MINUTES after issue.
    INDIGO_USER_KEY  a static API key (defaults to the public web one).

Optionally:

    INDIGO_COOKIE    the raw Cookie header, if the API rejects us without
                     the Akamai bot-manager cookies (_abck, bm_sz, ...).

Get a token by opening the booking page, running one search, and copying
the `authorization` header off the `search` request in DevTools. Because it
lasts 15 minutes, a full 60-cell run must complete inside that window — at
a 2 second delay that is about 2 minutes, so there is plenty of room, but
the token must be refreshed between daily runs.

TODO, and the one thing that would make this fully automatic: capture the
`token.json` or `refresh` request from DevTools and implement
`_fetch_token()` below. Then no manual step remains.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from typing import Any, Iterator, List, Optional

import requests

from ..config import REQUEST_DELAY_SECONDS
from ..model import FareOffer
from .base import FareSource, FareSourceError

ENDPOINT = "https://api-prod-flight-skyplus6e.goindigo.in/v2/flight/search"

# Public key the goindigo.in web booking engine uses. Not a secret, but
# overridable in case it rotates.
DEFAULT_USER_KEY = "31e90be8fff2f5e2eea242c225f21b1a"


class IndigoSource(FareSource):
    name = "indigo"
    daily_request_budget = 400
    default_carrier = "6E"

    @staticmethod
    def _credential(env_name: str, file_name: str) -> Optional[str]:
        """Read a credential from an env var, else from a local file.

        The file route exists because Windows cmd mangles the cookie
        string: it is full of %40, %2f and | characters, and cmd expands
        anything between percent signs as a variable. Pasting into a file
        sidesteps the whole problem.

        Both files are gitignored. Never commit either.
        """
        value = os.environ.get(env_name)
        if value:
            return value.strip()
        if os.path.exists(file_name):
            with open(file_name, encoding="utf-8") as handle:
                text = handle.read().strip()
            return text or None
        return None

    def __init__(self, timeout: int = 30):
        token = self._credential("INDIGO_TOKEN", ".indigo_token")
        if not token:
            raise FareSourceError(
                "No token. Either set INDIGO_TOKEN, or paste the "
                "'authorization' header value into a file named "
                ".indigo_token in this folder. It expires 15 minutes "
                "after it is issued."
            )

        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": token,
            "content-type": "application/json",
            "origin": "https://www.goindigo.in",
            "referer": "https://www.goindigo.in/",
            "user_key": os.environ.get("INDIGO_USER_KEY", DEFAULT_USER_KEY),
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
        })

        cookie = self._credential("INDIGO_COOKIE", ".indigo_cookie")
        if cookie:
            self._session.headers["cookie"] = cookie
            print(f"[indigo] using cookie header ({len(cookie)} chars)")
        else:
            print("[indigo] no cookie set — trying token only")

    # ------------------------------------------------------------------
    # request
    # ------------------------------------------------------------------

    @staticmethod
    def _payload(origin: str, destination: str, departure_date: date) -> dict:
        """The exact body the booking page sends, with our values in it."""
        return {
            "codes": {"currency": "INR", "promotionCode": ""},
            "criteria": [{
                "dates": {"beginDate": departure_date.isoformat()},
                "flightFilters": {"type": "All"},
                "stations": {
                    "originStationCodes": [origin],
                    "destinationStationCodes": [destination],
                },
            }],
            "passengers": {
                "residentCountry": "IN",
                "types": [{"count": 1, "discountCode": "", "type": "ADT"}],
            },
            # This is what makes the response carry the fare breakdown.
            "taxesAndFees": "TaxesAndFees",
            "tripCriteria": "oneWay",
            "isRedeemTransaction": False,
        }

    def fetch(self, origin: str, destination: str,
              departure_date: date) -> List[FareOffer]:
        try:
            response = self._session.post(
                ENDPOINT,
                data=json.dumps(self._payload(origin, destination,
                                              departure_date)),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise FareSourceError(
                f"indigo request failed for {origin}-{destination} "
                f"{departure_date}: {exc}"
            ) from exc
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

        if response.status_code in (401, 403):
            raise FareSourceError(
                f"indigo returned {response.status_code} — the token has "
                f"most likely expired (they last 15 minutes). Grab a fresh "
                f"one and re-export INDIGO_TOKEN. If a fresh token still "
                f"fails, the Akamai bot cookies are being enforced: set "
                f"INDIGO_COOKIE to the full cookie header."
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise FareSourceError(f"indigo HTTP error: {exc}") from exc
        except ValueError as exc:
            raise FareSourceError(
                f"indigo returned non-JSON (first 200 chars: "
                f"{response.text[:200]!r})"
            ) from exc

        offers = self._parse(payload, origin, destination, departure_date)

        if not offers:
            # Either genuinely no flights, or the response shape moved.
            # Say which, rather than silently returning nothing.
            raise FareSourceError(
                f"no fares parsed for {origin}-{destination} "
                f"{departure_date}. Top-level keys were: "
                f"{list(payload)[:10]}. If flights do exist on this route, "
                f"the response shape has changed — save the JSON and adjust "
                f"_parse()."
            )
        return offers

    # ------------------------------------------------------------------
    # response
    # ------------------------------------------------------------------

    @staticmethod
    def _walk(node: Any) -> Iterator[dict]:
        """Yield every dict anywhere in the response that carries a fare.

        Written defensively on purpose. dotREZ nests fares several levels
        deep inside journeys and fare keys, and the exact path differs
        between routes and response versions. Searching for the field we
        care about is more robust than hardcoding a path, and it cannot
        break silently — if it finds nothing, fetch() raises and says so.
        """
        if isinstance(node, dict):
            if "totalFareAmount" in node:
                yield node
            for value in node.values():
                yield from IndigoSource._walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from IndigoSource._walk(item)

    @staticmethod
    def _first(node: dict, *names: str) -> Optional[Any]:
        for name in names:
            if node.get(name) not in (None, ""):
                return node[name]
        return None

    def _parse(self, payload: Any, origin: str, destination: str,
               departure_date: date) -> List[FareOffer]:
        collection_date = date.today()
        offers: List[FareOffer] = []
        seen: set = set()

        for node in self._walk(payload):
            total = node.get("totalFareAmount")
            if not isinstance(total, (int, float)) or total <= 0:
                continue

            base = self._first(node, "totalPublishFare", "baseFareAmount",
                               "originalFareAmount")
            carrier = self._first(node, "carrierCode", "operatingCarrier",
                                  "marketingCarrier")
            carrier = carrier or getattr(self, "default_carrier", "")
            flight_number = self._first(node, "flightNumber", "identifier",
                                        "flightDesignator")
            if isinstance(flight_number, dict):
                flight_number = flight_number.get("identifier")
            if flight_number is not None:
                flight_number = str(flight_number).replace(" ", "")
                if carrier and not flight_number.startswith(str(carrier)):
                    flight_number = f"{carrier}{flight_number}"

            depart_time = None
            raw_departure = self._first(node, "departureTime", "std",
                                        "departure")
            if isinstance(raw_departure, str) and "T" in raw_departure:
                depart_time = raw_departure.split("T", 1)[1][:5]

            taxes = None
            if isinstance(base, (int, float)) and base > 0:
                taxes = round(float(total) - float(base), 2)
                if taxes < 0:
                    taxes = None

            key = (float(total), flight_number, depart_time,
                   self._first(node, "fareClass", "productClass"))
            if key in seen:
                continue
            seen.add(key)

            offers.append(FareOffer(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                collection_date=collection_date,
                total_fare_inr=float(total),
                base_fare_inr=float(base) if isinstance(base, (int, float)) else None,
                taxes_inr=taxes,
                source_portal=self.name,
                carrier=str(carrier),
                flight_number=flight_number,
                depart_time_local=depart_time,
                fare_class=self._first(node, "productClass", "fareClass",
                                       "cabin"),
                raw=node,
            ))

        return offers

    def close(self) -> None:
        self._session.close()
