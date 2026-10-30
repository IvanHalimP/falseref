"""End to end: an upload or a pasted reference list -> DocumentReports."""

import logging
import tempfile
from pathlib import Path

from .inputs import documents, to_pdf
from .models import DocumentReport
from .references import parse_reference_text, parse_references
from .verdict import check_reference

log = logging.getLogger(__name__)


def check_path(path):
    """Check every document in an upload: a PDF, DOC or DOCX, or a zip of them."""
    reports = []
    with tempfile.TemporaryDirectory() as tmp:
        for doc in documents(path, tmp):
            refs, method = parse_references(str(to_pdf(doc, Path(tmp) / "pdf")))
            log.info("%s: %d references via %s", doc.name, len(refs), method)
            reports.append(DocumentReport(doc.name, method, refs, [check_reference(r) for r in refs]))
    return reports


def check_text(text, name="pasted text"):
    """Check a pasted reference list, entries separated by blank lines. Read
    with the APA regex parser, so it needs no GROBID."""
    refs = parse_reference_text(text)
    return DocumentReport(name, "regex", refs, [check_reference(r) for r in refs])
