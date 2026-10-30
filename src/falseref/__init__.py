"""falseref: flags references that do not exist or are cited wrongly.

    from falseref import check_path, to_frame
    reports = check_path("submissions.zip")
    to_frame(reports)
"""

from .models import TIERS, CheckResult, DocumentReport, Issue, Reference
from .pipeline import check_path, check_text
from .report import http_status_counts, summary, to_frame, write_csv
from .verdict import check_reference

__all__ = [
    "check_path", "check_text", "check_reference",
    "to_frame", "write_csv", "summary", "http_status_counts",
    "Reference", "CheckResult", "Issue", "DocumentReport", "TIERS",
]
