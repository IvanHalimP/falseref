"""Text clean-up shared by the reference parsers."""

import re

# Volume, issue and pages as APA writes them: "Journal, 57(3), 47-66." or
# "Scientific Reports, 14, Article 12345." Read from the raw entry so the GROBID
# and regex paths agree.
LOCATOR = re.compile(
    r",\s*(\d{1,5})\s*(?:\(([^)]{1,15})\))?\s*,\s*"
    r"((?:pp?\.\s*|Article\s+)?[A-Za-z]?\d+(?:\s*[-–—]\s*[A-Za-z]?\d+)?)"
)


def locator(entry):
    """-> {"volume", "issue", "pages"}, None where the entry has no APA locator."""
    m = LOCATOR.search(re.sub(r"https?://\S+", "", entry))
    return dict(zip(("volume", "issue", "pages"), m.groups() if m else (None,) * 3))


def find_url(entry):
    """First link in an entry. MLA drops the scheme ("www.keyway.ai/blog/..."),
    and capitalised "Www.site.com" there is the site name, not the link."""
    m = re.search(r"https?://\S+|(?<![\w.])www\.\S+", entry)
    if not m:
        return None
    url = m.group(0).rstrip(".,;")
    return url if url.startswith("http") else "https://" + url


def rejoin_urls(text):
    """PDFs wrap long URLs after a hyphen, slash or dot: "the-role- of-ai",
    "global/en/ products", "www. salesforce.com". One URL can break twice.
    MLA drops the scheme, so "www." starts a URL too."""
    while True:
        new = re.sub(r"((?:https?://|www\.)\S*-)\s+(?=[A-Za-z0-9])", r"\1", text)
        new = re.sub(r"((?:https?://|www\.)\S*[/.])\s+(?=[a-z0-9])", r"\1", new)
        if new == text:
            return text
        text = new
