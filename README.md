# falseref

Flags references in student submissions that do not exist or are cited wrongly. It uses rules only, with no LLM.

Every identifier a reference gives is checked, not just one of them:

| identifier | checked against |
|---|---|
| DOI | Crossref, or doi.org for DataCite DOIs (arXiv, Zenodo) |
| URL | the live page: does it load, does it show the cited title, what its bibliographic `<meta>` tags say. Pages that block plain requests or render their text with JavaScript are read again in headless Chromium (Playwright) |
| title | Crossref + OpenAlex search |

What the lookups find about the cited work is summed into one record. The cited authors, title, year, venue, volume/issue/pages, DOI and URL are then compared with that record.

## Setup

```bash
pip install -e ".[test,browser]"
playwright install chromium                           # optional: browser for blocked/JavaScript pages
docker run --rm --init -p 8070:8070 grobid/grobid:0.8.2   # reads references out of PDFs
sudo apt install libreoffice                          # only for .doc/.docx
```

GROBID is expected at `http://localhost:8070`; set `GROBID_URL` to use another server. Without GROBID, APA references are still read with a regex parser. A pasted reference list never needs GROBID. Without Playwright, a blocked page counts as ❓ (no evidence either way), and a JavaScript page may not show the cited title.

## Usage

Command line, for a PDF/DOC/DOCX or a zip of them:

```bash
falseref submissions.zip -o reference_report.csv
```

Python:

```python
from falseref import check_path, check_text, to_frame, summary

reports = check_path("submissions.zip")     # one DocumentReport per file
print(summary(reports))
to_frame(reports).to_csv("report.csv", index=False)

check_text(pasted_reference_list)            # entries separated by blank lines
```

[demo.ipynb](demo.ipynb) walks through a pasted list, then one reference step by step, then a batch of submissions.

## Tiers

| tier | meaning |
|---|---|
| ✅ Verified | the work was found and the citation matches it |
| ⚠️ Exists, citation errors | the work was found, but a field has a major discrepancy |
| 🚩 No match found | nothing shows the work exists, or a cited DOI/URL is dead, redirects away, or belongs to another work |
| ❓ Inconclusive | a lookup was blocked or failed, or a book's year differs (reprint or later edition?) |
| 🤖 GenAI tool | output of a generative AI tool: listed, not checked |

The tier answers two questions in order. Does the cited work exist? A page showing the cited title, or a record carrying it, counts as yes. Is it cited correctly? Any **major** discrepancy (changed title words, an author not in the record, a year gap over one, a wrong volume or pages, a wrong DOI) makes it ⚠️. **Minor** ones (typos, initials, a missing co-author, a year off by one, an abbreviated venue) are reported but do not change the tier. Citation-quality problems, such as citing a database instead of the journal (APA 7 §9.30) or linking to a sharing platform or a bare domain, are listed in the notes and never change the tier.

## Report columns

One row per reference. For each field (authors, title, year, venue, volume, issue, pages, doi, url):
`cited_<field>` is what the reference says, `found_<field>` is what the sources say, and `check_<field>` is
`ok`, `minor`, `major`, `not confirmed` (the reference states it and no source lists it), `no data` or `not checked`.
`sources` summarises each lookup, `sim_*`/`year_gap` give similarity scores, `issues` lists every discrepancy,
and `notes` says what could not be found or confirmed.

## Layout

```
src/falseref/
  models.py            Reference, CheckResult, Issue, DocumentReport, TIERS; the Crossref-shaped record
  pipeline.py          check_path(upload), check_text(text)
  report.py            report generation: rows, CSV, per-file summary
  cli.py               the `falseref` command
  inputs/              uploads -> PDFs
    archive.py           compressed files: a zip -> the documents in it
    convert.py           .doc/.docx -> PDF via LibreOffice
  references/          document handling: PDF or text -> [Reference]
    layout.py            cuts the reference list into entries from the page layout (PyMuPDF)
    grobid.py            GROBID: parses each entry; finds the list when there is no heading
    apa.py               APA regex parser: GROBID fallback and pasted lists
    identifiers.py       the DOI and URL a reference gives
    text.py              URL rejoining, locator (volume/issue/pages) parsing
  matching/            network-free comparison
    similarity.py        normalisation; title, name and venue similarity
    compare.py           field-by-field discrepancies, graded minor/major
  sources/             lookups that authenticate a reference
    article.py           academic articles: DOI -> Crossref/doi.org; title -> Crossref + OpenAlex
    web.py               web sources: page fetch, title on page, <meta> tags
    browser.py           headless Chromium for blocked and JavaScript pages (optional)
    http.py              GET with rate-limit retries
  verdict/             combining the lookups
    decide.py            sums the records, finds discrepancies, picks the tier
    genai.py             references to generative AI tools
    citation.py          citation-quality rules, grey-literature heuristic
```
<!---
There are no import cycles: `pipeline → verdict → sources → matching → models`, and `references` depends only on `models`. `matching` never touches the network, which is what lets the tests run offline.

## Tests

```bash
pytest                       # offline: parsing, comparison, tier rules (lookups stubbed)
python scripts/regression_check.py ../try_grobid.ipynb ../Re__Referencing_Mistakes.zip
```

The regression check runs the original notebook's checker and this package on the same upload, and diffs the two reports. HTTP responses from the notebook run are recorded and replayed to the package, so any difference comes from the code. The browser is off during the check, because the notebook had none and browser traffic cannot be replayed.
-->
