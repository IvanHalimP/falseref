"""Lookups that authenticate a reference. Each returns a Source dict (see models)."""

from .article import doi_source, title_source
from .web import url_source

__all__ = ["doi_source", "title_source", "url_source"]
