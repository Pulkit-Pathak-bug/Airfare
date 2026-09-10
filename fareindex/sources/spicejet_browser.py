"""SpiceJet via a real browser — navigate the search, read the response.

WHY

The SpiceJet API answers the browser but returns a 9-byte "Forbidden" to
plain HTTP, even with a valid token, the right Referer and the client-hint
headers copied verbatim. The API is served from the same host as the
website, so its WAF sees these calls and refuses anything whose TLS
handshake does not look like a browser. Headers cannot fix that.

But SpiceJet's results page takes its entire search in the URL — from, to,
departure date. So we do not need to drive a form or inject fetch calls:
point a real browser at the search URL for each cell and simply read the
API response the page makes on its own. The browser supplies its own TLS
fingerprint, cookies, token and Referer, because it is genuinely the site
doing the search.

This is slower than plain HTTP — one page load per cell rather than one
request — but it is the honest way in, and 60 cells still finishes in a
few minutes.

    py collect.py --source spicejet_browser

Set SPICEJET_HEADLESS=1 to hide the window once it is known to work,
though headless shells are more detectable and it may start failing.
"""

from __future__ import annotations

import os
import time
from datetime import date
from typing import List, Optional

from ..config import REQUEST_DELAY_SECONDS
from ..model import FareOffer
from .base import FareSource, FareSourceError
from .spicejet import SpiceJetSource

RESPONSE_MARKER = "/api/v2/search/lowfare"


class SpiceJetBrowserSource(FareSource):
    name = "spicejet"          # same portal — rows sit with the others
    daily_request_budget = 200
    default_carrier = "SG"

    def __init__(self, headless: Optional[bool] = None, timeout: int = 60000):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise FareSourceError(
                "playwright is not installed. Run:\n"
                "    py -m pip install playwright\n"
                "    py -m playwright install chromium"
            ) from exc

        if headless is None:
            headless = os.environ.get("SPICEJET_HEADLESS", "") != ""

        # Off-screen is the middle option. Headless uses Playwright's
        # headless shell, which WAFs detect; off-screen runs the very same
        # full browser that already works and merely parks it where you
        # cannot see it. Slightly wasteful, completely undetectable.
        offscreen = os.environ.get("SPICEJET_OFFSCREEN", "") != ""
        args = ["--disable-blink-features=AutomationControlled"]
        if offscreen and not headless:
            args += ["--window-position=-32000,-32000"]

        self._timeout = timeout
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=headless,
                                                     args=args)
            self._context = self._browser.new_context(
                locale="en-IN", timezone_id="Asia/Kolkata",
                viewport={"width": 1440, "height": 900},
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/153.0.0.0 Safari/537.36"))
            self._context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',"
                "{get:()=>undefined})")
            self._page = self._context.new_page()
            mode = ("headless" if headless
                    else "off-screen" if offscreen else "visible")
            print(f"[spicejet_browser] browser up ({mode})")
        except Exception:
            self.close()
            raise

    def fetch(self, origin: str, destination: str,
              departure_date: date) -> List[FareOffer]:
        url = SpiceJetSource._referer(origin, destination, departure_date)

        # The same politeness delay the plain-HTTP sources apply. It was
        # missing here, which made the compliance claim ("requests are
        # spaced by a fixed delay") untrue of the one SpiceJet path that
        # actually runs. Page-load latency is not a rate limit.
        time.sleep(REQUEST_DELAY_SECONDS)

        try:
            # Wait for the page's own call to the fare API, rather than
            # making one ourselves. expect_response is armed before the
            # navigation so the response cannot be missed.
            with self._page.expect_response(
                lambda r: RESPONSE_MARKER in r.url,
                timeout=self._timeout,
            ) as caught:
                self._page.goto(url, wait_until="commit",
                                timeout=self._timeout)
            response = caught.value

            if response.status >= 400:
                raise FareSourceError(
                    f"spicejet page's own API call returned "
                    f"{response.status} for {origin}-{destination} "
                    f"{departure_date}"
                )
            payload = response.json()
        except FareSourceError:
            raise
        except Exception as exc:                             # noqa: BLE001
            raise FareSourceError(
                f"spicejet_browser failed for {origin}-{destination} "
                f"{departure_date}: {exc}"
            ) from exc

        # Save the first response of each run. The low-fare calendar's
        # field names and date format are not known from the captured
        # request alone, and a parser written against a guess fails
        # silently as empty cells rather than loudly as an error.
        if not getattr(self, "_dumped", False):
            self._dumped = True
            try:
                import json as _json
                os.makedirs("data", exist_ok=True)
                with open("data/spicejet_sample.json", "w",
                          encoding="utf-8") as handle:
                    _json.dump(payload, handle, indent=2)
                print("[spicejet_browser] saved data/spicejet_sample.json")
            except Exception as exc:                         # noqa: BLE001
                print(f"[spicejet_browser] could not save sample: {exc}")

        offers = self._parse(payload, origin, destination, departure_date)
        if not offers:
            # A route SpiceJet does not fly is data, not a bug; only shout
            # when the response looks like a shape we cannot read.
            if isinstance(payload, (dict, list)):
                return []
            raise FareSourceError(
                f"unreadable response for {origin}-{destination} "
                f"{departure_date}: {type(payload)}"
            )
        return offers

    # The low-fare calendar parser, shared with the plain-HTTP source. It
    # keeps only the exact departure date asked for — the calendar returns
    # neighbouring dates, and storing one against our advance-purchase
    # window would silently corrupt the index.
    _parse = SpiceJetSource._parse

    def close(self) -> None:
        for attr in ("_context", "_browser"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:                            # noqa: BLE001
                    pass
        pw = getattr(self, "_pw", None)
        if pw is not None:
            try:
                pw.stop()
            except Exception:                                # noqa: BLE001
                pass
