"""Air India fare source — POST /cbiz-booking/v2/prime/search/air-bounds.

DIFFERENT PLATFORM FROM AKASA AND INDIGO.

Akasa and IndiGo both run Navitaire, which is why their request bodies
look alike (criteria / stations / passengers) and why one parser served
both. Air India runs an Amadeus-style stack instead — cabin / itineraries
/ travelers / originLocationCode. So the request shape differs, and the
response shape will differ too. _parse() has to be written fresh.

That is the point of the adapter interface, and worth saying out loud on
the architecture slide: two unrelated reservation platforms, two parsers,
one normalised FareOffer, and a collector that cannot tell them apart.

CREDENTIALS

    AIRINDIA_TOKEN   the full authorization header value including the
                     word "Bearer", or paste it into .airindia_token

The token is a JWT carrying its own expiry. On the captured sample,
exp - iat = 2400 seconds, so roughly 40 minutes of life — more generous
than IndiGo's 15, and long enough for a full 60-cell run several times
over.

    AIRINDIA_COOKIE  optional, or .airindia_cookie

Air India sits behind Akamai on www.airindia.com. Whether the api.
subdomain enforces those cookies is unknown — try without first. If the
calls come back 403 with a valid token, paste the cookie string in.
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

ENDPOINT = "https://api.airindia.com/cbiz-booking/v2/prime/search/air-bounds"


class AirIndiaSource(FareSource):
    name = "airindia"
    daily_request_budget = 400
    default_carrier = "AI"

    def __init__(self, timeout: int = 30):
        token = IndigoSource._credential("AIRINDIA_TOKEN", ".airindia_token")
        if not token:
            raise FareSourceError(
                "No token. Paste the full 'authorization' header value "
                "(including the word Bearer) into a file named "
                ".airindia_token in this folder. It lasts about 40 minutes."
            )
        if not token.lower().startswith("bearer "):
            token = f"Bearer {token}"

        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": token,
            "content-type": "application/json",
            "origin": "https://www.airindia.com",
            "referer": "https://www.airindia.com/",
            "origincountrycode": "IN",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
        })

        cookie = IndigoSource._credential("AIRINDIA_COOKIE", ".airindia_cookie")
        if cookie:
            self._session.headers["cookie"] = cookie
            print(f"[airindia] using cookie header ({len(cookie)} chars)")

    @staticmethod
    def _payload(origin: str, destination: str,
                 departure_date: date) -> dict:
        """The captured request body, with our route and date substituted.

        Note the station codes go in LOWERCASE — that is how the booking
        site sends them, and matching the site exactly is the safest
        default when you cannot see the server's validation rules.
        """
        return {
            "cabin": "ECONOMY",
            "itineraries": [{
                "originLocationCode": origin.lower(),
                "destinationLocationCode": destination.lower(),
                "departureDateTime": departure_date.isoformat(),
                "flexibility": None,
                "isRequestedBound": True,
            }],
            "travelers": [{"passengerTypeCode": "ADT"}],
            "promotion": {"code": ""},
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
                f"airindia request failed for {origin}-{destination} "
                f"{departure_date}: {exc}"
            ) from exc
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

        if response.status_code in (401, 403):
            raise FareSourceError(
                f"airindia returned {response.status_code}. Either the "
                f"token expired (they last ~40 minutes) or Akamai is "
                f"enforcing cookies on the api subdomain — try putting "
                f"the cookie string into .airindia_cookie."
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise FareSourceError(f"airindia HTTP error: {exc}") from exc
        except ValueError as exc:
            raise FareSourceError(
                f"airindia returned non-JSON (first 200 chars: "
                f"{response.text[:200]!r})"
            ) from exc

        return self._parse(payload, origin, destination, departure_date)

    # ------------------------------------------------------------------
    # YOUR PART.
    #
    # Run `py probe.py --source airindia` first — it saves the real
    # response to data/airindia_sample.json and prints where the money
    # lives. Then write this method against what you actually see.
    #
    # What it has to do, in order:
    #   1. walk down to wherever the flights are
    #   2. for each flight, pull carrier, flight number, departure time
    #   3. for each fare on that flight, pull the total and the base
    #   4. skip anything whose origin/destination is not the pair we asked
    #      for — some APIs return nearby airports, and a different airport
    #      is a different product
    #   5. append a FareOffer for each one
    #
    # Compare against akasa.py's _parse. Yours will differ in the paths it
    # walks and the field names it reads; the shape of the loop is the
    # same. Leave taxes as total minus base when both are present.
    # ------------------------------------------------------------------

    def _parse(self, payload, origin: str, destination: str,
               departure_date: date) -> List[FareOffer]:
        raise NotImplementedError(
            "Write me. Run `py probe.py --source airindia` to see the "
            "response shape first, then model this on akasa.py's _parse. "
            "Emit FareOffer(origin=..., destination=..., "
            "departure_date=departure_date, collection_date=date.today(), "
            "total_fare_inr=..., base_fare_inr=..., taxes_inr=..., "
            "source_portal=self.name, carrier=..., flight_number=..., "
            "depart_time_local='HH:MM', fare_class=...)"
        )

    def close(self) -> None:
        self._session.close()
