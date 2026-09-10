"""IndiGo via a real browser — ATTEMPTED, AND CLOSED. See STATUS below.

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

STATUS: THIS SOURCE DOES NOT WORK, AND THE PARAGRAPH ABOVE EXPLAINS WHY IT
WAS EXPECTED TO. Instrumenting a completed search — banner dismissed, form
driven, results page rendered, 111 cookies set — showed that NO request
IndiGo makes carries an Authorization header at all, and no auth_token
cookie is ever set. The flow is authenticated by session cookie, so there
is no token to capture and the whole strategy above cannot apply here. The
only viable route would be the SpiceJet pattern (let the page make its own
call and read the response), which needs the search re-run per cell because
the results page carries no state in its URL. Left in the tree as the
record of a documented exclusion, not as a working adapter.

The browser-session approach itself is sound and IS what makes the working
sources schedulable — see token_broker.py and spicejet_browser.py, which
answer the PS clause about "JavaScript-rendered pages, anti-bot measures
and session management". It simply cannot be applied to a portal that
issues no token.

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
            #
            # Three things the earlier version got wrong, all of which
            # would look identical from the outside — "search worked, no
            # token":
            #
            #  * It only watched skyplus6e.goindigo.in. If the fare call
            #    goes to any other host, the token is invisible.
            #  * It required the header to start with "ey", i.e. a bare
            #    JWT. A header of "Bearer eyJ..." was silently rejected.
            #  * It listened on the page. A search that opens results in a
            #    new tab makes its requests on a different page object.
            #
            # So: listen at the CONTEXT level, accept any host, and accept
            # any header that contains a JWT. Also keep a record of what
            # was actually seen, so one failed run explains itself instead
            # of costing another round of guessing.
            self._sniffed_token: Optional[str] = None
            self._auth_hosts: dict = {}
            self._api_hosts: dict = {}

            def _sniff(request):
                try:
                    url = request.url
                    host = url.split("/")[2] if "//" in url else url[:40]
                    auth = request.headers.get("authorization")
                    if auth and len(auth) > 40 and "ey" in auth:
                        self._auth_hosts[host] = \
                            self._auth_hosts.get(host, 0) + 1
                        if not self._sniffed_token:
                            self._sniffed_token = auth
                            print(f"[indigo_browser]   token sniffed from "
                                  f"{host} ({len(auth)} chars, "
                                  f"{'Bearer-prefixed' if not auth.startswith('ey') else 'bare JWT'})")
                    elif ("/api/" in url or "skyplus" in host
                            or "availabil" in url.lower()):
                        self._api_hosts[host] = \
                            self._api_hosts.get(host, 0) + 1
                except Exception:                        # noqa: BLE001
                    pass

            # Context-level, so requests from popups and new tabs count too.
            self._context.on("request", _sniff)

            print(f"[indigo_browser] opening {BOOKING_URL} "
                  f"(headless={headless}) ...")
            self._page.goto(BOOKING_URL, wait_until="load",
                            timeout=self._timeout)
            self._page.wait_for_timeout(9000)   # let the Akamai sensor run

            # IndiGo mints its token only when a search is submitted
            # through the form — navigating to the results page directly
            # shows "No Data Found" and bounces. So run ONE search here at
            # startup; after that the token exists and every cell goes
            # through in-page fetch, no more form driving.
            if not self._sniffed_token and not any(
                c["name"] == "auth_token" for c in self._context.cookies()
            ):
                print("[indigo_browser] no token yet — running one search "
                      "through the form to mint one ...")
                self._search_once()
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

    def _search_once(self) -> None:
        """Drive one search on the homepage so IndiGo issues a token.

        Selectors are guesses until proven — IndiGo's markup is not
        documented anywhere. So this tries several strategies in order and,
        if all of them miss, dumps the page's actual inputs and buttons
        plus a screenshot. One failed run then tells us exactly what the
        DOM looks like, instead of costing another round of guessing.
        """
        page = self._page
        try:
            # The consent banner is an <a>, not a button.
            for label in ("Accept All", "Accept Essential Only"):
                try:
                    link = page.get_by_text(label, exact=False).first
                    if link.is_visible(timeout=2000):
                        link.click(timeout=2500)
                        page.wait_for_timeout(1200)
                        print(f"[indigo_browser]   dismissed banner ({label})")
                        break
                except Exception:                            # noqa: BLE001
                    continue

            # Origin and departure date come pre-filled with Delhi and
            # tomorrow, so only the destination needs setting. The airport
            # fields are <div>s that reveal an input once clicked — the
            # input's placeholder is "Start typing..", which is why looking
            # for a "To" placeholder found nothing.
            for label in ("Going to?", "Search by place"):
                try:
                    target = page.get_by_text(label, exact=False).first
                    if target.is_visible(timeout=2500):
                        target.click(timeout=3000)
                        page.wait_for_timeout(1200)
                        break
                except Exception:                            # noqa: BLE001
                    continue

            typed = False
            boxes = page.locator('input[placeholder*="Start typing" i]')
            for i in range(boxes.count()):
                box = boxes.nth(i)
                try:
                    if not box.is_visible(timeout=800):
                        continue
                    box.click(timeout=2000)
                    box.type("Mumbai", delay=160)
                    page.wait_for_timeout(2200)
                    # Prefer clicking the BOM suggestion; fall back to Enter.
                    try:
                        page.get_by_text("BOM", exact=False).first.click(
                            timeout=2500)
                    except Exception:                        # noqa: BLE001
                        page.keyboard.press("Enter")
                    page.wait_for_timeout(1500)
                    typed = True
                    break
                except Exception:                            # noqa: BLE001
                    continue

            if not typed:
                raise RuntimeError(
                    "could not type a destination into any "
                    "'Start typing..' input")

            for selector in ('a:has-text("Search Flight")',
                             'button:has-text("Search Flight")',
                             'a:has-text("Search")',
                             'button:has-text("Search")',
                             '[aria-label*="Search" i]',
                             'button[type="submit"]'):
                try:
                    button = page.locator(selector).first
                    if button.is_visible(timeout=1500):
                        button.click(timeout=3000)
                        print(f"[indigo_browser]   submitted via {selector}")
                        break
                except Exception:                            # noqa: BLE001
                    continue
            else:
                page.keyboard.press("Enter")

            page.wait_for_timeout(14000)

            # A search that opens results in a new tab leaves self._page on
            # the homepage, which has no booking session. Follow the newest
            # page in the context if one appeared.
            pages = self._context.pages
            if len(pages) > 1 and pages[-1] is not self._page:
                self._page = pages[-1]
                print(f"[indigo_browser]   followed new tab: {self._page.url}")
                self._page.wait_for_timeout(6000)

            if self._sniffed_token:
                print("[indigo_browser] search succeeded — token captured")
            else:
                raise RuntimeError("search ran but no token appeared")

        except Exception as exc:                             # noqa: BLE001
            print(f"[indigo_browser] form search failed: {exc}")
            # What the browser actually talked to. If the fare call went
            # somewhere unexpected, or carried no Authorization header at
            # all, this is the line that says so.
            if self._auth_hosts:
                print("[indigo_browser] hosts that DID carry an auth header: "
                      + ", ".join(f"{h} x{n}"
                                  for h, n in self._auth_hosts.items()))
            else:
                print("[indigo_browser] no request anywhere carried an "
                      "Authorization header.")
            if self._api_hosts:
                top = sorted(self._api_hosts.items(), key=lambda kv: -kv[1])
                print("[indigo_browser] API-looking hosts seen: "
                      + ", ".join(f"{h} x{n}" for h, n in top[:8]))
            try:
                os.makedirs("data", exist_ok=True)
                page.screenshot(path="data/indigo_form.png")
                fields = page.evaluate("""() => {
                    const out = [];
                    for (const el of document.querySelectorAll(
                            'input,button,a,[role=button],[role=combobox]')) {
                        out.push({
                            tag: el.tagName,
                            type: el.type || '',
                            id: el.id || '',
                            name: el.name || '',
                            placeholder: el.placeholder || '',
                            aria: el.getAttribute('aria-label') || '',
                            testid: el.getAttribute('data-testid') || '',
                            text: (el.innerText || '').slice(0, 28)
                        });
                    }
                    return out.filter(o => o.id||o.name||o.placeholder||o.aria||o.testid||o.text.trim()).slice(0, 90);
                }""")
                print("[indigo_browser] page controls (for fixing selectors):")
                for f in fields:
                    bits = [f"{k}={v}" for k, v in f.items() if v]
                    print("   ", " | ".join(bits))
                print("[indigo_browser] screenshot -> data/indigo_form.png")
            except Exception as dump_exc:                    # noqa: BLE001
                print(f"[indigo_browser] could not dump the page: {dump_exc}")

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
