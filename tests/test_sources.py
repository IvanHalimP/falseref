"""Lookup logic that needs no network: the network calls are stubbed."""

from falseref.models import Reference
from falseref.references.grobid import as_written
from falseref.sources import article

MDPI = Reference(raw="MDPI. (2024). Artificial intelligence for predictive maintenance applications: "
                     "Key components, trustworthiness, and future trends. https://www.mdpi.com/2076-3417/14/2/898",
                 authors=["MDPI"], year="2024",
                 title="Artificial intelligence for predictive maintenance applications: "
                       "Key components, trustworthiness, and future trends")
HIT = {"title": ["Artificial Intelligence for Predictive Maintenance Applications: "
                 "Key Components, Trustworthiness, and Future Trends"],
       "author": [{"given": "Ayşegül", "family": "Uçar"}], "issued": {"date-parts": [[2024]]},
       "DOI": "10.3390/app14020898"}
URL = "https://www.mdpi.com/2076-3417/14/2/898"


def test_hit_without_cited_authors_is_a_namesake(monkeypatch):
    monkeypatch.setattr(article, "best_match", lambda _: HIT)
    monkeypatch.setattr(article, "landing_pages", lambda _: ["https://elsewhere.org/paper"])
    assert article.title_source(MDPI, URL)["state"] == "missing"
    assert article.title_source(MDPI)["state"] == "missing"


def test_hit_whose_doi_resolves_to_the_cited_url_is_the_cited_work(monkeypatch):
    monkeypatch.setattr(article, "best_match", lambda _: HIT)
    monkeypatch.setattr(article, "landing_pages", lambda _: [URL])
    source = article.title_source(MDPI, URL)
    assert source["state"] == "confirmed" and source["rec"] is HIT


def test_same_page():
    assert article.same_page("https://www.mdpi.com/2076-3417/14/2/898", "http://mdpi.com/2076-3417/14/2/898/")
    assert not article.same_page("https://www.mdpi.com/2076-3417/14/2/898", "https://www.mdpi.com/2076-3417/14/2")


def test_as_written_restores_grobid_recasing():
    assert as_written("Mdpi", "MDPI. (2024). A title.") == "MDPI"
    assert as_written("A Kumar", "Kumar, A. (2016). A title.") == "A Kumar"


from falseref.sources import web

PAGE = b"<html><head><title>The role of AI | IBM</title></head><body>text</body></html>"
SHELL = b"<html><head><title>Loading</title></head><body><div id=app></div></body></html>"


def fetches(monkeypatch, plain, rendered):
    calls = []
    monkeypatch.setattr(web, "fetch_page", lambda url: plain)
    monkeypatch.setattr(web, "render", lambda url: calls.append(url) or rendered)
    return calls


def test_blocked_page_is_read_with_a_browser(monkeypatch):
    fetches(monkeypatch, (403, "https://x.com/a", None), (200, "https://x.com/a", PAGE))
    source = web.url_source("https://x.com/a", "The role of AI")
    assert (source["state"], source["http_status"], source["browser"]) == ("confirmed", 200, True)
    assert "a plain request got HTTP 403" in source["note"]


def test_browser_can_show_a_blocked_page_is_gone(monkeypatch):
    fetches(monkeypatch, (403, "https://x.com/a", None), (404, "https://x.com/a", b"<html></html>"))
    assert web.url_source("https://x.com/a", "The role of AI")["state"] == "missing"


def test_page_blocking_the_browser_too_stays_failed(monkeypatch):
    fetches(monkeypatch, (403, "https://x.com/a", None), (403, "https://x.com/a", b"<html>denied</html>"))
    source = web.url_source("https://x.com/a", "The role of AI")
    assert (source["state"], source["browser"]) == ("failed", False)


def test_javascript_page_is_rendered(monkeypatch):
    fetches(monkeypatch, (200, "https://x.com/a", SHELL), (200, "https://x.com/a", PAGE))
    assert web.url_source("https://x.com/a", "The role of AI")["title_on_page"] == "heading"


def test_readable_page_needs_no_browser(monkeypatch):
    calls = fetches(monkeypatch, (200, "https://x.com/a", PAGE), None)
    assert web.url_source("https://x.com/a", "The role of AI")["browser"] is False
    assert calls == []


def test_without_a_browser_the_plain_answer_stands(monkeypatch):
    fetches(monkeypatch, (403, "https://x.com/a", None), None)
    assert web.url_source("https://x.com/a", "The role of AI")["state"] == "failed"
