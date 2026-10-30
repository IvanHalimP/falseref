"""Data shapes shared across the package.

Reference       one entry of a reference list, as parsed from the document.
Record          what an index or a web page says about a work. A plain dict in
                Crossref's shape, because Crossref returns it that way and the
                other sources (OpenAlex, doi.org, page <meta> tags) are reshaped
                into it, so one comparison serves them all:
                    {"title": [str], "author": [{"given", "family"}],
                     "issued": {"date-parts": [[year]]}, "container-title": [str],
                     "DOI", "volume", "issue", "page", "article-number"}
Source          the outcome of one lookup (DOI, URL or title search), a dict:
                    name   "DOI", "URL", "title" or "GenAI"
                    state  "confirmed"   evidence the work exists
                           "unconfirmed" reached, but nothing about the work
                           "missing"     evidence against: unregistered DOI,
                                         dead URL, no search hit
                           "failed"      could not be checked
                           "not checked" / "not given"
                    rec    the Record it found, if any
                    note   why, for the report
                URL sources also carry http_status, http_meaning, final_url,
                title_on_page, page_title and moved.
Issue           one discrepancy between the reference and the record.
CheckResult     the verdict on one reference.
DocumentReport  the references of one document and their verdicts.
"""

from dataclasses import dataclass, field
from typing import NamedTuple

# "partial" means the work was found but is cited with errors; a work that
# nothing shows to exist is never partial.
TIERS = {
    "verified": "✅ Verified",
    "partial": "⚠️  Exists, citation errors",
    "none": "\U0001f6a9 No match found",
    "inconclusive": "❓ Inconclusive",
    "genai": "\U0001f916 GenAI tool",
}


@dataclass
class Reference:
    raw: str
    authors: list[str] = field(default_factory=list)
    title: str | None = None
    year: str | None = None
    venue: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi_or_url: str | None = None  # the parsers keep one link; see references.identifiers


class Issue(NamedTuple):
    field: str  # "title", "authors", "year", "venue", "locator", "doi" or "url"
    severity: str  # "major" or "minor"
    message: str


@dataclass
class CheckResult:
    tier: str  # a key of TIERS
    doi: str | None  # the DOI the reference gives
    url: str | None  # the URL the reference gives
    sources: list[dict]  # one Source per lookup
    rec: dict  # the Record summed from the sources that found the cited work
    issues: list[Issue]
    notes: list[str]  # what could not be found or confirmed
    citation: list[str]  # citation-quality problems that never change the tier

    @property
    def label(self):
        return TIERS[self.tier]


@dataclass
class DocumentReport:
    name: str
    method: str  # how references were read, e.g. "layout+grobid"
    references: list[Reference]
    results: list[CheckResult]


# Record accessors. Fields may be missing or empty in any source.

def rec_title(rec):
    return (rec.get("title") or [""])[0]


def rec_venue(rec):
    return (rec.get("container-title") or [""])[0]


def rec_year(rec):
    parts = (rec.get("issued") or {}).get("date-parts") or [[None]]
    return str(parts[0][0]) if parts[0] and parts[0][0] else None


def rec_locator(rec):
    return {"volume": rec.get("volume"), "issue": rec.get("issue"),
            "pages": rec.get("page") or rec.get("article-number")}


def show(author):
    """A record author as "Given Family"."""
    return f"{author.get('given') or ''} {author['family']}".strip()


def describe(rec):
    """One line naming a record, for notes: title (authors; year; DOI)."""
    names = ", ".join(show(a) for a in rec.get("author", [])[:3] if a.get("family"))
    return f"{rec_title(rec)!r} ({names}; {rec_year(rec)}; DOI {rec.get('DOI')})"
