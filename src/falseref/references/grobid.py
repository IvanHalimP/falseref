"""GROBID client: finds the reference list in a PDF, and parses one reference
string into fields. Expects a GROBID server at GROBID_URL (default
http://localhost:8070, override with the GROBID_URL environment variable)."""

import os
import re

import requests
from lxml import etree

from ..models import Reference
from .text import find_url, locator, rejoin_urls

GROBID_URL = os.environ.get("GROBID_URL", "http://localhost:8070")
TEI = {"t": "http://www.tei-c.org/ns/1.0"}

# GROBID fuses consecutive website references into one entry, so split its raw
# strings on the APA entry head "Author. (Year)." and re-parse each piece.
# The date may carry a month and day, or be "n.d.": (2024). (2023, October 9). (n.d.).
DATE = r"\((?:n\.d\.|\d{4}[a-z]?(?:,\s*[A-Za-z]+\.?(?:\s+\d{1,2})?)?)\)"
# A name token is a word or initials ("A.", "K.-H.", "Jr."). Only initials and
# short abbreviations may carry a period, so a venue closing the previous entry
# ("... architecture. Architectural Science Review. Daly, A. (2023).") is not
# swallowed into the next author list.
TOKEN = r"(?:[A-Z][a-z]{0,2}\.(?:-?[A-Z][a-z]?\.)*|[A-Z][A-Za-z'\-]*)"
# Lowercase joiners inside corporate and particle names: "Office of the
# Australian Information Commissioner", "Terri Janke and Company", "van der Berg".
JOIN = r"(?:of|the|and|for|on|in|de|del|der|van|von|du|da|la|le)\b"
HEAD = re.compile(r"(?<![\w.'\-])" + TOKEN + r"(?:[,;&]?\s+(?:" + TOKEN + "|&|" + JOIN + r"))*\.\s*" + DATE + r"\.")
FOOTER = re.compile(r"\|?\s*P a g e\b\s*\d*")  # Word footers: "| P a g e 12"
HEADING_WORDS = re.compile(r"(?i)^(reference list|references?|bibliography|works cited)\s*:?\s+")


def split_entries(raw):
    """Cut a run of APA references at each "Author. (Year)." head."""
    raw = rejoin_urls(FOOTER.sub(" ", raw))
    starts, end = [], -1
    for m in HEAD.finditer(raw):
        if m.start() >= end:
            starts.append(m.start())
            end = m.end()
    if not starts:
        return [raw.strip()]
    pieces = [raw[a:b].strip() for a, b in zip(starts, starts[1:] + [len(raw)])]
    # a heading that sits right before an entry ("References IEEE. (2022).")
    return [HEADING_WORDS.sub("", p) for p in pieces]


def as_written(name, entry):
    """GROBID recases names ("MDPI" -> "Mdpi", "GE Digital" -> "Ge Digital");
    take the entry's spelling where the name appears in it verbatim."""
    m = re.search(re.escape(name), entry, re.I)
    return m.group(0) if m else name


def parse_citation(entry):
    """One raw reference string -> Reference. processCitation returns a bare
    biblStruct with no namespace, so plain tag names are used here."""
    r = requests.post(f"{GROBID_URL}/api/processCitation", data={"citations": entry})
    bib = etree.fromstring(r.text.encode())

    analytic = bib.findtext(".//analytic/title[@level='a']")
    journal = bib.findtext(".//monogr/title[@level='j']")
    mono = bib.findtext(".//monogr/title[@level='m']")
    publisher = bib.findtext(".//publisher")

    doi = bib.findtext(".//idno[@type='DOI']")
    ptr = bib.find(".//ptr")
    # GROBID truncates URLs at a wrapped hyphen and glues on the next words
    # ("...guidelinesPrivacyAct"); the entry text already has them rejoined.
    url = find_url(entry) or (ptr.get("target") if ptr is not None else None)
    # corporate authors sometimes land in respStmt/orgName instead of author
    authors = [" ".join(p.itertext()).strip() for p in bib.findall(".//author/persName")]
    authors = authors or [o.text.strip() for o in bib.findall(".//respStmt/orgName") if o.text]
    authors = [as_written(a, entry) for a in authors]

    # GROBID misreads dates like "(2023, October 9)" as 2009, and returns full
    # dates elsewhere, so take the year from the entry text when it has one.
    date = bib.find(".//date")
    in_text = re.search(r"\((n\.d\.|\d{4})", entry)
    grobid_year = (date.get("when") or "")[:4] if date is not None else None
    year = in_text.group(1) if in_text else (grobid_year or None)

    # MLA, Chicago and IEEE put article titles in quotes, which GROBID can miss;
    # a date with no closing period leaves ") Title" behind.
    quoted = re.search(r"[“\"]([^”\"]{3,})[”\"]", entry)
    # GROBID can leave a short title untagged ("Direct marketing" lands in a
    # bare <note>); in APA the title is the sentence right after "(date)."
    after = re.search(DATE + r"\.\s*(.+?)(?:\.\s|\.?\s*(?:https?://|www\.)|\.?\s*$)", entry)
    title = analytic or mono or (quoted.group(1).strip(" .,") if quoted else None) or (after.group(1) if after else None)
    title = re.sub(r"^[^\w“\"'(\[]+", "", title) if title else None

    loc = locator(entry)
    if not any(loc.values()):  # other styles: "vol. 5, no. 2, pp. 1-10"
        page = bib.find(".//biblScope[@unit='page']")
        loc = {
            "volume": bib.findtext(".//biblScope[@unit='volume']"),
            "issue": bib.findtext(".//biblScope[@unit='issue']"),
            "pages": None if page is None else
                     "-".join(filter(None, (page.get("from"), page.get("to")))) or page.text,
        }

    return Reference(
        raw=entry,
        authors=authors,
        title=title,
        year=year,
        venue=journal or (mono if analytic else None) or publisher,
        doi_or_url=f"https://doi.org/{doi}" if doi else url,
        **loc,
    )


def grobid_references(pdf, timeout=60):
    """GROBID finds the reference list itself; used when the PDF has no
    reference heading for the layout reader to start from."""
    with open(pdf, "rb") as f:
        resp = requests.post(
            f"{GROBID_URL}/api/processReferences",
            files={"input": f},
            data={"includeRawCitations": "1"},
            timeout=timeout,
        )
    resp.raise_for_status()
    root = etree.fromstring(resp.text.encode())
    raws = [
        n.text for n in root.findall(".//t:biblStruct/t:note[@type='raw_reference']", TEI)
    ]
    # GROBID both fuses entries and splits single ones across records, so join
    # everything back together and cut it on APA entry heads instead. Other
    # styles have no such head, so keep GROBID's own segmentation for them.
    joined = re.sub(r"\s+", " ", " ".join(raws)).strip()
    if HEAD.search(joined):
        entries = split_entries(joined)
    else:
        entries = [rejoin_urls(re.sub(r"\s+", " ", r).strip()) for r in raws]
    return [parse_citation(e) for e in entries]
