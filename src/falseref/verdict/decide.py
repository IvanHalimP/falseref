"""The verdict on one reference.

Every identifier a reference gives is checked, not just one of them:
  DOI   -> Crossref, or doi.org for DataCite DOIs (arXiv, Zenodo)
  URL   -> the live page: does it load, does it show the cited title, and
           what its bibliographic <meta> tags say (title, authors, DOI, ...)
  title -> Crossref + OpenAlex search
What they find about the cited work is summed into one record, and the cited
authors, title, year, venue, volume/issue/pages, DOI and URL are compared
with it. Anything that could not be found goes in the notes.

The tier answers two questions in turn: does the cited work exist, and is it
cited correctly?"""

from ..matching import compare, major_count, ratio, title_issues
from ..models import CheckResult, Issue, describe, rec_title, rec_year
from ..references.identifiers import cited_links
from ..sources import doi_source, title_source, url_source
from .citation import citation_issues, looks_grey
from .genai import genai_tool

RECORD_KEYS = ("title", "author", "issued", "container-title", "DOI", "volume", "issue", "page", "article-number")
# cited field -> record key, for "the reference states it, no source has it"
CONFIRMS = {"title": "title", "authors": "author", "year": "issued", "venue": "container-title",
            "volume": "volume", "issue": "issue", "pages": "page"}
ON_PAGE = ("heading", "text")  # where a page showing the cited title shows it


def has(rec, key):
    if key == "issued":
        return bool(rec_year(rec))
    v = rec.get(key)
    return any(v) if isinstance(v, list) else bool(v)


def same_work(a, b):
    da, db = (a.get("DOI") or "").lower(), (b.get("DOI") or "").lower()
    return (da and da == db) or ratio(rec_title(a), rec_title(b)) >= 0.90


def retitled(ref, rec):
    """The record's title is not the cited one (a major title discrepancy)."""
    return any(sev == "major" for sev, _ in title_issues(ref.title, rec_title(rec)))


def check_reference(ref):
    """Reference -> CheckResult."""
    doi, url = cited_links(ref)
    tool = genai_tool(ref, url)
    if tool:
        return CheckResult(tier="genai", doi=doi, url=url, rec={}, issues=[], citation=[],
                           sources=[{"name": "GenAI", "state": "not checked"}],
                           notes=[f"GenAI tool reference ({tool}): output of a generative AI tool, "
                                  "not a published work, so it was not checked"])

    by_name = {s["name"]: s for s in (doi_source(doi), url_source(url, ref.title), title_source(ref, url))}
    page, hit = by_name["URL"], by_name["title"].get("rec")
    if page.get("title_on_page") in ON_PAGE and not page.get("rec") and hit and major_count(ref, hit):
        # the cited page holds the cited work, so a same-titled record that
        # disagrees with the reference is another version or a namesake
        by_name["title"] = {
            "name": "title", "state": "unconfirmed",
            "note": f"title search found a same-titled record that differs, not counted since the cited "
                    f"page holds the work: {describe(hit)}"}
    sources = list(by_name.values())
    notes = [s["note"] for s in sources if s.get("note")]
    issues = []

    # The work the reference describes is the record it matches best; the
    # identifiers are tried in the order DOI, title search, URL page.
    found = [by_name[n] for n in ("DOI", "title", "URL") if by_name[n].get("rec")]
    anchor = min(found, key=lambda s: major_count(ref, s["rec"]), default=None)
    rec = {}
    for s in found:
        other = f"{rec_title(s['rec'])!r} ({rec_year(s['rec'])})"
        if same_work(anchor["rec"], s["rec"]):
            for k in RECORD_KEYS:  # sum: each field from the first source that has it
                if not has(rec, k) and has(s["rec"], k):
                    rec[k] = s["rec"][k]
            # the only record found can still be the wrong work: a DOI or page
            # whose title has nothing to do with the cited one is itself wrong
            if s["name"] != "title" and ref.title and retitled(ref, s["rec"]):
                issues.append(Issue("doi" if s["name"] == "DOI" else "url", "major",
                                    f"the cited {s['name']} belongs to a different work: {other}"))
            continue
        if s["name"] == "DOI":
            issues.append(Issue("doi", "major", f"DOI {doi} belongs to a different work: {other}"))
        elif s["name"] == "URL":
            issues.append(Issue("url", "major", f"the cited page describes a different work: {other}"))
        else:
            notes.append(f"title search's best hit is a different work, ignored: {other}")

    if rec:
        issues += compare(ref, rec)[0]
    issues += identifier_issues(doi, url, by_name, rec, issues, notes)
    for f, key in CONFIRMS.items():
        on_page = f == "title" and page.get("title_on_page") in ON_PAGE
        if getattr(ref, f) and not has(rec, key) and not on_page and not (f == "pages" and rec.get("article-number")):
            notes.append(f"{f} not confirmed: no source lists it")

    tier = decide_tier(ref, by_name, anchor, issues, notes)
    return CheckResult(tier=tier, doi=doi, url=url, sources=sources, rec=rec,
                       issues=issues, notes=notes, citation=citation_issues(ref))


def identifier_issues(doi, url, by_name, rec, issues, notes):
    """-> new [Issue] about the cited DOI and URL themselves. Appends to notes."""
    out = []
    page = by_name["URL"]
    if doi and by_name["DOI"]["state"] == "missing":
        out.append(Issue("doi", "major", f"DOI {doi} is not registered"))
    elif doi and rec.get("DOI") and doi.lower() != rec["DOI"].lower() and not any(i.field == "doi" for i in issues):
        out.append(Issue("doi", "major", f"DOI: {doi} vs {rec['DOI']}"))  # DOIs are case-insensitive
    if not doi and rec.get("DOI"):
        notes.append(f"the work's DOI is {rec['DOI']}")
    if url and page["state"] == "missing":
        out.append(Issue("url", "major", f"URL returns HTTP {page['http_status']}"))
    elif page.get("moved"):
        out.append(Issue("url", "major", "URL redirects off the cited page, which no longer shows the work"))
    elif page["state"] == "unconfirmed" and "title_on_page" in page:  # page was read
        out.append(Issue("url", "minor", "the cited page does not show the cited work"))
    elif page.get("title_on_page") == "slug":
        out.append(Issue("title", "minor", f"the reference gives the site name as its title; "
                                           f"the page is titled {page['page_title']!r}"))
    return out


def decide_tier(ref, by_name, anchor, issues, notes):
    """-> tier key. Appends advice to notes."""
    page = by_name["URL"]
    major = [i.message for i in issues if i.severity == "major"]
    # First: does the cited work exist? Title search finds it by title (and
    # filters namesakes); a DOI or URL finds whatever it points to, which only
    # counts when that record carries the cited title.
    exists = page.get("title_on_page") in (*ON_PAGE, "slug") or bool(anchor) and (
        anchor["name"] == "title" or not ref.title or not retitled(ref, anchor["rec"]))
    # Then: is it cited correctly?
    if exists:
        # books reprint, so an edition-year gap is not evidence against a book
        if major and looks_grey(ref) and all(m.startswith("year:") for m in major):
            notes.append("year differs: reprint or later edition?")
            return "inconclusive"
        return "partial" if major else "verified"
    if "missing" in (by_name["DOI"]["state"], page["state"]) or page.get("moved") \
            or any(i.field in ("doi", "url") and i.severity == "major" for i in issues):
        # a cited identifier is dead, redirects off its page, or belongs to
        # another work, and nothing else found the cited one
        if page.get("moved"):
            notes.append("the page may have been retired: look for an archived copy")
        return "none"
    if {s["state"] for s in by_name.values()} & {"failed", "unconfirmed"}:
        return "inconclusive"
    if looks_grey(ref):  # still flagged: no source found it, so a person has to
        notes.append("book or grey literature: may exist outside Crossref/OpenAlex, check by hand")
    return "none"
