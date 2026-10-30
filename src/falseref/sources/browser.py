"""Headless Chromium (Playwright) for pages a plain request cannot read: sites
that turn scripts away, and pages that render their text with JavaScript.

Optional. Without Playwright, or with ENABLED = False, render() returns None
and pages are judged from the plain request alone.

    pip install playwright && playwright install chromium
"""

import logging
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

ENABLED = True

# Playwright's sync API is bound to the thread that started it and refuses to
# run inside a running event loop (Jupyter), so it lives in one worker thread.
_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="falseref-browser")
_state = {}


def _context():
    if "context" not in _state:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        try:
            # full Chromium in headless mode: closer to a real browser than
            # the headless shell, which bot filters spot readily
            browser = pw.chromium.launch(channel="chromium")
        except Exception:
            pw.stop()
            raise
        # and without "HeadlessChrome" in its user agent, which they look for
        page = browser.new_page()
        agent = page.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
        page.close()
        _state.update(pw=pw, browser=browser, context=browser.new_context(user_agent=agent, locale="en-US"))
    return _state["context"]


def _render(url, timeout):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    page = _context().new_page()
    # the status that counts is the last document the tab navigated to: bot
    # checks answer 403 first and reload into the page once the script passes
    documents = []
    page.on("response", lambda r: documents.append(r)
            if r.request.is_navigation_request() and r.frame == page.main_frame else None)
    try:
        page.goto(url, timeout=timeout * 1000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PlaywrightTimeout:
            pass  # pages that keep polling never go idle; read what has rendered
        status = documents[-1].status if documents else None
        return status, page.url, page.content().encode()
    finally:
        page.close()


def render(url, timeout=30):
    """-> (status, final url, rendered HTML bytes), or None when the browser is
    unavailable or could not load the page (PDF downloads included)."""
    if not ENABLED or _state.get("missing"):
        return None
    try:
        return _worker.submit(_render, url, timeout).result()
    except Exception as exc:
        if "context" in _state:
            log.info("browser could not load %s (%s)", url, type(exc).__name__)
        else:  # Playwright or its Chromium is not installed
            _state["missing"] = True
            log.warning("no browser (%s: %s): blocked and JavaScript pages are judged without one",
                        type(exc).__name__, str(exc).splitlines()[0] if str(exc) else "")
    return None
