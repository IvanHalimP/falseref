"""Tier rules, with the network lookups replaced by canned Sources."""

import pytest

from falseref.models import Reference
from falseref.verdict import decide
from falseref.verdict.citation import citation_issues, looks_grey
from falseref.verdict.genai import genai_tool

ARTICLE = Reference(raw="Kumar, A. (2020). Deep learning for credit risk. Expert Systems, 7, 1-10.",
                    authors=["A. Kumar"], title="Deep learning for credit risk", year="2020",
                    venue="Expert Systems", volume="7", pages="1-10")
REC = {"title": ["Deep learning for credit risk"], "author": [{"given": "Anna", "family": "Kumar"}],
       "issued": {"date-parts": [[2020]]}, "container-title": ["Expert Systems"], "volume": "7", "page": "1-10"}

NOT_GIVEN_DOI = {"name": "DOI", "state": "not given", "note": "no DOI in the reference"}
NOT_GIVEN_URL = {"name": "URL", "state": "not given", "note": "no URL in the reference"}


def stub(monkeypatch, doi=NOT_GIVEN_DOI, url=NOT_GIVEN_URL, title=None):
    title = title or {"name": "title", "state": "missing", "note": "title search: no match"}
    monkeypatch.setattr(decide, "doi_source", lambda _: doi)
    monkeypatch.setattr(decide, "url_source", lambda *_: url)
    monkeypatch.setattr(decide, "title_source", lambda *_: title)


def test_title_search_hit_that_matches_is_verified(monkeypatch):
    stub(monkeypatch, title={"name": "title", "state": "confirmed", "rec": REC})
    assert decide.check_reference(ARTICLE).tier == "verified"


def test_found_work_with_wrong_volume_is_partial(monkeypatch):
    stub(monkeypatch, title={"name": "title", "state": "confirmed", "rec": {**REC, "volume": "9"}})
    result = decide.check_reference(ARTICLE)
    assert result.tier == "partial"
    assert ("locator", "major", "volume: 7 vs 9") in result.issues


def test_unregistered_doi_and_nothing_else_is_none(monkeypatch):
    ref = Reference(raw=ARTICLE.raw + " https://doi.org/10.1/fake", **{
        k: getattr(ARTICLE, k) for k in ("authors", "title", "year", "venue")})
    stub(monkeypatch, doi={"name": "DOI", "state": "missing", "note": "not registered"})
    result = decide.check_reference(ref)
    assert result.tier == "none"
    assert ("doi", "major", "DOI 10.1/fake is not registered") in result.issues


def test_failed_search_is_inconclusive(monkeypatch):
    stub(monkeypatch, title={"name": "title", "state": "failed", "note": "Crossref HTTP 503"})
    assert decide.check_reference(ARTICLE).tier == "inconclusive"


def test_page_showing_the_cited_title_is_verified(monkeypatch):
    ref = Reference(raw="IBM. (2024). The role of AI. https://ibm.com/blog/role-of-ai",
                    authors=["IBM"], title="The role of AI", year="2024",
                    doi_or_url="https://ibm.com/blog/role-of-ai")
    stub(monkeypatch, url={"name": "URL", "state": "confirmed", "http_status": 200, "rec": None,
                           "title_on_page": "heading", "page_title": "The role of AI | IBM",
                           "final_url": ref.doi_or_url, "note": "page has no bibliographic metadata"})
    assert decide.check_reference(ref).tier == "verified"


def test_dead_url_is_none(monkeypatch):
    ref = Reference(raw="X. (2024). Gone. https://x.com/gone", title="Gone", doi_or_url="https://x.com/gone")
    stub(monkeypatch, url={"name": "URL", "state": "missing", "http_status": 404, "note": "URL returns HTTP 404"})
    result = decide.check_reference(ref)
    assert result.tier == "none"
    assert ("url", "major", "URL returns HTTP 404") in result.issues


def test_grey_literature_not_found_is_flagged_for_a_person(monkeypatch):
    book = Reference(raw="Daly, A. (2023). Good data. ANU Press.", authors=["A. Daly"],
                     title="Good data", year="2023", venue="Australian National University Press")
    stub(monkeypatch)
    result = decide.check_reference(book)
    assert result.tier == "none"
    assert any("grey literature" in n for n in result.notes)


def test_genai_reference_is_not_looked_up(monkeypatch):
    def boom(*_):
        raise AssertionError("GenAI references must not be looked up")
    for name in ("doi_source", "url_source", "title_source"):
        monkeypatch.setattr(decide, name, boom)
    ref = Reference(raw="OpenAI. (2024). ChatGPT [Large language model]. https://chatgpt.com/share/abc",
                    doi_or_url="https://chatgpt.com/share/abc")
    assert decide.check_reference(ref).tier == "genai"


@pytest.mark.parametrize("raw, title, url, tool", [
    ("OpenAI. (2024). ChatGPT. https://chatgpt.com/c/1", "ChatGPT", "https://chatgpt.com/c/1", "ChatGPT"),
    ("Anthropic. (2025). Claude [Large language model].", "Claude", None, "Claude"),
    ("OpenAI. (2024). ChatGPT (May 13 version).", "ChatGPT (May 13 version)", None, "ChatGPT"),
    ("OpenAI. (2024). Introducing ChatGPT. https://openai.com/blog/chatgpt", "Introducing ChatGPT",
     "https://openai.com/blog/chatgpt", None),  # a vendor's blog post is a web page
])
def test_genai_tool(raw, title, url, tool):
    assert genai_tool(Reference(raw=raw, title=title), url) == tool


def test_citation_issues():
    ref = Reference(raw="", venue="IEEE Xplore", doi_or_url="https://www.researchgate.net/publication/1")
    issues = citation_issues(ref)
    assert any("database/platform (IEEE Xplore)" in i for i in issues)
    assert any("sharing platform (researchgate.net)" in i for i in issues)
    assert citation_issues(Reference(raw="", doi_or_url="https://aaca.org.au")) == [
        "links to a bare domain, not to the page holding the work"]


def test_looks_grey():
    assert looks_grey(Reference(raw=""))  # no venue
    assert looks_grey(Reference(raw="", venue="Oxford University Press"))
    assert not looks_grey(Reference(raw="", title="A study", venue="Nature"))
