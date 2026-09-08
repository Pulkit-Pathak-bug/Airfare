"""IndiGo via a real browser — the version that actually survives Akamai.

WHY THIS EXISTS

The plain-requests source (indigo.py) gets 403. goindigo.in sits behind
Akamai Bot Manager, which does not merely check cookies: it fingerprints
the TLS handshake and requires cookies its JavaScript sensor sets, several
of which are HttpOnly and therefore invisible to document.cookie. No amount
of copying headers by hand gets past that, and anything that did would need
re-copying every morning.

So instead of imitating the browser, we use one. Playwright opens the real
booking site, the page runs Akamai's sensor JavaScript and earns a valid
session, and then we make the fare request *from inside that page* with
fetch(). The browser attaches its own cookies, presents its own TLS
fingerprint, and reads the bearer token out of its own auth_token cookie.
Nothing is copied by hand, and nothing expires between runs.

This is also what makes the collector schedulable, which the problem
statement explicitly requires. And it is the answer to the PS clause about
handling "JavaScript-rendered pages, anti-bot measures and session
management" — we handle them by running a browser session properly rather
than pretending to be one.

SETUP (once)

    py -m pip install playwright
    py -m playwright install chromium

RUN

    py collect.py --source indigo_browser --limit 3

Add --headful to watch it work the first time; it is reassuring, and it is
how you debug when a selector or a redirect changes.
"""

from __future__ import annotations

import os
from datetime import date
from typing import List, Optional

from ..model import FareOffer
from .base import FareSource, FareSourceError
from .indigo import ENDPOINT, DEFAULT_USER_KEY, IndigoSource

BOOKING_URL = "https://www.goindigo.in/"

# Runs inside the page. Reads the bearer token from the site's own cookie,
# then posts the fare request with the browser's cookies and TLS.
_FETCH_JS = """
async ({endpoint, userKey, payload, token}) => {
  if (!token) {
    const raw = document.cookie.split('; ').find(c => c.startsWith('auth_token='));
    if (raw) {
      try {
        token = JSON.parse(decodeURIComponent(raw.slice('auth_token='.length))).token;
      } catch (e) {
        try { token = JSON.parse(raw.slice('auth_token='.length)).token; } catch (e2) {}
      }
    }
  }
  if (!token) return {__error: 'no token: neither sniffed from a request nor present as an auth_token cookie'};

  const res = await fetch(endpoint, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'accept': '*/*',
      'authorization': token,
      'content-type': 'application/json',
      'user_key': userKey
    },
    body: JSON.stringify(payload)
  });
  if (!res.ok) return {__error: 'HTTP ' + res.status};
  return await res.json();
}
"""


class IndigoBrowserSource(FareSource):
    name = "indigo"          # same portal, so rows sit with the others
    daily_request_budget = 400

    def __init__(self, headless: Optional[bool] = None, timeout: int = 45000):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise FareSourceError(
                "playwright is not installed. Run:\n"
                "    py -m pip install playwright\n"
                "    py -m playwright install chromium"
            ) from exc

        # Headful by default. Playwright installs chromium-headless-shell,
        # which Akamai detects immediately — a headless run came back with
        # zero cookies, meaning the page never really loaded. A visible
        # window is far harder to fingerprint. Set INDIGO_HEADLESS=1 to
        # override once it is known to work.
        if headless is None:
            headless = os.environ.get("INDIGO_HEADLESS", "") != ""

        self._timeout = timeout
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = self._browser.new_context(
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/152.0.0.0 Safari/537.36"
                ),
            )
            # Hide the most obvious automation giveaway.
            self._context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            self._page = self._context.new_page()

            # Sniff the bearer token off any request the site makes to its
            # own API. More reliable than the cookie: the cookie is only
            # written on some flows, but every fare call carries the header.
            self._sniffed_token: Optional[str] = None

            def _sniff(request):
                try:
                    if "skyplus6e.goindigo.in" in request.url:
                        auth = request.headers.get("authorization")
                        if auth and auth.startswith("ey"):
                            self._sniffed_token = auth
                except Exception:                        # noqa: BLE001
                    pass

            self._page.on("request", _sniff)

            print(f"[indigo_browser] opening {BOOKING_URL} "
                  f"(headless={headless}) ...")
            self._page.goto(BOOKING_URL, wait_until="load",
                            timeout=self._timeout)
            self._page.wait_for_timeout(9000)   # let the Akamai sensor run

            # The homepage may not mint a token. The booking flow does.
            if not self._sniffed_token and not any(
                c["name"] == "auth_token" for c in self._context.cookies()
            ):
                print("[indigo_browser] no token from the homepage — "
                      "opening the booking page to mint one ...")
                try:
                    self._page.goto(
                        "https://www.goindigo.in/book/flight-select.html",
                        wait_until="load", timeout=self._timeout)
                    self._page.wait_for_timeout(9000)
                except Exception as exc:                 # noqa: BLE001
                    print(f"[indigo_browser] booking page did not load: {exc}")
        except Exception:
            self.close()
            raise

        # Diagnostics. When this fails, these three lines say why.
        try:
            print(f"[indigo_browser] landed on: {self._page.url}")
            print(f"[indigo_browser] page title: {self._page.title()!r}")
        except Exception:                                # noqa: BLE001
            pass

        names = sorted(c["name"] for c in self._context.cookies())
        print(f"[indigo_browser] {len(names)} cookies: "
              f"{', '.join(names[:12])}{' ...' if len(names) > 12 else ''}")

        if not names:
            raise FareSourceError(
                "The page set no cookies at all, so it did not really load "
                "— Akamai served a block or an interstitial. Check the "
                "title above. Try INDIGO_HEADLESS unset (headful), and if "
                "a visible window still shows a challenge page, this "
                "carrier is not winnable today: switch to Akasa Air or "
                "Air India Express, which are far less defended."
            )
        if "auth_token" not in names:
            print("[indigo_browser] warning: no auth_token cookie yet — it "
                  "may only be minted once a search runs on the booking "
                  "flow. Cells will report this if so.")

    def fetch(self, origin: str, destination: str,
              departure_date: date) -> List[FareOffer]:
        payload = IndigoSource._payload(origin, destination, departure_date)
        try:
            data = self._page.evaluate(_FETCH_JS, {
                "endpoint": ENDPOINT,
                "userKey": os.environ.get("INDIGO_USER_KEY", DEFAULT_USER_KEY),
                "payload": payload,
                # Falls back to the sniffed header when the cookie is absent.
                "token": getattr(self, "_sniffed_token", None),
            })
        except Exception as exc:                        # noqa: BLE001
            raise FareSourceError(
                f"{self.name} browser call failed for {origin}-{destination} "
                f"{departure_date}: {exc}"
            ) from exc

        if isinstance(data, dict) and data.get("__error"):
            raise FareSourceError(
                f"{self.name} {origin}-{destination} {departure_date}: "
                f"{data['__error']}"
            )

        offers = IndigoSource._parse(self, data, origin, destination,
                                     departure_date)
        if not offers:
            keys = list(data)[:10] if isinstance(data, dict) else type(data)
            raise FareSourceError(
                f"no fares parsed for {origin}-{destination} "
                f"{departure_date}. Top-level keys: {keys}"
            )
        return offers

    # Reuse the parser from the requests-based source verbatim.
    _walk = staticmethod(IndigoSource._walk)
    _first = staticmethod(IndigoSource._first)

    def close(self) -> None:
        for attr in ("_context", "_browser"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:                       # noqa: BLE001
                    pass
        pw = getattr(self, "_pw", None)
        if pw is not None:
            try:
                pw.stop()
            except Exception:                           # noqa: BLE001
                pass
