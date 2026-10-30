"""HTTP helpers shared by the article and web lookups."""

import time

import requests

UA = {"User-Agent": "falseref-check/0.1"}


def get(url, **kw):
    """GET that waits out rate limits (HTTP 429). A search that never ran
    cannot say a work is missing, so retrying turns 'failed' into an answer."""
    for wait in (2, 5, 15):
        r = requests.get(url, headers=UA, timeout=30, **kw)
        if r.status_code != 429:
            return r
        time.sleep(wait)
    return r


def fetch_page(url):
    """-> (status, final url, HTML/PDF bytes or None); on failure (None, error name, None)."""
    try:
        r = requests.get(url, headers=UA, timeout=20, allow_redirects=True)
    except Exception as exc:
        return None, type(exc).__name__, None
    # bytes, not text: lxml rejects str input that carries an encoding declaration
    readable = "html" in r.headers.get("Content-Type", "") or r.content[:5] == b"%PDF-"
    markup = r.content if readable and r.content.strip() else None
    return r.status_code, r.url, markup
