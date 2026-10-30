"""Normalisation and similarity scores for titles, names and venues."""

import difflib
import re
import unicodedata

from rapidfuzz.distance import Indel, JaroWinkler, Levenshtein

# Student references are often imperfect: initials only, a dropped co-author,
# a typo in the title. Differences are graded instead of all called mismatches.
NAME_SIM = 0.90
STOP = {"a", "an", "and", "de", "for", "in", "of", "on", "the", "und"}


def norm(s):
    """Lowercase words only, for comparing titles and page text."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)                # Crossref titles carry <i>, <sub> tags
    s = s.replace("&", " and ")
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)      # rejoin words broken across lines
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def fold(s):
    """Lowercase without accents, so Müller and Muller compare equal."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()


def surname(name):
    parts = [p for p in re.split(r"[\s.]+", name) if p]
    return parts[-1].lower() if parts else ""


def initials(given):
    return "".join(p[0] for p in re.split(r"[\s.\-]+", fold(given)) if p)


def ratio(a, b):
    """Loose title similarity, for finding the work: tolerates a dropped subtitle."""
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def title_sim(a, b):
    """Normalised Levenshtein: every changed letter costs one edit. Stricter
    than ratio(), which finds the work and so tolerates a dropped subtitle."""
    return Levenshtein.normalized_similarity(norm(a), norm(b))


def name_sim(a, b):
    """Jaro-Winkler, made for short names: it weights the shared prefix, so
    Hassan/Hasan (0.96) and Muller/Mueller (0.92) pass, Zhang/Zhong (0.89) and
    Wang/Wong (0.85) do not."""
    return JaroWinkler.normalized_similarity(fold(a), fold(b))


def venue_sim(a, b):
    """Journal names are abbreviated ("IEEE Trans. Pattern Anal. Mach. Intell.",
    ISO 4) or cut to an acronym ("JAMA"); either form is a full match. Otherwise
    Indel similarity of the content words."""
    a, b = ([w for w in norm(s).split() if w not in STOP] for s in (a, b))
    for x, y in ((a, b), (b, a)):
        if len(x) == len(y) and all(w.startswith(v) for v, w in zip(x, y)):
            return 1.0
        if len(x) == 1 and len(y) >= 2 and x[0] == "".join(w[0] for w in y):
            return 1.0
    return Indel.normalized_similarity(" ".join(a), " ".join(b))


def record_tokens(rec):
    """Every name token in a record. Crossref sometimes packs two tokens into
    "family" (e.g. "Junaid Hassan"), and students reverse given/family order
    ("K.Sanghun" for Sanghun Kim), so given names count too."""
    return {
        tok
        for a in rec.get("author", [])
        for field in (a.get("family"), a.get("given"))
        for tok in re.split(r"[\s.]+", (field or "").lower())
        if tok
    }


def name_matches(ref_name, rec_tokens):
    """Does a cited author's surname appear among a record's name tokens?"""
    s = surname(ref_name)
    if not s:
        return True
    return any(
        tok == s or name_sim(tok, s) >= NAME_SIM
        for tok in rec_tokens
    )
