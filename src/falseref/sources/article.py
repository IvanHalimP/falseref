"""Academic-article authentication: the DOI a reference gives (Crossref, or
doi.org for DataCite DOIs such as arXiv and Zenodo), and a title search over
Crossref and OpenAlex. Each lookup returns a Source (see models)."""

import re
from urllib.parse import urljoin, urlparse

import requests

from ..matching import major_count, name_matches, norm, ratio, record_tokens, title_issues
from ..matching.similarity import surname
from ..models import describe, rec_title, rec_year
from .http import UA, get

CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"


class LookupFailed(Exception):
    """An index could not be searched (rate limit, outage), so finding nothing
    there is no evidence the work does not exist."""


# --- DOI ---------------------------------------------------------------------

def crossref_by_doi(doi):
    r = get(f"{CROSSREF}/{doi}")
    return r.json()["message"] if r.status_code == 200 else None


def doi_source(doi):
    if not doi:
        return {"name": "DOI", "state": "not given", "note": "no DOI in the reference"}
    try:
        rec = crossref_by_doi(doi)
        if rec:
            return {"name": "DOI", "state": "confirmed", "rec": rec}
        # doi.org serves CSL JSON for Crossref and DataCite DOIs alike
        r = requests.get(f"https://doi.org/{doi}", timeout=30,
                         headers={**UA, "Accept": "application/vnd.citationstyles.csl+json"})
    except requests.RequestException as exc:
        return {"name": "DOI", "state": "failed", "note": f"DOI {doi}: lookup failed ({type(exc).__name__})"}
    if r.status_code == 404:
        return {"name": "DOI", "state": "missing", "note": f"DOI {doi} is not registered at doi.org"}
    if r.status_code == 200 and "json" in r.headers.get("Content-Type", ""):
        rec = r.json()
        for k in ("title", "container-title"):  # strings in CSL, lists in Crossref
            if isinstance(rec.get(k), str):
                rec[k] = [rec[k]]
        return {"name": "DOI", "state": "confirmed", "rec": rec}
    return {"name": "DOI", "state": "failed",
            "note": f"DOI {doi}: no metadata could be read (HTTP {r.status_code})"}


def landing_pages(doi, hops=5):
    """URLs doi.org redirects a DOI to. Followed one hop at a time and kept
    as they come, because publishers drop the connection or demand cookies
    partway along."""
    url, pages = f"https://doi.org/{doi}", []
    for _ in range(hops):
        try:
            r = requests.head(url, headers=UA, timeout=20, allow_redirects=False)
        except requests.RequestException:
            break
        if not r.headers.get("Location"):
            break
        url = urljoin(url, r.headers["Location"])
        pages.append(url)
    return pages


def same_page(a, b):
    """Same host (with or without www.) and path; scheme, query and case aside."""
    a, b = urlparse(a), urlparse(b)
    return (a.netloc.lower().removeprefix("www.") == b.netloc.lower().removeprefix("www.")
            and a.path.rstrip("/").lower() == b.path.rstrip("/").lower())


def lands_on(doi, url):
    """Does the DOI resolve to the cited URL?"""
    return any(same_page(page, url) for page in landing_pages(doi))


# --- title search --------------------------------------------------------------

def crossref_candidates(title, authors=(), rows=5):
    params = {"query.bibliographic": norm(title), "rows": rows}
    if authors:  # scores only, not a filter: ranks the cited authors' work above namesakes
        params["query.author"] = " ".join(surname(a) for a in authors)
    r = get(CROSSREF, params=params)
    if r.status_code != 200:
        raise LookupFailed(f"Crossref HTTP {r.status_code}")
    return r.json()["message"]["items"]


def openalex_candidates(title, per_page=5):
    """OpenAlex results reshaped as Crossref records, so one comparison serves both."""
    r = get(OPENALEX, params={"search": norm(title), "per_page": per_page})
    if r.status_code != 200:
        raise LookupFailed(f"OpenAlex HTTP {r.status_code}")
    out = []
    for it in r.json().get("results", []):
        source = (it.get("primary_location") or {}).get("source") or {}
        biblio = it.get("biblio") or {}
        names = [(a.get("author") or {}).get("display_name") or "" for a in it.get("authorships", [])]
        out.append({
            "title": [it.get("title") or ""],
            "issued": {"date-parts": [[it.get("publication_year")]]},
            "author": [
                {"given": n.rpartition(" ")[0], "family": n.rpartition(" ")[2]} for n in names
            ],
            "container-title": [source.get("display_name") or ""],
            "DOI": (it.get("doi") or "").replace("https://doi.org/", "") or None,
            "volume": biblio.get("volume"),
            "issue": biblio.get("issue"),
            "page": "-".join(filter(None, (biblio.get("first_page"), biblio.get("last_page")))) or None,
        })
    return out


def best_match(ref):
    """Best candidate across both indexes, or None. A middling title match
    must be backed by a shared author, or a same-titled different paper wins.
    Raises LookupFailed when nothing matched and an index could not be searched."""
    if not ref.title:
        return None
    cands, failed = [], []
    for search, args in ((crossref_candidates, (ref.title, ref.authors)), (openalex_candidates, (ref.title,))):
        try:
            cands += search(*args)
        except (LookupFailed, requests.RequestException) as exc:
            failed.append(str(exc) or type(exc).__name__)
    scored = sorted(
        ((ratio(ref.title, rec_title(c)), c) for c in cands),
        key=lambda pair: pair[0],
        reverse=True,
    )
    accepted = [
        (score, rec) for score, rec in scored
        if score >= 0.90 or (score >= 0.70 and any(name_matches(n, record_tokens(rec)) for n in ref.authors))
    ]
    if accepted:
        # reposts and preprints share the title: take the record that agrees
        # most with the reference, then the closest title
        return min(accepted, key=lambda p: (major_count(ref, p[1]), -p[0]))[1]
    if failed:
        raise LookupFailed("; ".join(failed))
    return None


def title_source(ref, url=None):
    """url: the URL the reference gives, which can vouch for a hit."""
    if not ref.title:
        return {"name": "title", "state": "not given", "note": "no title could be parsed from the reference"}
    try:
        rec = best_match(ref)
    except LookupFailed as exc:
        return {"name": "title", "state": "failed", "note": f"title search incomplete ({exc})"}
    if rec is None:
        return {"name": "title", "state": "missing", "note": "title search: no Crossref or OpenAlex match"}
    # Short titles are shared by unrelated works ("Generative design in
    # architecture"), and a web page's title can also be some paper's. A hit
    # with none of the cited authors (or, without authors, another year) is a
    # namesake: report it, but do not judge the reference against it. So is a
    # hit by the same author whose title and year both differ: another of
    # their works, which an author-ranked search readily brings up.
    year = re.sub(r"\D", "", ref.year or "")[:4]
    shared = any(name_matches(n, record_tokens(rec)) for n in ref.authors)
    near = not (year and rec_year(rec)) or abs(int(year) - int(rec_year(rec))) <= 1
    retitled = any(sev == "major" for sev, _ in title_issues(ref.title, rec_title(rec)))
    namesake = (ref.authors and not shared) or (not near and (retitled or not ref.authors))
    if namesake and not retitled and url and rec.get("DOI") and lands_on(rec["DOI"], url):
        # ...unless the cited URL is the hit's own page: then the hit is the
        # cited work, and the reference names the wrong authors (often the
        # publisher, "MDPI. (2024).") or year, which the comparison reports
        return {"name": "title", "state": "confirmed", "rec": rec,
                "note": f"title search hit has other authors or year, but its DOI {rec['DOI']} "
                        "resolves to the cited URL, so it is the cited work"}
    if namesake:
        return {"name": "title", "state": "missing",
                "note": f"title search found only a different work (other authors, or another title and year), "
                        f"not counted: {describe(rec)}"}
    return {"name": "title", "state": "confirmed", "rec": rec}
