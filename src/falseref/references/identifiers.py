"""The DOI and URL a reference gives."""

import re

from .text import rejoin_urls

DOI_TEXT = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+")
LINK = re.compile(r"https?://\S+|(?<![\w.])www\.\S+")


def doi_of(url):
    """DOI in a doi.org link, or in a publisher URL that embeds one. Other
    publishers' URLs carry the DOI itself, which the parsers already pick up."""
    if "doi.org/" in url:
        return url.split("doi.org/")[-1]
    m = re.search(r"nature\.com/articles/(s\d{5}-\d{3}-\d{4,5}-\w)", url)
    return f"10.1038/{m.group(1)}" if m else None


def cited_links(ref):
    """-> (DOI, URL) the reference gives. The parsers keep only one of the two
    in doi_or_url, so both are read from the raw entry as well."""
    raw = rejoin_urls(ref.raw or "")
    links = [u.rstrip(".,;") for u in LINK.findall(raw)]
    links = [u if u.startswith("http") else "https://" + u for u in links]
    links += [ref.doi_or_url] if ref.doi_or_url else []
    doi = next((doi_of(u) for u in links if doi_of(u)), None)
    if not doi:  # "doi:10.1016/..." written without a link
        m = DOI_TEXT.search(LINK.sub(" ", raw))
        doi = m.group(0) if m else None
    url = next((u for u in links if "doi.org/" not in u), None)
    return (doi.rstrip(".,;") if doi else None), url
