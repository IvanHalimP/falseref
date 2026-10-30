"""Report generation: one row per reference, with what the reference says,
what the summed record says, and a check status per field:
ok / minor / major / not confirmed / no data / not checked."""

from dataclasses import asdict

import pandas as pd

from .matching import compare, field_scores
from .models import TIERS, rec_locator, rec_title, rec_venue, rec_year

# report field -> the compare() check it belongs to
FIELD_CHECK = {"authors": "authors", "title": "title", "year": "year", "venue": "venue",
               "volume": "locator", "issue": "locator", "pages": "locator", "doi": "doi", "url": "url"}
TIER_ORDER = ("verified", "partial", "none", "inconclusive", "genai")


def record_fields(rec):
    """Record -> the same fields a parsed reference has, as strings."""
    return {
        "authors": "; ".join(
            " ".join(filter(None, (a.get("given"), a.get("family")))) for a in rec.get("author", [])
        ),
        "title": rec_title(rec),
        "year": rec_year(rec) or "",
        "venue": rec_venue(rec) or rec.get("publisher") or "",
        "doi_or_url": f"https://doi.org/{rec['DOI']}" if rec.get("DOI") else "",
        **rec_locator(rec),
    }


def worst(sevs):
    return "major" if "major" in sevs else "minor" if "minor" in sevs else "ok"


def source_summary(sources):
    """"DOI: not given | URL: HTTP 200 confirmed (browser) | title: missing"."""
    return " | ".join(
        f"{s['name']}: " + (f"HTTP {s['http_status']} {s['state']}" if s.get("http_status") else s["state"])
        + (" (browser)" if s.get("browser") else "")
        for s in sources
    )


def field_status(f, result, cited, found, checked, url_src):
    check = FIELD_CHECK[f]
    # locator messages start with their field: "volume: 7 vs 8"
    sevs = [i.severity for i in result.issues
            if i.field == check and (check != "locator" or i.message.startswith(f))]
    if result.tier == "genai":
        return "not checked"
    if sevs or check in checked:
        return worst(sevs)
    if check == "title" and url_src.get("title_on_page") in ("heading", "text"):
        return "ok"
    if check in ("doi", "url") and cited[f] and found[f]:
        return "ok"
    return "not confirmed" if cited.get(f) else "no data"


def report_rows(refs, results):
    """-> [dict], one per reference, numbered from 1."""
    rows = []
    for i, (ref, v) in enumerate(zip(refs, results), 1):
        found = record_fields(v.rec) if v.rec else {}
        found["doi"] = v.rec.get("DOI") or ""
        url_src = next((s for s in v.sources if s["name"] == "URL"), {})
        found["url"] = url_src.get("final_url") or ""
        if not found.get("title") and url_src.get("title_on_page") in ("heading", "text", "slug"):
            found["title"] = url_src.get("page_title")
        cited = {**asdict(ref), "authors": "; ".join(ref.authors), "doi": v.doi, "url": v.url}
        checked = compare(ref, v.rec)[1] if v.rec else set()
        row = {"n": i, "tier": v.label, "sources": source_summary(v.sources),
               "url_http_status": url_src.get("http_status") or "", "url_http_meaning": url_src.get("http_meaning") or ""}
        for f in FIELD_CHECK:
            row[f"cited_{f}"] = cited.get(f) or ""
            row[f"found_{f}"] = found.get(f) or ""
            row[f"check_{f}"] = field_status(f, v, cited, found, checked, url_src)
        scores = field_scores(ref, v.rec) if v.rec else {}
        for k in ("sim_title", "sim_authors", "sim_venue", "year_gap"):
            row[k] = scores.get(k)
        row["issues"] = "; ".join(f"{i.message} [{i.severity}]" for i in v.issues)
        row["notes"] = "; ".join(v.notes + [f"citation: {c}" for c in v.citation])
        row["raw"] = ref.raw
        rows.append(row)
    return rows


def to_frame(documents):
    """[DocumentReport] -> one table, a row per reference, with a file column."""
    return pd.DataFrame([{"file": d.name, **r} for d in documents for r in report_rows(d.references, d.results)])


def write_csv(table, path):
    table.to_csv(path, index=False, encoding="utf-8-sig")  # BOM so Excel reads UTF-8


def http_status_counts(table):
    """How many cited URLs answered with each HTTP status."""
    return table[table.url_http_meaning != ""].value_counts(["url_http_status", "url_http_meaning"])


def summary(documents):
    """One line per document: reference count and how many fall in each tier."""
    lines = []
    for d in documents:
        counts = " ".join(f"{TIERS[t].split()[0]}{sum(v.tier == t for v in d.results)}" for t in TIER_ORDER)
        lines.append(f"{d.name[:60]:60} {len(d.results):3} refs  {counts}")
    return "\n".join(lines)
