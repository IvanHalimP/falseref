"""Compressed uploads: a zip of submissions -> the documents inside it."""

import zipfile
from pathlib import Path

SUPPORTED = {".pdf", ".doc", ".docx"}


def documents(path, workdir):
    """-> [Path] of the documents in an upload. A zip is extracted into
    workdir and searched recursively; any other file is returned as is."""
    path, workdir = Path(path), Path(workdir)
    if path.suffix.lower() != ".zip":
        return [path]
    with zipfile.ZipFile(path) as z:
        z.extractall(workdir / "unzipped")
    return sorted(p for p in (workdir / "unzipped").rglob("*") if p.suffix.lower() in SUPPORTED)
