"""Citation-quality rules and source-type heuristics.

APA 7 section 9.30: works from academic databases and platforms are cited by
journal/proceedings and DOI, never by the database. Sharing platforms hold
preprints rather than the version of record. These are citation-quality
problems, not authenticity problems, so they never change the tier."""

import re
from urllib.parse import urlparse

DATABASE_NAMES = re.compile(
    r"(?i)\b(ieee\s*xplore|proquest|ebsco\w*|jstor|researchgate|academia\.edu|"
    r"semantic\s*scholar|google\s*scholar|springerlink|sciencedirect|scopus|"
    r"web\s+of\s+science|pubmed|scribd|slideshare)\b"
)
SHARING_HOSTS = ("researchgate.net", "academia.edu", "semanticscholar.org", "scribd.com")

# Sources Crossref/OpenAlex do not index well: books, theses, reports, standards.
GREY = re.compile(
    r"(?i)\b(press|publish\w*|university|report|thesis|dissertation|"
    r"white\s?paper|working\s?paper|handbook|book|edition|ed\.|"
    r"standard|guideline|act\b|bill\b)\b"
)


def citation_issues(ref):
    """-> [message] for citation-quality problems."""
    issues = []
    named = DATABASE_NAMES.search(ref.venue or "")
    if named:
        issues.append(
            f"venue is a database/platform ({named.group(0)}); "
            "APA 7 §9.30 wants the journal or proceedings name"
        )
    url = ref.doi_or_url or ""
    host = urlparse(url).netloc.lower().removeprefix("www.") if url else ""
    if any(host == h or host.endswith("." + h) for h in SHARING_HOSTS):
        issues.append(f"links to a sharing platform ({host}); cite the version of record")
    if url and not urlparse(url).path.strip("/"):
        issues.append("links to a bare domain, not to the page holding the work")
    return issues


def looks_grey(ref):
    """Book, report or other source the indexes are not expected to hold."""
    if not ref.venue:
        return True
    return bool(GREY.search(ref.venue) or GREY.search(ref.title or ""))
