"""Network-free comparison of a reference with a record."""

from .compare import compare, field_scores, major_count, title_issues
from .similarity import name_matches, norm, ratio, record_tokens

__all__ = ["compare", "field_scores", "major_count", "title_issues",
           "name_matches", "norm", "ratio", "record_tokens"]
