"""Field-by-field comparison of a reference with a record.

Finding the work is fuzzy (sources.article.best_match), so a typo cannot make
a real work look fake. Once the work is identified, every field is compared
strictly and any difference is reported: a fuzzy field check would wave
through one wrong author or word."""

import difflib
import re

from rapidfuzz.distance import OSA

from ..models import Issue, rec_locator, rec_title, rec_venue, rec_year, show
from .similarity import (NAME_SIM, fold, initials, name_matches, name_sim, norm,
                         record_tokens, surname, title_sim, venue_sim)

TITLE_MINOR = 0.80  # below this title_sim, a changed title is a different title


def title_issues(cited, found):
    """-> [(severity, message)]."""
    a, b = norm(cited).split(), norm(found).split()
    if a == b:
        return []
    if b[: len(a)] == a:
        return [("minor", f"title truncated, record continues: {' '.join(b[len(a):])!r}")]
    if title_sim(cited, found) < TITLE_MINOR:
        return [("major", f"title: {cited!r} vs {found!r}")]
    issues = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        x, y = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        if op == "replace":
            # a misspelt word is minor; a different word is how titles get invented.
            # OSA counts swapped letters ("leanring") as one edit, not two
            typo = OSA.normalized_similarity(x, y) >= 0.8
            issues.append(("minor" if typo else "major", f"title words changed: {x!r} -> {y!r}"))
        elif op == "delete":
            issues.append(("minor", f"title has extra words: {x!r}"))
        elif op == "insert":
            issues.append(("minor", f"title missing words: {y!r}"))
    return issues


def author_issues(cited, rec):
    """-> [(severity, message)]. Pair each cited author with an unused record
    author, then report every difference: spelling, initials, reversed names,
    order and omissions."""
    people = [a for a in rec.get("author", []) if a.get("family")]
    if not people or not cited:
        return []
    issues, used = [], []
    for name in cited:
        s = fold(surname(name))
        free = [j for j in range(len(people)) if j not in used]

        def sim(j):
            # Crossref sometimes packs two tokens into family ("Junaid Hassan")
            toks = re.split(r"[\s.]+", fold(people[j]["family"]))
            return max(name_sim(s, t) for t in toks)

        j = max(free, key=sim, default=None)
        if j is None or sim(j) < NAME_SIM:
            # students reverse given/family ("K.Sanghun" for Sanghun Kim)
            j = next((k for k in free if s in re.split(r"[\s.]+", fold(people[k].get("given")))), None)
            if j is None:
                issues.append(("major", f"author not in record: {name}"))
                continue
            issues.append(("minor", f"author given/family reversed: {name} vs {show(people[j])}"))
        else:
            if sim(j) < 1:
                issues.append(("minor", f"author spelling: {name} vs {show(people[j])}"))
            mine = initials(" ".join(re.split(r"[\s.]+", name.strip())[:-1]))
            theirs = initials(people[j].get("given"))
            if mine and theirs and mine[: len(theirs)] != theirs[: len(mine)]:
                issues.append(("minor", f"author initials: {name} vs {show(people[j])}"))
        used.append(j)
    if not used:
        # none of them is in the record: one issue reads better than a
        # "not in record" for each plus a list of who is missing
        expected = "; ".join(show(p) for p in people[:5]) + ("; et al." if len(people) > 5 else "")
        return [("major", f"author mismatch: got {'; '.join(cited)!r}, expected {expected!r}")]
    if used != sorted(used):
        issues.append(("minor", "author order differs from record: " + ", ".join(show(people[j]) for j in sorted(used))))
    left = [show(people[j]) for j in range(len(people)) if j not in used]
    # APA 7 lists up to 20 authors; beyond that it elides, so omissions are expected
    if left and len(people) <= 20:
        issues.append(("minor", "authors missing from reference: " + ", ".join(left)))
    return issues


def locator_issues(ref, rec):
    """-> [(severity, message)] for volume, issue and pages. Messages start
    with the field name ("volume: 7 vs 8"); the report relies on that."""
    def key(p):
        return re.sub(r"pp?\.|article|\s", "", str(p).lower()).replace("–", "-").replace("—", "-").split("-")

    issues = []
    journal = rec_venue(rec)
    for f, sev in (("volume", "major"), ("issue", "minor"), ("pages", "major")):
        mine, theirs = getattr(ref, f), rec_locator(rec)[f]
        if f == "pages" and re.match(r"(?i)article", mine or ""):
            # article numbers are not page ranges; compare them only with each other
            theirs = rec.get("article-number")
        if theirs and not mine and journal:
            issues.append(("minor", f"{f} missing from reference (record: {theirs})"))
        if not (mine and theirs):
            continue
        a, b = key(mine), key(theirs)
        n = min(len(a), len(b))  # a record may give the first page only
        if len(b) == 2 and b[0] == b[1]:
            # IEEE metadata often holds a single page as "1015-1015"
            ok = b[0] in a
        else:
            ok = a[:n] == b[:n]
        if not ok:
            issues.append((sev, f"{f}: {mine} vs {theirs}"))
    return issues


def compare(ref, rec):
    """-> ([Issue], checked). checked holds the fields both sides carry, i.e.
    the checks that actually ran."""
    issues, checked = [], set()
    if ref.title and rec_title(rec):
        checked.add("title")
        issues += [Issue("title", s, m) for s, m in title_issues(ref.title, rec_title(rec))]

    found_year = rec_year(rec)
    cited_year = re.sub(r"\D", "", ref.year or "")[:4]
    if cited_year and found_year:
        checked.add("year")
        if cited_year != found_year:
            gap = abs(int(cited_year) - int(found_year))
            # online-first and issue years legitimately differ by one
            issues.append(Issue("year", "minor" if gap <= 1 else "major", f"year: {cited_year} vs {found_year}"))

    if ref.authors and any(a.get("family") for a in rec.get("author", [])):
        checked.add("authors")
    issues += [Issue("authors", s, m) for s, m in author_issues(ref.authors, rec)]

    venue = rec_venue(rec)
    if ref.venue and venue:
        checked.add("venue")
        if venue_sim(ref.venue, venue) < 0.80:
            # abbreviated venue names are common, so this alone is weak evidence
            issues.append(Issue("venue", "minor", f"venue: {ref.venue!r} vs {venue!r}"))

    if any(rec_locator(rec).values()):
        checked.add("locator")
    issues += [Issue("locator", s, m) for s, m in locator_issues(ref, rec)]
    return issues, checked


def major_count(ref, rec):
    """How many major discrepancies; used to pick the record that fits best."""
    return sum(i.severity == "major" for i in compare(ref, rec)[0])


def field_scores(ref, rec):
    """Field scores for the report: title and venue in 0-1, authors as the
    share of cited authors found in the record, year as the gap in years.
    None where either side lacks the field."""
    title, venue, year = rec_title(rec), rec_venue(rec), rec_year(rec)
    cited_year = re.sub(r"\D", "", ref.year or "")[:4]
    toks = record_tokens(rec)
    return {
        "sim_title": round(title_sim(ref.title, title), 2) if ref.title and title else None,
        "sim_authors": round(sum(name_matches(n, toks) for n in ref.authors) / len(ref.authors), 2)
        if ref.authors and toks else None,
        "sim_venue": round(venue_sim(ref.venue, venue), 2) if ref.venue and venue else None,
        "year_gap": abs(int(cited_year) - int(year)) if cited_year and year else None,
    }
