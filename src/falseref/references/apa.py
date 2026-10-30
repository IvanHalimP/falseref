"""Regex parser for APA references. Used when GROBID is unavailable, and for
pasted reference lists, where GROBID folds corporate authors ("AACA",
"Stanford Human-Centered AI") into the venue and truncates long URLs."""

import re

from ..models import Reference
from .text import find_url, locator

NAME = re.compile(r"([A-Z][A-Za-z'\-]+),\s*((?:[A-Z]\.\s*)+)")


def parse_entry(entry):
    """One APA reference string -> Reference. Other styles yield only the
    raw text and locator."""
    m = re.match(
        r"(?P<authors>.+?)\((?P<year>n\.d\.|\d{4}[a-z]?)(?:,[^)]*)?\)\.\s*(?P<rest>.*)",
        entry,
        re.S,
    )
    if not m:
        return Reference(raw=entry, **locator(entry))

    doi = re.search(r"\b10\.\d{4,9}/\S+", entry)
    url = find_url(entry)

    auth_raw = re.sub(r"[\s(]+$", "", m.group("authors"))
    names = [f"{initials.strip()} {surname}" for surname, initials in NAME.findall(auth_raw)]

    rest = re.sub(r"https?://.*", "", m.group("rest"), flags=re.S).strip()
    chunks = [c.strip() for c in re.split(r"\.\s+", rest) if c.strip()]

    return Reference(
        raw=entry,
        authors=names or ([auth_raw.rstrip(".")] if auth_raw else []),
        title=chunks[0].rstrip(".") if chunks else None,
        year=m.group("year"),
        venue=chunks[1].split(",")[0].strip(" .;") if len(chunks) > 1 else None,
        doi_or_url=f"https://doi.org/{doi.group(0)}" if doi else url,
        **locator(entry),
    )


def parse_reference_text(text):
    """Blank-line-separated entries -> [Reference]. Every entry ends in its URL
    and copy-paste wraps the long ones, so whitespace from the URL onward is
    closed up first."""
    refs = []
    for entry in re.split(r"\n\s*\n", text.strip()):
        entry = re.sub(r"\s+", " ", entry).strip()
        if not entry:
            continue
        m = re.search(r"https?://", entry)
        if m:
            entry = entry[: m.start()] + re.sub(r"\s+", "", entry[m.start():])
        refs.append(parse_entry(entry))
    return refs
