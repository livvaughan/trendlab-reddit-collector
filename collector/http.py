"""Shared HTTP with retries and backoff. Every collector goes through request()."""
import logging
import random
import time

import requests

log = logging.getLogger("trendlab.social")

RETRY_STATUS = {429, 500, 502, 503, 504}


class ApiError(Exception):
    pass


def request(method, url, *, session=None, retries=5, base_delay=2.0, timeout=30, **kwargs):
    """Send a request; retry on network errors and 429/5xx with exponential backoff.

    Honors Retry-After when the server sends it. Raises ApiError after the last attempt
    or immediately on other 4xx (bad key, missing permission), since retrying won't fix those.
    """
    s = session or requests
    for attempt in range(retries):
        try:
            r = s.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as e:
            err = f"network error: {e}"
        else:
            if r.status_code < 400:
                return r
            if r.status_code not in RETRY_STATUS:
                raise ApiError(f"{r.status_code} from {url.split('?')[0]}: {r.text[:300]}")
            err = f"HTTP {r.status_code}"
            ra = r.headers.get("Retry-After")
            if ra and ra.isdigit():
                wait = min(int(ra), 300)
                log.warning("%s on %s, server asked to wait %ss", err, url.split("?")[0], wait)
                time.sleep(wait)
                continue
        wait = base_delay * 2 ** attempt + random.uniform(0, 1)
        log.warning("%s on %s (attempt %d/%d), retrying in %.0fs", err, url.split("?")[0], attempt + 1, retries, wait)
        time.sleep(wait)
    raise ApiError(f"gave up on {url.split('?')[0]} after {retries} attempts ({err})")
