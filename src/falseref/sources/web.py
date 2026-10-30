"""Web-source authentication: does the cited URL load, does the page show the
cited title, and what do its bibliographic <meta> tags say. Pages a plain
request cannot read are retried in a browser (see browser). Returns a Source
(see models)."""

import re
from urllib.parse import urlparse

import lxml.html
import pymupdf

from ..matching import norm
from ..references.identifiers import DOI_TEXT
from .browser import render
from .http import fetch_page

# What a URL's HTTP status says, recorded per reference so blocked, login-only
# and dead links can be told apart. A 200 is not proof the work is there: it
# can be a CAPTCHA or "are you human?" page standing in for it.
HTTP_MEANING = {401: "login required", 403: "forbidden (blocked?)", 404: "not found",
                410: "gone", 429: "rate limited"}


def http_meaning(code):
    if code in HTTP_MEANING:
        return HTTP_MEANING[code]
    if code >= 500:
        return "server error"
    if code >= 400:
        return "client error"
    return "redirect not followed" if code >= 300 else "ok"


def page_info(markup):
    """<title>, headings, body text and link text of a page, normalised."""
    if markup[:5] == b"%PDF-":
        # first two pages only, where the title sits: a PDF that merely cites
        # the title in its reference list must not count as holding the work
        pdf = pymupdf.open(stream=markup, filetype="pdf")
        title = (pdf.metadata or {}).get("title") or None
        text = " ".join(p.get_text() for p in pdf.pages(0, min(2, pdf.page_count)))
        return {"title": title, "heads": [norm(title)] if title else [], "text": norm(text), "links": ""}
    doc = lxml.html.fromstring(markup)
    for el in doc.xpath("//script|//style|//noscript"):
        el.drop_tree()
    title = re.sub(r"\s+", " ", doc.findtext(".//title") or "").strip() or None
    heads = [title or ""] + [h.text_content() for h in doc.iter("h1")]
    heads += doc.xpath("//meta[@property='og:title']/@content")
    links = " ".join(a.text_content() for a in doc.iter("a"))
    for a in doc.xpath("//a"):
        a.drop_tree()
    return {"title": title, "heads": [norm(h) for h in heads if h],
            "text": norm(doc.text_content()), "links": norm(links)}


def find_title(title, info):
    """Where the cited title sits on the page: 'heading' (<title>, <h1>,
    og:title), 'text', 'link' (only as link text, e.g. a hub page listing it)
    or None. Exact after normalising, so a changed word is not waved through.
    Headings carry site suffixes ("X | IBM") and GROBID glues the site name
    onto the cited title, so containment either way counts for those."""
    t = norm(title)
    if not (t and info):
        return None
    if any(t in h or (h in t and len(h.split()) >= 3) for h in info["heads"]):
        return "heading"
    if t in info["text"]:
        return "text"
    return "link" if t in info["links"] else None


def meta_record(markup):
    """A page's bibliographic <meta> tags as a Crossref-shaped record, or None.
    citation_* is the Highwire set Google Scholar reads: publishers,
    repositories and university pages carry it; some use Dublin Core."""
    meta = {}
    for m in lxml.html.fromstring(markup).xpath("//meta[@content]"):
        key, value = (m.get("name") or m.get("property") or "").lower(), m.get("content").strip()
        if value:
            meta.setdefault(key, []).append(value)

    def first(*keys):
        return next((meta[k][0] for k in keys if k in meta), None)

    title = first("citation_title", "dc.title")
    if not title:
        return None
    people = []
    for name in meta.get("citation_author") or meta.get("dc.creator") or []:
        # "Smith, John" or "John Smith"
        family, _, given = name.partition(",") if "," in name else name.rpartition(" ")[::-1]
        people.append({"family": family.strip(), "given": given.strip()})
    year = re.search(r"\b(?:1[89]|20)\d{2}\b", first(
        "citation_publication_date", "citation_date", "citation_online_date", "dc.date") or "")
    doi = DOI_TEXT.search(first("citation_doi", "prism.doi", "dc.identifier") or "")
    pages = "-".join(filter(None, (first("citation_firstpage"), first("citation_lastpage"))))
    return {
        "title": [title],
        "author": people,
        "issued": {"date-parts": [[int(year.group(0)) if year else None]]},
        "container-title": [first("citation_journal_title", "citation_conference_title",
                                  "citation_book_title", "dc.source") or ""],
        "DOI": doi.group(0) if doi else None,
        "volume": first("citation_volume"),
        "issue": first("citation_issue"),
        "page": pages or None,
    }


def blocked(code):
    """No answer, or one that says nothing about the page: a bot filter, a
    rate limit or an outage. Publishers routinely block automated requests."""
    return code is None or code in (403, 429) or code >= 500


def read_page(url, title):
    """-> (status, final url, markup, how). A plain request first, then a
    browser if the site turned the request away, or served HTML that does not
    show the cited title (its text may be rendered by JavaScript). The
    browser's answer is kept only when it says more; how then says so."""
    code, final, markup = fetch_page(url)
    unshown = (title and code is not None and code < 400 and markup and markup[:5] != b"%PDF-"
               and find_title(title, page_info(markup)) not in ("heading", "text"))
    if not (blocked(code) or unshown):
        return code, final, markup, None
    rendered = render(url)
    if not rendered or blocked(rendered[0]) or (unshown and rendered[0] >= 400):
        return code, final, markup, None
    if blocked(code):
        how = f"read with a browser (a plain request got {f'HTTP {code}' if code else final})"
    else:
        how = "read with a browser, which runs the page's JavaScript"
    return *rendered, how


def url_source(url, title):
    if not url:
        return {"name": "URL", "state": "not given", "note": "no URL in the reference"}
    if not urlparse(url).path.strip("/"):
        # every live site answers 200 at its root, whatever the reference claims
        return {"name": "URL", "state": "not checked",
                "note": f"URL {url} is a bare domain, so it says nothing about the work"}
    code, final, markup, how = read_page(url, title)
    seen = {"name": "URL", "http_status": code, "final_url": final if code else None,
            "http_meaning": http_meaning(code) if code else f"request failed ({final})", "browser": bool(how)}
    if code is None:
        return {**seen, "state": "failed", "note": f"URL request failed ({final})"}
    if blocked(code):
        # absence of proof only
        return {**seen, "state": "failed", "note": f"URL blocked or unavailable (HTTP {code}), page not read"}
    if code >= 400:
        return {**seen, "state": "missing", "note": "; ".join(filter(None, (f"URL returns HTTP {code}", how)))}
    if not markup:
        return {**seen, "state": "unconfirmed", "note": "URL loads but is not an HTML or PDF page, so it was not read"}
    info = page_info(markup)
    where = find_title(title, info)
    rec = meta_record(markup) if markup[:5] != b"%PDF-" else None
    notes = [how] if how else []
    # sites retire a page and redirect its URL to a hub or home page
    seg = [s for s in urlparse(url).path.split("/") if s]
    site = urlparse(final).netloc.lower().removeprefix("www.")
    if where is None and seg and len(norm(title)) >= 3 and norm(title).replace(" ", "") in site \
            and find_title(seg[-1], info) == "heading":
        # the reference names the site as its title ("Keyway". Keyway.ai, 2025,
        # URL): the URL alone identifies the work, and the page's headline is it
        where = "slug"
    moved = bool(seg) and seg[-1].lower() not in urlparse(final).path.lower()
    if moved:
        notes.append(f"URL redirects off the cited page to {final}")
    if where == "link":
        notes.append("cited title appears on the page only as link text (a listing page?)")
    elif where is None:
        notes.append(f"cited title not found on the page (page title: {info['title']!r}; "
                     "pages rendered by JavaScript can hide their text)")
    if rec is None:
        notes.append("page has no bibliographic metadata")
    return {**seen, "state": "confirmed" if rec or where in ("heading", "text", "slug") else "unconfirmed",
            "moved": moved and where not in ("heading", "text", "slug"), "rec": rec,
            "title_on_page": where, "page_title": info["title"], "note": "; ".join(notes) or None}
