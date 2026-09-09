"""Get a site's bearer token automatically, by watching a real browser.

WHY THIS EXISTS

Airline booking APIs hand their own front-end a short-lived token. Copying
that token out of DevTools by hand works once; it does not survive a daily
schedule, and "capable of scheduled daily extraction" is a stated PS
requirement. So instead of a human doing it, a browser does: open the
site, let it mint its token the way it normally does, and read the
Authorization header off the requests it makes to its own API.

The browser is used ONLY for authentication. Once a token is in hand the
collector goes back to plain HTTP for all 60 cells, which is far faster
than driving a browser 60 times. Browser for auth, requests for volume.

USE

    py -m fareindex.token_broker akasa        # mint and cache a token
    py -m fareindex.token_broker akasa --show

Sources call get() themselves, so normally you never run this directly —
the collector refreshes its own token when the cached one goes stale or a
call comes back 401/403.

REQUIRES

    py -m pip install playwright
    py -m playwright install chromium
"""

from __future__ import annotations

import os
import time
from typing import Dict, Optional, Sequence

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/152.0.0.0 Safari/537.36")

# site to open, host substring whose requests carry the token, cache file,
# and any follow-up pages to try if the landing page does not mint one.
SITES: Dict[str, dict] = {
    "akasa": {
        "site_url": "https://www.akasaair.com/",
        "api_host": "qp.akasaair.com",
        "cache_path": ".akasa_token",
        "follow_ups": ["https://www.akasaair.com/book/flights"],
        "ttl_seconds": 600,
    },
    "spicejet": {
        "site_url": "https://www.spicejet.com/",
        "api_host": "spicejet.com/api",
        "cache_path": ".spicejet_token",
        # The home page is only a search form and never calls the API, so
        # no token appears there. SpiceJet's results page, unlike
        # IndiGo's, takes its whole search in the URL — so the browser can
        # navigate straight to a real search, which mints the token and
        # fires the API call. {date} is filled in with a near-future date.
        "follow_ups": [
            "https://www.spicejet.com/search?from=DEL&to=BOM&tripType=1"
            "&departure={date}&adult=1&child=0&srCitizen=0&infant=0"
            "&currency=INR&redirectTo=/"
        ],
        "ttl_seconds": 900,
    },
    "indigo": {
        "site_url": "https://www.goindigo.in/",
        "api_host": "skyplus6e.goindigo.in",
        "cache_path": ".indigo_token",
        # Deliberately no follow-up to /book/flight-select.html: opened
        # directly it has no search state, shows "No Data Found" and
        # bounces to the home page without minting anything.
        "follow_ups": [],
        # IndiGo puts its bearer token in a cookie rather than only on the
        # wire. Playwright's context API can read HttpOnly cookies, which
        # document.cookie cannot — that is why earlier attempts to scrape
        # the cookie from inside the page came up empty.
        "cookie_names": ["auth_token"],
        "ttl_seconds": 600,
    },
}


def _token_from_cookies(cookies, names) -> Optional[str]:
    """Pull a bearer token out of a cookie, raw or JSON-wrapped.

    IndiGo's auth_token cookie holds {"token": "...", "expiresIn...": n}.
    Other sites store the JWT bare. Handle both, and URL-decoding too.
    """
    import json
    from urllib.parse import unquote

    for cookie in cookies:
        if cookie.get("name") not in names:
            continue
        raw = (cookie.get("value") or "").strip()
        if not raw:
            continue
        candidates = [raw]
        decoded = unquote(raw)
        if decoded != raw:
            candidates.append(decoded)

        # JSON-wrapped first, across every candidate. Doing this before
        # the bare-JWT branch matters: a URL-encoded JSON value contains
        # dots and would otherwise be mistaken for a bare token and
        # returned still encoded.
        for candidate in candidates:
            if not candidate.lstrip().startswith("{"):
                continue
            try:
                parsed = json.loads(candidate)
            except ValueError:
                continue
            for key in ("token", "accessToken", "access_token", "jwt"):
                value = parsed.get(key)
                if isinstance(value, str) and len(value) > 20:
                    return value

        # Otherwise a bare JWT, which has dots but no JSON or escaping.
        for candidate in candidates:
            if ("{" not in candidate and "%" not in candidate
                    and len(candidate) > 20 and candidate.count(".") >= 2):
                return candidate
    return None


class TokenUnavailable(RuntimeError):
    """The browser ran but no token appeared. Message says what to try."""


def cached(cache_path: str, ttl_seconds: int) -> Optional[str]:
    """A cached token, if one exists and is young enough to still be valid."""
    if not os.path.exists(cache_path):
        return None
    if time.time() - os.path.getmtime(cache_path) > ttl_seconds:
        return None
    with open(cache_path, encoding="utf-8") as handle:
        return handle.read().strip() or None


def capture(site_url: str, api_host: str, cache_path: str,
            follow_ups: Sequence[str] = (), wait_ms: int = 12000,
            headless: bool = False, verbose: bool = True,
            cookie_names: Sequence[str] = ()) -> str:
    """Open the site in a browser and read its token off its own traffic.

    Headful by default. Playwright installs chromium-headless-shell, which
    Akamai detects immediately — a headless run against goindigo.in came
    back with zero cookies, meaning the page never really loaded.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise TokenUnavailable(
            "playwright is not installed. Run:\n"
            "    py -m pip install playwright\n"
            "    py -m playwright install chromium"
        ) from exc

    found: Dict[str, str] = {}

    def watch(request):
        try:
            if api_host in request.url:
                auth = request.headers.get("authorization")
                if auth and len(auth) > 20:
                    found.setdefault("token", auth)
        except Exception:                                    # noqa: BLE001
            pass

    with sync_playwright() as p:
        # TOKEN_BROKER_OFFSCREEN=1 keeps the full browser (which passes
        # bot checks) but parks it where you cannot see it. Preferable to
        # headless, which uses a detectable shell.
        args = ["--disable-blink-features=AutomationControlled"]
        if os.environ.get("TOKEN_BROKER_OFFSCREEN") and not headless:
            args += ["--window-position=-32000,-32000"]
        browser = p.chromium.launch(headless=headless, args=args)
        try:
            context = browser.new_context(
                locale="en-IN", timezone_id="Asia/Kolkata",
                viewport={"width": 1440, "height": 900}, user_agent=USER_AGENT)
            context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',"
                "{get:()=>undefined})")
            page = context.new_page()
            page.on("request", watch)

            import datetime
            soon = (datetime.date.today()
                    + datetime.timedelta(days=7)).isoformat()

            for url in [site_url, *follow_ups]:
                if "token" in found:
                    break
                url = url.replace("{date}", soon)
                if verbose:
                    print(f"[token_broker] opening {url} ...")
                try:
                    page.goto(url, wait_until="load", timeout=60000)
                    page.wait_for_timeout(wait_ms)
                except Exception as exc:                     # noqa: BLE001
                    if verbose:
                        print(f"[token_broker]   page failed: {exc}")

                # Second place to look: the browser's own cookie jar. This
                # sees HttpOnly cookies, which page JavaScript cannot.
                if "token" not in found and cookie_names:
                    jar = context.cookies()
                    if verbose:
                        print(f"[token_broker]   {len(jar)} cookies; "
                              f"looking for {', '.join(cookie_names)}")
                    from_cookie = _token_from_cookies(jar, cookie_names)
                    if from_cookie:
                        found["token"] = from_cookie
                        if verbose:
                            print("[token_broker]   found it in a cookie")
        finally:
            browser.close()

    if "token" not in found:
        raise TokenUnavailable(
            f"No Authorization header seen on any request to {api_host}.\n"
            f"Either the site mints its token only after a search is "
            f"submitted through the form — in which case the browser has to "
            f"drive the form, or the token endpoint has to be called "
            f"directly — or the page was blocked before it loaded. Rerun "
            f"with headless=False and watch what the window actually shows."
        )

    token = found["token"]
    with open(cache_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(token)
    if verbose:
        print(f"[token_broker] captured {len(token)} chars -> {cache_path}")
    return token


def get(site: str, force: bool = False, verbose: bool = True) -> str:
    """Cached token if it is fresh, otherwise mint a new one."""
    if site not in SITES:
        raise TokenUnavailable(f"unknown site {site!r}; "
                               f"known: {', '.join(SITES)}")
    cfg = SITES[site]
    if not force:
        token = cached(cfg["cache_path"], cfg["ttl_seconds"])
        if token:
            if verbose:
                age = int(time.time() - os.path.getmtime(cfg["cache_path"]))
                print(f"[token_broker] using cached {site} token ({age}s old)")
            return token
    return capture(cfg["site_url"], cfg["api_host"], cfg["cache_path"],
                   cfg.get("follow_ups", ()), verbose=verbose,
                   cookie_names=cfg.get("cookie_names", ()))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("site", choices=sorted(SITES))
    ap.add_argument("--force", action="store_true",
                    help="ignore the cache and mint a new token")
    ap.add_argument("--headless", action="store_true",
                    help="not recommended: sites detect the headless shell")
    ap.add_argument("--show", action="store_true",
                    help="print the token (it is a credential — be careful)")
    args = ap.parse_args(argv)

    cfg = SITES[args.site]
    try:
        if args.headless:
            token = capture(cfg["site_url"], cfg["api_host"],
                            cfg["cache_path"], cfg.get("follow_ups", ()),
                            headless=True,
                            cookie_names=cfg.get("cookie_names", ()))
        else:
            token = get(args.site, force=args.force)
    except TokenUnavailable as exc:
        print(f"FAILED: {exc}")
        return 1
    print(token if args.show else f"ok — {len(token)} chars cached in "
                                  f"{cfg['cache_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
