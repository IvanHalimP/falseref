"""Uploads -> PDF files: unpacking archives and converting Word documents."""

from .archive import SUPPORTED, documents
from .convert import to_pdf

__all__ = ["SUPPORTED", "documents", "to_pdf"]
