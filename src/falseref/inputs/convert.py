"""Word files are converted to PDF with headless LibreOffice, so every format
goes through the same PDF reader."""

import subprocess
from pathlib import Path


def to_pdf(path, outdir):
    """-> Path of a PDF for the document: the file itself if it is a PDF,
    else a conversion written to outdir (needs `soffice` on PATH)."""
    path, outdir = Path(path), Path(outdir)
    if path.suffix.lower() == ".pdf":
        return path
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(path)],
        check=True, capture_output=True, timeout=180,
    )
    return outdir / f"{path.stem}.pdf"
