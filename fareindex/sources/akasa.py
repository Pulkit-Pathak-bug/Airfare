"""Akasa Air fare source — POST /api/ibe/availability/search.

This is the endpoint akasaair.com's own booking page calls to draw its
results. We send the same request the browser sends.

WHY THIS ONE IS EASY AND INDIGO WAS NOT

The captured Akasa request carries no cookies at all — no Akamai bot
cookies, no session cookie, nothing. Just headers and an authorization
token. So a plain HTTP client works and no browser is needed.

Akasa and IndiGo both run Navitaire as their reservation platform, which
is why the request bodies look so similar (criteria / stations /
passengers / codes). That is also why the response parser written for
IndiGo is reused here unchanged: same platform, same fare object shape.
One parser, two airlines — which is the multi-source engine the problem
statement asks for, demonstrated rather than claimed.

CREDENTIALS

    AKASA_TOKEN   the authorization header value, or paste it into a file
                  named .akasa_token in this folder.

Unlike IndiGo's 15-minute JWT, this token's lifetime is unknown — find out
empirically. If runs start failing with 401/403, grab a fresh one the same
way: search on akasaair.com, DevTools, Network, the availability/search
request, copy the authorization header.
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

ENDPOINT = "https://prod-bl.qp.akasaair.com/api/ibe/availability/search"


class AkasaSource(FareSource):
    name = "akasa"
    daily_request_budget = 400
    default_carrier = "QP"

    @staticmethod
    def _obtain_token(force: bool = False) -> str:
        """Env var, then cached file, then mint one with a browser.

        The manual paths stay first so a hand-captured token always wins —
        useful when debugging. The broker is the fallback that makes a
        scheduled daily run possible without a human in the loop.
        """
        if not force:
            token = IndigoSource._credential("AKASA_TOKEN", ".akasa_token")
            if token:
                return token
        from ..token_broker import TokenUnavailable, get
        try:
            return get("akasa", force=force)
        except TokenUnavailable as exc:
            raise FareSourceError(
                f"Could not obtain an Akasa token automatically: {exc}\n"
                f"Fall back to pasting the 'authorization' header from "
                f"DevTools into .akasa_token"
            ) from exc

    def __init__(self, timeout: int = 30):
        token = self._obtain_token()
        self._token_refreshed = False
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "accept": "application/json",
            "accept-language": "en-US,en;q=0.9",
            "authorization": token,
            "content-type": "application/json",
            "origin": "https://www.akasaair.com",
            "referer": "https://www.akasaair.com/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
        })

    @staticmethod
    def _payload(origin: str, destination: str,
                 departure_date: date) -> dict:
        """The body the booking page sends, with our route and date in it.

        Everything here is copied from the captured request. The only
        parts that change per call are the two station codes and
        beginDate — which is exactly why this endpoint is usable: the
        search is expressed in plain values, not an opaque blob.
        """
        return {
            "criteria": [{
                "stations": {
                    "originStationCodes": [origin],
                    "destinationStationCodes": [destination],
                    "searchDestinationMacs": True,
                    "searchOriginMacs": True,
                },
                # Akasa wants a full ISO timestamp, not a bare date.
                "dates": {"beginDate": f"{departure_date.isoformat()}T00:00:00"},
                "filters": {
                    "compressionType": 1,
                    "maxConnections": 8,
                    "productClasses": ["NB", "LB", "EC", "AV"],
                    "fareTypes": ["NB", "LB", "R", "V"],
                },
            }],
            "passengers": {
                "types": [{"type": "ADT", "count": 1}],
                "residentCountry": "",
            },
            "codes": {"currencyCode": "INR", "promotionCode": ""},
            "offerCode": None,
            "numberOfFaresPerJourney": 10,
            # 1 asks for the tax and fee breakdown, which is what fills
            # base_fare_inr and taxes_inr rather than only a total.
            "taxesAndFees": 1,
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
                f"akasa request failed for {origin}-{destination} "
                f"{departure_date}: {exc}"
            ) from exc
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

        if response.status_code in (401, 403):
            # Self-heal: mint a fresh token and retry this cell once. A
            # 60-cell run outlives most token lifetimes, so expiry
            # mid-collection is normal rather than exceptional.
            if not self._token_refreshed:
                self._token_refreshed = True
                print(f"[akasa] {response.status_code} — token expired "
                      f"mid-run, minting a fresh one")
                try:
                    self._session.headers["authorization"] = \
                        self._obtain_token(force=True)
                except FareSourceError:
                    raise
                try:
                    return self.fetch(origin, destination, departure_date)
                finally:
                    # Clear the flag so a LATER expiry in the same run is
                    # tolerated too. The one-shot guard exists to stop an
                    # infinite loop on a permanently bad credential, not to
                    # ration refreshes — and as the comment above says, a
                    # 60-cell run outlives most token lifetimes, so more
                    # than one expiry per run is entirely normal.
                    self._token_refreshed = False
            raise FareSourceError(
                f"akasa returned {response.status_code} even after "
                f"refreshing the token. Capture one by hand into "
                f".akasa_token and check the API has not changed."
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise FareSourceError(f"akasa HTTP error: {exc}") from exc
        except ValueError as exc:
            raise FareSourceError(
                f"akasa returned non-JSON (first 200 chars: "
                f"{response.text[:200]!r})"
            ) from exc

        offers = self._parse(payload, origin, destination, departure_date)

        if not offers:
            # Distinguish "Akasa does not fly this route" from "the
            # response shape changed". The first is data — an observed
            # absence, which the collector records as an empty cell. The
            # second is a bug and must be loud.
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict) and "results" in data:
                return []          # valid answer: no service on this pair
            raise FareSourceError(
                f"unparseable response for {origin}-{destination} "
                f"{departure_date}. Top-level keys were: "
                f"{list(payload)[:10] if isinstance(payload, dict) else type(payload)}"
            )
        return offers

    def _parse(self, payload, origin: str, destination: str,
               departure_date: date) -> List[FareOffer]:
        """Turn Akasa's response into FareOffer rows.

        The response is in two halves and you have to join them:

          data.results[].trips[].journeysAvailableByMarket[].value[]
              the flights — designator (airports, times), segments
              (carrier and flight number), and a list of fare KEYS

          data.faresAvailable[]
              the prices, each under the key a journey refers to

        So we index the fares by key first, then walk the journeys and
        look up each one's fares. Money mapping, verified against a live
        response: totals.fareTotal is what the passenger pays,
        totals.publishedTotal is the base fare, and the difference is
        taxes and fees (on the sample: 6880 - 5640 = 1240, matching the
        itemised service charges exactly).
        """
        collection_date = date.today()
        data = (payload or {}).get("data") or {}

        fare_index = {}
        for entry in data.get("faresAvailable") or []:
            key = entry.get("key")
            if key:
                fare_index[key] = entry.get("value") or {}

        offers: List[FareOffer] = []
        seen = set()

        for result in data.get("results") or []:
            for trip in result.get("trips") or []:
                for market in trip.get("journeysAvailableByMarket") or []:
                    for journey in market.get("value") or []:
                        des = journey.get("designator") or {}

                        # searchOriginMacs/searchDestinationMacs are true in
                        # the request, so the API also returns nearby
                        # airports — DXN (Noida) alongside DEL. A different
                        # airport is a different product and would pollute
                        # the index, so only the exact pair is kept.
                        if (des.get("origin") != origin
                                or des.get("destination") != destination):
                            continue

                        # Same reasoning, one axis over: keep only the date
                        # that was asked for. The stored departure_date is
                        # the REQUESTED one, so a journey returned for a
                        # neighbouring day — an overnight positioning leg,
                        # or a response that spans dates — would be filed
                        # against the wrong advance-purchase window and
                        # silently corrupt the index rather than error.
                        # spicejet.py guards this explicitly; so does this.
                        departed = str(des.get("departure") or "")
                        if departed and not departed.startswith(
                                departure_date.isoformat()):
                            continue

                        depart_time = None
                        raw = des.get("departure")
                        if isinstance(raw, str) and "T" in raw:
                            depart_time = raw.split("T", 1)[1][:5]

                        segments = journey.get("segments") or []
                        ident = (segments[0].get("identifier") or {}) if segments else {}
                        carrier = ident.get("carrierCode") or self.default_carrier
                        number = ident.get("identifier")
                        flight_number = (f"{carrier}{number}" if number else None)
                        stops = journey.get("stops")

                        for journey_fare in journey.get("fares") or []:
                            value = fare_index.get(
                                journey_fare.get("fareAvailabilityKey"))
                            if not value:
                                continue
                            totals = value.get("totals") or {}
                            total = totals.get("fareTotal")
                            base = totals.get("publishedTotal")
                            if not isinstance(total, (int, float)) or total <= 0:
                                continue

                            inner = value.get("fares") or []
                            product_class = (inner[0].get("productClass")
                                             if inner else None)

                            taxes = None
                            if isinstance(base, (int, float)) and base > 0:
                                taxes = round(float(total) - float(base), 2)
                                if taxes < 0:
                                    taxes = None

                            key = (flight_number, depart_time, product_class,
                                   float(total))
                            if key in seen:
                                continue
                            seen.add(key)

                            offers.append(FareOffer(
                                origin=origin,
                                destination=destination,
                                departure_date=departure_date,
                                collection_date=collection_date,
                                total_fare_inr=float(total),
                                base_fare_inr=(float(base) if isinstance(
                                    base, (int, float)) else None),
                                taxes_inr=taxes,
                                source_portal=self.name,
                                carrier=carrier,
                                flight_number=flight_number,
                                depart_time_local=depart_time,
                                fare_class=product_class,
                                raw={"totals": totals,
                                     "productClass": product_class,
                                     "stops": stops},
                            ))

        return offers

    def close(self) -> None:
        self._session.close()
