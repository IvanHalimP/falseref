"""Reading references out of a document: PDF -> [Reference]."""

import logging
import re

from .apa import parse_entry, parse_reference_text
from .grobid import grobid_references, parse_citation
from .layout import layout_entries

__all__ = ["parse_references", "parse_reference_text"]

log = logging.getLogger(__name__)

# GROBID drops some fonts' ligatures: "https" comes out as "hOps", "predictive"
# as "predic:ve". PyMuPDF reads the same PDFs correctly.
LIGATURE_LOSS = re.compile(r"\bhOps?://|[a-z]:[a-z]{2}")


def parse_references(pdf):
    """-> ([Reference], method). Cut entries from the layout and let GROBID
    parse each one. Without a reference heading, GROBID finds the list itself.
    Without GROBID, the regex parser takes over, but it reads APA only."""
    entries = layout_entries(pdf)
    try:
        if entries:
            return [parse_citation(e) for e in entries], "layout+grobid"
        refs = grobid_references(pdf)
        if not any(LIGATURE_LOSS.search(r.raw) for r in refs):
            return refs, "grobid"
        log.warning("GROBID lost ligatures (hOps://, predic:ve) and no reference heading was found")
        return [], "none"
    except Exception as exc:
        log.warning("GROBID unavailable (%s), falling back to regex", type(exc).__name__)
    return [parse_entry(e) for e in entries], "layout+regex"
