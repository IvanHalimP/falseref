"""Cuts a PDF's reference list into entries from the page layout rather than
from APA's "Author. (Year)." head, so any referencing style works: numbered
lists ([1], 1.), hanging indents, or entries separated by vertical space."""

import re
import statistics

import pymupdf

from .text import rejoin_urls

HEADING = re.compile(r"(?i)^[ \t]*(references?|reference list|bibliography|works cited)[ \t]*:?[ \t]*$")
END = re.compile(r"(?i)^[ \t]*(appendix|appendices|acknowledg\w*)\b")
NUMBERED = re.compile(r"^\s*(\[\d{1,3}\]|\d{1,3}[.)])\s+")
BULLET = re.compile(r"^\s*[•▪◦●]\s*")
YEAR = re.compile(r"\b(1[89]|20)\d{2}\b|n\.d\.")
URLISH = re.compile(r"https?://|www\.|\b10\.\d{4,9}/")


def section_lines(pdf):
    """(page, x0, y0, y1, text) for each line between the last reference heading
    and the next section heading. Running headers and footers are dropped."""
    lines = []
    for page in pymupdf.open(pdf):
        h = page.rect.height
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                text = "".join(s["text"] for s in l["spans"]).strip()
                x0, y0, _, y1 = l["bbox"]
                if text and 0.07 * h < y0 < 0.92 * h:
                    lines.append((page.number, x0, y0, y1, text))
    heads = [i for i, l in enumerate(lines) if HEADING.match(l[4])]
    if not heads:
        return []
    body = lines[heads[-1] + 1:]
    stop = next((i for i, l in enumerate(body) if END.match(l[4])), len(body))
    return body[:stop]


def entry_starts(lines):
    """Which lines open an entry: numbering if the list has it, else a hanging
    indent, else a gap wider than the normal line spacing (or a new page)."""
    if sum(bool(NUMBERED.match(l[4])) for l in lines) >= 2:
        return [bool(NUMBERED.match(l[4])) for l in lines]
    left = min(l[1] for l in lines)
    flush = [l[1] <= left + 8 for l in lines]
    if not all(flush):
        return flush
    gaps = sorted(b[2] - a[3] for a, b in zip(lines, lines[1:]) if a[0] == b[0])
    line_gap = statistics.median(gaps[: max(1, len(gaps) // 2)]) if gaps else 0
    return [True] + [b[0] != a[0] or b[2] - a[3] > line_gap + 4 for a, b in zip(lines, lines[1:])]


def continues(prev, text):
    """A piece split off by a stray paragraph break, not a new entry: it starts
    lowercase or with a URL, the previous entry stopped mid-sentence, or it has
    neither a year nor a link of its own ("Architectural Science Review.")."""
    return (
        text[:1].islower() or bool(URLISH.match(text))
        or not re.search(r"[.)\]]$|/$|https?://\S+$", prev)
        or not (YEAR.search(text) or URLISH.search(text))
    )


def layout_entries(pdf):
    """-> raw reference strings, [] when the PDF has no reference heading."""
    lines = [l for l in section_lines(pdf) if not BULLET.fullmatch(l[4])]
    if not lines:
        return []
    chunks = []
    for start, l in zip(entry_starts(lines), lines):
        if start or not chunks:
            chunks.append(l[4])
        else:
            chunks[-1] += " " + l[4]
    entries = []
    for c in chunks:
        c = rejoin_urls(NUMBERED.sub("", BULLET.sub("", c)))  # so a wrapped URL reads as an ending
        if entries and continues(entries[-1], c):
            entries[-1] += " " + c
        elif YEAR.search(c) or URLISH.search(c):  # drops template text before the list
            entries.append(c)
    return [rejoin_urls(e) for e in entries]
